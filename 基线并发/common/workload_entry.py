#!/usr/bin/env python3
"""Warm Python imports before the absolute operation-start deadline."""
import argparse
import os
from pathlib import Path
import sys
import time


def main():
    a=argparse.ArgumentParser();a.add_argument('--repo',required=True);a.add_argument('--input',required=True);a.add_argument('--output',required=True);a.add_argument('--operation',required=True);a.add_argument('--deadline-ns',required=True,type=int)
    args=a.parse_args();sys.path.insert(0,str(Path(args.repo)/'后台操作'))
    from oomlab.workloads import execute
    while True:
        remaining=(args.deadline_ns-time.monotonic_ns())/1e9
        if remaining<=0:break
        time.sleep(min(remaining,.01))
    execute(args.input,args.output,operation_id=args.operation)


if __name__=='__main__':main()
