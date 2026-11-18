"""Kernel files are sequential reads, not an atomic snapshot. Missing means None."""
import math
import os
import json
import time
from pathlib import Path
from .common import SCHEMA

EVENTS = ('low','high','max','oom','oom_kill','oom_group_kill')
STATS = ('anon','file','kernel','kernel_stack','pagetables','sock','shmem','slab','file_mapped','file_dirty','file_writeback','inactive_anon','active_anon','inactive_file','active_file','slab_reclaimable','slab_unreclaimable')
PSI_FIELDS = ('avg10','avg60','avg300','total')
PROCESS_FIELDS=['krita_pid','krita_ppid','krita_starttime','krita_state','krita_rss_bytes','krita_vm_rss_bytes','krita_vm_hwm_bytes','krita_vm_size_bytes','krita_threads','krita_cpu_ticks','krita_cpu_percent','krita_elapsed_s']
FIELDS = ['sample_index','schema_version','classification','scope','relative_s','monotonic_ns','boottime_ns','wall_time_ns','memory_current','memory_peak','swap_current','freeze_requested','frozen'] + ['stat_'+k for k in STATS] + ['event_'+k for k in EVENTS] + ['local_event_'+k for k in EVENTS] + [p+'_'+kind+'_'+field for p in ('cgroup_psi','global_psi') for kind in ('some','full') for field in PSI_FIELDS] + ['mem_total_bytes','mem_available_bytes','swap_total_bytes','swap_free_bytes','vmstat_json','capabilities_json']+PROCESS_FIELDS


def pairs(text):
    result={}
    for line in text.splitlines():
        key,value=line.split()
        if key in result: raise ValueError('duplicate kernel field')
        result[key]=int(value)
        if result[key]<0: raise ValueError('negative kernel counter')
    return result


def psi(text):
    result={kind+'_'+field:None for kind in ('some','full') for field in PSI_FIELDS}
    for line in text.splitlines():
        parts=line.split(); kind=parts[0]
        if kind not in ('some','full'): continue
        for token in parts[1:]:
            k,v=token.split('=')
            if k in PSI_FIELDS:
                value=int(v) if k=='total' else float(v)
                if not math.isfinite(value) or value<0 or (k!='total' and value>100): raise ValueError('invalid PSI')
                result[kind+'_'+k]=value
    return result


def read_optional(path):
    try: return Path(path).read_text()
    except FileNotFoundError: return None


def snapshot(cgroup, origin_ns, scope='krita', proc='/proc'):
    cg=Path(cgroup); proc=Path(proc); stamp=time.monotonic_ns()
    row=dict(schema_version=SCHEMA,scope=scope,relative_s=(stamp-origin_ns)/1e9,
             monotonic_ns=stamp,boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),wall_time_ns=time.time_ns())
    capabilities={}
    text=read_optional(cg/'cgroup.freeze');row['freeze_requested']=int(text) if text is not None else None
    text=read_optional(cg/'cgroup.events');row['frozen']=pairs(text).get('frozen') if text is not None else None
    for filename,key in [('memory.current','memory_current'),('memory.peak','memory_peak'),('memory.swap.current','swap_current')]:
        text=read_optional(cg/filename); row[key]=int(text) if text is not None else None
        capabilities[filename]=text is not None
    for filename,prefix,keys in [('memory.stat','stat_',STATS),('memory.events','event_',EVENTS),('memory.events.local','local_event_',EVENTS)]:
        text=read_optional(cg/filename); values=pairs(text) if text is not None else {}
        capabilities[filename]=text is not None
        row.update({prefix+k:values.get(k) for k in keys})
    for filename,prefix in [(cg/'memory.pressure','cgroup_psi_'),(proc/'pressure/memory','global_psi_')]:
        text=read_optional(filename); capabilities[prefix]=text is not None
        row.update({prefix+k:v for k,v in psi(text or '').items()})
    memory={}
    for line in (proc/'meminfo').read_text().splitlines():
        k,v=line.split(':',1)
        if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree'): memory[k]=int(v.split()[0])*1024
    row.update(mem_total_bytes=memory.get('MemTotal'),mem_available_bytes=memory.get('MemAvailable'),swap_total_bytes=memory.get('SwapTotal'),swap_free_bytes=memory.get('SwapFree'))
    vm=pairs((proc/'vmstat').read_text())
    keys={k for k in vm if k.startswith(('pgscan_','pgsteal_'))}|{'pgfault','pgmajfault','pswpin','pswpout','oom_kill','pgscan_kswapd','pgscan_direct','pgsteal_kswapd','pgsteal_direct'}
    row['vmstat']={k:vm.get(k) for k in keys}
    capabilities['vmstat_fields']={k:k in vm for k in keys}
    row['capabilities']=capabilities
    return row


