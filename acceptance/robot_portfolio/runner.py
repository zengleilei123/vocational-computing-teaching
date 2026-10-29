"""Bind independent browser checks to an explicit local project and evidence.

This module never starts an application server or selects a teacher fallback.
The adapter is declarative JSON, not executable Python or JavaScript.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import time
import traceback
import unittest
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

from .browser import ConfigError, load_config


CASE_IDS = tuple(f'A{number:02d}' for number in range(1, 13))


class TargetError(RuntimeError):
    """The requested target could not be established; no acceptance was run."""

    def __init__(self, message, evidence=None):
        super().__init__(message)
        self.evidence = evidence


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_endpoint(value):
    """Only an explicitly named local, same-origin classroom service is supported."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise ConfigError('URL 无效；请填写带端口的本机 HTTP 地址。') from exc
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or not port or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or '\\' in value
            or any(ord(character) < 33 for character in value)):
        raise ConfigError('URL 必须是带端口的回环 HTTP 地址，不含凭据、查询或片段。')
    return parsed._replace(path=parsed.path or '/').geturl()


def select_cases(value):
    chosen = value.split(',')
    if not chosen or any(item not in CASE_IDS for item in chosen) or len(set(chosen)) != len(chosen):
        raise ConfigError('--cases 须为不重复的 A01–A12 编号，使用英文逗号连接。')
    return [item for item in CASE_IDS if item in chosen]


def local_source_files(config, root):
    """Hash only explicitly listed ordinary files inside the declared source root."""
    root = root.resolve()
    if not root.is_dir():
        raise ConfigError('--source-root 必须是实际学生工程的目录。')
    files = []
    for entry in config['source_files']:
        relative = Path(entry['path'])
        if (relative.is_absolute() or PureWindowsPath(entry['path']).drive
                or '..' in relative.parts or '\\' in entry['path']):
            raise ConfigError(f'源码路径必须位于 source-root 内：{entry["path"]}')
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ConfigError(f'源码核验不接受符号链接：{entry["path"]}')
        if not current.resolve().is_relative_to(root):
            raise ConfigError(f'源码路径越出 source-root：{entry["path"]}')
        if not current.is_file():
            raise ConfigError(f'找不到声明的源码文件：{entry["path"]}')
        content = current.read_bytes()
        files.append({'url': entry['url'], 'path': relative.as_posix(),
                      'local_bytes': len(content), 'local_sha256': sha256(content)})
    return files


def git_identity(root):
    """Record a working tree, without borrowing an enclosing checkout's identity."""
    unknown = {'kind': 'unknown', 'commit': None, 'dirty': None}
    if not (root / '.git').exists():
        return unknown
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=5)
        if result.returncode:
            raise TargetError('无法读取 Git 版本信息。')
        return result.stdout.strip()
    try:
        return {'kind': 'working-tree', 'commit': git('rev-parse', 'HEAD'),
                'dirty': bool(git('status', '--porcelain'))}
    except (OSError, subprocess.SubprocessError, TargetError):
        return unknown


