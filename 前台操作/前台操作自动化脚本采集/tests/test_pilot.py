"""TEST_ONLY unit fixtures. No desktop, real Krita, workload or PILOT is run."""
import contextlib
import copy
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch,Mock
import zipfile
from PIL import Image
from oomlab_krita_collect.common import GUI,save,load,digest
from oomlab_krita_collect.config import read
from oomlab_krita_collect import metrics,cli
from oomlab_krita_collect.pilot_assets import inventory,script_contract
from oomlab_krita_collect.phases import observe,validate
from oomlab_krita_collect.engine import recipe,sustained_pressure,enforce
from oomlab_krita_collect.validation import iter_samples,verify_pilot_events,report
from oomlab_krita_collect.pilot_report import gb
from test_collect import kernel

spec=importlib.util.spec_from_file_location('auto_test',GUI/'scripts/krita_auto.py');auto=importlib.util.module_from_spec(spec);spec.loader.exec_module(auto)


def config():return load(Path(__file__).parent/'fixtures/collection.pilot.json')


def structured_events():
    events=[]
    for n in range(1,9):
        a=n*1_000_000_000;b=a+100_000_000
        for kind,stamp,extra in [('phase_start',a,dict(start_timestamp_ns=a,status='RUNNING')),('phase_end',b,dict(start_timestamp_ns=a,end_timestamp_ns=b,status='PASS',duration_ms=100,error_message=None))]:
            value=dict(schema_version=1,kind=kind,phase=n,phase_name=str(n),monotonic_ns=stamp,wall_time_ns=stamp+10**18,**extra)
            events.append(observe('@@OOM_EVENT '+json.dumps(value),stamp+1,stamp+10**18+1))
    return events


class ConfigTests(unittest.TestCase):
    def test_pilot_schema_and_actual_source_design(self):
        c=read(Path(__file__).parent/'fixtures/collection.pilot.json');self.assertEqual(c['interval_s'],.05)
        self.assertEqual(script_contract(),dict(import_count=45,hold_duration_s=1800));self.assertIsNone(c['asset']['sha256'])
    def test_no_count_or_duration_override(self):
        with tempfile.TemporaryDirectory() as t:
            c=config();c['pilot']['import_count']=40;p=Path(t)/'config.json';save(p,c)
            with self.assertRaises(ValueError):read(p)
    def test_safety_reserves_not_relaxed(self):
        with tempfile.TemporaryDirectory() as t:
            for key in ('min_available_bytes','min_swap_free_bytes'):
                c=config();c['safety'][key]-=1;p=Path(t)/'config.json';save(p,c)
                with self.assertRaises(ValueError):read(p)
    def test_wrong_interval_mode_or_missing_deadline(self):
        with tempfile.TemporaryDirectory() as t:
            for key in ('interval','mode','deadline'):
                c=config()
                if key=='interval':c['interval_s']=.1
                elif key=='mode':c['mode']='formal'
                else:del c['automation']['import_timeout_s']
                p=Path(t)/'config.json';save(p,c)
                with self.assertRaises(ValueError):read(p)
    def test_pilot_rejects_resume_background_smoke_and_repeats_before_preflight(self):
        base=['collect','--config',str(Path(__file__).parent/'fixtures/collection.pilot.json'),'--results','/tmp/TEST_ONLY-unused']
        for extra in (['--rounds','10'],['--resume-session','/tmp/anything'],['--operation','xz'],['--smoke'],['--target-valid-rounds','10']):
            with patch.object(cli,'check') as check,contextlib.redirect_stderr(io.StringIO()):self.assertEqual(cli.main(base+extra),2);check.assert_not_called()
    def test_recipe_uses_one_existing_framework_and_own_control_paths(self):
        cmd=recipe('krita',config())['command'];self.assertIn('{run_root}/stop-request.json',cmd);self.assertIn('--assets-manifest',cmd)
        self.assertFalse(any('memshift' in arg for arg in cmd))
    def test_dynamic_or_ambiguous_design_is_not_executed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source.py';p.write_text('total_layers=__import__("os").abort()\nkeep_duration_s=1800')
            with self.assertRaises(ValueError):script_contract(p)
            p.write_text('total_layers=45\ntotal_layers=46\nkeep_duration_s=1800')
            with self.assertRaises(ValueError):script_contract(p)


