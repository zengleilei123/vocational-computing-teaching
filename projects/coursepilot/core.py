"""Shared domain services: validated data, SQL, DAG planning, evidence and approval.

All seed records are synthetic. Keyword retrieval is deliberately transparent;
it is NOT semantic retrieval, a trained recommender, or an autonomous agent.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
import uuid
from graphlib import TopologicalSorter, CycleError

# id -> (title, prerequisites). Directed edges point from prerequisite to topic.
TOPICS = {
    'python': ('Python 程序设计', []),
    'algorithms': ('数据结构与算法', ['python']),
    'sql': ('SQL 与数据库', ['python']),
    'api': ('HTTP 与应用接口', ['python']),
    'agents': ('智能体与工具调用', ['algorithms', 'sql', 'api']),
    'rag': ('检索与证据问答', ['agents']),
    'evaluation': ('测试与评测', ['rag']),
    'deployment': ('部署与运维', ['evaluation']),
}
NOTES = (
    ('python', 'Python 数据处理', '先校验 CSV 字段、类型与数值范围，再批量入库；非法批次不得部分写入。', ['python', 'csv', '数据处理']),
    ('sql', '数据库与学情统计', '用参数化 SQL 聚合各知识点的练习次数和平均分；平均分只是演示代理指标，不等于真实掌握度。', ['sql', '数据库', '平均分', '学情']),
    ('algorithms', '先修课程图', '用有向无环图表达先修关系，拓扑排序后排除已经达标的知识点；存在环时应报错。', ['算法', '先修', '拓扑', '学习顺序']),
    ('agents', '工具调用安全', '模型只提出工具调用请求；应用校验名称和参数后执行。学习计划先保存为 pending，显式确认后才能变为 approved。', ['工具调用', '参数校验', '智能体', '计划', '审批']),
    ('rag', '检索与来源', '检索返回资料正文、来源及匹配分数。资料未命中时说明缺少依据，不编造引用。', ['rag', '检索', '引用', '来源']),
    ('evaluation', '测试与评测', '代码回归、离线模拟模型、真实模型评测、实际教学效果是不同证据层次，不可互相替代。', ['评测', '测试', '回归', '失败']),
)


def text(value, name='text', limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name} must be a non-empty string of at most {limit} characters')
    return value.strip()


def student_id(value):
    value = text(value, 'student', 64)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('student must contain only letters, digits, _ or -')
    return value


def learning_path(graph: dict[str, list[str]], goal: str, mastered: set[str]) -> list[str]:
    """Topologically sort the goal's prerequisite closure; O(V + E).