def verify_target(browser, url, config, files):
    """Compare served asset bytes before any case is allowed to run."""
    context = browser.new_context()
    evidence = {'final_url': None, 'title': None, 'assets': [],
                'identity_scope': 'Only the listed static asset bytes are verified, not the whole server.'}
    try:
        page = context.new_page()
        origin = urlsplit(url)[:2]
        blocked = []

        def same_origin(route):
            target = urlsplit(route.request.url)
            if target.scheme in {'http', 'https'} and target[:2] != origin:
                blocked.append(route.request.url)
                route.abort()
            else:
                route.continue_()

        context.route('**/*', same_origin)
        response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
        evidence['final_url'] = page.url
        if response is None or not 200 <= response.status < 300:
            raise TargetError('目标页面未返回成功的 HTTP 响应。')
        if page.url != url:
            raise TargetError(f'目标发生跳转：请求 {url}，实际 {page.url}；请明确填写最终地址。')
        title = page.title()
        evidence['title'] = title
        known_reference = ('教师参考' in title
                           or page.locator('.teacher-badge').count() > 0)
        if config['target_kind'] == 'student' and known_reference:
            raise TargetError('该页面具有教师参考标记；不能作为学生作品报告。请启动自己的学生工程。')
        for entry in files:
            asset_url = urljoin(url, entry['url'])
            if urlsplit(asset_url)[:2] != origin:
                raise ConfigError('声明的 HTTP 资产必须与目标页面同源。')
            asset = context.request.get(asset_url, timeout=15000, max_redirects=0)
            try:
                content = asset.body()
                record = {**entry, 'requested_url': asset_url, 'observed_url': asset.url,
                          'http_status': asset.status, 'served_bytes': len(content),
                          'served_sha256': sha256(content)}
                record['matches'] = (asset.status == 200 and asset.url == asset_url
                                     and record['served_sha256'] == entry['local_sha256'])
                evidence['assets'].append(record)
                if not record['matches']:
                    raise TargetError(f'源码与实际 HTTP 资产不一致：{entry["url"]}。'
                                      '请检查端口、启动目录和浏览器所访问的版本。')
            finally:
                asset.dispose()
        if blocked:
            raise TargetError('页面请求了其他来源；当前验收入口只支持本机同源版本。')
        return evidence
    except TargetError as exc:
        exc.evidence = evidence
        raise
    finally:
        context.close()


def case_id(test):
    match = re.search(r'\.test_(A\d{2})(?:_|$)', test.id())
    return match.group(1) if match else None


def suite_ids(suite):
    identifiers = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            identifiers.extend(suite_ids(test))
        else:
            identifiers.append(case_id(test))
    return identifiers


class EvidenceResult(unittest.TextTestResult):
    """Keep real unittest outcomes; skips, missing IDs and zero cases cannot pass."""

    def __init__(self, stream, descriptions, verbosity, report, output):
        super().__init__(stream, descriptions, verbosity)
        self.report = report
        self.output = output
        self._started = {}

    def startTest(self, test):
        super().startTest(test)
        self._started[test.id()] = time.monotonic()
        identifier = case_id(test)
        if identifier in self.report['cases']:
            self.report['cases'][identifier]['status'] = 'running'

    def record(self, test, status, error=None):
        identifier = case_id(test)
        if identifier not in self.report['cases']:
            self.report['runner_errors'].append(str(test) + ': ' + status)
            return
        item = self.report['cases'][identifier]
        if item['status'] not in {'failed', 'blocked'}:
            item['status'] = status
        if error is not None:
            item['errors'].append(''.join(traceback.format_exception(*error)))
        if status == 'failed' and hasattr(test, 'capture_artifacts'):
            try:
                item['artifacts'].extend(test.capture_artifacts(self.output))
            except Exception as exc:
                item['artifact_errors'].append(str(exc))

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'failed', err)

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'failed', err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.record(test, 'failed', err)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'blocked')
        identifier = case_id(test)
        if identifier in self.report['cases']:
            self.report['cases'][identifier]['errors'].append('用例被跳过：' + reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, 'failed', err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'failed')

    def stopTest(self, test):
        identifier = case_id(test)
        if identifier in self.report['cases']:
            item = self.report['cases'][identifier]
            item['duration_seconds'] = round(time.monotonic() - self._started[test.id()], 3)
            item['artifacts'] = sorted(set(item['artifacts'] + list(getattr(test, 'artifacts', []))))
            for check in getattr(test, 'manual_checks', []):
                if check not in self.report['manual_review']:
                    self.report['manual_review'].append(check)
            if item['status'] == 'running':
                item['status'] = 'blocked'
                item['errors'].append('测试结束时缺少完成结果。')
        super().stopTest(test)


