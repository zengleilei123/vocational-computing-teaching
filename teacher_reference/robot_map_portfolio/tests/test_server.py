"""Real HTTP checks for reference isolation and reuse of the student backend."""
import http.client
import json
import threading
import unittest

from projects.robot_playground.server import make_server as make_student_server, STATIC
from teacher_reference.robot_map_portfolio.server import make_server


class ReferenceServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = [make_server(0), make_student_server(0)]
        cls.threads = []
        for server in cls.servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cls.threads.append(thread)

    @classmethod
    def tearDownClass(cls):
        for server, thread in zip(cls.servers, cls.threads):
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def request(self, path='/', method='GET', data=None, student=False, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.servers[int(student)].server_port, timeout=5)
        body = json.dumps(data) if data is not None else None
        try:
            connection.request(method, path, body, headers or ({'Content-Type': 'application/json'} if data is not None else {}))
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_reference_has_own_controls_and_starter_does_not(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertIn(b'id="portfolio-name"', body)
        self.assertIn(b'/portfolio-core.js', body)
        self.assertIn(b'/portfolio-ui.js', body)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        status, _, starter = self.request(student=True)
        self.assertEqual(status, 200)
        self.assertEqual(starter, (STATIC / 'index.html').read_bytes())
        self.assertNotIn(b'portfolio', starter)

    def test_starter_assets_reused_without_rewriting(self):
        for name in ['app.js', 'style.css']:
            with self.subTest(name=name):
                status, _, body = self.request('/' + name)
                self.assertEqual(status, 200)
                self.assertEqual(body, (STATIC / name).read_bytes())

    def test_extension_assets_are_only_served_by_reference(self):
        for name in ['portfolio-core.js', 'portfolio-ui.js', 'portfolio.css']:
            with self.subTest(name=name):
                status, _, body = self.request('/' + name)
                self.assertEqual(status, 200)
                self.assertTrue(body)
                self.assertEqual(self.request('/' + name, student=True)[0], 404)

    def test_existing_solver_contract(self):
        status, _, body = self.request('/api/solve', method='POST', data={'grid': ['S..', '.#.', '..G'], 'algorithm': 'bfs'})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertTrue(result['success'])
        self.assertEqual(result['steps'], 4)
        self.assertEqual(result['energy'], 4)

    def test_reference_keeps_loopback_and_path_guards(self):
        self.assertEqual(self.request(headers={'Host': 'example.com'})[0], 403)
        self.assertEqual(self.request('/portfolio-core.js', headers={'Origin': 'https://example.com'})[0], 403)
        for path in ['/../README.md', '/exercises/TEACHER.md', '/portfolio.html', '/api/save']:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_invalid_port(self):
        for port in [-1, 65536, True, '8766']:
            with self.subTest(port=port), self.assertRaises(ValueError):
                make_server(port)


if __name__ == '__main__':
    unittest.main()