def deltas(first,last):
    result={}
    for k in first.keys()|last.keys():
        if k.startswith(('event_','local_event_')) or (k.startswith(('cgroup_psi_','global_psi_')) and k.endswith('_total')):
            a,b=first.get(k),last.get(k)
            if a is None or b is None: result[k]=None
            elif b<a: raise ValueError('counter rollback: '+k)
            else: result[k]=b-a
    result['vmstat']={}
    for k in first.get('vmstat',{}).keys()|last.get('vmstat',{}).keys():
        a,b=first.get('vmstat',{}).get(k),last.get('vmstat',{}).get(k)
        if a is None or b is None: result['vmstat'][k]=None
        elif b<a: raise ValueError('vmstat rollback: '+k)
        else: result['vmstat'][k]=b-a
    return result


def process_sample(record,cgroup,stamp,previous=None,proc='/proc'):
    """Null before startup/after exit. Identity/cgroup changes always abort."""
    empty={k:None for k in PROCESS_FIELDS}
    if not Path(record).exists():return empty
    expected=json.loads(Path(record).read_text());pid=expected['pid'];p=Path(proc)/str(pid)
    try:
        raw=(p/'stat').read_text();f=raw[raw.rindex(')')+2:].split()
        if f[0] in ('Z','X'):return empty
        birth=int(f[19]);ppid=int(f[1]);exe=os.readlink(p/'exe')
        if (birth,ppid,exe)!=(expected['starttime'],expected['ppid'],expected['exe']):raise RuntimeError('Krita process identity changed')
        from .units import process_cgroup
        group=process_cgroup(pid,proc)
        if group!=cgroup:raise RuntimeError('Krita PID escaped expected workload cgroup')
        status={}
        for line in (p/'status').read_text().splitlines():
            k,v=line.split(':',1);status[k]=v.strip()
        if status.get('State','').startswith(('Z','X')):return empty
        def kb(k):return int(status[k].split()[0])*1024 if k in status else None
        ticks=int(f[11])+int(f[12]);hz=os.sysconf('SC_CLK_TCK')
        elapsed=time.clock_gettime(time.CLOCK_BOOTTIME)-birth/hz
        cpu=None
        if previous and previous.get('krita_pid')==pid and previous.get('krita_starttime')==birth:
            delta=ticks-previous['krita_cpu_ticks'];dt=(stamp-previous['monotonic_ns'])/1e9
            if delta<0 or dt<=0:raise ValueError('invalid process CPU counter/time')
            cpu=100*delta/hz/dt
        return dict(krita_pid=pid,krita_ppid=ppid,krita_starttime=birth,krita_state=f[0],krita_rss_bytes=int(f[21])*os.sysconf('SC_PAGE_SIZE'),
                    krita_vm_rss_bytes=kb('VmRSS'),krita_vm_hwm_bytes=kb('VmHWM'),krita_vm_size_bytes=kb('VmSize'),
                    krita_threads=int(status['Threads']) if 'Threads' in status else None,krita_cpu_ticks=ticks,krita_cpu_percent=cpu,krita_elapsed_s=elapsed)
    except (FileNotFoundError,ProcessLookupError):return empty