def make_report(url, adapter, root, selected):
    return {
        'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
        'finished_at': None, 'requested_url': url, 'adapter_path': str(adapter),
        'adapter_sha256': None, 'source_root': str(root), 'source': git_identity(root),
        'target_kind': 'unknown', 'label': None, 'purpose': 'not_established',
        'target': None, 'declared_sources': [], 'selected_ids': selected, 'expected_count': len(selected),
        'tests_run': 0, 'skipped': 0, 'runner_errors': [], 'blockers': [],
        'selected_automated_pass': False, 'all_contract_automated_pass': False,
        'acceptance_decision': 'not_issued',
        'manual_review': [
            {'id': 'A07-parser-scope', 'status': 'not_reviewed',
             'requirement': 'JSON.parse 探针仅覆盖当前页面主线程；Worker、自定义解析器须另交解析顺序证据。'},
            {'id': 'A10-visible-focus', 'status': 'not_reviewed',
             'requirement': '结合 A10 焦点截图与实际键盘操作人工复核焦点可见性；未发出 WCAG 合规结论。'},
        ],
        'cases': {identifier: {'status': 'not_run', 'errors': [], 'artifacts': [],
                               'artifact_errors': [], 'duration_seconds': None}
                  for identifier in CASE_IDS},
    }


def finish_report(report, result=None):
    if result is not None:
        report['tests_run'] = result.testsRun
        report['skipped'] = len(result.skipped)
    good = (result is not None and result.testsRun == report['expected_count'] > 0
            and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and not result.failures and not result.errors
            and not report['runner_errors'] and not report['blockers']
            and all(report['cases'][identifier]['status'] == 'passed'
                    for identifier in report['selected_ids']))
    report['selected_automated_pass'] = good
    report['all_contract_automated_pass'] = good and report['selected_ids'] == list(CASE_IDS)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    return 0 if good else (2 if report['blockers'] else 1)


