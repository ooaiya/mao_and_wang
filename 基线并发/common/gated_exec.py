#!/usr/bin/env python3
"""Join the owned cgroup before exec, so all future descendants inherit it."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--cgroup', required=True)
    a.add_argument('--receipt', required=True)
    a.add_argument('--gate-fd', type=int, required=True)
    a.add_argument('--uid', type=int)
    a.add_argument('--gid', type=int)
    a.add_argument('command', nargs=argparse.REMAINDER)
    args = a.parse_args()
    (Path(args.cgroup)/'cgroup.procs').write_text(str(os.getpid()))
    if str(os.getpid()) not in (Path(args.cgroup)/'cgroup.procs').read_text().split():
        raise RuntimeError('target membership not confirmed')
    Path(args.receipt).write_text(json.dumps({'pid':os.getpid(), 'monotonic_ns':time.monotonic_ns()}))
    if os.read(args.gate_fd, 1) != b'G':
        raise RuntimeError('execution gate closed without release')
    os.close(args.gate_fd)
    if args.gid is not None:
        os.setgroups([])
        os.setgid(args.gid)
    if args.uid is not None:
        os.setuid(args.uid)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    os.execvpe(command[0], command, os.environ)


if __name__ == '__main__':
    main()
