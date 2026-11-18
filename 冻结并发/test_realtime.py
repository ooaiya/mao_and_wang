"""Online policy and fake-cgroup tests for the first-start and lease invariants."""

import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from realtime_audit import check_joint_budget
from realtime_policy import FOREGROUND, MIB, PRIORITIES, Reading, RealtimePolicy, Settings
from realtime_runner import RasterRealtimeFreezer, RealtimeFreezer


def reading(current=0, anon=0, *, high=128, events=0, state='RUNNING', started=True):
    return Reading(current * MIB, anon * MIB, events, 0, state, started, high * MIB)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(reserve_fraction=.125)
        self.policy = RealtimePolicy(self.settings, 16 * 1024 * MIB)

    def decide(self, now, available, jobs, frozen=None):
        return self.policy.decide(now, available * MIB, jobs, frozen or {})

    def test_short_drop_raises_freeze_line_before_long_window_is_ready(self):
        jobs = {'xz': reading(30), 'array': reading(30), 'table': reading(started=False)}
        self.decide(1, 2700, jobs)
        decision = self.decide(1.2, 2360, jobs)
        self.assertEqual(decision['short_drop_bytes'], 340 * MIB)
        self.assertEqual(decision['freeze'], 'array')
        self.assertEqual(decision['renew'], [])

    def test_soft_threshold_tightens_and_emergency_aborts(self):
        jobs = {'xz': reading(250, 120, high=275)}
        decision = self.decide(1, 2130, jobs)
        self.assertEqual(decision['limits'], {'xz': 152 * MIB})
        self.assertIn('xz', decision['renew'])
        self.assertIsNone(decision['freeze'])
        decision = self.decide(1.2, 300, jobs)
        self.assertTrue(decision['abort'])
        self.assertEqual(decision['renew'], [])

    def test_resume_needs_fresh_stable_budget_and_confirmed_other_startups(self):
        parked = {'xz': reading(400, 390, state='FROZEN'), 'array': reading(60, state='FROZEN')}
        frozen = {'xz': 0., 'array': 0.}
        self.assertIsNone(self.decide(1., 3000, parked, frozen)['resume'])
        self.assertIsNone(self.decide(2., 3000, parked, frozen)['resume'])
        decision = self.decide(2.5, 3000, parked, frozen)
        self.assertEqual(decision['resume'], 'xz')
        self.assertEqual(decision['limits'], {'xz': (400 + 128) * MIB})
        parked['table'] = reading(started=False)
        self.assertIsNone(self.decide(2.7, 3000, parked, frozen)['resume'])

    def test_backgrounds_resume_in_priority_order_and_keep_running_together(self):
        jobs = {name: reading(64, 64, state='FROZEN') for name in PRIORITIES}
        frozen = dict.fromkeys(PRIORITIES, 0.)
        for now, name in [(1., 'xz'), (1.75, 'array'), (2.5, 'table')]:
            earlier = set(PRIORITIES) - frozen.keys()
            self.assertIsNone(self.decide(now, 5000, jobs, frozen)['resume'])
            decision = self.decide(now + .5, 5000, jobs, frozen)
            self.assertEqual(decision['resume'], name)
            self.assertEqual(decision['limits'], {name: 192 * MIB})
            self.assertEqual(set(decision['renew']), earlier)
            self.policy.reset_stability()
            jobs[name] = reading(64, 64, high=192)
            del frozen[name]
        self.assertEqual(self.decide(3.25, 1600, jobs)['freeze'], 'table')

    def test_joint_budget_accounts_for_existing_limits_and_candidate_cache(self):
        jobs = {'xz': reading(480, 120, high=512), 'array': reading(300, 20, state='FROZEN')}
        frozen = {'array': 0.}
        first = self.decide(1., 3000, jobs, frozen)
        self.assertEqual(first['running_growth_bytes'], {'xz': 392 * MIB})
        self.assertEqual(first['resume_required_bytes'], {'array': 3104 * MIB})
        self.assertEqual(first['resume_since_s'], {})
        self.assertIsNone(self.decide(1.25, 3200, jobs, frozen)['resume'])
        self.assertEqual(self.decide(1.75, 3200, jobs, frozen)['resume'], 'array')

    def test_raster_uses_the_same_pressure_and_joint_resume_rules(self):
        self.policy = RealtimePolicy(self.settings, 16 * 1024 * MIB, RasterRealtimeFreezer.priorities)
        jobs = {'raster_fft': reading(24, 22), 'array': reading(64), 'table': reading(64)}
        self.assertEqual(self.decide(1., 1800, jobs)['freeze'], 'table')
        jobs['raster_fft'] = reading(24, 22, state='FROZEN')
        self.assertIsNone(self.decide(2., 5000, jobs, {'raster_fft': 1.})['resume'])
        decision = self.decide(2.5, 5000, jobs, {'raster_fft': 1.})
        self.assertEqual(decision['resume'], 'raster_fft')
        self.assertEqual(decision['limits']['raster_fft'], 152 * MIB)

    def test_joint_budget_audit_detects_double_spending_or_reused_window(self):
        jobs = {'xz': reading(100, 100, high=192), 'array': reading(64, 64, state='FROZEN')}
        frozen = {'array': 0.}
        ticks = {}
        for tick, now in [(1, 1.), (2, 1.5)]:
            decision = self.decide(now, 5000, jobs, frozen)
            ticks[tick] = dict(decision=decision, monotonic_s=now, readings={op: vars(r) for op, r in jobs.items()},
                               frozen_since=frozen, limits={}, frozen=None, resumed=None)
        row = ticks[2]
        recovery = (2048 + 256) * MIB
        args = (row, {'xz'}, ticks, recovery, self.settings, PRIORITIES)
        self.assertIsNone(check_joint_budget(*args))
        prior_limits = ticks[1]['limits']
        prior_limits['xz'] = {'applied_bytes': 192 * MIB}
        self.assertIn('crosses an action', check_joint_budget(*args))
        prior_limits.clear()
        row['decision']['running_growth_bytes']['xz'] = 0
        self.assertIn('joint memory budget', check_joint_budget(*args))

    def test_late_growth_can_only_open_one_soft_limit_step(self):
        jobs = {'xz': reading(120, 115), 'array': reading(10, high=512)}
        self.decide(1, 2800, jobs)
        self.assertEqual(self.decide(1.5, 2800, jobs)['limits'], {})
        decision = self.decide(2, 3600, jobs)
        self.assertEqual(decision['limits'], {'xz': 256 * MIB})

    def test_whole_resume_budget_must_hold_during_stability_window(self):
        jobs = {'xz': reading(400, 390, state='FROZEN')}
        frozen = {'xz': 0.}
        self.decide(1., 2400, jobs, frozen)
        self.decide(1.4, 2400, jobs, frozen)
        self.assertIsNone(self.decide(1.6, 2500, jobs, frozen)['resume'])
        self.assertEqual(self.decide(2.15, 2500, jobs, frozen)['resume'], 'xz')

    def test_retry_reserve_is_bounded_and_uses_foreground_growth(self):
        previous = {'xz': reading(160, 100), FOREGROUND: reading(6000, 5900)}
        foreground_grew = {'xz': reading(240, 180), FOREGROUND: reading(6250, 6150)}
        for _ in range(8):
            self.policy.record_pressure_freeze('xz', foreground_grew, previous)
        self.assertEqual(self.policy.retry_extra, {})
        victim_grew = dict(previous, xz=reading(240, 180))
        for _ in range(8):
            self.policy.record_pressure_freeze('xz', victim_grew, previous)
        self.assertEqual(self.policy.retry_extra, {'xz': 512 * MIB})


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.group = Path(folder.name)
        for name, data in {'memory.current': '1024', 'memory.stat': 'anon 1024',
                           'memory.events': 'high 0', 'cpu.stat': 'usage_usec 20'}.items():
            (self.group / name).write_text(data)
        self.runner = r = object.__new__(RealtimeFreezer)
        r.out = self.group
        r.settings = Settings()
        r.policy_config = {'freeze_timeout_s': r.settings.freeze_timeout_s}
        r.policy = RealtimePolicy(r.settings, 16 * 1024 * MIB)
        r.records = {'xz': {'created_ns': 9_999_000_000}}
        r.groups = {'xz': {'cgroup_path': str(self.group)}}
        r.pipes = {'xz': 99}
        r.clocks = {}
        r.high = {}
        r.lock = threading.RLock()
        r.watch_error = None
        r.tick_id = 1
        r.done = {FOREGROUND}
        r.freeze_rows = []
        r.decision_stream = io.StringIO()
        r.event = Mock()
        r.processes = {'xz': Mock(poll=Mock(return_value=None))}
        r.cm = Mock()
        r.cm.checked.return_value = self.group
        self.now = 10.
        for name, callback in [('monotonic', lambda: self.now), ('monotonic_ns', lambda: round(self.now * 1e9))]:
            clock = patch('realtime_runner.time.' + name, side_effect=callback)
            clock.start()
            self.addCleanup(clock.stop)
        r.background_start_ns = Mock(return_value=None)
        r.cm.set_frozen.side_effect = self.confirm

    def confirm(self, op, frozen, timeout):
        stamp = round(self.now * 1e9)
        return dict(requested_monotonic_ns=stamp, confirmed_monotonic_ns=stamp, cgroup=str(self.group),
                    events=dict(frozen=int(frozen), populated=1), frozen=frozen)

    def start(self):
        r = self.runner
        order = []

        def set_high(group, target):
            order.append('limit')
            (group / 'memory.high').write_text(str(target))

        def release(fd, token):
            order.append('release')
            self.assertEqual((fd, token), (99, b'G'))
            return 1

        with patch('realtime_runner.Freezer.launch') as gate, patch('realtime_runner.write_memory_high', set_high), \
                patch('realtime_runner.os.write', release), patch('realtime_runner.os.close'), \
                patch('realtime_runner.memory', return_value={'MemAvailable': 10 * 1024 * MIB}):
            r.launch('xz')
        gate.assert_called_once_with(r, 'xz', freeze_on_submit=False, defer_release=True)
        self.assertEqual(order, ['limit', 'release'])
        r.cm.set_frozen.assert_not_called()

    def test_first_freeze_waits_for_actual_execution_not_just_gate_release(self):
        self.start()
        r = self.runner
        self.now = 10.2
        self.assertFalse(r.freeze_started('xz', 'realtime_pressure'))
        r.cm.set_frozen.assert_not_called()
        started = 10_100_000_000
        r.background_start_ns.return_value = started
        self.assertTrue(r.freeze_started('xz', 'realtime_pressure'))
        self.assertEqual(r.freeze_rows[0]['admission']['actual_start_ns'], started)
        self.assertLess(started, r.freeze_rows[0]['requested_monotonic_ns'])

    def test_watchdog_can_freeze_after_main_loop_stalls(self):
        self.start()
        r = self.runner
        r.background_start_ns.return_value = 10_100_000_000
        r.watch_stop = Mock(wait=Mock(side_effect=[False, True]))
        self.now = 12.1
        r.watchdog()
        self.assertIsNone(r.watch_error)
        self.assertEqual(r.clocks['xz'].state, 'FROZEN')
        self.assertEqual(r.freeze_rows[0]['reason'], 'realtime_lease_expired')

    def test_expired_start_without_workload_execution_fails_without_freezing(self):
        self.start()
        r = self.runner
        r.watch_stop = Mock(wait=Mock(side_effect=[False, True]))
        self.now = 12.1
        r.watchdog()
        self.assertIn('startup lease expired', r.watch_error)
        r.cm.set_frozen.assert_not_called()

    def test_stale_sample_cannot_renew(self):
        self.start()
        r = self.runner
        r.records['xz']['actual_start_ns'] = 10_100_000_000
        self.now = 11.
        prior = r.clocks['xz'].lease_until
        with patch.object(r, 'read_sample', return_value=(10.6, 10.9, 3000 * MIB, {}, {})):
            r.control()
        self.assertEqual(r.clocks['xz'].lease_until, prior)
        self.assertEqual(r.decision_stream.getvalue(), '')

    def test_recovery_writes_soft_limit_before_confirmed_thaw(self):
        self.start()
        r = self.runner
        r.records['xz']['actual_start_ns'] = 10_100_000_000
        self.now = 10.3
        r.freeze_started('xz', 'realtime_pressure')
        with patch('realtime_runner.memory', return_value={'MemAvailable': 3000 * MIB}), \
                patch('realtime_runner.write_memory_high', lambda group, target:
                      (group / 'memory.high').write_text(str(target))):
            self.now = 11.5
            r.control()
            self.now = 12.
            r.control()
        row = json.loads(r.decision_stream.getvalue().splitlines()[-1])
        self.assertEqual(row['resumed'], 'xz')
        self.assertLessEqual(row['limits']['xz']['confirmed_ns'], r.freeze_rows[-1]['requested_monotonic_ns'])
        self.assertEqual(r.records['xz']['release_confirmed_ns'], 10_000_000_000)


if __name__ == '__main__':
    unittest.main()
