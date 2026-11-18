"""TEST_ONLY: real repeated kernel transitions and lease watchdog, no GUI/Swap."""
import json,os,subprocess,sys,threading,time
from pathlib import Path
from segmented_runner import SegmentedFreezer
from segmented_scheduler import TaskClock
from independent_runner import ROOT,save,members,wait_empty
from common.cgroup_manager import CgroupManager
from common.timeline import Timeline

def qualify(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);os.chown(out,1000,1000)
    parent=CgroupManager.current();CgroupManager.prepare_delegation(parent);cm=CgroupManager(parent,'oomlab_segment_probe_'+str(os.getpid()));cg=cm.create('xz')
    counter=out/'counter';ready=out/'ready';read_fd,write_fd=os.pipe()
    code="import os,sys,time;from pathlib import Path;Path(sys.argv[1]+'/cgroup.procs').write_text(str(os.getpid()));Path('/proc/self/oom_score_adj').write_text('0');os.setgroups([]);os.setgid(1000);os.setuid(1000);Path(sys.argv[2]).write_text('ready');os.read(int(sys.argv[4]),1);p=Path(sys.argv[3]);n=0\nwhile n<300:\n p.write_text(str(n));n+=1;time.sleep(.01)\n"
    child=subprocess.Popen([sys.executable,'-c',code,str(cg),str(ready),str(counter),str(read_fd)],pass_fds=(read_fd,));os.close(read_fd)
    r=object.__new__(SegmentedFreezer);r.out=out;r.cm=cm;r.clocks={};r.records={};r.groups={'xz':dict(cgroup_path=str(cg))};r.processes={'xz':child};r.done=set()
    r.lock=threading.RLock();r.watch_stop=threading.Event();r.watch_error=None;r.freeze_rows=[];r.tick_id=1;r.decision_stream=None;r.timeline=Timeline(out,'TEST_ONLY_segmented_probe')
    r.policy_config=json.loads(Path(__file__).with_name('segmented_policy.json').read_text());r.watch=None
    result=dict(test_only=True,real_gui=False,formal_workloads=False,swap_changed=False,status='FAILED')
    try:
        deadline=time.monotonic()+5
        while not ready.exists():
            if child.poll() is not None or time.monotonic()>deadline:raise RuntimeError('counter readiness failed')
            time.sleep(.01)
        p=cm.set_frozen('xz',True,timeout=.5);stamp=p['confirmed_monotonic_ns'];p.update(operation='xz',action='freeze');r.freeze_rows.append(p)
        r.clocks['xz']=TaskClock(frozen_since=stamp/1e9);r.records['xz']=dict(freeze_confirmed_ns=stamp,state='FROZEN',pause_intervals_ns=[[stamp,None]],running_intervals_ns=[])
        os.write(write_fd,b'G');os.close(write_fd);write_fd=None
        r.watch=threading.Thread(target=r.watchdog);r.watch.start()
        r.transition('xz',False,'test_manual_resume',lease_until=time.monotonic()+2);time.sleep(.15)
        r.transition('xz',True,'test_manual_pause');before=counter.read_text();time.sleep(.15);after=counter.read_text()
        if before!=after:raise RuntimeError('counter moved while confirmed frozen')
        r.transition('xz',False,'test_watchdog_resume',lease_until=time.monotonic()+.2)
        deadline=time.monotonic()+2
        while r.clocks['xz'].state!='FROZEN' and time.monotonic()<deadline:time.sleep(.02)
        if r.clocks['xz'].state!='FROZEN' or r.freeze_rows[-1].get('reason')!='offline_planned_deadline_watchdog':raise RuntimeError('watchdog did not freeze counter')
        before=counter.read_text();time.sleep(.15)
        if counter.read_text()!=before:raise RuntimeError('counter moved after watchdog confirmation')
        r.transition('xz',False,'test_final_resume',lease_until=time.monotonic()+5)
        if child.wait(timeout=5)!=0:raise RuntimeError('counter did not finish')
        wait_empty(cg);end=time.monotonic_ns();r.done.add('xz');r.clocks['xz'].finished(end/1e9);r.records['xz']['running_intervals_ns'][-1][1]=end
        result.update(status='PASS',kernel_events=r.freeze_rows,effective_model_age_s=r.clocks['xz'].active_s,counter_final=counter.read_text(),watchdog_error=r.watch_error)
    finally:
        r.before_cleanup()
        if write_fd is not None:os.close(write_fd)
        if members(cg):(cg/'cgroup.kill').write_text('1');child.wait(timeout=5)
        r.timeline.close();cm.cleanup(thaw=True);save(out/'qualification.json',result)
    print(json.dumps(dict(status=result['status'],output=str(out),events=len(r.freeze_rows),watchdog_error=r.watch_error)))

if __name__=='__main__':qualify(sys.argv[1])
