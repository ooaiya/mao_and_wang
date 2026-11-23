"""Measure one background workload in a delegated Linux cgroup with Swap disabled."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHAPED = ROOT / '后台操作/曲线任务'
sys.path[:0] = [str(ROOT / '基线并发'), str(ROOT / '冻结并发'), str(SHAPED)]
from common.cgroup_manager import CgroupManager
from common.timeline import Timeline
from freezer_monitor import Monitor, memory, values
from restore_swap import active as active_swap, restore as restore_swap
from shaped_workload import PROFILES, TIMING_FLAGS, add_timing_options, timing_args, timing_for


def save(path, result):
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def measure(args):
    out = args.output
    out.mkdir(exist_ok=False)
    os.chown(out, 1000, 1000)
    swap_state = out / 'swap_state.json'
    timeline = Timeline(out, out.name)
    manager = None
    stats = None
    error = None
    returncode = None
    oom_before = values('/proc/vmstat')['oom_kill']
    op = args.task or 'raster_fft'
    worker = SHAPED / 'shaped_workload.py' if args.task else Path(__file__).with_name('raster_fft.py')
    try:
        save(swap_state, dict(entries=active_swap(), proc_swaps=Path('/proc/swaps').read_text()))
        subprocess.run(['swapoff', '-a'], check=True)
        if memory()['SwapTotal']:
            raise RuntimeError('Swap remains enabled')
        parent = CgroupManager.prepare_delegation(CgroupManager.current())
        manager = CgroupManager(parent, f'oomlab_raster_{os.getpid()}')
        cgroup = manager.create('probe')
        controls = {name: (cgroup / name).read_text().strip()
                    for name in ('memory.max', 'memory.high', 'memory.swap.max', 'memory.oom.group')}
        save(out / 'environment.json', dict(kernel=os.uname().release, controls=controls,
                                            cgroup=str(cgroup), memory=memory(), operation=op,
                                            workload_sha256=hashlib.sha256(worker.read_bytes()).hexdigest()))
        args_worker = [str(args.python), str(worker), '--output', str(out / 'output.json')]
        if args.task:
            args_worker.extend(['--task', args.task, *timing_args(args.timing)])
        else:
            args_worker.extend(['--side', str(args.side), '--sweeps', str(args.sweeps)])
            if args.calibration_tiles is not None:
                args_worker.extend(['--calibration-tiles', str(args.calibration_tiles)])
        child_env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        monitor = Monitor(out, timeline, {op: {'cgroup_path': str(cgroup)}})
        gate = ROOT / '冻结并发' / 'allocation_gate.py'
        ready = out / 'allocation_ready.json'
        read_fd, write_fd = os.pipe()
        child = None
        monitor.start()
        try:
            with (out / 'phases.jsonl').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
                child = subprocess.Popen([sys.executable, str(gate), '--group', str(cgroup),
                                          '--ready', str(ready), '--fd', str(read_fd), '--', *args_worker],
                                         pass_fds=(read_fd,), stdout=stdout, stderr=stderr, env=child_env)
                deadline = time.monotonic() + 10
                while not ready.exists():
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('workload failed to enter its cgroup')
                    time.sleep(.01)
                timeline.t0_ns = time.monotonic_ns()
                os.write(write_fd, b'G')
                returncode = child.wait(timeout=1500)
                finish_ns = time.monotonic_ns()
                time.sleep(.15)
        finally:
            os.close(read_fd)
            os.close(write_fd)
            if child is not None and child.poll() is None:
                (cgroup / 'cgroup.kill').write_text('1')
                child.wait(timeout=10)
            stats = monitor.stop()
            stats['scope'] = 'T0=allocation gate release; each read is bracketed by monotonic timestamps'
        if returncode != 0 or not (out / 'output.json').is_file():
            raise RuntimeError(f'workload failed with exit code {returncode}')
        memory_events = values(cgroup / 'memory.events')
        oom_delta = values('/proc/vmstat')['oom_kill'] - oom_before
        if stats['errors'] or stats['formal_swap_total_max_bytes'] or oom_delta or memory_events['oom_kill']:
            raise RuntimeError('sampling, Swap, or OOM verification failed')
    except BaseException as exc:
        error = repr(exc)
    finally:
        if manager is not None:
            manager.cleanup(thaw=False)
        timeline.close()
        try:
            restore_swap(swap_state)
        except Exception as exc:
            error = f'{error or ""} Swap restoration failed: {exc}'
        save(out / 'summary.json', dict(success=error is None, error=error, returncode=returncode,
                                         t0_ns=timeline.t0_ns, stats=stats,
                                         global_oom_kill_delta=values('/proc/vmstat')['oom_kill'] - oom_before,
                                         **(dict(duration_s=(finish_ns-timeline.t0_ns)/1e9, memory_events=memory_events)
                                            if error is None else {})))
    return int(error is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--task', choices=PROFILES, help='select a new shaped workload')
    parser.add_argument('--side', type=int)
    parser.add_argument('--sweeps', type=int)
    parser.add_argument('--calibration-tiles', type=int)
    add_timing_options(parser)
    args = parser.parse_args()
    overrides = {key: getattr(args, key) for key in TIMING_FLAGS}
    if args.task:
        if any(value is not None for value in (args.side, args.sweeps, args.calibration_tiles)):
            parser.error('FFT options cannot be used with --task')
        try:
            args.timing = timing_for(args.task, overrides)
        except ValueError as error:
            parser.error(str(error))
    else:
        if any(value is not None for value in overrides.values()):
            parser.error('timing options require --task')
        if args.sweeps is None:
            parser.error('--sweeps is required for the legacy FFT workload')
        if args.side is None:
            args.side = 18432

    def stop(signum, frame):
        raise KeyboardInterrupt('received SIGTERM')

    signal.signal(signal.SIGTERM, stop)
    return measure(args)


if __name__ == '__main__':
    raise SystemExit(main())
