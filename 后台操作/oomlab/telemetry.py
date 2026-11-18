"""Shared bounded-frequency cgroup/proc collection. Unknown is never zero."""
import csv
import json
import os
import time
from pathlib import Path
from .common import meminfo, save_json
from .metrics import STATS, EVENTS
from .events import Events

CSV_NAMES = ('memory_trace', 'cpu_trace', 'io_trace', 'process_memory', 'process_faults',
             'psi_system', 'psi_cgroup', 'low_memory_trace', 'memory_events')
COLUMNS = ('monotonic_ns', 'relative_s', 'task_id', 'device', 'metric', 'value',
           'status', 'delta', 'rate_per_s')


def optional_text(path):
    try:
        return Path(path).read_text(), 'supported'
    except FileNotFoundError:
        return None, 'unsupported'
    except (PermissionError, ProcessLookupError, OSError):
        return None, 'unavailable'


def pairs_text(raw):
    if raw is None:
        return {}
    return {a: int(b) for a, b in (line.split() for line in raw.splitlines())}


def pressure(raw):
    return {line.split()[0]+'.'+key: (int(value) if key == 'total' else float(value))
            for line in (raw or '').splitlines()
            for key, value in (item.split('=') for item in line.split()[1:])}


def identity(pid, proc=Path('/proc'), pss=False):
    """Read identity twice so PID reuse cannot combine two process instances."""
    root = proc / str(pid)
    raw = (root / 'stat').read_text()
    fields = raw[raw.rfind(')')+2:].split()
    status = dict(line.split(':', 1) for line in (root / 'status').read_text().splitlines())
    start = int(fields[19])
    result = dict(pid=int(pid), starttime=start, ppid=int(fields[1]), state=fields[0],
                  comm=raw[raw.find('(')+1:raw.rfind(')')],
                  uid=int(status['Uid'].split()[0]), gid=int(status['Gid'].split()[0]),
                  threads=int(status['Threads']), cmdline=(root / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'),
                  cgroup=(root / 'cgroup').read_text().strip(),
                  create_boottime_s=start / os.sysconf('SC_CLK_TCK'),
                  minor_faults=int(fields[7]), major_faults=int(fields[9]))
    for key in ('VmRSS', 'RssAnon', 'RssFile', 'RssShmem', 'VmSwap',
                'voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches'):
        words = status.get(key, '').split()
        result[key] = int(words[0]) * (1024 if len(words)>1 and words[1]=='kB' else 1) if words else None
    result['Pss'] = None
    result['pss_status'] = 'not_sampled'
    if pss:
        raw_pss, result['pss_status'] = optional_text(root / 'smaps_rollup')
        if raw_pss:
            for line in raw_pss.splitlines():
                if line.startswith('Pss:'):
                    result['Pss'] = int(line.split()[1])*1024
    again = (root / 'stat').read_text()
    if int(again[again.rfind(')')+2:].split()[19]) != start:
        raise ProcessLookupError('PID 已复用')
    return result


class LowMemory:
    def __init__(self, enter, exit):
        if not 0 <= enter < exit:
            raise ValueError('低内存退出阈值必须大于进入阈值')
        self.enter, self.exit = enter, exit
        self.active, self.count, self.duration_s = False, 0, 0.0
        self.last_ns = None

    def sample(self, available, stamp):
        if self.last_ns is not None and self.active:
            self.duration_s += (stamp-self.last_ns)/1e9
        if available is not None:
            if not self.active and available < self.enter:
                self.active = True
                self.count += 1
            elif self.active and available >= self.exit:
                self.active = False
        self.last_ns = stamp
        return self.active


class Collector:
    def __init__(self, directory, epoch_ns=None, enter_bytes=1024**3, exit_bytes=1536*1024**2,
                 process_interval_s=1.0, pss_interval_s=5.0):
        if process_interval_s < .2 or pss_interval_s < 1:
            raise ValueError('进程/PSS 采样频率过高')
        self.directory = Path(directory)
        self.epoch = epoch_ns or time.monotonic_ns()
        self.files, self.writers = {}, {}
        for name in CSV_NAMES:
            f = open(self.directory / (name+'.csv'), 'x', newline='')
            self.files[name] = f
            self.writers[name] = csv.DictWriter(f, COLUMNS)
            self.writers[name].writeheader()
        self.lifecycle = Events(self.directory / 'process_lifecycle.jsonl', epoch_ns=self.epoch)
        self.identities = Events(self.directory / 'process_identity.jsonl', epoch_ns=self.epoch)
        self.seen, self.previous = {}, {}
        self.proc_period, self.pss_period = process_interval_s, pss_interval_s
        self.last_proc, self.last_pss = 0, 0
        self.low = LowMemory(enter_bytes, exit_bytes)
        self.samples, self.cost_ns, self.max_cost_ns, self.cpu_cost_ns = 0, 0, 0, 0
        self.minimum_available, self.max_gap_ns, self.last_stamp = None, 0, None
        self.unsupported = set()
        self.errors = []

    def record(self, file, stamp, task, metric, value, status='supported', device='', cumulative=False):
        if value is None:
            status = 'unsupported' if status == 'supported' else status
            self.unsupported.add((task, metric, status))
        delta = rate = None
        key = (file, task, device, metric)
        if cumulative and value is not None:
            previous = self.previous.get(key)
            if previous:
                old, old_ns = previous
                if value < old:
                    status = 'counter_reset'
                    self.errors.append({'task_id':task, 'metric':metric, 'error':'counter_reset'})
                elif stamp > old_ns:
                    delta, rate = value-old, (value-old)*1e9/(stamp-old_ns)
            self.previous[key] = (value, stamp)
        self.writers[file].writerow(dict(monotonic_ns=stamp, relative_s=(stamp-self.epoch)/1e9,
            task_id=task, device=device, metric=metric, value=value, status=status,
            delta=delta, rate_per_s=rate))

    def _psi(self, file, root, task, stamp, system=False):
        for kind in ('memory', 'cpu', 'io'):
            raw, status = optional_text(root / (kind if system else kind+'.pressure'))
            values = pressure(raw)
            for level in ('some', 'full'):
                for field in ('avg10', 'avg60', 'avg300', 'total'):
                    key = level+'.'+field
                    self.record(file, stamp, task, kind+'.'+key, values.get(key), status,
                                cumulative=field=='total')

    def _group(self, task, root, stamp):
        root = Path(root)
        stat_raw, stat_status = optional_text(root / 'memory.stat')
        stats = pairs_text(stat_raw)
        for key in STATS:
            self.record('memory_trace', stamp, task, 'stat_'+key, stats.get(key), stat_status,
                        cumulative=key.startswith(('pg', 'workingset_')))
        for key in ('memory.current', 'memory.peak', 'memory.max', 'memory.high',
                    'memory.swap.current', 'memory.swap.max'):
            raw, status = optional_text(root / key)
            value = ('max' if raw.strip()=='max' else int(raw)) if raw is not None else None
            self.record('memory_trace', stamp, task, key, value, status)
        for filename in ('memory.events', 'memory.events.local'):
            raw, status = optional_text(root / filename)
            values = pairs_text(raw)
            for key in EVENTS:
                self.record('memory_events', stamp, task, filename+'.'+key, values.get(key), status, cumulative=True)
        raw, status = optional_text(root / 'cpu.stat')
        cpu = pairs_text(raw)
        previous_cpu=self.previous.get(('cpu_trace',task,'','usage_usec'))
        cpu_percent=None
        if previous_cpu and cpu.get('usage_usec') is not None and stamp>previous_cpu[1] and cpu['usage_usec']>=previous_cpu[0]:
            cpu_percent=(cpu['usage_usec']-previous_cpu[0])*100000/(stamp-previous_cpu[1])
        self.record('cpu_trace',stamp,task,'cpu_percent',cpu_percent,'not_sampled' if previous_cpu is None else status)
        for key in ('usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec'):
            self.record('cpu_trace', stamp, task, key, cpu.get(key), status, cumulative=True)
        # usage_usec rate / 10000 = CPU percent, 100% means one CPU core.
        raw, status = optional_text(root / 'io.stat')
        if raw is None or not raw.strip():
            self.record('io_trace', stamp, task, 'io.stat', None, status if raw is None else 'no_devices')
        else:
            for line in raw.splitlines():
                device, *items = line.split()
                values = dict(item.split('=') for item in items)
                for key in ('rbytes', 'wbytes', 'rios', 'wios'):
                    self.record('io_trace', stamp, task, key, int(values[key]) if key in values else None,
                                status, device=device, cumulative=True)
        self._psi('psi_cgroup', root, task, stamp)

    def _processes(self, groups, stamp, pss):
        current = {}
        for task, group in groups.items():
            # Descendants inherit service cgroup. Include delegated subgroups if present.
            paths = [Path(group) / 'cgroup.procs', *Path(group).glob('**/cgroup.procs')]
            pids = set()
            for path in paths:
                raw, status = optional_text(path)
                if raw:
                    pids.update(int(pid) for pid in raw.split())
            for pid in pids:
                try:
                    item = identity(pid, pss=pss)
                except (OSError, ValueError, KeyError) as e:
                    self.lifecycle.emit('process_observation_unavailable', task_id=task, pid=pid, error=str(e))
                    continue
                key = (task, pid, item['starttime'])
                current[key] = item
                self.identities.emit('process_identity', task_id=task, **item)
                if key not in self.seen:
                    self.lifecycle.emit('process_observed', task_id=task, **item)
                for metric in ('VmRSS', 'RssAnon', 'RssFile', 'RssShmem', 'VmSwap', 'Pss'):
                    self.record('process_memory', stamp, task, metric, item[metric],
                                item['pss_status'] if metric=='Pss' else 'supported', device=f'{pid}:{item["starttime"]}')
                for metric in ('minor_faults', 'major_faults', 'voluntary_ctxt_switches', 'nonvoluntary_ctxt_switches'):
                    self.record('process_faults', stamp, task, metric, item[metric], device=f'{pid}:{item["starttime"]}', cumulative=True)
        for key, item in self.seen.items():
            if key not in current:
                # Disappearance alone cannot establish an exact exit timestamp or OOM.
                self.lifecycle.emit('process_no_longer_observed', task_id=key[0], pid=key[1],
                                    starttime=key[2], exit_time_ns=None, observed_missing_ns=stamp)
        self.seen = current

    def sample(self, groups):
        begin = time.monotonic_ns()
        cpu_begin = time.thread_time_ns()
        stamp = begin
        if self.last_stamp:
            self.max_gap_ns = max(self.max_gap_ns, stamp-self.last_stamp)
        self.last_stamp = stamp
        m = meminfo()
        available = m.get('MemAvailable')
        self.low.sample(available, stamp)
        if available is not None:
            self.minimum_available = min(available, self.minimum_available) if self.minimum_available is not None else available
        for key in ('MemTotal', 'MemAvailable', 'MemFree', 'Buffers', 'Cached', 'SwapTotal', 'SwapFree'):
            self.record('low_memory_trace', stamp, 'system', key, m.get(key))
        for key, value in dict(low_memory=int(self.low.active), low_count=self.low.count,
                               low_duration_s=self.low.duration_s).items():
            self.record('low_memory_trace', stamp, 'system', key, value)
        raw, status = optional_text('/proc/vmstat')
        for key, value in pairs_text(raw).items():
            if key.startswith(('pgscan', 'pgsteal', 'workingset_refault')):
                self.record('low_memory_trace', stamp, 'system', key, value, status, cumulative=True)
        self._psi('psi_system', Path('/proc/pressure'), 'system', stamp, system=True)
        for task, group in groups.items():
            self._group(task, group, stamp)
        now_s = stamp/1e9
        if now_s-self.last_proc >= self.proc_period:
            pss = now_s-self.last_pss >= self.pss_period
            self._processes(groups, stamp, pss)
            self.last_proc = now_s
            if pss:
                self.last_pss = now_s
        self.samples += 1
        cost = time.monotonic_ns()-begin
        self.cost_ns += cost
        self.max_cost_ns = max(self.max_cost_ns, cost)
        self.cpu_cost_ns += time.thread_time_ns()-cpu_begin
        return {'monotonic_ns':stamp, 'meminfo':m, 'task_ids':list(groups)}

    def close(self):
        for f in self.files.values():
            f.close()
        result = dict(samples=self.samples, collector_elapsed_s=self.cost_ns/1e9,
                      collector_cpu_s=self.cpu_cost_ns/1e9,
                      max_sample_cost_ms=self.max_cost_ns/1e6, max_gap_ms=self.max_gap_ns/1e6,
                      process_interval_s=self.proc_period, pss_interval_s=self.pss_period,
                      minimum_available_bytes=self.minimum_available,
                      low_memory_count=self.low.count, low_memory_duration_s=self.low.duration_s,
                      unsupported=[dict(task_id=t, metric=m, status=s) for t,m,s in sorted(self.unsupported)],
                      errors=self.errors)
        save_json(self.directory / 'collector.json', result)
        return result
