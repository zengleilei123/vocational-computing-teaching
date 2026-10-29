"""Loopback-only HTTP teaching adapter, not a production web server or RBAC."""
from __future__ import annotations
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from core import Store
from agents import offline_run


def handle(store, method, path, body, authorized):
    if method == 'GET' and path == '/health':
        return 200, {'status': 'ok', 'mode': 'local-teaching-demo'}
    if not authorized:
        return 401, {'error': 'unauthorized'}
    if type(body) is not dict:
        return 400, {'error': 'JSON object required'}
    try:
        if method == 'GET' and path == '/api/progress':
            return 200, store.progress('demo')
        if method == 'POST' and path == '/api/run':
            if set(body) - {'goal', 'query'}:
                raise ValueError('unexpected fields')
            return 200, offline_run(store, 'demo', body.get('goal', 'agents'), body.get('query', '工具调用'))
        if method == 'POST' and path == '/api/approve':
            if set(body) != {'id', 'confirmed'}:
                raise ValueError('id and confirmed required')
            return 200, store.approve(body['id'], 'demo', confirmed=body['confirmed'])
        return 404, {'error': 'not found'}
    except ValueError as exc:
        return 400, {'error': str(exc)}


def server(db_path, token, port=8000):
    if not isinstance(token, str) or len(token) < 16 or not token.isascii():
        raise ValueError('COURSEPILOT_TOKEN must be at least 16 ASCII characters')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            self.connection.settimeout(5)
            body = {}
            try:
                if self.command == 'POST':
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise ValueError('invalid body length')
                    body = json.loads(self.rfile.read(length).decode('utf-8'))
                supplied = self.headers.get('Authorization', '')
                authorized = hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode())
                store = Store(db_path)
                try:
                    store.seed()
                    code, result = handle(store, self.command, self.path, body, authorized)
                finally:
                    store.close()
            except (ValueError, UnicodeError, TimeoutError):
                code, result = 400, {'error': 'invalid request'}
            payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass  # Do not print credentials, request bodies or learner input.
    return HTTPServer(('127.0.0.1', port), Handler)
