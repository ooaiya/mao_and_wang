import json,unittest
from pathlib import Path
from segmented_scheduler import Curve,Forecaster,SegmentPolicy,TaskClock

def config(**changes):
    c=json.loads(Path(__file__).with_name('test_segmented_config.json').read_text())
    c.update(foreground_jitter_s=0,background_jitter_s=0,growth_uncertainty_bytes=0,growth_multiplier=1,
             resume_headroom_bytes=0,minimum_frozen_s=0,resume_stable_s=0,level_tolerance_bytes=1000)
    c.update(changes);return c
def model(values):return dict(duration_ms=(len(values)-1)*1000,curve=[[i*1000,v] for i,v in enumerate(values)])

class ForecastTests(unittest.TestCase):
    def test_ramp_only_next_piece_is_short_forecast(self):
        f=Forecaster(model(list(range(101))),config(),True);r=f.predict(20,20,5)
        self.assertEqual(r.growth_bytes,5);self.assertEqual(r.remaining_growth_bytes,80)
    def test_front_loaded_does_not_reserve_finished_peak(self):
        f=Forecaster(model([0,100,100,40,40,40,40]),config(),True);r=f.predict(3,40,1)
        self.assertEqual(r.remaining_growth_bytes,0)
    def test_late_burst_remains_in_parking_budget(self):
        f=Forecaster(model([10]*10+[100]*5),config(),True);r=f.predict(2,10,2)
        self.assertEqual(r.growth_bytes,0);self.assertEqual(r.remaining_growth_bytes,90)
    def test_second_peak_is_not_removed_after_first_fall(self):
        f=Forecaster(model([0,80,30,30,30,100,30,30,30]),config(),True)
        self.assertEqual(f.predict(3,30,1).remaining_growth_bytes,70)
    def test_phase_ambiguity_keeps_possible_nearby_peak(self):
        f=Forecaster(model([10,10,100,10,10,10,100,10,10,10]),config(foreground_jitter_s=2,level_tolerance_bytes=0,level_tolerance_fraction=0),True)
        self.assertGreater(f.predict(4,10,1).growth_bytes,0)
    def test_predicted_drop_never_becomes_free_memory(self):
        f=Forecaster(model([100,100,50,0,0]),config(),True)
        r=f.predict(1,100,2);self.assertEqual(r.growth_bytes,0);self.assertEqual(r.remaining_growth_bytes,0)
    def test_live_anchor_predicts_delta_not_full_peak_again(self):
        f=Forecaster(model([100,110,120,130,140]),config(),True)
        self.assertEqual(f.predict(1,1000,1).growth_bytes,10)
    def test_overrun_does_not_trust_terminal_zero(self):
        f=Forecaster(model([0,100,0]),config(),True);r=f.predict(3,20,1)
        self.assertFalse(r.reliable);self.assertGreaterEqual(r.growth_bytes,80)
    def test_recent_growth_can_exceed_flat_reference(self):
        f=Forecaster(model([100]*20),config(),True);f.observe(0,100);f.observe(1,110)
        self.assertGreaterEqual(f.predict(5,110,2).growth_bytes,30)
    def test_one_sample_jump_is_not_extrapolated_at_instantaneous_rate(self):
        f=Forecaster(model([100]*20),config(),True)
        for i in range(11):f.observe(i*.2,100+(36 if i==10 else 0))
        self.assertLessEqual(f.recent_rate(),36*1.5)
    def test_sustained_fast_growth_is_still_reserved(self):
        f=Forecaster(model([100]*20),config(),True)
        for i in range(11):f.observe(i*.2,100+i*20)
        self.assertGreaterEqual(f.recent_rate(),149.9)
    def test_safety_inflation_is_not_used_as_an_observed_phase_level(self):
        m=model([0,100,105,90,90,95,95,95]);m['reference_level_scale']=1.05;m['curve']=[[t,int(v*1.05)] for t,v in m['curve']]
        f=Forecaster(m,config(foreground_jitter_s=2,level_match_band_bytes=1),True)
        r=f.predict(2,100,1);self.assertEqual(r.phase_min_s,1);self.assertEqual(r.phase_max_s,1)
    def test_recent_rise_rejects_a_reference_fall_phase(self):
        f=Forecaster(model([90,100,105,95,95,100,105,105]),config(foreground_jitter_s=1,level_match_band_bytes=1000,trend_tolerance_bytes=1,trend_tolerance_fraction=0),True)
        f.observe(0,95);f.observe(1,100)
        r=f.predict(2,100,1);self.assertTrue(r.reliable);self.assertLess(r.phase_max_s,3)
    def test_parking_retains_absolute_inflated_foreground_ceiling(self):
        m=model([105,115,126,126]);m['reference_level_scale']=1.05
        f=Forecaster(m,config(),True);r=f.predict(0,100,1)
        self.assertEqual(r.growth_bytes,10);self.assertEqual(r.remaining_growth_bytes,26)
    def test_foreground_tail_does_not_restart_an_old_peak(self):
        f=Forecaster(model([100]*5+[20]*10+[0]),config(foreground_jitter_s=3,level_tolerance_bytes=0,level_tolerance_fraction=0,level_match_band_bytes=0),True)
        r=f.predict(14,20,3);self.assertTrue(r.reliable);self.assertEqual(r.remaining_growth_bytes,0)
    def test_tail_overrun_is_bounded_by_time_uncertainty(self):
        f=Forecaster(model([100]*5+[20]*10+[0]),config(foreground_jitter_s=3,level_tolerance_bytes=0,level_tolerance_fraction=0,level_match_band_bytes=0),True)
        self.assertEqual(f.predict(16,20,1).remaining_growth_bytes,0)
        r=f.predict(20,20,1);self.assertFalse(r.reliable);self.assertGreaterEqual(r.remaining_growth_bytes,80)
    def test_first_allocation_is_not_subtracted(self):
        f=Forecaster(model([10,20,30,30]),config())
        self.assertEqual(f.predict(0,0,1,started=False).growth_bytes,20)
    def test_curve_range_max_keeps_narrow_peak(self):
        c=Curve(dict(duration_ms=2000,curve=[[0,0],[500,100],[1000,0],[2000,0]]))
        self.assertEqual(c.maximum(.1,.9),100)

