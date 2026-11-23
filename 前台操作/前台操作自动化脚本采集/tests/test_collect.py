"""TEST_ONLY: fake kernel files, synthetic ORA, and tiny sleep subprocesses."""
import argparse
import contextlib
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from oomlab_krita_collect import metrics
from oomlab_krita_collect.common import save,load,fresh,seal,verify_seal,positive,ROOT,GUI,BACKGROUND,digest
from oomlab_krita_collect.asset import inspect,pinned
from oomlab_krita_collect.phases import observe,validate as validate_phases
from oomlab_krita_collect.units import Unit,process_cgroup
from oomlab_krita_collect.validation import validate_run,report
from oomlab_krita_collect.config import read,SAFETY
from oomlab_krita_collect.engine import run_one,enforce


def config(root):
    safety={k:0 for k in SAFETY}
    safety.update(max_sample_gap_s=1,max_cgroup_bytes=10**12,max_global_full_avg10=100,
                  cooldown_cgroup_bytes=10**10,cooldown_min_available_bytes=0,cooldown_max_full_avg10=100,
                  cooldown_timeout_s=1,cooldown_stable_s=.01,run_timeout_s=5)
    return dict(schema_version=1,interval_s=.01,asset=dict(path=str(root/'fixture.ora'),sha256='a'*64,width=4096,height=4096,layers=208),display_size=[2558,1200],safety=safety,acceptance={op:dict(min_peak_bytes=0,max_peak_bytes=10**11) for op in ('krita','xz','table','array_processing')},
                forbidden_processes=['krita','memshiftd','xz'],forbidden_units=['memshift','freezer'],forbidden_sockets=['/tmp/memshift-test-only-never.sock'])


def kernel(cg,proc):
    cg.mkdir(parents=True,exist_ok=True);(proc/'pressure').mkdir(parents=True,exist_ok=True)
    (cg/'memory.current').write_text('1000000');(cg/'memory.peak').write_text('2000000');(cg/'memory.swap.current').write_text('0')
    (cg/'memory.events').write_text(''.join(k+' 0\n' for k in metrics.EVENTS));(cg/'memory.events.local').write_text((cg/'memory.events').read_text())
    (cg/'memory.stat').write_text(''.join(k+' 123\n' for k in metrics.STATS));(cg/'cgroup.procs').write_text('');(cg/'cgroup.events').write_text('populated 1\nfrozen 0\n');(cg/'cgroup.freeze').write_text('0')
    pressure='some avg10=0.00 avg60=0.00 avg300=0.00 total=20\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=10\n'
    (cg/'memory.pressure').write_text(pressure);(proc/'pressure/memory').write_text(pressure)
    (proc/'meminfo').write_text('MemAvailable: 100000000 kB\nSwapFree: 10000000 kB\n')
    (proc/'vmstat').write_text('pgscan_kswapd 1\npgsteal_kswapd 1\npswpin 0\npswpout 0\noom_kill 0\n')


class MetricsTests(unittest.TestCase):
    def test_missing_metrics_are_null_not_zero(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);kernel(root/'cg',root/'proc');(root/'cg/memory.events.local').unlink();(root/'cg/memory.swap.current').unlink()
            row=metrics.snapshot(root/'cg',time.monotonic_ns(),proc=root/'proc')
            self.assertIsNone(row['local_event_oom']);self.assertIsNone(row['swap_current']);self.assertFalse(row['capabilities']['memory.events.local'])
    def test_psi_and_clock_domains(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);kernel(root/'cg',root/'proc');start=time.monotonic_ns()-1000000
            a=metrics.snapshot(root/'cg',start,proc=root/'proc');b=metrics.snapshot(root/'cg',start,proc=root/'proc')
            self.assertGreater(b['monotonic_ns'],a['monotonic_ns']);self.assertEqual(a['relative_s'],(a['monotonic_ns']-start)/1e9)
            self.assertGreater(a['wall_time_ns'],a['monotonic_ns']);self.assertEqual(a['cgroup_psi_full_total'],10)
            self.assertEqual(metrics.deltas(a,b)['global_psi_some_total'],0)
    def test_counter_rollback_rejected(self):
        with self.assertRaises(ValueError):metrics.deltas({'event_oom':2},{'event_oom':1})
        with self.assertRaises(ValueError):metrics.deltas({'vmstat':{'pswpin':2}},{'vmstat':{'pswpin':1}})
        self.assertIsNone(metrics.deltas({'event_oom':None},{'event_oom':0})['event_oom'])
    def test_bad_pressure_or_duplicate_fields(self):
        with self.assertRaises(ValueError):metrics.psi('some avg10=nan total=10')
        with self.assertRaises(ValueError):metrics.pairs('oom 1\noom 2')
        self.assertIsNone(metrics.psi('some avg10=1')['full_total'])
    def test_nonfinite_interval_and_explicit_safety(self):
        for n in ['nan','inf',-1,0,True]:
            with self.assertRaises(ValueError):positive(n)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=config(root);p=root/'c.json';save(p,c);self.assertEqual(read(p)['asset']['layers'],208)
            c['safety']['min_available_bytes']=None;save(p,c)
            with self.assertRaises(ValueError):read(p)
    def test_safety_limit_does_not_write_kernel_controls(self):
        with self.assertRaises(RuntimeError):enforce(dict(memory_current=100,memory_peak=100),{'max_cgroup_bytes':100})


