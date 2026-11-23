from dataclasses import replace
import unittest

from memory_prediction import ForecastErrorReserve, HistoricalLookup, MemoryPrediction
from priority_policy import LegacyPriorityPolicy as ArchivedPolicy, PriorityPolicy, TaskMemory


def task(priority, peak, *, current=0, anon=0, running=False, protected=False):
    return TaskMemory(priority, protected, running, current, anon, peak)


class PriorityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(headroom_bytes=10, allocation_margin_bytes=2, memory_high=True,
                           history_s=10, rate_window_s=1, rate_multiplier=1, reaction_s=0,
                           resume_stable_s=.5, max_sample_gap_s=.75)
        self.policy = ArchivedPolicy(20, 10, self.config, legacy_live_freeze=True)

    def test_generic_names_and_joint_budget(self):
        jobs = {'interactive': task(99, 60, current=40, anon=30, running=True, protected=True),
                'encode': task(20, 30), 'index': task(10, 25)}
        self.assertIsNone(self.policy.decide(0, 105, jobs)['resume'])
        decision = self.policy.decide(.5, 105, jobs)
        self.assertEqual(decision['resume'], 'encode')
        self.assertEqual(decision['limits'], {'encode': 30})
        jobs['encode'] = task(20, 30, running=True)
        decision = self.policy.decide(.6, 105, jobs)
        self.assertIsNone(decision['resume'])
        self.assertEqual(decision['required_bytes']['index'], 125)

    def test_cache_and_frozen_memory_do_not_add_credit(self):
        jobs = {'interactive': task(99, 60, current=40, anon=10, running=True, protected=True),
                'encode': task(20, 30, current=20, anon=10)}
        self.assertEqual(self.policy.decide(0, 95, jobs)['required_bytes']['encode'], 110)

    def test_throttle_then_freeze_low_priority(self):
        jobs = {'interactive': task(99, 60, running=True, protected=True),
                'encode': task(20, 40, current=30, anon=12, running=True),
                'index': task(10, 40, current=30, anon=12, running=True)}
        soft = self.policy.decide(0, 25, jobs)
        self.assertEqual(soft['limits'], {'encode': 20, 'index': 20})
        self.assertEqual(soft['freeze'], [])
        self.assertEqual(self.policy.decide(.1, 19, jobs)['freeze'], ['index'])
        self.assertTrue(self.policy.decide(.2, 35, jobs)['throttle'])
        self.assertEqual(self.policy.decide(.3, 45, jobs)['limits'], {'encode': 40, 'index': 40})

    def test_pressure_rate_reserves_reaction_time(self):
        self.config['reaction_s'] = 2
        jobs = {'encode': task(20, 30, running=True)}
        self.policy.decide(0, 100, jobs)
        decision = self.policy.decide(1, 70, jobs)
        self.assertEqual(decision['urgent_bytes'], 80)
        self.assertEqual(decision['freeze'], ['encode'])

    def test_unknown_peak_runs_only_without_active_work(self):
        jobs = {'interactive': task(99, None, running=True, protected=True),
                'unknown': task(20, None)}
        self.assertIsNone(self.policy.decide(0, 200, jobs)['required_bytes']['unknown'])
        del jobs['interactive']
        self.policy.decide(.1, 200, jobs)
        self.assertEqual(self.policy.decide(.65, 200, jobs)['resume'], 'unknown')
        jobs['unknown'] = task(20, None, running=True)
        jobs['index'] = task(10, 25)
        self.assertIsNone(self.policy.decide(.7, 200, jobs)['required_bytes']['index'])

    def test_stale_samples_cannot_complete_resume_hysteresis(self):
        jobs = {'encode': task(20, 30)}
        self.policy.decide(0, 100, jobs)
        self.assertIsNone(self.policy.decide(1, 100, jobs)['resume'])
        self.assertEqual(self.policy.decide(1.5, 100, jobs)['resume'], 'encode')

    def test_freeze_only_variant_never_writes_limit(self):
        self.config['memory_high'] = False
        decision = self.policy.decide(0, 15, {'encode': task(20, 40, running=True)})
        self.assertEqual(decision['freeze'], ['encode'])
        self.assertEqual(decision['limits'], {})


class PredictionFreezeTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(headroom_bytes=5, memory_high=False, history_s=10,
                           rate_window_s=1, rate_multiplier=1, reaction_s=2.5,
                           resume_stable_s=.5, max_sample_gap_s=.6,
                           freeze_prediction=dict(horizon_s=2.5, confirmation_s=.7))
        self.policy = ArchivedPolicy(20, 10, self.config, self)
        self.jobs = {'foreground': task(99, 60, running=True, protected=True),
                     'encode': task(20, 100, running=True),
                     'index': task(10, 100, running=True)}
        self.forecasts = {name: MemoryPrediction(((0., 0),)) for name in self.jobs}

    def predict(self, name, now, age_s, current_bytes, horizon_s):
        self.assertEqual(horizon_s, 2.5)
        return self.forecasts.get(name)

    def test_overlap_freezes_the_task_that_prevents_the_dip(self):
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (1., 45)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (2., 50)))
        decision = self.policy.decide(0, 100, self.jobs)
        self.assertGreater(decision['available_bytes'], decision['urgent_bytes'])
        self.assertEqual(decision['freeze'], ['encode'])
        evidence = decision['freeze_prediction']
        self.assertEqual(evidence['reason'], 'forecast_overlap')
        self.assertEqual(evidence['continued']['first_risk_in_s'], 2.)
        self.assertEqual(evidence['after_freeze']['min_available_bytes'], 55)

    def test_peaks_at_different_offsets_do_not_trigger_freeze(self):
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (.5, 60), (1., 0)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (2., 60)))
        decision = self.policy.decide(0, 100, self.jobs)
        self.assertEqual(decision['freeze'], [])
        self.assertEqual(decision['freeze_prediction']['continued']['min_available_bytes'], 40)

    def test_confirmation_order_can_make_a_two_task_freeze_safe(self):
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (1.8, 50)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (1.1, 45)))
        self.forecasts['index'] = MemoryPrediction(((0., 0), (1.6, 45)))
        decision = self.policy.decide(0, 100, self.jobs)
        self.assertEqual(decision['freeze'], ['encode', 'index'])
        self.assertIsNone(decision['freeze_prediction']['after_freeze']['first_risk_in_s'])

    def test_growth_before_confirmation_remains_charged(self):
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (1., 50)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (.5, 40), (1.2, 10), (2., 60)))
        decision = self.policy.decide(0, 100, self.jobs)
        self.assertEqual(decision['freeze'], ['encode'])
        self.assertEqual(decision['freeze_prediction']['after_freeze']['min_available_bytes'], 10)

    def test_missing_prediction_does_not_freeze_even_under_live_pressure(self):
        del self.forecasts['foreground']
        decision = self.policy.decide(0, 100, self.jobs)
        self.assertEqual(decision['freeze'], [])
        self.assertEqual(decision['freeze_prediction']['unavailable'], ['foreground'])
        decision = self.policy.decide(.2, 19, self.jobs)
        self.assertLess(decision['available_bytes'], decision['urgent_bytes'])
        self.assertEqual(decision['freeze'], [])
        self.assertEqual(decision['freeze_prediction']['reason'], 'forecast_unavailable')

    def test_live_pressure_does_not_freeze_without_a_predicted_dip(self):
        self.policy.decide(0, 150, self.jobs)
        decision = self.policy.decide(1, 100, self.jobs)
        self.assertLess(decision['available_bytes'], decision['urgent_bytes'])
        self.assertEqual(decision['freeze'], [])
        self.assertIsNone(decision['freeze_prediction']['continued']['first_risk_in_s'])

    def test_live_pressure_does_not_override_predicted_victim(self):
        self.policy.decide(0, 150, self.jobs)
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (1., 45)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (2., 50)))
        decision = self.policy.decide(1, 100, self.jobs)
        self.assertLess(decision['available_bytes'], decision['urgent_bytes'])
        self.assertEqual(decision['freeze'], ['encode'])
        self.assertEqual(decision['freeze_prediction']['reason'], 'forecast_overlap')

    def test_emergency_floor_aborts_without_issuing_a_freeze(self):
        decision = self.policy.decide(0, 9, self.jobs)
        self.assertTrue(decision['abort'])
        self.assertEqual(decision['freeze'], [])

    def test_peak_budget_and_stability_still_control_resume(self):
        del self.jobs['index']
        self.jobs['encode'] = task(20, 100, current=50, anon=50)
        original = ArchivedPolicy(20, 10, self.config)
        for now, available in [(0., 120), (.2, 150), (.71, 150)]:
            expected = original.decide(now, available, self.jobs)
            actual = self.policy.decide(now, available, self.jobs)
            self.assertEqual(actual['required_bytes'], expected['required_bytes'])
            self.assertEqual(actual['resume'], expected['resume'])
        self.assertEqual(actual['resume'], 'encode')

    def test_lookup_uses_matched_phase_and_holds_last_running_level(self):
        model = dict(curve=[[0, 10], [1000, 20], [2000, 40], [2500, 0]], duration_ms=2500)
        lookup = HistoricalLookup({'encode': model},
            dict(phase_search_s={'default': .5}, level_tolerance_bytes=0, growth_margin_bytes=0))
        forecast = lookup.predict('encode', 0, .5, 20, 2.5)
        self.assertEqual(forecast.phase_range_s, (1., 1.))
        self.assertEqual(forecast.steps, ((0., 0), (1., 20)))
        self.assertIsNone(lookup.predict('encode', 0, .5, 60, 2.5))

    def test_lookup_excludes_phases_before_confirmed_checkpoint(self):
        model = dict(curve=[[0, 10], [8500, 80], [10000, 10], [20000, 0]], duration_ms=20000)
        lookup = HistoricalLookup({'foreground': model},
            dict(phase_search_s={'default': 3}, level_tolerance_bytes=0, growth_margin_bytes=0))
        unrestricted = lookup.predict('foreground', 0, 10., 10, 2.5)
        bounded = lookup.predict('foreground', 0, 10., 10, 2.5, phase_floor_s=10.)
        self.assertGreater(max(growth for _, growth in unrestricted.steps), 0)
        self.assertEqual(bounded.steps, ((0., 0),))
        self.assertEqual(bounded.phase_range_s[0], 10.)

    def adaptive_policy(self):
        self.config['freeze_prediction']['adaptive_reserve'] = dict(
            base_bytes=5, min_windows=2, phase_bucket_s=60.)
        return ArchivedPolicy(20, 10, self.config, self)

    def test_thaw_uses_joint_forecast_and_keeps_hysteresis(self):
        policy = self.adaptive_policy()
        self.jobs = {'foreground': self.jobs['foreground'],
                     'encode': replace(self.jobs['encode'], running=False)}
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (.5, 55), (1., 0)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (2., 55)))
        first = policy.decide(0., 100, self.jobs)
        self.assertIsNone(first['resume'])
        self.assertEqual(first['required_bytes']['encode'], 86)
        self.assertEqual(first['freeze_prediction']['resume']['encode']['reason'], 'awaiting_stability')
        thaw = policy.decide(.5, 100, self.jobs)
        self.assertEqual(thaw['resume'], 'encode')
        self.jobs['encode'] = replace(self.jobs['encode'], running=True)
        next_tick = policy.decide(.7, 100, self.jobs)
        self.assertEqual(next_tick['freeze'], [])
        self.assertEqual(next_tick['freeze_prediction']['reserve_bytes'], 20)

    def test_thaw_denied_when_joint_forecast_crosses_hysteresis(self):
        policy = self.adaptive_policy()
        self.jobs['encode'] = replace(self.jobs['encode'], running=False)
        self.forecasts['foreground'] = MemoryPrediction(((0., 0), (2., 40)))
        self.forecasts['encode'] = MemoryPrediction(((0., 0), (2., 35)))
        decision = policy.decide(0., 100, self.jobs)
        self.assertEqual(decision['required_bytes']['encode'], 106)
        self.assertIsNone(decision['resume'])

    def test_unmatched_frozen_task_waits_then_uses_new_stability_window(self):
        policy = self.adaptive_policy()
        self.jobs['encode'] = replace(self.jobs['encode'], running=False)
        forecast = self.forecasts.pop('encode')
        self.assertIsNone(policy.decide(0., 500, self.jobs)['resume'])
        self.forecasts['encode'] = forecast
        self.assertIsNone(policy.decide(.5, 500, self.jobs)['resume'])
        self.assertEqual(policy.decide(1., 500, self.jobs)['resume'], 'encode')


