"""Offline business acceptance tests; no API key, real student records or code execution."""
from __future__ import annotations
import csv
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = Path(__file__).resolve().parent

def module(case, name):
    case.assertTrue((HERE / f'{name}.py').exists(), f'missing implementation: {name}')
    return importlib.import_module(f'projects.classroom_practice.{name}')


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.mod = module(self, 'booking')
        self.book = self.mod.BookingStore()
        self.book.seed()
        self.addCleanup(self.book.close)

    def reserve(self, request='r1', student='demo', start='2026-11-02T09:00:00+08:00', end='2026-11-02T10:00:00+08:00'):
        return self.book.reserve(request, student, 'camera-01', start, end)

    def test_adjacent_slots_do_not_overlap(self):
        self.reserve()
        self.reserve('r2', start='2026-11-02T10:00:00+08:00', end='2026-11-02T11:00:00+08:00')
        self.assertEqual(len(self.book.list_bookings()), 2)

    def test_overlap_rejected_and_no_partial_write(self):
        self.reserve()
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.reserve('r2', 'other', start='2026-11-02T09:30:00+08:00')
        self.assertEqual(len(self.book.list_bookings()), 1)

    def test_equivalent_timezones_conflict(self):
        self.reserve()
        with self.assertRaisesRegex(ValueError, 'conflict'):
            self.reserve('r2', start='2026-11-02T01:00:00+00:00', end='2026-11-02T02:00:00+00:00')

    def test_same_request_is_idempotent(self):
        first = self.reserve()
        self.assertEqual(first, self.reserve())
        self.assertEqual(len(self.book.list_bookings()), 1)

    def test_reused_request_cannot_change_payload(self):
        self.reserve()
        with self.assertRaisesRegex(ValueError, 'request'):
            self.reserve('r1', 'other')

    def test_cancel_checks_owner_and_frees_slot(self):
        self.reserve()
        with self.assertRaises(ValueError):
            self.book.cancel('r1', 'other', confirmed=True)
        self.book.cancel('r1', 'demo', confirmed=True)
        self.reserve('r2', 'other')
        self.assertEqual(self.book.list_bookings()[0]['status'], 'cancelled')

    def test_cancel_requires_explicit_boolean(self):
        self.reserve()
        for value in (False, 'yes', 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.book.cancel('r1', 'demo', confirmed=value)

    def test_invalid_times_rejected(self):
        for start,end in [('2026-11-02T09:00:00','2026-11-02T10:00:00'),
                          ('2026-11-02T10:00:00+08:00','2026-11-02T09:00:00+08:00'),
                          ('2026-11-02T09:00:00+08:00','2026-11-03T09:00:00+08:00')]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                self.reserve(start=start,end=end)

    def test_unknown_equipment_rejected(self):
        with self.assertRaises(ValueError):
            self.book.reserve('r1','demo','missing','2026-11-02T09:00:00+08:00','2026-11-02T10:00:00+08:00')

    def test_two_connections_cannot_double_book(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'booking.db')
            db = self.mod.BookingStore(path); db.seed(); db.close()
            barrier = threading.Barrier(2)
            results=[]
            def worker(request):
                store = self.mod.BookingStore(path)
                try:
                    barrier.wait(timeout=5)
                    store.reserve(request,request,'camera-01','2026-11-02T09:00:00+08:00','2026-11-02T10:00:00+08:00')
                    results.append('ok')
                except ValueError:
                    results.append('conflict')
                finally:
                    store.close()
            threads=[threading.Thread(target=worker,args=(f'r{i}',)) for i in range(2)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=10)
            self.assertTrue(all(not t.is_alive() for t in threads))
            self.assertCountEqual(results,['ok','conflict'])
            db=self.mod.BookingStore(path)
            self.assertEqual(len(db.list_bookings()),1)
            db.close()


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.mod = module(self,'classifier')
        self.rows = [
            {'id':'a','group':'a','split':'train','text':'网络断线无法上网','label':'network'},
            {'id':'b','group':'b','split':'train','text':'键盘损坏按键失灵','label':'hardware'},
            {'id':'c','group':'c','split':'train','text':'软件安装失败闪退','label':'software'},
            {'id':'d','group':'d','split':'dev','text':'无法连接网络','label':'network'},
            {'id':'e','group':'e','split':'test','text':'罕见测试独有词','label':'hardware'},
        ]

    def test_model_learns_and_ignores_test_vocabulary(self):
        model=self.mod.train(self.rows)
        self.assertNotIn('罕见',model.vocabulary)
        self.assertEqual(model.predict('网络断线')['label'],'network')

    def test_holdout_labels_do_not_change_fit(self):
        baseline=self.mod.train(self.rows).predict('网络断线')
        changed=[dict(r) for r in self.rows]; changed[-1]['label']='software'
        self.assertEqual(baseline,self.mod.train(changed).predict('网络断线'))

    def test_all_unknown_tokens_require_review(self):
        result=self.mod.train(self.rows).predict('火星海底火山')
        self.assertEqual(result['route'],'manual_review')
        self.assertIsNone(result['label'])

    def test_group_leakage_rejected(self):
        self.rows[-1]['group']='a'
        with self.assertRaisesRegex(ValueError,'group'):
            self.mod.train(self.rows)

    def test_duplicate_text_across_splits_rejected(self):
        self.rows[-1]['text']=self.rows[0]['text']
        with self.assertRaisesRegex(ValueError,'text'):
            self.mod.train(self.rows)

    def test_invalid_and_missing_training_labels(self):
        self.rows[1]['label']='unknown'
        with self.assertRaises(ValueError): self.mod.train(self.rows)
        with self.assertRaises(ValueError): self.mod.train([])

    def test_metrics_use_fixed_class_order(self):
        report=self.mod.metrics(['network','hardware','software'],['network','network',None])
        self.assertAlmostEqual(report['accuracy'],1/3)
        self.assertAlmostEqual(report['macro_f1'],(2/3)/3)
        self.assertEqual(report['confusion']['software']['manual_review'],1)
        self.assertEqual(report['n'],3)

    def test_complete_dataset_and_report(self):
        rows=self.mod.load_data(HERE/'data'/'tickets.csv')
        report=self.mod.run_experiment(rows)
        self.assertEqual(report['counts'],{'train':36,'dev':9,'test':12})
        self.assertEqual(report['test']['n'],12)
        self.assertIn('failures',report['test'])
        self.assertEqual(report['algorithm'],'character-bigram multinomial naive Bayes')
        self.assertIn('rules_test',report)


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.mod=module(self,'assessment')
        from projects.coursepilot.core import Store
        self.store=Store(); self.store.seed(); self.addCleanup(self.store.close)
        self.csv='evidence_id,student,project,topic,score\nE1,learner_01,booking,sql,45\nE2,learner_01,booking,algorithms,80\n'

    def test_requires_human_confirmation(self):
        for value in (False,'yes',1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.mod.import_assessments(self.store,self.csv,confirmed=value)
        self.assertEqual(self.store.progress('learner_01'),{})

    def test_real_store_integration_and_plan_stays_pending(self):
        out=self.mod.import_assessments(self.store,self.csv,confirmed=True)
        self.assertEqual(out,{'imported':2,'skipped':0})
        self.assertEqual(self.store.progress('learner_01')['sql']['average'],45)
        plan=self.store.draft('learner_01','agents')
        self.assertIn('sql',plan['steps'])
        self.assertNotIn('algorithms',plan['steps'])
        self.assertEqual(plan['status'],'pending')

    def test_replay_does_not_duplicate_grades(self):
        self.mod.import_assessments(self.store,self.csv,confirmed=True)
        out=self.mod.import_assessments(self.store,self.csv,confirmed=True)
        self.assertEqual(out,{'imported':0,'skipped':2})
        self.assertEqual(self.store.progress('learner_01')['sql']['attempts'],1)

    def test_same_evidence_changed_score_rejected(self):
        self.mod.import_assessments(self.store,self.csv,confirmed=True)
        with self.assertRaises(ValueError):
            self.mod.import_assessments(self.store,self.csv.replace(',45',',99'),confirmed=True)
        self.assertEqual(self.store.progress('learner_01')['sql']['average'],45)

    def test_whole_batch_invalid_is_not_partially_written(self):
        bad=self.csv+'E3,learner_01,booking,sql,nan\n'
        with self.assertRaises(ValueError): self.mod.import_assessments(self.store,bad,confirmed=True)
        self.assertEqual(self.store.progress('learner_01'),{})

    def test_replay_conflict_rolls_back_earlier_new_rows(self):
        self.mod.import_assessments(self.store,self.csv,confirmed=True)
        new='evidence_id,student,project,topic,score\nE3,learner_01,booking,sql,75\nE1,learner_01,booking,sql,99\n'
        with self.assertRaises(ValueError): self.mod.import_assessments(self.store,new,confirmed=True)
        self.assertEqual(self.store.progress('learner_01')['sql']['attempts'],1)

    def test_unknown_project_topic_and_duplicate_evidence_rejected(self):
        for bad in (self.csv.replace('booking','unapproved'),self.csv.replace(',sql,',',missing,'),self.csv+self.csv.splitlines()[1]+'\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.mod.import_assessments(self.store,bad,confirmed=True)


class CommandTests(unittest.TestCase):
    def test_all_demo_commands(self):
        module(self,'app')
        root=HERE.parents[1]
        for command in ('booking','classify','feedback'):
            with self.subTest(command=command):
                result=subprocess.run([sys.executable,'-m','projects.classroom_practice.app',command],cwd=root,capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIsInstance(json.loads(result.stdout),dict)

if __name__=='__main__': unittest.main()
