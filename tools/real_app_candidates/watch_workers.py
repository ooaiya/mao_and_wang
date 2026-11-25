"""Observe known computation children finishing, without submitting computation."""
import argparse,json,time
from pathlib import Path
from capture import event


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--workers',nargs='+',required=True);p.add_argument('--artifact',type=Path,required=True);a=p.parse_args()
    folder=a.directory;cg=Path(json.loads((folder/'environment.json').read_text())['cgroup']);seen=False;previous=None
    while cg.exists():
        now=time.monotonic_ns();names=[]
        for f in cg.rglob('cgroup.procs'):
            for pid in f.read_text().split():
                try:names.append(Path('/proc',pid,'comm').read_text().strip())
                except OSError:pass
        active=any(n in a.workers for n in names)
        if active:seen=True;previous=now
        elif seen:
            if not a.artifact.exists() or a.artifact.stat().st_size<=8:raise SystemExit('Workers exited without nonempty output')
            event(folder,'task_complete',dict(source='worker disappearance and nonempty artifact; GUI success still needs verification',last_worker_monotonic_ns=previous,first_absent_monotonic_ns=now,uncertainty_s=(now-previous)/1e9,artifact=str(a.artifact)))
            return
        time.sleep(.5)
    raise SystemExit('Application cgroup ended before worker completion')
if __name__=='__main__':main()
