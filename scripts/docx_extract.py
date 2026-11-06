"""Read-only DOCX extraction, no media decompression or network/model calls."""
from pathlib import Path
from zipfile import ZipFile
from collections import Counter
from defusedxml import ElementTree as ET
import hashlib, json, re

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS = {'w': W}
def tag(n): return '{'+W+'}'+n
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()
def dump(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def visible_text(p, include_math=True):
    out=[]
    def walk(e):
        if e is not p and e.tag in (tag('p'), tag('del'), tag('moveFrom')): return
        if not include_math and e.tag in ('{'+M+'}oMath','{'+M+'}oMathPara'): return
        if e.tag in (tag('t'), '{'+M+'}t'): out.append(e.text or '')
        elif e.tag==tag('tab'): out.append('\t')
        elif e.tag in (tag('br'),tag('cr')): out.append('\n')
        elif e.tag==tag('noBreakHyphen'): out.append('\u2011')
        elif e.tag==tag('softHyphen'): out.append('\u00ad')
        for ch in e: walk(ch)
    walk(p)
    return ''.join(out).strip()
def extract(path, ident, output_dir):
    digest=sha(path)
    with ZipFile(path) as z:
        doc=ET.fromstring(z.read('word/document.xml'))
        styles={}
        if 'word/styles.xml' in z.namelist():
            for s in ET.fromstring(z.read('word/styles.xml')).findall('w:style',NS):
                name=s.find('w:name',NS); base=s.find('w:basedOn',NS); ol=s.find('w:pPr/w:outlineLvl',NS)
                styles[s.get(tag('styleId'))]={'name':name.get(tag('val'),'') if name is not None else '', 'base':base.get(tag('val')) if base is not None else None,'outline':ol.get(tag('val')) if ol is not None else None}
        metadata={}
        for part in ('docProps/core.xml','docProps/custom.xml','docProps/app.xml'):
            if part in z.namelist(): metadata[part]=ET.fromstring(z.read(part))
        metadata={k:[{'name':e.tag.split('}')[-1], 'value':e.text} for e in v.iter() if len(e)==0 and e.text] for k,v in metadata.items()}
        body=doc.find('w:body',NS)
        parents={ch:par for par in body.iter() for ch in par}
        ps=[]
        for idx,p in enumerate(body.iter(tag('p'))):
            text=visible_text(p)
            s=p.find('w:pPr/w:pStyle',NS); sid=s.get(tag('val'),'') if s is not None else ''
            names=[]; outlines=[]; seen=set(); cur=sid
            while cur and cur not in seen:
                seen.add(cur); st=styles.get(cur,{})
                names.append(st.get('name','')); outlines.append(st.get('outline')); cur=st.get('base')
            anc=[]; cur=parents.get(p)
            while cur is not None:
                anc.append(cur.tag); cur=parents.get(cur)
            direct=p.find('w:pPr/w:outlineLvl',NS)
            outline=direct.get(tag('val')) if direct is not None else next((v for v in outlines if v is not None),None)
            ps.append({'index':idx, 'text':text,'style_id':sid,'style_name':styles.get(sid,{}).get('name',''),'style_ancestry':names,'outline_level':outline,'in_table':tag('tc') in anc,'in_textbox':tag('txbxContent') in anc,'math_only':bool(p.find('.//{'+M+'}oMath') is not None and not re.search(r'[A-Za-z\u3400-\u9fff]',visible_text(p,False))),'eligible':False,'exclusion':None})
        for p in ps:
            p['is_heading']=bool((p['outline_level'] is not None and int(p['outline_level'])<9) or any(re.search(r'heading|标题',n,re.I) for n in p['style_ancestry']) or (re.match(r'^[（(][\d一二三四五六七八九十]+[）)]\s*\S',p['text']) and not re.search(r'[。.;；：:!?！？]',p['text'])))
        intro=next((p['index'] for p in ps if re.match(r'^\s*(?:(?:1|一)[.、．]?\s*)?(?:Introduction|引言|绪论|前言)\s*$',p['text'],re.I)),None)
        references=False; abstract=False
        for p in ps:
            t=p['text']; norm=re.sub(r'\s+','',t)
            if re.fullmatch(r'(?:\d+[.、．]?)?(?:References|Bibliography|参考文献)[：:]?',norm,re.I): references=True
            if re.fullmatch(r'(?:Abstract|摘要)[：:]?',norm,re.I): abstract=True
            elif re.match(r'^(?:Keywords|Key words|关键词|关键字)\s*[:：]',t,re.I): abstract=False
            elif intro is not None and p['index']>=intro: abstract=False
            if not t: reason='empty'
            elif p['in_table']: reason='table_cell'
            elif p['in_textbox']: reason='textbox'
            elif p['math_only']: reason='standalone_equation'
            elif references: reason='references_and_backmatter'
            elif any(re.search(r'^toc\s*\d*$|目录',n,re.I) for n in p['style_ancestry']) or norm in ('目录','目次','Contents','TableofContents'): reason='table_of_contents'
            elif p['is_heading']: reason='heading'
            elif re.fullmatch(r'(?:(?:1|一)[.、．]?\s*)?(?:Introduction|引言|绪论|前言)',t,re.I): reason='heading'
            elif re.fullmatch(r'(?:Abstract|摘要)[：:]?',norm,re.I): reason='heading'
            elif re.match(r'^(?:Keywords|Key words|关键词|关键字)\s*[:：]',t,re.I): reason='keywords'
            elif any(re.search(r'caption|题注',n,re.I) for n in p['style_ancestry']): reason='caption'
            elif re.match(r'^(?:Figure|Fig\.|Table|图|表)\s*\d+[.\-\d]*\s*[:：.\s]',t,re.I) and not re.search(r'\b(?:shows?|presents?|illustrates?|indicates?|reveals?|summari[sz]es?|reports?|depicts?)\b|表明|显示|可见',t,re.I): reason='caption_label'
            elif intro is not None and p['index']<intro and not abstract and not re.match(r'^(?:Abstract|摘要)\s*[:：]',t,re.I): reason='frontmatter'
            elif intro is None and p['index']==next((x['index'] for x in ps if x['text']),-1): reason='title'
            elif any(re.search(r'^title$|^subtitle$|^标题$|^副标题$',n,re.I) for n in p['style_ancestry']): reason='title'
            elif not re.search(r'[A-Za-z\u3400-\u9fff]',t): reason='non_prose_formula_or_numeric'
            else: reason=None
            p['exclusion']=reason; p['eligible']=reason is None
        out=Path(output_dir)/ident; out.mkdir(parents=True,exist_ok=True)
        full='\n\n'.join(p['text'] for p in ps if p['text'])
        eligible='\n\n'.join(p['text'] for p in ps if p['eligible'])
        (out/'full.txt').write_text(full,encoding='utf-8'); (out/'eligible.txt').write_text(eligible,encoding='utf-8')
        dump(out/'paragraphs.json',ps); dump(out/'metadata.json',metadata)
        # Non-overlapping character windows; every character represented, no sampling/truncation.
        # Windows are paragraph-local to preserve source traceability. Model-specific token windows must retain tails.
        windows=[]
        for p in ps:
            if not p['eligible']: continue
            for start in range(0,len(p['text']),1000):
                windows.append({'id':f'{ident}_p{p["index"]}_c{start}','document_id':ident,'paragraph_index':p['index'],'start_char':start,'end_char':min(start+1000,len(p['text'])),'text':p['text'][start:start+1000]})
        dump(out/'windows.json',windows)
        cjk=len(re.findall(r'[\u3400-\u9fff]',eligible)); latin=len(re.findall(r'[A-Za-z]',eligible))
        flags=['No verified authorship labels or detector ground truth supplied; filenames and metadata cannot establish AI authorship.']
        if re.search(r'修订|重写|rewrite|draft',path.name,re.I): flags.append('Filename indicates revision/rewriting, not verified AI provenance.')
        signals=[]
        for p in ps:
            for m in re.finditer(r'(?i)(?:ChatGPT|GPT[- ]?\d|AIGC|AI生成|人工智能生成|知网.{0,12}(?:检测|查重)|检测报告)',p['text']):
                signals.append({'paragraph_index':p['index'],'match':m.group(0),'context':p['text'][max(0,m.start()-50):m.end()+80]})
        return {'id':ident,'filename':path.name,'source_path':str(path.resolve()),'sha256':digest,'bytes':path.stat().st_size,'language':'zh' if cjk>latin else 'en','eligible_chars':len(eligible),'full_chars':len(full),'paragraphs_count':len(ps),'eligible_paragraphs_count':sum(p['eligible'] for p in ps),'text_path':str((out/'eligible.txt').resolve()),'text_sha256':sha(out/'eligible.txt'),'full_text_path':str((out/'full.txt').resolve()),'paragraphs_path':str((out/'paragraphs.json').resolve()),'windows_path':str((out/'windows.json').resolve()),'metadata_path':str((out/'metadata.json').resolve()),'window_count':len(windows),'exclusions':dict(Counter(p['exclusion'] for p in ps if p['exclusion'])),'ground_truth':None,'provenance_flags':flags,'label_or_report_mentions':signals,'source_hash_after_extraction':sha(path),'introduction_index':intro}

