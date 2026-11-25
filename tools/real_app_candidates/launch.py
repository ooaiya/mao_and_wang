"""Start one detached GUI observer and application, refusing concurrent app units."""
import argparse,json,subprocess,sys,uuid
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--application',choices=['blender','hugin','darktable','kdenlive','handbrake','peazip'],required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    folder=a.directory.resolve()
    if folder.exists():raise SystemExit('Refuse an existing round directory: '+str(folder))
    parent=folder.parent
    while not parent.exists():parent=parent.parent
    if subprocess.run(['git','-C',str(parent),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Round must be outside Git')
    command=a.command[1:] if a.command and a.command[0]=='--' else a.command
    if not command:raise SystemExit('A real GUI application command is required')
    active=subprocess.check_output(['systemctl','--user','list-units','--state=active,activating,deactivating','--plain','--no-legend','teamoom-app-*'],text=True).strip()
    if active:raise SystemExit('Another app unit still exists; finish/close it before the next round: '+active)
    suffix=uuid.uuid4().hex[:10];unit='teamoom-app-'+a.application+'-'+suffix;observer='teamoom-observer-'+a.application+'-'+suffix
    subprocess.run(['systemd-run','--user','--collect','--unit='+observer,sys.executable,str(Path(__file__).with_name('capture.py')),'--directory',str(folder),'--unit',unit,'--',*command],check=True)
    print(json.dumps({'directory':str(folder),'application_unit':unit,'observer_unit':observer}))
if __name__=='__main__':main()
