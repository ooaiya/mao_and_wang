"""Process lifecycle, start gates and measurement shared by the concurrent modes."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .experiment import Experiment, members, wait_empty
from .restore_swap import active, restore
from .sampling import Monitor, memory, values
from .shaped_scene import load, load_offsets, make_plan, save


class ConcurrentRun(Experiment):
    def __init__(self, out, foreground_run, foreground_source, shaped_run, offsets, policy_path):
        super().__init__(out, '/home/ooaiya', foreground_run, foreground_source, shaped_run)
        self.offsets = Path(offsets)
        self.policy_config = load(policy_path)
        priority = self.policy_config['priority']
        if priority.get('memory_high') or priority.get('emergency_floor_bytes') is not None:
            raise ValueError('this scene does not configure memory.high or a live emergency floor')
        self.freeze_rows = []
        self.pipes = {}
        self.done = set()
        self.started = time.monotonic_ns()
        self.foreground_events = []

    def prepare(self):
        super().prepare(start_monitor=False)
        load_offsets(self.offsets)
        save(self.out/'swap_state.json', dict(entries=active(), proc_swaps=Path('/proc/swaps').read_text()))
        subprocess.run(['swapoff', '-a'], check=True)
        mem = memory()
        if mem['SwapTotal']:
            raise RuntimeError('Swap is not fully disabled')
        environment = load(self.out/'environment.json')
        environment.update(meminfo=mem, swaps=Path('/proc/swaps').read_text(), swap_changed=True)
        save(self.out/'environment.json', environment)
        self.plan = make_plan(self.shaped_reference, self.foreground_run, self.offsets,
                              self.out/'planning', mem['MemTotal'], self.provenance, self.policy_config)
        save(self.out/'offline_execution_config.json', self.policy_config)
        self.initialize()
        self.monitor = Monitor(self.out, self.timeline, self.groups)
        self.monitor.start()

    def launch(self,op,*,defer_release=False):
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
    def run(self):
        error=None;stats={};restoration_error=None
        try:
            self.prepare();self.launch('foreground_krita')
            while len(self.done)<len(self.order):
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



def run_cli(runner, default_policy):
    parser = argparse.ArgumentParser(description=runner.__doc__)
    for name in ('output', 'foreground-run', 'foreground-source', 'shaped-run', 'offsets'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--policy-config', type=Path, default=default_policy)
    args = parser.parse_args()

    def stop(signum, frame):
        raise KeyboardInterrupt('termination signal')

    signal.signal(signal.SIGTERM, stop)
    return runner(args.output, args.foreground_run, args.foreground_source,
                  args.shaped_run, args.offsets, args.policy_config).run()