class ArtifactTests(unittest.TestCase):
    def test_readonly_ora_metadata_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'TEST_ONLY.ora'
            with zipfile.ZipFile(p,'w') as z:z.writestr('mimetype','image/openraster');z.writestr('stack.xml','<image w="2" h="3"><stack><layer src="one.png"/></stack></image>')
            stamp=p.stat().st_mtime_ns;a=inspect(p);self.assertEqual((a['width'],a['height'],a['layers']),(2,3,1));self.assertEqual(p.stat().st_mtime_ns,stamp)
            self.assertEqual(pinned(dict(path=str(p),sha256=a['sha256'],width=2,height=3,layers=1))['sha256'],a['sha256'])
            with p.open('ab') as f:f.write(b'changed')
            with self.assertRaises(ValueError):pinned(dict(path=str(p),sha256=a['sha256'],width=2,height=3,layers=1))
    def test_eight_phases_and_known_error_zero_exit_are_distinct(self):
        events=[observe(f'[{i}/8] stage',i,i+100) for i in range(1,9)]
        self.assertTrue(validate_phases(events));self.assertFalse(validate_phases(events[:-1]))
        self.assertFalse(validate_phases(events+[observe('[错误] failed',10,110)]))
        self.assertFalse(validate_phases([events[1],events[0],*events[2:]]))
        self.assertTrue(observe('[cmd] xdotool windowsize None',1,1)['error'])
        self.assertTrue(observe('[警告] 素材加载超时，继续执行',1,1)['error'])
    def test_immutable_directory_and_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            p=fresh(Path(t)/'run');save(p/'evidence.json',dict(classification='TEST_ONLY'));seal(p);verify_seal(p)
            with self.assertRaises(FileExistsError):fresh(p)
            (p/'evidence.json').write_text('tamper')
            with self.assertRaises(ValueError):verify_seal(p)
    def test_symlink_manifest_escape_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=fresh(root/'run');(root/'secret').write_text('TEST_ONLY');(p/'link').symlink_to(root/'secret');seal(p)
            with self.assertRaises(ValueError):verify_seal(p)
    def test_no_legacy_import_and_protected_script_blobs(self):
        self.assertFalse(any(k.startswith('oomlab_krita_gui') for k in sys.modules))
        from oomlab_krita_collect.pilot_assets import script_contract
        self.assertEqual(script_contract(),dict(import_count=45,hold_duration_s=1800))
        expected={'pick_coords.py':'9aca211e3c917d4990eeaa3b4fda28b099fc701a'}
        for name,blob in expected.items():
            p=GUI/'scripts'/name
            self.assertEqual(subprocess.check_output(['git','hash-object',str(p)],text=True).strip(),blob)


