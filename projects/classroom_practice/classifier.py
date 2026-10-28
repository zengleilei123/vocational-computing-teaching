"""Train a small character-bigram Multinomial Naive Bayes model, without an API.

All provided tickets are synthetic. Scores are not calibrated probabilities.
This is a transparent supervised-learning lab, not a production ticket router.
"""
from __future__ import annotations
from collections import Counter
import csv
import math
from pathlib import Path
import re
import unicodedata

LABELS=('network','hardware','software')
FIELDS={'id','group','split','text','label'}


def normalize(text):
    if not isinstance(text,str) or not text.strip() or len(text)>1000:
        raise ValueError('text must be a nonempty string of at most 1000 characters')
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text).casefold())


def features(text):
    value=normalize(text)
    return Counter(value[i:i+2] for i in range(len(value)-1))


def validate(rows):
    if not isinstance(rows,list) or not rows: raise ValueError('empty data')
    ids=set(); groups={}; texts={}
    for row in rows:
        if not isinstance(row,dict) or set(row)!=FIELDS:
            raise ValueError('invalid dataset fields')
        if any(not isinstance(v,str) or not v.strip() for v in row.values()):
            raise ValueError('all fields must be nonempty strings')
        if row['id'] in ids: raise ValueError('duplicate ticket id')
        ids.add(row['id'])
        if row['label'] not in LABELS or row['split'] not in ('train','dev','test'):
            raise ValueError('invalid label or split')
        group=row['group']; split=row['split']; value=normalize(row['text'])
        if group in groups and groups[group]!=split: raise ValueError('group leakage across splits')
        if value in texts and texts[value]!=split: raise ValueError('duplicate text across splits')
        groups[group]=split; texts[value]=split
    training=[r for r in rows if r['split']=='train']
    if {r['label'] for r in training}!=set(LABELS): raise ValueError('training must cover all labels')
    return training


def load_data(path):
    with Path(path).open(encoding='utf-8',newline='') as source:
        rows=list(csv.DictReader(source))
    validate(rows)
    return rows


class TicketModel:
    """alpha=1 smoothing; vocabulary, priors and likelihoods use training only."""
    def __init__(self,training):
        self.counts={label:Counter() for label in LABELS}
        self.class_counts=Counter()
        for row in training:
            self.counts[row['label']].update(features(row['text']))
            self.class_counts[row['label']]+=1
        self.vocabulary=set().union(*(set(c) for c in self.counts.values()))
        if not self.vocabulary: raise ValueError('training contains no bigram features')
        self.totals={label:sum(counts.values()) for label,counts in self.counts.items()}
        self.size=sum(self.class_counts.values())

    def predict(self,text,*,min_margin=1.0):
        if type(min_margin) not in (int,float) or not math.isfinite(min_margin) or min_margin<0:
            raise ValueError('min_margin must be finite and nonnegative')
        known={term:n for term,n in features(text).items() if term in self.vocabulary}
        if not known:
            return {'label':None,'route':'manual_review','reason':'no_known_features','margin':0.0}
        scores={}
        for label in LABELS:
            scores[label]=math.log(self.class_counts[label]/self.size)+sum(
                n*math.log((self.counts[label][term]+1)/(self.totals[label]+len(self.vocabulary)))
                for term,n in known.items())
        ranked=sorted(scores,key=lambda label:(-scores[label],label))
        margin=scores[ranked[0]]-scores[ranked[1]]
        accepted=margin>=min_margin
        return {'label':ranked[0] if accepted else None,
                'route':ranked[0] if accepted else 'manual_review',
                'reason':'classified' if accepted else 'small_margin','margin':round(margin,6)}


def train(rows):
    return TicketModel(validate(rows))


def rule_predict(text):
    text=normalize(text)
    words={'network':('网络','wifi','网线','上网'),
           'hardware':('键盘','鼠标','显示器','电源','屏幕'),
           'software':('软件','安装','程序','应用','闪退')}
    hits=[label for label,terms in words.items() if any(term in text for term in terms)]
    return hits[0] if len(hits)==1 else None


def metrics(expected,predicted):
    if not expected or len(expected)!=len(predicted): raise ValueError('empty or mismatched evaluation')
    if any(v not in LABELS for v in expected) or any(v is not None and v not in LABELS for v in predicted):
        raise ValueError('unknown evaluation label')
    matrix={label:{column:0 for column in (*LABELS,'manual_review')} for label in LABELS}
    for truth,prediction in zip(expected,predicted): matrix[truth][prediction or 'manual_review']+=1
    f1=[]
    for label in LABELS:
        tp=matrix[label][label]
        fp=sum(matrix[other][label] for other in LABELS if other!=label)
        fn=sum(matrix[label][other] for other in (*LABELS,'manual_review') if other!=label)
        f1.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0)
    return {'n':len(expected),'accuracy':sum(a==b for a,b in zip(expected,predicted))/len(expected),
            'macro_f1':sum(f1)/len(LABELS),'manual_review_rate':predicted.count(None)/len(predicted),
            'confusion':matrix}


def run_experiment(rows):
    model=train(rows)
    result={'algorithm':'character-bigram multinomial naive Bayes',
            'counts':dict(Counter(r['split'] for r in rows)),
            'vocabulary_size':len(model.vocabulary),'synthetic_data':True,
            'settings':{'alpha':1,'min_margin':1.0,'threshold_tuned':False}}
    for split in ('dev','test'):
        subset=[r for r in rows if r['split']==split]
        if not subset: raise ValueError(f'missing {split} set')
        predicted=[model.predict(r['text'])['label'] for r in subset]
        report=metrics([r['label'] for r in subset],predicted)
        report['failures']=[{'id':r['id'],'text':r['text'],'expected':r['label'],'predicted':p}
                            for r,p in zip(subset,predicted) if r['label']!=p]
        result[split]=report
        if split=='test': result['rules_test']=metrics([r['label'] for r in subset],[rule_predict(r['text']) for r in subset])
    return result
