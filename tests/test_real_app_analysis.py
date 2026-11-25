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
    def test_long_pre_submit_idle_has_no_effect_on_compute_metrics(self):
        df=pd.DataFrame({'monotonic_ns':[0,7200*10**9,7201*10**9,7202*10**9], 'memory_current':[999,1,4,4], 'memory_anon':[1]*4,'memory_file':[1]*4})
        m=a.metrics(df,7200*10**9,7202*10**9)
        self.assertEqual(m['time_to_peak_s'],1)
        self.assertEqual(m['observed_compute_s'],2)
if __name__=='__main__':unittest.main()
