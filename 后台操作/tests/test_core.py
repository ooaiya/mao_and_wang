import csv
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from oomlab.common import ROOT, GIB, profile, save_json, load_json
from oomlab.environment import check_controls, check_environment, CONTROLS
from oomlab.metrics import FIELDS, EVENTS, event_delta, snapshot, read_curve
from oomlab.report import align, stats, generate, eligible
from oomlab.services import valid_unit, stop_owned, start, SLICE
from oomlab.workloads import prepare, execute, verify, validate_input


class CoreTests(unittest.TestCase):
    def test_profiles(self):
        for op in ('xz', 'table', 'array_processing'):
            for size in ('small', 'medium', 'large'):
                self.assertTrue(profile(ROOT / 'configs/profiles.json', op, size))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'p.json'
            for value in [True, 0, -1, 1.5, '96']:
                save_json(f, {'schema_version': 1, 'xz': {'x': {'input_mib': 1, 'dict_mib': value, 'threads': 1}}})
                with self.assertRaises(ValueError):
                    profile(f, 'xz', 'x')

    def test_cv_sample_standard_deviation(self):
        self.assertEqual(stats([])['cv'], None)
        self.assertEqual(stats([1])['cv'], None)
        self.assertEqual(stats([0, 0])['cv'], None)
        self.assertAlmostEqual(stats([90, 100, 110])['cv'], .1)
        self.assertEqual(stats([10, 10, 10])['cv'], 0)

    def test_alignment_interpolation_missing_tail(self):
        curves = [[{'relative_s': 0, 'memory_current': 10},
                   {'relative_s': 2, 'memory_current': 30}],
                  [{'relative_s': 0, 'memory_current': 20},
                   {'relative_s': 1, 'memory_current': 40}]]
        rows = align(curves, [2, 1], .5)
        self.assertEqual(rows[1]['memory_current_mean'], 22.5)
        self.assertEqual(rows[2]['memory_current_mean'], 30)
        self.assertEqual(rows[3]['memory_current_n'], 1)
        self.assertEqual(rows[3]['memory_current_mean'], 25)
        self.assertEqual(rows[3]['stat_anon_n'], 0)
        with self.assertRaises(ValueError):
            align(curves, [2, 1], 0)

    def test_no_extrapolation_or_after_end(self):
        curve = [{'relative_s': .1, 'memory_current': 10}, {'relative_s': .5, 'memory_current': 20}]
        rows = align([curve], [.3], .1)
        self.assertEqual(rows[0]['memory_current_n'], 0)
        self.assertEqual(rows[-1]['memory_current_n'], 1)
        self.assertEqual(align([], [], .05), [])

    def test_event_deltas_and_unknown(self):
        a = {'event_oom': 5, 'event_oom_kill': 2, 'event_max': 9}
        b = {'event_oom': 7, 'event_oom_kill': 3, 'event_max': 100}
        result = event_delta(a, b)
        self.assertEqual(result['oom'], 2)
        self.assertEqual(result['oom_kill'], 1)
        self.assertEqual(result['max'], 91)
        self.assertIsNone(result['high'])
        with self.assertRaises(ValueError):
            event_delta(b, a)

    def test_missing_controls_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, '缺少.*memory.current'):
                check_controls(d)
            for name in CONTROLS:
                (Path(d) / name).write_text('0')
            check_controls(d)
            with patch.object(Path, 'read_text', side_effect=PermissionError):
                with self.assertRaisesRegex(RuntimeError, '无权读取'):
                    check_controls(d)

    def test_env_permission_error(self):
        with patch('oomlab.environment.privileged', side_effect=PermissionError('sudo denied')), \
             patch('oomlab.environment.resource_check', return_value={}):
            info = check_environment('.')
        self.assertFalse(info['ok'])
        self.assertTrue(any('sudo' in e for e in info['errors']))

    def test_cleanup_rejects_unrelated_units(self):
        for name in ('ssh.service', 'oomlab-a-*.service', '../x', 'oomlab-a-bad.service'):
            with self.assertRaises(ValueError):
                valid_unit(name)

    def test_cleanup_ownership(self):
        unit = 'oomlab-a-' + 'a' * 32 + '.service'
        status = {'Id': unit, 'Description': 'foreign', 'Slice': SLICE,
                  'ControlGroup': '/oomlab.slice/' + SLICE + '/' + unit}
        inspection = {'existence': 'present', 'properties': status}
        with patch('oomlab.services.inspect_unit', return_value=inspection), \
             patch('oomlab.services.privileged') as privileged:
            with self.assertRaisesRegex(RuntimeError, '归属不匹配'):
                stop_owned(unit, '/tmp/foreign')
            privileged.assert_not_called()
        status['Description'] = 'oomlab-stage-a:/tmp/owned'
        with patch('oomlab.services.inspect_unit', return_value=inspection), \
             patch('oomlab.services.privileged', return_value=subprocess.CompletedProcess([], 0, '', '')) as privileged:
            self.assertEqual(stop_owned(unit, '/tmp/owned')['status'], 'stopped')
            self.assertEqual(privileged.call_args_list[0].args[0], ['systemctl', 'stop', unit])
            self.assertEqual(privileged.call_count, 2)

    def test_service_only_local_limits(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.services.privileged', return_value=subprocess.CompletedProcess([], 0, '', '')) as call:
            start('oomlab-a-' + 'b'*32 + '.service', Path(d), 'experiment', 8*GIB,
                  10, '/usr/bin/python3', ROOT, ['/usr/bin/sleep', '.1'])
        args = call.call_args.args[0]
        self.assertIn('--property=MemoryMax=' + str(8*GIB), args)
        self.assertIn('--property=User=experiment', args)
        self.assertIn('--property=MemorySwapMax=0', args)
        self.assertIn('--property=MemoryAccounting=yes', args)
        self.assertIn('--property=OOMPolicy=continue', args)
        self.assertIn('--property=KillMode=control-group', args)
        self.assertFalse(any('MemoryOOMGroup' in a for a in args))
        self.assertNotIn('set-property', args)
        self.assertIn('--slice=oomlab-a.slice', args)

    def test_report_failed_round_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            s = Path(d)
            save_json(s / 'session.json', {'operation': 'xz', 'profile': 'test', 'parameters': {}, 'requested_rounds': 4})
            for i in range(4):
                run = s / str(i)
                run.mkdir()
                m = {'run_id': str(i), 'success': i != 3, 'verified': True, 'cleanup_ok': True,
                     'peak_bytes': (2 if i != 3 else 10)*GIB, 'anon_sampled_peak_bytes': GIB,
                     'duration_s': 1, 'events_delta': {'max': 0, 'oom': 0, 'oom_kill': 0}, 'returncode': 0,
                     'reason': None if i != 3 else 'invalid checksum'}
                save_json(run / 'metadata.json', m)
                with open(run / 'raw.csv', 'w', newline='') as f:
                    w = csv.DictWriter(f, FIELDS)
                    w.writeheader()
                    w.writerows([{'relative_s': t, 'memory_current': 2*GIB} for t in [0, 1]])
            r = generate(s)
            self.assertEqual(r['valid_rounds'], 3)
            self.assertEqual(r['peak_bytes']['mean'], 2*GIB)
            self.assertFalse(r['qualified'])
            self.assertIn('invalid checksum', (s / 'report.md').read_text())
            self.assertTrue((s / 'mean.csv').exists())

    def test_report_empty_not_run(self):
        with tempfile.TemporaryDirectory() as d:
            save_json(Path(d) / 'session.json', {'operation': 'table', 'profile': 'large',
                       'parameters': {}, 'requested_rounds': 3})
            r = generate(d)
            self.assertEqual(r['status'], 'NOT_RUN')
            self.assertFalse(r['qualified'])
            self.assertIsNone(r['peak_bytes']['mean'])

    def test_qualification_thresholds_and_corrupt_curve(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_json(root / 'session.json', {'operation': 'table', 'profile': 'test',
                      'parameters': {}, 'requested_rounds': 3})
            for i in range(3):
                run = root / str(i)
                run.mkdir()
                save_json(run / 'metadata.json', {'run_id': str(i), 'success': True,
                          'verified': True, 'cleanup_ok': True, 'peak_bytes': 2*GIB,
                          'anon_sampled_peak_bytes': GIB, 'duration_s': 1,
                          'events_delta': {'max': 0, 'oom': 0, 'oom_kill': 0}})
                (run / 'raw.csv').write_text('relative_s,memory_current\n0,1\n1,2\n')
            self.assertTrue(generate(root)['qualified'])
            meta_path = root / '0' / 'metadata.json'
            meta = load_json(meta_path)
            for peak in (GIB-1, 3_000_000_001, 16*GIB):
                meta['peak_bytes'] = peak
                save_json(meta_path, meta)
                self.assertFalse(generate(root)['qualified'])
            meta['peak_bytes'] = 2*GIB
            meta['events_delta']['max'] = 1
            save_json(meta_path, meta)
            self.assertEqual(generate(root)['valid_rounds'], 2)
            meta['events_delta']['max'] = 0
            save_json(meta_path, meta)
            (root / '0' / 'raw.csv').write_text('relative_s,memory_current\n')
            r = generate(root)
            self.assertFalse(r['qualified'])
            self.assertEqual(r['valid_rounds'], 2)
            self.assertIn('原始曲线为空', (root / 'report.md').read_text())

    def test_cli_nonfinite_arguments_rejected(self):
        from oomlab.cli import parser
        from oomlab.common import positive
        for value in ['nan', 'inf', '-1', '0']:
            with self.assertRaises(ValueError):
                positive(value)
        self.assertEqual(parser().parse_args(['smoke']).rounds, 3)

    def test_unknown_oom_or_failure_invalid(self):
        m = {'success': True, 'verified': True, 'cleanup_ok': True, 'duration_s': 1, 'peak_bytes': GIB}
        self.assertFalse(eligible(m))
        m['events_delta'] = {'max': 0, 'oom': 0, 'oom_kill': 0}
        self.assertTrue(eligible(m))
        m['events_delta']['oom_kill'] = 1
        self.assertFalse(eligible(m))

    def test_real_small_workloads(self):
        configurations = {'xz': {'input_mib': 1, 'dict_mib': 1, 'threads': 1},
                          'table': {'rows': 300, 'users': 30, 'categories': 32, 'days': 31, 'extras': 4},
                          'array_processing': {'elements': 128, 'dtype': 'float64', 'arrays': 3,
                                               'chunk_elements': 32, 'seed': 20261026}}
        with tempfile.TemporaryDirectory() as d:
            for op, p in configurations.items():
                with self.subTest(operation=op):
                    data = Path(d) / op
                    out = Path(d) / (op + '-out')
                    out.mkdir()
                    prepare(op, p, data)
                    validate_input(data, op, p)
                    execute(data, out)
                    self.assertTrue(verify(data, out)['ok'])
                    with self.assertRaises(FileExistsError):
                        prepare(op, p, data)
                    (data / load_json(data / 'manifest.json')['file']).write_bytes(b'bad')
                    with self.assertRaises(ValueError):
                        validate_input(data, op, p)

    def test_worker_sleep_and_readonly_cgroup_sampling(self):
        # Real sleep + real cgroup reads, NOT isolated systemd validation.
        cg = Path('/sys/fs/cgroup')
        if not all((cg / n).exists() for n in ('memory.current', 'memory.peak', 'memory.stat', 'memory.events')):
            self.skipTest('read-only cgroup metrics unavailable')
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            p = subprocess.Popen([sys.executable, '-m', 'oomlab.worker', d, '/usr/bin/sleep', '.12'], cwd=ROOT)
            try:
                deadline = time.monotonic() + 5
                while not (run / 'ready.json').exists():
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(.01)
                self.assertFalse((run / 'finished.json').exists())
                (run / 'go').touch()
                rows = []
                start_ns = time.monotonic_ns()
                while not (run / 'finished.json').exists():
                    self.assertLess(time.monotonic(), deadline)
                    rows.append(snapshot(cg, start_ns))
                    time.sleep(.02)
                self.assertGreaterEqual(len(rows), 2)
                finish = load_json(run / 'finished.json')
                self.assertEqual(finish['returncode'], 0)
                self.assertGreater(finish['duration_s'], .1)
                self.assertIsNone(p.poll())  # supervisor remains for terminal cgroup read
                self.assertGreater(rows[-1]['monotonic_ns'], rows[0]['monotonic_ns'])
                event_delta(rows[0], rows[-1])
            finally:
                p.terminate()
                p.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
