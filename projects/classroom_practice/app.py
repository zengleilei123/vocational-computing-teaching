"""Run from repository root: python -m projects.classroom_practice.app booking"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .booking import BookingStore
from .classifier import load_data, run_experiment
from .assessment import import_assessments
from projects.coursepilot.core import Store

DATA=Path(__file__).resolve().parent/'data'


def booking_demo():
    store=BookingStore()
    try:
        store.seed()
        store.reserve('demo-r1','demo','camera-01','2026-11-02T09:00:00+08:00','2026-11-02T10:00:00+08:00')
        try:
            store.reserve('demo-r2','other','camera-01','2026-11-02T09:30:00+08:00','2026-11-02T10:30:00+08:00')
        except ValueError as exc:
            rejected=str(exc)
        else: raise RuntimeError('expected conflict was not rejected')
        store.cancel('demo-r1','demo',confirmed=True)
        store.reserve('demo-r2','other','camera-01','2026-11-02T09:30:00+08:00','2026-11-02T10:30:00+08:00')
        return {'synthetic_demo':True,'conflict_rejected':rejected,'bookings':store.list_bookings()}
    finally: store.close()


def feedback_demo():
    store=Store()
    try:
        store.seed()
        content=(DATA/'assessments.csv').read_text(encoding='utf-8')
        first=import_assessments(store,content,confirmed=True)
        replay=import_assessments(store,content,confirmed=True)
        plan=store.draft('learner_01','agents')
        return {'synthetic_demo':True,'import':first,'replay':replay,
                'progress':store.progress('learner_01'),'plan':plan,
                'evidence':store.search('SQL 学情 先修 计划'),
                'warning':'Demo scores are instructor-supplied examples, not inferred ability or real grades.'}
    finally: store.close()


def main():
    parser=argparse.ArgumentParser(description='Offline classroom projects: synthetic data, no credentials.')
    parser.add_argument('project',choices=['booking','classify','feedback'])
    args=parser.parse_args()
    if args.project=='booking': result=booking_demo()
    elif args.project=='classify': result=run_experiment(load_data(DATA/'tickets.csv'))
    else: result=feedback_demo()
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
