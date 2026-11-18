"""Deploy a fresh copy of the selected freezer strategy to Ubuntu."""
import argparse,base64,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'实验工具/baseline_b_9000'))
from remote import ssh

def package(policy='priority'):
    files={}
    for folder in ['冻结并发','基线并发/common','串行测试']:
        for p in (ROOT/folder).glob('*.py'):files[str(p.relative_to(ROOT)).replace('\\','/')]=p.read_bytes()
    files['冻结并发/segmented_policy.json']=(ROOT/'冻结并发/segmented_policy.json').read_bytes()
    files['冻结并发/offline_config.json']=(ROOT/'冻结并发/offline_config.json').read_bytes()
    worker='后台操作/栅格频域任务/raster_fft.py'
    files[worker]=(ROOT/worker).read_bytes()
    return files

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--policy',choices=['priority','realtime'],default='priority');options=a.parse_args()
    files=package(options.policy);payload={name:base64.b64encode(data).decode() for name,data in files.items()}
    script='execution_policy='+repr(options.policy)+'\n'+'''import base64,json,time
from pathlib import Path
h=Path.home()
prefix='freezer-realtime-' if execution_policy=='realtime' else 'freezer-'
source=h/'oom_lab/tools'/(prefix+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));source.mkdir(parents=True,exist_ok=False)
'''
    script+='files='+repr(payload)+'\n'
    script+='''for name,data in files.items():
 p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
receipt=dict(source=str(source),execution_policy=execution_policy)
pointer={'priority':'FREEZER_PRIORITY_SOURCE.json','realtime':'FREEZER_REALTIME_SOURCE.json'}[execution_policy]
(h/'oom_lab/config'/pointer).write_text(json.dumps(receipt))
print(json.dumps(receipt))
'''
    reply=ssh(script,120)
    if reply.returncode:raise RuntimeError(reply.stdout+reply.stderr)
    print(reply.stdout)
