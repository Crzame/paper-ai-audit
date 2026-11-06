"""Analyze DOCX, UTF-8 text or Markdown locally; source files are never overwritten."""
import argparse,hashlib,json,sys,time
from pathlib import Path
from audit_core import profile_applies
from detectors import DetectorSet

ROOT=Path(__file__).resolve().parents[1]
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def analyze_file(path,detectors,out,profile=None,domain='academic'):
    path=Path(path).resolve();digest=hashlib.sha256(path.read_bytes()).hexdigest();ident=digest[:12]
    target=Path(out)/ident;target.mkdir(parents=True,exist_ok=True)
    if path.suffix.lower()=='.docx':
        from docx_extract import extract
        extraction=extract(path,ident,Path(out)/'extracted')
        records=json.loads(Path(extraction['paragraphs_path']).read_text(encoding='utf-8'))
        paragraphs=[p for p in records if p['eligible']]
        scope={'policy':'prose-v3-explicit-intro-heading','exclusions':extraction['exclusions'],
               'eligible_characters_excluding_inserted_separators':sum(len(p['text']) for p in paragraphs),
               'all_xml_paragraphs':len(records),'limitations':['No image OCR or visual layout reconstruction','References and all following backmatter excluded, including post-reference English abstracts','Heuristic caption/frontmatter exclusions need review']}
    elif path.suffix.lower() in ['.txt','.md']:
        text=path.read_text(encoding='utf-8-sig')
        paragraphs=[{'index':i,'text':p.strip()} for i,p in enumerate(text.split('\n\n')) if p.strip()]
        scope={'policy':'utf8-blank-line-paragraphs','eligible_characters_excluding_inserted_separators':sum(len(p['text']) for p in paragraphs),
               'limitations':['No automatic Markdown code/reference exclusion; plain text scope is explicit']}
    else:raise ValueError('Supported inputs: DOCX, UTF-8 TXT, MD')
    begin=time.perf_counter();result=detectors.analyze(paragraphs,progress=True)
    result.update(input={'path':str(path),'filename':path.name,'sha256':digest},scope=scope,domain=domain,
                  elapsed_seconds=time.perf_counter()-begin)
    if profile:
        languages={w['language'] for w in result['windows']}
        language=next(iter(languages)) if len(languages)==1 else 'mixed'
        valid,reason=profile_applies(profile,detectors.fingerprint,language,domain,'document')
        result['profile_application']={'applied':valid,'reason':reason,'unit':'document'}
        means=result['summary']['raw_mean_scores']
        full_model_scores=[score for key,score in means.items() if result['summary']['model_coverage'][key]==1]
        if valid and len(full_model_scores)>=2:
            feature=min(full_model_scores)
            result['summary']['status']='CALIBRATED_DOCUMENT_CLASSIFICATION'
            result['summary']['document_prediction']={'label':'AI_SIGNAL' if feature>=profile['threshold'] else 'NOT_FLAGGED',
                                                     'score':feature,'threshold':profile['threshold'],
                                                     'note':'Document classification; NOT_FLAGGED does not confirm human, and no AI character fraction is inferred.'}
        elif valid:
            result['profile_application']={'applied':False,'reason':'required_model_coverage_missing','unit':'document'}
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,'Source changed while reading'
    dump(target/'result.json',result)
    s=result['summary'];model_rows='\n'.join(f"| {k} | {v:.6f} | {s['raw_flagged_shares_at_0_5'][k]:.2%} | {s['model_coverage'][k]:.2%} |" for k,v in s['raw_mean_scores'].items())
    agreement='不适用' if s['agreement_high_signal_share'] is None else f"{s['agreement_high_signal_share']:.2%}"
    report=f'''# {path.name} 检测记录

状态：{s['status']}。**当前没有经过适用校准的全文 AI 百分比。**

| 模型 | 字符加权类分数 | ≥0.5原始窗口份额 | 纳入文本的模型覆盖率 |
|---|---:|---:|---:|
{model_rows}

这些是分类器信号，不是真实生成比例。缺失模型不会计为0分或人工票。

双方分数均≥0.95的候选范围：{agreement}；分母为有双模型结果且非短片段的{s['candidate_denominator_characters']}字符。该候选阈值未做本任务校准，不能把模型一致当作独立证据或低误报保证。模型分歧和短片段保留不确定性。

纳入正文：{s['eligible_characters']}字符；短片段范围：{s['short_text_characters']}字符。排除范围及局限见 result.json 的 scope；未评分对象不计为人工。水印状态：NOT_TESTABLE，Unicode线索不计入作者身份分数。

本轮无任何文风规则到AI率的换算。逐窗口原文、位置、分数、失败状态和来源SHA-256在同目录result.json。原件未改动。
'''
    (target/'report.md').write_text(report,encoding='utf-8')
    return {'filename':path.name,'sha256':digest,'output':str(target),'summary':s}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--registry',type=Path,default=ROOT/'assets/models.local.json')
    parser.add_argument('--threads',type=int,default=4);parser.add_argument('--batch-size',type=int,default=8)
    parser.add_argument('--profile',type=Path);parser.add_argument('--domain',default='academic');args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    detector=DetectorSet(args.registry,args.threads,args.batch_size)
    files=sorted([p for p in args.input.iterdir() if p.suffix.lower() in ['.docx','.txt','.md']]) if args.input.is_dir() else [args.input]
    profile=json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else None
    rows=[analyze_file(path,detector,args.output,profile,args.domain) for path in files]
    dump(args.output/'summary.json',rows)
    print(json.dumps({'documents':len(rows),'output':str(args.output),'fingerprint':detector.fingerprint},ensure_ascii=True))

if __name__=='__main__':main()
