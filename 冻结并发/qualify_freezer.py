"""Real small counter worker; independent of the four formal workloads."""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'基线并发'))
from common.cgroup_manager import CgroupManager

def qualify(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    parent=CgroupManager.current();CgroupManager.prepare_delegation(parent);cm=CgroupManager(parent,'oomlab_freezer_probe_'+str(os.getpid()));cg=cm.create('probe')
    counter=out/'counter';r,w=os.pipe()
    script="import os,sys,time;from pathlib import Path;Path(sys.argv[1]+'/cgroup.procs').write_text(str(os.getpid()));os.read(int(sys.argv[3]),1);p=Path(sys.argv[2]);n=0\nwhile n<200:\n p.write_text(str(n));n+=1;time.sleep(.01)\n"
    child=subprocess.Popen([sys.executable,'-c',script,str(cg),str(counter),str(r)],pass_fds=(r,));os.close(r)
    result={}
    try:
        until=time.monotonic()+5
        while str(child.pid) not in (cg/'cgroup.procs').read_text().split():
            if time.monotonic()>until:raise TimeoutError('probe attach')
            time.sleep(.01)
        os.write(w,b'G');os.close(w);time.sleep(.2)
        frozen=cm.set_frozen('probe',True);before=counter.read_text();time.sleep(.3);after=counter.read_text()
        if before!=after:raise RuntimeError('counter advanced while kernel confirmed frozen')
        resumed=cm.set_frozen('probe',False);time.sleep(.2)
        if int(counter.read_text())<=int(after):raise RuntimeError('counter did not resume')
        if child.wait(timeout=5)!=0:raise RuntimeError('counter failed')
        result=dict(success=True,freeze=frozen,resume=resumed,frozen_counter_before=before,frozen_counter_after=after,returncode=child.returncode)
    finally:
        if child.poll() is None:(cg/'cgroup.kill').write_text('1');child.wait(timeout=5)
        cm.cleanup(thaw=True)
    (out/'qualification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':qualify(sys.argv[1])
