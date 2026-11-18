"""Streaming collector shared by baseline/freezer/original memshiftd.

All memory values are Bytes. Task memory is read only from cgroup-v2 files;
process, virtual, swap and disk-I/O fields have separate names and scopes.
"""
import csv
import json
from pathlib import Path
import threading
import time
from .timeline import wait_until_ns


def read_text(path):
    try:return Path(path).read_text()
    except (OSError,UnicodeError):return None


def integer(path):
    text=read_text(path)
    try:return int(text.strip()) if text is not None else None
    except ValueError:return None


def counters(path):
    text=read_text(path)
    if text is None:return None
    try:return {k:int(v) for k,v in (line.split() for line in text.splitlines())}
    except (ValueError,TypeError):return None


def meminfo(path='/proc/meminfo'):
    text=read_text(path)
    if text is None:raise OSError('meminfo unavailable')
    result={}
    for line in text.splitlines():
        key,value=line.split(':',1);parts=value.split()
        result[key]=int(parts[0])*(1024 if len(parts)>1 and parts[1]=='kB' else 1)
    return result


def pressure(path):
    text=read_text(path)
    if text is None:return None
    result={}
    for line in text.splitlines():
        values=line.split();result[values[0]]={}
        for part in values[1:]:
            k,v=part.split('=',1);result[values[0]][k]=int(v) if k=='total' else float(v)
    return result


def process_memory(pid):
    result={};raw=read_text(f'/proc/{pid}/status')
    if raw is None:return {'status':'process_unavailable'}
    keys={'VmRSS':'rss_bytes','VmHWM':'rss_high_water_bytes','VmSize':'virtual_size_bytes','VmPeak':'virtual_high_water_bytes','VmSwap':'process_swap_bytes','RssAnon':'rss_anon_bytes','RssFile':'rss_file_bytes','RssShmem':'rss_shared_bytes'}
    for line in raw.splitlines():
        key,_,value=line.partition(':')
        if key in keys:result[keys[key]]=int(value.split()[0])*1024
    smaps=read_text(f'/proc/{pid}/smaps_rollup');private=[]
    if smaps is not None:
        for line in smaps.splitlines():
            key,_,value=line.partition(':')
            if key=='Pss':result['pss_bytes']=int(value.split()[0])*1024
            if key in {'Private_Clean','Private_Dirty','Private_Hugetlb'}:private.append(int(value.split()[0])*1024)
        result['uss_bytes']=sum(private) if private else None
    result['status']='ok' if smaps is not None else 'smaps_rollup_unavailable'
    return result


class CsvSink:
    def __init__(self,path,fields):
        self.file=Path(path).open('w',newline='',buffering=1);self.writer=csv.DictWriter(self.file,fieldnames=fields)
        self.writer.writeheader();self.lock=threading.Lock()
    def write(self,row):
        with self.lock:self.writer.writerow(row)
    def close(self):self.file.close()


