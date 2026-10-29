"""Behavior and boundary tests; no GPU, external network, or API credentials."""
import json
import threading
import unittest
import urllib.error
import urllib.request

from projects.robot_playground.engine import parse_grid, solve, replay, PRESETS
from projects.robot_playground.glyphs import classify, evaluate, DEMO_TRAIN


class MapTests(unittest.TestCase):
    def setUp(self):
        self.grid = PRESETS[0]['grid']

    def test_shortest_steps_vs_lowest_cost(self):
        bfs = solve(self.grid, 'bfs')
        dijkstra = solve(self.grid, 'dijkstra')
        self.assertTrue(bfs['success'] and dijkstra['success'])
        self.assertEqual((bfs['steps'], bfs['energy']), (6, 46))
        self.assertEqual((dijkstra['steps'], dijkstra['energy']), (10, 10))
        self.assertEqual(replay(self.grid, dijkstra['actions'])['energy'], 10)

    def test_unreachable_is_not_success(self):
        result = solve(['S#G', '###', '...'], 'bfs')
        self.assertFalse(result['success'])
        self.assertIsNone(result['energy'])
        self.assertEqual(result['actions'], [])

    def test_rejects_ragged_grid(self):
        with self.assertRaises(ValueError):
            parse_grid(['S.G', '..', '...'])

    def test_rejects_invalid_symbols(self):
        with self.assertRaises(ValueError):
            parse_grid(['S0G', '...', '...'])

    def test_rejects_duplicate_start(self):
        with self.assertRaises(ValueError):
            parse_grid(['SSG', '...', '...'])

    def test_rejects_missing_goal(self):
        with self.assertRaises(ValueError):
            parse_grid(['S..', '...', '...'])

    def test_bounds_dimensions(self):
        with self.assertRaises(ValueError):
            parse_grid(['S' + '.' * 20 + 'G'] * 3)

    def test_unknown_algorithm(self):
        with self.assertRaises(ValueError):
            solve(self.grid, '__import__')

    def test_collision_is_not_applied(self):
        result = replay(self.grid, ['up'])
        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'blocked')
        self.assertEqual(result['steps'], 0)
        self.assertEqual(result['energy'], 0)

    def test_empty_manual_run(self):
        result = replay(self.grid, [])
        self.assertEqual(result['reason'], 'incomplete')
        self.assertEqual(result['path'], [[1, 1]])

    def test_extra_actions_after_goal_rejected(self):
        result = replay(['S.G', '...', '...'], ['right', 'right', 'left'])
        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'after_goal')

    def test_invalid_actions(self):
        for actions in (['jump'], 'right', ['right'] * 401):
            with self.subTest(actions=str(actions)[:20]), self.assertRaises(ValueError):
                replay(self.grid, actions)

    def test_all_solutions_replay_consistently(self):
        for preset in PRESETS:
            for algorithm in ('bfs', 'dijkstra'):
                result = solve(preset['grid'], algorithm)
                if result['success']:
                    checked = replay(preset['grid'], result['actions'])
                    self.assertTrue(checked['success'])
                    self.assertEqual(checked['energy'], result['energy'])

    def test_start_tile_does_not_cost_energy(self):
        result = replay(['SG.', '...', '...'], ['right'])
        self.assertEqual((result['steps'], result['energy']), (1, 1))


