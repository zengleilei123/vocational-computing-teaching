"""Real-HTTP calibration and negative controls for the student-target runner.

These are tool self-tests, not student scores. Variants are temporary derivatives
of the isolated teacher reference; they never enter the student distribution.
Requires the same Playwright/Chromium setup as the existing browser suite.
"""
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / 'teacher_reference/robot_map_portfolio'


@contextmanager
def serving(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def silent(base):
    class QuietHandler(base):
        def log_message(self, *args):
            pass
    return QuietHandler


def reference_config():
    return json.loads((REFERENCE / 'acceptance-adapter.json').read_text(encoding='utf-8'))


@contextmanager
def fixture(kind):
    """Change UI IDs, storage container and JS scope without editing source files."""
    from teacher_reference.robot_map_portfolio.server import Handler, render_index

    with tempfile.TemporaryDirectory(prefix='robot-adapter-fixture-') as directory:
        root = Path(directory)
        config = reference_config()
        config['label'] = '验收器校准夹具 ' + kind
        index = render_index().decode('utf-8')
        core = (REFERENCE / 'static/portfolio-core.js').read_text(encoding='utf-8')
        ui = (REFERENCE / 'static/portfolio-ui.js').read_text(encoding='utf-8')
        app = (ROOT / 'projects/robot_playground/static/app.js').read_text(encoding='utf-8')
        css = (REFERENCE / 'static/portfolio.css').read_text(encoding='utf-8')
        if kind == 'object-and-private-state':
            index = index.replace('portfolio-', 'fixture-')
            index = index.replace('>请确认地图操作</h2>', '><b>请确认地图操作</b></h2>')
            ui = ui.replace('portfolio-', 'fixture-')
            css = css.replace('portfolio-', 'fixture-')
            core = core.replace("'robot-map-portfolio:v1'", "'fixture-object-store:v1'")
            core = core.replace('JSON.stringify(records)', 'JSON.stringify({entries: records})')
            core = core.replace('entries = JSON.parse(raw);', 'entries = JSON.parse(raw).entries;')
            core = core.replace('  function persist(storage, records) {',
                                '  const cachedSetItem = localStorage.setItem.bind(localStorage);\n'
                                '  function persist(storage, records) {')
            core = core.replace('storage.setItem(STORAGE_KEY,', 'cachedSetItem(STORAGE_KEY,')
            # A successful load/export may update internal metadata. Only
            # rejected operations must preserve the raw archive bytes exactly.
            metadata = ("      { const key = 'fixture-object-store:v1'; "
                        "const saved = JSON.parse(localStorage.getItem(key)); "
                        "saved.observations = (saved.observations || 0) + 1; "
                        "localStorage.setItem(key, JSON.stringify(saved)); }\n")
            ui = ui.replace('      report(`已加载地图', metadata + '      report(`已加载地图')
            ui = ui.replace("      report('已导出当前地图 JSON。", metadata + "      report('已导出当前地图 JSON。")
            config['storage_keys'] = ['fixture-object-store:v1']
            for definition in config['selectors'].values():
                for key, value in list(definition.items()):
                    definition[key] = value.replace('portfolio-', 'fixture-')
            # Both app and portfolio UI now share only a private lexical scope.
            # The acceptance suite cannot obtain the map through global `grid`.
            ui = '(function () {\n' + app + '\n' + ui + '\n})();\n'
            index = index.replace('<script src="/app.js" defer></script>', '')
        elif kind == 'native-reject':
            start = ui.index('  function ask(message) {')
            end = ui.index('  // Lock both map changes', start)
            ui = ui[:start] + ('  function ask(message) {\n'
                              '    return Promise.resolve(window.confirm("确认这次操作？"));\n'
                              '  }\n\n') + ui[end:]
            ui = ui.replace("if (error.code !== 'duplicate') throw error;",
                            "if (error.code !== 'duplicate') throw error;\n      throw error;")
            ui = ui.replace('status.textContent = message;',
                            "status.textContent = error ? '操作未完成，未保存成功。' + message : message;")
            ui = ui.replace('  renderRecords(initial.records);',
                            "  renderRecords(initial.records);\n"
                            "  if (initial.warnings.length) byId('portfolio-save').disabled = true;")
            config['confirmation'] = 'native'
            config['duplicate_policy'] = 'reject'
            for key in ('confirm_dialog', 'confirm_yes', 'confirm_no'):
                del config['selectors'][key]
        elif kind != 'fault':
            raise ValueError(kind)

        payloads = {'/': ('index.html', index, 'text/html; charset=utf-8'),
                    '/app.js': ('app.js', app, 'text/javascript; charset=utf-8'),
                    '/portfolio-core.js': ('core.js', core, 'text/javascript; charset=utf-8'),
                    '/portfolio-ui.js': ('ui.js', ui, 'text/javascript; charset=utf-8'),
                    '/portfolio.css': ('portfolio.css', css, 'text/css; charset=utf-8')}
        if kind == 'object-and-private-state':
            # The renamed HTML also changed its script URL; preserve explicit paths.
            payloads['/fixture-core.js'] = payloads.pop('/portfolio-core.js')
            payloads['/fixture-ui.js'] = payloads.pop('/portfolio-ui.js')
        for relative, text, _mime in payloads.values():
            (root / relative).write_text(text, encoding='utf-8', newline='\n')
        config['source_files'] = [{'url': url, 'path': item[0]} for url, item in payloads.items()]

        class FixtureHandler(silent(Handler)):
            def do_GET(self):
                if self.path in payloads:
                    if not self.allowed():
                        return self.send(403, {'error': 'loopback only'})
                    relative, _text, mime = payloads[self.path]
                    return self.send(200, (root / relative).read_bytes(), mime)
                return super().do_GET()

        with serving(FixtureHandler) as url:
            yield root, url, config


class BrowserHarnessControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='robot-harness-controls-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        configured = os.environ.get('ROBOT_ACCEPTANCE_TEST_EVIDENCE')
        cls.evidence = Path(configured).resolve() if configured else cls.work / 'evidence'
        cls.evidence.mkdir(parents=True, exist_ok=True)
        # Import failure must fail this calibration gate, never become a skip.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            launch = {'headless': True}
            if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
                launch['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
            browser = playwright.chromium.launch(**launch)
            browser.close()

    def run_target(self, label, url, config, source=ROOT, cases=None, allow_reference=True):
        adapter = self.work / (label + '.json')
        adapter.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        output = self.evidence / label
        command = [sys.executable, '-m', 'acceptance.robot_portfolio', '--url', url,
                   '--adapter', str(adapter), '--source-root', str(source), '--output', str(output)]
        if cases:
            command += ['--cases', cases]
        if allow_reference:
            command += ['--allow-reference']
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=180)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'console.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
        report_file = output / 'report.json'
        self.assertTrue(report_file.is_file(), result.stdout + result.stderr)
        return result, json.loads(report_file.read_text(encoding='utf-8'))

    def assert_full_pass(self, result, report):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['tests_run'], 12)
        self.assertEqual(report['skipped'], 0)
        self.assertTrue(report['all_contract_automated_pass'])
        self.assertEqual(report['purpose'], 'reference_calibration')
        self.assertEqual(report['acceptance_decision'], 'not_issued')
        self.assertTrue(all(item['status'] == 'passed' for item in report['cases'].values()))
        self.assertTrue(all(item['matches'] for item in report['target']['assets']))

    def test_reference_calibration_runs_all_twelve_on_explicit_url(self):
        from teacher_reference.robot_map_portfolio.server import Handler
        with serving(silent(Handler)) as url:
            result, report = self.run_target('reference-all', url, reference_config())
        self.assert_full_pass(result, report)

    def test_changed_ids_object_storage_and_private_js_scope_still_pass(self):
        with fixture('object-and-private-state') as (root, url, config):
            result, report = self.run_target('variant-object-private', url, config, root)
            self.assert_full_pass(result, report)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                launch = {'headless': True}
                if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
                    launch['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
                browser = playwright.chromium.launch(**launch)
                try:
                    page = browser.new_page()
                    page.goto(url)
                    page.locator('#grid button').first.wait_for(state='visible')
                    # The grid element's ID exposes a named window property;
                    # only this DOM node remains, not the app's lexical row array.
                    self.assertFalse(page.evaluate('Array.isArray(grid)'))
                    self.assertTrue(page.evaluate('grid instanceof HTMLElement'))
                    page.get_by_label('地图名称', exact=True).fill('对象容器')
                    page.get_by_role('button', name='保存地图', exact=True).click()
                    page.wait_for_function("localStorage.getItem('fixture-object-store:v1') !== null")
                    raw = page.evaluate("localStorage.getItem('fixture-object-store:v1')")
                    self.assertIsInstance(json.loads(raw), dict)
                finally:
                    browser.close()

    def test_native_confirmation_and_reject_duplicate_policy(self):
        with fixture('native-reject') as (root, url, config):
            result, report = self.run_target('variant-native-reject', url, config, root)
        self.assert_full_pass(result, report)
        self.assertTrue(any('native' in str(item).lower() or '原生' in str(item)
                            for item in report['manual_review']))

    def test_starter_without_portfolio_cannot_pass(self):
        from projects.robot_playground.server import Handler
        config = reference_config()
        config['target_kind'], config['label'] = 'student', '未实现功能的原始起点负对照'
        config['source_files'] = [{'url': '/app.js', 'path': 'projects/robot_playground/static/app.js'}]
        config['timeout_ms'] = 1000
        with serving(silent(Handler)) as url:
            result, report = self.run_target('starter-negative', url, config, cases='A01', allow_reference=False)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report['tests_run'], 1)
        self.assertEqual(report['cases']['A01']['status'], 'failed')
        self.assertFalse(report['all_contract_automated_pass'])
        self.assertEqual(report['cases']['A12']['status'], 'not_run')

    def test_teacher_page_cannot_be_relabelled_as_a_student_target(self):
        from teacher_reference.robot_map_portfolio.server import Handler
        config = reference_config()
        config['target_kind'] = 'student'
        with serving(silent(Handler)) as url:
            result, report = self.run_target('wrong-teacher-target', url, config, allow_reference=False)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(report['tests_run'], 0)
        self.assertIn('教师参考', '\n'.join(report['blockers']))
        self.assertIsNotNone(report['target']['final_url'])

    def test_mismatched_source_and_wrong_url_block_before_business_cases(self):
        from teacher_reference.robot_map_portfolio.server import Handler
        with serving(silent(Handler)) as url:
            config = reference_config()
            config['source_files'][0]['path'] = 'README.md'
            result, report = self.run_target('source-mismatch', url, config)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(report['tests_run'], 0)
            observed = report['target']['assets'][0]
            self.assertFalse(observed['matches'])
            self.assertNotEqual(observed['local_sha256'], observed['served_sha256'])
            missing, missing_report = self.run_target('missing-page', url + 'missing-page', reference_config())
            self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
            self.assertEqual(missing_report['tests_run'], 0)

    def test_existing_fault_patch_is_detected_and_reversal_passes(self):
        git = shutil.which('git')
        self.assertIsNotNone(git, 'The patch reversal control requires Git; it must not be skipped.')
        with fixture('fault') as (root, url, config):
            target = root / 'teacher_reference/robot_map_portfolio/static/portfolio-core.js'
            target.parent.mkdir(parents=True)
            shutil.copyfile(root / 'core.js', target)
            patch = REFERENCE / 'exercises/storage-write-failure/fault.patch'
            # Apply the actual supplied patch to a temporary tree, then serve it.
            before = target.read_bytes()
            applied = subprocess.run([git, 'apply', str(patch)], cwd=root, capture_output=True, text=True)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            shutil.copyfile(target, root / 'core.js')
            faulty, failed_report = self.run_target('fault-a09', url, config, root, cases='A09')
            self.assertEqual(faulty.returncode, 1, faulty.stdout + faulty.stderr)
            self.assertEqual(failed_report['tests_run'], 1)
            failure = failed_report['cases']['A09']
            self.assertEqual(failure['status'], 'failed')
            # A missing browser or preparation error does not prove fault detection.
            self.assertTrue(any('AssertionError' in error for error in failure['errors']), failure['errors'])
            self.assertEqual(failed_report['blockers'], [])
            reversed_patch = subprocess.run([git, 'apply', '--reverse', str(patch)], cwd=root,
                                            capture_output=True, text=True)
            self.assertEqual(reversed_patch.returncode, 0, reversed_patch.stderr)
            self.assertEqual(target.read_bytes(), before)
            shutil.copyfile(target, root / 'core.js')
            restored, restored_report = self.run_target('restored-a09', url, config, root, cases='A09')
            self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
            self.assertTrue(restored_report['selected_automated_pass'])
            self.assertFalse(restored_report['all_contract_automated_pass'])
            self.assertEqual(restored_report['cases']['A01']['status'], 'not_run')


if __name__ == '__main__':
    unittest.main()
