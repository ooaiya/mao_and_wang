from pathlib import Path
"""Timed capture contracts and failures, without a real desktop."""
import importlib.util
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from oomlab_krita_collect.common import GUI
from oomlab_krita_collect.config import read
from oomlab_krita_collect.pilot_assets import script_contract
from oomlab_krita_collect.validation import verify_pilot_events
from oomlab_krita_collect.engine import cooldown_usage
from oomlab_krita_collect.worker import output_lines

spec=importlib.util.spec_from_file_location('timed_auto',GUI/'scripts/krita_auto.py')
auto=importlib.util.module_from_spec(spec);spec.loader.exec_module(auto)

def fixture():
    c=read(Path(__file__).parent/'fixtures/collection.timed-9000.json');contract=script_contract(config=c)
    names=['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE','LAYER_IMPORT_START',
           'LAYER_IMPORT_SUBMITTED','CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE','DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','KRITA_EXIT']
    events=[dict(kind=n,monotonic_ns=(i+1)*1_000_000_000) for i,n in enumerate(names)]
    origin=events[5]['monotonic_ns'];duration=contract['capture_window_s']
    events[4]['import_count']=45;events[5].update(import_count=45,verification='file_dialog_submission')
    for i in [6,7]:events[i].update(origin_monotonic_ns=origin,duration_s=duration)
    for i in range(7,11):events[i]['monotonic_ns']=origin+int(duration*1e9)+(i-7)*1_000_000_000
    events[7]['import_verified']=False;events[-1]['returncode']=0
    return contract,events

