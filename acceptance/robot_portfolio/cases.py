"""A01–A12 assertions against an explicit application through its UI adapter.

The fixture values and expected results below are independent of application
validators. This module imports neither the student app nor the reference app.
"""

import json
import re
import unittest
from pathlib import Path

from .browser import App, CASE_IDS


MAP_A = ['S..', '.#.', '..G']
MAP_B = ['S2G', '...', '.#.']
MAP_C = ['S#G', '###', '...']
PRESET_A = ['#########', '#S99999G#', '#.#####.#', '#.......#', '#########']
RIGHT_PIXELS = [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0]


def document(name='校园地图', rows=None):
    return {'version': 1, 'name': name, 'grid': list(MAP_A if rows is None else rows)}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


class PortfolioCases(unittest.TestCase):
    """A browser/config/URL is attached by build_suite, never chosen implicitly."""

    def setUp(self):
        self.apps = []
        self.artifacts = []
        self.manual_checks = []
        self.app = self.new_app()

    def new_app(self, *, initial_storage=None):
        app = App(self.browser, self.config, self.url, initial_storage=initial_storage)
        self.apps.append(app)
        self.addCleanup(app.close)
        app.open()
        return app

    def tearDown(self):
        for app in self.apps:
            self.assertEqual(app.errors, [], 'The tested page raised uncaught JavaScript errors.')
            self.assertEqual(app.blocked_requests, [], 'The tested page requested an undeclared remote origin.')
            self.assertEqual(app.unexpected_dialogs, [], 'The tested page opened an unexpected browser dialog.')

    def capture_artifacts(self, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        result = []
        for index, app in enumerate(self.apps):
            if app.page.is_closed():
                continue
            filename = f'{self._testMethodName[:8]}-failure-{index}.png'
            try:
                app.page.screenshot(path=str(output / filename), full_page=True)
            except Exception:
                continue  # The original failure must survive a disconnected browser.
            result.append(filename)
        self.artifacts.extend(name for name in result if name not in self.artifacts)
        return result

    def focus_artifact(self, name):
        filename = 'A10-focus-' + name + '.png'
        self.output.mkdir(parents=True, exist_ok=True)
        self.app.page.screenshot(path=str(self.output / filename))
        self.artifacts.append(filename)

    def baseline(self, app):
        app.save('已有地图', MAP_A)
        app.apply_map(MAP_B)
        self.assertTrue(any(value is not None for value in app.raw_storage().values()),
                        'Saving did not write any declared localStorage key.')
        return app.snapshot()

    def assert_preserved(self, app, before, message='Rejected operation changed the map or archives.'):
        self.assertEqual(app.snapshot(), before, message)

    def test_A01_save_refresh_load(self):
        app = self.app
        app.save('校园配送', MAP_A)
        saved = app.raw_storage()
        self.assertTrue(any(value is not None for value in saved.values()))
        app.apply_map(MAP_B)
        app.reload()
        app.load('校园配送', MAP_A)
        self.assertEqual(app.names(), ['校园配送'])

    def test_A02_name_validation_and_unicode(self):
        for index, name in enumerate((' \t\n ', '中' * 41, '🧭' * 41)):
            app = self.app if index == 0 else self.new_app()
            self.baseline(app)
            app.loc('name').fill(name)
            before = app.snapshot()
            app.loc('save').click()
            app.error()
            self.assert_preserved(app, before, f'Invalid name accepted or changed state: {name!r}')
            app.close()
        app = self.new_app()
        app.save('已有地图', MAP_A)
        name = '🧭' * 40
        app.save('  ' + name + '  ', MAP_B)
        self.assertCountEqual(app.names(), ['已有地图', name])
        app.reload()
        app.load(name, MAP_B)
        app.load('已有地图', MAP_A)

    def test_A03_duplicate_requires_choice(self):
        app = self.app
        app.save('同名地图', MAP_A)
        app.save('另一张地图', MAP_C)
        app.apply_map(MAP_B)
        app.loc('name').fill('同名地图')
        before = app.snapshot()
        if self.config['duplicate_policy'] == 'confirm':
            app.confirm_action(lambda: app.loc('save').click(), False,
                               before_choice=lambda: self.assert_preserved(app, before))
            self.assert_preserved(app, before)
            app.confirm_action(lambda: app.loc('save').click(), True)
            app.wait_storage_change(before['storage'])
            app.reload()
            app.load('同名地图', MAP_B)
            app.load('另一张地图', MAP_C)
        else:
            app.loc('save').click()
            app.error()
            self.assert_preserved(app, before)
            app.reload()
            app.load('同名地图', MAP_A)
            app.load('另一张地图', MAP_C)
        app.save('改名副本', MAP_B)
        self.assertEqual(set(app.names()), {'同名地图', '另一张地图', '改名副本'})
        app.close()
        # Import conflicts get a fresh context. A previous rejected save's error
        # must not accidentally satisfy the subsequent asynchronous import check.
        app = self.new_app()
        app.save('同名地图', MAP_B if self.config['duplicate_policy'] == 'confirm' else MAP_A)
        app.save('另一张地图', MAP_C)
        app.save('改名副本', MAP_B)
        before = app.snapshot()
        if self.config['duplicate_policy'] == 'confirm':
            app.confirm_action(lambda: app.upload(document('同名地图', MAP_C)), False,
                               before_choice=lambda: self.assert_preserved(app, before))
            self.assert_preserved(app, before)
            app.confirm_action(lambda: app.upload(document('同名地图', MAP_C)), True)
            app.wait_storage_change(before['storage'])
            app.wait_grid(MAP_C)
        else:
            app.upload(document('同名地图', MAP_C))
            app.error()
            self.assert_preserved(app, before)
        app.reload()
        app.load('同名地图', MAP_C if self.config['duplicate_policy'] == 'confirm' else MAP_A)
        app.load('另一张地图', MAP_C)
        app.load('改名副本', MAP_B)

    def test_A04_delete_cancel_and_confirm(self):
        app = self.app
        app.save('保留 A', MAP_A)
        app.save('保留 B', MAP_B)
        app.apply_map(MAP_C)
        app.select('保留 A')
        before = app.snapshot()
        app.confirm_action(lambda: app.loc('delete').click(), False,
                           before_choice=lambda: self.assert_preserved(app, before))
        self.assert_preserved(app, before)
        app.load('保留 A', MAP_A)
        app.apply_map(MAP_C)
        app.confirm_action(lambda: app.loc('delete').click(), True)
        app.wait_absent('保留 A')
        self.assertEqual(app.names(), ['保留 B'])
        app.wait_grid(MAP_C)
        app.reload()
        self.assertEqual(app.names(), ['保留 B'])
        app.load('保留 B', MAP_B)

    def test_A05_invalid_documents_preserve_state(self):
        invalid = {
            'invalid JSON': b'{not json',
            'unknown version': {**document(), 'version': 2},
            'boolean version': {**document(), 'version': True},
            'string version': {**document(), 'version': '1'},
            'fractional version': {**document(), 'version': 1.5},
            'array root': [], 'null root': None,
            'missing field': {'version': 1, 'name': '缺地图'},
            'extra field': {**document(), 'train': []},
            'wrong name type': {**document(), 'name': 12},
            'wrong grid type': {**document(), 'grid': 'S..\n.#.\n..G'},
        }
        for index, (label, payload) in enumerate(invalid.items()):
            app = self.app if index == 0 else self.new_app()
            before = self.baseline(app)
            app.upload(payload)
            app.error()
            self.assert_preserved(app, before, f'Invalid document changed state: {label}')
            app.close()

    def test_A06_grid_contract_and_boundaries(self):
        invalid = {
            'missing S': ['...', '.#.', '..G'], 'missing G': ['S..', '.#.', '...'],
            'two S': ['SS.', '.#.', '..G'], 'two G': ['S.G', '.#.', '..G'],
            'unequal rows': ['S..', '..', '..G'],
            '21 rows': ['S..'] + ['...'] * 19 + ['..G'],
            '21 columns': ['S' + '.' * 20, '.' * 21, '.' * 20 + 'G'],
            '2 rows': ['S..', '..G'], '2 columns': ['S.', '..', '.G'],
            'non-string row': ['S..', ['.', '.', '.'], '..G'],
            'zero': ['S0.', '...', '..G'], 'one': ['S1.', '...', '..G'],
            'non-ASCII digit': ['S２.', '...', '..G'],
        }
        for index, (label, rows) in enumerate(invalid.items()):
            app = self.app if index == 0 else self.new_app()
            before = self.baseline(app)
            app.upload(document(label, rows))
            app.error()
            self.assert_preserved(app, before, f'Invalid geometry changed state: {label}')
            app.close()
        app = self.new_app()
        largest = ['S' + '.' * 19] + ['.' * 20] * 18 + ['.' * 19 + 'G']
        for name, rows in [('最小合法地图', MAP_A), ('最大合法地图', largest), ('合法无解地图', MAP_C)]:
            app.upload(document(name, rows))
            app.wait_saved(name)
            app.wait_grid(rows)
            app.reload()
            app.load(name, rows)

    def test_A07_utf8_limit_precedes_parse(self):
        app = self.app
        exact = json_bytes(document('字节边界😀', MAP_A))
        exact += b' ' * (16384 - len(exact))
        self.assertEqual(len(exact), 16384)
        app.upload(exact)
        app.wait_saved('字节边界😀')
        app.wait_grid(MAP_A)
        before = app.snapshot()
        oversized = json_bytes(document(app.probe_marker + '😀', MAP_B))
        oversized += b' ' * (16385 - len(oversized))
        self.assertEqual(len(oversized), 16385)
        self.assertLess(len(oversized.decode('utf-8')), 16384)
        app.upload(oversized)
        app.error()
        self.assert_preserved(app, before)
        self.assertEqual(app.page.evaluate('window.__robotAcceptanceProbe.parseHits'), 0,
                         'The oversized document reached main-thread JSON.parse before rejection.')

    def test_A08_names_are_text(self):
        def name_markup(app):
            # Observe only markup matching the attack fixtures, rather than
            # rejecting existing presentation markup such as a bold dialog title.
            return app.page.evaluate('''() => ({
                bold: [...document.querySelectorAll('b')].filter(e => e.textContent === '地图').length,
                image: [...document.querySelectorAll('img')].filter(e =>
                    e.getAttribute('src') === 'x' && e.getAttribute('onerror') === 'alert(1)').length
            })''')

        for index, name in enumerate(('<b>地图</b>', '<img src=x onerror=alert(1)>')):
            app = self.app if index == 0 else self.new_app()
            original_markup = name_markup(app)
            app.save(name, MAP_A)
            app.load(name, MAP_A)
            self.assertIn(name, app.names())
            self.assertEqual(name_markup(app), original_markup, 'The map name created HTML elements.')
            if self.config['confirmation'] == 'dom':
                def inspect_confirmation():
                    self.assertEqual(name_markup(app), original_markup,
                                     'The confirmation created markup from a map name.')
                app.confirm_action(lambda: app.loc('delete').click(), False,
                                   before_choice=inspect_confirmation)
            else:
                app.confirm_action(lambda: app.loc('delete').click(), False)
            self.assertEqual(app.unexpected_dialogs, [])
            app.close()

    def test_A09_storage_failures_and_bad_history(self):
        operations = ['save', 'import', 'delete']
        if self.config['duplicate_policy'] == 'confirm':
            operations.append('overwrite')
        for index, operation in enumerate(operations):
            app = self.app if index == 0 else self.new_app()
            app.save('原有地图', MAP_A)
            app.save('旁边地图', MAP_C)
            app.apply_map(MAP_B)
            app.loc('name').fill('原有地图' if operation == 'overwrite' else '新的地图')
            if operation == 'delete':
                app.select('原有地图')
            before = app.snapshot()
            app.write_failure(True)
            if operation == 'save':
                app.loc('save').click()
            elif operation == 'import':
                app.upload(document('新的导入', MAP_B))
            elif operation == 'delete':
                app.confirm_action(lambda: app.loc('delete').click(), True)
            else:
                app.confirm_action(lambda: app.loc('save').click(), True)
            app.error()
            self.assertGreater(app.write_attempts(), 0,
                               f'{operation}: the declared localStorage write fault was not reached; '
                               'this run cannot establish storage-failure recovery.')
            self.assert_preserved(app, before, f'{operation} claimed success or changed state after a failed write.')
            app.write_failure(False)
            self.assertEqual(app.raw_storage(), before['storage'])
            app.reload()
            app.load('原有地图', MAP_A)
            app.load('旁边地图', MAP_C)
            self.assertEqual(set(app.names()), {'原有地图', '旁边地图'})
            app.close()
        baseline = self.new_app()
        baseline.save('完好记录', MAP_A)
        original = baseline.raw_storage()
        populated = [key for key, value in original.items() if value is not None]
        self.assertTrue(populated, 'There is no declared persisted key to corrupt.')
        baseline.close()
        for key in populated:
            corrupted = {**original, key: '{A09 malformed history'}
            app = self.new_app(initial_storage=corrupted)
            # CAPSTONE permits either a readable warning or ignoring the bad
            # record. Neither strategy may crash or overwrite the original bytes.
            self.assertEqual(app.raw_storage(), corrupted)
            app.grid()
            self.assertEqual(app.errors, [])
            app.close()

    def test_A10_keyboard_and_accessible_names(self):
        app = self.app
        for name in ('name', 'archives', 'save', 'load', 'delete', 'import_file', 'export_file'):
            app.accessible_name(name)
        app.tab_to('name')
        self.focus_artifact('name')
        app.page.keyboard.insert_text('键盘地图')
        app.tab_to('save')
        self.focus_artifact('save')
        app.page.keyboard.press('Enter')
        app.wait_saved('键盘地图')
        before_grid = app.grid()
        app.tab_to('presets', index=1)
        app.page.keyboard.press('Enter')
        app.tab_to('archives')
        self.focus_artifact('archives')
        app.page.keyboard.press('End')
        app.tab_to('load')
        self.focus_artifact('load')
        app.page.keyboard.press('Space')
        app.wait_grid(before_grid)
        app.expect(app.loc('name')).to_have_value('键盘地图')
        stored = app.raw_storage()

        def confirmation_evidence(name):
            app.tab_to(name)
            app.accessible_name(name)
            self.focus_artifact(name)

        if self.config['confirmation'] == 'native':
            self.manual_checks.append({
                'id': 'A10-native-confirm-keyboard', 'status': 'not_reviewed',
                'requirement': 'Native confirm was accepted/dismissed through Playwright Dialog API; '
                               'a person must verify actual keyboard cancellation and confirmation in the native window.',
            })
        app.tab_to('delete')
        app.confirm_action(lambda: app.page.keyboard.press('Enter'), False, keyboard=True,
                           before_choice=lambda: confirmation_evidence('confirm_no'))
        self.assertEqual(app.raw_storage(), stored)
        self.assertEqual(app.names(), ['键盘地图'])
        app.tab_to('delete')
        app.confirm_action(lambda: app.page.keyboard.press('Enter'), True, keyboard=True,
                           before_choice=lambda: confirmation_evidence('confirm_yes'))
        app.wait_absent('键盘地图')
        self.assertEqual(app.names(), [])

    def test_A11_original_application_regression(self):
        app = self.app
        app.wait_grid(PRESET_A)
        app.loc('bfs').click()
        app.expect(app.loc('comparisons')).to_contain_text('46')
        app.loc('dijkstra').click()
        app.expect(app.loc('comparisons')).to_contain_text('Dijkstra')
        rows = app.loc('comparisons').locator('tr').evaluate_all(
            'rows => rows.map(r => [...r.cells].map(c => c.textContent))')
        self.assertEqual(rows, [['BFS', '到达', '6', '46'], ['Dijkstra', '到达', '10', '10']])
        app.loc('frame').press('End')
        app.expect(app.loc('state')).to_have_text('已到达')
        app.expect(app.loc('energy')).to_have_text('10')
        app.loc('reset').click()
        app.loc('move_right').click()
        app.expect(app.loc('steps')).to_have_text('1')
        app.expect(app.loc('energy')).to_have_text('9')
        app.open_editor()
        app.loc('brush_wall').click()
        app.loc('grid_cells').nth(11).click()
        app.loc('student_strategy').click()
        app.expect(app.loc('comparisons')).to_contain_text('未到达')
        app.loc('presets').first.click()
        app.loc('brush_play').click()
        app.loc('demo_data').click()
        for index, value in enumerate(RIGHT_PIXELS):
            if value:
                app.loc('pad_cells').nth(index).press('Space')
        before_prediction = app.loc('steps').inner_text()
        app.loc('recognize').click()
        app.expect(app.loc('prediction')).to_contain_text('预测：右')
        app.expect(app.loc('execute')).to_be_enabled()
        app.expect(app.loc('steps')).to_have_text(before_prediction)
        app.loc('execute').click()
        app.expect(app.loc('steps')).to_have_text('1')
        app.expect(app.loc('execute')).to_be_disabled()
        app.loc('recognize').click()
        app.expect(app.loc('execute')).to_be_enabled()
        app.loc('pad_cells').nth(0).press('Space')
        app.expect(app.loc('execute')).to_be_disabled()
        app.loc('sample_label').select_option('right')
        app.loc('add_test').click()
        app.loc('evaluate').click()
        app.expect(app.loc('evaluation')).to_contain_text('当前留出集 1 条')
        app.loc('recognize').click()
        app.expect(app.loc('execute')).to_be_enabled()
        app.loc('k').select_option('3')
        app.expect(app.loc('execute')).to_be_disabled()
        samples = app.loc('sample_count').inner_text()
        app.save('只保存地图')
        app.loc('dijkstra').click()
        app.expect(app.loc('comparisons')).to_contain_text('Dijkstra')
        app.upload(document('切换地图', MAP_C))
        app.wait_saved('切换地图')
        app.wait_grid(MAP_C)
        self.assertEqual(app.loc('sample_count').inner_text(), samples)
        self.assertNotIn('Dijkstra', app.loc('comparisons').inner_text())
        app.expect(app.loc('frame')).to_be_disabled()
        app.expect(app.loc('execute')).to_be_disabled()
        app.reload()
        app.expect(app.loc('sample_count')).to_contain_text('训练 0')
        app.expect(app.loc('sample_count')).to_contain_text(re.compile(r'(留出测试|测试) 0'))
        app.load('只保存地图', PRESET_A)
        app.expect(app.loc('sample_count')).to_contain_text('训练 0')

    def test_A12_export_import_fresh_context(self):
        app = self.app
        app.save('交换地图', MAP_A)
        app.apply_map(MAP_B)
        app.loc('demo_data').click()
        self.output.mkdir(parents=True, exist_ok=True)
        destination = self.output / 'A12-export.json'
        exported = app.download(destination)
        self.artifacts.append(destination.name)
        self.assertEqual(exported, document('交换地图', MAP_B))
        self.assertEqual(set(exported), {'version', 'name', 'grid'})
        # Successful export/load may update harmless storage metadata. Observe
        # that the archived map itself was not replaced with the current map.
        app.reload()
        app.load('交换地图', MAP_A)
        receiver = self.new_app()
        self.assertTrue(all(value is None for value in receiver.raw_storage().values()))
        receiver.upload(destination.read_bytes())
        receiver.wait_saved('交换地图')
        receiver.wait_grid(MAP_B)
        receiver.reload()
        receiver.load('交换地图', MAP_B)
        receiver.close()
        for index, name in enumerate(('A\nB', 'A\rB', 'A\r\nB', 'A\r\nB\rC')):
            receiver = self.new_app()
            self.assertTrue(all(value is None for value in receiver.raw_storage().values()))
            expected = document(name, MAP_A)
            receiver.upload(expected)
            receiver.wait_saved(name)
            receiver.wait_grid(MAP_A)
            destination = self.output / f'A12-line-separator-{index}.json'
            self.assertEqual(receiver.download(destination), expected,
                             'An untouched imported legal name did not round-trip exactly.')
            self.artifacts.append(destination.name)
            receiver.apply_map(MAP_B)
            receiver.load(name, MAP_A, check_name=False)
            self.assertEqual(receiver.download(destination), expected)
            if self.config['duplicate_policy'] == 'confirm':
                receiver.confirm_action(lambda: receiver.loc('save').click(), True)
            else:
                before = receiver.snapshot()
                receiver.loc('save').click()
                receiver.error()
                self.assert_preserved(receiver, before)
            self.assertEqual(receiver.download(destination), expected)
            receiver.close()


def build_suite(browser, config, url, output, case_ids):
    """Build selected independent cases without starting or guessing a service."""
    if not case_ids or len(set(case_ids)) != len(case_ids) or any(item not in CASE_IDS for item in case_ids):
        raise ValueError('case_ids must be a nonempty list of unique A01–A12 identifiers.')
    suite = unittest.TestSuite()
    methods = unittest.defaultTestLoader.getTestCaseNames(PortfolioCases)
    for case_id in case_ids:
        method = next(name for name in methods if name.startswith('test_' + case_id + '_'))
        case = PortfolioCases(method)
        case.browser, case.config, case.url, case.output = browser, config, url, Path(output)
        suite.addTest(case)
    return suite
