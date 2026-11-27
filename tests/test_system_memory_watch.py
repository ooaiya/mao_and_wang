import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest import mock

SPEC=importlib.util.spec_from_file_location('watch',Path(__file__).resolve().parents[1]/'tools/diagnostics/system_memory_watch.py')
w=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(w)


def task(pid=12,start=99,comm='a (b) c'):
    return f'{pid} ({comm}) S 1 '+' '.join(['0']*17+[str(start)])+'\n'


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.proc=self.root/'proc';self.cg=self.root/'cg';self.sys=self.root/'sys'
        for p in [self.proc,self.cg,self.sys]:p.mkdir()
        p=self.proc/'12';p.mkdir();(p/'stat').write_text(task());(p/'status').write_text('Uid:\t1000 1000 1000 1000\nState:\tS\nPPid:\t1\nThreads:\t1\nVmRSS:\t20 kB\nVmSwap:\t0 kB\n');(p/'comm').write_text('a (b) c');(p/'cgroup').write_text('0::/a\n');(p/'smaps_rollup').write_text('Pss: 10 kB\nPss_Anon: 8 kB\n');(p/'exe').symlink_to('/bin/python3');(p/'cmdline').write_text('SECRET_NEVER_READ');(p/'environ').write_text('SECRET_NEVER_READ')
        (self.proc/'meminfo').write_text('MemTotal: 123 kB\nHugePages_Total: 2\n');(self.proc/'stat').write_text('cpu 1 2 3 4\ncpu0 1 2 3 4\n');(self.proc/'vmstat').write_text('pgfault 2\n');(self.proc/'pressure').mkdir()
        for name in ['memory','cpu','io']:(self.proc/'pressure'/name).write_text('some avg10=1.0 avg60=2.0 avg300=3.0 total=4\n')
        (self.proc/'sys/kernel/random').mkdir(parents=True);(self.proc/'sys/kernel/random/boot_id').write_text('fake-boot')
        for name,text in {'memory.current':'4','memory.peak':'8','memory.swap.current':'0','memory.stat':'anon 4\nfile 0\n','memory.events':'oom 0\n','memory.events.local':'oom 0\n','memory.pressure':'some avg10=0 avg60=0 avg300=0 total=0\n','cgroup.procs':'12\n','cgroup.events':'populated 1\n'}.items():(self.cg/name).write_text(text)
    def tearDown(self):self.tmp.cleanup()
    def test_proc_stat(self):self.assertEqual(w.cpu_stat('cpu 1 2 3\ncpu2 4 5 6\nintr 10'),{'cpu':[1,2,3],'cpu2':[4,5,6]})
    def test_comm_parentheses(self):self.assertEqual(w.pid_stat(task())['starttime'],99);self.assertEqual(w.pid_stat(task())['comm'],'a (b) c')
    def test_meminfo_units(self):self.assertEqual(w.memory_fields('MemTotal: 2 kB\nHugePages_Total: 3'),{'MemTotal':2048,'HugePages_Total':3})
    def test_psi(self):
        p=w.psi('some avg10=1 avg60=2 avg300=3 total=4\nfull avg10=5 avg60=6 avg300=7 total=8');self.assertEqual(p['full']['total'],8);self.assertEqual(p['some']['avg300'],3);self.assertIsNone(w.psi('')['full'])
    def test_delta(self):self.assertEqual(w.counter_delta({'a':2,'b':5},{'a':7,'b':1,'c':4}),{'a':5,'b':None,'c':None})
    def test_process_and_privacy(self):
        r=w.process(self.proc/'12',True);self.assertEqual(r['status']['value']['VmRSS'],20480);self.assertEqual(r['pss']['value']['Pss'],10240);self.assertNotIn('SECRET',json.dumps(r));self.assertNotIn('VmHWM',r['status']['value'])
    def test_permission(self):
        original=Path.read_text
        def denied(p,*a,**kw):
            if p.name=='smaps_rollup':raise PermissionError(13,'denied')
            return original(p,*a,**kw)
        with mock.patch.object(Path,'read_text',denied):r=w.process(self.proc/'12',True)
        self.assertEqual(r['pss']['status'],'permission_denied');self.assertIsNone(r['pss']['value'])
    def test_disappearance(self):
        (self.proc/'12/stat').unlink();self.assertEqual(w.process(self.proc/'12')['identity_status'],'disappeared')
    def test_pid_reuse(self):
        original=w.read;count=[0]
        def reused(p,*a,**kw):
            if p.name=='stat':
                count[0]+=1;return dict(status='ok',value=w.pid_stat(task(start=count[0])))
            return original(p,*a,**kw)
        with mock.patch.object(w,'read',reused):self.assertEqual(w.process(self.proc/'12',True)['identity_status'],'pid_reused')
        events=w.transitions({'12:1':'/a'},{'12:2':'/a'});self.assertEqual({e['event'] for e in events},{'new','exit'})
    def test_migration(self):self.assertEqual(w.transitions({'12:1':'/a'},{'12:1':'/b'})[0]['event'],'cgroup_migration')
    def test_cgroups(self):
        o=self.root/'out';o.mkdir();watch=w.Watch(o,self.proc,self.cg,self.sys);r=watch.cgroups();self.assertEqual(r['readable'],1);self.assertEqual(r['rows'][0]['metrics']['process_count'],1)
        (self.cg/'memory.current').unlink();self.assertIn('/',watch.cgroups()['removed']);self.assertEqual(w.cgroup(self.cg)['memory.current']['status'],'not_found');watch.writer.close()
    def test_protected_configuration_directory(self):
        o=self.root/'out';o.mkdir();watch=w.Watch(o,self.proc,self.cg,self.sys)
        original=Path.iterdir
        def denied(p):
            if p.name=='zswap':raise PermissionError(13,'denied')
            return original(p)
        with mock.patch.object(Path,'iterdir',denied):r=watch.configuration()
        self.assertTrue(r['enumeration_errors']);watch.writer.close()
    def test_clock_json_seal(self):
        o=self.root/'out';o.mkdir();wr=w.Writer(o,'boot');first=wr.emit('system',{});last=wr.emit('system',{});wr.close();self.assertGreater(last['monotonic_ns'],first['monotonic_ns']);self.assertIn('boottime_ns',last);w.seal(o)
        import hashlib
        for line in (o/'manifest.sha256').read_text().splitlines():h,name=line.split('  ');self.assertEqual(h,hashlib.sha256((o/name).read_bytes()).hexdigest())
    def test_fake_smoke_interrupt(self):
        o=self.root/'smoke';timer=threading.Timer(.15,lambda:os.kill(os.getpid(),signal.SIGTERM))
        with mock.patch.object(w.Watch,'vmware',return_value={'status':'UNKNOWN','reason':'fixture'}):
            timer.start()
            try:code=w.main(['--output',str(o),'--duration','2','--proc-root',str(self.proc),'--cgroup-root',str(self.cg),'--sys-root',str(self.sys),'--system-interval','.02','--process-interval','.02','--cgroup-interval','.02','--pss-interval','.02','--zone-interval','.02'])
            finally:timer.join()
        self.assertEqual(code,0);self.assertTrue(json.loads((o/'final_snapshot.json').read_text())['interrupted'])
        for name in ['system','processes','cgroups','pss','zones','vmware','monitor_health']:
            rows=[json.loads(l) for l in (o/(name+'.jsonl')).read_text().splitlines()];self.assertTrue(rows);self.assertTrue(all(x['boot_id']=='fake-boot' for x in rows));self.assertEqual([x['monotonic_ns'] for x in rows],sorted(x['monotonic_ns'] for x in rows))

if __name__=='__main__':unittest.main()
