"""Install post-run review and a quiet waiter without touching running code."""
import base64,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'实验工具/baseline_b_9000'))
from remote import ssh
data=base64.b64encode(Path(__file__).with_name('review_independent.py').read_bytes()).decode()
script='''import base64,json,subprocess
from pathlib import Path
h=Path.home();v=json.loads((h/'TeamOOM/runtime/config/FREEZER_LATEST.json').read_text());source=Path(v['source']);out=Path(v['output'])
'''
script+='data='+repr(data)+'\n'
script+='''review=source/'冻结并发/review_independent.py';temp=review.with_suffix('.tmp');temp.write_bytes(base64.b64decode(data));temp.replace(review)
waiter=h/'TeamOOM/runtime/tools'/('wait-'+out.name+'.py')
lines=["import subprocess,time;from pathlib import Path","out=Path("+repr(str(out))+")","while not (out/'summary.json').exists():time.sleep(5)","time.sleep(2)","raise SystemExit(subprocess.call("+repr([str(h/'TeamOOM/runtime/venv/bin/python'),str(review),str(out)])+"))"]
waiter.write_text(chr(10).join(lines))
log=h/'TeamOOM/reports/reviews'/('post-'+out.name+'.log');log.parent.mkdir(exist_ok=True)
existing=[]
for item in Path('/proc').iterdir():
 if item.name.isdigit():
  try:
   if str(waiter).encode() in (item/'cmdline').read_bytes().split(bytes([0])):existing.append(int(item.name))
  except (FileNotFoundError,PermissionError):pass
if existing or (out/'validation.json').exists():print(json.dumps(dict(existing_waiters=existing,log=str(log))))
else:
 with log.open('w') as f:p=subprocess.Popen(['/usr/bin/python3',str(waiter)],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 print(json.dumps(dict(waiter_pid=p.pid,log=str(log))))
'''
reply=ssh(script,30)
print(reply.stdout,reply.stderr)
raise SystemExit(reply.returncode)