The prerequisite graph is an instructional design choice, not a universal course
standard. Mastering a goal does not silently mark its prerequisites as mastered.
"""
    needed = {}
    queue = [goal]
    while queue:
        node = queue.pop()
        if node not in graph:
            raise ValueError(f'unknown topic: {node}')
        if node not in needed:
            needed[node] = graph[node]
            queue.extend(reversed(graph[node]))
    try:
        ordered = list(TopologicalSorter(needed).static_order())
    except CycleError as exc:
        raise ValueError('prerequisite graph contains a cycle') from exc
    return [node for node in ordered if node not in mastered]


class Store:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS topics(id TEXT PRIMARY KEY, title TEXT NOT NULL, prerequisites TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, student TEXT NOT NULL,
                topic TEXT REFERENCES topics(id), score REAL CHECK(score >= 0 AND score <= 100));
            CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, title TEXT, body TEXT, keywords TEXT, source TEXT);
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, student TEXT NOT NULL, goal TEXT REFERENCES topics(id),
                steps TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved')));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event TEXT, detail TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
        ''')

    def close(self):
        self.db.close()

    def seed(self):
        """Idempotently create original teaching notes and synthetic demo records."""
        with self.db:
            for key, (title, prerequisites) in TOPICS.items():
                self.db.execute('INSERT OR IGNORE INTO topics VALUES(?,?,?)', (key, title, json.dumps(prerequisites)))
            for key, title, body, keywords in NOTES:
                self.db.execute('INSERT OR IGNORE INTO notes VALUES(?,?,?,?,?)',
                    (key, title, body, json.dumps(keywords), 'projects/coursepilot/core.py'))
            if not self.db.execute("SELECT 1 FROM metadata WHERE key='seed-v1'").fetchone():
                self.db.executemany('INSERT INTO attempts(student,topic,score) VALUES(?,?,?)',
                    [('demo', 'python', 90.0), ('demo', 'sql', 40.0), ('demo', 'algorithms', 50.0)])
                self.db.execute("INSERT INTO metadata VALUES('seed-v1','synthetic')")

    def topics(self):
        return {row['id']: {'title': row['title'], 'prerequisites': json.loads(row['prerequisites'])}
                for row in self.db.execute('SELECT * FROM topics ORDER BY rowid')}

    def import_csv(self, content: str):
        content = text(content, 'csv', 100_000)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames != ['student', 'topic', 'score']:
            raise ValueError('CSV header must be student,topic,score')
        rows = []
        topics = self.topics()
        for row in reader:
            if set(row) != {'student', 'topic', 'score'}:
                raise ValueError('malformed CSV row')
            who = student_id(row['student'])
            topic = text(row['topic'], 'topic', 64)
            try:
                score = float(row['score'])
            except (ValueError, TypeError) as exc:
                raise ValueError('score must be numeric') from exc
            if topic not in topics or not math.isfinite(score) or not 0 <= score <= 100:
                raise ValueError('unknown topic or score outside [0, 100]')
            rows.append((who, topic, score))
        if not rows:
            raise ValueError('CSV must contain at least one record')
        with self.db:
            self.db.executemany('INSERT INTO attempts(student,topic,score) VALUES(?,?,?)', rows)
            self._event('csv_imported', f'rows={len(rows)}')
        return {'imported': len(rows)}

    def progress(self, student):
        who = student_id(student)
        rows = self.db.execute('''SELECT topic, COUNT(*) AS attempts, AVG(score) AS average
                                  FROM attempts WHERE student=? GROUP BY topic''', (who,))
        return {r['topic']: {'attempts': r['attempts'], 'average': round(r['average'], 2)} for r in rows}

    def search(self, query):
        query = text(query, 'query').casefold()
        hits = []
        for row in self.db.execute('SELECT * FROM notes'):
            score = sum(keyword.casefold() in query for keyword in json.loads(row['keywords']))
            if score:
                hits.append({'id': row['id'], 'title': row['title'], 'excerpt': row['body'],
                             'source': row['source'], 'score': score})
        return sorted(hits, key=lambda r: (-r['score'], r['id']))[:3]

    def draft(self, student, goal):
        who = student_id(student)
        goal = text(goal, 'goal', 64)
        graph = {k: v['prerequisites'] for k, v in self.topics().items()}
        mastered = {k for k, v in self.progress(who).items() if v['average'] >= 70}
        steps = learning_path(graph, goal, mastered)
        ident = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO plans VALUES(?,?,?,?,?)', (ident, who, goal, json.dumps(steps), 'pending'))
            self._event('plan_drafted', ident)
        return self.plan(ident, who)

    def plan(self, ident, student):
        row = self.db.execute('SELECT * FROM plans WHERE id=? AND student=?',
                              (text(ident, 'id', 64), student_id(student))).fetchone()
        if row is None:
            raise ValueError('plan not found for this student')
        return {**dict(row), 'steps': json.loads(row['steps'])}

    def approve(self, ident, student, *, confirmed):
        if confirmed is not True:
            raise ValueError('explicit boolean confirmation is required')
        plan = self.plan(ident, student)
        with self.db:
            cursor = self.db.execute("UPDATE plans SET status='approved' WHERE id=? AND student=? AND status='pending'",
                                     (plan['id'], plan['student']))
            if cursor.rowcount:
                self._event('plan_approved', plan['id'])
        return self.plan(ident, student)

    def _event(self, event, detail):
        self.db.execute('INSERT INTO events(event,detail) VALUES(?,?)', (event, detail))

    def log_tool(self, name, ok):
        # No prompts, credentials or student answers in this minimal trace.
        with self.db:
            self._event('tool_ok' if ok else 'tool_error', name[:80])

    def events(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY id')]
