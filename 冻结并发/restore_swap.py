"""Restore only swap entries active before this experiment; safe to call twice."""
import json,subprocess,sys,time
from pathlib import Path
def active():
    return [dict(path=x.split()[0],priority=int(x.split()[-1])) for x in Path('/proc/swaps').read_text().splitlines()[1:]]
def restore(state):
    state=Path(state)
    if not state.exists():return
    before=json.loads(state.read_text())['entries'];present={r['path'] for r in active()};actions=[]
    for row in before:
        if row['path'] in present:continue
        cmd=['swapon']+(['-p',str(row['priority'])] if row['priority']>=0 else [])+[row['path']]
        p=subprocess.run(cmd,capture_output=True,text=True);actions.append(dict(path=row['path'],returncode=p.returncode,stderr=p.stderr))
    after=active();result=dict(actions=actions,entries_after=after,restored={r['path'] for r in before}<={r['path'] for r in after},monotonic_ns=time.monotonic_ns())
    (state.parent/'swap_restoration.json').write_text(json.dumps(result,indent=2))
    if not result['restored']:raise RuntimeError('swap restoration failed')
if __name__=='__main__':restore(sys.argv[1])
