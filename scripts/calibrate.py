"""Fit on a declared calibration split, evaluate once on a disjoint held-out test split."""
import argparse,json
from pathlib import Path
from audit_core import fit_profile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--language',required=True);parser.add_argument('--domain',required=True)
    parser.add_argument('--unit',choices=['document','window'],required=True)
    parser.add_argument('--target-fpr',type=float,default=.01);args=parser.parse_args()
    rows=[json.loads(line) for line in args.input.read_text(encoding='utf-8').splitlines() if line.strip()]
    identities={r.get('fingerprint') for r in rows}
    if len(identities)!=1 or None in identities:raise ValueError('One complete pipeline fingerprint required for all rows')
    profile=fit_profile(rows,args.target_fpr,identities.pop(),args.language,args.domain,args.unit)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(profile,ensure_ascii=True))

if __name__=='__main__':main()
