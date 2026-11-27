"""Run the current four workloads with predictive freeze and thaw."""

import json
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'基线并发'))
from common.concurrent import ConcurrentRun
from common.experiment import digest
from common.phase_events import phase_events, read_events
from common.sampling import memory, values
from common.shaped_scene import save
from priority_policy import TaskMemory, policy_from_plan
from segmented_scheduler import TaskClock


class SegmentedFreezer(ConcurrentRun):
    """Predict memory contention and freeze running background tasks."""

    run_kind = 'freezer'

    def __init__(self, out, foreground_run, foreground_source, shaped_run, offsets, policy_path, *, predictor=None):
        super().__init__(out, foreground_run, foreground_source, shaped_run, offsets, policy_path)
        self.predictor = predictor
        self.high_exit_ns = None
        self.clocks = {}
        self.lock = threading.RLock()
        self.last_decision = 0
        self.decision_stream = None
        self.tick_id = 0

    def initialize(self):
        self.priority_policy = policy_from_plan(self.plan, self.predictor)
        save(self.out/'freeze_events.json', self.freeze_rows)
        self.decision_stream = (self.out/'priority_decisions.jsonl').open('w', encoding='utf-8', buffering=1)

    def launch(self, op):
        super().launch(op)
        if op in self.background_ops:
            with self.lock:
                record = self.records[op]
                stamp = record['release_confirmed_ns']
                clock = TaskClock()
                clock.resumed(stamp/1e9, 0)
                self.clocks[op] = clock
                record.update(state='RUNNING', pause_intervals_ns=[], running_intervals_ns=[[stamp, None]])

    def scheduled(self):
        self.schedule_priority()

    def observe(self):
        super().observe()
        with self.lock:
            for op in self.done:
                if op not in self.clocks:continue
                clock=self.clocks[op];r=self.records[op];stamp=r['empty_confirmed_ns']
                if clock.state!='FINISHED':clock.finished(stamp/1e9)
                r['state']='FINISHED'
                if r['running_intervals_ns'] and r['running_intervals_ns'][-1][1] is None:r['running_intervals_ns'][-1][1]=stamp
                if r['pause_intervals_ns'] and r['pause_intervals_ns'][-1][1] is None:r['pause_intervals_ns'][-1][1]=stamp
                self.update_times(op)
    def update_times(self,op):
        r=self.records[op];now=time.monotonic_ns()
        r['frozen_s']=sum(((b if b is not None else now)-a)/1e9 for a,b in r['pause_intervals_ns'])
        r['unfrozen_wall_s']=sum(((b if b is not None else now)-a)/1e9 for a,b in r['running_intervals_ns'])
        r['effective_model_age_s']=self.clocks[op].age(now/1e9)
        if r.get('actual_start_ns') and r.get('empty_confirmed_ns'):r['execution_span_s']=(r['empty_confirmed_ns']-r['actual_start_ns'])/1e9
    def transition(self,op,frozen,reason,lease_until=None,admission=None):
        with self.lock:
            c=self.clocks[op];r=self.records[op]
            if op in self.done or self.processes[op].poll() is not None:return
            if frozen and c.state!='RUNNING':return
            if not frozen and c.state!='FROZEN':return
            # The epoch changes only on confirmed transitions, never on request.
            proof=self.cm.set_frozen(op,frozen,timeout=self.policy_config['freeze_timeout_s']);stamp=proof['confirmed_monotonic_ns'];cg=Path(self.groups[op]['cgroup_path'])
            if frozen:
                c.frozen(stamp/1e9);r['state']='FROZEN';r['pause_intervals_ns'].append([stamp,None]);r['running_intervals_ns'][-1][1]=stamp
            else:
                # Count all time since the thaw request conservatively in model
                # age; wall intervals still use the confirmed state boundary.
                c.resumed(proof['requested_monotonic_ns']/1e9,lease_until);r['state']='RUNNING'
                r.setdefault('release_confirmed_ns',stamp);r['pause_intervals_ns'][-1][1]=stamp;r['running_intervals_ns'].append([stamp,None])
            proof.update(operation=op,action='freeze' if frozen else 'resume',reason=reason,generation=c.generation,
                memory_current_bytes=int((cg/'memory.current').read_text()),anonymous_bytes=values(cg/'memory.stat')['anon'],
                cpu_usage_usec=values(cg/'cpu.stat')['usage_usec'],effective_model_age_s=c.age(stamp/1e9),lease_until_monotonic_s=c.lease_until,decision_tick=self.tick_id,admission=admission)
            self.freeze_rows.append(proof);save(self.out/'freeze_events.json',self.freeze_rows);self.update_times(op)
            self.event('freeze_confirmed' if frozen else 'resume_confirmed',op,actual_ns=stamp,proof=proof)
    def priority_checkpoint(self, now):
        checkpoint=self.plan.get('priority_checkpoint')
        if checkpoint is None or self.high_exit_ns is not None or 'foreground_krita' in self.done:
            return
        event=next((e for e in self.foreground_events if e.get('kind')==checkpoint['event']),None)
        if event is None:
            return
        start=next((e for e in self.foreground_events if e.get('kind')==checkpoint['identity_event']),{})
        pid=event.get('pid')
        if pid is None or pid!=start.get('pid') or event.get('returncode')!=0:
            raise RuntimeError('priority checkpoint has an invalid process exit')
        if not Path('/proc',str(pid)).exists():
            self.high_exit_ns=event['monotonic_ns']
            self.event('priority_checkpoint_confirmed','foreground_krita',
                       actual_ns=self.high_exit_ns,observed_monotonic_s=now,pid=pid)

    def prediction_age(self, op, now_ns, t0_ns):
        if op=='foreground_krita':
            reference=self.plan.get('priority_checkpoint',{}).get('reference_age_s')
            if self.high_exit_ns is not None and reference is not None:
                return reference+max(0,now_ns-self.high_exit_ns)/1e9
            return max(0,now_ns-t0_ns)/1e9
        record=self.records[op]
        start=record.get('actual_start_ns',record['release_confirmed_ns'])
        return sum(max(0,min(end if end is not None else now_ns,now_ns)-max(begin,start))
                   for begin,end in record['running_intervals_ns'])/1e9

    def prediction_events(self, op):
        if op=='foreground_krita':
            if self.high_exit_ns is not None:
                return iter(self.foreground_events)
            withheld={'HIGH_INSTANCE_EXIT'}
            if self.plan.get('priority_checkpoint'):
                withheld.add('POST_CLOSE_REVIEW_START')
            return (row for row in self.foreground_events if row.get('kind') not in withheld)
        path=self.out/op/'phase_trace.jsonl'
        return read_events(path) if path.is_file() else ()

    def prediction_position(self, op, now_ns, t0_ns):
        age=self.prediction_age(op,now_ns,t0_ns)
        markers=self.plan['models'][op].get('phase_markers_s',{})
        floor=None
        if op=='foreground_krita' and self.high_exit_ns is not None:
            floor=self.plan['priority_checkpoint'].get('reference_age_s')
        latest=max(((stamp,key) for key,stamp in phase_events(op,self.prediction_events(op))
                    if key in markers and stamp<=now_ns and (floor is None or markers[key]>=floor)),
                   default=None)
        if latest is None:
            return age,floor,None,None
        stamp,key=latest
        anchor=markers[key]
        ceiling=min((value for value in markers.values() if value>anchor),default=None)
        if ceiling is not None:
            ceiling=max(anchor,ceiling-1e-9)
        elapsed=(now_ns-stamp)/1e9 if op=='foreground_krita' else max(
            0.,age-self.prediction_age(op,stamp,t0_ns))
        estimate=anchor+elapsed
        if ceiling is not None:
            estimate=min(estimate,ceiling)
        return estimate,anchor,ceiling,key

    def schedule_priority(self):
        t0=self.timeline.t0_ns
        if t0 is None:
            return
        elapsed=(time.monotonic_ns()-t0)/1e9
        offsets=self.plan['alignment']['offsets_s']
        launched=False
        for op in sorted(self.background_ops,key=offsets.__getitem__):
            if op not in self.records and elapsed>=offsets[op]:
                self.launch(op)
                launched=True
        started=time.monotonic()
        if not launched and started-self.last_decision<self.policy_config['guard_interval_s']:
            return
        self.priority_checkpoint(started)
        tasks={}
        for op in self.groups.keys()-self.done:
            cg=self.cm.checked(op)
            protected=op=='foreground_krita'
            peak=self.plan['priority_peaks_bytes'].get(op)
            if protected and self.high_exit_ns is not None:
                peak=self.plan['priority_checkpoint']['peak_bytes']
            anon=values(cg/'memory.stat')['anon']
            current=int((cg/'memory.current').read_text())
            age,phase_floor,phase_ceiling,marker=self.prediction_position(op,time.monotonic_ns(),t0)
            can_freeze=True
            if self.priority_policy.reserve_foreground_peak and not protected:
                can_freeze='actual_start_ns' in self.records[op]
                if self.plan.get('workload_kind')=='shaped':
                    can_freeze=can_freeze and marker not in (None, 'task_start', 'prepare', 'grow')
            tasks[op]=TaskMemory(self.plan['priority']['task_priorities'].get(op,0),protected,
                                 protected or self.clocks[op].state=='RUNNING',current,min(anon,current),peak,
                                 age,phase_floor,phase_ceiling,marker,freeze_eligible=can_freeze)
        available=memory()['MemAvailable']
        now=time.monotonic()
        if now-started>self.policy_config['guard_interval_s']:
            self.priority_policy.stable_since.clear()
            return
        self.last_decision=now
        self.tick_id+=1
        elapsed=(now-t0/1e9)
        upcoming={op:max(0.,offsets[op]-elapsed) for op in self.background_ops
                  if op not in self.records and offsets[op]-elapsed<=self.priority_policy.horizon}
        decision=self.priority_policy.decide(now,available,tasks,upcoming)
        self.decision_stream.write(json.dumps(dict(tick=self.tick_id,monotonic_s=now,
            checkpoint_ns=self.high_exit_ns,tasks={op:asdict(task) for op,task in sorted(tasks.items())},
            upcoming_s=upcoming,decision=decision))+'\n')
        for op in decision['freeze']:
            self.transition(op,True,'priority_forecast',admission=decision)
        if decision['abort']:
            raise RuntimeError('available memory fell below the experiment emergency floor')
        if decision['resume'] is not None:
            self.transition(decision['resume'],False,'priority_admission',lease_until=0,admission=decision)

    def execution_age_s(self,op,now_ns):
        with self.lock:
            if op in self.clocks:return self.clocks[op].age(now_ns/1e9)
        return (now_ns-self.records[op]['release_confirmed_ns'])/1e9
    def after_task_cleanup(self,op,stamp):
        if op not in self.clocks:return
        with self.lock:
            r=self.records[op];c=self.clocks[op]
            if c.state!='FINISHED':c.finished(stamp/1e9)
            for key in ['pause_intervals_ns','running_intervals_ns']:
                if r[key] and r[key][-1][1] is None:r[key][-1][1]=stamp
            r['state']='ABORTED' if r.get('cleanup_terminated') else 'FINISHED';self.update_times(op)

    def before_cleanup(self):
        with self.lock:
            for op in self.clocks:
                self.update_times(op)
        if self.decision_stream:
            self.decision_stream.close()

    def runtime_policy_evidence(self):
        return dict(name='priority_freezer', background_start='run_on_submit', configuration=self.policy_config,
                    confirmed_checkpoint_ns=self.high_exit_ns, guard_samples=self.tick_id,
                    policy_sha256=digest(Path(__file__).with_name('priority_policy.py')),
                    runner_sha256=digest(__file__))
