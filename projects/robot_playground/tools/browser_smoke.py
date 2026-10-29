"""Optional browser QA. Requires playwright and Chromium; runtime app does not.
Run from repo root: python -m projects.robot_playground.tools.browser_smoke
Uses PLAYWRIGHT_CHROMIUM_EXECUTABLE when set, otherwise Playwright's Chromium.
"""
import json
import os
import tempfile
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from projects.robot_playground.server import make_server, STATIC
from projects.robot_playground.engine import PRESETS, solve, replay
from projects.robot_playground.glyphs import classify, evaluate
from projects.robot_playground.student_strategy import plan
from projects.robot_playground.glyphs import DEMO_TRAIN


def main():
    server = make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    directory = Path(os.getenv('ROBOT_QA_DIR', tempfile.mkdtemp(prefix='robot-qa-')))
    directory.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        with sync_playwright() as p:
            opts = {'headless': True, 'args': ['--no-sandbox']}
            if os.getenv('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
                opts['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
            browser = p.chromium.launch(**opts)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
            page.on('pageerror', lambda error: errors.append(str(error)))
            if os.getenv('ROBOT_OFFLINE_DOM') == '1':
                # Offline component test: no URL navigation or network-policy changes.
                # Real HTTP is independently exercised by test_playground.HttpTests.
                def dispatch(endpoint, data):
                    try:
                        if endpoint == '/api/presets':
                            result = {'maps': PRESETS, 'train': DEMO_TRAIN}
                        elif endpoint == '/api/solve':
                            if data.get('algorithm') == 'student':
                                actions = plan(data['grid'])
                                result = {**replay(data['grid'], actions), 'actions': actions, 'expanded': [], 'algorithm': 'student'}
                            else:
                                result = solve(data['grid'], data.get('algorithm', 'bfs'))
                        elif endpoint == '/api/replay':
                            result = replay(data['grid'], data['actions'])
                        elif endpoint == '/api/classify':
                            result = classify(data['train'], data['pixels'], data.get('k', 1))
                        else:
                            result = evaluate(data['train'], data['test'], data.get('k', 1))
                        return {'ok': True, 'body': result}
                    except (ValueError, TypeError) as exc:
                        return {'ok': False, 'body': {'error': str(exc)}}
                page.expose_function('offlineDomain', dispatch)
                html = (STATIC / 'index.html').read_text().replace('<link rel="stylesheet" href="/style.css">', '').replace('<script src="/app.js" defer></script>', '')
                page.set_content(html)
                page.add_style_tag(content=(STATIC / 'style.css').read_text())
                page.add_script_tag(content="window.fetch = async (url, opts={}) => {const r=await window.offlineDomain(url, opts.body ? JSON.parse(opts.body) : {});return {ok:r.ok,json:async()=>r.body};};")
                page.add_script_tag(content=(STATIC / 'app.js').read_text())
            else:
                page.goto(f'http://127.0.0.1:{server.server_port}')
            expect(page.locator('#map-title')).to_have_text('近路不一定省电')
            page.locator('#bfs').click()
            expect(page.locator('#comparisons')).to_contain_text('46')
            page.locator('#dijkstra').click()
            expect(page.locator('#comparisons')).to_contain_text('Dijkstra')
            page.locator('#frame').focus()
            page.locator('#frame').press('End')
            expect(page.locator('#state')).to_have_text('已到达')
            expect(page.locator('#energy')).to_have_text('10')
            page.screenshot(path=str(directory / 'desktop.png'), full_page=True)
            page.locator('#reset').click()
            page.locator('[data-move="right"]').click()
            expect(page.locator('#steps')).to_have_text('1')
            expect(page.locator('#energy')).to_have_text('9')
            page.locator('.editor summary').click()
            page.locator('[data-brush="#"]').click()
            page.locator('#grid button').nth(11).click()
            page.locator('#student').click()
            expect(page.locator('#comparisons')).to_contain_text('未到达')
            page.locator('#presets button').first.click()
            page.locator('[data-brush="play"]').click()
            page.locator('#demo-data').click()
            right = next(s['pixels'] for s in DEMO_TRAIN if s['label'] == 'right')
            for index, value in enumerate(right):
                if value:
                    page.locator('#pad button').nth(index).press('Space')
            page.locator('#recognize').click()
            expect(page.locator('#prediction')).to_contain_text('预测：右')
            expect(page.locator('#execute')).to_be_enabled()
            page.locator('#execute').click()
            expect(page.locator('#steps')).to_have_text('1')
            page.locator('#pad button').nth(0).press('Space')
            expect(page.locator('#execute')).to_be_disabled()
            page.locator('#label').select_option('right')
            page.locator('#add-test').click()
            page.locator('#evaluate').click()
            expect(page.locator('#evaluation')).to_contain_text('当前留出集 1 条')
            with page.expect_download() as info:
                page.locator('#export').click()
            downloaded = directory / 'experiment.json'
            info.value.save_as(downloaded)
            report = json.loads(downloaded.read_text())
            assert len(report['train']) == 4 and len(report['test']) == 1
            page.locator('#map-text').fill('bad')
            page.locator('#apply-map').click()
            expect(page.locator('#notice')).to_have_class('notice error')
            assert page.locator('#grid button').count() == 45
            page.locator('#clear-pad').click()
            page.locator('#recognize').click()
            expect(page.locator('#prediction')).to_contain_text('暂不判断')
            page.locator('#presets button').nth(2).click()
            page.locator('#bfs').click()
            expect(page.locator('#notice')).to_contain_text('unreachable')
            page.set_viewport_size({'width': 390, 'height': 844})
            page.locator('#presets button').first.click()
            page.screenshot(path=str(directory / 'mobile.png'), full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors, errors
            browser.close()
            print(json.dumps({'browser': 'chromium', 'mode': 'offline-dom' if os.getenv('ROBOT_OFFLINE_DOM') == '1' else 'http', 'desktop': '1440x1100', 'mobile': '390x844',
                'checks': ['route comparison', 'replay', 'manual move', 'map editor', 'student collision',
                           'keyboard drawing', 'glyph classification', 'explicit movement', 'holdout evaluation',
                           'export', 'invalid map', 'blank rejection', 'unreachable map', 'mobile overflow'],
                'page_errors': errors, 'artifacts': str(directory)}, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    main()
