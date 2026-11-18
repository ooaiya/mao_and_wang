"""Preserve kernel OOM evidence; unavailable logs never mean zero OOM."""
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import time

OOM_PATTERN = re.compile(r'out of memory|oom-kill|killed process', re.I)


def _capture(command, raw):
    diagnostic = dict(source=command[0], command=command, raw_file=str(raw))
    try:
        with raw.open('w') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE,
                                    text=True, timeout=10)
        diagnostic.update(returncode=result.returncode, stderr=(result.stderr or '').strip())
        if result.returncode:
            diagnostic.update(status='FAILED', error=diagnostic['stderr'] or
                              'command exited with status '+str(result.returncode))
        else:
            diagnostic['status'] = 'READABLE'
    except (OSError, subprocess.TimeoutExpired) as error:
        diagnostic.update(status='FAILED', returncode=None, error=repr(error))
    return diagnostic


def _journal_entries(raw):
    entries = []
    for number, line in enumerate(raw.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError as error:
            raise ValueError('journal JSON parse failure at line '+str(number)) from error
        if not isinstance(value, dict):
            raise ValueError('journal record is not an object at line '+str(number))
        entries.append(value)
    return entries


def _window_start(timeline, wall_start_ns):
    for row in getattr(timeline, 'rows', ()):
        if row.get('event_type') == 'runner_start':
            return row['actual_monotonic_ns'], 'recorded runner_start CLOCK_MONOTONIC'
    # Used by standalone callers lacking Runner events. Preserve the clock
    # mapping method rather than claiming an exact kernel transition timestamp.
    wall = time.time_ns()
    mono = time.monotonic_ns()
    return mono-(wall-wall_start_ns), 'collection wall/monotonic clock mapping'


def _dmesg_entries(raw, start_ns):
    entries = []
    parsed = 0
    nonempty = 0
    for line in raw.read_text().splitlines():
        if not line.strip():
            continue
        nonempty += 1
        matched = re.search(r'\[\s*(\d+(?:\.\d+)?)\]\s*(.*)', line)
        if not matched:
            # Never silently ignore an OOM-looking line whose time cannot be
            # associated with this run.
            if OOM_PATTERN.search(line):
                raise ValueError('dmesg OOM record has no usable raw timestamp')
            continue
        parsed += 1
        stamp = int(Decimal(matched[1])*1_000_000_000)
        if stamp >= start_ns:
            entries.append(dict(MESSAGE=matched[2], _MONOTONIC_NS=stamp))
    if nonempty and not parsed:
        raise ValueError('dmesg raw timestamps could not be parsed')
    return entries


def _record(entries, timeline, operations, sink, source):
    kills = 0
    candidates = 0
    for entry in entries:
        message = entry.get('MESSAGE', '')
        if not isinstance(message, str) or not OOM_PATTERN.search(message):
            continue
        candidates += 1
        matched = re.search(r'Killed process\s+(\d+)', message, re.I)
        pid = int(matched[1]) if matched else None
        stamp = entry.get('__MONOTONIC_TIMESTAMP')
        note = 'journal CLOCK_MONOTONIC'
        try:
            now = entry['_MONOTONIC_NS'] if source == 'dmesg' else int(stamp)*1000
            if source == 'dmesg':
                note = 'dmesg raw kernel timestamp'
        except (TypeError, ValueError):
            now = time.monotonic_ns()
            note = 'collector observation fallback'
        operation = ''
        for name, info in operations.items():
            group = info.get('cgroup_path')
            if ((pid and pid == info.get('pid')) or
                    (group and str(group).removeprefix('/sys/fs/cgroup') in message)):
                operation = name
                break
        scope = ('kernel_cgroup' if re.search(r'memory cgroup|constraint=CONSTRAINT_MEMCG',
                                             message, re.I)
                 else 'kernel_global_or_unclassified')
        if matched:
            kills += 1
        sink.write(dict(monotonic_ns=now,
                        relative_T0_s=(now-timeline.t0_ns)/1e9 if timeline.t0_ns is not None else None,
                        scope=scope, operation=operation,
                        counter='kernel_kill_record' if matched else 'kernel_oom_candidate',
                        delta=1, value=None, killed_pid=pid, evidence=message))
        timeline.emit('OOM_kernel_observation', operation, actual_ns=now, pid=pid,
                      scope=scope, message=message, source_timestamp=note)
    return dict(status='OBSERVED',
                assessment='OOM_CONFIRMED' if candidates else 'NO_OOM_FOUND',
                candidate_messages=candidates, confirmed_kill_records=kills,
                attempt_count=None,
                attempt_count_reason='related kernel messages are preserved, not falsely summed as distinct OOM attempts',
                log_source=source, logs_accessible=True)


def collect(output, timeline, operations, wall_start_ns, sink):
    output = Path(output)
    attempts = []
    raw = output/'kernel_journal.jsonl'
    command = ['journalctl', '-k', '--output=json', '--no-pager',
               '--since', f'@{wall_start_ns/1e9:.6f}']
    attempt = _capture(command, raw)
    attempts.append(attempt)
    if attempt['status'] == 'READABLE':
        try:
            entries = _journal_entries(raw)
        except (OSError, ValueError) as error:
            attempt.update(status='FAILED', error=repr(error))
        else:
            evidence = _record(entries, timeline, operations, sink, 'journalctl')
            evidence.update(collection_attempts=attempts, coverage='queried kernel journal window')
            return evidence

    # No sudo, sysctl change or OOM injection. This succeeds only if the
    # current process already has permission to read the kernel ring buffer.
    raw = output/'kernel_dmesg.txt'
    attempt = _capture(['dmesg', '--color=never', '--time-format=raw'], raw)
    attempts.append(attempt)
    if attempt['status'] == 'READABLE':
        try:
            start, alignment = _window_start(timeline, wall_start_ns)
            entries = _dmesg_entries(raw, start)
        except (OSError, ValueError) as error:
            attempt.update(status='FAILED', error=repr(error))
        else:
            evidence = _record(entries, timeline, operations, sink, 'dmesg')
            evidence.update(collection_attempts=attempts,
                            journalctl_failure=attempts[0].get('error'),
                            dmesg_alignment=alignment,
                            coverage='retained current-boot kernel ring buffer, filtered to run window')
            return evidence
    reason = '; '.join(a['source']+': '+a.get('error', 'log unavailable') for a in attempts)
    return dict(status='UNAVAILABLE', assessment='UNKNOWN', reason=reason,
                confirmed_kill_records=None, candidate_messages=None,
                attempt_count=None, logs_accessible=False,
                collection_attempts=attempts)
