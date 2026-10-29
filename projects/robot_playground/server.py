"""Loopback-only classroom server; not suitable for public deployment."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import PRESETS, replay, solve
from .glyphs import DEMO_TRAIN, classify, evaluate
from .student_strategy import plan

STATIC = Path(__file__).parent / 'static'
FILES = {'/': ('index.html', 'text/html; charset=utf-8'),
         '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
         '/style.css': ('style.css', 'text/css; charset=utf-8')}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Keep request bodies, student samples, and environment out of logs.

    def allowed(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        origin = self.headers.get('Origin')
        return self.headers.get('Host') in hosts and (origin is None or origin in {'http://' + h for h in hosts})

    def send(self, status, body, mime='application/json; charset=utf-8'):
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': '仅接受本机同源请求。'})
        if self.path == '/api/presets':
            return self.send(200, {'maps': PRESETS, 'train': DEMO_TRAIN})
        if self.path not in FILES:
            return self.send(404, {'error': '不存在的路径。'})
        filename, mime = FILES[self.path]
        return self.send(200, (STATIC / filename).read_bytes(), mime)

    def do_POST(self):
        if not self.allowed():
            return self.send(403, {'error': '拒绝跨来源或非本机请求。'})
        if self.path not in ('/api/solve', '/api/replay', '/api/classify', '/api/evaluate'):
            return self.send(404, {'error': '不存在的接口。'})
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.send(415, {'error': '需要 application/json。'})
        if self.headers.get('Transfer-Encoding'):
            return self.send(400, {'error': '不接受分块请求。'})
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return self.send(400, {'error': '无效的 Content-Length。'})
        if size > 65536:
            return self.send(413, {'error': '请求不能超过 64 KiB。'})
        if size < 0:
            return self.send(411, {'error': '需要 Content-Length。'})
        try:
            self.connection.settimeout(3)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('请求必须是 JSON 对象。')
            if self.path == '/api/solve':
                if data.get('algorithm') == 'student':
                    actions = plan(data.get('grid'))
                    result = {**replay(data.get('grid'), actions), 'actions': actions, 'expanded': [], 'algorithm': 'student'}
                else:
                    result = solve(data.get('grid'), data.get('algorithm', 'bfs'))
            elif self.path == '/api/replay':
                result = replay(data.get('grid'), data.get('actions'))
            elif self.path == '/api/classify':
                result = classify(data.get('train'), data.get('pixels'), data.get('k', 1))
            else:
                result = evaluate(data.get('train'), data.get('test'), data.get('k', 1))
        except (ValueError, TypeError, UnicodeError, TimeoutError, RecursionError) as exc:
            return self.send(400, {'error': str(exc)})
        return self.send(200, result)


def make_server(port=8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('端口必须是 0–65535 的整数。')
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'校园机器人挑战场：http://127.0.0.1:{server.server_port}', flush=True)
    print('仅供本机教学；Ctrl+C 退出。无云端服务、账号、摄像头或持久化采集。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
