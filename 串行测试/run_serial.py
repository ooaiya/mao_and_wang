#!/usr/bin/env python3
"""Four unchanged workloads, one at a time; shared baseline memory accounting."""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'基线并发'))
sys.path.insert(0,str(ROOT/'冻结并发'))
from common.cgroup_manager import CgroupManager
from common.monitor import MemoryMonitor,meminfo,counters
from common.timeline import Timeline
from restore_swap import active as active_swap,restore as restore_swap

ORDER=['foreground_krita','xz','table','array']
EXPECTED={'xz':'24079d1b208f773d6651199546dc272d658b341a0d341d77a1ed90067dfcaa61',
          'table':'f68ccafda469a5693cbd932750b38c86fcfdcc5e6c94e2618cbd609e7ca53943',
          'array':'d0e1748db5423006be8685e78a0cecfb5d0aa7ee37cffa7a7b6c683f75a7cf05'}
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False))
def members(cg):
    return sorted({int(x) for p in Path(cg).rglob('cgroup.procs') for x in p.read_text().split()})
def wait_empty(cg,timeout=20):
    end=time.monotonic()+timeout
    while members(cg):
        if time.monotonic()>end:raise RuntimeError('descendants remain in '+str(cg))
        time.sleep(.05)
def validate_sequence(records):
    if list(records)!=ORDER:return False
    return all(records[b]['start_ns']>=records[a]['empty_confirmed_ns'] for a,b in zip(ORDER,ORDER[1:]))

