"""Declarative UI adapter for the original robot map UI and native form controls.

Only DOM observations, user actions and test-side fault/probe instrumentation are
used. The adapter never imports the reference app or reads its JavaScript state.
"""

import json
import re
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


CASE_IDS = tuple(f'A{number:02d}' for number in range(1, 13))
CORE_SELECTORS = {
    'map_editor', 'map_input', 'map_apply', 'map_title', 'name', 'archives',
    'save', 'load', 'delete', 'import_file', 'export_file', 'feedback', 'error',
}
REGRESSION_SELECTORS = {
    'presets', 'bfs', 'dijkstra', 'comparisons', 'frame', 'state', 'energy',
    'steps', 'reset', 'move_right', 'brush_wall', 'brush_play', 'grid_cells',
    'student_strategy', 'demo_data', 'pad_cells', 'recognize', 'prediction',
    'execute', 'sample_count', 'sample_label', 'add_test', 'evaluate',
    'evaluation', 'k',
}
CONFIRM_SELECTORS = {'confirm_dialog', 'confirm_yes', 'confirm_no'}


class ConfigError(ValueError):
    """The UI adapter is incomplete, ambiguous or outside the supported shape."""


def _text(value, location):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ConfigError(f'{location} must be a nonempty string.')
    if len(value) > 2048:
        raise ConfigError(f'{location} is too long.')
    if value.strip().upper().startswith(('TODO', 'REPLACE_', 'CHANGE_ME')) or '待填写' in value:
        raise ConfigError(f'{location} is still an unfilled template placeholder.')
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def load_config(path):
    """Load a strict JSON-only configuration; no app code is executed."""
    try:
        raw = Path(path).read_text(encoding='utf-8')
        config = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f'Cannot read adapter JSON: {exc}') from exc
    if not isinstance(config, dict):
        raise ConfigError('The adapter must be one JSON object.')
    required = {
        'schema_version', 'target_kind', 'label', 'source_files', 'storage_keys',
        'duplicate_policy', 'confirmation', 'selectors',
    }
    allowed = required | {'archive_placeholder_values', 'timeout_ms'}
    if set(config) - allowed or required - set(config):
        raise ConfigError(f'Adapter fields mismatch; missing={sorted(required - set(config))}, '
                          f'unknown={sorted(set(config) - allowed)}.')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ConfigError('schema_version must be the integer 1.')
    if config['target_kind'] not in ('student', 'reference'):
        raise ConfigError('target_kind must be student or reference.')
    _text(config['label'], 'label')
    if config['duplicate_policy'] not in ('confirm', 'reject'):
        raise ConfigError('duplicate_policy must be confirm or reject.')
    if config['confirmation'] not in ('dom', 'native'):
        raise ConfigError('confirmation must be dom or native.')
    keys = config['storage_keys']
    if not isinstance(keys, list) or not keys:
        raise ConfigError('storage_keys must list the actual localStorage keys.')
    for index, key in enumerate(keys):
        _text(key, f'storage_keys[{index}]')
    if len(set(keys)) != len(keys):
        raise ConfigError('storage_keys must be unique.')
    files = config['source_files']
    if not isinstance(files, list) or not files:
        raise ConfigError('source_files must identify at least one served source file.')
    seen_urls, seen_paths = set(), set()
    for index, item in enumerate(files):
        where = f'source_files[{index}]'
        if not isinstance(item, dict) or set(item) != {'url', 'path'}:
            raise ConfigError(f'{where} must contain exactly url and path.')
        url = _text(item['url'], f'{where}.url')
        parts = urlsplit(url)
        if (not url.startswith('/') or url.startswith('//') or parts.scheme or parts.netloc
                or parts.query or parts.fragment or '\\' in url or '%' in url
                or any(part in ('.', '..') for part in url.split('/'))):
            raise ConfigError(f'{where}.url must be a same-origin absolute URL path.')
        local = _text(item['path'], f'{where}.path')
        if (PurePosixPath(local).is_absolute() or '\\' in local or ':' in local
                or any(part in ('', '.', '..') for part in local.split('/'))):
            raise ConfigError(f'{where}.path must be a normalized source-root-relative path.')
        if url in seen_urls or local in seen_paths:
            raise ConfigError('source_files URLs and local paths must each be unique.')
        seen_urls.add(url)
        seen_paths.add(local)
    selectors = config['selectors']
    expected = CORE_SELECTORS | REGRESSION_SELECTORS
    if config['confirmation'] == 'dom':
        expected |= CONFIRM_SELECTORS
    if not isinstance(selectors, dict) or set(selectors) != expected:
        actual = set(selectors) if isinstance(selectors, dict) else set()
        raise ConfigError(f'selectors mismatch; missing={sorted(expected - actual)}, '
                          f'unknown={sorted(actual - expected)}.')
    for key, value in selectors.items():
        if not isinstance(value, dict) or set(value) not in (
            {'role', 'name'}, {'label'}, {'test_id'}, {'css'},
        ):
            raise ConfigError(f'selectors.{key} must be role/name, label, test_id, or css.')
        for field, text in value.items():
            _text(text, f'selectors.{key}.{field}')
    placeholders = config.get('archive_placeholder_values', [''])
    if (not isinstance(placeholders, list) or any(not isinstance(value, str) for value in placeholders)
            or len(set(placeholders)) != len(placeholders)):
        raise ConfigError('archive_placeholder_values must be a list of unique strings.')
    timeout = config.get('timeout_ms', 5000)
    if type(timeout) is not int or not 1000 <= timeout <= 30000:
        raise ConfigError('timeout_ms must be an integer from 1000 to 30000.')
    config['archive_placeholder_values'] = placeholders
    config['timeout_ms'] = timeout
    return config


