"""Observe a native writer closing its real output; never execute a workload."""
import argparse,json,time,os
from pathlib import Path
from capture import event

def open_pids(cgroup,artifact):
    found=[]
    for membership in cgroup.rglob('cgroup.procs'):
        try:pids=membership.read_text().split()
        except OSError:continue
        for pid in pids:
            try:
                for fd in Path('/proc',pid,'fd').iterdir():
                    try:
                        if os.readlink(fd)==str(artifact):found.append(int(pid));break
                    except OSError:pass
            except OSError:pass
    return found

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True);a=p.parse_args()
    cg=Path(json.loads((a.directory/'environment.json').read_text())['cgroup']);artifact=a.artifact.resolve();seen=False;last=None
    while cg.exists():
        now=time.monotonic_ns();pids=open_pids(cg,artifact);size=artifact.stat().st_size if artifact.exists() else 0
        if pids and size>1024:
            if not seen:event(a.directory,'task_progress',dict(source='native output fd observed in application cgroup',artifact=str(artifact),pids=pids,bytes=size))
            seen=True;last=now
        elif seen and not pids:
            event(a.directory,'task_complete',dict(source='native writer output fd closed after nonempty output; GUI all-green verification required separately',artifact=str(artifact),bytes=size,last_open_monotonic_ns=last,first_closed_monotonic_ns=now,poll_uncertainty_s=(now-last)/1e9))
            return
        time.sleep(.5)
    raise SystemExit('Application ended before writer completion observed')
if __name__=='__main__':main()