def write_report(report, output):
    (output / 'report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    status = {'passed': '通过', 'failed': '失败', 'blocked': '阻塞', 'not_run': '未运行'}
    # Values are quoted JSON strings in a fenced block, not interpolated Markdown.
    identity = {name: report[name] for name in (
        'requested_url', 'source_root', 'source', 'adapter_path', 'adapter_sha256',
        'target_kind', 'purpose', 'label', 'target')}
    lines = ['# 地图作品集自动验收证据', '',
             '**这份报告不是评分或完整验收结论；仍需完成人工复核与个人讲解。**', '',
             f'实际执行 {report["tests_run"]} 项；本次选择 {report["expected_count"]} 项；'
             f'跳过 {report["skipped"]} 项。', '',
             f'所选自动检查全部通过：{report["selected_automated_pass"]}。',
             f'完整 A01–A12 自动检查全部通过：{report["all_contract_automated_pass"]}。', '',
             '| 编号 | 结果 |', '|---|---|']
    for identifier, item in report['cases'].items():
        lines.append(f'| {identifier} | {status.get(item["status"], item["status"])} |')
    lines += ['', '## 被测对象与来源', '', '```json',
              json.dumps(identity, ensure_ascii=False, indent=2).replace('```', '\\u0060' * 3),
              '```', '', '## 人工复核', '']
    lines += ['- ' + item['requirement'] for item in report['manual_review']]
    lines += ['', '详细异常、阻塞原因和截图路径见同目录 report.json。', '']
    (output / 'summary.md').write_text('\n'.join(lines), encoding='utf-8')


def run(args):
    output = Path(args.output).resolve()
    try:
        # Existing directories are rejected even if empty: never mix old evidence.
        if Path(args.output).is_symlink():
            raise FileExistsError('输出路径是符号链接。')
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f'无法建立新的报告目录：{exc}', file=sys.stderr)
        return 2
    root = Path(args.source_root).resolve()
    adapter = Path(args.adapter).resolve()
    report = make_report(args.url, adapter, root, list(CASE_IDS))
    result = None
    try:
        selected = select_cases(args.cases)
        report['selected_ids'], report['expected_count'] = selected, len(selected)
        url = parse_endpoint(args.url)
        report['requested_url'] = url
        report['adapter_sha256'] = sha256(adapter.read_bytes())
        config = load_config(adapter)
        report['target_kind'], report['label'] = config['target_kind'], config['label']
        report['purpose'] = ('reference_calibration' if config['target_kind'] == 'reference'
                             else 'student_project_evidence')
        if config['target_kind'] == 'reference' and not args.allow_reference:
            raise ConfigError('教师适配器只用于校准；须显式加 --allow-reference，不会生成学生成绩。')
        if config['target_kind'] == 'student' and args.allow_reference:
            raise ConfigError('--allow-reference 只与 reference 适配器配合，不能为 student 绕过目标核验。')
        files = local_source_files(config, root)
        report['declared_sources'] = files
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise TargetError('缺少 Playwright；请按验收 README 安装依赖和 Chromium。') from exc
        with sync_playwright() as playwright:
            launch = {'headless': True}
            if os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'):
                launch['executable_path'] = os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE']
            try:
                browser = playwright.chromium.launch(**launch)
            except Exception as exc:
                raise TargetError(f'Chromium 无法启动，验收未运行：{exc}') from exc
            try:
                try:
                    report['target'] = verify_target(browser, url, config, files)
                except (ConfigError, TargetError):
                    raise
                except Exception as exc:
                    raise TargetError(f'无法核验请求的本机服务，验收未运行：{exc}') from exc
                from .cases import build_suite
                suite = build_suite(browser, config, url, output, selected)
                discovered = suite_ids(suite)
                if (any(identifier not in CASE_IDS for identifier in discovered)
                        or sorted(discovered) != sorted(selected)):
                    raise TargetError('发现的测试编号与本次请求不一致；拒绝产生不完整通过报告。')
                captured = []
                def factory(stream, descriptions, verbosity):
                    created = EvidenceResult(stream, descriptions, verbosity, report, output)
                    captured.append(created)
                    return created
                try:
                    unittest.TextTestRunner(verbosity=2, resultclass=factory).run(suite)
                finally:
                    if captured:
                        result = captured[0]
            finally:
                browser.close()
    except (ConfigError, TargetError, OSError, ValueError) as exc:
        report['blockers'].append(str(exc))
        if isinstance(exc, TargetError) and exc.evidence is not None:
            report['target'] = exc.evidence
        for identifier in report['selected_ids']:
            if report['cases'][identifier]['status'] == 'not_run':
                report['cases'][identifier]['status'] = 'blocked'
    except KeyboardInterrupt:
        report['blockers'].append('运行被中断；尚未执行的用例不能计为通过。')
        for identifier in report['selected_ids']:
            if report['cases'][identifier]['status'] in {'not_run', 'running'}:
                report['cases'][identifier]['status'] = 'blocked'
    except Exception:
        report['runner_errors'].append(traceback.format_exc())
    code = finish_report(report, result)
    try:
        write_report(report, output)
    except OSError as exc:
        print(f'报告写入失败，不能交付完整证据：{exc}', file=sys.stderr)
        return 2
    print(f'报告：{output / "report.json"}')
    print(f'实际执行 {report["tests_run"]}/{report["expected_count"]} 项；'
          f'完整 A01–A12 自动通过：{report["all_contract_automated_pass"]}；人工复核待完成。')
    for message in report['blockers']:
        print('阻塞：' + message, file=sys.stderr)
    return code


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='实际运行的学生工程回环 HTTP URL，须带端口')
    parser.add_argument('--adapter', required=True, help='与实际页面对应的 JSON 适配器')
    parser.add_argument('--source-root', required=True, help='声明的源码根目录')
    parser.add_argument('--output', required=True, help='尚不存在的报告目录')
    parser.add_argument('--cases', default=','.join(CASE_IDS), help='本次执行的 A 编号，以英文逗号连接')
    parser.add_argument('--allow-reference', action='store_true', help='仅用于明确的教师参考校准')
    return run(parser.parse_args(argv))
