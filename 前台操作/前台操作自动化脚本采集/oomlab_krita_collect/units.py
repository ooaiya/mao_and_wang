"""Owned user units. Never infer cgroup paths, set memory limits, or use sudo."""
import os
import re
import sys
from pathlib import Path,PurePosixPath
from .common import command,save,GUI,ROOT

UNIT = re.compile(r'oomcollect-[0-9a-f]{32}-(krita|xz|table|images|smoke|hold)\.service\Z')


def members(path):
    result=set()
    for p in Path(path).rglob('cgroup.procs'): result.update(int(x) for x in p.read_text().split())
    return result


def process_cgroup(pid,proc='/proc'):
    lines=(Path(proc)/str(pid)/'cgroup').read_text().splitlines()
    paths=[line[3:] for line in lines if line.startswith('0::/')]
    if len(paths)!=1 or '..' in PurePosixPath(paths[0]).parts: raise ValueError('invalid process cgroup')
    return paths[0]


class Unit:
    def __init__(self,unit,run,slice_name):
        if not UNIT.fullmatch(unit): raise ValueError('not an owned unit name')
        if slice_name!='oomcollect-'+unit.split('-')[1]+'.slice': raise ValueError('slice UUID mismatch')
        self.unit,self.run,self.slice=unit,Path(run).resolve(),slice_name
        self.description='oomcollect-v1:'+str(self.run)
        self.path=None;self.cg=None;self.pid=None;self.birth=None;self.observed={};self.stop_timeout_s=10

    def show(self):
        text=command(['systemctl','--user','show',self.unit,'--no-pager','--property=Id,Description,Slice,ControlGroup,MainPID,ActiveState,LoadState'],check=False).stdout
        return dict(line.split('=',1) for line in text.splitlines() if '=' in line)

    def owned(self,properties):
        if any(properties.get(k)!=v for k,v in [('Id',self.unit),('Description',self.description),('Slice',self.slice)]): raise RuntimeError('unit ownership not proven; refusing mutation')
        cg=properties.get('ControlGroup','')
        if not cg.startswith('/') or '..' in PurePosixPath(cg).parts or Path(cg).name!=self.unit or Path(cg).parent.name!=self.slice:
            raise RuntimeError('invalid manager ControlGroup')
        if self.cg and cg!=self.cg: raise RuntimeError('ControlGroup changed')
        path=(Path('/sys/fs/cgroup')/cg.lstrip('/')).resolve()
        if not path.is_relative_to(Path('/sys/fs/cgroup')): raise RuntimeError('cgroup escaped mount')
        return path

    def start(self,hold=False,timeout_s=600,stop_timeout_s=10):
        self.stop_timeout_s=stop_timeout_s
        args=['systemd-run','--user','--quiet','--unit='+self.unit,'--slice='+self.slice,
              '--description='+self.description,'--service-type=exec','--property=MemoryAccounting=yes',
              '--property=KillMode=control-group','--property=OOMPolicy=continue','--property=TimeoutStopSec='+str(stop_timeout_s),
              '--property=RuntimeMaxSec='+str(timeout_s),'--working-directory='+str(GUI)]
        for key in ('DISPLAY','XAUTHORITY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','XDG_SESSION_TYPE','XDG_SESSION_ID','DBUS_SESSION_BUS_ADDRESS','HOME','PATH'):
            if key in os.environ: args.append('--setenv='+key+'='+os.environ[key])
        args+=['--setenv=QT_QPA_PLATFORM=xcb','--setenv=PYTHONUNBUFFERED=1',
               '--setenv=PYTHONPATH='+str(GUI),sys.executable,'-u','-m','oomlab_krita_collect.worker',str(self.run)]
        if hold: args.append('--hold')
        record=command(args,check=False)
        save(self.run/'systemd-start.json',dict(command=args,returncode=record.returncode,stdout=record.stdout,stderr=record.stderr))
        if record.returncode: raise RuntimeError('systemd user service failed: '+record.stderr)

    def bind(self):
        p=self.show();self.path=self.owned(p);self.cg=p['ControlGroup'];self.pid=int(p['MainPID'])
        if self.pid<=0 or process_cgroup(self.pid)!=self.cg: raise RuntimeError('MainPID membership mismatch')
        raw=(Path('/proc')/str(self.pid)/'stat').read_text();self.birth=int(raw[raw.rindex(')')+2:].split()[19])
        save(self.run/'unit-identity.json',dict(unit=self.unit,properties=p,pid=self.pid,starttime=self.birth,cgroup=str(self.path)))
        return self.path

    def check_members(self):
        self.check_descendants()
        rows=[]
        for pid in members(self.path):
            try:
                group=process_cgroup(pid)
                if group!=self.cg and not group.startswith(self.cg+'/'): raise RuntimeError('workload escaped cgroup')
                raw=(Path('/proc')/str(pid)/'stat').read_text(); fields=raw[raw.rindex(')')+2:].split()
                rows.append(dict(pid=pid,ppid=int(fields[1]),starttime=int(fields[19]),exe=os.readlink(Path('/proc')/str(pid)/'exe'),cgroup=group))
            except (FileNotFoundError,ProcessLookupError):continue  # short-lived helper ended during the scan
        return rows

    def check_descendants(self):
        # Inventory outside cgroup.procs too: a child that migrated out must not
        # disappear from the evidence merely because we only scanned the unit.
        processes={}
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                raw=(p/'stat').read_text();f=raw[raw.rindex(')')+2:].split()
                processes[int(p.name)]=(int(f[1]),int(f[19]))
            except (FileNotFoundError,ProcessLookupError):continue
        owned={self.pid};changed=True
        owned.update(pid for pid,birth in self.observed.items() if processes.get(pid,(None,None))[1]==birth)
        while changed:
            children={pid for pid,(ppid,birth) in processes.items() if ppid in owned}
            changed=not children<=owned;owned|=children
        for pid in owned:
            if pid not in processes:continue
            try:
                group=process_cgroup(pid)
                raw=(Path('/proc')/str(pid)/'stat').read_text();birth=int(raw[raw.rindex(')')+2:].split()[19])
                if birth!=processes[pid][1]:raise RuntimeError('descendant PID reused during audit')
                if group!=self.cg and not group.startswith(self.cg+'/'):raise RuntimeError('descendant escaped cgroup: '+str(pid))
                self.observed[pid]=birth
            except (FileNotFoundError,ProcessLookupError):continue

    def stop(self):
        p=self.show()
        if p.get('Id')==self.unit and p.get('LoadState')=='not-found' and p.get('MainPID')=='0' and p.get('ControlGroup')=='':
            return dict(ok=True,already_absent=True,properties=p)
        path=self.owned(p)
        if self.pid and p.get('MainPID') not in ('0',str(self.pid)): raise RuntimeError('supervisor PID changed; cleanup refused')
        if self.pid and p.get('MainPID')==str(self.pid):
            raw=(Path('/proc')/str(self.pid)/'stat').read_text()
            if int(raw[raw.rindex(')')+2:].split()[19])!=self.birth: raise RuntimeError('supervisor starttime changed')
        command(['systemctl','--user','stop',self.unit],timeout=self.stop_timeout_s+5)
        after=self.show()
        ok=after.get('Id')==self.unit and after.get('MainPID')=='0' and after.get('ActiveState') in ('inactive','failed')
        if path.exists() and members(path): ok=False
        if not ok: raise RuntimeError('unit stop not proven complete')
        return dict(ok=True,before=p,after=after)
