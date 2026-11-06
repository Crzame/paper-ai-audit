"""Measured public labelled pilot; not a clean unseen-model academic test."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SKILL=ROOT.parent
sys.path.insert(0,str(SKILL/'scripts'))
from audit_core import fit_profile,metrics
from detectors import DetectorSet

samples=[json.loads(line) for line in (ROOT/'hc3_pilot.jsonl').read_text(encoding='utf-8').splitlines()]
detector=DetectorSet(SKILL/'assets/models.local.json')
assert all(detector.status[k]['status']=='READY' for k in ['v3_zh','bert_zh']),detector.status
rows=[];started=time.perf_counter()
out=ROOT/'pilot_predictions.jsonl'
with out.open('w',encoding='utf-8') as stream:
    for i,sample in enumerate(samples):
        paragraphs=[{'index':n,'text':text.strip()} for n,text in enumerate(sample['text'].split('\n\n')) if text.strip()]
        result=detector.analyze(paragraphs)
        means=result['summary']['raw_mean_scores']
        if set(means)!={'v3_zh','bert_zh'} or any(v!=1 for v in result['summary']['model_coverage'].values()):
            raise ValueError('Incomplete language/model coverage for '+sample['id'])
        row={k:sample[k] for k in ['id','group_id','split','label','training_overlap_unknown']}
        row.update(text_sha256=hashlib.sha256(sample['text'].encode()).hexdigest(),fingerprint=detector.fingerprint,
                   language='zh',domain='question-answering',unit='document',score=min(means.values()),
                   v3_score=means['v3_zh'],bert_score=means['bert_zh'])
        rows.append(row);stream.write(json.dumps(row)+'\n');stream.flush()
        if (i+1)%20==0:print('Pilot',i+1,'/',len(samples),flush=True)
profile=fit_profile(rows,.01,detector.fingerprint,'zh','question-answering','document')
(ROOT/'pilot_profile_RESEARCH_ONLY.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
test=[r for r in rows if r['split']=='test']
comparisons={}
for name,key in [('V3_0.5','v3_score'),('BERT_0.5','bert_score'),('min_pair_0.5','score')]:
    comparisons[name]=metrics([{**r,'score':r[key]} for r in test],.5)
comparisons['calibrated_min_pair']=profile['validation']
summary={'samples':len(rows),'source_groups':len({r['group_id'] for r in rows}),'fingerprint':detector.fingerprint,
         'elapsed_seconds':time.perf_counter()-started,'comparison':comparisons,'profile':profile,
         'limitations':['Nonrandom 6-domain HC3 QA sample','Training overlap unknown','Not academic target domain','No claim of improved paper detection accuracy or sub-1% FPR'],
         'source_metadata':json.loads((ROOT/'hc3_pilot_metadata.json').read_text(encoding='utf-8'))}
(ROOT/'pilot_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'samples':len(rows),'comparison':comparisons,'threshold':profile['threshold'],'validated_low_fpr':profile['validated_low_fpr']},ensure_ascii=True))
