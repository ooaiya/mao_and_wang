"""systemd boundary tests; no real transient service is claimed here."""
import subprocess
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from oomlab.common import ROOT, GIB, load_json
from oomlab.collect import collect_one
from oomlab.services import CGROUP_PREFIX, ServiceError, inspect_unit, start, stop_owned

UNIT = 'oomlab-a-' + 'a' * 32 + '.service'


def absent(unit=UNIT, code=1):
    return subprocess.CompletedProcess([], code,
        f'Id={unit}\nLoadState=not-found\nActiveState=inactive\nMainPID=0\nControlGroup=\n', '')


def present(unit=UNIT, **changes):
    p = {'Id': unit, 'LoadState': 'loaded', 'ActiveState': 'active', 'MainPID': '123',
         'Description': 'oomlab-stage-a:/tmp/owned', 'Slice': 'oomlab-a.slice',
         'ControlGroup': CGROUP_PREFIX + '/' + unit}
    p.update(changes)
    return subprocess.CompletedProcess([], 0, ''.join(f'{k}={v}\n' for k, v in p.items()), '')


class ServiceTests(unittest.TestCase):
    def test_start_failure_captures_exact_output_and_status(self):
        with tempfile.TemporaryDirectory() as d, patch('oomlab.services.privileged',
             return_value=subprocess.CompletedProcess([], 1, 'manager stdout\n', 'Unknown assignment: MemoryOOMGroup=no\n')):
            with self.assertRaisesRegex(ServiceError, 'Unknown assignment') as caught:
                start(UNIT, Path(d), 'experiment', 8*GIB, 5, '/usr/bin/python3', ROOT, ['/usr/bin/sleep', '.1'])
            evidence = load_json(Path(d) / 'systemd-run.json')
            self.assertEqual(evidence, caught.exception.diagnostic)
            self.assertEqual(evidence['returncode'], 1)
            self.assertEqual(evidence['stdout'], 'manager stdout\n')
            self.assertEqual(evidence['stderr'], 'Unknown assignment: MemoryOOMGroup=no\n')
            self.assertFalse(any('MemoryOOMGroup' in arg for arg in evidence['command']))

    def test_missing_sudo_exit_code_remains_unknown(self):
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.services.privileged', side_effect=FileNotFoundError('sudo missing')):
            with self.assertRaises(ServiceError):
                start(UNIT, Path(d), 'experiment', 8*GIB, 5, '/usr/bin/python3', ROOT, ['/usr/bin/sleep', '.1'])
            evidence = load_json(Path(d) / 'systemd-run.json')
            self.assertIsNone(evidence['returncode'])
            self.assertIn('sudo missing', evidence['execution_error'])

    def test_absent_service_never_stopped_or_reset(self):
        for code in (0, 1, 4):
            with self.subTest(code=code), patch('oomlab.services.privileged', return_value=absent(code=code)) as call:
                result = stop_owned(UNIT, '/tmp/owned', creation_failed=True)
                self.assertEqual(result['status'], 'not_created')
                self.assertEqual(result['message'], '服务未创建，无需停止')
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args[0][:2], ['systemctl', 'show'])

    def test_permission_and_incomplete_queries_are_not_absence(self):
        replies = [subprocess.CompletedProcess([], 1, '', 'Access denied'),
                   subprocess.CompletedProcess([], 1, 'Id=' + UNIT + '\n', 'not found'),
                   subprocess.CompletedProcess([], 0, 'LoadState=not-found\n', ''),
                   absent(unit='other.service'),
                   subprocess.CompletedProcess([], 1, absent().stdout.replace('MainPID=0\n', ''), ''),
                   subprocess.CompletedProcess([], 1, absent().stdout.replace('ControlGroup=\n', ''), ''),
                   subprocess.CompletedProcess([], 1, absent().stdout.replace('MainPID=0', 'MainPID=123'), '')]
        for reply in replies:
            with self.subTest(reply=reply), patch('oomlab.services.privileged', return_value=reply) as call:
                with self.assertRaisesRegex(ServiceError, '无法确认') as caught:
                    stop_owned(UNIT, '/tmp/owned', creation_failed=True)
                self.assertEqual(caught.exception.diagnostic['existence'], 'unknown')
                self.assertEqual(call.call_count, 1)

    def test_existing_service_requires_all_ownership_fields(self):
        for change in [{'Description': 'foreign'}, {'Slice': 'system.slice'}, {'ControlGroup': ''},
                       {'ControlGroup': CGROUP_PREFIX + '/other.service'},
                       {'ControlGroup': '/foreign/oomlab-a.slice/' + UNIT}, {'Id': 'other.service'}]:
            with self.subTest(change=change), patch('oomlab.services.privileged', return_value=present(**change)) as call:
                with self.assertRaises(ServiceError):
                    stop_owned(UNIT, '/tmp/owned')
                self.assertEqual(call.call_count, 1)

    def test_partial_creation_can_stop_only_verified_existing_service(self):
        with patch('oomlab.services.privileged', side_effect=[present(),
                   subprocess.CompletedProcess([], 0, '', ''), subprocess.CompletedProcess([], 0, '', '')]) as call:
            result = stop_owned(UNIT, '/tmp/owned', creation_failed=True)
            self.assertEqual(result['status'], 'stopped')
            self.assertEqual(call.call_args_list[1].args[0], ['systemctl', 'stop', UNIT])
            self.assertEqual(call.call_args_list[2].args[0], ['systemctl', 'reset-failed', UNIT])

    def test_stop_failure_retains_error_and_never_resets(self):
        with patch('oomlab.services.privileged', side_effect=[present(),
                   subprocess.CompletedProcess([], 1, '', 'stop denied')]) as call:
            with self.assertRaisesRegex(ServiceError, 'stop denied') as caught:
                stop_owned(UNIT, '/tmp/owned')
            self.assertEqual(caught.exception.diagnostic['stop']['returncode'], 1)
            self.assertEqual(call.call_count, 2)

    def test_collector_failure_preserves_start_journal_and_cleanup(self):
        # Real start/inspect/cleanup logic, simulated subprocess results; no real systemd.
        def fake_privileged(args, check=True):
            if args[0] == 'systemd-run':
                return subprocess.CompletedProcess(args, 1, 'start output', 'Unknown assignment: rejected-property')
            if args[:2] == ['systemctl', 'show']:
                return absent(args[2])
            if args[0] == 'journalctl':
                return subprocess.CompletedProcess(args, 0, '-- No entries --\n', '')
            self.fail('Unexpected mutation: ' + repr(args))
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.collect.resource_check', return_value={}), \
             patch('oomlab.services.privileged', side_effect=fake_privileged), \
             patch('oomlab.collect.privileged', side_effect=fake_privileged):
            meta = collect_one(d, 'smoke', 'sleep', {}, None, smoke=True)
            run = Path(meta['run_directory'])
            self.assertFalse(meta['success'])
            self.assertTrue(meta['creation_failed'])
            self.assertIn('Unknown assignment: rejected-property', meta['reason'])
            self.assertTrue(meta['cleanup_ok'])
            self.assertEqual(meta['cleanup']['status'], 'not_created')
            self.assertIsNone(meta['cgroup'])
            self.assertIsNone(meta['pid'])
            self.assertEqual(meta['events_delta'], {})
            self.assertNotIn('peak_bytes', meta)
            self.assertEqual(meta['service_start']['returncode'], 1)
            self.assertEqual(meta['service_start']['stdout'], 'start output')
            self.assertEqual(load_json(run / 'metadata.json'), meta)
            self.assertEqual((run / 'journal.log').read_text(), '-- No entries --\n')
            self.assertEqual(load_json(run / 'cleanup.json')['status'], 'not_created')
            self.assertEqual(load_json(run / 'systemctl-show.json')['existence'], 'absent')

    def test_manual_cleanup_preserves_previous_evidence(self):
        from oomlab.cli import main
        from oomlab.common import save_json
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / UNIT.removeprefix('oomlab-a-').removesuffix('.service')
            run.mkdir()
            meta = {'unit': UNIT, 'run_directory': str(run), 'creation_failed': True}
            save_json(run / 'metadata.json', meta)
            (run / 'journal.log').write_text('old journal evidence')
            with patch('oomlab.services.privileged', return_value=absent()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['cleanup', str(run / 'metadata.json')]), 0)
            with patch('oomlab.services.privileged', return_value=present(Description='foreign')), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['cleanup', str(run / 'metadata.json')]), 2)
            evidence = [load_json(p) for p in run.glob('cleanup-retry-*.json')]
            self.assertEqual(len(evidence), 2)
            self.assertEqual({e['status'] for e in evidence}, {'not_created', 'refused_or_failed'})
            self.assertEqual(load_json(run / 'metadata.json'), meta)
            self.assertEqual((run / 'journal.log').read_text(), 'old journal evidence')

    def test_collector_unknown_ownership_preserves_diagnostic(self):
        def denied(args, check=True):
            return subprocess.CompletedProcess(args, 1, '', 'Access denied')
        with tempfile.TemporaryDirectory() as d, \
             patch('oomlab.collect.resource_check', return_value={}), \
             patch('oomlab.services.privileged', side_effect=denied), \
             patch('oomlab.collect.privileged', side_effect=denied):
            meta = collect_one(d, 'smoke', 'sleep', {}, None, smoke=True)
            self.assertFalse(meta['cleanup_ok'])
            self.assertIn('Access denied', meta['reason'])
            self.assertIn('无法确认', meta['cleanup_error'])
            self.assertEqual(meta['cleanup_diagnostic']['existence'], 'unknown')
            evidence = load_json(Path(meta['run_directory']) / 'cleanup.json')
            self.assertEqual(evidence['status'], 'refused_or_failed')


if __name__ == '__main__':
    unittest.main()
