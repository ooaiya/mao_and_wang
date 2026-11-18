"""Kernel evidence is independent of cgroup counters and SIGKILL candidates."""
import json
import re
import subprocess
from pathlib import Path
from .common import save_json


def journal(args):
    try:
        p=subprocess.run(['journalctl','-k','-b','--no-pager',*args],capture_output=True,text=True,timeout=15)
        return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {'returncode':None,'error':repr(e)}


def begin(directory):
    result=journal(['-n','1','-o','json','--show-cursor'])
    cursor=None
    for line in result.get('stdout','').splitlines():
        if line.startswith('-- cursor: '):
            cursor=line[len('-- cursor: '):]
    save_json(Path(directory)/'kernel_start.json',dict(result,cursor=cursor))
    return cursor


def finish(directory,cursor):
    directory=Path(directory)
    if cursor is None:
        evidence=dict(status='unavailable',confirmed_count=None,candidates=[],confirmed=[])
    else:
        result=journal(['--after-cursor='+cursor,'-o','json'])
        (directory/'kernel_oom_raw.jsonl').write_text(result.get('stdout',''))
        confirmed,candidates=[],[]
        parse_errors=[]
        for line in result.get('stdout','').splitlines():
            try:
                row=json.loads(line)
                message=row.get('MESSAGE','')
                match=re.search(r'(?:Out of memory: |Memory cgroup out of memory: )?Killed process (\d+) \(([^)]+)\)',message)
                if match:
                    confirmed.append(dict(pid=int(match[1]),comm=match[2],
                                          monotonic_us=row.get('__MONOTONIC_TIMESTAMP'),message=message,
                                          source='kernel_killed_process',process_instance=None))
                elif re.search(r'out of memory|oom-kill|invoked oom-killer',message,re.I):
                    candidates.append(row)
            except (ValueError,TypeError) as e:
                parse_errors.append(str(e))
        available=result['returncode']==0 and not parse_errors
        evidence=dict(status='observed' if available else 'incomplete',
                      confirmed_count=len(confirmed) if available else None,
                      confirmed_observed_lower_bound=len(confirmed),confirmed=confirmed,candidates=candidates,
                      parse_errors=parse_errors,diagnostic={k:v for k,v in result.items() if k!='stdout'})
    save_json(directory/'kernel_oom.json',evidence)
    return evidence
