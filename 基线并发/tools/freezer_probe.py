#!/usr/bin/env python3
"""Real lightweight freezer qualification. Unsupported hosts return BLOCKED."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common.cgroup_manager import CgroupManager,fields


def qualify(parent,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);cm=None;child=None;result={'status':'BLOCKED','simulated':False}
    try:
        CgroupManager.prepare_delegation(parent);cm=CgroupManager(parent,'oomlab_'+uuid.uuid4().hex[:10]);group=cm.create('probe')
        counter=output/'counter';worker=output/'worker.py'
        worker.write_text('import pathlib,time,os\np=pathlib.Path('+repr(str(counter))+')\nn=0\nwhile n<1000:\n p.write_text(str(n));n+=1;time.sleep(.01)\n')
        receipt=output/'ready.json';r,w=os.pipe();wrapper=Path(__file__).resolve().parents[1]/'common/gated_exec.py'
        child=subprocess.Popen([sys.executable,str(wrapper),'--cgroup',str(group),'--receipt',str(receipt),'--gate-fd',str(r),'--',sys.executable,str(worker)],pass_fds=(r,),start_new_session=True);os.close(r)
        limit=time.monotonic()+3
        while not receipt.exists() and time.monotonic()<limit:time.sleep(.01)
        if not receipt.exists():raise RuntimeError('probe did not enter owned group')
        os.write(w,b'G');os.close(w);time.sleep(.2)
        if not counter.exists():raise RuntimeError('probe heartbeat missing')
        freeze=cm.set_frozen('probe',True);time.sleep(.05);before=counter.read_text();time.sleep(.3);after=counter.read_text()
        if before!=after:raise RuntimeError('worker executed while frozen=1')
        resume=cm.set_frozen('probe',False);time.sleep(.2);continued=counter.read_text()
        if continued==after:raise RuntimeError('worker did not resume')
        result.update(status='PASS',cgroup_version=2,freeze_interface=str(group/'cgroup.freeze'),cgroup=str(group),pid=child.pid,freeze=freeze,resume=resume,counter_during_freeze=[before,after],counter_after_resume=continued)
    except Exception as error:result['reason']=repr(error)
    finally:
        if cm:
            try:cm.set_frozen('probe',False)
            except Exception:pass
        if child and child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=3)
        if cm:result['cleanup_errors']=cm.cleanup()
        (output/'freezer_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--cgroup-parent');a.add_argument('--output',type=Path,required=True);args=a.parse_args();result=qualify(args.cgroup_parent or CgroupManager.current(),args.output);print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['status']=='PASS' else 2)
