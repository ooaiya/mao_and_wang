"""Deploy and launch a no-Swap serial run using a verified foreground capture."""

import argparse
import base64
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '实验工具/baseline_b_9000'))
from remote import ssh


DEPLOY = r'''
import base64
import json
import subprocess
import time
from pathlib import Path

h = Path.home()
foreground_source = Path(FOREGROUND['source'])
foreground_run = Path(FOREGROUND['run'])
if not (foreground_run / 'manifest.sha256').is_file():
    raise RuntimeError('foreground evidence is not sealed')
if subprocess.run(['pgrep','-x','krita'],capture_output=True).returncode == 0:
    raise RuntimeError('existing Krita session')
for flags in ([], ['--user']):
    units = subprocess.check_output(
        ['systemctl',*flags,'list-units','--type=service','--state=running','--no-legend'],
        text=True,
    )
    if any('oomlab' in line or 'oomcollect' in line or 'memshift' in line for line in units.splitlines()):
        raise RuntimeError('another experiment service is active')

tag = time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
source = h / 'TeamOOM/runtime/tools' / ('serial-extended-'+tag)
source.mkdir(parents=True,exist_ok=False)
for name, payload in FILES.items():
    path = source / name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(base64.b64decode(payload))
subprocess.run(['/usr/bin/python3','-B','-m','unittest','discover','-s','串行测试',
                '-p','test_serial.py'],cwd=source,check=True)
out = h / 'TeamOOM/results' / ('serial-extended-'+tag)
unit = 'oomlab-serial-extended-'+tag
recovery = f'/usr/bin/python3 "{source/"冻结并发/restore_swap.py"}" "{out/"swap_state.json"}"'
args = [
    'sudo','-n','systemd-run','--unit='+unit,
    '-p','Delegate=yes','-p','OOMScoreAdjust=-900','-p','OOMPolicy=continue',
    '-p','RuntimeMaxSec=4800','-p','KillMode=control-group','-p','ExecStopPost='+recovery,
    '/usr/bin/python3',str(source/'串行测试/run_serial.py'),'--output',str(out),
    '--foreground-run',str(foreground_run),'--foreground-source',str(foreground_source),'--no-swap',
]
subprocess.run(args,check=True)
receipt = dict(source=str(source),output=str(out),unit=unit,
               foreground_source=str(foreground_source),foreground_run=str(foreground_run),
               no_swap=True,launched_wall_ns=time.time_ns())
(h/'TeamOOM/runtime/config'/('SERIAL_EXTENDED_'+tag+'.json')).write_text(json.dumps(receipt,indent=2))
print('RECEIPT '+json.dumps(receipt,ensure_ascii=True))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--foreground-receipt', type=Path, required=True)
    parser.add_argument('--foreground-archive', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError(args.receipt)
    launch = json.loads(args.foreground_receipt.read_text(encoding='utf-8'))
    archive = json.loads(args.foreground_archive.read_text(encoding='utf-8'))
    foreground = dict(source=launch['source'],run=archive['run'])
    files = {
        path.relative_to(ROOT).as_posix(): base64.b64encode(path.read_bytes()).decode()
        for path in [
            *(ROOT/'串行测试').glob('*.py'), *(ROOT/'基线并发/common').glob('*.py'),
            ROOT/'冻结并发/restore_swap.py',
        ]
    }
    reply = ssh('FOREGROUND='+repr(foreground)+'\nFILES='+repr(files)+'\n'+DEPLOY,60)
    if reply.returncode:
        raise RuntimeError(reply.stderr+reply.stdout)
    line = next(line for line in reply.stdout.splitlines() if line.startswith('RECEIPT '))
    receipt = json.loads(line[len('RECEIPT '):])
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    with args.receipt.open('x',encoding='utf-8') as file:
        json.dump(receipt,file,ensure_ascii=False,indent=2)
        file.write('\n')
    print(json.dumps(receipt,ensure_ascii=True))


if __name__ == '__main__':
    main()