class FixedPredictionTests(unittest.TestCase):
    def setUp(self):
        self.policy = PriorityPolicy(dict(resume_stable_s=.5, max_sample_gap_s=.6,
            freeze_prediction=dict(reserve_bytes=20, resume_margin_bytes=10,
                                   horizon_s=2.5, confirmation_s=.7)), self)
        self.jobs = {'foreground': task(99, 100, running=True, protected=True),
                     'raster': task(30, 100, running=True)}
        self.forecasts = {'foreground': MemoryPrediction(((0., 0),)),
                          'raster': MemoryPrediction(((0., 0), (2., 45)))}

    def predict(self, name, now, age_s, current_bytes, horizon_s, **phase):
        return self.forecasts.get(name)

    def predict_startup(self, name, now, lead_s, horizon_s):
        return MemoryPrediction(((0., 0), (lead_s, 40)))

    def test_imminent_start_causes_early_freeze_without_soft_limits(self):
        self.assertEqual(self.policy.decide(0., 100, self.jobs)['freeze'], [])
        decision = self.policy.decide(.2, 100, self.jobs, {'array': 1.})
        self.assertEqual(decision['freeze'], ['raster'])
        self.assertEqual(decision['freeze_prediction']['continued']['first_risk_in_s'], 2.)
        self.assertEqual(decision['freeze_prediction']['after_freeze']['min_available_bytes'], 60)
        self.assertNotIn('limits', decision)
        self.assertNotIn('reserve_calibration', decision['freeze_prediction'])

    def test_thaw_strictly_exceeds_hysteresis_including_planned_launch(self):
        held = {**self.jobs, 'raster': replace(self.jobs['raster'], running=False)}
        rejected = self.policy.decide(0., 115, held, {'array': 1.})
        self.assertEqual(rejected['freeze_prediction']['resume']['raster']['reason'], 'insufficient_headroom')
        self.assertIsNone(rejected['resume'])
        self.assertIsNone(self.policy.decide(.2, 116, held, {'array': 1.})['resume'])
        thawed = self.policy.decide(.71, 116, held, {'array': 1.})
        self.assertEqual(thawed['resume'], 'raster')
        self.assertEqual(self.policy.decide(.8, 116, self.jobs, {'array': 1.})['freeze'], [])

    def test_unknown_forecast_blocks_thaw_instead_of_ignoring_it(self):
        del self.forecasts['foreground']
        held = {**self.jobs, 'raster': replace(self.jobs['raster'], running=False)}
        decision = self.policy.decide(0., 1000, held)
        self.assertEqual(decision['freeze'], [])
        self.assertIsNone(decision['resume'])
        self.assertEqual(decision['freeze_prediction']['resume']['raster']['unavailable'], ['foreground'])

    def test_lookup_matches_anonymous_charge_inside_confirmed_stage(self):
        curve = dict(curve=[[0, 40], [1000, 80], [3000, 200], [4000, 0]], duration_ms=4000)
        curve['anonymous_curve'] = dict(
            curve=[[0, 10], [1000, 20], [3000, 60], [4000, 0]], duration_ms=4000)
        lookup = HistoricalLookup({'raster': curve},
            dict(phase_search_s={'default': 2}, level_tolerance_bytes=0))
        forecast = lookup.predict('raster', 0, 1.5, 20, 2.5, anonymous_bytes=20,
                                  phase_floor_s=1., phase_ceiling_s=2.)
        self.assertEqual(forecast.phase_range_s, (1., 2.))
        self.assertEqual(forecast.match_basis, 'anonymous')
        self.assertLessEqual(forecast.steps[-1][0], 2.5)
        startup = lookup.predict_startup('raster', 0, .5, 2.5)
        self.assertEqual(startup.steps, ((0., 0), (.5, 40), (1.5, 80)))
        self.assertEqual(lookup.predict_startup('raster', 0, 0., 2.5).steps[0], (0., 40))