class TimedTests(unittest.TestCase):
    def test_localized_no_shortcut_is_discard_and_yes_is_not(self):
        state=dict(dialogs=[dict(text=["The document 'blank_9000x9000.ora' has been modified. Do you want to save it?"],buttons=[dict(name='否(N)',box=[1,2,80,31]),dict(name='是(Y)',box=[90,2,80,31]),dict(name='取消(C)',box=[180,2,80,31])])])
        self.assertEqual(auto.discard_target(state,'blank_9000x9000.ora'),[1,2,80,31])
        with self.assertRaises(auto.GuiPending):auto.discard_target(state,'other.ora')
    def test_small_normal_helper_window_is_not_the_main_window(self):
        with patch.object(auto,'find_window',return_value=dict(id='0x1',width=640,height=537)):self.assertIsNone(auto.main_window())
        with patch.object(auto,'find_window',return_value=dict(id='0x2',width=1868,height=970)):self.assertEqual(auto.main_window()['id'],'0x2')
    def test_layout_requires_the_owned_main_window(self):
        old=auto.CTX.copy();auto.CTX.update(wid='0x123',settings=dict(auto.DEFAULTS))
        try:
            w=dict(id='0x123',width=1868,height=970)
            with patch.object(auto,'focus'),patch.object(auto,'find_window',return_value=w),patch.object(auto,'emit'),patch.object(auto,'wait_until',side_effect=lambda fn,*a:fn()):
                self.assertEqual(auto.prepare_window(),w)
                w['id']='0x999';self.assertIsNone(auto.prepare_window())
        finally:auto.CTX.clear();auto.CTX.update(old)
    def test_layout_does_not_claim_maximization(self):
        old=auto.CTX.copy();auto.CTX.update(wid='0x123',settings=dict(auto.DEFAULTS))
        try:
            with patch.object(auto,'focus'),patch.object(auto,'find_window',return_value=dict(id='0x123',width=1868,height=970)),patch.object(auto,'emit') as emit,patch.object(auto,'wait_until',side_effect=lambda fn,*a:fn()):auto.prepare_window()
            self.assertIn('maximization not required',emit.call_args.kwargs['method'])
        finally:auto.CTX.clear();auto.CTX.update(old)
    def test_failed_parent_cannot_be_hidden_by_descendant_holding_stdout(self):
        code='import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(3)"]);print("parent done",flush=True);sys.exit(2)'
        p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,start_new_session=True)
        try:
            start=time.monotonic();lines=list(output_lines(p))
            self.assertLess(time.monotonic()-start,2);self.assertIn('parent done\n',lines);self.assertEqual(p.wait(),2)
        finally:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            p.stdout.close()
    def test_cooldown_distinguishes_clean_cache_from_retained_working_memory(self):
        row=dict(memory_current=5000,stat_file=4800,stat_shmem=100,stat_file_dirty=50,stat_file_writeback=25,swap_current=30)
        self.assertEqual(cooldown_usage(row),5000)
        self.assertEqual(cooldown_usage(row,True),405)
        row['stat_anon']=4000;row['stat_file']=500
        self.assertGreater(cooldown_usage(row,True),4000)
    def test_window_covers_reference_import_and_observation(self):
        c=read(Path(__file__).parent/'fixtures/collection.timed-9000.json');a=c['automation']
        self.assertEqual((c['asset']['width'],c['asset']['height']),(9000,9000))
        self.assertEqual(a['capture_window_s'],1350)
        self.assertGreaterEqual(a['capture_window_s'],sum(a['timing_basis'][k] for k in ['import_duration_s','post_import_observation_s']))
    def test_timed_capture_valid_without_layer_or_hold_success(self):
        contract,events=fixture();verify_pilot_events(events,contract)
        self.assertNotIn('hold_duration_s',contract)
    def test_early_window_or_wrong_origin_cannot_pass(self):
        for mode in ['early','origin']:
            contract,events=fixture()
            if mode=='early':events[7]['monotonic_ns']=events[5]['monotonic_ns']+1
            else:events[7]['origin_monotonic_ns']+=1
            with self.assertRaises(ValueError):verify_pilot_events(events,contract)
    def test_elapsed_time_cannot_be_reported_as_verified_layers(self):
        contract,events=fixture();events[7]['import_verified']=True
        with self.assertRaisesRegex(ValueError,'cannot verify'):verify_pilot_events(events,contract)
        contract,events=fixture();events.insert(7,dict(kind='LAYER_IMPORT_DONE',monotonic_ns=events[6]['monotonic_ns']))
        with self.assertRaises(ValueError):verify_pilot_events(events,contract)
    def test_dead_process_aborts_timed_capture(self):
        with patch.object(auto,'emit'),patch.object(auto,'check_stop'),patch.object(auto,'owned',side_effect=RuntimeError('Krita exited')):
            with self.assertRaisesRegex(RuntimeError,'exited'):auto.capture_window(0,1350)
    def test_timer_never_calls_accessibility_or_claims_import_completion(self):
        with patch.object(auto,'check_stop'),patch.object(auto,'owned'),patch.object(auto,'emit') as emit,patch.object(auto,'probe_state') as probe,patch.object(auto.time,'monotonic_ns',side_effect=[1350_000_000_001,1350_000_000_002]):
            auto.capture_window(0,1350)
            probe.assert_not_called();self.assertFalse(emit.call_args.kwargs['import_verified'])
    def test_dialog_clears_remembered_path_before_typing(self):
        with patch.object(auto,'focus'),patch.object(auto,'run') as run,patch.object(auto.time,'sleep'):
            auto.submit_paths(dict(id='0x123'),['/tmp/layer_001.png','/tmp/layer_002.png'])
        commands=[c.args[0] for c in run.call_args_list]
        self.assertEqual(commands[0][-1],'ctrl+l');self.assertEqual(commands[1][-1],'ctrl+a')
        self.assertEqual(commands[2][-1],'"/tmp/layer_001.png" "/tmp/layer_002.png"')
    def test_ambiguous_dialog_path_rejected_before_input(self):
        with patch.object(auto,'focus') as focus:
            with self.assertRaises(ValueError):auto.submit_paths(dict(id='0x123'),['/tmp/a"b.png'])
            focus.assert_not_called()

if __name__=='__main__':unittest.main()
