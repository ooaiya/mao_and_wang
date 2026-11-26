"""Timestamp observed native application log completion; never starts computation."""
import argparse,json,time
from pathlib import Path
from capture import event

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--log-file',type=Path);p.add_argument('--success-text',required=True);p.add_argument('--count',type=int,default=1);p.add_argument('--failure-text');a=p.parse_args()
    folder=a.directory;cg=Path(json.loads((folder/'environment.json').read_text())['cgroup']);previous=time.monotonic_ns()
    while cg.exists():
        now=time.monotonic_ns();source=a.log_file or folder/'application.log';content=source.read_text(errors='replace') if source.exists() else ''
        if a.failure_text and a.failure_text in content:event(folder,'task_failed',{'source':str(source),'failure_text':a.failure_text});return
        if content.count(a.success_text)>=a.count:
            event(folder,'task_complete',{'source':str(source),'success_text':a.success_text,'count':a.count,'previous_poll_ns':previous,'first_confirmed_ns':now,'poll_interval_s':(now-previous)/1e9,'limitation':'Log buffering may add latency; output verification is separate.'});return
        previous=now;time.sleep(.25)
    raise SystemExit('Application ended before expected log completion')
if __name__=='__main__':main()