class OwnershipTests(unittest.TestCase):
    def test_process_cgroup_exact_v2_path(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'123';p.mkdir();(p/'cgroup').write_text('0::/user.slice/owned.service\n')
            self.assertEqual(process_cgroup(123,t),'/user.slice/owned.service')
            (p/'cgroup').write_text('0::/../../foreign\n')
            with self.assertRaises(ValueError):process_cgroup(123,t)
    def test_unrelated_unit_or_description_cannot_be_cleaned(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):Unit('ssh.service',t,'x.slice')
            u=Unit('oomcollect-'+'a'*32+'-krita.service',t,'oomcollect-'+'a'*32+'.slice')
            with patch.object(u,'show',return_value=dict(Id=u.unit,Description='foreign',Slice=u.slice)),patch('oomlab_krita_collect.units.command') as call:
                with self.assertRaises(RuntimeError):u.stop()
                call.assert_not_called()
    def test_start_only_user_service_no_resource_scheduling(self):
        with tempfile.TemporaryDirectory() as t:
            u=Unit('oomcollect-'+'a'*32+'-krita.service',t,'oomcollect-'+'a'*32+'.slice')
            with patch('oomlab_krita_collect.units.command',return_value=subprocess.CompletedProcess([],0,'','')) as call:u.start()
            args=call.call_args.args[0];self.assertIn('--user',args);self.assertIn('--setenv=QT_QPA_PLATFORM=xcb',args)
            self.assertFalse(any(word in ' '.join(args) for word in ['MemoryMax','MemoryHigh','MemorySwapMax','Nice=','IOWeight','CPUWeight','sudo','cgroup.freeze']))


class EngineTests(unittest.TestCase):
    def exercise(self,base,recipes,incomplete=False):
        import oomlab_krita_collect.engine as engine
        cg=base/'TEST_ONLY-cgroup';proc=base/'TEST_ONLY-proc';kernel(cg,proc);handles=[]
        class FakeUnit:
            def __init__(self,name,run,slice_name):self.unit=name;self.run=Path(run);self.slice=slice_name;self.path=cg/name;self.pid=None
            def start(self,hold=False,**kwargs):
                args=[sys.executable,'-u','-m','oomlab_krita_collect.worker',str(self.run)]+(['--hold'] if hold else [])
                env=dict(os.environ,PYTHONPATH=str(GUI))
                self.child=subprocess.Popen(args,cwd=GUI,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);handles.append(self.child);self.pid=self.child.pid
            def bind(self):kernel(self.path,proc);(self.path/'cgroup.procs').write_text(str(self.pid));return self.path
            def check_members(self):return [dict(pid=self.pid)]
            def stop(self):
                self.child.terminate();self.child.wait(timeout=3)
                if self.path.exists():(self.path/'cgroup.procs').write_text('')
                return dict(ok=True)
        def parent(hold,slice_name):return cg,dict(Id=slice_name,ControlGroup=str(cg))
        def command(args,**kwargs):
            if args[:3]==['systemctl','--user','show']:return subprocess.CompletedProcess(args,0,'Id='+args[3]+'\nControlGroup='+str(cg)+'\n','')
            return subprocess.CompletedProcess(args,0,'','')
        c=config(base);session=fresh(base/'session')
        try:
            with patch.object(engine,'Unit',FakeUnit),patch.object(engine,'parent_identity',side_effect=parent),patch.object(engine,'snapshot',side_effect=lambda p,t,s:metrics.snapshot(p,t,s,proc)),patch('oomlab_krita_collect.common.command',side_effect=command):
                run,result=engine.run_one(session,c,recipes,dict(source=dict(classification='TEST_ONLY')),test_only=True)
            return run,result
        finally:
            for child in handles:
                if child.poll() is None:child.terminate();child.wait(timeout=3)
    def test_real_gated_sleep_through_fake_cgroup_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            run,result=self.exercise(Path(t),{'smoke':dict(command=['/usr/bin/sleep','.2'])})
            self.assertTrue(result['valid'],result);self.assertFalse(result['formal_eligible']);verify_seal(run)
            self.assertTrue(load(run/'metadata.json')['cleanup_ok']);self.assertIn('parent',result['peak_bytes'])
            self.assertTrue({'schema_version','monotonic_ns','wall_time_ns','event_oom_group_kill','cgroup_psi_full_total','global_psi_some_avg10'}<=set(metrics.FIELDS))
    def test_zero_exit_incomplete_gui_markers_is_invalid(self):
        with tempfile.TemporaryDirectory() as t:
            code="import time;print('[1/8] TEST_ONLY',flush=True);time.sleep(.2)"
            run,result=self.exercise(Path(t),{'krita':dict(command=[sys.executable,'-u','-c',code])})
            self.assertFalse(result['valid']);self.assertIn('incomplete/out-of-order/error GUI stages',result['errors'])
    def test_empty_or_incomplete_evidence_is_invalid(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);save(p/'metadata.json',dict(classification='TEST_ONLY'))
            self.assertFalse(validate_run(p)['valid'])
    def test_safety_resume_only_nine_after_first_review(self):
        from oomlab_krita_collect.cli import collect
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=config(root);session=fresh(root/'session');run=fresh(session/('a'*32));save(run/'metadata.json',dict(classification='TEST_ONLY'));save(run/'summary.json',dict(test_only=True))
            save(session/'first-round.json',dict(run_id=run.name,summary_sha256=digest(run/'summary.json')))
            source=dict(classification='TEST_ONLY');spec=dict(command=['TEST_ONLY'])
            save(session/'session.json',dict(operation='krita',classification='FORMAL',config=c,recipe=spec,source=source))
            args=argparse.Namespace(results=str(root),smoke=False,operation='krita',data=None,profile='small',resume_session=str(session),target_valid_rounds=10,approve_first_summary_sha256=digest(run/'summary.json'),rounds=1)
            with patch('oomlab_krita_collect.cli.check',return_value=dict(ok=True,source=source)),patch('oomlab_krita_collect.cli.source_identity',return_value=source),patch('oomlab_krita_collect.cli.recipe',return_value=spec),patch('oomlab_krita_collect.cli.report',return_value=dict(status='VALIDATED',valid_rounds=1)),patch('oomlab_krita_collect.cli.run_one',return_value=(run,dict(valid=True,formal_eligible=True))) as one,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collect(c,args),0);self.assertEqual(one.call_count,9)
            args.approve_first_summary_sha256=None
            with patch('oomlab_krita_collect.cli.check',return_value=dict(ok=True,source=source)),patch('oomlab_krita_collect.cli.source_identity',return_value=source),patch('oomlab_krita_collect.cli.recipe',return_value=spec),patch('oomlab_krita_collect.cli.report',return_value=dict(status='VALIDATED',valid_rounds=1)),patch('oomlab_krita_collect.cli.run_one') as one:
                with self.assertRaises(ValueError):collect(c,args)
                one.assert_not_called()


