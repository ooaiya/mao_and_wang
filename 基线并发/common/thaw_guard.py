#!/usr/bin/env python3
"""Independent death-thaw guard for the fixed Freezer line; never touches Krita."""
import argparse
import json
import os
from pathlib import Path
import select
import time


def main():
    a=argparse.ArgumentParser();a.add_argument('--pipe-fd',required=True,type=int);a.add_argument('--groups',required=True);a.add_argument('--log',required=True);a.add_argument('--deadline',required=True,type=float);args=a.parse_args();groups=json.loads(args.groups)
    reason='guard_deadline'
    while time.monotonic()<args.deadline:
        ready,_,_=select.select([args.pipe_fd],[],[],min(1,max(0,args.deadline-time.monotonic())))
        if ready:
            value=os.read(args.pipe_fd,1);reason='normal_cleanup' if value==b'Q' else 'runner_pipe_closed';break
    with open(args.log,'a') as log:
        for item in groups:
            path=Path(item['path'])
            try:
                if path.stat().st_ino!=item['inode']:raise RuntimeError('group generation changed')
                (path/'cgroup.freeze').write_text('0')
                log.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),cgroup=str(path),reason=reason,thaw_requested=True,events=(path/'cgroup.events').read_text()))+'\n')
            except FileNotFoundError:pass
            except Exception as error:log.write(json.dumps(dict(cgroup=str(path),reason=reason,error=repr(error)))+'\n')


if __name__=='__main__':main()
