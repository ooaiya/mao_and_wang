"""Check the recorded online decisions, first execution and freezer ordering."""

import json
from mmap import PAGESIZE

from raster_priority import RASTER, raster_events
from realtime_policy import FOREGROUND, RealtimePolicy, Settings


def check_joint_budget(row, running, ticks, recovery, settings, priorities):
    decision = row['decision']
    readings = row['readings']
    growth = {name: max(0, readings[name]['high'] - readings[name]['anon']) for name in running}
    required = {}
    if not decision['pressure'] and all(readings[name]['started'] for name in running):
        base = recovery + sum(growth.values()) + settings.step_bytes
        required = {name: base + readings[name]['current'] - readings[name]['anon']
                    + decision['retry_extra_bytes'].get(name, 0) for name in row['frozen_since']}
    if (decision['recovery_bytes'] != recovery or decision['running_growth_bytes'] != growth
            or decision['resume_required_bytes'] != required):
        return 'joint memory budget differs from recorded readings'
    since = decision['resume_since_s']
    if since.keys() != {op for op, need in required.items() if decision['available_bytes'] >= need}:
        return 'resume eligibility differs from joint memory budget'
    now = row['monotonic_s']
    ready = [name for name, start in since.items() if now - start >= settings.stable_s
             and now - row['frozen_since'][name] >= settings.retry_cooldown_s]
    proposed = decision['resume']
    if proposed != max(ready, key=priorities.__getitem__, default=None):
        return 'resume priority differs from the eligible candidates'
    if proposed is None:
        return None
    start = since[proposed]
    if (decision['resume_budget_since_s'] != start or not decision['stable']
            or decision['limits'] != {proposed: readings[proposed]['current'] + settings.step_bytes}):
        return 'resume lacks a stable budget or the requested trial limit'
    window = [tick for tick in reversed(ticks.values()) if tick['monotonic_s'] >= start]
    if (window[-1]['monotonic_s'] != start
            or any(tick['decision']['resume_since_s'].get(proposed) != start for tick in window)
            or any(tick['limits'] or tick['frozen'] or tick['resumed'] for tick in window[1:])
            or any(first['monotonic_s'] - second['monotonic_s'] > settings.max_sample_gap_s
                   for first, second in zip(window, window[1:]))):
        return 'resume window crosses an action, an eligibility loss or a sample gap'
    return None


