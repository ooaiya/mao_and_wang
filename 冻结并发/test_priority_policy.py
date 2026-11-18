import unittest

from priority_policy import PriorityPolicy, TaskMemory


def task(priority, peak, *, current=0, anon=0, running=False, protected=False):
    return TaskMemory(priority, protected, running, current, anon, peak)


class PriorityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(headroom_bytes=10, allocation_margin_bytes=2, memory_high=True,
                           history_s=10, rate_window_s=1, rate_multiplier=1, reaction_s=0,
                           resume_stable_s=.5, max_sample_gap_s=.75)
        self.policy = PriorityPolicy(20, 10, self.config)

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


if __name__ == '__main__':
    unittest.main()
