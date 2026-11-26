"""50ms observer of one real GUI application unit. No workload or memory limits."""
import argparse,csv,json,os,subprocess,sys,time,datetime
from pathlib import Path

# Reuse the established monitor readers without starting any formal scheduler.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"基线并发"))
from common.monitor import meminfo as shared_meminfo


def kv(text):
    return {k:int(v) for k,v in (l.split()[:2] for l in text.splitlines() if len(l.split())>=2)}


def system_memory():
    return shared_meminfo()


def event(folder,kind,detail):
    with (folder/'phase_trace.jsonl').open('a') as f:
        f.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind=kind,detail=detail))+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--unit');p.add_argument('--event');p.add_argument('--detail',default='');p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    folder=a.directory.resolve();probe=folder
    while not probe.exists():probe=probe.parent
    if subprocess.run(['git','-C',str(probe),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Capture output must be outside Git worktrees')
    folder.mkdir(parents=True,exist_ok=True)
    if a.event:event(folder,a.event,a.detail);return
    if (folder/'task_memory.csv').exists():raise SystemExit('Refuse to overwrite an existing capture')
    if subprocess.run(['git','-C',str(folder),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Capture output must be outside Git worktrees')
    assert a.unit and a.unit.startswith('teamoom-app-') and a.command
    command=a.command[1:] if a.command[0]=='--' else a.command
    env=dict(os.environ)
    for line in subprocess.check_output(['systemctl','--user','show-environment'],text=True).splitlines():
        k,_,v=line.partition('=')
        if k in {'DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS'}:env[k]=v
    event(folder,'app_launch',{'command':command,'unit':a.unit})
    launch=['systemd-run','--user','--collect','--unit='+a.unit,'-p','MemoryAccounting=yes','-p','Delegate=yes','-p','StandardOutput=append:'+str(folder/'application.log'),'-p','StandardError=append:'+str(folder/'application.log')]
    for k in ['DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']:
        if k in env:launch+=['--setenv='+k+'='+env[k]]
    # App-specific user paths are passed explicitly in its command/environment.
    config=folder/'user_config';config.mkdir(exist_ok=True)
    launch+=['--setenv=XDG_CONFIG_HOME='+str(config),'--setenv=XDG_CACHE_HOME='+str(folder/'user_cache'),'--setenv=QT_QPA_PLATFORM=xcb','--setenv=GDK_BACKEND=x11',*command]
    with (folder/'application.log').open('w') as log:
        subprocess.run(launch,stdout=log,stderr=subprocess.STDOUT,check=True,env=env)
    cg_text=subprocess.check_output(['systemctl','--user','show',a.unit,'-p','ControlGroup','--value'],text=True).strip()
    cg=Path('/sys/fs/cgroup')/cg_text.lstrip('/');assert cg_text and a.unit in cg_text
    ancestors={}
    for parent in [cg,*cg.parents]:
        if str(parent).startswith('/sys/fs/cgroup') and (parent/'memory.max').exists():
            ancestors[str(parent)]={n:(parent/n).read_text().strip() for n in ['memory.max','memory.high']}
    (folder/'ancestor_limits.json').write_text(json.dumps(ancestors,indent=2))
    def read(n):return (cg/n).read_text().strip() if (cg/n).exists() else ''
    assert read('memory.max')=='max' and read('memory.high')=='max','Unexpected inherited limit: do not collect as unconstrained'
    initial_oom=kv(Path('/proc/vmstat').read_text()).get('oom_kill',0);initial_events=kv(read('memory.events'));start=time.monotonic_ns();known=set();next_tree=start;abort=None;last_current=0;intervals=[];last_ns=None
    (folder/'environment.json').write_text(json.dumps(dict(unit=a.unit,cgroup=str(cg),command=command,start_monotonic_ns=start,memory=system_memory(),memory_max=read('memory.max'),memory_high=read('memory.high'),memory_swap_max=read('memory.swap.max'),sample_period_ns=50000000),indent=2))
    fields=['monotonic_ns','elapsed_s','memory_current','memory_anon','memory_file','memory_peak','pids_current','cpu_usage_usec','memory_events','memory_pressure','MemAvailable','SwapTotal','SwapFree','global_oom_kill','pswpin_pages','pswpout_pages','cgroup_swap_current','cpu_pressure','io_pressure']
    with (folder/'task_memory.csv').open('w') as f,(folder/'process_tree.csv').open('w') as tree:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();tw=csv.writer(tree);tw.writerow(['monotonic_ns','pid','ppid','comm','cgroup'])
        deadline=time.monotonic_ns()
        while cg.exists():
            now=time.monotonic_ns()
            try:
                current=read('memory.current')
                if not current:break
                last_current=int(current);stat=kv(read('memory.stat'));cpu=kv(read('cpu.stat'));mem=system_memory();events=kv(read('memory.events'));vm=kv(Path('/proc/vmstat').read_text());oom=vm.get('oom_kill',0)
                writer.writerow(dict(monotonic_ns=now,elapsed_s=(now-start)/1e9,memory_current=current,memory_anon=stat.get('anon'),memory_file=stat.get('file'),memory_peak=read('memory.peak'),pids_current=read('pids.current'),cpu_usage_usec=cpu.get('usage_usec'),memory_events=json.dumps(events),memory_pressure=read('memory.pressure').replace('\n',';'),MemAvailable=mem['MemAvailable'],SwapTotal=mem['SwapTotal'],SwapFree=mem['SwapFree'],global_oom_kill=oom,pswpin_pages=vm.get('pswpin'),pswpout_pages=vm.get('pswpout'),cgroup_swap_current=read('memory.swap.current'),cpu_pressure=read('cpu.pressure').replace('\n',';'),io_pressure=read('io.pressure').replace('\n',';')));f.flush()
                if last_ns is not None:intervals.append((now-last_ns)/1e9)
                last_ns=now
                if now>=next_tree:
                    pids=set()
                    for path in [cg,*[p for p in cg.rglob('*') if p.is_dir()]]:
                        if (path/'cgroup.procs').exists():pids.update(int(s) for s in (path/'cgroup.procs').read_text().split())
                    for pid in pids:
                        try:
                            raw=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();actual=Path(f'/proc/{pid}/cgroup').read_text().strip();tw.writerow([now,pid,raw[1],Path(f'/proc/{pid}/comm').read_text().strip(),actual])
                        except OSError:pass
                    # Descendants of observed members must remain in this subtree.
                    for proc in Path('/proc').iterdir():
                        if not proc.name.isdigit() or int(proc.name) in pids:continue
                        try:
                            parent=int((proc/'stat').read_text().rsplit(')',1)[1].split()[1])
                            if parent in (known|pids):
                                actual=(proc/'cgroup').read_text()
                                if cg_text not in actual:abort='observed descendant escaped cgroup'
                        except (OSError,ValueError):pass
                    known|=pids;tree.flush();next_tree=now+1000000000
                if mem['MemAvailable']<2*1024**3:abort='MemAvailable below 2GiB: imminent host pressure'
                if oom>initial_oom or events.get('oom_kill',0)>initial_events.get('oom_kill',0):abort='OOM kill observed'
                if abort:
                    event(folder,'safety_abort',abort);subprocess.run(['systemctl','--user','stop',a.unit]);break
            except FileNotFoundError:break
            deadline+=50000000;remaining=(deadline-time.monotonic_ns())/1e9
            if remaining>0:time.sleep(remaining)
            else:deadline=time.monotonic_ns()
    event(folder,'cgroup_empty',{'path_exists':cg.exists(),'last_memory_current':last_current})
    event(folder,'app_exit',{'evidence':'application cgroup removed or capture ended','cgroup_exists':cg.exists(),'safety_abort':abort})
    result=dict(status='SAFETY_ABORT' if abort else 'CAPTURE_ENDED',abort_reason=abort,samples=len(intervals)+1,max_interval_s=max(intervals,default=0),mean_interval_s=sum(intervals)/max(1,len(intervals)),over_100ms=sum(v>.1 for v in intervals),process_ids=sorted(known),actual_task_completion='requires GUI/output verification; capture end alone is not success')
    (folder/'capture_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
