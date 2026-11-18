#!/usr/bin/env python3
"""Run the four no-Swap workloads with online memory feedback and cgroup v2."""

import argparse
from dataclasses import asdict
import json
from mmap import PAGESIZE
import os
from pathlib import Path
import signal
import threading
import time

from independent_runner import Freezer, Monitor, Serial, digest, memory, save, values
from priority_policy import write_memory_high
from raster_priority import RASTER, WORKER, raster_events
from realtime_policy import FOREGROUND, OFFSETS, PRIORITIES, Reading, RealtimePolicy, Settings
from segmented_runner import SegmentedFreezer, TaskClock


class RealtimeFreezer(SegmentedFreezer):
    run_kind = 'realtime'
    offsets = OFFSETS
    priorities = PRIORITIES

    def __init__(self, output, foreground_source, foreground_config, foreground_assets, settings):
        Serial.__init__(self, output, '/home/ooaiya', foreground_source=foreground_source,
                        no_swap=True, foreground_inputs=(foreground_config, foreground_assets))
        self.settings = settings
        self.policy_config = asdict(settings)
        self.lock = threading.RLock()
        self.watch_stop = threading.Event()
        self.watch = self.watch_error = self.decision_stream = None
        self.clocks = {}
        self.high = {}
        self.freeze_rows = []
        self.pipes = {}
        self.done = set()
        self.foreground_events = []
        self.started = time.monotonic_ns()
        self.last_sample = 0.
        self.tick_id = 0

    def prepare(self, start_monitor=False):
        Serial.prepare(self, start_monitor=False)
        memtotal = memory()['MemTotal']
        self.policy = RealtimePolicy(self.settings, memtotal, self.priorities)
        self.plan = dict(schema='oomlab-realtime-freezer-v2', execution_mode='realtime',
                         source_kind='LIVE_CGROUP_FEEDBACK', background_start='run_on_submit',
                         alignment={'offsets_s': self.offsets}, priorities=self.priorities,
                         budget=dict(memtotal_bytes=memtotal, reserve_bytes=self.policy.reserve),
                         settings=self.policy_config)
        (self.out / 'planning').mkdir()
        save(self.out / 'planning/plan.json', self.plan)
        save(self.out / 'freeze_events.json', self.freeze_rows)
        self.decision_stream = (self.out / 'realtime_decisions.jsonl').open('w', encoding='utf-8', buffering=1)
        self.monitor = Monitor(self.out, self.timeline, self.groups)
        self.monitor.start()
        self.watch = threading.Thread(target=self.watchdog, name='realtime-lease-watchdog')
        self.watch.start()

    def set_high(self, op, limit):
        group = self.cm.checked(op)
        write_memory_high(group, limit)
        applied = int((group / 'memory.high').read_text())
        if abs(applied - limit) >= PAGESIZE:
            raise RuntimeError(f'{op}: memory.high write did not take effect')
        self.high[op] = applied
        return dict(requested_bytes=limit, applied_bytes=applied, confirmed_ns=time.monotonic_ns())

    def launch(self, op):
        if op == FOREGROUND:
            Freezer.launch(self, op, freeze_on_submit=False)
            return
        Freezer.launch(self, op, freeze_on_submit=False, defer_release=True)
        rec = self.records[op]
        self.event('task_submitted', op, actual_ns=rec['created_ns'], nominal_offset_s=self.offsets[op],
                   large_allocation_started=False)
        with self.lock:
            group = self.cm.checked(op)
            current = int((group / 'memory.current').read_text())
            rec['initial_memory_high'] = self.set_high(op, current + self.settings.step_bytes)
            available = memory()['MemAvailable']
            if available < self.settings.emergency_bytes or self.watch_error:
                raise RuntimeError(f'{op}: unable to start during emergency pressure or watchdog failure')
            released = time.monotonic_ns()
            pipe = self.pipes[op]
            if os.write(pipe, b'G') != 1:
                raise OSError(f'{op}: incomplete allocation gate write')
            os.close(pipe)
            del self.pipes[op]
            clock = TaskClock()
            clock.resumed(released / 1e9, released / 1e9 + self.settings.startup_timeout_s)
            self.clocks[op] = clock
            rec.update(release_confirmed_ns=released, state='RUNNING', pause_intervals_ns=[],
                       running_intervals_ns=[[released, None]], initial_lease_until_s=clock.lease_until,
                       initial_mem_available_bytes=available)
            self.policy.reset_stability()
        self.event('allocation_gate_released', op, actual_ns=released, reason='realtime_run_on_submit')

    def freeze_started(self, op, reason, *, expired_only=False, admission=None):
        record = self.records[op]
        if self.processes[op].poll() is not None:
            return False
        stamp = record.get('actual_start_ns')
        if stamp is None:
            stamp = self.background_start_ns(op)
        if stamp is None or not record['release_confirmed_ns'] <= stamp <= time.monotonic_ns():
            if expired_only:
                raise TimeoutError(f'{op}: startup lease expired before workload start was confirmed')
            return False
        proof = dict(admission or {}, actual_start_ns=stamp, prior_lease_s=self.clocks[op].lease_until)
        self.transition(op, True, reason, expired_only=expired_only, admission=proof)
        return self.clocks[op].state == 'FROZEN'

    def watchdog(self):
        try:
            while not self.watch_stop.wait(self.settings.watchdog_interval_s):
                with self.lock:
                    for op in sorted(self.clocks, key=self.priorities.__getitem__):
                        clock = self.clocks[op]
                        if clock.state == 'RUNNING' and time.monotonic() >= clock.lease_until:
                            if self.freeze_started(op, 'realtime_lease_expired', expired_only=True):
                                self.policy.reset_stability()
        except Exception as error:
            self.watch_error = repr(error)

    def read_sample(self):
        start = time.monotonic()
        with self.lock:
            active = {op: (c.generation, c.state, self.high[op], self.records[op].get('actual_start_ns') is not None)
                      for op, c in self.clocks.items() if c.state != 'FINISHED'}
            foreground_running = FOREGROUND not in self.done
        readings = {}
        for op in ([FOREGROUND] if foreground_running else []) + list(active):
            group = self.cm.checked(op)
            current = int((group / 'memory.current').read_text())
            anon = min(current, values(group / 'memory.stat')['anon'])
            events = values(group / 'memory.events')
            cpu = values(group / 'cpu.stat')['usage_usec']
            _, state, high, started = active.get(op, (0, 'RUNNING', None, True))
            readings[op] = Reading(current, anon, events['high'], cpu, state, started, high)
        available = memory()['MemAvailable']
        return start, time.monotonic(), available, readings, active

    def control(self):
        start, now, available, readings, active = self.read_sample()
        timeout = self.settings.sample_interval_s
        with self.lock:
            if time.monotonic() - start > timeout or any(self.clocks[op].generation != state[0]
                                                        for op, state in active.items()):
                self.policy.reset_stability()
                return
            self.last_sample = now
            self.tick_id += 1
            previous = self.policy.previous
            frozen = {op: self.clocks[op].frozen_since for op in active if active[op][1] == 'FROZEN'}
            decision = self.policy.decide(now, available, readings, frozen)
            applied = {}
            renewed = {}
            frozen_op = resumed_op = None
            if not decision['abort']:
                frozen_op, resumed_op = self.apply_decision(start, now, readings, previous, decision,
                                                            applied, renewed)
            evidence = dict(tick=self.tick_id, sample_started_s=start, monotonic_s=now,
                            readings={op: asdict(row) for op, row in readings.items()}, frozen_since=frozen,
                            decision=decision, limits=applied, renewed=renewed,
                            frozen=frozen_op, resumed=resumed_op)
        self.decision_stream.write(json.dumps(evidence) + '\n')
        if decision['abort']:
            raise RuntimeError('MemAvailable fell below the real-time emergency floor')

    def apply_decision(self, start, now, readings, previous, decision, applied, renewed):
        op = decision['freeze']
        if op is not None:
            if self.freeze_started(op, 'realtime_pressure', admission=decision):
                self.policy.record_pressure_freeze(op, readings, previous)
                return op, None
            return None, None

        resume = decision['resume']
        deadline = now + self.settings.lease_s
        for name, limit in decision['limits'].items():
            if time.monotonic() - start > self.settings.sample_interval_s:
                break
            if name == resume or time.monotonic() < self.clocks[name].lease_until:
                applied[name] = self.set_high(name, limit)
                self.policy.reset_stability()
        if time.monotonic() - start <= self.settings.sample_interval_s:
            for name in decision['renew']:
                clock = self.clocks[name]
                if time.monotonic() < clock.lease_until < deadline:
                    clock.lease_until = deadline
                    renewed[name] = deadline
            if resume in applied:
                self.transition(resume, False, 'realtime_resume', lease_until=deadline, admission=decision)
                if self.clocks[resume].state == 'RUNNING':
                    return None, resume
        return None, None

    def scheduled(self):
        if self.watch_error:
            raise RuntimeError('real-time watchdog: ' + self.watch_error)
        t0 = self.timeline.t0_ns
        if t0 is None:
            return
        elapsed = (time.monotonic_ns() - t0) / 1e9
        due = min((op for op in self.priorities if op not in self.records and elapsed >= self.offsets[op]),
                  key=self.offsets.__getitem__, default=None)
        if due is not None:
            self.launch(due)
        if due is not None or time.monotonic() - self.last_sample >= self.settings.sample_interval_s:
            self.control()

    def runtime_policy_evidence(self):
        return dict(name='realtime_freezer', background_start='run_on_submit', guard_samples=self.tick_id,
                    watchdog_error=self.watch_error, configuration=self.policy_config,
                    policy_sha256=digest(Path(__file__).with_name('realtime_policy.py')),
                    runner_sha256=digest(__file__))


