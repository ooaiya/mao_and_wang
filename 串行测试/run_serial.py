#!/usr/bin/env python3
"""Run the current four workloads in strict serial order."""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'基线并发'))
from common.experiment import Experiment, members, save, wait_empty
from common.monitor import meminfo, counters
from common.restore_swap import restore as restore_swap
from common.shaped_scene import FOREGROUND, TASKS

ORDER = [FOREGROUND, *TASKS]


def validate_sequence(records,order=ORDER):
    if list(records)!=order:return False
    return all(records[b]['start_ns']>=records[a]['empty_confirmed_ns'] for a,b in zip(order,order[1:]))

class Serial(Experiment):
    def launch(self,op,command):
        if any(members(v['cgroup_path']) for v in self.groups.values()):raise RuntimeError('previous task boundary not empty')
        folder=self.out/op;folder.mkdir();os.chown(folder,1000,1000)
        cg=self.cm.create(op);self.groups[op]=dict(cgroup_path=str(cg),pid=None)
        save(folder/'memory_controls.json',{k:(cg/k).read_text().strip() for k in ['memory.max','memory.high','memory.swap.max','memory.oom.group']})
        gate="import os,sys;from pathlib import Path;Path(sys.argv[1]+'/cgroup.procs').write_text(str(os.getpid()));Path('/proc/self/oom_score_adj').write_text('0');os.setgroups([4,24,27,46]);os.setgid(1000);os.setuid(1000);os.execvpe(sys.argv[2],sys.argv[2:],os.environ)"
        log=(folder/'process.log').open('w');self.logs.append(log)
        if self.timeline.t0_ns is None:self.timeline.t0_ns=time.monotonic_ns()
        start=time.monotonic_ns()
        p=subprocess.Popen([sys.executable,'-c',gate,str(cg),*command],cwd=self.home/'bg',env=self.env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.processes[op]=p;self.groups[op]['pid']=p.pid
        self.records[op]=dict(pid=p.pid,start_ns=start,command=command,cgroup=str(cg))
        self.event('task_start',op,actual_ns=start,pid=p.pid,command=command)
        deadline=time.monotonic()+2000
        while p.poll() is None:
            if self.monitor.errors:raise RuntimeError('sampling failed: '+repr(self.monitor.errors))
            if counters('/proc/vmstat')['oom_kill']!=self.oom_before:raise RuntimeError('unexpected OOM during serial run')
            if self.no_swap and meminfo().get('SwapTotal',0)!=0:raise RuntimeError('Swap changed during serial run')
            if time.monotonic()>deadline:raise TimeoutError(op+' deadline exceeded')
            time.sleep(.05)
        self.records[op].update(exit_observed_ns=time.monotonic_ns(),returncode=p.returncode)
        wait_empty(cg);self.records[op]['empty_confirmed_ns']=time.monotonic_ns()
        self.records[op]['duration_s']=(self.records[op]['empty_confirmed_ns']-start)/1e9
        save(self.out/'tasks.partial.json',self.records)
        self.event('task_end',op,returncode=p.returncode,duration_s=self.records[op]['duration_s'])
        if p.returncode!=0:raise RuntimeError(op+' failed with exit '+str(p.returncode))
    def run(self):
        error=None
        try:
            self.prepare()
            for op in self.order:
                self.launch(op,self.command(op))
        except BaseException as e:error=repr(e);self.event('serial_error',error=error)
        finally:
            # Close only this run's process groups, including orphaned GUI helpers.
            for op,p in self.processes.items():
                cg=Path(self.groups[op]['cgroup_path'])
                if members(cg):
                    (cg/'cgroup.kill').write_text('1');wait_empty(cg)
                if p.poll() is None:p.wait(timeout=10)
            stats=self.monitor.stop() if self.monitor else {}
            if self.inhibitor:self.inhibitor.terminate();self.inhibitor.wait(timeout=5)
            for log in self.logs:log.close()
            finish=time.monotonic_ns();workload_finish=max((r.get('empty_confirmed_ns',r['start_ns']) for r in self.records.values()),default=finish)
            result=dict(status='EXECUTED' if error is None else 'FAILED',error=error,order=self.order,tasks=self.records,
                T0_monotonic_ns=self.timeline.t0_ns,total_workload_wall_s=(workload_finish-self.timeline.t0_ns)/1e9 if self.timeline.t0_ns else None,
                all_groups_empty=all(not members(v['cgroup_path']) for v in self.groups.values()),strict_serial=validate_sequence(self.records,self.order),collector=stats,
                global_oom_kill_delta=counters('/proc/vmstat')['oom_kill']-self.oom_before if self.oom_before is not None else None,
                swap_changed=self.no_swap,swaps_after=Path('/proc/swaps').read_text(),note='output verification and final success are computed after sampling, not during the next workload')
            try:
                save(self.out/'summary.json',result);self.timeline.close()
                if hasattr(self,'cm'):self.cm.cleanup(thaw=False)
            finally:
                if self.no_swap:restore_swap(self.out/'swap_state.json')
        return 0 if error is None else 1

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--home',default='/home/ooaiya')
    a.add_argument('--foreground-run',required=True);a.add_argument('--foreground-source',required=True);a.add_argument('--no-swap',action='store_true')
    a.add_argument('--shaped-run',type=Path,required=True)
    args=a.parse_args()
    if not args.no_swap:a.error('--shaped-run requires --no-swap for comparable results')
    def interrupt(signum,frame):raise KeyboardInterrupt('termination signal')
    signal.signal(signal.SIGTERM,interrupt)
    raise SystemExit(Serial(args.output,args.home,args.foreground_run,args.foreground_source,args.shaped_run,args.no_swap).run())
