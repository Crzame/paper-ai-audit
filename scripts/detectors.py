"""Published checkpoint adapters; local-only inference on the exact same character spans."""
import hashlib,json,os
from pathlib import Path
from audit_core import fingerprint,language_of,split_spans,summarize,style_clues,provenance_clues
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'

class DetectorSet:
    def __init__(self,registry,threads=4,batch_size=8):
        import torch
        from transformers import AutoModelForSequenceClassification,AutoTokenizer
        torch.set_num_threads(threads);torch.manual_seed(20261106)
        self.torch=torch;self.batch_size=batch_size;self.loaded={};self.status={}
        self.registry=json.loads(Path(registry).read_text(encoding='utf-8'))
        identities=[]
        for row in self.registry['models']:
            key=row['key'];identities.append({k:row[k] for k in ['key','id','revision','language','max_length','temperature','ai_class','files']})
            try:
                folder=Path(os.path.expandvars(row['local_path']))
                for record in row['files']:
                    path=folder/record['name'];h=hashlib.sha256()
                    with path.open('rb') as stream:
                        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
                    if h.hexdigest()!=record['sha256']:raise ValueError('Model file hash mismatch: '+record['name'])
                tok=AutoTokenizer.from_pretrained(folder,local_files_only=True,use_fast=False,trust_remote_code=False)
                model=AutoModelForSequenceClassification.from_pretrained(folder,local_files_only=True,trust_remote_code=False).eval()
                if model.config.num_labels!=2 or row['ai_class']!=1:raise ValueError('Unsupported class mapping')
                if key=='bert_zh' and model.config.id2label.get(1)!='AI-generated':raise ValueError('BERT label mapping mismatch')
                self.loaded[key]=(row,tok,model);self.status[key]={'status':'READY','model_id':row['id'],'revision':row['revision']}
            except Exception as exc:
                self.status[key]={'status':'UNAVAILABLE','error':type(exc).__name__+': '+str(exc)}
        self.identity={'pipeline_version':1,'extraction_policy':'prose-v3-explicit-intro-heading',
                       'partition':'paragraph_balanced_chars_then_bisect_until_all_active_tokenizers_fit',
                       'max_chars_zh':220,'max_chars_en':1600,'short_nonspace_characters':80,'models':identities}
        self.fingerprint=fingerprint(self.identity)

    def _safe_spans(self,text,language):
        applicable=[(row,tok) for row,tok,_ in self.loaded.values() if row['language']==language]
        initial=split_spans(text,220 if language=='zh' else 1600)
        def refine(start,end):
            candidate=text[start:end]
            if all(len(tok.encode(candidate,add_special_tokens=True,truncation=False,verbose=False))<=row['max_length'] for row,tok in applicable):return [(start,end)]
            if end-start<2:raise ValueError('A single character exceeds a tokenizer capacity')
            mid=(start+end)//2
            return refine(start,mid)+refine(mid,end)
        return [span for start,end in initial for span in refine(start,end)]

    def analyze(self,paragraphs,progress=False):
        windows=[]
        for paragraph in paragraphs:
            text=paragraph['text'];language=language_of(text)
            for start,end in self._safe_spans(text,language):
                sample=text[start:end]
                windows.append({'paragraph_index':paragraph['index'],'language':language,'start':start,'end':end,
                                'characters':end-start,'text':sample,'short_text':len(''.join(sample.split()))<80,
                                'scores':{row['key']:None for row in self.registry['models'] if row['language']==language}})
        run_status=dict(self.status)
        with self.torch.inference_mode():
            for key,(row,tok,model) in self.loaded.items():
                indices=[i for i,w in enumerate(windows) if w['language']==row['language']]
                try:
                    for start_batch in range(0,len(indices),self.batch_size):
                        batch_indices=indices[start_batch:start_batch+self.batch_size]
                        texts=[windows[i]['text'] for i in batch_indices]
                        batch=tok(texts,add_special_tokens=True,padding=True,truncation=False,return_tensors='pt',verbose=False)
                        if batch['input_ids'].shape[1]>row['max_length']:raise ValueError('Unsplit overlong input; no truncation allowed')
                        scores=self.torch.softmax(model(**batch).logits/row['temperature'],dim=-1)[:,row['ai_class']].tolist()
                        for index,score in zip(batch_indices,scores):windows[index]['scores'][key]=score
                    if progress:print('Scored',key,len(indices),'common spans',flush=True)
                except Exception as exc:
                    # A partial failed pass is not a complete zero-score vote.
                    for index in indices:windows[index]['scores'][key]=None
                    run_status[key]={'status':'FAILED','error':type(exc).__name__+': '+str(exc)}
        summary=summarize(windows)
        summary.update(model_status=run_status,fingerprint=self.fingerprint,
                       short_text_characters=sum(w['characters'] for w in windows if w['short_text']),
                       classification_unit='unvalidated_character_windows',document_prediction=None)
        all_text='\n\n'.join(p['text'] for p in paragraphs)
        return {'summary':summary,'windows':windows,'style':style_clues(all_text),
                'provenance':provenance_clues(all_text),'identity':self.identity}
