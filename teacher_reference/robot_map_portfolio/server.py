"""Isolated teacher reference; reuse the unmodified student playground backend."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from projects.robot_playground.server import Handler as StudentHandler, STATIC as STUDENT_STATIC

STATIC = Path(__file__).parent / 'static'
ASSETS = {
    '/portfolio-core.js': ('portfolio-core.js', 'text/javascript; charset=utf-8'),
    '/portfolio-ui.js': ('portfolio-ui.js', 'text/javascript; charset=utf-8'),
    '/portfolio.css': ('portfolio.css', 'text/css; charset=utf-8'),
}


def render_index():
    """Compose the teacher page without changing or copying student application code."""
    html = (STUDENT_STATIC / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<title>校园机器人挑战场</title>', '<title>地图作品集 · 教师参考实现</title>')
    html = html.replace('</head>', '<link rel="stylesheet" href="/portfolio.css">'
                        '<script src="/portfolio-core.js" defer></script>'
                        '<script src="/portfolio-ui.js" defer></script></head>', 1)
    html = html.replace('<div class="workspace">',
                        (STATIC / 'portfolio.html').read_text(encoding='utf-8') + '\n<div class="workspace">', 1)
    return html.encode('utf-8')


class Handler(StudentHandler):
    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': '仅接受本机同源请求。'})
        if self.path == '/':
            return self.send(200, render_index(), 'text/html; charset=utf-8')
        if self.path in ASSETS:
            filename, mime = ASSETS[self.path]
            return self.send(200, (STATIC / filename).read_bytes(), mime)
        return super().do_GET()


def make_server(port=8766):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('端口必须是 0–65535 的整数。')
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'地图作品集 · 教师参考实现：http://127.0.0.1:{server.server_port}', flush=True)
    print('地图仅在当前浏览器保存；作品交换需手动导入/导出。不提供云同步。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