class GlyphTests(unittest.TestCase):
    def test_each_demo_shape_recognized(self):
        for sample in DEMO_TRAIN:
            self.assertEqual(classify(DEMO_TRAIN, sample['pixels'])['label'], sample['label'])

    def test_blank_rejected_not_guessed(self):
        self.assertIsNone(classify(DEMO_TRAIN, [0] * 25)['label'])

    def test_non_binary_pixels_rejected(self):
        with self.assertRaises(ValueError):
            classify(DEMO_TRAIN, [2] * 25)

    def test_incomplete_training_classes_rejected(self):
        with self.assertRaises(ValueError):
            classify(DEMO_TRAIN[:1], DEMO_TRAIN[0]['pixels'])

    def test_far_shape_rejected(self):
        result = classify(DEMO_TRAIN, [1] * 25)
        self.assertIsNone(result['label'])
        self.assertEqual(result['reason'], 'too_far')

    def test_test_set_relabeling_does_not_change_prediction(self):
        query = list(DEMO_TRAIN[0]['pixels'])
        query[0] = 1 - query[0]
        a = evaluate(DEMO_TRAIN, [{'label': 'up', 'pixels': query}])
        b = evaluate(DEMO_TRAIN, [{'label': 'down', 'pixels': query}])
        self.assertEqual(a['results'][0]['label'], b['results'][0]['label'])
        self.assertNotEqual(a['accuracy'], b['accuracy'])

    def test_wrong_pixel_count(self):
        with self.assertRaises(ValueError):
            classify(DEMO_TRAIN, [0] * 24)

    def test_invalid_k(self):
        for k in (True, 0, 2, 99):
            with self.subTest(k=k), self.assertRaises(ValueError):
                classify(DEMO_TRAIN, DEMO_TRAIN[0]['pixels'], k=k)

    def test_conflicting_training_duplicate_rejected(self):
        collision = {'label': 'down', 'pixels': DEMO_TRAIN[0]['pixels']}
        with self.assertRaises(ValueError):
            classify(DEMO_TRAIN + [collision], DEMO_TRAIN[0]['pixels'])

    def test_identical_training_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            classify(DEMO_TRAIN + [DEMO_TRAIN[0]], DEMO_TRAIN[0]['pixels'])

    def test_holdout_leakage_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(DEMO_TRAIN, [DEMO_TRAIN[0]])

    def test_actual_holdout_metrics(self):
        sample = dict(DEMO_TRAIN[0])
        sample['pixels'] = list(sample['pixels'])
        sample['pixels'][0] = 1 - sample['pixels'][0]
        report = evaluate(DEMO_TRAIN, [sample])
        self.assertEqual(report['n_test'], 1)
        self.assertEqual(report['accuracy'], 1.0)
        self.assertEqual(report['coverage'], 1.0)
        self.assertEqual(report['confusion']['up']['up'], 1)

    def test_empty_holdout_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(DEMO_TRAIN, [])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from projects.robot_playground.server import make_server
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, path, data=None, headers=None):
        headers = headers or {}
        body = None if data is None else json.dumps(data).encode()
        if body is not None:
            headers.setdefault('Content-Type', 'application/json')
        req = urllib.request.Request(self.base + path, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_index_served(self):
        status, body, headers = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('机器人挑战场'.encode(), body)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])

    def test_solve_endpoint(self):
        status, body, _ = self.request('/api/solve', {'grid': PRESETS[0]['grid'], 'algorithm': 'dijkstra'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['energy'], 10)

    def test_invalid_payload_400(self):
        status, _, _ = self.request('/api/solve', {'grid': ['nope']})
        self.assertEqual(status, 400)

    def test_cross_origin_403(self):
        status, _, _ = self.request('/api/solve', {}, {'Origin': 'https://untrusted.example'})
        self.assertEqual(status, 403)

    def test_bad_host_403(self):
        status, _, _ = self.request('/', headers={'Host': 'attacker.example'})
        self.assertEqual(status, 403)

    def test_path_allowlist(self):
        self.assertEqual(self.request('/../../README.md')[0], 404)

    def test_body_limit(self):
        self.assertEqual(self.request('/api/solve', {'x': 'a' * 66000})[0], 413)

    def test_method_media_and_unknown_endpoint(self):
        self.assertEqual(self.request('/api/nope', {})[0], 404)
        self.assertEqual(self.request('/api/solve', {}, {'Content-Type': 'text/plain'})[0], 415)

    def test_student_strategy_is_checked_by_same_evaluator(self):
        status, body, _ = self.request('/api/solve', {'grid': PRESETS[1]['grid'], 'algorithm': 'student'})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertFalse(result['success'])
        self.assertEqual(result['reason'], 'blocked')

    def test_classify_endpoint(self):
        status, body, _ = self.request('/api/classify', {'train': DEMO_TRAIN, 'pixels': DEMO_TRAIN[0]['pixels']})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['label'], 'up')


if __name__ == '__main__':
    unittest.main()
