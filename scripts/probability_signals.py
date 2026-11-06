"""Optional local Qwen scoring adapter; raw statistics only, no official-model thresholds."""
import argparse,hashlib,json,math,os
from pathlib import Path
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM

@torch.inference_mode()
def score_document(ids,models,doc_id,out):
    windows=[]
    total=len(ids)-1
    next_target=1
    while next_target<len(ids):
        left=max(0,next_target-64)
        right=min(len(ids),next_target+448)
        inputs=torch.tensor([ids[left:right]],dtype=torch.long)
        logits_ref=models[0](inputs,use_cache=False).logits[0,:-1].float()
        logits_score=models[1](inputs,use_cache=False).logits[0,:-1].float()
        begin=next_target-left-1
        logits_ref=logits_ref[begin:]
        logits_score=logits_score[begin:]
        labels=inputs[0,begin+1:]
        log_q=torch.log_softmax(logits_score,dim=-1)
        p=torch.softmax(logits_ref,dim=-1)
        observed=log_q.gather(-1,labels[:,None]).squeeze(-1)
        mean=(p*log_q).sum(-1)
        var=(p*log_q.square()).sum(-1)-mean.square()
        var=var.clamp_min(1e-12)
        discrepancy=((observed.sum()-mean.sum())/var.sum().sqrt()).item()
        nll=-observed.mean().item()
        cross_entropy=-mean.mean().item()
        item={'window':len(windows)+1,'context_start_token':left,'target_start_token':next_target,
            'target_end_token_exclusive':right,'scored_tokens':len(labels),'mean_nll':nll,
            'perplexity':math.exp(min(700,nll)), 'cross_entropy':cross_entropy,
            'binoculars_style_ratio':nll/cross_entropy,'fast_detect_gpt_analytic_raw':discrepancy,
            'observed_sum':observed.sum().item(),'expected_sum':mean.sum().item(),'variance_sum':var.sum().item()}
        windows.append(item)
        next_target=right
        del logits_ref,logits_score,log_q,p,observed,mean,var,inputs
        if len(windows)%10==0 or next_target==len(ids):
            print(doc_id,'window',len(windows),'coverage_tokens',sum(w['scored_tokens'] for w in windows),'/',total,flush=True)
        out.write(json.dumps(item)+'\n');out.flush()
    assert sum(w['scored_tokens'] for w in windows)==total
    nll=sum(w['mean_nll']*w['scored_tokens'] for w in windows)/total
    ce=sum(w['cross_entropy']*w['scored_tokens'] for w in windows)/total
    obs=sum(w['observed_sum'] for w in windows)
    exp=sum(w['expected_sum'] for w in windows)
    variance=sum(w['variance_sum'] for w in windows)
    mean_window_nll=nll
    return {'tokens':len(ids),'scored_tokens':total,'token_coverage_excluding_first':1.0,
        'windows':len(windows),'mean_nll':nll,'perplexity':math.exp(nll),
        'window_nll_weighted_sd':math.sqrt(sum(w['scored_tokens']*(w['mean_nll']-mean_window_nll)**2 for w in windows)/total),
        'binoculars_style_ratio':nll/ce,'fast_detect_gpt_analytic_raw':(obs-exp)/math.sqrt(variance),
        'ai_rate':None,'classification':None,'threshold':None,
        'warning':'Qwen small-model/window adaptation; no calibrated threshold or labels; raw statistics are not AI percentages.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--text',required=True,type=Path);parser.add_argument('--models',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--threads',type=int,default=4)
    args=parser.parse_args();torch.set_num_threads(args.threads)
    records=json.loads(args.models.read_text(encoding='utf-8'))
    if len(records)!=2:raise ValueError('Two local Base/Instruct model records required')
    if [r['id'] for r in records]!=['Qwen/Qwen2.5-0.5B','Qwen/Qwen2.5-0.5B-Instruct']:raise ValueError('This adapter is bound to the documented Qwen pair')
    toks=[AutoTokenizer.from_pretrained(r['folder'],local_files_only=True,trust_remote_code=False) for r in records]
    if toks[0].get_vocab()!=toks[1].get_vocab():raise ValueError('Tokenizer vocabularies differ')
    text=args.text.read_text(encoding='utf-8-sig');ids=toks[0].encode(text,add_special_tokens=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if len(ids)<2:
        result={'status':'INSUFFICIENT_TEXT','ai_rate':None}
    else:
        models=[AutoModelForCausalLM.from_pretrained(r['folder'],local_files_only=True,trust_remote_code=False,dtype=torch.float32,attn_implementation='sdpa').eval() for r in records]
        with args.output.with_suffix('.windows.jsonl').open('w',encoding='utf-8') as stream:
            result=score_document(ids,models,'input',stream)
    result.update(model_records=records,text_sha256=hashlib.sha256(text.encode()).hexdigest(),scope='caller-supplied text file',
                  note='Small-model adaptation; Binoculars CE aligns new shifted targets rather than upstream full input positions. No calibrated detector threshold.')
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['ai_rate','text_sha256']},ensure_ascii=True))

if __name__=='__main__':main()