class AssetTests(unittest.TestCase):
    def fixture(self,root,count=45):
        c=config();c['asset'].update(path=str(root/'TEST_ONLY.ora'),width=3,height=2);c['pilot']['layers_dir']=str(root/'layers');(root/'layers').mkdir()
        with zipfile.ZipFile(c['asset']['path'],'w') as z:
            z.writestr('mimetype','image/openraster');z.writestr('stack.xml','<image w="3" h="2"><stack><layer src="data/a.png"/></stack></image>');z.writestr('data/a.png',b'TEST_ONLY CRC member')
        for n in range(count):Image.new('RGBA',(3,2)).save(root/'layers'/f'layer_{n:03d}.png')
        return c
    def test_readonly_complete_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);first=inventory(c);self.assertEqual(first,inventory(c));self.assertEqual(first['png_count'],45)
            self.assertEqual(first['png_files'][0]['color_mode'],'RGBA');self.assertTrue(first['ora']['zip_crc_verified'])
            self.assertEqual(first['png_files'][0]['sha256'],digest(root/'layers/layer_000.png'))
    def test_count_mismatch_fails_without_generating_assets(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root,44)
            with self.assertRaisesRegex(ValueError,'44'):inventory(c)
            self.assertEqual(len(list((root/'layers').iterdir())),44)
    def test_corrupt_png_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);(root/'layers/layer_000.png').write_bytes(b'broken')
            with self.assertRaises((OSError,ValueError)):inventory(c)
    def test_wrong_dimensions_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);Image.new('RGB',(4,2)).save(root/'layers/layer_000.png')
            with self.assertRaisesRegex(ValueError,'dimensions'):inventory(c)
    def test_ora_full_zip_crc_verification(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);p=Path(c['asset']['path']);p.write_bytes(p.read_bytes().replace(b'TEST_ONLY CRC member',b'TEST_ONLY crc member'))
            with self.assertRaises((ValueError,zipfile.BadZipFile)):inventory(c)
    def test_changed_png_fingerprint_is_detected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=self.fixture(root);a=inventory(c);Image.new('RGBA',(3,2),(255,0,0,255)).save(root/'layers/layer_000.png');self.assertNotEqual(a,inventory(c))


