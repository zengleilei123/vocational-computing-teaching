"""A01–A12, observed through a real browser and the public teacher page.

Run from the repository root::

    python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v
    python -m unittest teacher_reference.robot_map_portfolio.tests.test_acceptance -v -k A09

Requires Playwright and Chromium. Missing browser prerequisites fail explicitly;
there are no skipped acceptance cases or simulated localStorage origins. Set
PLAYWRIGHT_CHROMIUM_EXECUTABLE to use an already-installed Chromium executable.
No assertion calls the reference implementation's validator or storage helpers.
"""

import json
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit


STORAGE_KEY = 'robot-map-portfolio:v1'
MAP_A = ['S..', '.#.', '..G']
MAP_B = ['S2G', '...', '.#.']
MAP_C = ['S#G', '###', '...']  # Legal geometry; deliberately unreachable.
PRESET_A = ['#########', '#S99999G#', '#.#####.#', '#.......#', '#########']


def document(name='校园地图', rows=None):
    """A literal contract fixture, independent of the teacher implementation."""
    return {'version': 1, 'name': name, 'grid': list(MAP_A if rows is None else rows)}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


class PortfolioAcceptanceTests(unittest.TestCase):
    """Each A-ID receives a new browser context and its own archive state."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright, expect
        except ImportError as exc:
            raise RuntimeError(
                'A01–A12 require Playwright: install playwright, then run '
                'python -m playwright install chromium. Acceptance was NOT run.'
            ) from exc

        from teacher_reference.robot_map_portfolio.server import make_server

        cls.expect = staticmethod(expect)
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.addClassCleanup(cls._stop_server)
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        launch = {'headless': True, 'args': ['--no-sandbox']}
        if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
            launch['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
        try:
            cls.browser = cls.playwright.chromium.launch(**launch)
        except Exception as exc:
            raise RuntimeError(
                'A01–A12 could not start Chromium. Install it with '
                'python -m playwright install chromium, or set '
                'PLAYWRIGHT_CHROMIUM_EXECUTABLE. Acceptance was NOT run.'
            ) from exc
        cls.addClassCleanup(cls.browser.close)

    @classmethod
    def _stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.page_errors = []
        self.requests = []
        self.page = self._new_page()

    def tearDown(self):
        self.assertEqual(self.page_errors, [], 'The page raised an uncaught JavaScript error.')

    def _new_page(self, init_script=None):
        context = self.browser.new_context(
            accept_downloads=True, viewport={'width': 1440, 'height': 1100}
        )
        self.addCleanup(context.close)
        if init_script:
            context.add_init_script(init_script)
        page = context.new_page()
        page.set_default_timeout(5000)
        page.on('pageerror', lambda error: self.page_errors.append(str(error)))
        page.on('request', lambda request: self.requests.append(request.url))
        page.goto(self.base, wait_until='networkidle')
        self.expect(page.locator('#map-title')).to_have_text('近路不一定省电')
        self.expect(page.locator('#portfolio-name')).to_be_visible()
        self.expect(page.locator('#grid button')).to_have_count(45)
        return page

    def _reload(self):
        self.page.reload(wait_until='networkidle')
        self.expect(self.page.locator('#map-title')).to_have_text('近路不一定省电')
        self.expect(self.page.locator('#portfolio-name')).to_be_visible()

    def _raw_storage(self):
        return self.page.evaluate('(key) => localStorage.getItem(key)', STORAGE_KEY)

    def _records(self):
        raw = self._raw_storage()
        return [] if raw is None else json.loads(raw)

    def _snapshot(self):
        # Read the unchanged starter state and public DOM; do not call teacher code.
        return self.page.evaluate('''(key) => ({
            stored: localStorage.getItem(key),
            grid: grid.slice(), path: path.map(row => row.slice()),
            actions: actions.slice(), costs: costs.slice(),
            comparisons: JSON.parse(JSON.stringify(comparisons)),
            train: JSON.parse(JSON.stringify(train)), test: JSON.parse(JSON.stringify(test)),
            pixels: pixels.slice(), prediction,
            title: document.getElementById('map-title').textContent,
            mapText: document.getElementById('map-text').value,
            mode: document.getElementById('mode-label').textContent,
            frame: document.getElementById('frame').value,
            frameMax: document.getElementById('frame').max,
            name: document.getElementById('portfolio-name').value,
            selected: document.getElementById('portfolio-list').value,
            options: [...document.getElementById('portfolio-list').options]
                .map(option => ({value: option.value, text: option.textContent}))
        })''', STORAGE_KEY)

    def _wait_grid(self, rows):
        self.page.wait_for_function(
            '(rows) => JSON.stringify(grid) === JSON.stringify(rows)', arg=rows
        )
        self.assertEqual(self.page.locator('#map-text').input_value(), '\n'.join(rows))

    def _apply_map(self, rows):
        editor = self.page.locator('details.editor')
        if not editor.evaluate('(element) => element.open'):
            editor.locator('summary').click()
        self.page.locator('#map-text').fill('\n'.join(rows))
        self.page.locator('#apply-map').click()
        self._wait_grid(rows)

    def _wait_record(self, name):
        self.page.wait_for_function('''({key, name}) => {
            const raw = localStorage.getItem(key);
            return raw !== null && JSON.parse(raw).some(item => item.name === name);
        }''', arg={'key': STORAGE_KEY, 'name': name})
        self.page.wait_for_function('''(name) =>
            [...document.getElementById('portfolio-list').options]
                .some(option => option.value === name)
        ''', arg=name)

    def _save(self, name, rows=None):
        if rows is not None:
            self._apply_map(rows)
        self.page.locator('#portfolio-name').fill(name)
        self.page.locator('#portfolio-save').click()
        self._wait_record(name.strip())
        self.expect(self.page.locator('#portfolio-status')).not_to_have_class(re.compile(r'\berror\b'))

    def _load(self, name, rows):
        self.page.locator('#portfolio-list').select_option(name)
        self.page.locator('#portfolio-load').click()
        self._wait_grid(rows)
        self.expect(self.page.locator('#map-title')).to_have_text(name)
        self.expect(self.page.locator('#portfolio-name')).to_have_value(name)

    def _upload(self, payload, *, wait=True, filename='acceptance-map.json'):
        if not isinstance(payload, bytes):
            payload = json_bytes(payload)
        self.page.locator('#portfolio-import').set_input_files({
            'name': filename, 'mimeType': 'application/json', 'buffer': payload
        })
        if wait:
            self._wait_import_complete()

    def _wait_import_complete(self):
        # Resetting this input also makes retrying the same file possible.
        self.page.wait_for_function(
            "() => document.getElementById('portfolio-import').value === ''"
        )

    def _download_map(self, destination):
        with self.page.expect_download() as result:
            self.page.locator('#portfolio-export').click()
        result.value.save_as(destination)
        return json.loads(destination.read_text(encoding='utf-8'))

    def _expect_error(self):
        status = self.page.locator('#portfolio-status')
        self.expect(status).to_have_class(re.compile(r'\berror\b'))
        self.expect(status).not_to_have_text('')
        self.assertNotRegex(status.inner_text(), r'已保存|已删除|已导入|保存成功|导入成功|删除成功')

    def _confirm(self, accept):
        self.expect(self.page.locator('#portfolio-confirm')).to_be_visible()
        self.page.locator('#portfolio-confirm-yes' if accept else '#portfolio-confirm-no').click()
        self.expect(self.page.locator('#portfolio-confirm')).not_to_be_visible()
        # dialog.close() hides immediately; its close event resumes the operation
        # in a later task. Re-enabled controls establish that commit/rollback ended.
        self.expect(self.page.locator('#portfolio-save')).to_be_enabled()

    def _tab_to(self, selector, *, backwards=False):
        target = self.page.locator(selector)
        self.expect(target).to_be_visible()
        for _ in range(250):
            if target.evaluate('(element) => element === document.activeElement'):
                return
            self.page.keyboard.press('Shift+Tab' if backwards else 'Tab')
        self.fail(f'Keyboard focus could not reach {selector}.')

    def _assert_focus_visible(self, selector):
        state = self.page.locator(selector).evaluate('''(element) => {
            const style = getComputedStyle(element);
            return {focused: element === document.activeElement,
                keyboard: element.matches(':focus-visible'),
                ring: (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0)
                    || style.boxShadow !== 'none'};
        }''')
        self.assertTrue(state['focused'], selector)
        self.assertTrue(state['keyboard'], f'{selector} is missing keyboard focus state.')
        self.assertTrue(state['ring'], f'{selector} has no visible outline or focus shadow.')

    def test_A01_save_refresh_load(self):
        self._save('校园配送', MAP_A)
        self.assertEqual(self._records(), [document('校园配送', MAP_A)])
        self._reload()
        self._apply_map(MAP_B)
        self._load('校园配送', MAP_A)
        self.assertEqual(self._records(), [document('校园配送', MAP_A)])

    def test_A02_name_validation_and_code_points(self):
        self._save('已有记录', MAP_A)
        for name in (' \t\n ', '中' * 41, '😀' * 41):
            with self.subTest(name=repr(name)):
                self.page.locator('#portfolio-name').fill(name)
                before = self._snapshot()
                self.page.locator('#portfolio-save').click()
                self._expect_error()
                self.assertEqual(self._snapshot(), before)
        self._save('  ' + '😀' * 40 + '  ', MAP_B)
        self.assertEqual(self._records(), [document('已有记录', MAP_A), document('😀' * 40, MAP_B)])

    def test_A03_duplicate_requires_explicit_choice(self):
        self._save('同名地图', MAP_A)
        self._save('另一张地图', MAP_C)
        self._apply_map(MAP_B)
        self.page.locator('#portfolio-name').fill('同名地图')
        before = self._snapshot()
        self.page.locator('#portfolio-save').click()
        self.expect(self.page.locator('#portfolio-confirm')).to_be_visible()
        self.assertEqual(self._snapshot(), before, 'Opening confirmation must not write anything.')
        self._confirm(False)
        self.assertEqual(self._snapshot(), before)
        self.page.locator('#portfolio-save').click()
        self._confirm(True)
        self.assertEqual(self._records(), [document('同名地图', MAP_B), document('另一张地图', MAP_C)])

        self.page.locator('#portfolio-name').fill('改名副本')
        self.page.locator('#portfolio-save').click()
        self._wait_record('改名副本')
        self.assertEqual(len(self._records()), 3)
        before = self._snapshot()
        self._upload(document('同名地图', MAP_A), wait=False)
        self.expect(self.page.locator('#portfolio-confirm')).to_be_visible()
        self.assertEqual(self._snapshot(), before)
        self._confirm(False)
        self._wait_import_complete()
        self.assertEqual(self._snapshot(), before)
        self._upload(document('同名地图', MAP_A), wait=False)
        self._confirm(True)
        self._wait_import_complete()
        self._wait_grid(MAP_A)
        self.assertEqual(self._records(), [
            document('同名地图', MAP_A), document('另一张地图', MAP_C), document('改名副本', MAP_B)
        ])

    def test_A04_delete_cancel_and_confirm(self):
        self._save('保留 A', MAP_A)
        self._save('保留 B', MAP_B)
        self._apply_map(MAP_C)
        self.page.locator('#portfolio-list').select_option('保留 A')
        before = self._snapshot()
        self.page.locator('#portfolio-delete').click()
        self._confirm(False)
        self.assertEqual(self._snapshot(), before)
        self.page.locator('#portfolio-delete').click()
        self._confirm(True)
        self.assertEqual(self._records(), [document('保留 B', MAP_B)])
        self._wait_grid(MAP_C)
        self._load('保留 B', MAP_B)

    def test_A05_invalid_documents_preserve_state(self):
        self._save('原有地图', MAP_A)
        self.page.locator('#bfs').click()
        self.expect(self.page.locator('#comparisons')).to_contain_text('BFS')
        self.page.locator('#demo-data').click()
        before = self._snapshot()
        cases = {
            'invalid JSON': b'{not json',
            'unknown version': {**document(), 'version': 2},
            'boolean version': {**document(), 'version': True},
            'string version': {**document(), 'version': '1'},
            'fractional version': {**document(), 'version': 1.5},
            'array root': [],
            'null root': None,
            'missing field': {'version': 1, 'name': '缺少地图'},
            'extra field': {**document(), 'train': []},
            'wrong name type': {**document(), 'name': 123},
            'wrong grid type': {**document(), 'grid': 'S..\n.#.\n..G'},
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                self._upload(payload)
                self._expect_error()
                self.assertEqual(self._snapshot(), before)

    def test_A06_grid_contract_and_boundaries(self):
        self._save('原有地图', MAP_A)
        before = self._snapshot()
        invalid = {
            'missing S': ['...', '.#.', '..G'],
            'missing G': ['S..', '.#.', '...'],
            'two S': ['SS.', '.#.', '..G'],
            'two G': ['S.G', '.#.', '..G'],
            'ragged rows': ['S..', '..', '..G'],
            '21 rows': ['S..'] + ['...'] * 19 + ['..G'],
            '21 columns': ['S' + '.' * 20, '.' * 21, '.' * 20 + 'G'],
            'two rows': ['S..', '..G'],
            'two columns': ['S.', '..', '.G'],
            'non-string row': ['S..', ['.', '.', '.'], '..G'],
            'forbidden zero': ['S0.', '...', '..G'],
            'forbidden one': ['S1.', '...', '..G'],
            'non-ASCII digit': ['S２.', '...', '..G'],
        }
        for label, rows in invalid.items():
            with self.subTest(case=label):
                self._upload(document(label, rows))
                self._expect_error()
                self.assertEqual(self._snapshot(), before)
        largest = ['S' + '.' * 19] + ['.' * 20] * 18 + ['.' * 19 + 'G']
        self._upload(document('最大合法地图', largest))
        self._wait_grid(largest)
        self._upload(document('合法无解地图', MAP_C))
        self._wait_grid(MAP_C)
        self.assertEqual(self._records(), [
            document('原有地图', MAP_A), document('最大合法地图', largest), document('合法无解地图', MAP_C)
        ])

    def test_A07_byte_limit_precedes_read_and_parse(self):
        exact = json_bytes(document('字节边界😀', MAP_A))
        exact += b' ' * (16 * 1024 - len(exact))
        self.assertEqual(len(exact), 16384)
        self._upload(exact)
        self._wait_record('字节边界😀')
        before = self._snapshot()
        self.page.evaluate('''() => {
            window.__a07Reads = 0;
            window.__a07Parses = 0;
            const originalParse = JSON.parse;
            JSON.parse = function(value, ...args) {
                if (typeof value === 'string' && value.includes('A07-oversize'))
                    window.__a07Parses++;
                return originalParse.call(this, value, ...args);
            };
            for (const method of ['text', 'arrayBuffer']) {
                const original = Blob.prototype[method];
                Blob.prototype[method] = function(...args) {
                    if (this.size > 16384) window.__a07Reads++;
                    return original.apply(this, args);
                };
            }
            for (const method of ['readAsText', 'readAsArrayBuffer']) {
                const original = FileReader.prototype[method];
                FileReader.prototype[method] = function(blob, ...args) {
                    if (blob.size > 16384) window.__a07Reads++;
                    return original.call(this, blob, ...args);
                };
            }
        }''')
        oversized = json_bytes(document('A07-oversize-😀', MAP_B))
        oversized += b' ' * (16 * 1024 + 1 - len(oversized))
        self.assertEqual(len(oversized), 16385)
        self.assertLess(len(oversized.decode('utf-8')), 16384, 'Fixture must distinguish bytes from characters.')
        self._upload(oversized)
        self._expect_error()
        self.assertRegex(self.page.locator('#portfolio-status').inner_text(), r'16|16384|大小|过大')
        self.assertEqual(self.page.evaluate('window.__a07Reads'), 0, 'Oversized file was read.')
        self.assertEqual(self.page.evaluate('window.__a07Parses'), 0, 'Oversized JSON reached the parser.')
        self.assertEqual(self._snapshot(), before)

    def test_A08_names_render_as_text(self):
        dialogs = []

        def dismiss_unexpected(dialog):
            dialogs.append(dialog.message)
            dialog.dismiss()

        self.page.on('dialog', dismiss_unexpected)
        for name in ('<b>地图</b>', '<img src=x onerror=alert(1)>'):
            with self.subTest(name=name):
                self._save(name, MAP_A)
                self._load(name, MAP_A)
                self.expect(self.page.locator('#map-title')).to_have_text(name)
                self.assertIn(name, self.page.locator('#portfolio-list option').all_text_contents())
                for container in ('#portfolio-list', '#map-title'):
                    self.assertEqual(self.page.locator(container + ' b, ' + container + ' img').count(), 0)
                self.page.locator('#portfolio-save').click()
                self.expect(self.page.locator('#portfolio-confirm-text')).to_contain_text(name)
                self.assertEqual(self.page.locator('#portfolio-confirm b, #portfolio-confirm img').count(), 0)
                self._confirm(False)
                self.page.locator('#portfolio-delete').click()
                self.expect(self.page.locator('#portfolio-confirm-text')).to_contain_text(name)
                self.assertEqual(self.page.locator('#portfolio-confirm b, #portfolio-confirm img').count(), 0)
                self._confirm(False)
        self.assertEqual(dialogs, [], 'A map name caused script execution or a native browser dialog.')

    def test_A09_storage_failure_and_corruption(self):
        damaged = '{broken history'
        self.page.evaluate('([key, value]) => localStorage.setItem(key, value)', [STORAGE_KEY, damaged])
        self._reload()
        self._expect_error()
        self.expect(self.page.locator('#portfolio-list option')).to_have_count(1)
        self.assertEqual(self._raw_storage(), damaged, 'Startup must not silently erase corrupt history.')

        mixed = json.dumps([document('可恢复记录', MAP_A), {'version': 1, 'name': '坏记录', 'grid': ['bad']}], ensure_ascii=False)
        self.page.evaluate('([key, value]) => localStorage.setItem(key, value)', [STORAGE_KEY, mixed])
        self._reload()
        self.expect(self.page.locator('#portfolio-list option')).to_have_count(2)
        self._load('可恢复记录', MAP_A)
        self.assertEqual(self._raw_storage(), mixed)

        self.page.evaluate('(key) => localStorage.removeItem(key)', STORAGE_KEY)
        self._reload()
        self._save('A', MAP_A)
        self._save('B', MAP_B)
        self._apply_map(MAP_C)
        self.page.evaluate('''(key) => {
            window.__a09Writes = 0;
            const original = Storage.prototype.setItem;
            Storage.prototype.setItem = function(name, value) {
                if (name === key) {
                    window.__a09Writes++;
                    throw new DOMException('A09 injected quota failure', 'QuotaExceededError');
                }
                return original.call(this, name, value);
            };
        }''', STORAGE_KEY)

        for action in ('save', 'overwrite', 'delete', 'import'):
            with self.subTest(action=action):
                self.page.locator('#portfolio-name').fill('A' if action == 'overwrite' else '新记录')
                self.page.locator('#portfolio-list').select_option('A')
                before = self._snapshot()
                writes = self.page.evaluate('window.__a09Writes')
                if action in ('save', 'overwrite'):
                    self.page.locator('#portfolio-save').click()
                    if action == 'overwrite':
                        self._confirm(True)
                elif action == 'delete':
                    self.page.locator('#portfolio-delete').click()
                    self._confirm(True)
                else:
                    self._upload(document('导入失败', MAP_B))
                self._expect_error()
                self.assertEqual(self.page.evaluate('window.__a09Writes'), writes + 1)
                self.assertEqual(self._snapshot(), before, f'{action} changed state despite a failed write.')

        self.page = self._new_page('''(() => {
            const original = Storage.prototype.getItem;
            Storage.prototype.getItem = function(key) {
                if (key === 'robot-map-portfolio:v1')
                    throw new DOMException('A09 injected read failure', 'SecurityError');
                return original.call(this, key);
            };
        })();''')
        self._expect_error()
        self.expect(self.page.locator('#grid button')).to_have_count(45)

    def test_A10_keyboard_operation_and_visible_focus(self):
        self.expect(self.page.get_by_role('textbox', name='地图名称', exact=True)).to_have_count(1)
        self.expect(self.page.get_by_role('combobox', name='已保存的地图', exact=True)).to_have_count(1)
        self.expect(self.page.get_by_label('导入地图 JSON', exact=True)).to_have_count(1)
        self._tab_to('#portfolio-name')
        self._assert_focus_visible('#portfolio-name')
        self.page.keyboard.insert_text('键盘地图')
        self._tab_to('#portfolio-save')
        self._assert_focus_visible('#portfolio-save')
        self.page.keyboard.press('Enter')
        self._wait_record('键盘地图')

        self._tab_to('#presets button:nth-child(2)')
        self.page.keyboard.press('Enter')
        self.expect(self.page.locator('#map-title')).to_have_text('绕路才到得了')
        self._tab_to('#portfolio-list')
        self._assert_focus_visible('#portfolio-list')
        self.page.keyboard.press('End')
        self._tab_to('#portfolio-load')
        self._assert_focus_visible('#portfolio-load')
        self.page.keyboard.press('Space')
        self._wait_grid(PRESET_A)
        self.expect(self.page.locator('#map-title')).to_have_text('键盘地图')

        self._tab_to('#portfolio-save')
        self.page.keyboard.press('Enter')
        self.expect(self.page.locator('#portfolio-confirm')).to_be_visible()
        self.expect(self.page.locator('#portfolio-confirm-no')).to_be_focused()
        self._assert_focus_visible('#portfolio-confirm-no')
        before = self._raw_storage()
        self._tab_to('#portfolio-confirm-yes')
        self._assert_focus_visible('#portfolio-confirm-yes')
        self.page.keyboard.press('Shift+Tab')
        self.expect(self.page.locator('#portfolio-confirm-no')).to_be_focused()
        self.page.keyboard.press('Escape')
        self.expect(self.page.locator('#portfolio-confirm')).not_to_be_visible()
        self.expect(self.page.locator('#portfolio-save')).to_be_focused()
        self.assertEqual(self._raw_storage(), before)

        self._tab_to('#portfolio-delete')
        self.page.keyboard.press('Enter')
        self.expect(self.page.locator('#portfolio-confirm-no')).to_be_focused()
        self.page.keyboard.press('Space')
        self.expect(self.page.locator('#portfolio-confirm')).not_to_be_visible()
        self.expect(self.page.locator('#portfolio-delete')).to_be_focused()
        self.assertEqual(self._raw_storage(), before)
        self.page.keyboard.press('Enter')
        self._tab_to('#portfolio-confirm-yes')
        self._assert_focus_visible('#portfolio-confirm-yes')
        self.page.keyboard.press('Space')
        self.expect(self.page.locator('#portfolio-confirm')).not_to_be_visible()
        self.expect(self.page.locator('#portfolio-save')).to_be_enabled()
        self.assertEqual(self._records(), [])

    def test_A11_existing_playground_behaviors(self):
        # Existing domain and HTTP tests remain executable as part of this gate.
        old_suite = unittest.defaultTestLoader.loadTestsFromName('projects.robot_playground.test_playground')
        old_result = unittest.TestResult()
        old_suite.run(old_result)
        self.assertGreater(old_result.testsRun, 30)
        self.assertEqual(old_result.errors + old_result.failures, [])

        self.page.locator('#bfs').click()
        self.expect(self.page.locator('#comparisons')).to_contain_text('46')
        self.page.locator('#dijkstra').click()
        self.expect(self.page.locator('#comparisons')).to_contain_text('Dijkstra')
        rows = self.page.locator('#comparisons tr').evaluate_all(
            '(rows) => rows.map(row => [...row.cells].map(cell => cell.textContent))'
        )
        self.assertEqual(rows, [['BFS', '到达', '6', '46'], ['Dijkstra', '到达', '10', '10']])
        self.page.locator('#frame').focus()
        self.page.locator('#frame').press('End')
        self.expect(self.page.locator('#state')).to_have_text('已到达')
        self.expect(self.page.locator('#energy')).to_have_text('10')
        self.page.locator('#reset').click()
        self.page.locator('[data-move="right"]').click()
        self.expect(self.page.locator('#steps')).to_have_text('1')
        self.expect(self.page.locator('#energy')).to_have_text('9')

        self.page.locator('.editor summary').click()
        self.page.locator('[data-brush="#"]').click()
        self.page.locator('#grid button').nth(11).click()
        self.page.locator('#student').click()
        self.expect(self.page.locator('#comparisons')).to_contain_text('未到达')
        self.page.locator('#presets button').first.click()
        self.page.locator('[data-brush="play"]').click()
        self.page.locator('#demo-data').click()
        from projects.robot_playground.glyphs import DEMO_TRAIN
        right = next(sample['pixels'] for sample in DEMO_TRAIN if sample['label'] == 'right')
        for index, value in enumerate(right):
            if value:
                self.page.locator('#pad button').nth(index).press('Space')
        steps_before_prediction = self.page.locator('#steps').inner_text()
        self.page.locator('#recognize').click()
        self.expect(self.page.locator('#prediction')).to_contain_text('预测：右')
        self.expect(self.page.locator('#execute')).to_be_enabled()
        self.expect(self.page.locator('#steps')).to_have_text(steps_before_prediction)
        self.page.locator('#execute').click()
        self.expect(self.page.locator('#steps')).to_have_text('1')
        self.expect(self.page.locator('#execute')).to_be_disabled()
        self.page.locator('#recognize').click()
        self.expect(self.page.locator('#execute')).to_be_enabled()
        self.page.locator('#pad button').nth(0).press('Space')
        self.expect(self.page.locator('#execute')).to_be_disabled()
        self.page.locator('#label').select_option('right')
        self.page.locator('#add-test').click()
        self.page.locator('#evaluate').click()
        self.expect(self.page.locator('#evaluation')).to_contain_text('当前留出集 1 条')
        self.page.locator('#recognize').click()
        self.expect(self.page.locator('#execute')).to_be_enabled()
        self.page.locator('#k').select_option('3')
        self.expect(self.page.locator('#execute')).to_be_disabled()

        self._save('只保存地图')
        self.assertEqual(self._records(), [document('只保存地图', PRESET_A)])
        self._upload(document('切换地图', MAP_C))
        self._wait_grid(MAP_C)
        self.assertEqual(self.page.evaluate('[train.length, test.length]'), [4, 1])
        self.expect(self.page.locator('#comparisons')).to_contain_text('运行算法后显示')
        self.expect(self.page.locator('#play')).to_be_disabled()
        self.page.locator('#bfs').click()
        self.expect(self.page.locator('#notice')).to_contain_text('unreachable')

    def test_A12_export_import_empty_browser(self):
        self._save('交换地图', MAP_A)
        self._apply_map(MAP_B)  # Export must use the current map, not stale archive data.
        self.page.locator('#demo-data').click()
        with tempfile.TemporaryDirectory(prefix='portfolio-a12-') as directory:
            downloaded = Path(directory) / 'map.json'
            exported = self._download_map(downloaded)
            self.assertEqual(exported, document('交换地图', MAP_B))
            self.assertEqual(set(exported), {'version', 'name', 'grid'})
            self.assertEqual(self._records(), [document('交换地图', MAP_A)])

            self.page = self._new_page()
            self.assertIsNone(self._raw_storage())
            self.page.locator('#portfolio-import').set_input_files(downloaded)
            self._wait_import_complete()
            self._wait_grid(MAP_B)
            self.expect(self.page.locator('#portfolio-name')).to_have_value('交换地图')
            self.assertEqual(self._records(), [document('交换地图', MAP_B)])
            self.assertEqual(self.page.evaluate('[train.length, test.length]'), [0, 0])
            self._reload()
            self._load('交换地图', MAP_B)

            # Internal line separators are legal name code points. Native form
            # controls may normalize their displayed value, but an untouched
            # imported document must retain its exact canonical name on export.
            for index, name in enumerate(('A\nB', 'A\rB', 'A\r\nB', 'A\r\nB\rC')):
                with self.subTest(imported_name=repr(name)):
                    self.page = self._new_page()
                    self.assertIsNone(self._raw_storage())
                    expected = document(name, MAP_A)
                    self._upload(expected)
                    self._wait_grid(MAP_A)
                    self.assertEqual(self._records(), [expected])
                    self.assertEqual(self.page.locator('#portfolio-list').input_value(), name)
                    destination = Path(directory) / f'line-separator-{index}.json'
                    self.assertEqual(self._download_map(destination), expected,
                                     'Export changed an untouched legal imported name.')

                    self._apply_map(MAP_B)
                    self.page.locator('#portfolio-list').select_option(name)
                    self.page.locator('#portfolio-load').click()
                    self._wait_grid(MAP_A)
                    # Deliberately do not compare textarea.value to a raw CR:
                    # browsers normalize that property even for textarea.
                    self.assertEqual(self.page.locator('#portfolio-list').input_value(), name)
                    self.page.locator('#portfolio-save').click()
                    self.expect(self.page.locator('#portfolio-confirm')).to_be_visible()
                    self.assertEqual(self._records(), [expected],
                                     'Re-saving a loaded name must request overwrite first.')
                    self._confirm(True)
                    self.assertEqual(self._records(), [expected])
                    self.assertEqual(self._download_map(destination), expected)

                    typed_name = f'编辑后的\n地图 {index}'
                    self._save(typed_name)
                    edited = document(typed_name, MAP_A)
                    self.assertEqual(self._records(), [expected, edited])
                    self.assertEqual(self.page.locator('#portfolio-list').input_value(), typed_name)
                    self.assertEqual(self._download_map(destination), edited,
                                     'A real name edit must replace the imported canonical name.')

        expected_origin = urlsplit(self.base).netloc
        self.assertTrue(self.requests)
        self.assertTrue(all(urlsplit(url).netloc == expected_origin for url in self.requests),
                        f'Unexpected remote request during local-only exchange: {self.requests!r}')


if __name__ == '__main__':
    unittest.main()
