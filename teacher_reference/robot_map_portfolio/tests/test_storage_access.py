"""Teacher-only browser regressions for denied storage reads and recovery.

These checks supplement, rather than redefine, the student A01–A12 contract.
Compose the existing HTTP/browser fixture without inheriting its twelve tests.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from teacher_reference.robot_map_portfolio.tests import test_acceptance as reference


def storage_probe(mode, records):
    """Install before application code; retain a raw observer outside the fault.

    The observer calls the original browser getter/method. It never reads the
    reference store or decodes its internal state. Method probes target only
    this page's map key; getter denial blocks the entire localStorage API in
    this isolated context. All patches can be explicitly restored.
    """
    arguments = json.dumps({
        'mode': mode,
        'key': reference.STORAGE_KEY,
        'raw': json.dumps(records, ensure_ascii=False, separators=(',', ':')),
    }, ensure_ascii=False)
    return '''(({mode, key, raw}) => {
        const descriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
        const storage = descriptor.get.call(window);
        const getItem = Storage.prototype.getItem;
        const setItem = Storage.prototype.setItem;
        setItem.call(storage, key, raw);
        const probe = window.__storageAccessRegression = {
            mode, getterDenied: 0, readDenied: 0, writeAttempts: 0,
            raw: () => getItem.call(storage, key),
            restore: () => {
                Object.defineProperty(window, 'localStorage', descriptor);
                Storage.prototype.getItem = getItem;
                Storage.prototype.setItem = setItem;
                probe.mode = 'none';
            },
        };
        Object.defineProperty(window, 'localStorage', {
            ...descriptor,
            get() {
                if (probe.mode === 'access') {
                    probe.getterDenied++;
                    throw new DOMException('Injected storage permission denial', 'SecurityError');
                }
                return descriptor.get.call(this);
            },
        });
        Storage.prototype.getItem = function (candidate) {
            if (this === storage && candidate === key && probe.mode === 'read') {
                probe.readDenied++;
                throw new DOMException('Injected storage read denial', 'SecurityError');
            }
            return getItem.call(this, candidate);
        };
        Storage.prototype.setItem = function (candidate, value) {
            if (this === storage && candidate === key) probe.writeAttempts++;
            return setItem.call(this, candidate, value);
        };
    })(''' + arguments + ');'


class StorageAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Register first so a partial browser setup also releases its HTTP server.
        cls.addClassCleanup(reference.PortfolioAcceptanceTests.doClassCleanups)
        reference.PortfolioAcceptanceTests.setUpClass()

    def setUp(self):
        self.app = reference.PortfolioAcceptanceTests()
        self.app.page_errors = []
        self.app.requests = []
        self.addCleanup(self.app.doCleanups)
        self.addCleanup(self.app.tearDown)

    def open(self, mode, records):
        self.app.page = self.app._new_page(storage_probe(mode, records))
        self.page = self.app.page

    def probe(self, field):
        return self.page.evaluate(
            '(field) => window.__storageAccessRegression[field]', field
        )

    def raw_storage(self):
        return self.page.evaluate('window.__storageAccessRegression.raw()')

    def snapshot(self):
        # Observe the same visible/runtime state as the existing teacher suite,
        # but read persistent bytes through the original getter while denied.
        return self.page.evaluate('''() => ({
            stored: window.__storageAccessRegression.raw(),
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
        })''')

    def assert_read_error(self):
        self.app._expect_error()
        self.app.expect(self.page.locator('#portfolio-status')).to_contain_text('本地存储')
        self.app.expect(self.page.locator('#portfolio-save')).to_be_enabled()

    def test_startup_storage_access_denied_keeps_edit_export_and_recovers(self):
        existing = [reference.document('已保存 A', reference.MAP_A)]
        self.open('access', existing)
        raw_before = self.raw_storage()
        self.assertGreater(self.probe('getterDenied'), 0,
                           'The application must actually encounter the denied getter.')
        self.assert_read_error()
        self.assertEqual(self.probe('writeAttempts'), 0)
        self.assertEqual(json.loads(raw_before), existing)

        # The unavailable archive must not disable unrelated map editing/export.
        self.app._apply_map(reference.MAP_B)
        self.page.locator('#portfolio-name').fill('临时编辑 B')
        before = self.snapshot()
        denied_before = self.probe('getterDenied')
        self.page.locator('#portfolio-save').click()
        self.assert_read_error()
        self.assertGreater(self.probe('getterDenied'), denied_before)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.probe('writeAttempts'), 0)
        with tempfile.TemporaryDirectory(prefix='robot-denied-export-') as directory:
            exported = self.app._download_map(Path(directory) / 'map.json')
        self.assertEqual(exported, reference.document('临时编辑 B', reference.MAP_B))
        self.assertEqual(self.raw_storage(), raw_before)
        self.assertEqual(self.probe('writeAttempts'), 0)

        # Remove the injected denial and retry through ordinary UI controls.
        # No deletion, browser reset or new storage container is needed.
        self.page.evaluate('window.__storageAccessRegression.restore()')
        self.app._save('临时编辑 B')
        self.assertEqual(self.app._records(),
                         existing + [reference.document('临时编辑 B', reference.MAP_B)])
        self.app._load('已保存 A', reference.MAP_A)

    def test_runtime_storage_read_denied_preserves_operations_then_recovers(self):
        existing = [reference.document('已保存 A', reference.MAP_A),
                    reference.document('已保存 B', reference.MAP_B)]
        self.open('none', existing)
        self.app._load('已保存 A', reference.MAP_A)
        self.app._apply_map(reference.MAP_C)
        raw_before = self.raw_storage()
        self.page.evaluate("window.__storageAccessRegression.mode = 'read'")

        for action in ('save', 'overwrite', 'load', 'import', 'delete'):
            with self.subTest(action=action):
                # Establish the exact starting UI for each requested operation.
                self.page.locator('#portfolio-name').fill(
                    '已保存 A' if action == 'overwrite' else '待保存 C'
                )
                self.page.locator('#portfolio-list').select_option('已保存 A')
                self.page.evaluate('''() => {
                    const status = document.getElementById('portfolio-status');
                    status.textContent = '等待当前操作';
                    status.classList.remove('error');
                }''')
                before = self.snapshot()
                denied_before = self.probe('readDenied')
                if action in ('save', 'overwrite'):
                    self.page.locator('#portfolio-save').click()
                elif action == 'load':
                    self.page.locator('#portfolio-load').click()
                elif action == 'import':
                    self.app._upload(reference.document('导入 D', reference.MAP_B))
                else:
                    self.page.locator('#portfolio-delete').click()
                    self.app._confirm(True)
                self.assert_read_error()
                self.assertGreater(self.probe('readDenied'), denied_before,
                                   'This operation must actually reach the injected failure.')
                self.assertEqual(self.snapshot(), before,
                                 'A denied read must not commit a partial UI or archive update.')
                self.assertEqual(self.raw_storage(), raw_before)
                self.assertEqual(self.probe('writeAttempts'), 0,
                                 'Unreadable existing data must never be replaced with an empty store.')
                self.app.expect(self.page.locator('#portfolio-confirm')).not_to_be_visible()

        self.page.evaluate('window.__storageAccessRegression.restore()')
        self.app._save('恢复后 C')
        self.assertEqual(self.app._records(),
                         existing + [reference.document('恢复后 C', reference.MAP_C)])
        self.app._load('已保存 B', reference.MAP_B)
        self.app._upload(reference.document('恢复后 D', reference.MAP_A))
        self.app._wait_grid(reference.MAP_A)
        self.app.expect(self.page.locator('#portfolio-status')).not_to_have_class(
            re.compile(r'\berror\b')
        )
        self.assertEqual(self.app._records(), existing + [
            reference.document('恢复后 C', reference.MAP_C),
            reference.document('恢复后 D', reference.MAP_A),
        ])


if __name__ == '__main__':
    unittest.main()
