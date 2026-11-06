"""Create ignored local model configuration from the public pinned manifest."""
import argparse,copy,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def verify_files(folder,files):
    folder=Path(folder)
    for record in files:
        path=folder/record['name'];h=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
        if h.hexdigest()!=record['sha256']:raise ValueError('Checkpoint SHA-256 mismatch: '+record['name'])

def configure(manifest,output,model_root=None,cache_dir=None,download=False):
    if model_root is not None and download:raise ValueError('--model-root and --download are alternative modes')
    data=copy.deepcopy(manifest)
    for row in data['models']:
        if model_root is not None:
            folder=Path(model_root)/row['key']
        else:
            from huggingface_hub import snapshot_download
            folder=Path(snapshot_download(repo_id=row['id'],revision=row['revision'],
                allow_patterns=[f['name'] for f in row['files']],cache_dir=str(cache_dir) if cache_dir else None,
                local_files_only=not download))
        verify_files(folder,row['files'])
        row['local_path']=str(folder.resolve())
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'assets/models.example.json')
    parser.add_argument('--output',type=Path,default=ROOT/'assets/models.local.json')
    parser.add_argument('--cache-dir',type=Path);parser.add_argument('--model-root',type=Path)
    parser.add_argument('--download',action='store_true',help='Explicitly allow official checkpoint downloads')
    args=parser.parse_args()
    data=configure(json.loads(args.manifest.read_text(encoding='utf-8')),args.output,args.model_root,args.cache_dir,args.download)
    print(json.dumps({'models':len(data['models']),'output':str(args.output),'download_allowed':args.download},ensure_ascii=True))

if __name__=='__main__':main()
