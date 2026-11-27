"""Run through the existing SSH transport: a new result and guarded service."""
import argparse,json,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--shaped-run',required=True)
parser.add_argument('--offsets',required=True)
parser.add_argument('--policy-config')
parser.add_argument('--foreground-run',required=True)
parser.add_argument('--foreground-source',required=True)
args=parser.parse_args()
h=Path.home();v=json.loads((h/'oom_lab/config/FREEZER_PRIORITY_SOURCE.json').read_text());source=Path(v['source'])
session=subprocess.check_output(['loginctl','show-seat','seat0','-p','ActiveSession','--value'],text=True).strip()
locked=subprocess.check_output(['loginctl','show-session',session,'-p','LockedHint'],text=True)
if 'LockedHint=no' not in locked:raise RuntimeError('desktop locked; unlock before running')
if subprocess.run(['pgrep','-x','krita'],capture_output=True).returncode==0:raise RuntimeError('existing Krita')
if v['execution_policy']!='priority':
    raise ValueError('unsupported freezer execution policy')
out=h/'oom_lab/results'/('freezer-priority-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
unit='oomlab-freezer-priority-'+str(time.time_ns())
inputs={key:value for key,value in vars(args).items() if value is not None}
for key,value in inputs.items():
    expected = Path(value).is_file() if key in ('offsets','policy_config') else Path(value).is_dir()
    if not expected:
        parser.error(f'invalid {key} path on this VM')
receipt=dict(source=str(source),output=str(out),execution_policy='priority',unit=unit,**inputs)
options=[item for key,value in inputs.items() for item in ('--'+key.replace('_','-'),value)]
recovery='/usr/bin/python3 "'+str(source/'基线并发/common/restore_swap.py')+'" "'+str(out/'swap_state.json')+'"'
q=subprocess.run(['sudo','-n','systemd-run','--unit='+unit,'-p','Delegate=yes','-p','OOMScoreAdjust=-900','-p','OOMPolicy=continue',
    '-p','RuntimeMaxSec=4800','-p','KillMode=control-group','-p','ExecStopPost='+recovery,
    '/usr/bin/python3',str(source/'冻结并发/raster_priority.py'),'--output',str(out),*options],capture_output=True,text=True)
if q.returncode:raise RuntimeError(q.stdout+q.stderr)
(h/'oom_lab/config/FREEZER_LATEST.json').write_text(json.dumps(receipt))
print(json.dumps(receipt))
