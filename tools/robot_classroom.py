"""Offline classroom diagnostics and an explicit, answer-free student ZIP.

Python 3.10+; standard library only. Run from any working directory by passing
this script's path. Neither command installs software or changes configuration.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]

# An explicit list prevents new teacher answers, personal files, Git history,
# and unrelated projects from silently becoming part of a later student pack.
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
BUNDLE_FILES = ROBOT_FILES + (
    'curriculum/ai-assisted-development/CAPSTONE.md',
    'curriculum/ai-assisted-development/WORK-CARDS.md',
    'curriculum/ai-assisted-development/SOURCES.md',
    'classroom/robot_portfolio/student/START.md',
    'classroom/robot_portfolio/student/DIAGNOSTIC.md',
    'classroom/robot_portfolio/student/WORKBOOK.md',
    'classroom/robot_portfolio/student/SUBMISSION.md',
    'classroom/robot_portfolio/student/acceptance-adapter.example.json',
    'acceptance/__init__.py',
    'acceptance/robot_portfolio/__init__.py',
    'acceptance/robot_portfolio/__main__.py',
    'acceptance/robot_portfolio/runner.py',
    'acceptance/robot_portfolio/browser.py',
    'acceptance/robot_portfolio/cases.py',
    'acceptance/robot_portfolio/README.md',
    'acceptance/robot_portfolio/SOURCES.md',
    'tools/robot_classroom.py',
    'LICENSE-CODE',
    'LICENSE-DOCS.md',
)
RUNTIME_FILES = (
    'projects/robot_playground/__init__.py',
    'projects/robot_playground/engine.py',
    'projects/robot_playground/glyphs.py',
    'projects/robot_playground/server.py',
    'projects/robot_playground/student_strategy.py',
    'projects/robot_playground/static/app.js',
    'projects/robot_playground/static/index.html',
    'projects/robot_playground/static/style.css',
)


class ClassroomError(Exception):
    """An actionable failure; callers must not report a completed bundle."""


def checked_file(root, relative):
    """Reject symlinks in every in-root component, including parent folders."""
    candidate = root
    for part in Path(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ClassroomError(f'拒绝符号链接：{relative}（链接位置：{candidate}）。')
    if not candidate.is_file():
        raise ClassroomError(f'缺少必需文件或路径不是普通文件：{relative}。请恢复材料后重试。')
    return candidate


def shell_commands(root, port):
    """Present commands for the platform's usual interactive shell."""
    if os.name == 'nt':
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        change_directory = f'Set-Location -LiteralPath {quote(root)}'
        python = f'& {quote(sys.executable)}'
    else:
        change_directory = f'cd -- {shlex.quote(str(root))}'
        python = shlex.quote(sys.executable)
    return {
        'change_directory': change_directory,
        'start': f'{python} -m projects.robot_playground.server --port {port}',
        'test': (f'{python} -m unittest discover -s projects/robot_playground '
                 '-p "test_*.py" -v'),
    }


