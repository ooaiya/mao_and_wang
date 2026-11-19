"""Run through the existing SSH transport: a new result and guarded service."""
import argparse,json,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--serial-run')
parser.add_argument('--foreground-run')
parser.add_argument('--foreground-source')
parser.add_argument('--realtime',action='store_true')
parser.add_argument('--foreground-config')
parser.add_argument('--foreground-assets')
parser.add_argument('--policy-config')
parser.add_argument('--raster-reference')
args=parser.parse_args()
serial_args=(args.serial_run,args.foreground_run,args.foreground_source)
if args.realtime:
    if args.serial_run or args.foreground_run or not all((args.foreground_source,args.foreground_config,args.foreground_assets)):
        parser.error('real-time mode requires --foreground-source, --foreground-config and --foreground-assets')
    pointer='FREEZER_REALTIME_SOURCE.json'
elif args.foreground_config or args.foreground_assets or args.policy_config or args.raster_reference:
    parser.error('these configuration arguments require --realtime')
elif not all(serial_args):
    parser.error('priority requires --serial-run, --foreground-run and --foreground-source')
else:
    pointer='FREEZER_PRIORITY_SOURCE.json'
h=Path.home();v=json.loads((h/'TeamOOM/runtime/config'/pointer).read_text());source=Path(v['source'])
session=subprocess.check_output(['loginctl','show-seat','seat0','-p','ActiveSession','--value'],text=True).strip()
locked=subprocess.check_output(['loginctl','show-session',session,'-p','LockedHint'],text=True)
if 'LockedHint=no' not in locked:raise RuntimeError('desktop locked; unlock before running')
if subprocess.run(['pgrep','-x','krita'],capture_output=True).returncode==0:raise RuntimeError('existing Krita')
policy=v['execution_policy']
if policy not in {'priority','realtime'} or args.realtime!=(policy=='realtime'):
    raise ValueError('unsupported freezer execution policy')
entry={'priority':'segmented_runner.py','realtime':'realtime_runner.py'}[policy]
tag=policy
if args.raster_reference:tag+='-raster'
out=h/'TeamOOM/results'/('freezer-'+tag+'-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()))
unit='oomlab-freezer-'+tag+'-'+str(time.time_ns())
receipt=dict(source=str(source),output=str(out),execution_policy=policy,unit=unit)
if policy=='realtime':
    if not Path(args.foreground_source).is_dir():parser.error('foreground source directory is missing on this VM')
    inputs=dict(foreground_source=args.foreground_source,foreground_config=args.foreground_config,
                foreground_assets=args.foreground_assets)
    if args.policy_config:inputs['policy_config']=args.policy_config
    for key,value in inputs.items():
        if key!='foreground_source' and not Path(value).is_file():parser.error(f'{key} is missing on this VM')
    if args.raster_reference:
        if not Path(args.raster_reference).is_dir():parser.error('raster reference directory is missing on this VM')
        inputs['raster_reference']=args.raster_reference
    receipt.update(inputs)
    options=[item for key,value in inputs.items() for item in ('--'+key.replace('_','-'),value)]
elif policy=='priority':
    inputs=dict(serial_run=args.serial_run,foreground_run=args.foreground_run,foreground_source=args.foreground_source)
    for key,value in inputs.items():
        if not Path(value).is_dir():
            parser.error(f'{key} is not a directory on this VM')
    receipt.update(inputs)
    options=[item for key,value in inputs.items() for item in ('--'+key.replace('_','-'),value)]
recovery='/usr/bin/python3 "'+str(source/'冻结并发/restore_swap.py')+'" "'+str(out/'swap_state.json')+'"'
q=subprocess.run(['sudo','-n','systemd-run','--unit='+unit,'-p','Delegate=yes','-p','OOMScoreAdjust=-900','-p','OOMPolicy=continue',
    '-p','RuntimeMaxSec=4800','-p','KillMode=control-group','-p','ExecStopPost='+recovery,
    '/usr/bin/python3',str(source/'冻结并发'/entry),'--output',str(out),*options],capture_output=True,text=True)
if q.returncode:raise RuntimeError(q.stdout+q.stderr)
latest='FREEZER_REALTIME_LATEST.json' if args.realtime else 'FREEZER_LATEST.json'
(h/'TeamOOM/runtime/config'/latest).write_text(json.dumps(receipt))
print(json.dumps(receipt))
