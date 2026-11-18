"""Run the identical raster comparison workloads at fixed offsets without intervention."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from independent_runner import Freezer
from raster_priority import RasterPriority, run_cli, save, values


class DeadlineBaseline:
    def build_serial_plan(self, memory_info):
        plan = super().build_serial_plan(memory_info)
        plan['execution_mode'] = 'baseline'
        save(self.out / 'planning/plan.json', plan)
        return plan

    def initialize_priority_policy(self):
        self.deadline_helpers = {}
        self.deadlines_armed = False
        save(self.out / 'freeze_events.json', [])
        helper = Path(__file__).with_name('release_at_deadline.py')
        offsets = self.plan['alignment']['offsets_s']
        for op in self.background_ops:
            self.launch(op)
            fd = self.pipes[op]
            with (self.out/op/'deadline_release.jsonl').open('wb') as evidence:
                timer = subprocess.Popen([sys.executable, str(helper), str(fd), str(round(offsets[op]*1e9))],
                                         pass_fds=(fd,), stdin=subprocess.PIPE, stdout=evidence)
            self.deadline_helpers[op] = timer
            os.close(self.pipes.pop(op))

    def scheduled(self):
        if self.timeline.t0_ns is None:
            return
        if not self.deadlines_armed:
            origin = f'{self.timeline.t0_ns}\n'.encode('ascii')
            for timer in getattr(self, 'deadline_helpers', {}).values():
                timer.stdin.write(origin)
                timer.stdin.close()
            self.deadlines_armed = True
        self.record_releases()

    def record_releases(self):
        for op, timer in getattr(self, 'deadline_helpers', {}).items():
            record = self.records[op]
            if 'release_confirmed_ns' in record or timer.poll() != 0:
                continue
            proof = json.loads((self.out/op/'deadline_release.jsonl').read_text(encoding='utf-8'))
            record.update(release_confirmed_ns=proof['released_ns'], planned_ns=proof['planned_ns'])
            self.event('task_submitted',op,actual_ns=proof['released_ns'],planned_ns=proof['planned_ns'],
                       background_start='deadline_release')

    def launch(self, op):
        Freezer.launch(self, op, freeze_on_submit=False, defer_release=op in self.background_ops)
        path = Path(self.records[op]['cgroup'])
        ancestors = {}
        for group in (path, *path.parents):
            if group == self.cm.mount:
                break
            controls = {key: (group / key).read_text().strip() for key in ('memory.high', 'memory.max')}
            ancestors[str(group)] = controls
            if any(value != 'max' for value in controls.values()):
                raise RuntimeError(f'unexpected memory limit on {group}')
        save(self.out / op / 'ancestor_memory_controls.json', ancestors)

    def before_cleanup(self):
        self.measurement_end_ns = time.monotonic_ns()
        self.event('measurement_ended', actual_ns=self.measurement_end_ns)
        for timer in getattr(self, 'deadline_helpers', {}).values():
            if timer.poll() is None:
                timer.terminate()
            timer.wait(timeout=5)
            timer.stdin.close()
        self.record_releases()
        super().before_cleanup()

    def after_task_cleanup(self, op, stamp):
        path = self.cm.checked(op)
        self.records[op]['final_memory_events'] = values(path / 'memory.events')
        self.records[op]['final_memory_peak_bytes'] = int((path / 'memory.peak').read_text())

    def runtime_policy_evidence(self):
        return dict(name=f'{self.run_kind}_fixed_offsets', configuration=self.policy_config,
                    background_start='independent_deadline_release', freeze_enabled=False, memory_high_writes=0,
                    formal_end_monotonic_ns=getattr(self, 'measurement_end_ns', None))


class RasterBaseline(DeadlineBaseline, RasterPriority):
    run_kind = 'raster_baseline'
    memory_high_enabled = False

if __name__ == '__main__':
    raise SystemExit(run_cli(RasterBaseline))
