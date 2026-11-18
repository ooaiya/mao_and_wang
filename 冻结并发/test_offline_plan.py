import unittest
from offline_plan import DEFAULT,search,candidate,held_bound,combine
from segmented_scheduler import Curve

def model(v):return dict(curve=[[i*1000,x] for i,x in enumerate(v)],duration_ms=(len(v)-1)*1000,peak_bytes=max(v),terminal_bytes=v[-1])
def config(**kw):
    c=dict(DEFAULT);c.update(step_s=.5,start_step_s=1.,foreground_jitter_s=0.,background_jitter_s=0.,background_speed_upper=1.,reaction_s=0.,model_error_bytes=0,admission_headroom_bytes=0,early_finish_lead_s=0.,minimum_early_s=1.,maximum_early_s=20.);c.update(kw);return c

class OfflineTests(unittest.TestCase):
    def test_pause_retains_charge_across_later_foreground_peak(self):
        fg=Curve(model([20,20,20,90,90,90,90]));xz=Curve(model([0,5,15,30,30,30,30]))
        self.assertIsNone(candidate(fg,xz,0,2,100,config()))
        self.assertIsNotNone(candidate(fg,xz,0,1,100,config()))
    def test_memory_decline_does_not_reclaim_frozen_charge(self):
        xz=Curve(model([0,80,0,0,0]));self.assertEqual(held_bound(xz,3,config()),80)
    def test_second_peak_is_kept_after_a_valley(self):
        fg=Curve(model([50,10,10,95,95,10,10]));xz=Curve(model([0,10,20,30,40,50,60]))
        self.assertIsNone(candidate(fg,xz,1,1,100,config()))
    def test_search_can_use_a_late_window_after_an_early_peak(self):
        r=search(model([90,90,90,20,20,20,20,20,20,20]),model([0,20,30,40,50,60,70,80,90,100]),0,100,0,0,0,config())
        self.assertGreaterEqual(r['selected']['start_s'],2);self.assertGreater(r['selected']['freeze_request_s'],3)
    def test_insufficient_capacity_does_not_invent_a_plan(self):
        r=search(model([100]*10),model([1]*10),0,100,0,0,0,config())
        self.assertIsNone(r['selected'])
    def test_nominal_submission_is_a_hard_lower_bound(self):
        r=search(model([10]*20),model(list(range(20))),7.3,100,0,0,0,config())
        self.assertGreaterEqual(r['selected']['start_s'],7.3)
    def test_foreground_terminal_zero_is_held_until_real_exit(self):
        m=combine(model([100,30,30,0]),model([90,20,20,0]),True)
        self.assertGreater(m['curve'][-1][1],0)
    def test_calibration_includes_larger_observed_xz_peak(self):
        self.assertGreaterEqual(combine(model([0,10,10]),model([0,30,30]))['peak_bytes'],30)

if __name__=='__main__':unittest.main()