class MetricTests(unittest.TestCase):
    def test_additional_stat_and_global_fields(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);kernel(root/'cg',root/'proc');(root/'proc/meminfo').write_text('MemTotal: 200 kB\nMemAvailable: 100 kB\nSwapTotal: 20 kB\nSwapFree: 10 kB\n');(root/'proc/vmstat').write_text('pgfault 30\npgmajfault 2\n')
            a=metrics.snapshot(root/'cg',time.monotonic_ns(),proc=root/'proc');self.assertEqual(a['mem_total_bytes'],204800);self.assertEqual(a['vmstat']['pgmajfault'],2);self.assertEqual(a['stat_file_writeback'],123)
            (root/'cg/memory.stat').write_text('anon 12\n');self.assertIsNone(metrics.snapshot(root/'cg',0,proc=root/'proc')['stat_file_mapped'])
    def test_process_metrics_on_real_test_process_not_krita(self):
        with tempfile.TemporaryDirectory() as t:
            pid=os.getpid();info=auto.identity(pid);p=Path(t)/'record.json';save(p,info)
            cg=info['cgroup'][3:];a=metrics.process_sample(p,cg,time.monotonic_ns());a['monotonic_ns']=time.monotonic_ns()-1_000_000
            b=metrics.process_sample(p,cg,time.monotonic_ns(),a)
            self.assertEqual(b['krita_pid'],pid);self.assertGreater(b['krita_vm_rss_bytes'],0);self.assertIsNotNone(b['krita_cpu_percent'])
    def test_process_wrong_starttime_ppid_or_cgroup_aborts(self):
        with tempfile.TemporaryDirectory() as t:
            info=auto.identity(os.getpid());p=Path(t)/'record.json';save(p,info)
            with self.assertRaisesRegex(RuntimeError,'escaped'):metrics.process_sample(p,'/foreign',time.monotonic_ns())
            for key in ('starttime','ppid'):
                bad=dict(info);bad[key]+=1;save(p,bad)
                with self.assertRaisesRegex(RuntimeError,'identity'):metrics.process_sample(p,info['cgroup'][3:],time.monotonic_ns())
    def test_no_record_means_null_process_fields(self):
        self.assertTrue(all(v is None for v in metrics.process_sample('/tmp/TEST_ONLY-no-record-unique','/unused',0).values()))
    def test_csv_preserves_state_and_fractional_cpu_time(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'samples.csv'
            with p.open('w',newline='') as f:
                w=csv.DictWriter(f,['scope','classification','krita_state','krita_cpu_percent','krita_elapsed_s','sample_index']);w.writeheader();w.writerow(dict(scope='krita',classification='TEST_ONLY',krita_state='S',krita_cpu_percent=.25,krita_elapsed_s=1.75,sample_index=0))
            a=list(iter_samples(t))[0];self.assertEqual(a['krita_state'],'S');self.assertEqual(a['krita_cpu_percent'],.25)
    def test_decimal_gb(self):self.assertEqual(gb(1_000_000_000),'1.000000 GB');self.assertEqual(gb(None),'unavailable')
    def test_sustained_pressure_and_recovery(self):
        c=config();since={};row=dict(global_psi_full_avg10=20,monotonic_ns=0)
        sustained_pressure(row,c,since,'krita');row['monotonic_ns']=4_000_000_000;sustained_pressure(row,c,since,'krita')
        row['monotonic_ns']=5_000_000_000
        with self.assertRaisesRegex(RuntimeError,'sustained'):sustained_pressure(row,c,since,'krita')
        row['global_psi_full_avg10']=0;sustained_pressure(row,c,since,'krita');self.assertFalse(since)
    def test_minimum_memory_and_swap_stop(self):
        c=config();row=dict(freeze_requested=0,frozen=0,memory_current=1,memory_peak=1,mem_available_bytes=2**34,swap_free_bytes=2**34,global_psi_full_avg10=0)
        for key in ('mem_available_bytes','swap_free_bytes'):
            bad=dict(row);bad[key]=0
            with self.assertRaisesRegex(RuntimeError,key):enforce(bad,c['safety'])


class ProtocolTests(unittest.TestCase):
    def test_eight_paired_stages(self):
        a=structured_events();self.assertTrue(validate(a,structured=True));self.assertEqual(a[0]['received_monotonic_ns'],1_000_000_001)
    def test_missing_reordered_or_failed_end_rejected(self):
        a=structured_events();self.assertFalse(validate(a[:-1],structured=True));a[1]['status']='FAILED';self.assertFalse(validate(a,structured=True))
        a=structured_events();a[1],a[2]=a[2],a[1];self.assertFalse(validate(a,structured=True))
    def test_legacy_markers_alone_do_not_validate_pilot(self):self.assertFalse(validate([observe(f'[{n}/8]',n,n) for n in range(1,9)],structured=True))
    def test_malformed_or_future_protocol_is_error(self):
        self.assertTrue(observe('@@OOM_EVENT broken',1,1)['error']);self.assertTrue(observe('@@OOM_EVENT {"schema_version":1,"monotonic_ns":20}',1,1)['error'])
    def test_hold_duration_and_layer_completion_required(self):
        names=['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE','LAYER_IMPORT_START','LAYER_IMPORT_DONE','HOLD_START','HOLD_DONE','DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','KRITA_EXIT']
        events=[dict(kind=n,monotonic_ns=i*1800*10**9) for i,n in enumerate(names)]
        events[4]['import_count']=45;events[5]['verified_total_layers']=46;events[6]['duration_s']=1800;events[-1]['returncode']=0
        verify_pilot_events(events,script_contract());events[7]['monotonic_ns']=events[6]['monotonic_ns']+1
        with self.assertRaises(ValueError):verify_pilot_events(events,script_contract())
    def test_pilot_session_report_never_formal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);save(root/'session.json',dict(classification='PILOT',operation='krita'));a=report(root);self.assertEqual(a['status'],'NOT_RUN');self.assertFalse(a['formal_eligible'])


