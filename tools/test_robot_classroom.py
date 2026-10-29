"""Exercise the classroom CLI and the actual unpacked student project.

Run from the repository root:
    python -m unittest discover -s tools -p 'test_*.py' -v

Socket tests use real loopback ports. No browser, Node, network download, or
third-party Python package is required. Git metadata tests use Git if present.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TOOL = Path('tools/robot_classroom.py')
ROBOT_FILES = (
    'projects/robot_playground/__init__.py',
    'projects/robot_playground/engine.py',
    'projects/robot_playground/glyphs.py',
    'projects/robot_playground/server.py',
    'projects/robot_playground/student_strategy.py',
    'projects/robot_playground/test_playground.py',
    'projects/robot_playground/static/app.js',
    'projects/robot_playground/static/index.html',
    'projects/robot_playground/static/style.css',
    'projects/robot_playground/tools/browser_smoke.py',
    'projects/robot_playground/README.md',
    'projects/robot_playground/TEACHING.md',
    'projects/robot_playground/CHALLENGES.md',
    'projects/robot_playground/SOURCES.md',
)
COPIED_FILES = ROBOT_FILES + (
    'curriculum/ai-assisted-development/CAPSTONE.md',
    'curriculum/ai-assisted-development/WORK-CARDS.md',
    'curriculum/ai-assisted-development/SOURCES.md',
    'classroom/robot_portfolio/student/START.md',
    'classroom/robot_portfolio/student/DIAGNOSTIC.md',
    'classroom/robot_portfolio/student/WORKBOOK.md',
    'classroom/robot_portfolio/student/SUBMISSION.md',
    'tools/robot_classroom.py',
    'LICENSE-CODE',
    'LICENSE-DOCS.md',
)
FIXTURE_NAMES = (
    'valid-map.json', 'invalid-json.json', 'unknown-version.json',
    'missing-goal.json', 'duplicate-start.json', 'unequal-rows.json',
    'html-name.json', 'unicode-name-40.json', 'boundary-16384.json',
    'oversize-16385.json', 'README.md',
)


def environment(**changes):
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    env['PYTHONUTF8'] = '1'
    env.update(changes)
    return env


def available_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def command(args, cwd, env=None, timeout=30):
    return subprocess.run(
        args, cwd=cwd, env=environment() if env is None else env,
        capture_output=True, text=True, encoding='utf-8', timeout=timeout,
    )


def run_tool(*args, root=ROOT, cwd=None, env=None, no_site=False):
    prefix = [sys.executable] + (['-S'] if no_site else [])
    return command(prefix + [str(root / TOOL), *map(str, args)],
                   cwd=root if cwd is None else cwd, env=env)


def copy_source(destination):
    for relative in COPIED_FILES:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return destination


def load_tool(root):
    spec = importlib.util.spec_from_file_location('classroom_tool_under_test', root / TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def partial_write_failure(output, failure, observed):
    """Inject only the final write; create and flush a real 32-byte file first."""
    original_open = Path.open

    class InterruptedWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, data):
            self.stream.write(data[:32])
            self.stream.flush()
            observed.append(output.read_bytes())
            raise failure

    def open_file(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path == output and mode == 'xb':
            return InterruptedWriter(stream)
        return stream

    return mock.patch.object(Path, 'open', open_file)


class DoctorTests(unittest.TestCase):
    def test_doctor_from_another_directory_reports_root_and_real_port(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            port = available_port()
            result = run_tool('doctor', '--port', port, '--json', cwd=elsewhere)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertTrue(report['ready'])
            self.assertEqual(Path(report['root']), ROOT)
            checks = {check['id']: check for check in report['checks']}
            for name in ('python', 'files', 'port'):
                self.assertTrue(checks[name]['required'])
                self.assertEqual(checks[name]['status'], 'pass')
            self.assertEqual(checks['cwd']['status'], 'warning')
            self.assertIn(str(ROOT), report['commands']['change_directory'])
            self.assertIn('projects.robot_playground.server', report['commands']['start'])
            self.assertIn(str(port), report['commands']['start'])

    def test_occupied_loopback_port_is_a_required_failure(self):
        with socket.socket() as listener:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            result = run_tool('doctor', '--port', port, '--json')
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertFalse(report['ready'])
        check = next(item for item in report['checks'] if item['id'] == 'port')
        self.assertEqual(check['status'], 'fail')
        self.assertIn(str(port), check['message'])
        self.assertIn('占用', check['message'])

    def test_invalid_ports_are_rejected_before_diagnosis(self):
        for value in ('-1', '0', '65536', 'not-a-port'):
            with self.subTest(port=value):
                result = run_tool('doctor', '--port', value, '--json')
                self.assertEqual(result.returncode, 2)
                self.assertIn('1', result.stderr)
                self.assertIn('65535', result.stderr)

    def test_missing_optional_tools_do_not_block_basic_run_or_claim_browser_tested(self):
        result = run_tool('doctor', '--port', available_port(), '--json',
                          env=environment(PATH=''), no_site=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report['ready'])
        checks = {item['id']: item for item in report['checks']}
        for name in ('node', 'playwright'):
            self.assertFalse(checks[name]['required'])
            self.assertEqual(checks[name]['status'], 'warning')
        self.assertEqual(checks['chromium']['status'], 'not_checked')
        self.assertIn('未检查', checks['chromium']['message'])

    def test_missing_runtime_file_is_actionable_and_does_not_install_or_repair_it(self):
        with tempfile.TemporaryDirectory() as temp:
            source = copy_source(Path(temp) / '学生 source')
            missing = source / 'projects/robot_playground/engine.py'
            missing.unlink()
            result = run_tool('doctor', '--port', available_port(), '--json', root=source)
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report['ready'])
            check = next(item for item in report['checks'] if item['id'] == 'files')
            self.assertEqual(check['status'], 'fail')
            self.assertIn('engine.py', check['message'])
            self.assertFalse(missing.exists())

    def test_human_output_gives_next_command_and_scope_without_json_flag(self):
        port = available_port()
        result = run_tool('doctor', '--port', port)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('projects.robot_playground.server', result.stdout)
        self.assertIn(str(port), result.stdout)
        self.assertIn('环境', result.stdout)
        self.assertIn('功能验收', result.stdout)

    def test_doctor_outputs_utf8_when_pipe_defaults_to_cp1252(self):
        env = environment(PYTHONUTF8='0', PYTHONIOENCODING='cp1252')
        for arguments in (['--json'], []):
            with self.subTest(arguments=arguments):
                result = run_tool('doctor', '--port', available_port(), *arguments, env=env)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                if arguments:
                    report = json.loads(result.stdout)
                    self.assertTrue(report['ready'])
                    self.assertIn('当前 Python', report['checks'][0]['message'])
                else:
                    self.assertIn('基础运行条件已满足', result.stdout)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = copy_source(self.directory / '学生 source')
        self.output = self.directory / 'output' / 'student.zip'

    def bundle(self, output=None):
        result = run_tool('bundle', '--output', self.output if output is None else output,
                          root=self.source, cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return zipfile.ZipFile(self.output if output is None else output)

    def make_symlink(self, link, target, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            if os.name == 'nt' and getattr(exc, 'winerror', None) == 1314:
                self.skipTest('当前 Windows 账户没有创建符号链接的权限。')
            raise

    def test_bundle_copies_only_explicit_inputs_and_never_adds_answers_or_git(self):
        for relative in ('teacher_reference/secret.py', '.git/private-note',
                         'projects/robot_playground/answer.py', 'personal.txt'):
            extra = self.source / relative
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_text('must not leave the source tree', encoding='utf-8')
        with self.bundle() as archive:
            expected = set(COPIED_FILES) | {'README.md', 'MANIFEST.json'} | {
                f'fixtures/{name}' for name in FIXTURE_NAMES
            }
            self.assertEqual(set(archive.namelist()), expected)
            for relative in COPIED_FILES:
                self.assertEqual(archive.read(relative), (self.source / relative).read_bytes())
            self.assertTrue(all('..' not in Path(name).parts for name in archive.namelist()))
        self.assertTrue((self.source / 'personal.txt').exists())

    def test_manifest_covers_every_payload_with_actual_byte_size_and_sha256(self):
        with self.bundle() as archive:
            manifest = json.loads(archive.read('MANIFEST.json'))
            self.assertEqual(manifest['format_version'], 1)
            self.assertIsNone(manifest['source']['commit'])
            self.assertIsNone(manifest['source']['dirty'])
            entries = {entry['path']: entry for entry in manifest['files']}
            self.assertEqual(set(entries), set(archive.namelist()) - {'MANIFEST.json'})
            for name, entry in entries.items():
                data = archive.read(name)
                self.assertEqual(entry['bytes'], len(data))
                self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())

    def test_same_content_and_source_metadata_produce_identical_archives(self):
        with self.bundle():
            pass
        second = self.directory / 'second.zip'
        with self.bundle(second):
            pass
        self.assertEqual(self.output.read_bytes(), second.read_bytes())

    def test_fixtures_have_the_promised_independent_failure_and_byte_boundaries(self):
        with self.bundle() as archive:
            def fixture(name):
                return json.loads(archive.read('fixtures/' + name))

            self.assertEqual(fixture('valid-map.json'), {
                'version': 1, 'name': '校园地图', 'grid': ['S..', '.#.', '..G'],
            })
            with self.assertRaises(json.JSONDecodeError):
                fixture('invalid-json.json')
            self.assertEqual(fixture('unknown-version.json')['version'], 2)
            self.assertNotIn('G', ''.join(fixture('missing-goal.json')['grid']))
            self.assertEqual(''.join(fixture('duplicate-start.json')['grid']).count('S'), 2)
            self.assertGreater(len(set(map(len, fixture('unequal-rows.json')['grid']))), 1)
            self.assertEqual(fixture('html-name.json')['name'], '<b>地图</b>')
            self.assertEqual(len(fixture('unicode-name-40.json')['name']), 40)
            self.assertGreater(len(fixture('unicode-name-40.json')['name'].encode('utf-16-le')), 80)
            boundary = archive.read('fixtures/boundary-16384.json')
            oversized = archive.read('fixtures/oversize-16385.json')
            self.assertEqual(len(boundary), 16384)
            self.assertEqual(len(oversized), 16385)
            self.assertEqual(oversized, boundary + b' ')
            self.assertEqual(json.loads(boundary), json.loads(oversized))
            self.assertEqual(json.loads(boundary)['grid'], ['S..', '.#.', '..G'])

    def test_missing_source_refuses_to_publish_a_partial_archive(self):
        (self.source / 'projects/robot_playground/engine.py').unlink()
        result = run_tool('bundle', '--output', self.output, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('engine.py', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob('*')), [])

    def test_existing_output_file_and_directory_are_never_overwritten(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep these bytes')
        result = run_tool('bundle', '--output', self.output, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'keep these bytes')
        result = run_tool('bundle', '--output', self.output.parent, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'keep these bytes')

    def test_interrupted_zip_write_removes_partial_output_and_reraises_interrupt(self):
        tool = load_tool(self.source)
        interrupt = KeyboardInterrupt('simulate Ctrl+C after actual bytes reached disk')
        observed = []
        with partial_write_failure(self.output, interrupt, observed):
            with self.assertRaises(KeyboardInterrupt) as caught:
                tool.bundle(self.source, self.output)
        self.assertIs(caught.exception, interrupt)
        self.assertEqual([len(data) for data in observed], [32])
        self.assertEqual(observed[0][:4], b'PK\x03\x04')
        self.assertFalse(self.output.exists(), '中断不能留下看似可发放的半个 ZIP。')
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_oserror_during_zip_write_removes_partial_output_and_preserves_other_archive(self):
        tool = load_tool(self.source)
        self.output.parent.mkdir()
        existing = self.output.parent / 'previous-student.zip'
        existing.write_bytes(b'previous verified archive')
        observed = []
        with partial_write_failure(self.output, OSError('simulated disk full'), observed):
            with self.assertRaises(tool.ClassroomError):
                tool.bundle(self.source, self.output)
        self.assertEqual([len(data) for data in observed], [32])
        self.assertFalse(self.output.exists())
        self.assertEqual(existing.read_bytes(), b'previous verified archive')
        self.assertEqual(list(self.output.parent.iterdir()), [existing])

    def test_output_created_before_exclusive_open_is_preserved(self):
        tool = load_tool(self.source)
        original_open = Path.open

        def racing_open(path, mode='r', *args, **kwargs):
            if path == self.output and mode == 'xb':
                with original_open(path, 'wb') as existing:
                    existing.write(b'archive created by someone else')
            return original_open(path, mode, *args, **kwargs)

        with mock.patch.object(Path, 'open', racing_open):
            with self.assertRaises(tool.ClassroomError):
                tool.bundle(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b'archive created by someone else')

    def test_bundle_success_output_is_utf8_when_pipe_defaults_to_cp1252(self):
        result = run_tool('bundle', '--output', self.output, root=self.source,
                          env=environment(PYTHONUTF8='0', PYTHONIOENCODING='cp1252'))
        self.assertTrue(zipfile.is_zipfile(self.output), '包本身必须完整。')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('学生包已生成', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_bundle_error_is_utf8_when_pipe_defaults_to_cp1252(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b'keep this existing archive')
        result = run_tool('bundle', '--output', self.output, root=self.source,
                          env=environment(PYTHONUTF8='0', PYTHONIOENCODING='cp1252'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('输出目标已存在', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(self.output.read_bytes(), b'keep this existing archive')

    def test_symbolic_link_file_source_is_rejected_before_creating_output(self):
        candidate = self.source / 'projects/robot_playground/engine.py'
        outside = self.directory / 'outside.py'
        candidate.rename(outside)
        self.make_symlink(candidate, outside)
        result = run_tool('bundle', '--output', self.output, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('符号链接', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertTrue(candidate.is_symlink())
        self.assertEqual(outside.read_bytes(), (ROOT / 'projects/robot_playground/engine.py').read_bytes())

    def test_symbolic_link_parent_inside_source_is_also_rejected(self):
        candidate = self.source / 'projects/robot_playground/static'
        outside = self.directory / 'outside-static'
        candidate.rename(outside)
        self.make_symlink(candidate, outside, directory=True)
        result = run_tool('bundle', '--output', self.output, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('符号链接', result.stderr)
        self.assertFalse(self.output.exists())

    def test_dangling_symbolic_link_output_is_not_followed_or_replaced(self):
        self.output.parent.mkdir()
        target = self.directory / 'must-not-be-created.zip'
        self.make_symlink(self.output, target)
        result = run_tool('bundle', '--output', self.output, root=self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(target.exists())

    @unittest.skipUnless(shutil.which('git'), 'Git 未安装；Git 元数据分支无法实测。')
    def test_nested_non_git_source_does_not_claim_the_outer_repository_commit(self):
        git = shutil.which('git')
        for args in (
            ['init', '-q'], ['add', '.'],
            ['-c', 'user.name=Classroom Test', '-c', 'user.email=classroom@example.invalid',
             'commit', '-qm', 'unrelated outer repository'],
        ):
            result = command([git, *args], self.directory)
            self.assertEqual(result.returncode, 0, result.stderr)
        with self.bundle() as archive:
            source = json.loads(archive.read('MANIFEST.json'))['source']
            self.assertIsNone(source['commit'])
            self.assertIsNone(source['dirty'])

    @unittest.skipUnless(shutil.which('git'), 'Git 未安装；Git 元数据分支无法实测。')
    def test_working_tree_metadata_reports_commit_and_real_uncommitted_changes(self):
        git = shutil.which('git')
        for args in (
            ['init', '-q'], ['add', '.'],
            ['-c', 'user.name=Classroom Test', '-c', 'user.email=classroom@example.invalid',
             'commit', '-qm', 'student source'],
        ):
            result = command([git, *args], self.source)
            self.assertEqual(result.returncode, 0, result.stderr)
        commit = command([git, 'rev-parse', 'HEAD'], self.source).stdout.strip()
        with self.bundle() as archive:
            source = json.loads(archive.read('MANIFEST.json'))['source']
            self.assertEqual(source['commit'], commit)
            self.assertFalse(source['dirty'])
        engine = self.source / 'projects/robot_playground/engine.py'
        engine.write_bytes(engine.read_bytes() + b'\n# student working-tree change\n')
        with self.bundle(self.directory / 'dirty.zip') as archive:
            source = json.loads(archive.read('MANIFEST.json'))['source']
            self.assertEqual(source['kind'], 'working-tree')
            self.assertEqual(source['commit'], commit)
            self.assertTrue(source['dirty'])
            self.assertEqual(archive.read('projects/robot_playground/engine.py'), engine.read_bytes())

    def test_unpacked_unicode_space_path_runs_37_original_tests_and_serves_student_page(self):
        extracted = self.directory / '解压 学生目录'
        with self.bundle() as archive:
            archive.extractall(extracted)
        for relative in ROBOT_FILES:
            self.assertEqual((extracted / relative).read_bytes(), (ROOT / relative).read_bytes())
        imported = command([
            sys.executable, '-c',
            "import importlib.util; assert importlib.util.find_spec('teacher_reference') is None",
        ], extracted)
        self.assertEqual(imported.returncode, 0, imported.stderr)
        baseline = command([
            sys.executable, '-m', 'unittest', 'discover', '-s', 'projects/robot_playground',
            '-p', 'test_*.py', '-v',
        ], extracted)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        self.assertRegex(baseline.stderr, r'Ran 37 tests\b')

        port = available_port()
        process = subprocess.Popen([
            sys.executable, '-m', 'projects.robot_playground.server', '--port', str(port),
        ], cwd=extracted, env=environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 8
            while True:
                try:
                    with opener.open(f'http://127.0.0.1:{port}', timeout=1) as response:
                        html = response.read()
                    break
                except (urllib.error.URLError, TimeoutError):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail('解压后的学生 HTTP 服务未按时启动。')
                    time.sleep(0.05)
            self.assertEqual(html, (extracted / 'projects/robot_playground/static/index.html').read_bytes())
            self.assertIn('校园机器人挑战场'.encode('utf-8'), html)
            self.assertNotIn(b'portfolio-save', html)
            self.assertNotIn(b'portfolio-name', html)
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)

        # Doctor describes environment readiness; it must not grade legitimate
        # student edits by treating the original manifest hashes as immutable.
        script = extracted / 'projects/robot_playground/static/app.js'
        script.write_bytes(script.read_bytes() + b'\n// student change\n')
        result = run_tool('doctor', '--port', available_port(), '--json', root=extracted)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)['ready'])


if __name__ == '__main__':
    unittest.main()