class ForegroundPeakTests(unittest.TestCase):
    def setUp(self):
        fg = dict(curve=[[0, 100], [8000, 180], [12000, 100], [14000, 125], [16000, 0]],
                  duration_ms=16000,
                  anonymous_curve=dict(curve=[[0, 70], [8000, 155], [12000, 55], [14000, 85], [16000, 0]],
                                       duration_ms=16000))
        bg = dict(curve=[[0, 15], [2000, 55], [4000, 0]], duration_ms=4000)
        self.config = dict(resume_stable_s=.5, max_sample_gap_s=.6,
            freeze_prediction=dict(reserve_bytes=20, resume_margin_bytes=10, horizon_s=2.5,
                                   confirmation_s=.7, phase_search_s={'default': 0}, level_tolerance_bytes=0))
        self.lookup = HistoricalLookup({'foreground': fg, 'table': bg}, self.config['freeze_prediction'])
        self.jobs = {'foreground': replace(task(100, 180, current=110, anon=80, running=True, protected=True), age_s=0.),
                     'table': replace(task(20, 55, current=15, anon=15, running=True), age_s=.5)}

    def peak_policy(self):
        forecast = dict(self.config['freeze_prediction'], reserve_foreground_peak=True)
        cfg = dict(self.config, freeze_prediction=forecast)
        return PriorityPolicy(cfg, self.lookup)

    def test_freezes_for_protected_peak_beyond_background_horizon(self):
        old = PriorityPolicy(self.config, self.lookup).decide(0., 125, self.jobs)
        new = self.peak_policy().decide(0., 125, self.jobs)
        self.assertEqual(old['freeze'], [])
        self.assertEqual(new['freeze'], ['table'])
        evidence = new['freeze_prediction']
        self.assertEqual(evidence['foreground_peak_growth_bytes'], {'foreground': 75})
        self.assertEqual(evidence['continued']['min_available_bytes'], 10)
        self.assertEqual(evidence['after_freeze']['min_available_bytes'], 50)

    def test_thaw_still_reserves_peak_until_a_later_stage_is_confirmed(self):
        policy = self.peak_policy()
        self.jobs['table'] = replace(self.jobs['table'], running=False)
        # Wall-clock progress alone must not age away the peak.
        self.jobs['foreground'] = replace(self.jobs['foreground'], age_s=13.)
        held = policy.decide(0., 125, self.jobs)
        self.assertIsNone(held['resume'])
        self.assertEqual(held['freeze_prediction']['resume']['table']['min_available_bytes'], 10)
        self.jobs['foreground'] = replace(self.jobs['foreground'], phase_floor_s=12., current=105, anon=60)
        tail = policy.decide(.5, 125, self.jobs)
        self.assertEqual(tail['freeze_prediction']['foreground_peak_growth_bytes'], {'foreground': 25})
        self.assertIsNone(tail['resume'])
        self.assertEqual(policy.decide(1., 125, self.jobs)['resume'], 'table')


