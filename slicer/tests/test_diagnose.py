"""Synthetic crash diagnostic tests; no engine or debugger execution."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from slicer.builder import diagnose


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.build = self.output / 'build'
        logs = self.build / 'Testing/Temporary'
        logs.mkdir(parents=True)
        (logs / 'LastTest.log').write_text('1/2 Testing: crashed\nSIGSEGV - Segmentation\n2/2 Testing: assertion\nFAILED:\n')
        self.original = {'compiled': True, 'tests_passed': False, 'state': 'failed', 'printer_ready': False}
        (self.output / 'build-report.json').write_text(json.dumps(self.original))
        binary = self.build / 'test-bin'
        binary.write_text('synthetic, never executed')
        self.test = {'name': 'crashed', 'command': [str(binary), 'exclude:[NotWorking]'],
                     'properties': [{'name': 'WORKING_DIRECTORY', 'value': str(self.build)}]}
        guard = patch.object(diagnose, 'PRODUCTION_MARKER', self.output / 'absent')
        guard.start()
        self.addCleanup(guard.stop)

    def test_selects_crashes_not_assertions(self):
        self.assertEqual(diagnose.crash_tests('1/2 Testing: x\nSIGABRT - abort\n2/2 Testing: y\nFAILED:\n'), {'x'})

    def test_cad_host_and_unconfirmed_rejected(self):
        with self.assertRaises(ValueError):
            diagnose.diagnose(self.output)
        with patch.object(diagnose, 'PRODUCTION_MARKER', self.output):
            with self.assertRaises(ValueError):
                diagnose.diagnose(self.output, True)
        self.assertFalse((self.output / 'crash-diagnostics').exists())

    def test_outside_binary_and_directory_rejected(self):
        for test in [dict(self.test, command=['/bin/true']),
                     dict(self.test, properties=[{'name': 'WORKING_DIRECTORY', 'value': '/tmp'}])]:
            with self.assertRaises(ValueError):
                diagnose.checked_test(test, self.build)

    def test_gate_and_timeout_bounds(self):
        with self.assertRaises(ValueError):
            diagnose.diagnose(self.output, True, timeout=121)
        (self.output / 'build-report.json').write_text(json.dumps(dict(self.original, compiled=False)))
        with self.assertRaises(ValueError):
            diagnose.diagnose(self.output, True)

    def test_missing_debugger_records_unavailability(self):
        with patch.object(diagnose.shutil, 'which', return_value=None), patch.object(diagnose.subprocess, 'run') as run:
            summary = diagnose.diagnose(self.output, True)
        self.assertIn('unavailable', summary)
        run.assert_not_called()

    def exercise(self, timeout=False):
        listing = subprocess.CompletedProcess([], 0, stdout=json.dumps({'tests': [self.test]}))
        process = MagicMock(pid=12345, returncode=0)
        if timeout:
            process.wait.side_effect = [subprocess.TimeoutExpired('gdb', 120), 0]
        with patch.object(diagnose.shutil, 'which', return_value='/usr/bin/gdb'), \
                patch.object(diagnose.subprocess, 'run', return_value=listing), \
                patch.object(diagnose.subprocess, 'Popen', return_value=process) as popen, \
                patch.object(diagnose.os, 'killpg') as kill, \
                patch.dict(diagnose.os.environ, {'GITHUB_TOKEN': 'secret', 'DEBUGINFOD_URLS': 'https://invalid'}):
            summary = diagnose.diagnose(self.output, True)
        kill.assert_called_once_with(12345, diagnose.signal.SIGKILL)
        args, kwargs = popen.call_args
        self.assertIn('-nx', args[0])
        self.assertEqual(args[0][-2:], self.test['command'])
        self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
        self.assertEqual(kwargs['env']['DEBUGINFOD_URLS'], '')
        self.assertTrue(kwargs['start_new_session'])
        self.assertIs(kwargs['preexec_fn'], diagnose.disable_core_dumps)
        self.assertEqual(summary['runs'][0]['timeout'], timeout)
        self.assertFalse(summary['printer_ready'])
        self.assertEqual(json.loads((self.output / 'build-report.json').read_text()), self.original)
        with self.assertRaises(FileExistsError):
            diagnose.diagnose(self.output, True)

    def test_rerun_preserves_selection_credentials_and_failed_gate(self):
        self.exercise()

    def test_ctest_inventory_cannot_destroy_original_evidence(self):
        logs = self.build / 'Testing/Temporary'
        original = (logs / 'LastTest.log').read_bytes()
        (logs / 'LastTestsFailed.log').write_text('1:crashed\n')

        def inventory(*args, **kwargs):
            (logs / 'LastTest.log').write_text('Start testing\nEnd testing\n')
            (logs / 'LastTestsFailed.log').unlink()
            return subprocess.CompletedProcess([], 0, stdout=json.dumps({'tests': [self.test]}))

        process = MagicMock(pid=12345, returncode=0)
        with patch.object(diagnose.shutil, 'which', return_value='/usr/bin/gdb'), \
                patch.object(diagnose.subprocess, 'run', side_effect=inventory), \
                patch.object(diagnose.subprocess, 'Popen', return_value=process), \
                patch.object(diagnose.os, 'killpg'):
            summary = diagnose.diagnose(self.output, True)
        saved = self.output / 'crash-diagnostics'
        self.assertEqual((saved / 'LastTest.log').read_bytes(), original)
        self.assertEqual((saved / 'LastTestsFailed.log').read_text(), '1:crashed\n')
        self.assertEqual(summary['runs'][0]['suite'], 'crashed')
        self.assertFalse(summary['printer_ready'])

    def test_timeout_kills_debugger_and_descendants(self):
        self.exercise(timeout=True)


if __name__ == '__main__':
    unittest.main()