class MemoryMonitor:
    def __init__(self,output_dir,timeline,operations,interval_s=.05,low_memory_bytes=500*1024**2,proc='/proc'):
        if interval_s<=0:raise ValueError('positive sample interval required')
        self.output=Path(output_dir);self.timeline=timeline;self.operations=operations;self.interval=interval_s
        self.threshold=low_memory_bytes;self.proc=Path(proc);self.stop_event=threading.Event();self.ready=threading.Event();self.thread=None
        self.system=CsvSink(self.output/'system_memory.csv',['monotonic_ns','wall_time_ns','relative_T0_s','mem_total_bytes','mem_free_bytes','mem_available_bytes','resident_allocated_bytes','pressure_used_bytes','buffers_bytes','cached_bytes','sreclaimable_bytes','shmem_bytes','swap_total_bytes','swap_free_bytes','swap_used_bytes','vmstat_json','sample_status'])
        self.task=CsvSink(self.output/'task_memory.csv',['monotonic_ns','relative_T0_s','operation','cgroup','pid','memory_current_bytes','memory_peak_bytes','memory_swap_current_bytes','stat_anon_bytes','stat_file_bytes','stat_kernel_bytes','memory_stat_json','memory_events_json','memory_events_local_json','cpu_stat_json','io_stat_json','process_memory_json','sample_status'])
        self.psi=CsvSink(self.output/'psi.csv',['monotonic_ns','relative_T0_s','scope','resource','stall','avg10','avg60','avg300','total_us','status'])
        self.oom=CsvSink(self.output/'oom_events.csv',['monotonic_ns','relative_T0_s','scope','operation','counter','delta','value','killed_pid','evidence'])
        self.low=CsvSink(self.output/'low_memory_events.csv',['start_monotonic_ns','end_monotonic_ns','duration_s','threshold_bytes','minimum_available_bytes','censored'])
        self.previous={};self.low_start=None;self.low_min=None;self.global_peak=0;self.pressure_peak=0;self.min_available=None;self.task_peaks={};self.samples=0;self.errors=[];self.low_count=0;self.low_duration=0;self.last_ns=None
        self.formal_samples=0

    def relative(self,now):return (now-self.timeline.t0_ns)/1e9 if self.timeline.t0_ns is not None else None

    def event_counters(self,scope,operation,current,now):
        if current is None:return
        for key in ('oom','oom_kill','oom_group_kill'):
            if key not in current:continue
            ident=(scope,operation,key);prior=self.previous.get(ident);value=current[key];self.previous[ident]=value
            if prior is not None and value>prior:
                self.oom.write(dict(monotonic_ns=now,relative_T0_s=self.relative(now),scope=scope,operation=operation,counter=key,delta=value-prior,value=value,killed_pid=None,evidence='counter delta; victim PID requires kernel evidence'))
                self.timeline.emit('OOM',operation,actual_ns=now,counter=key,delta=value-prior,scope=scope)

    def psi_rows(self,scope,root,now):
        for resource in ('memory','cpu','io'):
            path=root/resource if scope=='system' else root/(resource+'.pressure')
            data=pressure(path)
            if data is None:
                self.psi.write(dict(monotonic_ns=now,relative_T0_s=self.relative(now),scope=scope,resource=resource,stall='',status='unsupported_or_unreadable'));continue
            for stall,values in data.items():
                self.psi.write(dict(monotonic_ns=now,relative_T0_s=self.relative(now),scope=scope,resource=resource,stall=stall,avg10=values.get('avg10'),avg60=values.get('avg60'),avg300=values.get('avg300'),total_us=values.get('total'),status='ok'))

    def finish_low(self,now,censored=False):
        if self.low_start is None:return
        duration=(now-self.low_start)/1e9;self.low_duration+=duration
        self.low.write(dict(start_monotonic_ns=self.low_start,end_monotonic_ns=now,duration_s=duration,threshold_bytes=self.threshold,minimum_available_bytes=self.low_min,censored=censored))
        self.low_start=None;self.low_min=None

    def sample(self):
        now=time.monotonic_ns();info=meminfo(self.proc/'meminfo');vm=counters(self.proc/'vmstat') or {}
        total=info['MemTotal'];available=info.get('MemAvailable');free=info.get('MemFree')
        valid=available is not None and free is not None and 0<=available<=total and 0<=free<=total
        resident=total-free if free is not None else None;used=total-available if available is not None else None
        status='ok' if valid else 'INVALID_MEMINFO_RANGE'
        self.system.write(dict(monotonic_ns=now,wall_time_ns=time.time_ns(),relative_T0_s=self.relative(now),mem_total_bytes=total,mem_free_bytes=free,mem_available_bytes=available,resident_allocated_bytes=resident,pressure_used_bytes=used,buffers_bytes=info.get('Buffers'),cached_bytes=info.get('Cached'),sreclaimable_bytes=info.get('SReclaimable'),shmem_bytes=info.get('Shmem'),swap_total_bytes=info.get('SwapTotal'),swap_free_bytes=info.get('SwapFree'),swap_used_bytes=info.get('SwapTotal',0)-info.get('SwapFree',0),vmstat_json=json.dumps(vm),sample_status=status))
        if not valid:self.errors.append(status)
        formal=self.timeline.t0_ns is not None and now>=self.timeline.t0_ns
        if formal:self.formal_samples+=1
        if valid and formal:
            self.global_peak=max(self.global_peak,resident);self.pressure_peak=max(self.pressure_peak,used)
            self.min_available=available if self.min_available is None else min(self.min_available,available)
            if available<self.threshold:
                if self.low_start is None:self.low_start=now;self.low_count+=1;self.low_min=available
                self.low_min=min(self.low_min,available)
            else:self.finish_low(now)
        self.event_counters('system','',{'oom_kill':vm['oom_kill']} if 'oom_kill' in vm else None,now)
        self.psi_rows('system',self.proc/'pressure',now)
        for operation,op in list(self.operations.items()):
            group=op.get('cgroup_path');pid=op.get('pid')
            if not group:continue
            root=Path(group);stat=counters(root/'memory.stat');events=counters(root/'memory.events');local=counters(root/'memory.events.local');current=integer(root/'memory.current');peak=integer(root/'memory.peak')
            pm=process_memory(pid) if pid and self.samples%max(1,round(1/self.interval))==0 else {'status':'not_sampled_this_tick'}
            self.task.write(dict(monotonic_ns=now,relative_T0_s=self.relative(now),operation=operation,cgroup=str(root),pid=pid,memory_current_bytes=current,memory_peak_bytes=peak,memory_swap_current_bytes=integer(root/'memory.swap.current'),stat_anon_bytes=(stat or {}).get('anon'),stat_file_bytes=(stat or {}).get('file'),stat_kernel_bytes=(stat or {}).get('kernel'),memory_stat_json=json.dumps(stat),memory_events_json=json.dumps(events),memory_events_local_json=json.dumps(local),cpu_stat_json=json.dumps(counters(root/'cpu.stat')),io_stat_json=read_text(root/'io.stat'),process_memory_json=json.dumps(pm),sample_status='ok' if current is not None else 'cgroup_unreadable'))
            if current is not None and formal:self.task_peaks[operation]=max(self.task_peaks.get(operation,0),current)
            # Only leaf workload scopes are counted. Parent slices are not added.
            self.event_counters('task_cgroup',operation,events,now)
            self.psi_rows(operation,root,now)
        self.samples+=1;self.last_ns=now

    def start(self):
        self.thread=threading.Thread(target=self.run,name='oomlab-collector');self.thread.start()
        if not self.ready.wait(10):raise TimeoutError('monitor did not become ready')
        if self.errors:raise RuntimeError('monitor failed: '+self.errors[0])

    def run(self):
        deadline=time.monotonic_ns()
        try:
            self.sample();self.timeline.emit('monitor_ready');self.ready.set()
            while not self.stop_event.is_set():
                deadline+=int(self.interval*1e9)
                if not wait_until_ns(deadline,self.stop_event):break
                self.sample()
                # Skip missed ticks rather than burst-sampling under pressure.
                if deadline<time.monotonic_ns()-int(self.interval*1e9):deadline=time.monotonic_ns()
        except Exception as error:
            self.errors.append(repr(error));self.ready.set();self.timeline.emit('collector_error',status='failed',error=repr(error))

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=10)
        if self.thread and self.thread.is_alive():raise RuntimeError('collector did not stop')
        self.finish_low(self.last_ns or time.monotonic_ns(),True)
        for sink in (self.system,self.task,self.psi,self.oom,self.low):sink.close()
        return dict(samples=self.samples,formal_samples=self.formal_samples,summary_scope='at/after homepage_ready T0; negative-time raw samples retained only as preflight/baseline evidence',interval_s=self.interval,low_memory_threshold_bytes=self.threshold,low_memory_events=self.low_count,low_memory_duration_s=self.low_duration,min_available_bytes=self.min_available,system_resident_allocated_peak_bytes=self.global_peak if self.formal_samples else None,system_pressure_used_peak_bytes=self.pressure_peak if self.formal_samples else None,task_sampled_current_peaks_bytes=self.task_peaks,errors=self.errors,global_oom_count=None,global_oom_count_status='Linux vmstat exposes kill count; global OOM attempts require kernel evidence')
