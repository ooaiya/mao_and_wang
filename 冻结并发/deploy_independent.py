"""Deploy a fresh copy of the curve-based priority freezer to Ubuntu."""
import argparse,base64,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'实验工具/baseline_b_9000'))
from remote import ssh

def package():
    files={}
    for folder in ['冻结并发','基线并发/common','串行测试']:
        for p in (ROOT/folder).glob('*.py'):files[str(p.relative_to(ROOT)).replace('\\','/')]=p.read_bytes()
    for name in ('segmented_policy.json','offline_config.json','raster_priority_config.json',
                 'priority_freeze_only_config.json'):
        files['冻结并发/'+name]=(ROOT/'冻结并发'/name).read_bytes()
    for worker in ('后台操作/栅格频域任务/raster_fft.py',
                   '后台操作/栅格频域任务/measure_raster.py',
                   '后台操作/曲线任务/shaped_workload.py'):
        files[worker]=(ROOT/worker).read_bytes()
    return files

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',choices=['priority'],default='priority')
    parser.parse_args()
    files=package();payload={name:base64.b64encode(data).decode() for name,data in files.items()}
    script='''import base64,json,time
from pathlib import Path
h=Path.home()
source=h/'oom_lab/tools'/('freezer-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));source.mkdir(parents=True,exist_ok=False)
'''
    script+='files='+repr(payload)+'\n'
    script+='''for name,data in files.items():
 p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(data))
receipt=dict(source=str(source),execution_policy='priority')
(h/'oom_lab/config/FREEZER_PRIORITY_SOURCE.json').write_text(json.dumps(receipt))
print(json.dumps(receipt))
'''
    reply=ssh(script,120)
    if reply.returncode:raise RuntimeError(reply.stdout+reply.stderr)
    print(reply.stdout)
