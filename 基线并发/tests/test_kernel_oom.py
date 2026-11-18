"""TEST_ONLY subprocess fixtures. No real VM, OOM or Freezer is exercised."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'基线并发'))
from common import kernel_oom


class KernelOomTests(unittest.TestCase):
    def capture(self, journal, dmesg=None):
        timeline = SimpleNamespace(t0_ns=100_000_000_000,
            rows=[dict(event_type='runner_start', actual_monotonic_ns=99_000_000_000)],
            emit=mock.Mock())
        sink = SimpleNamespace(rows=[])
        sink.write = sink.rows.append
        operations = dict(xz=dict(pid=9000, cgroup_path='/sys/fs/cgroup/owned/xz'))
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            case = journal if command[0] == 'journalctl' else dmesg
            if case is None:
                raise AssertionError('unexpected fallback')
            if isinstance(case, BaseException):
                raise case
            code, text, error = case
            kwargs['stdout'].write(text)
            return subprocess.CompletedProcess(command, code, stderr=error)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                kernel_oom.subprocess, 'run', side_effect=run):
            evidence = kernel_oom.collect(directory, timeline, operations, 0, sink)
            files = {p.name: p.read_text() for p in Path(directory).iterdir()}
        return evidence, sink.rows, timeline, commands, files

    def test_ubuntu_2204_argument_contract_and_empty_journal(self):
        evidence, rows, timeline, commands, files = self.capture((0, '', ''))
        self.assertIn('-k', commands[0])
        self.assertNotIn('--kernel', commands[0])
        self.assertIn('--output=json', commands[0])
        self.assertEqual(len(commands), 1)
        self.assertEqual(evidence['status'], 'OBSERVED')
        self.assertEqual(evidence['assessment'], 'NO_OOM_FOUND')
        self.assertEqual(evidence['confirmed_kill_records'], 0)
        self.assertEqual(rows, [])
        timeline.emit.assert_not_called()

    def test_oom_victim_group_and_original_time_association(self):
        message = 'Memory cgroup out of memory: Killed process 4321 (xz) task_memcg=/owned/xz'
        raw = json.dumps(dict(MESSAGE=message, __MONOTONIC_TIMESTAMP='101500000'))+'\n'
        evidence, rows, timeline, commands, files = self.capture((0, raw, ''))
        self.assertEqual(evidence['assessment'], 'OOM_CONFIRMED')
        self.assertEqual(evidence['confirmed_kill_records'], 1)
        self.assertEqual(rows[0]['killed_pid'], 4321)
        self.assertEqual(rows[0]['operation'], 'xz')
        self.assertEqual(rows[0]['scope'], 'kernel_cgroup')
        self.assertEqual(rows[0]['relative_T0_s'], 1.5)
        self.assertEqual(rows[0]['counter'], 'kernel_kill_record')
        self.assertEqual(files['kernel_journal.jsonl'], raw)

    def test_non_oom_logs_do_not_create_events(self):
        raw = json.dumps(dict(MESSAGE='network link restored', __MONOTONIC_TIMESTAMP='101000000'))+'\n'
        evidence, rows, timeline, commands, files = self.capture((0, raw, ''))
        self.assertEqual(evidence['assessment'], 'NO_OOM_FOUND')
        self.assertEqual(evidence['candidate_messages'], 0)
        self.assertEqual(rows, [])
        timeline.emit.assert_not_called()

    def test_oom_without_victim_does_not_invent_attempt_count(self):
        raw = json.dumps(dict(MESSAGE='oom-kill:constraint=CONSTRAINT_NONE',
                              __MONOTONIC_TIMESTAMP='101000000'))+'\n'
        evidence, rows, timeline, commands, files = self.capture((0, raw, ''))
        self.assertEqual(evidence['assessment'], 'OOM_CONFIRMED')
        self.assertIsNone(evidence['attempt_count'])
        self.assertEqual(evidence['confirmed_kill_records'], 0)
        self.assertIsNone(rows[0]['killed_pid'])

    def test_readable_dmesg_fallback_keeps_failure_and_filters_old_records(self):
        text = '[ 50.000000] Out of memory: Killed process 1 (old)\n'
        text += '[ 102.250000] Out of memory: Killed process 9000 (python)\n'
        evidence, rows, timeline, commands, files = self.capture(
            (1, '', 'journal permission denied'), (0, text, ''))
        self.assertEqual(evidence['status'], 'OBSERVED')
        self.assertEqual(evidence['log_source'], 'dmesg')
        self.assertEqual(evidence['journalctl_failure'], 'journal permission denied')
        self.assertEqual(evidence['assessment'], 'OOM_CONFIRMED')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['killed_pid'], 9000)
        self.assertEqual(rows[0]['relative_T0_s'], 2.25)
        self.assertEqual(rows[0]['operation'], 'xz')
        self.assertEqual(files['kernel_dmesg.txt'], text)
        self.assertEqual(commands[1], ['dmesg', '--color=never', '--time-format=raw'])

    def test_both_sources_unavailable_are_unknown_never_zero(self):
        evidence, rows, timeline, commands, files = self.capture(
            (1, '', 'journal permission denied'), (1, '', 'dmesg: Operation not permitted'))
        self.assertEqual(evidence['status'], 'UNAVAILABLE')
        self.assertEqual(evidence['assessment'], 'UNKNOWN')
        self.assertIsNone(evidence['confirmed_kill_records'])
        self.assertIsNone(evidence['candidate_messages'])
        self.assertIsNone(evidence['attempt_count'])
        self.assertIn('journal permission denied', evidence['reason'])
        self.assertIn('Operation not permitted', evidence['reason'])
        self.assertEqual(rows, [])

    def test_missing_journalctl_can_use_permitted_empty_dmesg(self):
        evidence, rows, timeline, commands, files = self.capture(
            FileNotFoundError('journalctl missing'), (0, '', ''))
        self.assertEqual(evidence['assessment'], 'NO_OOM_FOUND')
        self.assertEqual(evidence['log_source'], 'dmesg')
        self.assertIn('FileNotFoundError', evidence['journalctl_failure'])
        self.assertEqual(rows, [])

    def test_malformed_journal_is_not_reported_as_zero_oom(self):
        evidence, rows, timeline, commands, files = self.capture(
            (0, '{bad json\n', ''), (1, '', 'permission denied'))
        self.assertEqual(evidence['status'], 'UNAVAILABLE')
        self.assertIsNone(evidence['confirmed_kill_records'])
        self.assertIn('parse failure', evidence['reason'])
        self.assertEqual(rows, [])

    def test_unaligned_dmesg_oom_record_remains_unknown(self):
        evidence, rows, timeline, commands, files = self.capture(
            (1, '', 'journal unreadable'), (0, 'Out of memory: Killed process 123 (unknown-time)\n', ''))
        self.assertEqual(evidence['status'], 'UNAVAILABLE')
        self.assertEqual(evidence['assessment'], 'UNKNOWN')
        self.assertIsNone(evidence['confirmed_kill_records'])
        self.assertEqual(rows, [])

    def test_timeout_preserves_reason_and_can_fall_back(self):
        evidence, rows, timeline, commands, files = self.capture(
            subprocess.TimeoutExpired(['journalctl', '-k'], 10), (0, '', ''))
        self.assertEqual(evidence['assessment'], 'NO_OOM_FOUND')
        self.assertIn('TimeoutExpired', evidence['journalctl_failure'])

    def test_missing_journal_timestamp_preserves_observation_fallback(self):
        raw = json.dumps(dict(MESSAGE='Out of memory: Killed process 9000 (python)'))+'\n'
        with mock.patch.object(kernel_oom.time, 'monotonic_ns', return_value=103_000_000_000):
            evidence, rows, timeline, commands, files = self.capture((0, raw, ''))
        self.assertEqual(rows[0]['monotonic_ns'], 103_000_000_000)
        self.assertEqual(timeline.emit.call_args.kwargs['source_timestamp'], 'collector observation fallback')

    def test_old_csv_fields_are_preserved(self):
        raw = json.dumps(dict(MESSAGE='Killed process 9000 (python)',
                              __MONOTONIC_TIMESTAMP='101000000'))+'\n'
        evidence, rows, timeline, commands, files = self.capture((0, raw, ''))
        self.assertEqual(set(rows[0]), {'monotonic_ns', 'relative_T0_s', 'scope',
            'operation', 'counter', 'delta', 'value', 'killed_pid', 'evidence'})
        for name in ('status', 'candidate_messages', 'confirmed_kill_records',
                     'attempt_count', 'attempt_count_reason'):
            self.assertIn(name, evidence)


if __name__ == '__main__':
    unittest.main()
