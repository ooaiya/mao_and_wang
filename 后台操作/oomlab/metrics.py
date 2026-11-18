import csv
import time
from pathlib import Path

EVENTS = ('low', 'high', 'max', 'oom', 'oom_kill', 'oom_group_kill')
STATS = ('anon', 'file', 'kernel', 'kernel_stack', 'pagetables', 'sock', 'shmem', 'slab',
         'slab_reclaimable', 'slab_unreclaimable', 'file_mapped', 'file_dirty',
         'file_writeback', 'inactive_anon', 'active_anon', 'inactive_file', 'active_file',
         'workingset_refault_anon', 'workingset_refault_file', 'pgfault', 'pgmajfault',
         'pgscan', 'pgsteal')
FIELDS = ['relative_s', 'monotonic_ns', 'memory_current', 'memory_peak', 'swap_current'] + [
    'stat_' + x for x in STATS] + ['event_' + x for x in EVENTS]


def pairs(path):
    return {k: int(v) for k, v in (line.split() for line in Path(path).read_text().splitlines())}


def snapshot(cgroup, start_ns):
    p = Path(cgroup)
    stamp = time.monotonic_ns()
    stat = pairs(p / 'memory.stat')
    events = pairs(p / 'memory.events')
    row = dict(relative_s=(stamp - start_ns) / 1e9, monotonic_ns=stamp,
               memory_current=int((p / 'memory.current').read_text()),
               memory_peak=int((p / 'memory.peak').read_text()),
               swap_current=int((p / 'memory.swap.current').read_text())
               if (p / 'memory.swap.current').exists() else None)
    row.update({'stat_' + k: stat.get(k) for k in STATS})
    row.update({'event_' + k: events.get(k) for k in EVENTS})
    return row


def event_delta(first, last):
    result = {}
    for k in EVENTS:
        a, b = first.get('event_' + k), last.get('event_' + k)
        if a is None or b is None:
            result[k] = None
        elif b < a:
            raise ValueError('memory.events 计数回退，cgroup 可能被替换')
        else:
            result[k] = b - a
    return result


def read_curve(path):
    with open(path, newline='') as f:
        return [{k: (float(v) if k == 'relative_s' else int(v)) if v else None
                 for k, v in row.items()} for row in csv.DictReader(f)]


def is_populated(cgroup):
    return pairs(Path(cgroup) / 'cgroup.events').get('populated') == 1