class Serial:
    background_input_ops = ORDER[1:]
    def __init__(self,out,home,foreground_run=None,foreground_source=None,no_swap=False,*,foreground_inputs=None):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False);self.home=Path(home)
        self.foreground_run=Path(foreground_run) if foreground_run else None
        self.foreground_source=Path(foreground_source) if foreground_source else None
        self.foreground_inputs=foreground_inputs
        self.no_swap=no_swap
        os.chown(self.out,1000,1000);self.timeline=Timeline(self.out,self.out.name)
        self.groups={};self.processes={};self.logs=[];self.records={};self.monitor=None;self.inhibitor=None;self.oom_before=None
        self.env=dict(os.environ,HOME=str(self.home),USER='ooaiya',LOGNAME='ooaiya',DISPLAY=':0',XDG_RUNTIME_DIR='/run/user/1000',
             DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/1000/bus',WAYLAND_DISPLAY='wayland-0',XDG_SESSION_TYPE='wayland',
             QT_QPA_PLATFORM='xcb',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1',LC_ALL='C.UTF-8')
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
        if self.foreground_inputs:
            settings_path,assets_path=self.foreground_inputs
            self.source=self.foreground_source
            self.config=json.loads(settings_path.read_text(encoding='utf-8'))
        elif self.foreground_run:
            prior=self.foreground_run
            review=json.loads((prior/'summary.json').read_text())
            if not review['valid'] or not review.get('pressure_profile',{}).get('valid'):
                raise RuntimeError('foreground run lacks a passing independent pressure profile')
            self.source=self.foreground_source
            self.config=json.loads((prior/'config.snapshot.json').read_text())
        else:
            raise ValueError('a verified low–high–medium foreground run or config/manifest pair is required')
        if not all(key in self.config['automation'] for key in ('prepared_document', 'tail_document')):
            raise ValueError('a low–high–medium foreground configuration is required')
        self.gui=self.source/'前台操作/前台操作自动化脚本采集'
        if not self.foreground_inputs:assets_path=prior/'assets_manifest.json'
        assets=json.loads(assets_path.read_text(encoding='utf-8'))
        inputs=[assets['ora'],*assets['png_files']]
        if self.foreground_run or self.foreground_inputs:
            settings=self.config['automation']
            contract=assets['script_contract']
            if any(settings.get(key)!=contract.get(key) for key in
                   ('prepared_document','tail_document','pressure_profile','capture_window_s',
                    'tile_memory_percent','tail_charge_range_bytes')):
                raise RuntimeError('verified foreground configuration/asset contract mismatch')
            inputs.extend(assets[key] for key in ('prepared_ora','tail_ora') if key in assets)
        elif assets['png_count']!=45:raise RuntimeError('wrong number of input PNGs')
        for f in inputs:
            if digest(f['path'])!=f['sha256']:raise RuntimeError('foreground input changed: '+f['path'])
        provenance=self.background_provenance()
        self.provenance=provenance;save(self.out/'input_provenance.json',provenance);save(self.out/'foreground_assets.json',assets)
        save(self.out/'foreground_config.json',self.config)
        (self.out/'kritarc.before').write_bytes((self.home/'.config/kritarc').read_bytes())
        if self.foreground_inputs:
            files=[self.gui/'scripts/krita_auto.py',*(self.gui/'oomlab_krita_collect').glob('*.py')]
            original=dict(files={p.relative_to(self.source).as_posix():digest(p) for p in files})
        else:
            original=json.loads((prior/'metadata.json').read_text())['source']
            hashes={rel:digest(self.source/rel) for rel in original['files']}
            if hashes!=original['files']:raise RuntimeError('foreground code differs from verified timed implementation')
        save(self.out/'source_provenance.json',dict(foreground=original,runner_sha256=digest(__file__),
            foreground_source=str(self.source),foreground_independent_run=None if self.foreground_inputs else str(prior),
            bg_workloads_sha256=digest(self.home/'bg/oomlab/workloads.py')))
        if self.no_swap:
            save(self.out/'swap_state.json',dict(entries=active_swap(),proc_swaps=Path('/proc/swaps').read_text()))
            subprocess.run(['swapoff','-a'],check=True)
            if meminfo().get('SwapTotal',0)!=0:raise RuntimeError('Swap is not fully disabled')
        save(self.out/'environment.json',dict(meminfo=meminfo(),swaps=Path('/proc/swaps').read_text(),kernel=os.uname().release,
             order=ORDER,swap_changed=self.no_swap,cache_policy='normal retained cache; no cache dropping or memory reclaim between tasks'))
        parent=CgroupManager.current();CgroupManager.prepare_delegation(parent);self.cm=CgroupManager(parent,'oomlab_'+getattr(self,'run_kind','serial')+'_'+str(os.getpid()))
        self.oom_before=counters('/proc/vmstat')['oom_kill']
        self.inhibitor=subprocess.Popen(['gnome-session-inhibit','--inhibit','idle','--reason','Serial foreground experiment','/bin/sleep','4500'],
             env=self.env,user=1000,group=1000,extra_groups=[],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if start_monitor:
            self.monitor=MemoryMonitor(self.out,self.timeline,self.groups,interval_s=.05);self.monitor.start()
    def background_provenance(self):
        provenance={}
        for op in self.background_input_ops:
            data=self.home/'oom_data'/('array_large' if op=='array' else op+'_large');m=json.loads((data/'manifest.json').read_text())
            actual=digest(data/m['file'])
            if actual!=m['sha256'] or actual!=EXPECTED[op]:raise RuntimeError('background input changed: '+op)
            provenance[op]=dict(path=str(data),manifest=m,input_sha256=actual)
        return provenance

    def launch(self,op,command):
        if any(members(v['cgroup_path']) for v in self.groups.values()):raise RuntimeError('previous task boundary not empty')
        folder=self.out/op;folder.mkdir();os.chown(folder,1000,1000)
        cg=self.cm.create(op);self.groups[op]=dict(cgroup_path=str(cg),pid=None)
        save(folder/'memory_controls.json',{k:(cg/k).read_text().strip() for k in ['memory.max','memory.high','memory.swap.max','memory.oom.group']})
        gate="import os,sys;from pathlib import Path;Path(sys.argv[1]+'/cgroup.procs').write_text(str(os.getpid()));Path('/proc/self/oom_score_adj').write_text('0');os.setgroups([4,24,27,46]);os.setgid(1000);os.setuid(1000);os.execvpe(sys.argv[2],sys.argv[2:],os.environ)"
        log=(folder/'process.log').open('w');self.logs.append(log)
        if self.timeline.t0_ns is None:self.timeline.t0_ns=time.monotonic_ns()
        start=time.monotonic_ns()
        p=subprocess.Popen([sys.executable,'-c',gate,str(cg),*command],cwd=self.home/'bg',env=self.env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.processes[op]=p;self.groups[op]['pid']=p.pid
        self.records[op]=dict(pid=p.pid,start_ns=start,command=command,cgroup=str(cg))
        self.event('task_start',op,actual_ns=start,pid=p.pid,command=command)
        deadline=time.monotonic()+2000
        while p.poll() is None:
            if self.monitor.errors:raise RuntimeError('sampling failed: '+repr(self.monitor.errors))
            if counters('/proc/vmstat')['oom_kill']!=self.oom_before:raise RuntimeError('unexpected OOM during serial run')
            if self.no_swap and meminfo().get('SwapTotal',0)!=0:raise RuntimeError('Swap changed during serial run')
            if time.monotonic()>deadline:raise TimeoutError(op+' deadline exceeded')
            time.sleep(.05)
        self.records[op].update(exit_observed_ns=time.monotonic_ns(),returncode=p.returncode)
        wait_empty(cg);self.records[op]['empty_confirmed_ns']=time.monotonic_ns()
        self.records[op]['duration_s']=(self.records[op]['empty_confirmed_ns']-start)/1e9
        save(self.out/'tasks.partial.json',self.records)
        self.event('task_end',op,returncode=p.returncode,duration_s=self.records[op]['duration_s'])
        if p.returncode!=0:raise RuntimeError(op+' failed with exit '+str(p.returncode))
    def run(self):
        error=None
        try:
            self.prepare()
            self.launch('foreground_krita',[str(self.home/'bg/.venv/bin/python'),'-u',str(self.gui/'scripts/krita_auto.py'),self.config['asset']['path'],
                '--layers-dir',self.config['pilot']['layers_dir'],'--settings',str(self.out/'foreground_config.json'),
                '--assets-manifest',str(self.out/'foreground_assets.json'),'--process-record',str(self.out/'foreground_krita/process.json')])
            for op in ORDER[1:]:self.launch(op,[str(self.home/'bg/.venv/bin/python'),'-m','oomlab.workloads',self.provenance[op]['path'],str(self.out/op),'--operation-id',op])
        except BaseException as e:error=repr(e);self.event('serial_error',error=error)
        finally:
            # Close only this run's process groups, including orphaned GUI helpers.
            for op,p in self.processes.items():
                cg=Path(self.groups[op]['cgroup_path'])
                if members(cg):
                    (cg/'cgroup.kill').write_text('1');wait_empty(cg)
                if p.poll() is None:p.wait(timeout=10)
            stats=self.monitor.stop() if self.monitor else {}
            if self.inhibitor:self.inhibitor.terminate();self.inhibitor.wait(timeout=5)
            for log in self.logs:log.close()
            finish=time.monotonic_ns();workload_finish=max((r.get('empty_confirmed_ns',r['start_ns']) for r in self.records.values()),default=finish)
            result=dict(status='EXECUTED' if error is None else 'FAILED',error=error,order=ORDER,tasks=self.records,
                T0_monotonic_ns=self.timeline.t0_ns,total_workload_wall_s=(workload_finish-self.timeline.t0_ns)/1e9 if self.timeline.t0_ns else None,
                all_groups_empty=all(not members(v['cgroup_path']) for v in self.groups.values()),strict_serial=validate_sequence(self.records),collector=stats,
                global_oom_kill_delta=counters('/proc/vmstat')['oom_kill']-self.oom_before if self.oom_before is not None else None,
                swap_changed=self.no_swap,swaps_after=Path('/proc/swaps').read_text(),note='output verification and final success are computed after sampling, not during the next workload')
            try:
                save(self.out/'summary.json',result);self.timeline.close()
                if hasattr(self,'cm'):self.cm.cleanup(thaw=False)
            finally:
                if self.no_swap:restore_swap(self.out/'swap_state.json')
        return 0 if error is None else 1

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);a.add_argument('--home',default='/home/ooaiya')
    a.add_argument('--foreground-run',required=True);a.add_argument('--foreground-source',required=True);a.add_argument('--no-swap',action='store_true')
    args=a.parse_args()
    def interrupt(signum,frame):raise KeyboardInterrupt('termination signal')
    signal.signal(signal.SIGTERM,interrupt)
    raise SystemExit(Serial(args.output,args.home,args.foreground_run,args.foreground_source,args.no_swap).run())