def locator(page, definition):
    """Construct a locator without executable adapter expressions."""
    if 'role' in definition:
        return page.get_by_role(definition['role'], name=definition['name'], exact=True)
    if 'label' in definition:
        return page.get_by_label(definition['label'], exact=True)
    if 'test_id' in definition:
        return page.get_by_test_id(definition['test_id'])
    return page.locator('css=' + definition['css'])


class App:
    """One isolated browser context, explicit endpoint and observed DOM state."""

    def __init__(self, browser, config, url, *, initial_storage=None):
        from playwright.sync_api import expect

        self.expect = expect
        self.config, self.url = config, url
        self.errors, self.blocked_requests, self.unexpected_dialogs = [], [], []
        self.native_decisions = []
        self._next_dialog_decision = None
        self.probe_marker = 'A07-probe-' + uuid.uuid4().hex[:16]
        parts = urlsplit(url)
        self.origin = (parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
        self.context = browser.new_context(accept_downloads=True, viewport={'width': 1440, 'height': 1100})
        self.context.set_default_timeout(config['timeout_ms'])

        def route_local(route):
            request_url = urlsplit(route.request.url)
            origin = (request_url.scheme, request_url.hostname,
                      request_url.port or (443 if request_url.scheme == 'https' else 80))
            if request_url.scheme in ('http', 'https') and origin != self.origin:
                self.blocked_requests.append(route.request.url)
                route.abort('blockedbyclient')
            else:
                route.continue_()

        self.context.route('**/*', route_local)
        instrumentation = '''({marker, initial, keys}) => {
            const nativeParse = JSON.parse;
            const probe = window.__robotAcceptanceProbe = {
                parseHits: 0, failWrites: false, writeAttempts: 0,
            };
            JSON.parse = function(text, ...args) {
                if (typeof text === 'string' && text.includes(marker))
                    probe.parseHits++;
                return nativeParse.call(this, text, ...args);
            };
            if (initial !== null) for (const [key, value] of Object.entries(initial)) {
                if (value === null) localStorage.removeItem(key);
                else localStorage.setItem(key, value);
            }
            const original = {setItem: Storage.prototype.setItem,
                removeItem: Storage.prototype.removeItem, clear: Storage.prototype.clear};
            const wrappers = {};
            const fail = () => {
                probe.writeAttempts++;
                throw new DOMException('A09 injected storage write failure', 'QuotaExceededError');
            };
            for (const method of ['setItem', 'removeItem']) {
                wrappers[method] = function(key, ...args) {
                    if (probe.failWrites && this === localStorage && keys.includes(String(key))) fail();
                    return original[method].call(this, key, ...args);
                };
            }
            wrappers.clear = function(...args) {
                if (probe.failWrites && this === localStorage &&
                    keys.some(key => localStorage.getItem(key) !== null)) fail();
                return original.clear.apply(this, args);
            };
            // Install before application scripts, including apps which cache a
            // bound Storage method at startup. Cached wrappers consult the flag.
            for (const method of Object.keys(original)) Storage.prototype[method] = wrappers[method];
            probe.configureWrites = enabled => {
                probe.failWrites = enabled;
                if (enabled) probe.writeAttempts = 0;
                for (const method of Object.keys(original))
                    Storage.prototype[method] = enabled ? wrappers[method] : original[method];
            };
        }'''
        self.context.add_init_script('(' + instrumentation + ')(' + json.dumps(
            {'marker': self.probe_marker, 'initial': initial_storage, 'keys': config['storage_keys']},
            ensure_ascii=True) + ');')
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('dialog', self._native_dialog)

    def _native_dialog(self, dialog):
        choice = self._next_dialog_decision
        self._next_dialog_decision = None
        if choice is None or dialog.type != 'confirm':
            self.unexpected_dialogs.append({'type': dialog.type, 'message': dialog.message})
            dialog.dismiss()
            return
        self.native_decisions.append({'accepted': choice, 'message': dialog.message})
        if choice:
            dialog.accept()
        else:
            dialog.dismiss()

    def loc(self, name):
        return locator(self.page, self.config['selectors'][name])

    def open(self):
        response = self.page.goto(self.url, wait_until='load')
        assert response is not None and response.ok, 'The explicit target did not return an OK document.'
        self.ready()

    def ready(self):
        actual, expected = urlsplit(self.page.url), urlsplit(self.url)
        assert (actual.scheme, actual.netloc, actual.path.rstrip('/') or '/', actual.query) == (
            expected.scheme, expected.netloc, expected.path.rstrip('/') or '/', expected.query
        ), f'The page navigated away from the explicit target: {self.page.url}'
        self.expect(self.loc('name')).to_be_visible()
        self.expect(self.loc('save')).to_be_visible()
        self.expect(self.loc('archives')).to_have_count(1)
        assert self.loc('archives').evaluate('(e) => e.tagName') == 'SELECT', (
            'This adapter supports a native select archive list; other UI shapes need an adapter extension.'
        )
        self.expect(self.loc('grid_cells').first).to_be_visible()

    def close(self):
        self.context.close()

    def reload(self):
        self.page.reload(wait_until='load')
        self.ready()

    def raw_storage(self):
        return self.page.evaluate('(keys) => Object.fromEntries(keys.map(k => [k, localStorage.getItem(k)]))',
                                  self.config['storage_keys'])

    def names(self):
        return self.loc('archives').evaluate('''(e, placeholders) => [...e.options]
            .filter(o => !placeholders.includes(o.value)).map(o => o.textContent)''',
            self.config['archive_placeholder_values'])

    def grid(self):
        labels = self.loc('grid_cells').evaluate_all('(cells) => cells.map(e => e.getAttribute("aria-label"))')
        cells = {}
        for label in labels:
            match = re.fullmatch(r'第(\d+)行第(\d+)列，(?:机器人，)?(墙|普通地面|[SG2-9])', label or '')
            assert match is not None, f'The original grid accessibility labels are required: {label!r}'
            row, column, value = match.groups()
            position = (int(row), int(column))
            assert position not in cells, f'Duplicate visible grid cell: {position}'
            cells[position] = {'墙': '#', '普通地面': '.'}.get(value, value)
        assert cells, 'The visible grid is empty.'
        height, width = max(row for row, _ in cells), max(column for _, column in cells)
        assert len(cells) == height * width, 'The visible map has missing cells.'
        return [''.join(cells[row, column] for column in range(1, width + 1))
                for row in range(1, height + 1)]

    def wait_grid(self, rows):
        self.expect(self.loc('grid_cells')).to_have_count(sum(len(row) for row in rows))
        expected = []
        for row, line in enumerate(rows, 1):
            for column, symbol in enumerate(line, 1):
                terrain = {'#': '墙', '.': '普通地面'}.get(symbol, symbol)
                expected.append(re.compile(f'^第{row}行第{column}列，(?:机器人，)?{re.escape(terrain)}$'))
        for index, label in enumerate(expected):
            self.expect(self.loc('grid_cells').nth(index)).to_have_attribute('aria-label', label)
        self.expect(self.loc('map_input')).to_have_value('\n'.join(rows))
        assert self.grid() == list(rows)

    def open_editor(self):
        editor = self.loc('map_editor')
        assert editor.evaluate('(e) => e.tagName') == 'DETAILS', 'map_editor must locate the original details element.'
        if not editor.evaluate('(e) => e.open'):
            editor.locator('summary').click()

    def apply_map(self, rows):
        self.open_editor()
        self.loc('map_input').fill('\n'.join(rows))
        self.loc('map_apply').click()
        self.wait_grid(rows)

    def wait_saved(self, name):
        self.page.wait_for_function('''([select, name]) =>
            [...select.options].filter(o => o.textContent === name).length === 1''',
            arg=[self.loc('archives').element_handle(), name])
        assert name in self.names(), f'The archive list does not contain {name!r}.'

    def wait_absent(self, name):
        self.page.wait_for_function('''([select, name]) =>
            ![...select.options].some(o => o.textContent === name)''',
            arg=[self.loc('archives').element_handle(), name])

    def wait_storage_change(self, before):
        self.page.wait_for_function('''before =>
            Object.entries(before).some(([key, raw]) => localStorage.getItem(key) !== raw)''',
            arg=before)

    def save(self, name, rows=None):
        if rows is not None:
            self.apply_map(rows)
        self.loc('name').fill(name)
        self.loc('save').click()
        self.wait_saved(name.strip())

    def select(self, name):
        options = self.loc('archives').evaluate('''e => [...e.options]
            .map(o => ({text: o.textContent, value: o.value}))''')
        matches = [option for option in options if option['text'] == name]
        assert len(matches) == 1, f'Expected exactly one visible archive named {name!r}.'
        self.loc('archives').select_option(value=matches[0]['value'])

    def load(self, name, rows, *, check_name=True):
        self.select(name)
        self.loc('load').click()
        self.wait_grid(rows)
        self.expect(self.loc('map_title')).to_have_text(name)
        if check_name:
            self.expect(self.loc('name')).to_have_value(name)

    def upload(self, payload, *, filename='acceptance-map.json'):
        if not isinstance(payload, bytes):
            payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        # Clear only the test's file selection, so a same-file retry also emits change.
        self.loc('import_file').set_input_files([])
        self.loc('import_file').set_input_files({'name': filename, 'mimeType': 'application/json', 'buffer': payload})

    def download(self, destination):
        with self.page.expect_download() as result:
            self.loc('export_file').click()
        result.value.save_as(destination)
        raw = Path(destination).read_bytes()
        assert len(raw) <= 16384, 'Exported map exceeds the exchange size limit.'
        return json.loads(raw.decode('utf-8'))

    def error(self):
        self.expect(self.loc('error')).to_be_visible()
        self.expect(self.loc('error')).not_to_have_text('')
        message = self.loc('error').inner_text()
        return message

    def snapshot(self):
        return {
            'storage': self.raw_storage(), 'grid': self.grid(),
            'map_input': self.loc('map_input').input_value(),
            'name': self.loc('name').input_value(), 'title': self.loc('map_title').inner_text(),
            'names': self.names(), 'selected': self.loc('archives').input_value(),
            'comparisons': self.loc('comparisons').inner_text(),
            'samples': self.loc('sample_count').inner_text(),
            'steps': self.loc('steps').inner_text(), 'energy': self.loc('energy').inner_text(),
        }

    def confirm_action(self, trigger, accept, *, before_choice=None, keyboard=False):
        """Run an action requiring confirmation; native decisions are explicit."""
        if self.config['confirmation'] == 'native':
            count = len(self.native_decisions)
            self._next_dialog_decision = accept
            with self.page.expect_event('dialog'):
                trigger()
            assert len(self.native_decisions) == count + 1, 'The operation did not request a native confirmation.'
        else:
            trigger()
            self.expect(self.loc('confirm_dialog')).to_be_visible()
            if before_choice:
                before_choice()
            button = 'confirm_yes' if accept else 'confirm_no'
            if keyboard:
                self.tab_to(button)
                self.page.keyboard.press('Space')
            else:
                self.loc(button).click()
            self.expect(self.loc('confirm_dialog')).not_to_be_visible()

    def tab_to(self, name, *, index=None):
        target = self.loc(name)
        if index is not None:
            target = target.nth(index)
        self.expect(target).to_have_count(1)
        self.expect(target).to_be_visible()
        for _ in range(260):
            if target.evaluate('(e) => e === document.activeElement'):
                return
            self.page.keyboard.press('Tab')
        raise AssertionError(f'Keyboard Tab could not reach {name}.')

    def accessible_name(self, name):
        """Check the browser-computed accessible name, independent of CSS naming."""
        self.expect(self.loc(name)).to_have_accessible_name(re.compile(r'\S'))

    def write_failure(self, enabled):
        self.page.evaluate('(enabled) => window.__robotAcceptanceProbe.configureWrites(enabled)', enabled)

    def write_attempts(self):
        return self.page.evaluate('window.__robotAcceptanceProbe.writeAttempts')