def doctor(root, port):
    checks = []

    def add(identifier, status, required, message):
        checks.append({'id': identifier, 'status': status,
                       'required': required, 'message': message})

    supported = sys.version_info >= (3, 10)
    add('python', 'pass' if supported else 'fail', True,
        f'当前 Python {sys.version.split()[0]}；需要 Python 3.10 或更高版本。')
    missing = []
    for relative in RUNTIME_FILES:
        try:
            checked_file(root, relative)
        except (ClassroomError, OSError) as exc:
            missing.append(str(exc))
    add('files', 'fail' if missing else 'pass', True,
        '；'.join(missing) if missing else '运行所需源码与页面文件齐全；未用起始哈希限制学生修改。')

    in_root = Path.cwd().resolve() == root
    add('cwd', 'pass' if in_root else 'warning', False,
        '当前位于项目根目录。' if in_root else
        f'当前目录不是项目根目录；工具已定位到 {root}。启动前先执行下方切换目录命令。')

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            # Windows permits some rebinding combinations unless exclusivity is
            # requested. Do not use SO_REUSEADDR for this availability check.
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(('127.0.0.1', port))
    except OSError as exc:
        add('port', 'fail', True,
            f'回环端口 127.0.0.1:{port} 无法绑定，可能已被占用或受到权限限制。'
            f'请停止自己的旧服务，或用 --port 8767 重新检查并以同一端口启动。系统信息：{exc}')
    else:
        add('port', 'pass', True,
            f'检查时可绑定 127.0.0.1:{port}；本次已释放端口，正式启动前仍可能被其他程序占用。')

    node = shutil.which('node')
    if node:
        try:
            result = subprocess.run([node, '--version'], capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=5)
            match = re.fullmatch(r'v(\d+)\.\d+\.\d+', result.stdout.strip())
            usable = result.returncode == 0 and match is not None and int(match.group(1)) >= 20
            add('node', 'pass' if usable else 'warning', False,
                f'Node 检查结果：{result.stdout.strip() or "无法识别版本"}。'
                '开发期核心测试建议 Node 20+；未满足不影响打开基础课堂页面。')
        except (OSError, subprocess.SubprocessError):
            add('node', 'warning', False, 'Node 无法执行；仅影响可选 JavaScript 检查，不阻止基础运行。')
    else:
        add('node', 'warning', False, '未发现 Node；仅影响可选 JavaScript 检查，不阻止基础运行。')
    try:
        has_playwright = importlib.util.find_spec('playwright') is not None
    except (ImportError, ValueError):
        has_playwright = False
    add('playwright', 'pass' if has_playwright else 'warning', False,
        '已发现 Playwright 包；尚未执行浏览器测试。' if has_playwright else
        '未发现 Playwright；仅影响可选浏览器测试，不阻止基础运行。')
    add('chromium', 'not_checked', False,
        'Chromium 未检查：本命令没有启动浏览器，不能证明浏览器已安装或端到端测试已通过。')
    return {
        'ready': all(check['status'] == 'pass' for check in checks if check['required']),
        'root': str(root),
        'checks': checks,
        'commands': shell_commands(root, port),
    }


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def fixture_files():
    def document(name='校园地图', grid=None, version=1):
        return {'version': version, 'name': name,
                'grid': ['S..', '.#.', '..G'] if grid is None else grid}

    documents = {
        'valid-map.json': document(),
        'unknown-version.json': document(version=2),
        'missing-goal.json': document(grid=['S..', '.#.', '...']),
        'duplicate-start.json': document(grid=['SS.', '.#.', '..G']),
        'unequal-rows.json': document(grid=['S..', '.#', '..G']),
        'html-name.json': document(name='<b>地图</b>'),
        'unicode-name-40.json': document(name='🧭' * 40),
    }
    files = {f'fixtures/{name}': json_bytes(value) for name, value in documents.items()}
    files['fixtures/invalid-json.json'] = b'{"version": 1,\n'
    boundary = json_bytes(document(name='字节边界地图'))
    files['fixtures/boundary-16384.json'] = boundary + b' ' * (16384 - len(boundary))
    files['fixtures/oversize-16385.json'] = boundary + b' ' * (16385 - len(boundary))
    files['fixtures/README.md'] = '''# 地图导入验收输入

这些文件只是独立测试输入，不包含保存、加载、导入或导出的实现。
原始学生项目尚未实现作品集导入；完成相应功能后，记录实际结果。
下表是验收预期，不是已经自动执行并通过的报告。

| 文件 | 输入特点 | 预期观察 |
|---|---|---|
| valid-map.json | 合法 3×3 地图 | 按契约恢复名称与网格 |
| invalid-json.json | JSON 语法损坏 | 可读错误，当前地图和存档不变 |
| unknown-version.json | version 为 2 | 拒绝未知版本，原状态不变 |
| missing-goal.json | 缺少 G | 拒绝，原状态不变 |
| duplicate-start.json | 两个 S | 拒绝，原状态不变 |
| unequal-rows.json | 行宽不同 | 拒绝，原状态不变 |
| html-name.json | 名称含 HTML 标签文字 | 原样作为普通文本显示，不执行 HTML |
| unicode-name-40.json | 40 个非 BMP Unicode 码点 | 名称边界允许；不能按 UTF-16 长度拒绝 |
| boundary-16384.json | 恰好 16,384 个 UTF-8 字节 | 大小边界允许，仍需执行结构校验 |
| oversize-16385.json | 恰好 16,385 个 UTF-8 字节 | 解析前拒绝，原状态不变 |

两个字节边界文件来自相同的合法 JSON，差别只有一个尾随空格；
JSON 结构本身都合法。名称的 Unicode 码点与文件的 UTF-8 字节是不同约束。
只观察页面拒绝结果不能证明检查发生于解析前；请用自己的测试或调试证据验证顺序。
测试时另行构造空名称、41 码点、取消覆盖/删除和存储失败等反例。

完整约束见 [综合任务书](../curriculum/ai-assisted-development/CAPSTONE.md)。
按 [提交模板](../classroom/robot_portfolio/student/SUBMISSION.md) 记录被测对象和证据。
'''.encode('utf-8')
    return files


