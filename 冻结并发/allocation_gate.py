"""Attach before allocation; wait on a pipe that can be held under real freezer."""
import argparse,json,os,time
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('--group',required=True);a.add_argument('--ready',required=True);a.add_argument('--fd',type=int,required=True);a.add_argument('command',nargs=argparse.REMAINDER);v=a.parse_args()
Path(v.group,'cgroup.procs').write_text(str(os.getpid()))
Path('/proc/self/oom_score_adj').write_text('0')
os.setgroups([4,24,27,46]);os.setgid(1000);os.setuid(1000)
Path(v.ready).write_text(json.dumps(dict(pid=os.getpid(),ready_ns=time.monotonic_ns(),allocation_started=False)))
if os.read(v.fd,1)!=b'G':raise SystemExit(125)
os.close(v.fd)
command=v.command[1:] if v.command[0]=='--' else v.command
os.execvpe(command[0],command,os.environ)