class RasterRealtimeFreezer(RealtimeFreezer):
    background_input_ops = ('table', 'array')
    background_ops = (RASTER, 'table', 'array')
    priorities = {RASTER: PRIORITIES['xz'], 'array': PRIORITIES['array'], 'table': PRIORITIES['table']}
    # Match the calibrated no-intervention scenario that reached global OOM.
    offsets = {FOREGROUND: 0, RASTER: 13.51, 'array': 704.74, 'table': 705.84}

    def __init__(self, *args, raster_reference):
        super().__init__(*args)
        self.raster_reference = raster_reference
        self.env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')

    def background_provenance(self):
        provenance = super().background_provenance()
        ref = self.raster_reference
        names = ('summary.json', 'environment.json', 'output.json')
        summary, environment, output = (json.loads((ref / name).read_text(encoding='utf-8')) for name in names)
        worker_sha = digest(WORKER)
        if (not summary['success'] or summary['global_oom_kill_delta']
                or summary['stats']['formal_swap_total_max_bytes'] or output['calibration_tiles'] is not None
                or output['pixels'] != output['side'] ** 2 or worker_sha != environment['workload_sha256']):
            raise ValueError('raster reference must be a completed run of this workload without Swap or OOM')
        provenance[RASTER] = dict(worker=str(WORKER), worker_sha256=worker_sha, reference_run=str(ref),
                                  reference_hashes={name: digest(ref / name) for name in names},
                                  side=output['side'], sweeps=output['sweeps'])
        return provenance

    def command(self, op):
        if op != RASTER:
            return super().command(op)
        inputs = self.provenance[op]
        return [str(self.home / 'bg/.venv/bin/python'), str(WORKER), '--side', str(inputs['side']),
                '--sweeps', str(inputs['sweeps']), '--output', str(self.out / op / 'output.json')]

    def background_start_ns(self, op):
        if op != RASTER:
            return super().background_start_ns(op)
        return next((event['monotonic_ns'] for event in raster_events(self.out / op / 'process.log')
                     if event['event'] == 'tile_background_start'), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'foreground-source', 'foreground-config', 'foreground-assets'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--policy-config', type=Path, help='JSON overrides for the online policy settings')
    parser.add_argument('--raster-reference', type=Path, help='verified workload and expected output for the raster scenario')
    args = parser.parse_args()
    overrides = json.loads(args.policy_config.read_text(encoding='utf-8')) if args.policy_config else {}
    settings = Settings(**overrides)

    def stop(signum, frame):
        raise KeyboardInterrupt('termination signal')

    signal.signal(signal.SIGTERM, stop)
    inputs = (args.output, args.foreground_source, args.foreground_config, args.foreground_assets, settings)
    if args.raster_reference:
        return RasterRealtimeFreezer(*inputs, raster_reference=args.raster_reference).run()
    return RealtimeFreezer(*inputs).run()


if __name__ == '__main__':
    raise SystemExit(main())
