"""Deterministic coverage, separate signals and held-out low-FPR validation."""
import hashlib,json,math,re,statistics,unicodedata

def fingerprint(config):
    return hashlib.sha256(json.dumps(config,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def language_of(text):
    han=len(re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff]',text));latin=len(re.findall(r'[A-Za-z]',text))
    if han+latin==0:return 'unknown'
    return 'zh' if han/(han+latin)>=.2 else 'en'

def split_spans(text,max_chars):
    if max_chars<1:raise ValueError('max_chars must be positive')
    if not text:return []
    count=math.ceil(len(text)/max_chars)
    return [(i*len(text)//count,(i+1)*len(text)//count) for i in range(count)]

def summarize(windows,high_threshold=.95):
    total=sum(w['characters'] for w in windows)
    weights={};sums={};flagged={};two=high=disagree=0
    for w in windows:
        weight=w['characters']
        scores={k:v for k,v in w['scores'].items() if v is not None}
        if any(not math.isfinite(v) or not 0<=v<=1 for v in scores.values()):raise ValueError('Invalid model score')
        for key,value in scores.items():
            weights[key]=weights.get(key,0)+weight;sums[key]=sums.get(key,0)+weight*value
            flagged[key]=flagged.get(key,0)+(weight if value>=.5 else 0)
        if len(scores)>=2 and not w.get('short_text',False):
            two+=weight
            if min(scores.values())>=high_threshold:high+=weight
            if min(scores.values())<.5<=max(scores.values()):disagree+=weight
    return {'status':'UNCALIBRATED' if weights else 'NO_MODELS','final_ai_rate':None,
            'raw_mean_scores':{k:sums[k]/weights[k] for k in weights},
            'raw_flagged_shares_at_0_5':{k:flagged[k]/weights[k] for k in weights},
            'model_coverage':{k:weights[k]/total for k in weights} if total else {},
            'eligible_characters':total,'two_model_coverage':two/total if total else 0,
            'agreement_high_signal_characters':high,'agreement_high_signal_share':high/two if two else None,
            'disagreement_characters':disagree,'disagreement_share':disagree/two if two else None,
            'candidate_threshold':high_threshold,'candidate_denominator_characters':two,
            'interpretation':'Raw scores and thresholded window scopes, not true AI percentage; agreement candidate share is conditional on >=2 available models.'}

def style_clues(text):
    residues=[]
    for phrase in ['当然可以，以下是','希望这对你有帮助','作为一个AI语言模型','作为人工智能语言模型',
                   'As an AI language model','I hope this helps']:
        for m in re.finditer(re.escape(phrase),text,re.I):residues.append({'start':m.start(),'end':m.end(),'quote':m.group()})
    lengths=[len(v.strip()) for v in re.split(r'[。！？!?\n]+',text) if v.strip()]
    return {'authorship_score':None,'chat_residue':residues,
            'sentence_length_characters':lengths,
            'sentence_length_cv':statistics.pstdev(lengths)/statistics.mean(lengths) if len(lengths)>1 else None,
            'note':'Clues require context review, including quotation and academic-register checks; length variation is not perplexity.'}

def provenance_clues(text):
    chars=[{'index':i,'codepoint':f'U+{ord(c):04X}','name':unicodedata.name(c,'UNKNOWN')}
           for i,c in enumerate(text) if unicodedata.category(c)=='Cf' or 0xE0100<=ord(c)<=0xE01EF]
    return {'unicode_candidates':chars,'watermark_status':'NOT_TESTABLE',
            'watermark_score':None,'ai_rate':None,
            'reason':'No matched generation tokenizer, watermark scheme and key/config supplied; Unicode findings do not establish AI origin.'}

def upper_fpr(false_positives,human_count,alpha=.05):
    """One-sided exact Clopper-Pearson upper confidence limit, not a deployment guarantee."""
    if not 0<=false_positives<=human_count or not 0<alpha<1:raise ValueError('Invalid binomial counts')
    if human_count==0:return None
    if false_positives==human_count:return 1.0
    if false_positives==0:return 1-alpha**(1/human_count)
    k,n=false_positives,human_count
    def cdf(p):
        logs=[math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p) for i in range(k+1)]
        m=max(logs);return math.exp(m)*sum(math.exp(x-m) for x in logs)
    lo,hi=0.0,1.0
    for _ in range(60):
        mid=(lo+hi)/2
        if cdf(mid)>alpha:lo=mid
        else:hi=mid
    return (lo+hi)/2

def metrics(rows,threshold):
    human=[r for r in rows if r['label']==0];ai=[r for r in rows if r['label']==1]
    fp=sum(r['score']>=threshold for r in human);tp=sum(r['score']>=threshold for r in ai)
    return {'human_count':len(human),'ai_count':len(ai),'false_positives':fp,'true_positives':tp,
            'fpr':fp/len(human) if human else None,'fpr_upper_95_one_sided':upper_fpr(fp,len(human)),
            'recall':tp/len(ai) if ai else None,
            'precision':tp/(tp+fp) if tp+fp else None,
            'accuracy':(tp+len(human)-fp)/len(rows) if rows else None}

def fit_profile(rows,target_fpr,model_fingerprint,language,domain,unit):
    if not 0<target_fpr<1:raise ValueError('target_fpr must lie in (0,1)')
    if unit not in ['document','window']:raise ValueError('unit must be document or window')
    for r in rows:
        if r.get('label') not in [0,1] or not isinstance(r.get('score'),(int,float)) or not math.isfinite(r['score']) or not 0<=r['score']<=1:
            raise ValueError('Verified binary labels and finite score in [0,1] required')
        if not r.get('group_id') or r.get('split') not in ['calibration','test']:raise ValueError('group_id and calibration/test split required')
        if not isinstance(r.get('text_sha256'),str) or not r['text_sha256']:raise ValueError('Text digest required to check duplicate samples')
        for key,expected in [('fingerprint',model_fingerprint),('language',language),('domain',domain),('unit',unit)]:
            if r.get(key)!=expected:raise ValueError('Row '+key+' does not match declared calibration scope')
    family_labels=[(r['group_id'],r['label']) for r in rows]
    if len(set(family_labels))!=len(family_labels):
        raise ValueError('Repeated source-group/class observations are not independent samples; select one per group/class or use a separate cluster-aware evaluation')
    text_hashes=[r['text_sha256'] for r in rows]
    if len(set(text_hashes))!=len(text_hashes):raise ValueError('Duplicate text records cannot increase independent sample size')
    cal=[r for r in rows if r['split']=='calibration'];test=[r for r in rows if r['split']=='test']
    if set(r['group_id'] for r in cal)&set(r['group_id'] for r in test):raise ValueError('Source-group leakage across splits')
    hashes=lambda items:{r['text_sha256'] for r in items if r.get('text_sha256')}
    if hashes(cal)&hashes(test):raise ValueError('Duplicate text across splits')
    if any(not any(r['label']==label for r in split) for split in [cal,test] for label in [0,1]):raise ValueError('Both classes required in both splits')
    human=[r['score'] for r in cal if r['label']==0]
    candidates=sorted(set([0.0]+[math.nextafter(s,math.inf) for s in human]))
    threshold=next(t for t in candidates if sum(s>=t for s in human)/len(human)<=target_fpr)
    validation=metrics(test,threshold)
    overlap_unknown=any(r.get('training_overlap_unknown') is not False for r in rows)
    validated=validation['fpr_upper_95_one_sided']<=target_fpr and not overlap_unknown
    return {'version':2,'fingerprint':model_fingerprint,'language':language,'domain':domain,'unit':unit,
            'target_fpr':target_fpr,'threshold':threshold,'selection':'lowest threshold satisfying calibration empirical FPR; independent test only evaluates',
            'calibration':metrics(cal,threshold),'validation':validation,'validated_low_fpr':validated,
            'training_overlap_unknown':overlap_unknown,'positive_detection_observed':validation['true_positives']>0,
            'independent_sample_policy':'one observation per source-group and class; globally unique text hashes',
            'scope_note':'Confidence limit applies conditionally to this held-out population and independence assumptions; no cross-domain guarantee.'}

def profile_applies(profile,model_fingerprint,language,domain,unit):
    if profile.get('version')!=2:return False,'unsupported_profile_version'
    if profile.get('independent_sample_policy')!='one observation per source-group and class; globally unique text hashes':
        return False,'independent_sample_policy_missing'
    for key,expected in [('fingerprint',model_fingerprint),('language',language),('domain',domain),('unit',unit)]:
        if profile.get(key)!=expected:return False,key+'_mismatch'
    if not profile.get('validated_low_fpr'):return False,'low_fpr_not_validated'
    if profile.get('training_overlap_unknown') is not False:return False,'training_overlap_unknown'
    validation=profile.get('validation',{})
    try:
        n=validation['human_count'];fp=validation['false_positives'];tp=validation['true_positives']
        target=profile['target_fpr'];threshold=profile['threshold']
        if not isinstance(n,int) or not isinstance(fp,int) or n<=0 or not 0<=fp<=n:return False,'invalid_validation_counts'
        if not isinstance(threshold,(int,float)) or not math.isfinite(threshold) or not 0<target<1:return False,'invalid_profile_threshold'
        if upper_fpr(fp,n)>target:return False,'independent_test_upper_bound_exceeds_target'
        if tp<1:return False,'no_positive_detection_observed'
    except (KeyError,TypeError,ValueError):return False,'missing_or_invalid_validation_evidence'
    return True,'matched_held_out_scope'
