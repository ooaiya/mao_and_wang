#!/usr/bin/env python3
"""Independent-prior Oracle CLI planning + owned cgroup v2 freezer execution.

This explicit mode is separate from the historical concurrent-profile daemon.
Only admission can move later at runtime; allocation gate precedes real freeze.
"""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'串行测试'))
from run_serial import Serial,members,wait_empty,digest,save
from independent_plan import plan,OPS
from freezer_monitor import Monitor,memory,values
from restore_swap import active,restore

class Freezer(Serial):
    run_kind='freezer'
    background_ops=OPS
    def __init__(self,out,profiles,binary):
        super().__init__(out,'/home/ooaiya')
        self.profiles=Path(profiles);self.binary=Path(binary);self.freeze_rows=[];self.pipes={};self.done=set();self.last_wait={};self.started=time.monotonic_ns();self.foreground_events=[]
    def prepare(self,start_monitor=False):
        super().prepare(start_monitor=False)
        save(self.out/'swap_state.json',dict(entries=active(),proc_swaps=Path('/proc/swaps').read_text()))
        subprocess.run(['swapoff','-a'],check=True)
        if memory().get('SwapTotal',0)!=0:raise RuntimeError('Swap is not fully disabled')
        m=memory();self.plan=plan(self.profiles,self.out/'planning',self.binary,m['MemTotal'],m['MemTotal']-m['MemAvailable'])
        save(self.out/'source_runtime.json',dict(files={str(p.relative_to(ROOT)):digest(p) for p in [*Path(__file__).parent.glob('*.py'),ROOT/'串行测试/run_serial.py']},planner_binary=str(self.binary),planner_sha256=digest(self.binary)))
        self.monitor=Monitor(self.out,self.timeline,self.groups);self.monitor.start()
    def command(self,op):
        if op=='foreground_krita':
            return [str(self.home/'bg/.venv/bin/python'),'-u',str(self.gui/'scripts/krita_auto.py'),self.config['asset']['path'],
                '--layers-dir',self.config['pilot']['layers_dir'],'--settings',str(self.out/'foreground_config.json'),
                '--assets-manifest',str(self.out/'foreground_assets.json'),'--process-record',str(self.out/op/'process.json')]
        return [str(self.home/'bg/.venv/bin/python'),'-m','oomlab.workloads',self.provenance[op]['path'],str(self.out/op),'--operation-id',op]
    def launch(self,op,*,freeze_on_submit=True,defer_release=False):
        folder=self.out/op;folder.mkdir();os.chown(folder,1000,1000);cg=self.cm.create(op)
        self.groups[op]=dict(cgroup_path=str(cg),pid=None)
        save(folder/'memory_controls.json',{k:(cg/k).read_text().strip() for k in ['memory.max','memory.high','memory.swap.max','memory.oom.group']})
        r,w=os.pipe();self.pipes[op]=w;log=(folder/'process.log').open('w');self.logs.append(log)
        command=self.command(op);start=time.monotonic_ns();ready=folder/'gate_ready.json'
        p=subprocess.Popen([sys.executable,str(Path(__file__).with_name('allocation_gate.py')),'--group',str(cg),'--ready',str(ready),'--fd',str(r),'--',*command],pass_fds=(r,),cwd=self.home/'bg',env=self.env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        os.close(r);self.processes[op]=p;self.groups[op]['pid']=p.pid;self.records[op]=dict(pid=p.pid,created_ns=start,command=command,cgroup=str(cg))
        until=time.monotonic()+10
        while not ready.exists():
            if p.poll() is not None:raise RuntimeError(op+' allocation gate failed')
            if time.monotonic()>until:raise TimeoutError(op+' allocation gate readiness')
            time.sleep(.005)
        if defer_release:
            self.event('allocation_gate_ready',op,actual_ns=time.monotonic_ns(),large_allocation_started=False)
            return
        self.event('task_submitted',op,actual_ns=start,nominal_offset_s=self.plan['alignment']['offsets_s'].get(op,0),large_allocation_started=False)
        foreground=op=='foreground_krita'
        if freeze_on_submit and not foreground:
            proof=self.cm.set_frozen(op,True);self.records[op]['freeze_confirmed_ns']=proof['confirmed_monotonic_ns']
            proof.update(operation=op,action='freeze',memory_current_bytes=int((cg/'memory.current').read_text()),cpu_usage_usec=values(cg/'cpu.stat')['usage_usec'])
            self.freeze_rows.append(proof);save(self.out/'freeze_events.json',self.freeze_rows)
            # Queue the execution token while the kernel still holds the child.
            os.write(w,b'G');os.close(w);del self.pipes[op]
            self.event('freeze_confirmed',op,actual_ns=proof['confirmed_monotonic_ns'],proof=proof)
            return
        released=time.monotonic_ns()
        os.write(w,b'G');os.close(w);del self.pipes[op]
        self.records[op]['release_confirmed_ns']=released
        if foreground:
            self.event('task_start',op,actual_ns=start)
        else:
            self.event('allocation_gate_released',op,actual_ns=released,reason='run_on_submit')
    def background_start_ns(self, op):
        path=self.out/op/'phase_trace.jsonl'
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    event=json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event['event_type']=='task_start':
                    return event['monotonic_ns']
        return None

    def observe(self):
        if 'foreground_krita' in self.processes:
            path=self.out/'foreground_krita/process.log'
            lines=path.read_text().splitlines()
            events=[json.loads(x[len('@@OOM_EVENT '):]) for x in lines if x.startswith('@@OOM_EVENT ')]
            self.foreground_events=events
            if self.timeline.t0_ns is None:
                ready=next((e for e in events if e.get('kind')=='KRITA_PROCESS'),None)
                if ready:
                    self.timeline.t0_ns=ready['monotonic_ns'];self.event('homepage_ready','foreground_krita',actual_ns=self.timeline.t0_ns,pid=ready['pid'])
        for op,p in list(self.processes.items()):
            rec=self.records[op]
            if op in self.background_ops and 'actual_start_ns' not in rec:
                stamp=self.background_start_ns(op)
                if stamp is not None:
                    rec['actual_start_ns']=stamp;self.event('task_start',op,actual_ns=stamp)
            if op in self.done or p.poll() is None:continue
            rec.update(returncode=p.returncode,exit_observed_ns=time.monotonic_ns())
            wait_empty(self.groups[op]['cgroup_path']);rec['empty_confirmed_ns']=time.monotonic_ns();self.done.add(op)
            rec['process_wall_s']=(rec['empty_confirmed_ns']-rec['created_ns'])/1e9
            rec['execution_wall_s']=(rec['empty_confirmed_ns']-rec.get('actual_start_ns',rec['created_ns']))/1e9
            self.event('task_end',op,returncode=p.returncode,execution_wall_s=rec['execution_wall_s'])
            save(self.out/'tasks.partial.json',self.records)
            if p.returncode!=0:raise RuntimeError(op+' exited '+str(p.returncode))
    def admission(self,op):
        m=memory();future_fg=0;future_running=0
        if 'foreground_krita' not in self.done:
            current=int((Path(self.groups['foreground_krita']['cgroup_path'])/'memory.current').read_text())
            # Do not age away a possible foreground peak because import ran slowly.
            future_fg=max(0,self.plan['models']['foreground_krita']['peak_bytes']-current)
        for other in OPS:
            if other in self.records and other not in self.done and 'release_confirmed_ns' in self.records[other]:
                current=int((Path(self.groups[other]['cgroup_path'])/'memory.current').read_text())
                future_running+=max(0,self.plan['models'][other]['peak_bytes']-current)
        required=self.plan['budget']['reserve_bytes']+future_fg+future_running+self.plan['models'][op]['peak_bytes']
        return dict(allowed=m['MemAvailable']>=required,available_bytes=m['MemAvailable'],required_bytes=required,foreground_future_growth_bytes=future_fg,running_future_growth_bytes=future_running,candidate_peak_bytes=self.plan['models'][op]['peak_bytes'],reserve_bytes=self.plan['budget']['reserve_bytes'])
    def scheduled(self):
        if self.timeline.t0_ns is None:return
        now=time.monotonic_ns();elapsed=(now-self.timeline.t0_ns)/1e9
        for op in sorted(OPS,key=lambda x:self.plan['alignment']['offsets_s'][x]):
            if op not in self.records and elapsed>=self.plan['alignment']['offsets_s'][op]:self.launch(op)
        for op in sorted(OPS,key=lambda x:self.plan['planned_release_s'][x]):
            if op not in self.records or op in self.done or 'release_confirmed_ns' in self.records[op]:continue
            rec=self.records[op]
            if elapsed<self.plan['planned_release_s'][op]:continue
            check=self.admission(op)
            if time.monotonic()-self.last_wait.get(op,0)>1:
                self.event('admission_check',op,**check);self.last_wait[op]=time.monotonic()
            if not check['allowed']:rec.pop('safe_since',None);continue
            rec.setdefault('safe_since',time.monotonic())
            if time.monotonic()-rec['safe_since']<.5:continue
            proof=self.cm.set_frozen(op,False);rec['release_confirmed_ns']=proof['confirmed_monotonic_ns']
            rec['frozen_s']=(rec['release_confirmed_ns']-rec['freeze_confirmed_ns'])/1e9
            cg=Path(self.groups[op]['cgroup_path']);proof.update(operation=op,action='resume',memory_current_bytes=int((cg/'memory.current').read_text()),cpu_usage_usec=values(cg/'cpu.stat')['usage_usec'],admission=check)
            self.freeze_rows.append(proof);save(self.out/'freeze_events.json',self.freeze_rows)
            self.event('resume_confirmed',op,actual_ns=proof['confirmed_monotonic_ns'],proof=proof)
    def run(self):
        error=None;stats={};restoration_error=None
        try:
            self.prepare();self.launch('foreground_krita')
            while len(self.done)<4:
                self.observe();self.scheduled()
                if self.monitor.errors:raise RuntimeError('collector: '+repr(self.monitor.errors))
                if values('/proc/vmstat')['oom_kill']!=self.oom_before:raise RuntimeError('unexpected global OOM kill')
                if memory().get('SwapTotal',0):raise RuntimeError('Swap changed during measurement')
                if (time.monotonic_ns()-self.started)/1e9>4500:raise TimeoutError('bounded experiment deadline')
                for op,rec in self.records.items():
                    origin=rec.get('release_confirmed_ns')
                    if op in self.done or origin is None:
                        continue
                    now=time.monotonic_ns()
                    age=self.execution_age_s(op,now) if hasattr(self,'execution_age_s') else (now-origin)/1e9
                    if age>2000:raise TimeoutError(op+' execution timeout')
                time.sleep(.05)
            time.sleep(.2)  # Retain observed post-exit charge, not an invented zero.
        except BaseException as e:
            error=repr(e)
            self.event('freezer_error',error=error,filename=getattr(e,'filename',None))
        finally:
            cleanup_errors=[]
            if hasattr(self,'before_cleanup'):
                try:self.before_cleanup()
                except Exception as e:cleanup_errors.append(repr(e))
            for op,p in self.processes.items():
                try:
                    cg=Path(self.groups[op]['cgroup_path'])
                    if members(cg):
                        self.records[op]['cleanup_terminated']=True
                        (cg/'cgroup.kill').write_text('1');wait_empty(cg)
                    if p.poll() is None:p.wait(timeout=10)
                    stamp=time.monotonic_ns();rec=self.records[op]
                    rec.setdefault('returncode',p.returncode);rec.setdefault('exit_observed_ns',stamp);rec.setdefault('empty_confirmed_ns',stamp)
                    rec.setdefault('execution_wall_s',(stamp-rec.get('actual_start_ns',rec['created_ns']))/1e9)
                    if hasattr(self,'after_task_cleanup'):self.after_task_cleanup(op,stamp)
                except Exception as e:cleanup_errors.append(repr(e))
            for w in self.pipes.values():os.close(w)
            if self.monitor:stats=self.monitor.stop()
            if self.inhibitor:self.inhibitor.terminate();self.inhibitor.wait(timeout=5)
            for f in self.logs:f.close()
            if (self.out/'swap_state.json').exists():
                try:restore(self.out/'swap_state.json')
                except Exception as e:restoration_error=repr(e)
            finish=max((r.get('empty_confirmed_ns',r['created_ns']) for r in self.records.values()),default=time.monotonic_ns())
            t0=self.timeline.t0_ns
            result=dict(status='EXECUTED' if error is None and not cleanup_errors and not restoration_error else 'FAILED',error=error,cleanup_errors=cleanup_errors,swap_restoration_error=restoration_error,
                T0_monotonic_ns=t0,T0_event='automatic_KRITA_PROCESS_homepage_ready',order=list(self.records),tasks=self.records,
                total_from_homepage_s=(finish-t0)/1e9 if t0 else None,total_from_first_launch_s=(finish-min(r['created_ns'] for r in self.records.values()))/1e9 if self.records else None,
                all_groups_empty=all(not members(v['cgroup_path']) for v in self.groups.values()),collector=stats,
                global_oom_kill_delta=values('/proc/vmstat')['oom_kill']-self.oom_before if self.oom_before is not None else None,
                source_kind=getattr(self,'plan',{}).get('source_kind','MEASURED_INDEPENDENT_PRIOR'),
                baseline_rerun=False,swaps_after=Path('/proc/swaps').read_text())
            if hasattr(self,'runtime_policy_evidence'):result['runtime_policy']=self.runtime_policy_evidence()
            save(self.out/'summary.json',result);self.timeline.close()
            if hasattr(self,'cm'):self.cm.cleanup(thaw=False)
        return 0 if result['status']=='EXECUTED' else 1

