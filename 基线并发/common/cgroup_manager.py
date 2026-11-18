"""Owned cgroup-v2 subtrees; no SIGSTOP/SIGCONT substitute."""
import os
import time
from pathlib import Path


def fields(path):
    return {k:int(v) for k,v in (line.split(maxsplit=1) for line in Path(path).read_text().splitlines())}


class CgroupManager:
    def __init__(self, parent, name, mount='/sys/fs/cgroup'):
        self.mount=Path(mount).resolve();self.parent=Path(parent).resolve()
        if self.parent==self.mount or not self.parent.is_relative_to(self.mount):
            raise ValueError('use a delegated systemd scope, never the mount root')
        if not name.startswith('oomlab_') or not name.replace('_','').isalnum():
            raise ValueError('invalid owned cgroup name')
        self.root=self.parent/name;self.groups={};self.root.mkdir(exist_ok=False)
        self.generation=self.root.stat().st_ino

    @staticmethod
    def current(mount='/sys/fs/cgroup'):
        for line in Path('/proc/self/cgroup').read_text().splitlines():
            if line.startswith('0::'):return Path(mount)/line[3:].lstrip('/')
        raise RuntimeError('unified cgroup record missing')

    @staticmethod
    def prepare_delegation(parent):
        parent=Path(parent).resolve()
        if parent==Path('/sys/fs/cgroup'):
            raise RuntimeError('start through systemd-run --scope -p Delegate=yes')
        available=set((parent/'cgroup.controllers').read_text().split())
        if 'memory' not in available:raise RuntimeError('memory controller not delegated by systemd')
        enabled=set((parent/'cgroup.subtree_control').read_text().split());required={'memory','cpu','io'}&available
        if not required<=enabled:
            members=[int(x) for x in (parent/'cgroup.procs').read_text().split()]
            if members!=[os.getpid()]:raise RuntimeError('scope must contain only this runner before controller setup')
            manager=parent/('oomlab_manager_'+str(os.getpid()));manager.mkdir(exist_ok=False)
            (manager/'cgroup.procs').write_text(str(os.getpid()))
            (parent/'cgroup.subtree_control').write_text(' '.join('+'+x for x in sorted(required-enabled)))
        return parent

    def create(self, operation):
        if operation not in {'foreground_krita','xz','table','array','raster_fft','probe'}:raise ValueError('unknown operation')
        enabled=set((self.root/'cgroup.subtree_control').read_text().split());available=set((self.root/'cgroup.controllers').read_text().split())
        if 'memory' not in available:raise RuntimeError('task memory accounting unavailable')
        missing=({'memory','cpu','io'}&available)-enabled
        if missing:(self.root/'cgroup.subtree_control').write_text(' '.join('+'+x for x in sorted(missing)))
        group=self.root/operation;group.mkdir(exist_ok=False)
        for name in ('memory.current','memory.events','cgroup.freeze','cgroup.events'):
            if not (group/name).exists():raise RuntimeError('missing cgroup-v2 ABI: '+str(group/name))
        self.groups[operation]=(group,group.stat().st_ino);return group

    def checked(self, operation):
        group,inode=self.groups[operation]
        if group.stat().st_ino!=inode or self.root.stat().st_ino!=self.generation:raise RuntimeError('cgroup generation changed')
        return group

    def attach(self, operation, pid):
        if pid<=1 or pid==os.getpid():raise ValueError('runner/monitor cannot enter target cgroup')
        group=self.checked(operation);(group/'cgroup.procs').write_text(str(pid))
        if str(pid) not in (group/'cgroup.procs').read_text().split():raise RuntimeError('attachment not confirmed')

    def set_frozen(self, operation, frozen, timeout=2):
        if operation=='foreground_krita':raise ValueError('Krita must never be frozen')
        group=self.checked(operation);requested=time.monotonic_ns();(group/'cgroup.freeze').write_text('1' if frozen else '0')
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            state=fields(group/'cgroup.events')
            if state.get('frozen')==int(frozen):return dict(requested_monotonic_ns=requested,confirmed_monotonic_ns=time.monotonic_ns(),frozen=bool(frozen),cgroup=str(group),events=state)
            time.sleep(.005)
        raise TimeoutError('freezer transition not confirmed')

    def cleanup(self,thaw=True):
        errors=[]
        for operation in self.groups:
            if thaw and operation!='foreground_krita':
                try:self.set_frozen(operation,False)
                except (OSError,TimeoutError) as e:errors.append(str(e))
        for group,_ in reversed(list(self.groups.values())):
            try:group.rmdir()
            except OSError:pass
        try:self.root.rmdir()
        except OSError:pass
        return errors
