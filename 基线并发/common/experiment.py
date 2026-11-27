"""Shared setup, provenance checks and task commands for the four-task experiment."""

import json
import os
import subprocess
import time
from pathlib import Path

from .cgroup_manager import CgroupManager
from .monitor import MemoryMonitor, meminfo, counters
from .restore_swap import active as active_swap
from .shaped_scene import FOREGROUND, TASKS, WORKER, command, provenance, save, sha as digest
from .timeline import Timeline


def members(cg):
    return sorted({int(x) for p in Path(cg).rglob('cgroup.procs') for x in p.read_text().split()})
def wait_empty(cg,timeout=20):
    end=time.monotonic()+timeout
    while members(cg):
        if time.monotonic()>end:raise RuntimeError('descendants remain in '+str(cg))
        time.sleep(.05)

class Experiment:
    background_ops = TASKS

    def __init__(self,out,home,foreground_run,foreground_source,shaped_run,no_swap=False):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False);self.home=Path(home)
        self.foreground_run=Path(foreground_run)
        self.foreground_source=Path(foreground_source)
        self.shaped_reference=Path(shaped_run)
        self.order=[FOREGROUND,*TASKS]
        self.no_swap=no_swap
        os.chown(self.out,1000,1000);self.timeline=Timeline(self.out,self.out.name)
        self.groups={};self.processes={};self.logs=[];self.records={};self.monitor=None;self.inhibitor=None;self.oom_before=None
        self.env=dict(os.environ,HOME=str(self.home),USER='ooaiya',LOGNAME='ooaiya',DISPLAY=':0',XDG_RUNTIME_DIR='/run/user/1000',
             DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus',WAYLAND_DISPLAY='wayland-0',XDG_SESSION_TYPE='wayland',
             QT_QPA_PLATFORM='xcb',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1',LC_ALL='C.UTF-8')
        self.env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    def event(self,kind,op='',**kw):
        self.timeline.emit(kind,op,**kw);print(json.dumps(dict(event=kind,op=op,**kw)),flush=True)
    def prepare(self,start_monitor=True):
        if os.geteuid()!=0:raise RuntimeError('start in the delegated root service')
        if subprocess.run(['pgrep','-x','krita'],capture_output=True).returncode==0:raise RuntimeError('existing Krita; refusing attachment')
        sessions=subprocess.check_output(['loginctl','list-sessions','--no-legend'],text=True)
        for line in sessions.splitlines():
            session=line.split()[0]
            fields=dict(row.split('=',1) for row in subprocess.check_output(
                ['loginctl','show-session',session,'-p','Name','-p','Seat','-p','LockedHint','-p','Type'],text=True).splitlines())
            if fields=={'Name':'ooaiya','Seat':'seat0','LockedHint':'no','Type':'wayland'}:
                self.env['XDG_SESSION_ID']=session;break
        else:raise RuntimeError('unlocked ooaiya Wayland desktop session required')
        prior=self.foreground_run
        if not prior:
            raise ValueError('a verified low–high–medium foreground run is required')
        review=json.loads((prior/'summary.json').read_text())
        if not review['valid'] or not review.get('pressure_profile',{}).get('valid'):
            raise RuntimeError('foreground run lacks a passing independent pressure profile')
        self.source=self.foreground_source
        self.config=json.loads((prior/'config.snapshot.json').read_text())
        if not all(key in self.config['automation'] for key in ('prepared_document', 'tail_document')):
            raise ValueError('a low–high–medium foreground configuration is required')
        self.gui=self.source/'前台操作/前台操作自动化脚本采集'
        assets=json.loads((prior/'assets_manifest.json').read_text(encoding='utf-8'))
        inputs=[assets['ora'],*assets['png_files']]
        settings=self.config['automation']
        contract=assets['script_contract']
        if any(settings.get(key)!=contract.get(key) for key in
               ('prepared_document','tail_document','pressure_profile','capture_window_s',
                'tile_memory_percent','tail_charge_range_bytes')):
            raise RuntimeError('verified foreground configuration/asset contract mismatch')
        inputs.extend(assets[key] for key in ('prepared_ora','tail_ora') if key in assets)
        for f in inputs:
            if digest(f['path'])!=f['sha256']:raise RuntimeError('foreground input changed: '+f['path'])
        provenance=self.background_provenance()
        self.provenance=provenance;save(self.out/'input_provenance.json',provenance);save(self.out/'foreground_assets.json',assets)
        save(self.out/'foreground_config.json',self.config)
        (self.out/'kritarc.before').write_bytes((self.home/'.config/kritarc').read_bytes())
        original=json.loads((prior/'metadata.json').read_text())['source']
        # Old captures included hashes for the retired backend. Validate the frontend
        # files from those captures and use the shaped capture for backend validation.
        frontend_files = {rel: expected for rel, expected in original['files'].items()
                          if rel.startswith('前台操作/')}
        if not frontend_files or any(digest(self.source/rel) != expected
                                     for rel, expected in frontend_files.items()):
            raise RuntimeError('foreground code differs from verified timed implementation')
        save(self.out/'source_provenance.json',dict(foreground=original,runner_sha256=digest(__file__),
            foreground_source=str(self.source),foreground_independent_run=str(prior),
            bg_workloads_sha256=digest(WORKER)))
        if self.no_swap:
            save(self.out/'swap_state.json',dict(entries=active_swap(),proc_swaps=Path('/proc/swaps').read_text()))
            subprocess.run(['swapoff','-a'],check=True)
            if meminfo().get('SwapTotal',0)!=0:raise RuntimeError('Swap is not fully disabled')
        save(self.out/'environment.json',dict(meminfo=meminfo(),swaps=Path('/proc/swaps').read_text(),kernel=os.uname().release,
             order=self.order,swap_changed=self.no_swap,cache_policy='normal retained cache; no cache dropping or memory reclaim between tasks'))
        parent=CgroupManager.current();CgroupManager.prepare_delegation(parent);self.cm=CgroupManager(parent,'oomlab_'+getattr(self,'run_kind','serial')+'_'+str(os.getpid()))
        self.oom_before=counters('/proc/vmstat')['oom_kill']
        self.inhibitor=subprocess.Popen(['gnome-session-inhibit','--inhibit','idle','--reason','Serial foreground experiment','/bin/sleep','4500'],
             env=self.env,user=1000,group=1000,extra_groups=[],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if start_monitor:
            self.monitor=MemoryMonitor(self.out,self.timeline,self.groups,interval_s=.05);self.monitor.start()

    def background_provenance(self):
        return provenance(self.shaped_reference)

    def command(self, op):
        python = str(self.home / 'bg/.venv/bin/python')
        if op == FOREGROUND:
            return [python, '-u', str(self.gui/'scripts/krita_auto.py'), self.config['asset']['path'],
                    '--layers-dir', self.config['pilot']['layers_dir'],
                    '--settings', str(self.out/'foreground_config.json'),
                    '--assets-manifest', str(self.out/'foreground_assets.json'),
                    '--process-record', str(self.out/op/'process.json')]
        return command(op, python, self.out/op/'output.json', self.provenance[op])
