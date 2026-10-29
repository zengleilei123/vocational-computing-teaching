"""Negative controls for target selection, accounting and durable evidence.

These tests exercise actual unittest outcomes and real temporary files. They do
not require a browser, and their success does not imply a student app passed.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from acceptance.robot_portfolio import runner
from acceptance.robot_portfolio.browser import ConfigError


# This is an adapter for dependency/configuration checks only. It is never used
# to operate a page and is deliberately independent of the teacher's selectors.
SELECTORS = '''map_editor map_input map_apply map_title name archives save load
delete import_file export_file feedback error presets bfs dijkstra comparisons
frame state energy steps reset move_right brush_wall brush_play grid_cells
student_strategy demo_data pad_cells recognize prediction execute sample_count
sample_label add_test evaluate evaluation k'''.split()


def adapter_document(kind='student'):
    return {
        'schema_version': 1, 'target_kind': kind, 'label': '配置阻塞验证',
        'source_files': [{'url': '/app.js', 'path': 'app.js'}],
        'storage_keys': ['learner:maps'], 'duplicate_policy': 'reject',
        'confirmation': 'native',
        'selectors': {name: {'css': '#' + name} for name in SELECTORS},
    }


def arguments(root, *, cases='A01,A09', adapter=None, output=None, **overrides):
    values = {
        'url': 'http://127.0.0.1:8765', 'adapter': str(adapter or root / 'adapter.json'),
        'source_root': str(root), 'output': str(output or root / 'evidence'),
        'cases': cases, 'allow_reference': False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def invoke(args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = runner.run(args)
    return code, stdout.getvalue(), stderr.getvalue()


class RunnerResultTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='robot-acceptance-result-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def execute(self, methods, selected):
        # Keeping deliberately failing test classes local prevents discovery
        # from executing those negative controls as repository test failures.
        probe = type('OutcomeProbe', (unittest.TestCase,), methods)
        suite = unittest.TestSuite(probe(name) for name in methods)
        report = runner.make_report('http://127.0.0.1:8765/',
                                    self.root / 'adapter.json', self.root, selected)
        result_factory = lambda stream, descriptions, verbosity: runner.EvidenceResult(
            stream, descriptions, verbosity, report, self.root)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0,
                                         resultclass=result_factory).run(suite)
        code = runner.finish_report(report, result)
        return code, report, result

    def test_all_twelve_real_outcomes_pass_without_issuing_a_grade(self):
        methods = {f'test_{identifier}_observation': lambda self: self.assertEqual(2 + 2, 4)
                   for identifier in runner.CASE_IDS}
        code, report, result = self.execute(methods, list(runner.CASE_IDS))
        self.assertEqual(code, 0)
        self.assertEqual(result.testsRun, 12)
        self.assertTrue(report['all_contract_automated_pass'])
        self.assertEqual(report['acceptance_decision'], 'not_issued')
        self.assertTrue(all(item['status'] == 'not_reviewed' for item in report['manual_review']))

    def test_selected_success_keeps_unselected_cases_not_run(self):
        code, report, _ = self.execute({'test_A09_observation': lambda self: None}, ['A09'])
        self.assertEqual(code, 0)
        self.assertTrue(report['selected_automated_pass'])
        self.assertFalse(report['all_contract_automated_pass'])
        self.assertEqual(report['tests_run'], 1)
        self.assertEqual(report['cases']['A09']['status'], 'passed')
        self.assertEqual({item['status'] for key, item in report['cases'].items() if key != 'A09'},
                         {'not_run'})

    def test_empty_suite_never_counts_as_acceptance(self):
        code, report, _ = self.execute({}, ['A01'])
        self.assertEqual(code, 1)
        self.assertEqual(report['tests_run'], 0)
        self.assertFalse(report['selected_automated_pass'])
        self.assertFalse(report['all_contract_automated_pass'])

    def test_missing_case_is_not_hidden_by_other_successes(self):
        code, report, _ = self.execute({'test_A01_observation': lambda self: None}, ['A01', 'A02'])
        self.assertEqual(code, 1)
        self.assertEqual(report['expected_count'], 2)
        self.assertEqual(report['tests_run'], 1)
        self.assertEqual(report['cases']['A02']['status'], 'not_run')

    def test_skipped_requirement_is_blocked_and_cannot_pass(self):
        method = unittest.skip('页面能力尚未适配')(lambda self: None)
        code, report, result = self.execute({'test_A01_observation': method}, ['A01'])
        self.assertTrue(result.wasSuccessful(), 'This proves the extra acceptance gate matters.')
        self.assertEqual(code, 1)
        self.assertEqual(report['skipped'], 1)
        self.assertEqual(report['cases']['A01']['status'], 'blocked')
        self.assertIn('尚未适配', report['cases']['A01']['errors'][0])

    def test_expected_failure_and_unexpected_success_cannot_pass(self):
        def failure(self):
            self.fail('known business defect')
        for body in (failure, lambda self: None):
            with self.subTest(body=body.__name__):
                code, report, _ = self.execute(
                    {'test_A09_observation': unittest.expectedFailure(body)}, ['A09'])
                self.assertEqual(code, 1)
                self.assertEqual(report['cases']['A09']['status'], 'failed')
                self.assertFalse(report['selected_automated_pass'])

    def test_subtest_failure_is_retained_when_later_subtest_passes(self):
        def body(self):
            for value in (1, 2):
                with self.subTest(value=value):
                    self.assertEqual(value, 2, 'bad map was accepted')
        code, report, _ = self.execute({'test_A06_observation': body}, ['A06'])
        self.assertEqual(code, 1)
        self.assertEqual(report['cases']['A06']['status'], 'failed')
        self.assertIn('bad map was accepted', '\n'.join(report['cases']['A06']['errors']))

    def test_failures_and_runtime_errors_are_separate_from_not_run(self):
        def failure(self):
            self.fail('not persisted')
        def error(self):
            raise RuntimeError('page execution broke')
        code, report, _ = self.execute(
            {'test_A01_observation': failure, 'test_A02_observation': error}, ['A01', 'A02'])
        self.assertEqual(code, 1)
        self.assertEqual(report['tests_run'], 2)
        self.assertEqual(report['cases']['A01']['status'], 'failed')
        self.assertEqual(report['cases']['A02']['status'], 'failed')
        self.assertEqual(report['cases']['A03']['status'], 'not_run')
        self.assertIn('RuntimeError', report['cases']['A02']['errors'][0])

    def test_unrecognised_test_id_cannot_supply_success_for_requested_id(self):
        code, report, _ = self.execute({'test_not_an_acceptance_id': lambda self: None}, ['A01'])
        self.assertEqual(code, 1)
        self.assertTrue(report['runner_errors'])
        self.assertEqual(report['cases']['A01']['status'], 'not_run')

    def test_nested_suite_ids_preserve_duplicates_and_invalid_names(self):
        probe = type('IdentifierProbe', (unittest.TestCase,), {
            'test_A01_good': lambda self: None,
            'test_A01BAD': lambda self: None,
            'test_A12_good': lambda self: None,
        })
        suite = unittest.TestSuite([
            unittest.TestSuite([probe('test_A01_good'), probe('test_A01_good')]),
            probe('test_A01BAD'), probe('test_A12_good'),
        ])
        self.assertEqual(runner.suite_ids(suite), ['A01', 'A01', None, 'A12'])

    def test_artifact_error_cannot_hide_original_failure(self):
        def failure(self):
            self.fail('original map failure')
        def screenshot(self, output):
            raise OSError('screenshot directory denied')
        probe = type('ScreenshotProbe', (unittest.TestCase,), {
            'test_A09_failure': failure, 'capture_artifacts': screenshot,
        })
        report = runner.make_report('http://localhost:8765/', self.root / 'a.json', self.root, ['A09'])
        factory = lambda stream, descriptions, verbosity: runner.EvidenceResult(
            stream, descriptions, verbosity, report, self.root)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=factory).run(
            unittest.TestSuite([probe('test_A09_failure')]))
        self.assertEqual(runner.finish_report(report, result), 1)
        self.assertIn('original map failure', report['cases']['A09']['errors'][0])
        self.assertIn('screenshot directory denied', report['cases']['A09']['artifact_errors'][0])

    def test_interrupted_case_is_incomplete_while_prior_real_failure_is_retained(self):
        def failure(self):
            self.fail('confirmed business failure')
        def interrupted(self):
            raise KeyboardInterrupt()
        probe = type('InterruptProbe', (unittest.TestCase,), {
            'test_A01_failure': failure, 'test_A02_interrupt': interrupted,
        })
        report = runner.make_report('http://localhost:8765/', self.root / 'a.json',
                                    self.root, ['A01', 'A02', 'A03'])
        captured = []
        def factory(stream, descriptions, verbosity):
            result = runner.EvidenceResult(stream, descriptions, verbosity, report, self.root)
            captured.append(result)
            return result
        with self.assertRaises(KeyboardInterrupt):
            unittest.TextTestRunner(stream=io.StringIO(), resultclass=factory).run(
                unittest.TestSuite([probe('test_A01_failure'), probe('test_A02_interrupt')]))
        runner.finish_report(report, captured[0])
        self.assertEqual(report['tests_run'], 2)
        self.assertEqual(report['cases']['A01']['status'], 'failed')
        self.assertEqual(report['cases']['A02']['status'], 'blocked')
        self.assertEqual(report['cases']['A03']['status'], 'not_run')
        self.assertFalse(report['selected_automated_pass'])


class RunnerTargetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='robot-acceptance-target-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_only_explicit_local_http_endpoints_are_accepted(self):
        for value in ('http://127.0.0.1:8765', 'http://localhost:8765/', 'http://[::1]:8765/app/'):
            with self.subTest(value=value):
                self.assertTrue(runner.parse_endpoint(value).endswith('/'))
        invalid = ('https://127.0.0.1:8765/', 'http://example.com:8765/',
                   'http://127.0.0.1/', 'http://localhost:0/', 'http://localhost:65536/',
                   'http://student:secret@localhost:8765/', 'http://localhost:8765/?teacher=1',
                   'http://localhost:8765/#teacher', 'http://localhost:8765/\n',
                   'file:///tmp/answer.html', 'http://localhost:8765\\@example.com/')
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ConfigError):
                runner.parse_endpoint(value)

    def test_case_selection_rejects_empty_unknown_duplicates_and_typos(self):
        self.assertEqual(runner.select_cases('A12,A01,A09'), ['A01', 'A09', 'A12'])
        for value in ('', 'A00', 'A13', 'a01', 'A1', 'A01,A01', 'A01, A02', 'A01,'):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                runner.select_cases(value)

    def test_source_bytes_are_hashed_and_traversal_is_rejected(self):
        (self.root / 'app.js').write_bytes(b'abc')
        config = {'source_files': [{'url': '/app.js', 'path': 'app.js'}]}
        records = runner.local_source_files(config, self.root)
        self.assertEqual(records[0]['local_bytes'], 3)
        self.assertEqual(records[0]['local_sha256'],
                         'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
        for name in ('../app.js', str(self.root / 'app.js'), 'dir\\app.js', 'Z:app.js'):
            with self.subTest(path=name), self.assertRaisesRegex(ConfigError, 'source-root|根目录|相对'):
                runner.local_source_files({'source_files': [{'url': '/app.js', 'path': name}]}, self.root)

    def test_unknown_git_identity_does_not_borrow_enclosing_repository(self):
        # The root contains no .git even though the caller may be in a checkout.
        with mock.patch.object(runner.subprocess, 'run', side_effect=AssertionError('must not run git')):
            observed = runner.git_identity(self.root)
        self.assertEqual(observed, {'kind': 'unknown', 'commit': None, 'dirty': None})

    def test_existing_evidence_directory_is_not_reused_or_overwritten(self):
        output = self.root / 'evidence'
        output.mkdir()
        marker = output / 'report.json'
        marker.write_bytes(b'{"old_pass":true}')
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        code, _, stderr = invoke(arguments(self.root))
        self.assertEqual(code, 2)
        self.assertIn('报告目录', stderr)
        self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)

    def assert_blocked(self, args):
        code, _, _ = invoke(args)
        self.assertEqual(code, 2)
        report = json.loads((Path(args.output) / 'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['tests_run'], 0)
        self.assertTrue(report['blockers'])
        self.assertFalse(report['selected_automated_pass'])
        self.assertFalse(report['all_contract_automated_pass'])
        for identifier in report['selected_ids']:
            self.assertEqual(report['cases'][identifier]['status'], 'blocked')
        self.assertEqual(report['cases']['A02']['status'], 'not_run')
        self.assertTrue((Path(args.output) / 'summary.md').is_file())
        return report

    def test_missing_adapter_and_malformed_json_leave_blocked_evidence(self):
        self.assert_blocked(arguments(self.root, output=self.root / 'missing'))
        adapter = self.root / 'adapter.json'
        raw = b'{"broken": '
        adapter.write_bytes(raw)
        report = self.assert_blocked(arguments(self.root, output=self.root / 'malformed'))
        self.assertEqual(report['adapter_sha256'], hashlib.sha256(raw).hexdigest())

    def test_missing_playwright_is_not_reported_as_failed_student_business_logic(self):
        (self.root / 'app.js').write_bytes(b'// local student source\n')
        (self.root / 'adapter.json').write_text(json.dumps(adapter_document()), encoding='utf-8')
        with mock.patch.dict('sys.modules', {'playwright': None, 'playwright.sync_api': None}):
            report = self.assert_blocked(arguments(self.root))
        self.assertIn('Playwright', report['blockers'][0])
        self.assertEqual(report['purpose'], 'student_project_evidence')

    def test_reference_permission_is_explicit_and_cannot_override_student_target(self):
        for kind, flag in (('reference', False), ('student', True)):
            with self.subTest(kind=kind):
                (self.root / 'adapter.json').write_text(json.dumps(adapter_document(kind)), encoding='utf-8')
                report = self.assert_blocked(arguments(
                    self.root, output=self.root / kind, allow_reference=flag))
                self.assertIn('--allow-reference', report['blockers'][0])

    def test_report_json_keeps_unicode_and_summary_cannot_break_out_of_identity_block(self):
        report = runner.make_report('http://localhost:8765/', self.root / 'a.json', self.root, ['A09'])
        report['label'] = '学生甲\n```\n# 冒充全通过'
        runner.finish_report(report)
        runner.write_report(report, self.root)
        stored = json.loads((self.root / 'report.json').read_text(encoding='utf-8'))
        summary = (self.root / 'summary.md').read_text(encoding='utf-8')
        self.assertEqual(stored['label'], report['label'])
        self.assertEqual(summary.count('```'), 2)
        self.assertIn('| A09 | 未运行 |', summary)
        self.assertIn('不是评分', summary)


if __name__ == '__main__':
    unittest.main()
