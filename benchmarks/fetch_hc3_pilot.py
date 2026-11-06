"""Bounded public CC-BY-SA-4.0 pilot; unknown training overlap, non-academic QA.
Collect 12 Chinese-only, nonduplicate question pairs per domain.
No user document or private text is transmitted.
"""
import hashlib,json,random,requests,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO='Hello-SimpleAI/HC3-Chinese'
REV='09a687b8dc164b89e7df95abf15df3b216bc31c2'
domains=['baike','finance','law','medicine','open_qa','psychology']
rows=[];seen=set();seen_texts=set()
def all_chinese_paragraphs(text):
    for paragraph in text.split('\n\n'):
        if not paragraph.strip():continue
        han=len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]',paragraph));latin=len(re.findall(r'[A-Za-z]',paragraph))
        if not han or han/(han+latin)<.2:return False
    return True
for domain in domains:
    pairs=[]
    url=f'https://huggingface.co/datasets/{REPO}/resolve/{REV}/{domain}.jsonl'
    with requests.get(url,stream=True,timeout=(20,60)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:continue
            obj=json.loads(line)
            human=[v for v in obj.get('human_answers',[]) if isinstance(v,str) and v.strip()]
            ai=[v for v in obj.get('chatgpt_answers',[]) if isinstance(v,str) and v.strip()]
            if not human or not ai:continue
            h,a=human[0].strip(),ai[0].strip()
            if not(120<=len(h)<=4000 and 120<=len(a)<=4000):continue
            if not all_chinese_paragraphs(h) or not all_chinese_paragraphs(a):continue
            group=hashlib.sha256(obj['question'].encode()).hexdigest()
            if group in seen:continue
            text_hashes={hashlib.sha256(t.encode()).hexdigest() for t in [h,a]}
            if len(text_hashes)!=2 or text_hashes&seen_texts:continue
            seen_texts.update(text_hashes)
            seen.add(group);pairs.append((group,h,a))
            if len(pairs)==12:break
    assert len(pairs)==12,(domain,len(pairs))
    random.Random('paper-ai-audit-pilot-20261106-'+domain).shuffle(pairs)
    for i,(group,h,a) in enumerate(pairs):
        split='calibration' if i<6 else 'test'
        for label,text in [(0,h),(1,a)]:
            rows.append({'id':group+'-'+str(label),'group_id':group,'domain':domain,'split':split,
                         'language':'zh','label':label,'text':text,'source':REPO,'source_revision':REV,
                         'source_domain':'question-answering','training_overlap_unknown':True})
    print('Downloaded',domain,len(pairs),'question pairs',flush=True)
target=ROOT/'hc3_pilot.jsonl'
target.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
(ROOT/'hc3_pilot_metadata.json').write_text(json.dumps({'dataset':REPO,'revision':REV,'license':'CC-BY-SA-4.0',
 'url':f'https://huggingface.co/datasets/{REPO}','samples':len(rows),'groups':len(seen),
 'selection':'first 12 valid distinct pairs per domain; each answer 120..4000 chars; all paragraphs route zh; globally unique question and answer hashes; deterministic domain-stratified 6/6 group split',
 'limitations':['Not a random representative sample','Unknown overlap with pretrained detector training','QA rather than academic-paper domain','36 human test samples cannot substantiate <1% population FPR'],
 'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