def source_information(root):
    unknown = {'kind': 'unknown', 'commit': None, 'dirty': None}
    # Do not let Git walk up to an unrelated outer repository after extraction.
    # A .git file is valid for an explicitly created Git worktree.
    marker = root / '.git'
    if not marker.exists() or marker.is_symlink():
        return unknown
    git = shutil.which('git')
    if not git:
        return unknown

    def git_output(*args):
        return subprocess.run([git, '-C', str(root), *args], check=True,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=5).stdout.strip()

    try:
        if Path(git_output('rev-parse', '--show-toplevel')).resolve() != root:
            return unknown
        commit = git_output('rev-parse', '--verify', 'HEAD')
        if not re.fullmatch(r'[0-9a-f]{40,64}', commit):
            return unknown
        dirty = bool(git_output('status', '--porcelain=v1', '--untracked-files=normal'))
    except (OSError, subprocess.SubprocessError):
        return unknown
    return {'kind': 'working-tree', 'commit': commit, 'dirty': dirty}


def bundle_readme():
    return '''# 机器人地图作品集：学生起始包

从 [首次启动与学习入口](classroom/robot_portfolio/student/START.md) 开始。
本包提供原机器人挑战场、学习单和测试输入；作品集的保存、加载、删除、
JSON 导入与导出仍需由你按 [任务书](curriculum/ai-assisted-development/CAPSTONE.md) 完成。

## 首次运行

需要 Python 3.10+。先解压，再在本包根目录运行；不要在 ZIP 内或双击 HTML 启动。
某些系统使用 python3，Windows 也可使用 py -3；详细说明见首次启动学习单。

```text
python tools/robot_classroom.py doctor --port 8765
python -m projects.robot_playground.server --port 8765
```

浏览器打开 http://127.0.0.1:8765，Ctrl+C 退出服务。
Node 和 Playwright 都不是基础运行的必需依赖。诊断器不自动安装软件。
基础测试命令：

```text
python -m unittest discover -s projects/robot_playground -p "test_*.py" -v
```

## 学习与证据

- [先修诊断](classroom/robot_portfolio/student/DIAGNOSTIC.md)
- [五阶段工作簿](classroom/robot_portfolio/student/WORKBOOK.md)
- [提交与独立验收记录](classroom/robot_portfolio/student/SUBMISSION.md)
- [针对自己作品的 A01–A12 自动检查](acceptance/robot_portfolio/README.md)
- [待填写的界面适配模板](classroom/robot_portfolio/student/acceptance-adapter.example.json)
- [导入测试输入及预期](fixtures/README.md)
- [AI 协作工作卡](curriculum/ai-assisted-development/WORK-CARDS.md)

环境诊断和旧测试通过不能证明你新增的作品集功能已完成。
自动检查需要另装 Playwright 与 Chromium，填写自己的界面适配并指定实际学生服务 URL；
模板故意保留待填写项，运行器不会代你启动教师答案或实现存档功能。
本包不含教师参考实现或 Git 历史；Git 回退练习先在自己的副本初始化练习仓库。
公开仓库中的参考材料仍可公开阅读，文件发放隔离不是保密措施。

## 文件来源

MANIFEST.json 记录每个其他文件的 UTF-8 路径、字节数和 SHA-256；它不包含自己的哈希。
来源是打包时的工作树，commit/dirty 为 null 表示无法确认 Git 来源，不能冒充提交快照。
清单用于交接核对，不是学生作业评分规则；学生可以按任务修改源码。
同样的输入字节与来源信息生成同样的 ZIP，包内没有当前时间或机器绝对路径。

许可证见 [代码许可](LICENSE-CODE) 和 [文档许可](LICENSE-DOCS.md)。
'''.encode('utf-8')


