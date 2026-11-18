"""Service supervisor: gate workload start, retain cgroup until collector stops unit."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from oomlab.common import save_json


def main():
    run = Path(sys.argv[1])
    deadline = time.monotonic() + float(os.environ.get('OOMLAB_GATE_TIMEOUT', 60))
    save_json(run / 'ready.json', {'pid': os.getpid()})
    while not (run / 'go').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('collector did not release start gate')
        time.sleep(.01)
    start = time.monotonic_ns()
    save_json(run / 'started.json', {'monotonic_ns': start, 'wall_time_ns': time.time_ns()})
    code = None
    error = None
    try:
        with open(run / 'workload.log', 'w') as log:
            p = subprocess.Popen(sys.argv[2:], stdout=log, stderr=subprocess.STDOUT)
            save_json(run / 'pid.json', {'pid': p.pid, 'supervisor_pid': os.getpid()})
            code = p.wait()
    except Exception as e:
        error = repr(e)
    end = time.monotonic_ns()
    save_json(run / 'finished.json', {'start_ns': start, 'end_ns': end,
              'wall_end_ns': time.time_ns(), 'duration_s': (end-start)/1e9,
              'returncode': code, 'error': error})
    # Keeps memory.peak/events readable even for sub-50ms workloads and failures.
    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
