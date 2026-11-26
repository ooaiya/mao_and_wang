"""Irregular real-observation metric semantics, no GUI or workload started."""
import importlib.util
from pathlib import Path
import unittest
import pandas as pd
spec=importlib.util.spec_from_file_location('real_analysis',Path(__file__).resolve().parents[1]/'tools/real_app_candidates/analyze.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class MetricsTests(unittest.TestCase):
    def test_loading_and_close_excluded(self):
        df=pd.DataFrame({'monotonic_ns':[0,10**9,2*10**9,4*10**9,5*10**9], 'memory_current':[99,4,4,1,0], 'memory_anon':[1]*5,'memory_file':[1]*5})
        m=a.metrics(df,10**9,4*10**9)
        self.assertAlmostEqual(m['peak_gib'],4/a.GIB)
        self.assertEqual(m['time_to_peak_s'],0)
        self.assertEqual(m['platform95_total_s'],3)
        self.assertEqual(m['observed_compute_s'],3)
    def test_disjoint_platform_uses_actual_intervals(self):
        df=pd.DataFrame({'monotonic_ns':[0,10**9,3*10**9,4*10**9,6*10**9], 'memory_current':[10,1,10,10,1], 'memory_anon':[1]*5,'memory_file':[1]*5})
        m=a.metrics(df,0,6*10**9)
        self.assertEqual(m['platform95_total_s'],4)
        self.assertEqual(m['platform95_longest_s'],3)
    def test_missing_compute_samples(self):
        df=pd.DataFrame({'monotonic_ns':[0],'memory_current':[10],'memory_anon':[1],'memory_file':[1]})
        self.assertEqual(a.metrics(df,1,2)['status'],'NO_COMPUTE_SAMPLES')
    def test_late_global_peak_does_not_imply_slow_main_growth(self):
        df=pd.DataFrame({'monotonic_ns':[0,1e9,3e9,30e9,90e9], 'memory_current':[1,9.5,9.6,9.7,10], 'memory_anon':[1,9,9,9,9], 'memory_file':[0,.5,.6,.7,1]})
        m=a.metrics(df,0,90e9)
        self.assertEqual(m['time_to_peak_s'],90)
        self.assertEqual(m['time_to90_s'],1)
        self.assertEqual(m['anon_time_to90_s'],1)
    def test_increment_metrics_remove_loaded_gui_baseline(self):
        df=pd.DataFrame({'monotonic_ns':[-.5e9,0,1e9,2e9,3e9], 'memory_current':[8,8,8.5,9.5,10], 'memory_anon':[8,8,8.5,9.5,10], 'memory_file':[0]*5})
        m=a.metrics(df,0,3e9)
        self.assertEqual(m['baseline_gib'],8/a.GIB)
        self.assertEqual(m['increment_peak_gib'],2/a.GIB)
        self.assertEqual(m['time_to90_s'],2)
        self.assertEqual(m['increment_growth10_to90_s'],2)
class PhaseSelectionTests(unittest.TestCase):
    def event(self,kind,stamp):return {'kind':kind,'monotonic_ns':stamp}
    def test_failed_segment_does_not_contaminate_successful_retry(self):
        events=[self.event('task_submit',1),self.event('task_failed',3),self.event('task_submit',10),self.event('task_complete',20),self.event('output_verified',25)]
        self.assertEqual(a.select_compute_window(events),(10,20))
    def test_last_submission_cannot_use_earlier_completion(self):
        events=[self.event('task_submit',1),self.event('task_complete',3),self.event('output_verified',4),self.event('task_submit',10)]
        self.assertIsNone(a.select_compute_window(events))
    def test_gui_completion_without_output_proof_is_not_success(self):
        self.assertIsNone(a.select_compute_window([self.event('task_submit',1),self.event('task_complete',3)]))
    def test_native_log_override_preserves_gui_submit(self):
        events=[self.event('task_submit',1),self.event('task_complete',30),self.event('output_verified',35)]
        self.assertEqual(a.select_compute_window(events,{'task_complete_ns':20}),(1,20))
    def test_verification_before_completion_is_not_sufficient(self):
        events=[self.event('task_submit',1),self.event('output_verified',3),self.event('task_complete',20)]
        self.assertIsNone(a.select_compute_window(events))
    def test_documented_operator_correction_preserves_original_trace(self):
        events=[self.event('task_submit',1),self.event('task_failed',3),{'kind':'event_correction','monotonic_ns':4,'detail':{'supersedes_monotonic_ns':3,'corrected_kind':'configuration_warning'}},self.event('task_complete',20),self.event('output_verified',25)]
        self.assertEqual(a.select_compute_window(events),(1,20))
        self.assertEqual(events[1]['kind'],'task_failed')
    def test_correction_does_not_hide_another_failure(self):
        events=[self.event('task_submit',1),self.event('task_failed',3),{'kind':'event_correction','monotonic_ns':4,'detail':{'supersedes_monotonic_ns':3,'corrected_kind':'configuration_warning'}},self.event('safety_abort',5),self.event('task_complete',20),self.event('output_verified',25)]
        self.assertIsNone(a.select_compute_window(events))
    def test_native_failure_cannot_be_overridden_by_operator(self):
        failure={'kind':'task_failed','monotonic_ns':3,'detail':{'source':'native application log'}}
        events=[self.event('task_submit',1),failure,{'kind':'event_correction','monotonic_ns':4,'detail':{'supersedes_monotonic_ns':3,'corrected_kind':'configuration_warning'}},self.event('task_complete',20),self.event('output_verified',25)]
        self.assertIsNone(a.select_compute_window(events))
    def test_safety_abort_cannot_be_corrected_away(self):
        events=[self.event('task_submit',1),self.event('safety_abort',3),{'kind':'event_correction','monotonic_ns':4,'detail':{'supersedes_monotonic_ns':3,'corrected_kind':'configuration_warning'}},self.event('task_complete',20),self.event('output_verified',25)]
        self.assertIsNone(a.select_compute_window(events))
    def test_long_pre_submit_idle_has_no_effect_on_compute_metrics(self):
        df=pd.DataFrame({'monotonic_ns':[0,7200*10**9,7201*10**9,7202*10**9], 'memory_current':[999,1,4,4], 'memory_anon':[1]*4,'memory_file':[1]*4})
        m=a.metrics(df,7200*10**9,7202*10**9)
        self.assertEqual(m['time_to_peak_s'],1)
        self.assertEqual(m['observed_compute_s'],2)
if __name__=='__main__':unittest.main()
