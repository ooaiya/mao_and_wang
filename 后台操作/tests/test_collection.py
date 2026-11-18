"""Controller integration with explicit fake service boundary, no fake experiment results."""
import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from oomlab.common import ROOT, GIB, load_json, save_json
from oomlab.collect import collect_one, collect_session
from oomlab.environment import CONTROLS
from oomlab.metrics import EVENTS
from oomlab.report import generate


class CollectionTests(unittest.TestCase):
    def test_preflight_failure_preserves_report(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.collect.check_environment', return_value={'ok': False, 'errors': ['no systemd']}):
            with self.assertRaisesRegex(RuntimeError, 'no systemd'):
                collect_session(d, 'smoke', 'sleep', {}, None, rounds=1, smoke=True)
            session = next(Path(d).iterdir())
            self.assertEqual(load_json(session / 'summary.json')['status'], 'PREFLIGHT_FAILED')
            self.assertFalse(load_json(session / 'summary.json')['qualified'])

    def test_start_failure_evidence(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.collect.resource_check', return_value={}), \
             patch('oomlab.collect.services.start', side_effect=PermissionError('sudo denied')):
            m = collect_one(d, 'smoke', 'sleep', {}, None, smoke=True)
            self.assertFalse(m['success'])
            self.assertIn('sudo denied', m['reason'])
            self.assertTrue((Path(m['run_directory']) / 'raw.csv').exists())
            self.assertTrue((Path(m['run_directory']) / 'metadata.json').exists())

    def test_controller_sampling_through_fake_service_boundary(self):
        # Fake only service management + kernel files, run actual gated worker and sleep.
        # These temporary files are never delivered as real experiment results.
        from oomlab.metrics import snapshot as actual_snapshot
        with tempfile.TemporaryDirectory() as d:
            session = Path(d)
            cg = session / 'fake-cgroup'
            cg.mkdir()
            for name in CONTROLS:
                (cg / name).write_text('0')
            (cg / 'memory.current').write_text(str(4*1024**2))
            (cg / 'memory.peak').write_text(str(5*1024**2))
            (cg / 'memory.stat').write_text('anon 2097152\nfile 1048576\nkernel 1048576\n')
            (cg / 'memory.events').write_text('\n'.join(k+' 0' for k in EVENTS)+'\n')
            processes = []
            def start(unit, run, user, safety, timeout, python, root, workload):
                status.update(Id=unit, Description='oomlab-stage-a:' + str(run), Slice='oomlab-a.slice',
                              ControlGroup='/oomlab.slice/oomlab-a.slice/' + unit)
                processes.append(subprocess.Popen([python, '-m', 'oomlab.worker', str(run)]+workload, cwd=root))
            def stop(unit, run, creation_failed=False):
                processes[-1].terminate()
                processes[-1].wait(timeout=5)
                return {'status': 'stopped', 'message': '已停止指定服务'}
            status = {'ControlGroup': '/oomlab-a.slice/test.service', 'MainPID': '123', 'MemoryMax': str(8*GIB)}
            try:
                with patch('oomlab.collect.resource_check', return_value={}), \
                     patch('oomlab.collect.services.start', side_effect=start), \
                     patch('oomlab.collect.services.show', return_value=status), \
                     patch('oomlab.collect.services.inspect_unit', return_value={'existence': 'present', 'properties': status}), \
                     patch('oomlab.collect.services.stop_owned', side_effect=stop), \
                     patch('oomlab.collect.check_controls'), \
                     patch('oomlab.collect.is_populated', return_value=True), \
                     patch('oomlab.collect.snapshot', side_effect=lambda _, t: actual_snapshot(cg, t)), \
                     patch('oomlab.collect.privileged', return_value=subprocess.CompletedProcess([], 0, '', '')):
                    m = collect_one(session, 'smoke', 'sleep', {}, None, interval=.02, smoke=True)
                self.assertTrue(m['success'], m['reason'])
                self.assertTrue(m['cleanup_ok'])
                self.assertIsNotNone(m['pid'])
                self.assertEqual(m['events_delta']['oom_kill'], 0)
                with open(Path(m['run_directory']) / 'raw.csv') as f:
                    self.assertGreater(len(list(csv.DictReader(f))), 2)
                save_json(session / 'session.json', {'operation': 'smoke', 'profile': 'sleep',
                          'parameters': {}, 'requested_rounds': 1})
                self.assertFalse(generate(session)['qualified'])
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=5)

    def test_cleanup_failure_stops_remaining_rounds(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.collect.check_environment', return_value={'ok': True, 'errors': []}), \
             patch('oomlab.collect.collect_one', return_value={'success': False, 'cleanup_ok': False}) as one:
            session, results = collect_session(d, 'smoke', 'sleep', {}, None, rounds=3, smoke=True)
            self.assertEqual(one.call_count, 1)
            self.assertEqual(len(results), 1)
            self.assertEqual(load_json(session / 'session.json')['status'], 'FAILED')

    def test_lock_rejects_another_collector(self):
        import fcntl
        lock = Path('/tmp') / f'oomlab-stage-a-{os.getuid()}.lock'
        with open(lock, 'a') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, '已有阶段 A 采集'):
                collect_session('unused', 'smoke', 'sleep', {}, None, smoke=True)


if __name__ == '__main__':
    unittest.main()
