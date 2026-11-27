#!/usr/bin/env python3
"""Read-only, bounded-duration host memory observer. No GUI, cgroup writes or services.

JSONL streams retain per-read status and clocks. Missing values are never zero-filled.
Parent and child cgroup charges MUST NOT be summed as host memory usage.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time


def pairs(text):
    return {p[0]: int(p[1]) for line in text.splitlines() if len(p := line.split()) == 2}


def cpu_stat(text):
    """Parse aggregate and per-CPU /proc/stat counters without treating ticks as bytes."""
    return {p[0]: [int(x) for x in p[1:]] for line in text.splitlines()
            if (p := line.split()) and (p[0] == 'cpu' or p[0][3:].isdigit() and p[0].startswith('cpu'))}


def pid_stat(text):
    left, right = text.index('('), text.rindex(')')
    fields = text[right + 1:].split()
    return dict(pid=int(text[:left].strip()), comm=text[left + 1:right],
                state=fields[0], ppid=int(fields[1]), starttime=int(fields[19]))


def memory_fields(text):
    result = {}
    for line in text.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        p = value.split()
        if p and p[0].isdigit():
            result[key] = int(p[0]) * (1024 if len(p) > 1 and p[1] == 'kB' else 1)
    return result


def psi(text):
    result = {k: None for k in ('some', 'full')}
    for line in text.splitlines():
        p = line.split()
        if p and p[0] in result:
            row = {k: None for k in ('avg10', 'avg60', 'avg300', 'total')}
            for token in p[1:]:
                k, v = token.split('=')
                if k in row:
                    row[k] = int(v) if k == 'total' else float(v)
            result[p[0]] = row
    return result


def counter_delta(first, last):
    return {k: None if first.get(k) is None or last.get(k) is None or last[k] < first[k]
            else last[k] - first[k] for k in first.keys() | last.keys()}


def read(path, parser=lambda x: x, link=False):
    try:
        value = os.readlink(path) if link else Path(path).read_text()
        return dict(status='ok', value=parser(value))
    except OSError as e:
        status = 'permission_denied' if e.errno in (errno.EACCES, errno.EPERM) else 'not_found' if e.errno in (errno.ENOENT, errno.ESRCH) else 'read_error'
        return dict(status=status, value=None, errno=e.errno)
    except (ValueError, IndexError) as e:
        return dict(status='parse_error', value=None, error=str(e))


def process(path, pss=False):
    before = read(path / 'stat', pid_stat)
    raw = read(path / 'status')
    status = dict(raw, value=memory_fields(raw['value']) if raw['status'] == 'ok' else None)
    r = dict(pid=int(path.name), identity=before, status=status,
             exe=read(path / 'exe', link=True), cgroup=read(path / 'cgroup'),
             comm=read(path / 'comm'))
    # UID/state/PPID/Threads are explicitly retained; no cmdline or environ is opened.
    r['attributes'] = {k: next((line.split(':', 1)[1].strip() for line in (raw['value'] or '').splitlines()
                              if line.startswith(k + ':')), None)
                       for k in ('Uid', 'State', 'PPid', 'Threads')}
    if pss:
        r['pss'] = read(path / 'smaps_rollup', memory_fields)
    r['uid'] = int(r['attributes']['Uid'].split()[0]) if r['attributes']['Uid'] else None
    after = read(path / 'stat', pid_stat)
    r['identity_status'] = ('ok' if before['status'] == after['status'] == 'ok' and
                            before['value']['starttime'] == after['value']['starttime'] else
                            'pid_reused' if before['status'] == after['status'] == 'ok' else
                            'disappeared' if after['status'] == 'not_found' else before['status'] if before['status'] != 'ok' else after['status'])
    if r['identity_status'] != 'ok':
        r['status'] = dict(status=r['identity_status'], value=None)
        if pss:
            r['pss'] = dict(status=r['identity_status'], value=None)
    r['memory'] = {k: (r['status']['value'] or {}).get(k) for k in ('VmRSS','VmHWM','RssAnon','RssFile','RssShmem','VmSwap')}
    if pss:
        r['pss_fields'] = {k: (r['pss']['value'] or {}).get(k) for k in ('Pss','Pss_Anon','Pss_File','Pss_Shmem','SwapPss')}
    return r


def transitions(previous, current):
    events = []
    for key in previous.keys() - current.keys():
        events.append(dict(event='exit', identity=key))
    for key in current:
        if key not in previous:
            events.append(dict(event='new', identity=key, cgroup=current[key]))
        elif previous[key] != current[key]:
            events.append(dict(event='cgroup_migration', identity=key, before=previous[key], after=current[key]))
    return events


def cgroup(path):
    r = {}
    for name in ('memory.current', 'memory.peak', 'memory.swap.current'):
        r[name] = read(path / name, lambda t: int(t.strip()))
    for name in ('memory.stat', 'memory.events', 'memory.events.local', 'cgroup.events'):
        r[name] = read(path / name, pairs)
    r['memory.pressure'] = read(path / 'memory.pressure', psi)
    r['cgroup.procs'] = read(path / 'cgroup.procs', lambda t: [int(x) for x in t.split()])
    r['process_count'] = len(r['cgroup.procs']['value']) if r['cgroup.procs']['status'] == 'ok' else None
    return r


class Writer:
    def __init__(self, output, boot_id):
        self.output, self.boot_id, self.handles = output, boot_id, {}
        self.write_ns = 0

    def emit(self, stream, data):
        begin = time.monotonic_ns()
        row = dict(monotonic_ns=begin, boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                   wall_time_ns=time.time_ns(), boot_id=self.boot_id, **data)
        if stream not in self.handles:
            self.handles[stream] = (self.output / (stream + '.jsonl')).open('x')
        self.handles[stream].write(json.dumps(row, separators=(',', ':')) + '\n')
        self.handles[stream].flush()
        self.write_ns += time.monotonic_ns() - begin
        return row

    def close(self):
        for h in self.handles.values():
            h.close()


def seal(output):
    files = sorted(p for p in output.iterdir() if p.is_file() and p.name != 'manifest.sha256')
    (output / 'manifest.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))


class Watch:
    def __init__(self, output, proc=Path('/proc'), cg=Path('/sys/fs/cgroup'), sysroot=Path('/sys')):
        self.proc, self.cg, self.sysroot = proc, cg, sysroot
        self.boot = read(proc / 'sys/kernel/random/boot_id')['value']
        self.writer = Writer(output, self.boot.strip() if self.boot else None)
        self.previous, self.previous_groups = {}, set()

    def system(self):
        return dict(meminfo=read(self.proc / 'meminfo', memory_fields),
                    vmstat=read(self.proc / 'vmstat', pairs), cpu_stat=read(self.proc / 'stat', cpu_stat),
                    psi={kind: read(self.proc / 'pressure' / kind, psi) for kind in ('memory', 'cpu', 'io')})

    def processes(self, pss=False):
        begin = time.monotonic_ns()
        try:
            paths = sorted(p for p in self.proc.iterdir() if p.name.isdigit())
        except OSError as e:
            return dict(status='read_error', error=str(e), rows=[], duration_ns=time.monotonic_ns()-begin)
        rows = [process(p, pss) for p in paths]
        good = [r for r in rows if r['identity_status'] == 'ok']
        mapping = {str(r['pid']) + ':' + str(r['identity']['value']['starttime']): r['cgroup']['value'] for r in good}
        event = [] if pss else transitions(self.previous, mapping)
        if not pss:
            self.previous = mapping
        count = sum(r.get('pss', {}).get('status') == 'ok' for r in rows) if pss else sum(r['status']['status'] == 'ok' for r in good)
        return dict(rows=rows, events=event, attempted=len(paths), readable=count,
                    coverage=count / len(paths) if paths else None, duration_ns=time.monotonic_ns()-begin,
                    scope='all visible PIDs; permission/exit failures retained; PSS is partial unless every PID readable')

    def cgroups(self):
        begin = time.monotonic_ns(); rows = []; errors = []
        for root, ds, fs in os.walk(self.cg, onerror=lambda e: errors.append(str(e))):
            if 'memory.current' in fs:
                p = Path(root); rows.append(dict(path='/' + str(p.relative_to(self.cg)).replace('.', '', 1) if p == self.cg else '/' + str(p.relative_to(self.cg)), metrics=cgroup(p)))
        current = {r['path'] for r in rows}; removed = sorted(self.previous_groups-current); self.previous_groups = current
        return dict(rows=rows, removed=removed, attempted=len(rows), readable=sum(r['metrics']['memory.current']['status']=='ok' for r in rows), walk_errors=errors, duration_ns=time.monotonic_ns()-begin, accounting='hierarchical; never sum parents and children')

    def zones(self):
        return {name: read(self.proc/name) for name in ('zoneinfo', 'buddyinfo', 'pagetypeinfo')}

    def configuration(self):
        paths, errors = [], []
        for base, recursive in [(self.sysroot/'kernel/mm/transparent_hugepage', True),
                                (self.sysroot/'module/zswap/parameters', False),
                                (self.sysroot/'kernel/debug/zswap', False)]:
            try:
                if recursive:
                    for root, ds, fs in os.walk(base, onerror=lambda e: errors.append(str(e))):
                        paths.extend(Path(root)/name for name in fs)
                else:
                    paths.extend(base.iterdir())
            except OSError as e:
                errors.append(str(e))
        for dev in (self.sysroot/'block').glob('zram*'):
            paths += [dev/n for n in ('mm_stat', 'disksize', 'comp_algorithm')]
        paths += [self.proc/'sys/vm'/n for n in ('swappiness','overcommit_memory','overcommit_ratio','min_free_kbytes','watermark_scale_factor','watermark_boost_factor','zone_reclaim_mode','page-cluster')]
        return dict(files={str(p):read(p) for p in paths}, enumeration_errors=errors,
                    zswap_debug=read(self.sysroot/'kernel/debug/zswap'),
                    zram_devices=[p.name for p in (self.sysroot/'block').glob('zram*')])

    def vmware(self):
        tool = shutil.which('vmware-toolbox-cmd')
        if not tool:
            return dict(status='UNKNOWN', reason='tool unavailable')
        try:
            p = subprocess.run([tool,'stat','balloon'],capture_output=True,text=True,timeout=2)
            return dict(status='ok' if p.returncode==0 else 'UNKNOWN', returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except (OSError, subprocess.TimeoutExpired) as e:
            return dict(status='UNKNOWN', reason=str(e))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--duration',type=float,default=180)
    for kind,value in [('system',1),('process',2),('cgroup',2),('pss',10),('zone',10)]:p.add_argument('--'+kind+'-interval',type=float,default=value)
    p.add_argument('--proc-root',type=Path,default=Path('/proc'));p.add_argument('--cgroup-root',type=Path,default=Path('/sys/fs/cgroup'));p.add_argument('--sys-root',type=Path,default=Path('/sys'))
    a=p.parse_args(argv)
    if a.duration<=0 or any(getattr(a,k+'_interval')<=0 for k in ('system','process','cgroup','pss','zone')):p.error('positive duration and intervals required')
    output=a.output.absolute();repo=Path(__file__).resolve().parents[2]
    if output.resolve().is_relative_to(repo):p.error('output must be outside repository')
    existing = output
    while not existing.exists():
        existing = existing.parent
    if subprocess.run(['git','-C',str(existing),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:p.error('output is inside a Git checkout')
    if os.geteuid()==0:p.error('run as login user; no implicit root monitoring')
    output.mkdir(parents=True,exist_ok=False);w=Watch(output,a.proc_root,a.cgroup_root,a.sys_root);start=time.monotonic();cpu=time.process_time();stop=[];old={}
    for sig in (signal.SIGINT,signal.SIGTERM):old[sig]=signal.signal(sig,lambda s,f:stop.append(s))
    tasks={'system':(a.system_interval,w.system),'processes':(a.process_interval,w.processes),'cgroups':(a.cgroup_interval,w.cgroups),'pss':(a.pss_interval,lambda:w.processes(True)),'zones':(a.zone_interval,w.zones),'vmware':(a.zone_interval,w.vmware)};due={k:start for k in tasks};last={};error=None
    (output/'metadata.json').write_text(json.dumps(dict(uid=os.getuid(),pid=os.getpid(),duration_requested_s=a.duration,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),boot_id=w.writer.boot_id,intervals={k:v[0] for k,v in tasks.items()},clock='monotonic scheduling; snapshots bracketed, not atomic',privacy='no cmdline or environ',readonly=True),indent=2))
    try:
        w.writer.emit('configuration',dict(phase='start',data=w.configuration()))
        while not stop and time.monotonic()-start<a.duration:
            for name,(interval,fn) in tasks.items():
                now=time.monotonic()
                if now<due[name]:continue
                begin=time.monotonic_ns();data=fn();elapsed=time.monotonic_ns()-begin
                failures=[]
                def walk(x):
                    if isinstance(x,dict):
                        if 'status' in x and isinstance(x['status'],str) and x['status'] not in ('ok',):failures.append(x['status'])
                        for v in x.values():walk(v)
                    elif isinstance(x,list):
                        for v in x:walk(v)
                walk(data);w.writer.emit(name,dict(read_start_monotonic_ns=begin,read_end_monotonic_ns=time.monotonic_ns(),data=data))
                own=read(Path('/proc')/str(os.getpid())/'status',memory_fields);own_pss=read(Path('/proc')/str(os.getpid())/'smaps_rollup',memory_fields)
                w.writer.emit('monitor_health',dict(stream=name,sample_duration_ns=elapsed,failures=len(failures),failure_statuses=failures,cpu_time_s=time.process_time()-cpu,own_status=own,own_pss=own_pss,write_duration_ns_total=w.writer.write_ns,interval_deviation_s=None if name not in last else now-last[name]-interval,lateness_s=max(0,now-due[name])))
                last[name]=now;due[name]=max(due[name]+interval,time.monotonic()+.001)
            time.sleep(min(.1,max(.001,min(due.values())-time.monotonic())))
    except Exception as e:error=repr(e)
    finally:
        final=dict(monotonic_ns=time.monotonic_ns(),boottime_ns=time.clock_gettime_ns(time.CLOCK_BOOTTIME),wall_time_ns=time.time_ns(),boot_id=w.writer.boot_id,elapsed_s=time.monotonic()-start,cpu_time_s=time.process_time()-cpu,max_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,interrupted=bool(stop),error=error,configuration=w.configuration(),system=w.system())
        final['single_core_cpu_percent']=100*final['cpu_time_s']/final['elapsed_s'];(output/'final_snapshot.json').write_text(json.dumps(final,indent=2));w.writer.close();seal(output)
        for sig,handler in old.items():signal.signal(sig,handler)
    print(json.dumps({k:final[k] for k in ('elapsed_s','cpu_time_s','single_core_cpu_percent','max_rss_bytes','interrupted','error')}));return 1 if error else 0

if __name__=='__main__':raise SystemExit(main())