class ClockTests(unittest.TestCase):
    def test_repeated_pauses_preserve_effective_age(self):
        c=TaskClock();c.resumed(10,20);self.assertEqual(c.age(13),3)
        c.frozen(14);self.assertEqual(c.age(100),4)
        c.resumed(100,105);self.assertEqual(c.age(102),6)
        c.frozen(103);self.assertEqual(c.age(300),7)
    def test_invalid_double_resume_is_rejected(self):
        c=TaskClock();c.resumed(0,5)
        with self.assertRaises(ValueError):c.resumed(1,6)

class AdmissionTests(unittest.TestCase):
    def make(self,c=None):
        models={'foreground_krita':model(list(range(20,41))), 'raster':model(list(range(101))),
                'table':model([0]*101),'array':model([0]*101)}
        return SegmentPolicy(models,c or config(),3)
    def test_future_deficit_freezes_and_holds_without_claiming_emergency(self):
        p=self.make();c=TaskClock(state='RUNNING',since=90,ever_started=True)
        d=p.decide(100,10,8,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertTrue(d.parking_deficit);self.assertTrue(d.retention_hold)
        self.assertFalse(d.emergency_deficit);self.assertEqual(d.freeze,['raster'])
        self.assertEqual(d.leases,{});self.assertEqual(d.resume,[])
    def test_hold_never_reopens_on_prediction_recovery(self):
        p=self.make();c=TaskClock(state='RUNNING',since=90,ever_started=True)
        p.decide(100,10,8,{'foreground_krita':30,'raster':10},{'raster':c});c.frozen(100)
        d=p.decide(110,10,1000,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertTrue(d.retention_hold);self.assertFalse(d.parking_deficit);self.assertEqual(d.resume,[])
    def test_normal_foreground_exit_reopens_held_background(self):
        p=self.make();c=TaskClock(state='RUNNING',since=90,ever_started=True)
        p.decide(100,10,8,{'foreground_krita':30,'raster':10},{'raster':c});c.frozen(100)
        d=p.decide(110,10,1000,{'foreground_krita':0,'raster':10},{'raster':c},foreground_done=True)
        self.assertFalse(d.retention_hold);self.assertFalse(d.emergency_deficit);self.assertEqual(d.resume,['raster'])
    def test_live_reserve_breach_is_emergency_even_with_frozen_background(self):
        p=self.make();c=TaskClock(ever_started=True)
        d=p.decide(100,10,2,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertTrue(d.emergency_deficit);self.assertEqual(d.resume,[])
        self.assertEqual(d.evidence['live_reserve_guard']['reserve_bytes'],3)
    def test_live_guard_reserves_foreground_reaction_growth(self):
        p=self.make();c=TaskClock(ever_started=True)
        p.observe(99,{'foreground_krita':20,'raster':10});p.observe(100,{'foreground_krita':30,'raster':10})
        d=p.decide(100,10,35,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertTrue(d.emergency_deficit)
        self.assertGreater(d.evidence['live_reserve_guard']['required_bytes'],35)
    def test_can_run_piece_when_whole_background_peak_would_not_fit(self):
        p=self.make();clocks={'raster':TaskClock(frozen_since=-100)}
        d=p.decide(100,10,30,{'foreground_krita':30,'raster':0},clocks)
        self.assertEqual(d.resume,['raster']);self.assertLess(d.evidence['raster']['parking_required_bytes'],100)
    def test_remaining_front_peak_limits_retained_allocation(self):
        p=self.make();d=p.decide(100,0,10,{'foreground_krita':20,'raster':0},{'raster':TaskClock(frozen_since=-100)})
        self.assertEqual(d.resume,[]);self.assertTrue(d.parking_deficit)
    def test_freezing_does_not_add_retained_pages_back_to_available(self):
        p=self.make();c=TaskClock(state='RUNNING',since=90,ever_started=True)
        running=p.decide(100,10,8,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertEqual(running.freeze,['raster'])
        c.frozen(100)
        parked=p.decide(101,11,8,{'foreground_krita':31,'raster':10},{'raster':c})
        self.assertEqual(parked.resume,[])
    def test_short_tasks_wait_for_foreground_done_by_role(self):
        p=self.make();c={'table':TaskClock(frozen_since=-100)}
        self.assertEqual(p.decide(100,10,1000,{'foreground_krita':30,'table':0},c).resume,[])
        self.assertEqual(p.decide(100,10,1000,{'foreground_krita':30,'table':0},c,True).resume,['table'])
    def test_generic_early_role_can_be_configured(self):
        p=self.make(config(early_backgrounds=['table'],hold_until_foreground_done=['raster','array']));c={'table':TaskClock(frozen_since=-100)}
        self.assertEqual(p.decide(100,10,1000,{'foreground_krita':30,'table':0},c).resume,['table'])
    def test_running_task_is_paused_when_next_piece_unsafe(self):
        p=self.make();c=TaskClock(state='RUNNING',since=90,ever_started=True)
        d=p.decide(100,10,14,{'foreground_krita':30,'raster':10},{'raster':c})
        self.assertEqual(d.freeze,['raster'])
    def test_mismatch_denies_admission_while_foreground_active(self):
        p=self.make(config(level_tolerance_bytes=0,level_tolerance_fraction=0));c={'raster':TaskClock(frozen_since=-100)}
        d=p.decide(100,10,1000,{'foreground_krita':999,'raster':0},c)
        self.assertEqual(d.resume,[])
    def test_background_overrun_can_finish_after_foreground_exits(self):
        p=self.make();c=TaskClock(state='RUNNING',since=0,ever_started=True)
        d=p.decide(200,200,1000,{'foreground_krita':0,'raster':110},{'raster':c},True)
        self.assertEqual(d.freeze,[]);self.assertIn('raster',d.leases)
    def test_collective_growth_is_not_approved_independently(self):
        m={'foreground_krita':model([10]*100),'a':model(list(range(101))),'b':model(list(range(101)))}
        p=SegmentPolicy(m,config(early_backgrounds=['a','b'],hold_until_foreground_done=[]),3)
        d=p.decide(100,10,16,{'foreground_krita':10,'a':0,'b':0},{'a':TaskClock(frozen_since=-100),'b':TaskClock(frozen_since=-100)})
        self.assertLessEqual(len(d.resume),2)
        if len(d.resume)==2:
            self.assertEqual(d.leases['a'],d.leases['b'])
            self.assertLess(d.leases['a']-100,8)

if __name__=='__main__':unittest.main()