class ForecastErrorReserveTests(unittest.TestCase):
    def test_learns_the_worst_one_sided_error_per_completed_window(self):
        reserve = ForecastErrorReserve(dict(base_bytes=50, min_windows=2, phase_bucket_s=60.), 100, 2.5)
        phase = ('foreground', 'raster')
        path = ((0., 300), (1., 170), (2., 120))
        initial = reserve.observe(0., 300, phase, phase, False)
        self.assertEqual(initial['reserve_bytes'], 100)
        reserve.record(0., phase, path, False)
        reserve.observe(1., 150, phase, phase, False)
        reserve.observe(2., 180, phase, phase, False)
        cold = reserve.observe(2.5, 130, phase, phase, False)
        self.assertEqual((cold['windows'], cold['reserve_bytes']), (1, 100))
        reserve.record(2.5, phase, path, False)
        reserve.observe(3.5, 140, phase, phase, False)
        reserve.observe(4.5, 160, phase, phase, False)
        learned = reserve.observe(5.0, 125, phase, phase, False)
        self.assertEqual((learned['windows'], learned['error_margin_bytes'], learned['reserve_bytes']),
                         (2, 30, 80))
        other = reserve.observe(5.2, 125, ('foreground',), ('foreground',), False)
        self.assertEqual((other['windows'], other['reserve_bytes']), (0, 100))

    def test_changed_actions_and_stale_samples_discard_pending_windows(self):
        reserve = ForecastErrorReserve(dict(base_bytes=50, min_windows=1, phase_bucket_s=60.), 100, 2.5)
        phase = ('foreground',)
        path = ((0., 300), (1., 200))
        reserve.record(0., phase, path, False)
        reserve.observe(1., 100, phase, phase, False)
        reserve.record(1., phase, path, True)
        self.assertEqual(reserve.observe(2.5, 100, phase, phase, False)['windows'], 0)
        reserve.record(2.5, phase, path, False)
        self.assertEqual(reserve.observe(5.0, 100, phase, phase, True)['windows'], 0)


if __name__ == '__main__':
    unittest.main()
