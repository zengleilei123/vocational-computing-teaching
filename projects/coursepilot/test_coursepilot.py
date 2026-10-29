"""Offline contract tests: no credentials, model calls, or real learner data."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import Store, learning_path
from agents import dispatch, offline_run, run_llm
from api import handle


class BaseStoreCase(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.store.seed()
        self.addCleanup(self.store.close)


class StoreTests(BaseStoreCase):
    def test_seed_is_idempotent(self):
        self.store.seed()
        self.assertEqual(len(self.store.topics()), 8)
        self.assertEqual(self.store.progress('demo')['python']['attempts'], 1)

    def test_sql_aggregate(self):
        self.store.import_csv('student,topic,score\ndemo,python,70\n')
        self.assertEqual(self.store.progress('demo')['python']['average'], 80.0)

    def test_csv_rejects_whole_invalid_batch(self):
        before = self.store.progress('demo')
        with self.assertRaises(ValueError):
            self.store.import_csv('student,topic,score\ndemo,python,80\ndemo,sql,nan\n')
        self.assertEqual(before, self.store.progress('demo'))

    def test_csv_rejects_bad_schema_and_unknown_topic(self):
        for text in ('student,score\ndemo,1\n', 'student,topic,score\ndemo,missing,90\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.store.import_csv(text)

    def test_student_identifier_is_not_sql(self):
        with self.assertRaises(ValueError):
            self.store.progress("x'; DROP TABLE attempts;--")
        self.assertEqual(len(self.store.topics()), 8)

    def test_retrieval_evidence_and_no_match(self):
        hits = self.store.search('工具调用参数校验')
        self.assertTrue(hits)
        self.assertTrue(all(x['source'] and x['id'] for x in hits))
        self.assertEqual(self.store.search('火星天气'), [])

    def test_draft_requires_separate_confirmation(self):
        draft = self.store.draft('demo', 'agents')
        self.assertEqual(draft['status'], 'pending')
        self.assertNotIn('python', draft['steps'])
        self.assertLess(draft['steps'].index('sql'), draft['steps'].index('agents'))
        with self.assertRaises(ValueError):
            self.store.approve(draft['id'], 'demo', confirmed=False)
        self.assertEqual(self.store.approve(draft['id'], 'demo', confirmed=True)['status'], 'approved')
        self.assertEqual(self.store.approve(draft['id'], 'demo', confirmed=True)['status'], 'approved')
        self.assertEqual(sum(x['event'] == 'plan_approved' for x in self.store.events()), 1)

    def test_other_student_cannot_approve(self):
        draft = self.store.draft('demo', 'agents')
        with self.assertRaises(ValueError):
            self.store.approve(draft['id'], 'someone-else', confirmed=True)

    def test_false_like_confirmation_is_rejected(self):
        draft = self.store.draft('demo', 'agents')
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.store.approve(draft['id'], 'demo', confirmed=value)

    def test_disk_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'demo.db')
            one = Store(path)
            one.seed()
            plan = one.draft('demo', 'agents')
            one.close()
            two = Store(path)
            try:
                self.assertEqual(two.plan(plan['id'], 'demo')['status'], 'pending')
            finally:
                two.close()


class AlgorithmTests(unittest.TestCase):
    def test_dag_orders_prerequisites_and_deduplicates(self):
        graph = {'a': [], 'b': ['a'], 'c': ['a'], 'd': ['b', 'c']}
        self.assertEqual(learning_path(graph, 'd', {'a'}), ['b', 'c', 'd'])

    def test_cycle_unknown_goal_and_missing_dependency(self):
        for graph, goal in (({'a': ['b'], 'b': ['a']}, 'a'), ({'a': []}, 'x'), ({'a': ['x']}, 'a')):
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                learning_path(graph, goal, set())

    def test_mastered_goal_still_checks_prerequisites(self):
        self.assertEqual(learning_path({'a': [], 'b': ['a']}, 'b', {'b'}), ['a'])


def call(name, args, ident='c1'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': ident, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


class AgentTests(BaseStoreCase):
    def test_offline_business_flow(self):
        result = offline_run(self.store, 'demo', 'agents', '工具调用参数校验')
        self.assertEqual(result['mode'], 'deterministic')
        self.assertEqual(result['plan']['status'], 'pending')
        self.assertTrue(result['evidence'])
        self.assertEqual(result['plan']['steps'][-1], 'agents')

    def test_tool_allowlist_and_exact_fields(self):
        for name, args in (('approve_plan', {}), ('progress', {'student': 'someone-else'}), ('search', {'query': ''})):
            with self.subTest(name=name), self.assertRaises(ValueError):
                dispatch(self.store, 'demo', name, args)

    def test_model_tool_result_roundtrip(self):
        replies = iter([call('progress', {}), {'role': 'assistant', 'content': '已读取学情。'}])
        captured = []
        def client(messages, tools):
            captured.append(copy.deepcopy(messages))
            return next(replies)
        result = run_llm(client, self.store, 'demo', '我的学习情况？')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(captured[1][-1]['role'], 'tool')
        self.assertEqual(captured[1][-1]['tool_call_id'], 'c1')
        self.assertEqual(result['tool_calls'], 1)

    def test_untrusted_tool_is_error_not_execution(self):
        replies = iter([call('approve_plan', {}), {'role': 'assistant', 'content': '不能自动批准。'}])
        captured = []
        def client(messages, tools):
            captured.append(copy.deepcopy(messages))
            return next(replies)
        result = run_llm(client, self.store, 'demo', '自动批准')
        self.assertEqual(result['tool_errors'], 1)
        self.assertFalse(json.loads(captured[1][-1]['content'])['ok'])

    def test_final_turn_does_not_execute_unreturnable_tool(self):
        with patch('agents.dispatch') as execute:
            result = run_llm(lambda m, t: call('draft', {'goal': 'agents'}), self.store, 'demo', '计划', max_turns=1)
            self.assertEqual(result['status'], 'budget_exceeded')
            execute.assert_not_called()

    def test_tool_budget_and_bad_protocol(self):
        msg = call('progress', {})
        msg['tool_calls'].append(call('progress', {}, 'c2')['tool_calls'][0])
        with patch('agents.dispatch') as execute:
            result = run_llm(lambda m, t: msg, self.store, 'demo', '学情', max_calls=1)
            self.assertEqual(result['status'], 'budget_exceeded')
            execute.assert_not_called()
        bad = call('progress', {})
        bad['tool_calls'][0]['id'] = ''
        with self.assertRaises(ValueError):
            run_llm(lambda m, t: bad, self.store, 'demo', '学情')


class APITests(BaseStoreCase):
    def test_health_and_authorization(self):
        self.assertEqual(handle(self.store, 'GET', '/health', {}, False)[0], 200)
        self.assertEqual(handle(self.store, 'POST', '/api/run', {}, False)[0], 401)

    def test_api_run_approve_and_bad_input(self):
        code, body = handle(self.store, 'POST', '/api/run', {'goal': 'agents', 'query': '工具调用'}, True)
        self.assertEqual(code, 200)
        ident = body['plan']['id']
        self.assertEqual(handle(self.store, 'POST', '/api/approve', {'id': ident, 'confirmed': False}, True)[0], 400)
        self.assertEqual(handle(self.store, 'POST', '/api/approve', {'id': ident, 'confirmed': True}, True)[1]['status'], 'approved')
        self.assertEqual(handle(self.store, 'POST', '/api/run', {'student': 'other'}, True)[0], 400)
        self.assertEqual(handle(self.store, 'POST', '/missing', {}, True)[0], 404)



class IntegrationTests(unittest.TestCase):
    def test_cli_demo_and_evaluation(self):
        import subprocess
        import sys
        app = Path(__file__).with_name('app.py')
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(app), '--db', str(Path(tmp) / 'x.db'), 'demo'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['plan']['status'], 'pending')
            result = subprocess.run([sys.executable, str(app), 'evaluate'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertGreaterEqual(report['total'], 6)
            self.assertEqual(report['passed'], report['total'])
            self.assertIn('not model quality', report['scope'])

    def test_real_http_transport(self):
        import threading
        import urllib.request
        import urllib.error
        from api import server
        with tempfile.TemporaryDirectory() as tmp:
            token = 'local-test-token-not-a-secret'
            httpd = server(str(Path(tmp) / 'x.db'), token, port=0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{httpd.server_port}'
            try:
                with urllib.request.urlopen(base + '/health', timeout=5) as response:
                    self.assertEqual(response.status, 200)
                request = urllib.request.Request(base + '/api/run', data=b'{}', method='POST')
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request, timeout=5)
                self.assertEqual(caught.exception.code, 401)
                request.add_header('Authorization', 'Bearer ' + token)
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(json.load(response)['plan']['status'], 'pending')
                bad = urllib.request.Request(base + '/api/run', data=b'not-json', method='POST')
                bad.add_header('Authorization', 'Bearer ' + token)
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(bad, timeout=5)
                self.assertEqual(caught.exception.code, 400)
            finally:
                httpd.shutdown()
                thread.join(timeout=5)
                httpd.server_close()


if __name__ == '__main__':
    unittest.main()
