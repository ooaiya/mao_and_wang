"""Lightweight field-bracketed sampling; no smaps reads in the 50 ms loop."""
import csv,json,threading,time
from pathlib import Path

def values(path):
    return {a:int(b) for a,b in (line.split() for line in Path(path).read_text().splitlines())}
def memory():return {a.rstrip(':'):int(b)*1024 for a,b,*_ in (line.split() for line in Path('/proc/meminfo').read_text().splitlines())}

class Monitor:
    def __init__(self,out,timeline,groups):
        self.out=Path(out);self.timeline=timeline;self.groups=groups;self.stop_event=threading.Event();self.errors=[];self.files=[];self.samples=0
        self.previous=None;self.gaps=[];self.task_peaks={};self.minimum=None;self.pressure_peak=0;self.swap_max=0
        self.system=self.writer('system_memory.csv',['monotonic_ns','read_end_ns','relative_T0_s','mem_total_bytes','mem_available_bytes','pressure_used_bytes','swap_total_bytes','swap_used_bytes','oom_kill'])
        self.task=self.writer('task_memory.csv',['monotonic_ns','read_end_ns','relative_T0_s','operation','cgroup','memory_current_bytes','memory_peak_bytes','stat_anon_bytes','stat_file_bytes','memory_swap_current_bytes','frozen','populated','cpu_usage_usec','memory_events_json'])
        self.batches=self.writer('sampling_batches.csv',['start_ns','end_ns','duration_s'])
        self.psi=self.writer('psi.csv',['monotonic_ns','memory_pressure'])
    def writer(self,name,fields):
        f=(self.out/name).open('w',newline='',buffering=1);self.files.append(f);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();return w
    def relative(self,t):return (t-self.timeline.t0_ns)/1e9 if self.timeline.t0_ns else None
    def sample(self):
        begin=time.monotonic_ns();m=memory();vm=values('/proc/vmstat');end=time.monotonic_ns();used=m['MemTotal']-m['MemAvailable'];swap=m.get('SwapTotal',0)-m.get('SwapFree',0)
        self.system.writerow(dict(monotonic_ns=begin,read_end_ns=end,relative_T0_s=self.relative(begin),mem_total_bytes=m['MemTotal'],mem_available_bytes=m['MemAvailable'],pressure_used_bytes=used,swap_total_bytes=m.get('SwapTotal',0),swap_used_bytes=swap,oom_kill=vm['oom_kill']))
        if self.timeline.t0_ns and begin>=self.timeline.t0_ns:
            if self.previous is not None:self.gaps.append((begin-self.previous)/1e9)
            self.previous=begin;self.minimum=m['MemAvailable'] if self.minimum is None else min(self.minimum,m['MemAvailable']);self.pressure_peak=max(self.pressure_peak,used);self.swap_max=max(self.swap_max,m.get('SwapTotal',0))
        for op,row in list(self.groups.items()):
            cg=Path(row['cgroup_path']);stamp=time.monotonic_ns();current=int((cg/'memory.current').read_text());stat=values(cg/'memory.stat');events=values(cg/'memory.events');state=values(cg/'cgroup.events');cpu=values(cg/'cpu.stat')
            self.task.writerow(dict(monotonic_ns=stamp,read_end_ns=time.monotonic_ns(),relative_T0_s=self.relative(stamp),operation=op,cgroup=str(cg),memory_current_bytes=current,memory_peak_bytes=int((cg/'memory.peak').read_text()),stat_anon_bytes=stat.get('anon',0),stat_file_bytes=stat.get('file',0),memory_swap_current_bytes=int((cg/'memory.swap.current').read_text()),frozen=state['frozen'],populated=state['populated'],cpu_usage_usec=cpu['usage_usec'],memory_events_json=json.dumps(events)))
            self.task_peaks[op]=max(current,self.task_peaks.get(op,0))
        if self.samples%5==0:self.psi.writerow(dict(monotonic_ns=time.monotonic_ns(),memory_pressure=Path('/proc/pressure/memory').read_text().strip()))
        self.batches.writerow(dict(start_ns=begin,end_ns=time.monotonic_ns(),duration_s=(time.monotonic_ns()-begin)/1e9));self.samples+=1
    def run(self):
        deadline=time.monotonic()
        try:
            while not self.stop_event.is_set():
                self.sample();deadline+=.05
                if deadline<time.monotonic():deadline=time.monotonic()+.05
                self.stop_event.wait(max(0,deadline-time.monotonic()))
        except Exception as e:self.errors.append(repr(e))
    def start(self):self.thread=threading.Thread(target=self.run);self.thread.start()
    def stop(self):
        self.stop_event.set();self.thread.join(10)
        if self.thread.is_alive():raise RuntimeError('sampler failed to stop')
        for f in self.files:f.close()
        return dict(samples=self.samples,errors=self.errors,mean_interval_s=sum(self.gaps)/len(self.gaps) if self.gaps else None,max_gap_s=max(self.gaps,default=0),min_available_bytes=self.minimum,system_pressure_peak_bytes=self.pressure_peak,formal_swap_total_max_bytes=self.swap_max,task_sampled_current_peaks_bytes=self.task_peaks,
                    scope='T0=verified automatic Krita homepage; each field group has read-start/end brackets; no smaps in collector loop')
