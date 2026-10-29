"""Import instructor-reviewed synthetic assessments into the real CoursePilot Store.

No submission code is executed and no score is invented by a model. confirmed=True
is a local explicit-confirmation teaching gate, NOT teacher authentication.
"""
from __future__ import annotations
import csv
import io
import json
import math
from projects.coursepilot.core import Store, student_id, text

PROJECT_TOPICS={
    'booking':{'python','algorithms','sql','api','evaluation'},
    'tickets':{'python','algorithms','evaluation','agents'},
}
HEADER=['evidence_id','student','project','topic','score']


def import_assessments(store: Store, content: str, *, confirmed: bool):
    if confirmed is not True: raise ValueError('explicit boolean confirmation required')
    reader=csv.DictReader(io.StringIO(text(content,'assessments CSV',100_000)))
    if reader.fieldnames!=HEADER: raise ValueError('invalid assessment CSV header')
    rows=[]; evidence_ids=set(); topics=store.topics()
    for row in reader:
        if set(row)!=set(HEADER): raise ValueError('malformed assessment row')
        evidence=student_id(row['evidence_id']); who=student_id(row['student'])
        if evidence in evidence_ids: raise ValueError('duplicate evidence id within batch')
        evidence_ids.add(evidence)
        project=text(row['project'],'project',64); topic=text(row['topic'],'topic',64)
        if topic not in topics or topic not in PROJECT_TOPICS.get(project,set()):
            raise ValueError('unknown project/topic mapping')
        try: score=float(row['score'])
        except (ValueError,TypeError) as exc: raise ValueError('score must be numeric') from exc
        if not math.isfinite(score) or not 0<=score<=100: raise ValueError('score outside [0,100]')
        payload=json.dumps([who,project,topic,score],ensure_ascii=False,separators=(',',':'))
        rows.append((evidence,who,topic,score,payload))
    if not rows: raise ValueError('assessment batch is empty')
    if store.db.in_transaction: raise ValueError('finish existing transaction before assessment import')
    imported=skipped=0
    store.db.execute('BEGIN IMMEDIATE')
    try:
        for evidence,who,topic,score,payload in rows:
            key=f'practice-evidence:{evidence}'
            previous=store.db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
            if previous:
                if previous['value']!=payload: raise ValueError('evidence id reused with changed assessment')
                skipped+=1
                continue
            store.db.execute('INSERT INTO attempts(student,topic,score) VALUES(?,?,?)',(who,topic,score))
            store.db.execute('INSERT INTO metadata(key,value) VALUES(?,?)',(key,payload))
            imported+=1
        if imported:
            store.db.execute('INSERT INTO events(event,detail) VALUES(?,?)',
                             ('practice_assessments_imported',f'rows={imported}'))
        store.db.commit()
    except Exception:
        store.db.rollback()
        raise
    return {'imported':imported,'skipped':skipped}
