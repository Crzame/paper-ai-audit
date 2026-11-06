import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_core import split_spans,summarize,upper_fpr,fit_profile,profile_applies,style_clues

class AuditChecks(unittest.TestCase):
    def clean_rows(self,overlap=False):
        rows=[]
        for split in ['calibration','test']:
            for label in [0,1]:
                for i in range(300):
                    ident=f'{split}-{label}-{i}'
                    row={'id':ident,'group_id':ident,'text_sha256':ident,'label':label,'score':.1 if label==0 else .9,
                         'split':split,'fingerprint':'f','language':'zh','domain':'academic','unit':'document'}
                    if overlap is not None:row['training_overlap_unknown']=overlap
                    rows.append(row)
        return rows
    def test_every_character_including_tail_is_covered_once(self):
        for n in range(1,1700):
            text=('中文。a b；'*300)[:n]
            spans=split_spans(text,220)
            self.assertEqual(''.join(text[a:b] for a,b in spans),text)
            self.assertTrue(all(0<b-a<=220 for a,b in spans))
            self.assertTrue(all(spans[i-1][1]==spans[i][0] for i in range(1,len(spans))))
    def test_high_agreement_is_not_a_calibrated_ai_rate(self):
        s=summarize([{'characters':100,'scores':{'v3_zh':.99,'bert_zh':.98}},{'characters':50,'scores':{'v3_zh':.99,'bert_zh':.1}}])
        self.assertIsNone(s['final_ai_rate']);self.assertEqual(s['status'],'UNCALIBRATED')
        self.assertAlmostEqual(s['agreement_high_signal_share'],2/3)
        self.assertAlmostEqual(s['disagreement_share'],1/3)
    def test_missing_model_is_not_a_zero_or_human_vote(self):
        s=summarize([{'characters':100,'scores':{'v3_zh':.99,'bert_zh':None}}])
        self.assertEqual(s['two_model_coverage'],0)
        self.assertIsNone(s['agreement_high_signal_share'])
        self.assertEqual(s['raw_mean_scores'],{'v3_zh':.99})
    def test_short_high_scores_remain_outside_joint_candidates(self):
        s=summarize([{'characters':20,'short_text':True,'scores':{'v3_zh':.99,'bert_zh':.99}}])
        self.assertIsNone(s['agreement_high_signal_share'])
        self.assertIsNone(s['final_ai_rate'])
    def test_exact_small_sample_fpr_upper_bound(self):
        self.assertGreater(upper_fpr(0,60),.01)
        self.assertLess(upper_fpr(0,300),.01)
        self.assertAlmostEqual(upper_fpr(0,60),1-.05**(1/60),places=12)
        self.assertEqual(upper_fpr(30,30),1)
        self.assertIsNone(upper_fpr(0,0))
    def test_unlabelled_rows_and_group_leakage_rejected(self):
        with self.assertRaises(ValueError):fit_profile([{'group_id':'a','score':.7,'split':'calibration'}],.01,'f','zh','academic','document')
        rows=self.clean_rows()
        rows[600]['group_id']=rows[0]['group_id']
        with self.assertRaises(ValueError):fit_profile(rows,.01,'f','zh','academic','document')
    def test_profile_scope_and_low_fpr_evidence_are_binding(self):
        p=fit_profile(self.clean_rows(),.01,'f','zh','academic','document')
        self.assertFalse(profile_applies(p,'f','zh','qa','document')[0])
        self.assertFalse(profile_applies(p,'other','zh','qa','document')[0])
        self.assertFalse(profile_applies(p,'f','zh','academic','window')[0])
        self.assertTrue(profile_applies(p,'f','zh','academic','document')[0])
        p['validated_low_fpr']=False
        self.assertFalse(profile_applies(p,'f','zh','academic','document')[0])
    def test_repeated_test_group_cannot_inflate_independent_sample_size(self):
        rows=self.clean_rows()
        for r in rows:
            if r['split']=='test' and r['label']==0:r['group_id']='same-human-source'
        with self.assertRaisesRegex(ValueError,'[Dd]uplicate|[Rr]epeated'):fit_profile(rows,.01,'f','zh','academic','document')
    def test_missing_training_overlap_declaration_is_unknown(self):
        p=fit_profile(self.clean_rows(overlap=None),.01,'f','zh','academic','document')
        self.assertTrue(p['training_overlap_unknown'])
        self.assertFalse(p['validated_low_fpr'])
    def test_duplicate_text_with_different_group_ids_is_rejected(self):
        rows=self.clean_rows();rows[1]['text_sha256']=rows[0]['text_sha256']
        with self.assertRaisesRegex(ValueError,'Duplicate'):fit_profile(rows,.01,'f','zh','academic','document')
    def test_older_profiles_cannot_bypass_new_independence_checks(self):
        p=fit_profile(self.clean_rows(),.01,'f','zh','academic','document');p['version']=1
        self.assertFalse(profile_applies(p,'f','zh','academic','document')[0])
    def test_rows_cannot_be_relabelled_into_another_domain(self):
        rows=self.clean_rows()
        for r in rows:r['domain']='question-answering'
        with self.assertRaises(ValueError):fit_profile(rows,.01,'f','zh','academic','document')
    def test_forged_boolean_is_not_validation_evidence(self):
        p={'fingerprint':'f','language':'zh','domain':'academic','unit':'document','validated_low_fpr':True}
        self.assertFalse(profile_applies(p,'f','zh','academic','document')[0])
    def test_zero_recall_does_not_activate_a_detector(self):
        rows=self.clean_rows()
        for r in rows:
            if r['split']=='test' and r['label']==1:r['score']=.05
        p=fit_profile(rows,.01,'f','zh','academic','document')
        self.assertTrue(p['validated_low_fpr'])
        self.assertEqual(p['validation']['recall'],0)
        self.assertFalse(profile_applies(p,'f','zh','academic','document')[0])
    def test_domain_terms_and_real_academic_limitations_are_not_style_convictions(self):
        clues=style_clues('协同创新是本研究的研究对象。由于采用截面数据，不能据此推断因果关系。')
        self.assertEqual(clues['authorship_score'],None)
        self.assertFalse(clues['chat_residue'])

if __name__=='__main__':unittest.main(verbosity=2)
