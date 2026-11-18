#!/usr/bin/env python3
"""Second-version executor, now driven by a precomputed curve schedule."""
import argparse,json,os,signal,subprocess,threading,time
from dataclasses import asdict
from pathlib import Path
from independent_runner import Freezer,OPS,memory,values,save,digest,members
from priority_policy import PriorityPolicy,TaskMemory,write_memory_high
from segmented_scheduler import TaskClock
from run_serial import Serial
from freezer_monitor import Monitor
from restore_swap import active

class SegmentedFreezer(Freezer):
    def __init__(self,out,profiles,binary,policy_path=None,serial_run=None,foreground_run=None,foreground_source=None,
                 serial_policy='priority'):
        super().__init__(out,profiles,binary)
        self.serial_run=Path(serial_run) if serial_run else None
        self.serial_policy=serial_policy
        if self.serial_run:
            self.foreground_run=Path(foreground_run)
            self.foreground_source=Path(foreground_source)
        self.policy_path=Path(policy_path or Path(__file__).with_name('offline_config.json'))
        self.policy_config=json.loads(self.policy_path.read_text(encoding='utf-8'))
        self.clocks={};self.lock=threading.RLock();self.watch_stop=threading.Event();self.watch=None;self.watch_error=None
        self.last_decision=0;self.stable={};self.decision_stream=None;self.tick_id=0
    def prepare(self,start_monitor=False):
        if self.serial_run:
            self.prepare_serial_curves()
            return
        super().prepare(start_monitor=False)
        from offline_plan import make_plan
        m=memory()
        self.offline=make_plan(self.profiles,self.profiles/'calibration.json',self.out/'planning',m['MemTotal'],
                               m['MemTotal']-m['MemAvailable'],self.binary)
        self.early=self.offline['search']['selected'];self.early_state='PENDING';self.fallback_reason=None
        self.offline_sha=digest(self.out/'planning/offline_plan.json')
        self.guard_history=[];self.last_guard_log=0;self.foreground_end_ns=None
        save(self.out/'offline_execution_config.json',self.policy_config)
        self.plan['execution_mode']='curve_offline'
        self.plan['runtime_policy']='precomputed curve intervals and actual foreground-exit barrier; live veto only'
        save(self.out/'planning/plan.json',self.plan)
        self.decision_stream=(self.out/'offline_execution.jsonl').open('w',buffering=1)
        self.watch=threading.Thread(target=self.watchdog,name='planned-freeze-watchdog');self.watch.start()
    def prepare_serial_curves(self):
        from serial_curve_plan import load
        Serial.prepare(self,start_monitor=False)
        self.validate_serial_inputs()
        save(self.out/'swap_state.json',dict(entries=active(),proc_swaps=Path('/proc/swaps').read_text()))
        subprocess.run(['swapoff','-a'],check=True)
        m=memory()
        if m['SwapTotal']:raise RuntimeError('Swap is not fully disabled')
        environment=load(self.out/'environment.json')
        environment.update(meminfo=m,swaps=Path('/proc/swaps').read_text(),swap_changed=True)
        save(self.out/'environment.json',environment)
        self.plan=self.build_serial_plan(m)
        self.offline=self.plan
        self.guard_history=[];self.last_guard_log=0;self.foreground_end_ns=None
        self.high_exit_ns=None;self.fallback_reason=None;self.early_state='WAIT_HIGH_INSTANCE_EXIT'
        save(self.out/'offline_execution_config.json',self.policy_config)
        if self.serial_policy=='priority':
            self.initialize_priority_policy()
        else:
            self.decision_stream=(self.out/'offline_execution.jsonl').open('w',buffering=1)
        self.monitor=Monitor(self.out,self.timeline,self.groups);self.monitor.start()
    def initialize_priority_policy(self):
        budget=self.plan['budget']
        self.priority_policy=PriorityPolicy(budget['reserve_bytes'],budget['emergency_floor_bytes'],
                                            self.plan['priority'])
        save(self.out/'freeze_events.json',self.freeze_rows)
        self.decision_stream=(self.out/'priority_decisions.jsonl').open('w',encoding='utf-8',buffering=1)
    def validate_serial_inputs(self):
        from serial_curve_plan import load
        for name in ('foreground_config.json','foreground_assets.json','input_provenance.json'):
            if load(self.out/name)!=load(self.serial_run/name):
                raise RuntimeError('workload inputs differ from the serial baseline: '+name)
    def build_serial_plan(self,memory_info):
        from serial_curve_plan import make_serial_plan
        return make_serial_plan(self.serial_run,self.out/'planning',memory_info['MemTotal'],
                                memory_info['MemTotal']-memory_info['MemAvailable'],self.binary,
                                self.policy_config,priority=self.serial_policy=='priority')
    def launch(self,op):
        run_on_submit=self.serial_run and self.serial_policy=='priority'
        super().launch(op,freeze_on_submit=not run_on_submit)
        if op in self.background_ops:
            with self.lock:
                if run_on_submit:
                    record=self.records[op]
                    stamp=record['release_confirmed_ns']
                    clock=TaskClock()
                    clock.resumed(stamp/1e9,0)
                    self.clocks[op]=clock
                    record.update(state='RUNNING',pause_intervals_ns=[],running_intervals_ns=[[stamp,None]])
                    return
                stamp=self.records[op]['freeze_confirmed_ns']/1e9
                self.clocks[op]=TaskClock(frozen_since=stamp)
                self.records[op].update(state='FROZEN',pause_intervals_ns=[[self.records[op]['freeze_confirmed_ns'],None]],running_intervals_ns=[])
                self.freeze_rows[-1]['generation']=0;save(self.out/'freeze_events.json',self.freeze_rows)
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
    def transition(self,op,frozen,reason,lease_until=None,expired_only=False,admission=None):
        with self.lock:
            c=self.clocks[op];r=self.records[op];now=time.monotonic()
            if op in self.done or self.processes[op].poll() is not None:return
            if frozen and c.state!='RUNNING':return
            if not frozen and c.state!='FROZEN':return
            if expired_only and (not c.lease_until or now<c.lease_until):return
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
                memory_current_bytes=int((cg/'memory.current').read_text()),cpu_usage_usec=values(cg/'cpu.stat')['usage_usec'],effective_model_age_s=c.age(stamp/1e9),lease_until_monotonic_s=c.lease_until,decision_tick=self.tick_id,admission=admission)
            self.freeze_rows.append(proof);save(self.out/'freeze_events.json',self.freeze_rows);self.update_times(op)
            self.event('freeze_confirmed' if frozen else 'resume_confirmed',op,actual_ns=stamp,proof=proof)
            if frozen and op=='xz' and c.ever_started and hasattr(self,'offline') and not (self.out/'progress_at_freeze.json').exists():self.capture_progress()
    def capture_progress(self):
        rows=[]
        for pid in members(self.groups['xz']['cgroup_path']):
            try:
                proc=Path('/proc')/str(pid);cmd=(proc/'cmdline').read_bytes().split(bytes([0]))
                if Path(os.fsdecode(cmd[0])).name!='xz':continue
                fds=[]
                for fd in (proc/'fd').iterdir():
                    try:fds.append(dict(fd=fd.name,target=os.readlink(fd),info=(proc/'fdinfo'/fd.name).read_text()))
                    except OSError:pass
                rows.append(dict(pid=pid,command=[os.fsdecode(x) for x in cmd if x],fds=fds))
            except OSError:pass
        fg=next((e for e in self.foreground_events if e.get('kind')=='KRITA_PROCESS'),{})
        save(self.out/'progress_at_freeze.json',dict(monotonic_ns=time.monotonic_ns(),xz_processes=rows,
             foreground_pid=fg.get('pid'),foreground_alive=bool(fg.get('pid') and Path('/proc',str(fg['pid'])).exists())))
    def watchdog(self):
        try:
            while not self.watch_stop.wait(self.policy_config['watchdog_interval_s']):
                with self.lock:expired=[op for op,c in self.clocks.items() if c.state=='RUNNING' and c.lease_until and time.monotonic()>=c.lease_until]
                for op in expired:self.transition(op,True,'offline_planned_deadline_watchdog',expired_only=True)
        except BaseException as e:self.watch_error=repr(e)
    def snapshot(self):
        start=time.monotonic()
        with self.lock:generations={op:c.generation for op,c in self.clocks.items()}
        # Never hold the transition lock across proc/cgroup reads: the watchdog
        # must remain able to pause a task if one of these reads blocks.
        current={op:int((Path(row['cgroup_path'])/'memory.current').read_text()) for op,row in list(self.groups.items())}
        available=memory()['MemAvailable'];now=time.monotonic()
        with self.lock:
            if any(self.clocks[op].generation!=generation for op,generation in generations.items()):return None
            clocks={op:TaskClock(**vars(c)) for op,c in self.clocks.items()}
        if now-start>self.policy_config.get('guard_interval_s',self.policy_config.get('decision_interval_s',.2)):return None
        self.snapshot_bounds=dict(start_monotonic_s=start,end_monotonic_s=now)
        return now,available,current,clocks
    def live_guard(self,now,available,current,clocks):
        self.guard_history.append((now,dict(current)))
        self.guard_history=[r for r in self.guard_history if now-r[0]<=self.policy_config['history_s']]
        required=self.offline['budget']['reserve_bytes'];rates={}
        foreground_active='foreground_krita' not in self.done
        growing=([ 'foreground_krita' ] if foreground_active and any(c.ever_started for c in clocks.values()) else [])+([op for op,c in clocks.items() if c.state=='RUNNING'] if foreground_active else [])
        for op in growing:
            rates[op]=max([0.]+[(current.get(op,0)-row.get(op,0))/(now-t)*self.policy_config['rate_multiplier']
                for t,row in self.guard_history if now-t>=self.policy_config['rate_window_s']])
            required+=int(rates[op]*self.policy_config['reaction_s'])+self.policy_config['model_error_bytes']
        return dict(available_bytes=available,required_bytes=required,rates_bytes_s=rates,allowed=available>=required)
    def cancel_early(self,reason):
        if self.fallback_reason is None:
            self.fallback_reason=reason;self.event('offline_early_cancelled','xz',reason=reason)
        if 'xz' in self.clocks and self.clocks['xz'].state=='RUNNING':self.transition('xz',True,'offline_safety_veto')
        self.early_state='CANCELLED';self.stable.clear()
    def early_admission(self,elapsed,available,current):
        from segmented_scheduler import Curve
        p=self.offline;c=p['config'];curve=Curve(p['models']['foreground_system'])
        future=curve.maximum(max(0,elapsed-c['foreground_jitter_s']),curve.duration)
        pressure=p['budget']['memtotal_bytes']-available
        retained=current.get('xz',0)
        # System-only pressure already includes the desktop/base. Subtracting
        # the full retained XZ charge is conservative if some of it is reclaimable.
        future_growth=max(0,future-max(0,pressure-retained))
        xz_growth=max(0,self.early['held_upper_bytes']-retained)
        required=p['budget']['reserve_bytes']+future_growth+xz_growth+3*p['budget']['waiting_per_task_bytes']+c['admission_headroom_bytes']+c['model_error_bytes']
        return dict(allowed=available>=required,available_bytes=available,required_bytes=required,
                    foreground_system_future_bytes=future,remaining_xz_growth_bytes=xz_growth,
                    plan_sha256=self.offline_sha,role='veto of a fixed offline interval; no new execution window')
    def continuation_admission(self,op,available,current):
        required=self.offline['budget']['reserve_bytes']
        for other in OPS:
            if other in self.done:continue
            if other==op or other in self.clocks and self.clocks[other].state=='RUNNING':
                required+=max(0,self.offline['models'][other]['peak_bytes']-current.get(other,0))
        return dict(allowed=available>=required,available_bytes=available,required_bytes=required,
                    role='post-foreground native continuation, runtime veto only')
    def scheduled(self):
        if self.serial_run:
            if self.serial_policy=='priority':
                self.schedule_priority()
            else:
                self.schedule_serial_curves()
            return
        if self.timeline.t0_ns is None:return
        if self.watch_error:raise RuntimeError('planned-freeze watchdog: '+self.watch_error)
        elapsed=(time.monotonic_ns()-self.timeline.t0_ns)/1e9
        for op in sorted(OPS,key=lambda x:self.plan['alignment']['offsets_s'][x]):
            if op not in self.records and elapsed>=self.plan['alignment']['offsets_s'][op]:self.launch(op)
        if time.monotonic()-self.last_decision<self.policy_config['guard_interval_s']:return
        sample=self.snapshot()
        if sample is None:return
        now,available,current,clocks=sample;elapsed=now-self.timeline.t0_ns/1e9
        self.last_decision=now;self.tick_id+=1;fg_done='foreground_krita' in self.done
        guard=self.live_guard(now,available,current,clocks)
        if now-self.last_guard_log>=1:
            self.decision_stream.write(json.dumps(dict(tick=self.tick_id,elapsed_s=elapsed,monotonic_s=now,
                foreground_done=fg_done,early_state=self.early_state,available_bytes=available,current_bytes=current,
                clocks={op:dict(**vars(c),effective_age_s=c.age(now)) for op,c in clocks.items()},live_guard=guard))+'\n')
            self.last_guard_log=now
        if not guard['allowed']:
            self.cancel_early('observed reserve and stop-reaction budget')
            raise RuntimeError('actual available memory below unchanged reserve plus observed stop-reaction growth')
        if not fg_done:
            if 'xz' not in self.clocks:return
            clock=self.clocks['xz']
            from segmented_scheduler import Curve
            c=self.offline['config'];fg=Curve(self.offline['models']['foreground_krita'])
            upper=fg.maximum(max(0,elapsed-c['foreground_jitter_s']),min(fg.duration,elapsed+c['foreground_jitter_s']))
            if current['foreground_krita']>upper+c['model_error_bytes'] or current.get('xz',0)>self.early['held_upper_bytes']:
                self.cancel_early('observed charge outside offline envelope');return
            if self.fallback_reason:return
            if elapsed>=self.early['freeze_request_s']:
                if clock.state=='RUNNING':self.transition('xz',True,'offline_planned_freeze')
                if self.early_state=='PENDING':self.early_state='SKIPPED'
                elif self.early_state=='RUNNING':self.early_state='FROZEN'
                return
            if self.early_state!='PENDING' or elapsed<self.early['start_s']:return
            if elapsed>self.early['start_s']+self.policy_config['release_max_lateness_s']:
                self.early_state='SKIPPED';self.event('offline_window_missed','xz');return
            check=self.early_admission(elapsed,available,current)
            if not check['allowed']:self.stable.pop('xz',None);return
            self.stable.setdefault('xz',now)
            if now-self.stable['xz']<self.policy_config['resume_stable_s']:return
            deadline=self.timeline.t0_ns/1e9+self.early['freeze_request_s']
            self.transition('xz',False,'offline_planned_early_resume',lease_until=deadline,admission=check)
            self.early_state='RUNNING';self.stable.pop('xz',None);return
        if self.foreground_end_ns is None:
            self.foreground_end_ns=self.records['foreground_krita']['empty_confirmed_ns']
            # A fixed early stop deadline is cancelled only after real exit.
            with self.lock:
                for clock in self.clocks.values():clock.lease_until=0
            self.event('offline_foreground_exit_barrier',actual_ns=self.foreground_end_ns)
        after=(now-self.foreground_end_ns/1e9)
        release={'xz':0.,**self.offline['continuation']['release_after_foreground_exit_s']}
        for op in sorted(OPS,key=lambda op:release[op]):
            if op not in self.clocks or self.clocks[op].state!='FROZEN' or after<release[op]:continue
            check=self.continuation_admission(op,available,current)
            if not check['allowed']:self.stable.pop(op,None);continue
            self.stable.setdefault(op,now)
            if now-self.stable[op]<self.policy_config['resume_stable_s']:continue
            self.transition(op,False,'offline_native_continuation',lease_until=0,admission=check)
            self.stable.pop(op,None);break
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
            tasks[op]=TaskMemory(self.plan['priority']['task_priorities'].get(op,0),protected,
                                 protected or self.clocks[op].state=='RUNNING',current,min(anon,current),peak)
        available=memory()['MemAvailable']
        now=time.monotonic()
        if now-started>self.policy_config['guard_interval_s']:
            self.priority_policy.stable_since.clear()
            return
        self.last_decision=now
        self.tick_id+=1
        decision=self.priority_policy.decide(now,available,tasks)
        applied_limits={}
        for op,limit in sorted(decision['limits'].items()):
            write_memory_high(self.cm.checked(op),limit)
            applied_limits[op]=(self.cm.checked(op)/'memory.high').read_text().strip()
        self.decision_stream.write(json.dumps(dict(tick=self.tick_id,monotonic_s=now,
            checkpoint_ns=self.high_exit_ns,tasks={op:asdict(task) for op,task in sorted(tasks.items())},
            decision=decision,applied_memory_high=applied_limits))+'\n')
        for op in decision['freeze']:
            self.transition(op,True,'priority_pressure',admission=decision)
        if decision['abort']:
            raise RuntimeError('available memory fell below the experiment emergency floor')
        if decision['resume'] is not None:
            self.transition(decision['resume'],False,'priority_admission',lease_until=0,admission=decision)

    def schedule_serial_curves(self):
        t0=self.timeline.t0_ns
        if t0 is None:return
        elapsed=(time.monotonic_ns()-t0)/1e9
        offsets=self.plan['alignment']['offsets_s']
        for op in sorted(OPS,key=offsets.__getitem__):
            if op not in self.records and elapsed>=offsets[op]:self.launch(op)
        if time.monotonic()-self.last_decision<self.policy_config['guard_interval_s']:return
        sample=self.snapshot()
        if sample is None:return
        now,available,current,clocks=sample
        self.last_decision=now;self.tick_id+=1
        fg_done='foreground_krita' in self.done
        if self.high_exit_ns is None:
            exit_event=next((e for e in self.foreground_events if e.get('kind')=='HIGH_INSTANCE_EXIT'),None)
            if exit_event:
                pid=next(e['pid'] for e in self.foreground_events if e.get('kind')=='KRITA_PROCESS')
                if exit_event.get('pid')!=pid or exit_event.get('returncode')!=0:
                    raise RuntimeError('invalid high-memory Krita instance exit')
                if not Path('/proc',str(pid)).exists():
                    self.high_exit_ns=exit_event['monotonic_ns']
                    self.guard_history.clear()
                    self.event('high_instance_exit_barrier','foreground_krita',actual_ns=self.high_exit_ns,pid=pid)
        if fg_done and self.foreground_end_ns is None:
            self.foreground_end_ns=self.records['foreground_krita']['empty_confirmed_ns']
            self.event('offline_foreground_exit_barrier','foreground_krita',actual_ns=self.foreground_end_ns)
        budget=self.plan['budget']
        if not any(c.ever_started for c in clocks.values()):
            floor=budget['foreground_only_floor_bytes']
            guard=dict(available_bytes=available,required_bytes=floor,allowed=available>=floor)
        else:
            guard=self.live_guard(now,available,current,clocks)
        if now-self.last_guard_log>=1:
            self.decision_stream.write(json.dumps(dict(tick=self.tick_id,elapsed_s=elapsed,
                high_exit_ns=self.high_exit_ns,foreground_done=fg_done,current_bytes=current,live_guard=guard))+'\n')
            self.last_guard_log=now
        if not guard['allowed']:
            self.cancel_early('live memory floor')
            raise RuntimeError('observed available memory fell below active phase floor')
        for op in OPS:
            if op not in clocks or clocks[op].state!='FROZEN':continue
            if not fg_done:
                if op!='xz' or self.high_exit_ns is None:continue
                tail_growth=max(0,budget['tail_system_upper_bytes']-(budget['memtotal_bytes']-available))
                required=(budget['reserve_bytes']+self.plan['models']['xz']['peak_bytes']
                          +tail_growth+budget['tail_headroom_bytes'])
                check=dict(available_bytes=available,required_bytes=required,allowed=available>=required,
                           tail_future_growth_bytes=tail_growth,confirmed_high_exit_ns=self.high_exit_ns)
                reason='serial_curve_tail_release'
            else:
                offset=self.plan['continuation']['release_after_foreground_exit_s'].get(op,0)
                if now-self.foreground_end_ns/1e9<offset:continue
                check=self.continuation_admission(op,available,current)
                reason='offline_native_continuation'
            if not check['allowed']:
                self.stable.pop(op,None);continue
            self.stable.setdefault(op,now)
            if now-self.stable[op]<self.policy_config['resume_stable_s']:continue
            self.transition(op,False,reason,lease_until=0,admission=check)
            if op=='xz':self.early_state='TAIL_RELEASED' if not fg_done else 'RELEASED_AFTER_FOREGROUND'
            self.stable.pop(op,None)
            break
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
        self.watch_stop.set()
        if self.watch:self.watch.join(timeout=5)
        if self.watch and self.watch.is_alive():raise RuntimeError('lease watchdog did not stop')
        with self.lock:
            for op in self.clocks:self.update_times(op)
        if self.decision_stream:self.decision_stream.close()
        if self.watch_error:raise RuntimeError('lease watchdog failed: '+self.watch_error)
    def runtime_policy_evidence(self):
        if self.serial_run:
            if self.serial_policy=='priority':
                return dict(name='priority_freezer',background_start='run_on_submit',configuration=self.policy_config,
                            confirmed_checkpoint_ns=getattr(self,'high_exit_ns',None),guard_samples=self.tick_id,
                            policy_sha256=digest(Path(__file__).with_name('priority_policy.py')),
                            runner_sha256=digest(__file__))
            return dict(name='serial_curve_offline_v2',configuration=self.policy_config,
                        confirmed_high_exit_ns=getattr(self,'high_exit_ns',None),
                        early_state=getattr(self,'early_state',None),guard_samples=self.tick_id)
        return dict(name='curve_offline',configuration=self.policy_config,configuration_sha256=digest(self.policy_path),
                    early_state=getattr(self,'early_state',None),fallback_reason=getattr(self,'fallback_reason',None),
                    lease_watchdog_error=self.watch_error,guard_samples=self.tick_id,
                    offline_plan_sha256=digest(self.out/'planning/offline_plan.json') if (self.out/'planning/offline_plan.json').exists() else None,
                    note='Fixed offline stop deadline is never renewed. Live checks can veto or delay, never create a new early window.')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--profiles',default='.')
    a.add_argument('--planner');a.add_argument('--policy-config');a.add_argument('--serial-run',required=True)
    a.add_argument('--serial-policy',choices=('priority','offline'),default='priority')
    a.add_argument('--foreground-run',required=True);a.add_argument('--foreground-source',required=True);v=a.parse_args()
    if not v.planner and v.serial_policy=='offline':
        a.error('--planner is required for offline planning')
    def stop(signum,frame):raise KeyboardInterrupt('termination signal')
    signal.signal(signal.SIGTERM,stop)
    raise SystemExit(SegmentedFreezer(v.output,v.profiles,v.planner or '.',v.policy_config,
                                     v.serial_run,v.foreground_run,v.foreground_source,v.serial_policy).run())
