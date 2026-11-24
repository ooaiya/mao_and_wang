"""Single-operation observer inside a unique systemd cgroup; never sets limits."""
import argparse,csv,datetime,json,os,subprocess,sys,time
from pathlib import Path


def metrics():
    m={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
    return m


def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=list('ABCD'));p.add_argument('--notebook',type=Path);a=p.parse_args()
    base=Path('/home/mxt/TeamOOM');case='real_cases/nyc_transport_workstation'
    out=base/'data_collection'/case/'single_task_profiles'/a.operation;out.mkdir(parents=True,exist_ok=True)
    cg=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().strip().split('::')[1].lstrip('/')
    if 'teamoom-nyc-'+a.operation.lower() not in str(cg) or not (cg/'memory.current').exists():raise RuntimeError('unique cgroup attribution unavailable')
    def read(name):return (cg/name).read_text().strip() if (cg/name).exists() else None
    global_before=dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines()).get('oom_kill')
    initial_events=read('memory.events');start=time.monotonic();stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    if a.notebook:
        command=[sys.executable,'-m','jupyter','nbconvert','--to','notebook','--execute',str(a.notebook),'--output',str(base/'results'/case/'operation_A/A_annual_taxi_analysis.executed.ipynb'),'--ExecutePreprocessor.timeout=-1']
    else:command=[sys.executable,str(Path(__file__).with_name('operations.py')),a.operation]
    peak_rss=peak_pss=peak_cgroup=0;guard_stop=None
    with (out/'process.log').open('w') as log,(out/'samples.csv').open('w') as stream,(out/'process_trees.jsonl').open('w') as trees:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        fields=['elapsed_s','pid','rss_bytes','pss_bytes','cgroup_current_bytes','cgroup_peak_bytes','mem_available_bytes','swap_used_bytes','psi_some_avg10','psi_full_avg10','cpu_ticks','cgroup_swap_bytes']
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader()
        while True:
            memory=metrics();pids=[int(x) for x in (cg/'cgroup.procs').read_text().split()];rss=pss=ticks=0
            for pid in pids:
                try:
                    d={k:v.strip() for k,v in (l.split(':',1) for l in Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines() if ':' in l)}
                    rss+=int(d['Rss'].split()[0])*1024;pss+=int(d['Pss'].split()[0])*1024
                    stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();ticks+=int(stat[11])+int(stat[12])
                except (OSError,KeyError,ValueError):pass
            pressure={line.split()[0]:dict(item.split('=') for item in line.split()[1:]) for line in Path('/proc/pressure/memory').read_text().splitlines()}
            current=int(read('memory.current'));peak_cgroup=max(peak_cgroup,current);peak_rss=max(peak_rss,rss);peak_pss=max(peak_pss,pss)
            w.writerow(dict(elapsed_s=time.monotonic()-start,pid=child.pid,rss_bytes=rss,pss_bytes=pss,cgroup_current_bytes=current,cgroup_peak_bytes=read('memory.peak'),mem_available_bytes=memory['MemAvailable'],swap_used_bytes=memory['SwapTotal']-memory['SwapFree'],psi_some_avg10=pressure['some']['avg10'],psi_full_avg10=pressure['full']['avg10'],cpu_ticks=ticks,cgroup_swap_bytes=read('memory.swap.current')));stream.flush()
            tree=[]
            for pid in pids:
                try:
                    fields_stat=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
                    tree.append(dict(pid=pid,ppid=int(fields_stat[1]),comm=Path(f'/proc/{pid}/comm').read_text().strip()))
                except OSError:pass
            trees.write(json.dumps(dict(elapsed_s=time.monotonic()-start,processes=tree))+'\n');trees.flush()
            code=child.poll()
            if code is not None:break
            if memory['MemAvailable']<1536*1024**2:
                import signal
                guard_stop='MemAvailable below 1.5 GiB: stop related operation, no condition changes'
                os.killpg(child.pid,signal.SIGTERM);code=child.wait(timeout=30);break
            time.sleep(.5)
    result=dict(operation=a.operation,pid=child.pid,cgroup=str(cg),started_utc=stamp,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),duration_s=time.monotonic()-start,peak_rss_bytes=peak_rss,peak_pss_bytes=peak_pss,peak_cgroup_observed_bytes=peak_cgroup,kernel_memory_peak=read('memory.peak'),returncode=code,guard_stop=guard_stop,memory_events_before=initial_events,memory_events_after=read('memory.events'),cpu_clock_ticks_per_second=os.sysconf('SC_CLK_TCK'),input_bytes=sum(p.stat().st_size for p in (base/'assets'/case/'yellow_taxi').glob('*.parquet')))
    global_after=dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines()).get('oom_kill')
    result['global_oom_kill_delta']=int(global_after)-int(global_before)
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    before = dict(line.split() for line in initial_events.splitlines())
    after = dict(line.split() for line in read('memory.events').splitlines())
    if code or guard_stop or result['global_oom_kill_delta'] or int(after['oom_kill']) > int(before['oom_kill']):raise SystemExit(1)

if __name__=='__main__':main()
