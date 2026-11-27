"""One CLOCK_MONOTONIC event log and absolute deadlines for all three lines."""
import csv
import json
import threading
import time
import uuid
from pathlib import Path


def wait_until_ns(deadline, stop=None):
    while True:
        remaining = (deadline-time.monotonic_ns())/1e9
        if remaining <= 0:
            return True
        if stop is not None:
            if stop.wait(min(remaining, .05)):
                return False
        else:
            time.sleep(min(remaining, .05))


class Timeline:
    def __init__(self, directory, run_id):
        self.directory = Path(directory)
        self.run_id = run_id
        self.t0_ns = None
        self.rows = []
        self.lock = threading.RLock()
        self.stream = (self.directory/'events.jsonl').open('a', buffering=1)

    def emit(self, event_type, operation='', *, actual_ns=None, planned_ns=None,
             pid=None, pgid=None, cgroup='', status='ok', **details):
        actual_ns = time.monotonic_ns() if actual_ns is None else actual_ns
        row = dict(run_id=self.run_id, event_id=uuid.uuid4().hex, operation=operation,
                   event_type=event_type, planned_offset_ms=None, actual_offset_ms=None,
                   planned_monotonic_ns=planned_ns, actual_monotonic_ns=actual_ns,
                   start_error_ms=(actual_ns-planned_ns)/1e6 if planned_ns is not None else None,
                   pid=pid, pgid=pgid, cgroup=cgroup, status=status,
                   details=json.dumps(details, ensure_ascii=False, allow_nan=False))
        with self.lock:
            self.rows.append(row)
            self.stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n')
        return row

    def homepage_ready(self, stamp, **evidence):
        with self.lock:
            if self.t0_ns is not None:
                raise ValueError('homepage_ready/T0 is immutable within one run')
            self.t0_ns = stamp
            self.emit('homepage_ready', 'foreground_krita', actual_ns=stamp, **evidence)
            self.emit('T0', 'foreground_krita', actual_ns=stamp, **evidence)
            self.emit('task_start', 'foreground_krita', actual_ns=stamp,
                      planned_ns=stamp, origin_event='homepage_ready')

    def close(self):
        with self.lock:
            for row in self.rows:
                if self.t0_ns is not None:
                    row['actual_offset_ms'] = (row['actual_monotonic_ns']-self.t0_ns)/1e6
                    if row['planned_monotonic_ns'] is not None:
                        row['planned_offset_ms'] = (row['planned_monotonic_ns']-self.t0_ns)/1e6
            fields = list(self.rows[0]) if self.rows else []
            for name, selection in [('timeline.csv', self.rows), ('task_events.csv', [r for r in self.rows if r['event_type'].startswith('task_')])]:
                with (self.directory/name).open('w', newline='') as h:
                    w = csv.DictWriter(h, fieldnames=fields)
                    w.writeheader()
                    w.writerows(selection)
            self.stream.close()