class AutomationTests(unittest.TestCase):
    def setUp(self):self.old=copy.deepcopy(auto.CTX);auto.CTX.update(process=None,control=None,settings=dict(auto.DEFAULTS),record=None)
    def tearDown(self):auto.CTX.clear();auto.CTX.update(self.old)
    def test_command_nonzero_is_failure(self):
        with patch.object(auto.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','failed')):
            with self.assertRaisesRegex(RuntimeError,'failed'):auto.run(['wmctrl','-lpG'])
    def test_stop_request_prevents_input(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'stop.json';save(p,dict(reason='low memory'));auto.CTX['control']=str(p)
            with patch.object(auto.subprocess,'run') as call:
                with self.assertRaises(auto.StopRequested):auto.run(['xdotool','key','Return'])
                call.assert_not_called()
    def test_focus_foreign_pid_stops_before_key(self):
        auto.CTX['pid']=os.getpid()
        with patch.object(auto,'owned'),patch.object(auto.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,'123',''),subprocess.CompletedProcess([],0,'_NET_WM_PID(CARDINAL) = 999999','')]) as call:
            with self.assertRaisesRegex(RuntimeError,'焦点'):auto.run(['xdotool','key','Return'])
            self.assertEqual(call.call_count,2)
    def test_layers_must_be_unique_and_actual(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=45)])):self.assertFalse(auto.expected_layers(46))
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=46)])):self.assertTrue(auto.expected_layers(46))
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=47)])):
            with self.assertRaises(RuntimeError):auto.expected_layers(46)
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=46),dict(row_count=46)])):
            with self.assertRaises(auto.GuiPending):auto.layer_count()
    def test_discard_is_unique_correct_document_and_not_save(self):
        state=dict(dialogs=[dict(text=['Save changes to "blank_8000x8000"?'],buttons=[dict(name='Save',box=[1,2,30,20]),dict(name="Don't Save",box=[40,2,30,20])])])
        self.assertEqual(auto.discard_target(state,'blank_8000x8000.ora'),[40,2,30,20]);state['dialogs'][0]['buttons'].append(dict(name='Discard',box=[80,2,30,20]))
        with self.assertRaises(auto.GuiPending):auto.discard_target(state,'blank_8000x8000.ora')
        with self.assertRaises(auto.GuiPending):auto.discard_target(state,'foreign.ora')
    def test_old_discard_geometry_not_clicked(self):
        auto.CTX.update(asset='/tmp/TEST_ONLY.ora',wid='0x1',settings=dict(auto.DEFAULTS))
        with patch.object(auto,'focus'),patch.object(auto,'run'),patch.object(auto,'wait_until',return_value=[1,2,30,20]),patch.object(auto,'probe_state'),patch.object(auto,'discard_target',return_value=[2,2,30,20]),patch.object(auto,'click') as click:
            with self.assertRaisesRegex(RuntimeError,'几何'):auto.close_document()
            click.assert_not_called()
    def test_phase_failure_has_end_status_and_duration(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                with auto.phase(3,'test'):raise RuntimeError('fail')
        events=[json.loads(line[12:]) for line in output.getvalue().splitlines() if line.startswith('@@OOM_EVENT ')]
        self.assertEqual(events[-1]['status'],'FAILED');self.assertIn('end_timestamp_ns',events[-1]);self.assertGreaterEqual(events[-1]['duration_ms'],0)
    def test_startup_identity_does_not_use_layer_ocr(self):
        source=(GUI/'scripts/krita_auto.py').read_text();startup=source[source.index("with phase(1,"):source.index("with phase(2,")]
        startup+=source[source.index('def start_krita('):source.index('def quit_krita(')]
        self.assertNotIn('layer_count(',startup);self.assertNotIn('pytesseract',source);self.assertIn('libqxcb.so',startup)
        self.assertIn('expected_layers(1+total_layers)',source)


class SafetyAndEvidenceTests(unittest.TestCase):
    def test_stop_request_precedes_grace_sampling_and_preserves_csv(self):
        from oomlab_krita_collect.engine import cooperative_stop
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);work=root/'krita';work.mkdir();(work/'automation.log').write_text('[5/8] import\n');p=root/'samples.csv'
            with p.open('w',newline='') as f:w=csv.DictWriter(f,metrics.FIELDS);w.writeheader();w.writerow(dict(sample_index=0,classification='TEST_ONLY'))
            prefix=p.read_bytes();c=config();c['pilot']['graceful_stop_timeout_s']=.05
            def sample(writer,check_safety=True):
                self.assertFalse(check_safety);self.assertEqual(load(root/'stop-request.json')['phase'],5)
                writer.writerow(dict(sample_index=1,classification='TEST_ONLY'));save(work/'finished.json',dict(classification='TEST_ONLY'))
            result=cooperative_stop(root,{'krita':Mock(run=work)},c,'TEST_ONLY safety',{},sample)
            self.assertTrue(p.read_bytes().startswith(prefix));self.assertTrue(result['cooperative_worker_completed'])
            with p.open() as f:self.assertEqual(len(list(csv.DictReader(f))),2)
    def test_grace_timeout_does_not_fabricate_completion(self):
        from oomlab_krita_collect.engine import cooperative_stop
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);work=root/'krita';work.mkdir();(root/'samples.csv').write_text('TEST_ONLY prefix\n');c=config();c['pilot']['graceful_stop_timeout_s']=.001
            result=cooperative_stop(root,{'krita':Mock(run=work)},c,'TEST_ONLY',{},lambda writer,**kwargs:None)
            self.assertFalse(result['cooperative_worker_completed']);self.assertTrue((root/'stop-request.json').is_file())
    def test_report_renders_partial_failure_without_claiming_run(self):
        from oomlab_krita_collect.pilot_report import write_report
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);save(root/'metadata.json',dict(classification='TEST_ONLY',error='TEST_ONLY aborted',source={}));save(root/'environment.json',dict(classification='TEST_ONLY'))
            with (root/'samples.csv').open('w',newline='') as f:csv.DictWriter(f,metrics.FIELDS).writeheader()
            (root/'phase-events.jsonl').write_text('');write_report(root,dict(status='PILOT_INVALID',errors=['TEST_ONLY fixture']))
            report_text=(root/'report.md').read_text();self.assertIn('NOT_RUN',report_text);self.assertIn('unavailable',report_text);self.assertIn('PILOT_INVALID',report_text)
    def test_unit_rejects_descendant_outside_owned_cgroup(self):
        from oomlab_krita_collect.units import Unit,process_cgroup
        from oomlab_krita_collect.common import fresh
        with tempfile.TemporaryDirectory() as t:
            u=Unit('oomcollect-'+'a'*32+'-krita.service',t,'oomcollect-'+'a'*32+'.slice');u.pid=os.getpid();u.cg='/TEST_ONLY-foreign'
            with self.assertRaisesRegex(RuntimeError,'escaped'):u.check_descendants()
    def test_accessibility_filters_exact_process_and_queries_real_table_interface(self):
        import types,sys
        spec=importlib.util.spec_from_file_location('access_test',GUI/'scripts/krita_accessibility.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        class Node:
            bus_name='test';path=None
            def __init__(self,name,role,children=()):self.name=name;self.role=role;self.children=children
            def __iter__(self):return iter(self.children)
            @property
            def childCount(self):return len(self.children)
            def getChildAtIndex(self,index):return self.children[index]
            def getRoleName(self):return 'application' if self.role==0 else 'frame' if self.role==7 else 'tree'
            def getRole(self):return self.role
            def getState(self):return types.SimpleNamespace(contains=lambda value:True)
            def getRelationSet(self):return []
            def queryTable(self):return types.SimpleNamespace(nRows=46)
            def get_process_id(self):return os.getpid()
        table=Node('Layers',3);app=Node('Krita',0,[Node('Krita',7,[table])]);desktop=Node('Desktop',7,[app]);api=types.SimpleNamespace(ROLE_APPLICATION=0,Registry=types.SimpleNamespace(getDesktop=lambda n:desktop),STATE_SHOWING=1,ROLE_DIALOG=1,ROLE_FILE_CHOOSER=2,ROLE_ALERT=8,ROLE_PUSH_BUTTON=9,ROLE_TREE=3,ROLE_TREE_TABLE=4,ROLE_TABLE=5,RELATION_LABELLED_BY=6)
        with patch.dict(sys.modules,pyatspi=api):
            state=helper.snapshot(os.getpid());self.assertEqual(state['layer_views'][0]['row_count'],46)
            with self.assertRaisesRegex(RuntimeError,'PID'):helper.snapshot(os.getpid()+1)


class PrelaunchTests(unittest.TestCase):
    def test_asset_race_preserves_invalid_run_without_starting_units(self):
        from oomlab_krita_collect.engine import run_one
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=config();c['asset']['path']=str(root/'missing.ora')
            with patch('oomlab_krita_collect.pilot_assets.inventory',return_value=dict(schema_version=1,ora={},png_files=[])),patch('oomlab_krita_collect.engine.Unit') as unit,patch('oomlab_krita_collect.common.source_identity',return_value={}):
                run,result=run_one(root,c,{'krita':recipe('krita',c)},dict(source={},assets_manifest={}))
                unit.assert_not_called()
            self.assertFalse(result['valid']);self.assertFalse(result['formal_eligible']);self.assertTrue((run/'report.md').exists());self.assertTrue((run/'manifest.sha256').exists())
            self.assertIn('assets changed after preflight',load(run/'metadata.json')['error'])
    def test_missing_pilot_process_proof_cannot_be_validated(self):
        from oomlab_krita_collect.validation import verify_pilot_process
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(FileNotFoundError):verify_pilot_process(t,{})
    def test_complete_legacy_log_does_not_satisfy_pilot_events(self):
        with self.assertRaisesRegex(ValueError,'events'):verify_pilot_events([observe(f'[{i}/8]',i,i) for i in range(1,9)],script_contract())
    def test_grace_deadline_prevents_late_input(self):
        prior=dict(auto.CTX)
        try:
            auto.CTX.update(control=None,shutdown_deadline=time.monotonic()-1)
            with patch.object(auto.subprocess,'run') as call:
                with self.assertRaises(TimeoutError):auto.run(['xdotool','key','Return'])
                call.assert_not_called()
        finally:auto.CTX.clear();auto.CTX.update(prior)


if __name__=='__main__':unittest.main()
