"""CLI: offline workflow, explicit confirmation, evaluation, local API, optional LLM."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from core import Store
from agents import dispatch, offline_run, run_llm, model_client_from_env
from api import server


def evaluate():
    """Small regression suite. Success here is not an estimate of model quality."""
    results = []
    def check(name, operation):
        store = Store(':memory:')
        store.seed()
        try:
            passed = bool(operation(store))
            results.append({'id': name, 'passed': passed})
        except Exception as exc:
            results.append({'id': name, 'passed': False, 'error': type(exc).__name__})
        finally:
            store.close()
    def denied(operation):
        try:
            operation()
        except ValueError:
            return True
        return False
    check('retrieval_hit', lambda s: s.search('工具调用参数校验')[0]['id'] == 'agents')
    check('retrieval_abstain', lambda s: s.search('火星天气') == [])
    check('prerequisite_plan', lambda s: s.draft('demo', 'agents')['steps'] == ['algorithms', 'sql', 'api', 'agents'])
    check('pending_not_autoapproved', lambda s: offline_run(s, 'demo', 'agents', '工具调用')['plan']['status'] == 'pending')
    check('approval_requires_true', lambda s: denied(lambda: s.approve(s.draft('demo', 'agents')['id'], 'demo', confirmed=False)))
    check('tool_cannot_approve', lambda s: denied(lambda: dispatch(s, 'demo', 'approve_plan', {})))
    check('invalid_csv_rejected', lambda s: denied(lambda: s.import_csv('student,topic,score\ndemo,sql,nan\n')))
    check('explicit_approval', lambda s: s.approve(s.draft('demo', 'agents')['id'], 'demo', confirmed=True)['status'] == 'approved')
    passed = sum(r['passed'] for r in results)
    return {'scope': 'synthetic deterministic regression; not model quality or teaching outcomes',
            'passed': passed, 'total': len(results), 'pass_rate': passed / len(results), 'cases': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description='CoursePilot: connected computing and AI teaching lab')
    parser.add_argument('--db', default='coursepilot.db', help='synthetic SQLite database path')
    sub = parser.add_subparsers(dest='command', required=True)
    demo = sub.add_parser('demo', help='run fixed workflow, no network and no automatic approval')
    demo.add_argument('--goal', default='agents')
    demo.add_argument('--query', default='工具调用参数校验')
    load = sub.add_parser('import-csv')
    load.add_argument('file')
    approve = sub.add_parser('approve')
    approve.add_argument('id')
    approve.add_argument('--confirm', action='store_true')
    sub.add_parser('progress')
    sub.add_parser('events')
    sub.add_parser('evaluate')
    web = sub.add_parser('serve', help='loopback-only HTTP teaching adapter')
    web.add_argument('--port', type=int, default=8000)
    chat = sub.add_parser('chat', help='explicit opt-in to a paid/external model API')
    chat.add_argument('prompt')
    args = parser.parse_args(argv)
    if args.command == 'evaluate':
        report = evaluate()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['passed'] == report['total'] else 1
    if args.command == 'serve':
        if args.db == ':memory:':
            raise ValueError('HTTP requests need a persistent database file')
        httpd = server(args.db, os.environ.get('COURSEPILOT_TOKEN', ''), args.port)
        print(f'Local teaching API: http://127.0.0.1:{httpd.server_port}; synthetic data only', flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
        return 0
    store = Store(args.db)
    try:
        store.seed()
        if args.command == 'demo':
            output = offline_run(store, 'demo', args.goal, args.query)
        elif args.command == 'approve':
            output = store.approve(args.id, 'demo', confirmed=args.confirm)
        elif args.command == 'progress':
            output = store.progress('demo')
        elif args.command == 'events':
            output = store.events()
        elif args.command == 'import-csv':
            output = store.import_csv(Path(args.file).read_text(encoding='utf-8'))
        else:
            output = run_llm(model_client_from_env(), store, 'demo', args.prompt)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    finally:
        store.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