class SemanticValidationTests(unittest.TestCase):
    exercise=EngineTests.exercise
    def test_corrupt_semantics_stay_invalid_even_with_resealed_files(self):
        with tempfile.TemporaryDirectory() as t:
            run,result=self.exercise(Path(t),{'smoke':dict(command=['/usr/bin/sleep','.2'])})
            self.assertTrue(result['valid'],result)
            samples=(run/'samples.csv').read_text();end=(run/'cgroup-end.json').read_text();meta=(run/'metadata.json').read_text()
            cases=[]
            rows=list(csv.DictReader(io.StringIO(samples)))
            rows[2]['monotonic_ns']=rows[0]['monotonic_ns'];rows[2]['relative_s']=rows[0]['relative_s']
            stream=io.StringIO();writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows);cases.append(('samples.csv',stream.getvalue()))
            changed=json.loads(end);changed['scopes']['parent']['event_oom']=1;cases.append(('cgroup-end.json',json.dumps(changed)))
            changed=json.loads(meta);changed['cleanup_ok']=False;cases.append(('metadata.json',json.dumps(changed)))
            for name,value in cases:
                with self.subTest(name=name):
                    (run/name).write_text(value);seal(run);self.assertFalse(validate_run(run)['valid'])
                    (run/'samples.csv').write_text(samples);(run/'cgroup-end.json').write_text(end);(run/'metadata.json').write_text(meta)
            seal(run);self.assertTrue(validate_run(run)['valid'])



class ReportStatsTests(unittest.TestCase):
    def test_summary_percentiles_and_cv(self):
        from oomlab_krita_collect.validation import stats
        s=stats([90,100,110])
        self.assertEqual(s['median'],100)
        self.assertEqual(s['p95'],109)
        self.assertAlmostEqual(s['cv'],.1)


class RepositoryLayoutTests(unittest.TestCase):
    def test_main_layout_paths_and_source_identity(self):
        from oomlab_krita_collect.common import source_identity
        self.assertEqual(GUI,ROOT/'前台操作/前台操作自动化脚本采集')
        self.assertEqual(BACKGROUND,ROOT/'后台操作')
        for path in (GUI/'scripts/krita_auto.py', GUI/'scripts/pick_coords.py',
                     GUI/'scripts/krita_accessibility.py',
                     BACKGROUND/'oomlab/workloads.py',
                     BACKGROUND/'configs/profiles.json'):
            self.assertTrue(path.is_file(),str(path))
        identity=source_identity()
        branch = subprocess.run(
            ['git', 'symbolic-ref', '--quiet', '--short', 'HEAD'],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertIn(branch.returncode, (0, 1))
        self.assertEqual(identity['git_branch'], branch.stdout.strip())
        self.assertFalse(identity['source_dirty'])