def bundle(root, output):
    output = Path(output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ClassroomError(f'输出目标已存在，拒绝覆盖：{output}。请换一个文件名。')
    files = {}
    for relative in BUNDLE_FILES:
        try:
            files[relative] = checked_file(root, relative).read_bytes()
        except OSError as exc:
            raise ClassroomError(f'无法读取 {relative}：{exc}。未生成学生包。') from exc
    files['README.md'] = bundle_readme()
    files.update(fixture_files())
    source = source_information(root)
    files['MANIFEST.json'] = json_bytes({
        'format_version': 1,
        'source': source,
        'files': [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())],
    })

    # Generate fully in memory before publishing. Fixed metadata and ZIP_STORED
    # avoid timestamps, local permissions, and zlib versions changing the bytes.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    created = False
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects an output that appeared after the
        # initial check. Existing files and dangling symlinks are never followed.
        with output.open('xb') as stream:
            created = True
            stream.write(buffer.getvalue())
    except BaseException as exc:
        # Ctrl+C and other interruptions also leave the exclusive output owned
        # by this call. Close (via the context manager), clean it, then preserve
        # the interruption; do not remove a file that appeared before open().
        if created:
            output.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise ClassroomError(f'无法写入学生包，未保留半包：{exc}') from exc
        raise
    return {'output': str(output), 'files': len(files), 'source': source}


def port_number(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('端口必须是 1–65535 的整数。') from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('端口必须是 1–65535 的整数。')
    return port


def main(argv=None):
    # Keep CLI text and JSON readable in redirected output too. In particular,
    # a cp1252 pipe must not turn an already-created ZIP into a false failure.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8', errors='backslashreplace')
    parser = argparse.ArgumentParser(description='机器人课堂环境诊断与学生起始包（只用标准库）。')
    commands = parser.add_subparsers(dest='command', required=True)
    diagnose = commands.add_parser('doctor', help='检查基础运行条件，不安装或修改配置')
    diagnose.add_argument('--port', type=port_number, default=8765)
    diagnose.add_argument('--json', action='store_true', help='输出机器可读诊断结果')
    package = commands.add_parser('bundle', help='按白名单发放学生起始包，不含教师答案')
    package.add_argument('--output', required=True, help='新 ZIP 路径；已有目标不会被覆盖')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            report = doctor(ROOT, args.port)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                labels = {'pass': '通过', 'fail': '需处理', 'warning': '提示', 'not_checked': '未检查'}
                for check in report['checks']:
                    level = '必需' if check['required'] else '辅助'
                    print(f'[{labels[check["status"]]} / {level}] {check["message"]}')
                print('\n基础运行条件已满足。' if report['ready'] else '\n请先处理必需项中的阻塞。')
                print('环境诊断不等于功能验收；不会自动安装、修复或给学生作品评分。')
                print('\n切换到根目录，然后启动：')
                print(report['commands']['change_directory'])
                print(report['commands']['start'])
                print('\n基础测试（在另一个终端的同一根目录运行）：')
                print(report['commands']['test'])
            return 0 if report['ready'] else 1
        result = bundle(ROOT, args.output)
        print(f'学生包已生成：{result["output"]}（{result["files"]} 个文件）。')
        print('发放前请解压到独立目录，运行 doctor 和原有测试。地图存档功能仍由学生实现。')
        return 0
    except (ClassroomError, OSError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