def audit(root, plan, summary, freezes):
    errors = []
    settings = Settings(**plan['settings'])
    policy = RealtimePolicy(settings, plan['budget']['memtotal_bytes'])
    priorities = plan['priorities']
    joint = plan['schema'] == 'oomlab-realtime-freezer-v2'
    if plan['budget']['reserve_bytes'] != policy.reserve:
        errors.append('memory reserve disagrees with the configured policy')
    if summary['runtime_policy']['watchdog_error']:
        errors.append('watchdog failed')

    starts = {}
    t0 = summary['T0_monotonic_ns']
    for op in priorities:
        record = summary['tasks'][op]
        if op == RASTER:
            start = next((row['monotonic_ns'] for row in raster_events(root / op / 'process.log')
                          if row['event'] == 'tile_background_start'), None)
        else:
            with (root / op / 'phase_trace.jsonl').open(encoding='utf-8') as stream:
                events = (json.loads(line) for line in stream)
                start = next((row['monotonic_ns'] for row in events if row['event_type'] == 'task_start'), None)
        starts[op] = start
        release = record['release_confirmed_ns']
        cap = record['initial_memory_high']
        nominal = t0 + round(plan['alignment']['offsets_s'][op] * 1e9)
        if (start is None or start != record.get('actual_start_ns')
                or not nominal <= record['created_ns'] <= cap['confirmed_ns'] <= release <= start
                or cap['requested_bytes'] < settings.step_bytes
                or abs(cap['applied_bytes'] - cap['requested_bytes']) >= PAGESIZE):
            errors.append(f'{op}: invalid first start or initial memory.high evidence')

    ticks = {}
    previous_stamp = 0.
    with (root / 'realtime_decisions.jsonl').open(encoding='utf-8') as stream:
        for tick, line in enumerate(stream, 1):
            row = json.loads(line)
            now = row['monotonic_s']
            decision = row['decision']
            available = decision['available_bytes']
            urgent, _, _ = policy.thresholds(now, available)
            if (row['tick'] != tick or now <= previous_stamp
                    or not 0 <= now - row['sample_started_s'] <= settings.sample_interval_s
                    or urgent != decision['urgent_bytes'] or available < settings.emergency_bytes):
                errors.append(f'tick {tick}: invalid sample or pressure threshold')
            previous_stamp = now
            ticks[tick] = row
            running = {op for op, reading in row['readings'].items()
                       if op in priorities and reading['state'] == 'RUNNING'}
            if row['frozen']:
                started = {op for op in running if row['readings'][op]['started']}
                expected = min(started, key=priorities.__getitem__, default=None)
                if available >= urgent or row['frozen'] != expected or row['frozen'] != decision['freeze']:
                    errors.append(f'tick {tick}: pressure victim differs from the lowest running priority')
            if joint:
                error = check_joint_budget(row, running, ticks, urgent + settings.recovery_bytes, settings, priorities)
                if error:
                    errors.append(f'tick {tick}: {error}')
                if row['resumed'] and row['resumed'] != decision['resume']:
                    errors.append(f'tick {tick}: thaw differs from approved candidate')
            elif row['resumed']:
                op = row['resumed']
                required = urgent + settings.recovery_bytes + settings.step_bytes
                required += decision['retry_extra_bytes'].get(op, 0)
                if (running or op != decision['resume'] or available < required or not decision['stable']
                        or now - decision['resume_budget_since_s'] < settings.stable_s
                        or now - row['frozen_since'][op] < settings.retry_cooldown_s):
                    errors.append(f'tick {tick}: thaw lacks an isolated, stable budget')
            for op, cap in row['limits'].items():
                if (op not in priorities or cap['requested_bytes'] != decision['limits'].get(op)
                        or abs(cap['applied_bytes'] - cap['requested_bytes']) >= PAGESIZE):
                    errors.append(f'tick {tick}: invalid memory.high write for {op}')
            for op, deadline in row['renewed'].items():
                if (op not in running or not row['readings'][op]['started'] or available < urgent
                        or deadline != now + settings.lease_s):
                    errors.append(f'tick {tick}: invalid lease renewal for {op}')

    if not ticks or len(ticks) != summary['runtime_policy']['guard_samples']:
        errors.append('missing real-time control samples')
    expected_actions = {(tick, row[action], event) for tick, row in ticks.items()
                        for action, event in [('frozen', 'freeze'), ('resumed', 'resume')] if row[action]}
    matched = set()
    freeze_delays_ms = []
    reaction_ms = []
    for proof in freezes:
        op = proof['operation']
        requested = proof['requested_monotonic_ns']
        confirmed = proof['confirmed_monotonic_ns']
        action = proof['action']
        if (op == FOREGROUND or starts.get(op) is None or not starts[op] <= requested <= confirmed
                or proof['events']['frozen'] != int(action == 'freeze')):
            errors.append(f'{op}: freezer transition precedes actual start or lacks kernel confirmation')
        if action == 'freeze':
            freeze_delays_ms.append((confirmed - requested) / 1e6)
            if proof['admission']['actual_start_ns'] != starts.get(op):
                errors.append(f'{op}: freeze has a different workload start timestamp')
        if proof['reason'] == 'realtime_lease_expired':
            if action != 'freeze' or requested / 1e9 < proof['admission']['prior_lease_s']:
                errors.append(f'{op}: watchdog froze before the lease deadline')
            continue
        key = (proof['decision_tick'], op, action)
        if key not in expected_actions or key in matched:
            errors.append(f'{op}: unexpected transition at tick {key[0]}')
            continue
        matched.add(key)
        row = ticks[key[0]]
        if action == 'freeze':
            reaction_ms.append((confirmed / 1e9 - row['sample_started_s']) * 1000)
        else:
            cap = row['limits'].get(op)
            if (cap is None or not cap['confirmed_ns'] <= requested
                    or requested / 1e9 >= proof['lease_until_monotonic_s']):
                errors.append(f'{op}: thaw preceded its soft limit or used an expired lease')
    if matched != expected_actions:
        errors.append('missing confirmed freezer transitions')
    return dict(errors=errors, ticks=len(ticks), memory_high_writes=len(starts) + sum(len(r['limits']) for r in ticks.values()),
                max_freeze_confirmation_ms=max(freeze_delays_ms, default=None),
                max_pressure_sample_to_freeze_ms=max(reaction_ms, default=None),
                freeze_count=len(freeze_delays_ms))
