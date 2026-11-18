#!/usr/bin/env python3
"""Original correctness verifier, run outside workload cgroups after sampling."""
import argparse
import json
from pathlib import Path
import sys


def main():
    a=argparse.ArgumentParser();a.add_argument('--repo',required=True);a.add_argument('--input',required=True);a.add_argument('--output',required=True);args=a.parse_args()
    sys.path.insert(0,str(Path(args.repo)/'后台操作'))
    from oomlab.workloads import verify
    try:
        result=verify(args.input,args.output);status=0
    except Exception as error:
        result={'ok':False,'error':repr(error)};status=2
    (Path(args.output)/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return status


if __name__=='__main__':raise SystemExit(main())
