"""Build a static, inspectable Lab demo. No backend/model execution or publication."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def build(out,root=ROOT):
    root=Path(root).resolve();out=Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('site output must be absent or empty')
    paths=['demo/index.html','README.md','LICENSE',
           'artifacts/rc1/research/normal/index.html','artifacts/rc1/research/normal/result.json',
           'artifacts/rc1/research/normal/frozen_selection.json','artifacts/rc1/research/normal/field/workflow.json',
           'artifacts/rc1/label-visibility/index.html','artifacts/rc1/label-visibility/result.json',
           'artifacts/rc1/field-tools/transcript.json','artifacts/rc1/field-tools/evaluation.json']
    for directory in ['artifacts/rc1/research/normal','artifacts/rc1/label-visibility','artifacts/rc1/field-tools',
                      'artifacts/rc1/external-credit','artifacts/rc1/selective-maturity','artifacts/rc1/incremental-fields']:
        paths.extend(p.relative_to(root).as_posix() for p in (root/directory).rglob('*') if p.is_file())
    paths.extend(['artifacts/rc1/seed-summary.json','artifacts/rc1/seed-20261018/result.json'])
    paths.extend(p.relative_to(root).as_posix() for p in (root/'docs').glob('*.md')
                 if p.name.startswith('RC1_') or p.name in ['INTERVIEW_GUIDE.md','GITHUB_FIRST.md','licenses.md'])
    paths.extend(p.relative_to(root).as_posix() for p in (root/'docs').glob('RC1_*.json'))
    entries={}
    for name in sorted(set(paths)):
        source=root/name
        if not source.is_file() or source.is_symlink():
            raise ValueError('nonregular/missing site asset: '+name)
        source.resolve().relative_to(root)
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        entries[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    home=re.sub(r'''(href=["'])\.\./''',r'\1',(root/'demo/index.html').read_text())
    (out/'index.html').write_text(home,encoding='utf-8')
    entries['index.html']=hashlib.sha256((out/'index.html').read_bytes()).hexdigest()
    (out/'.nojekyll').write_text('')
    commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    receipt=dict(commit=commit,static_only=True,backend=False,llm_execution=False,files_sha256=entries)
    (out/'site-provenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=build(args.out);print(json.dumps({'commit':result['commit'],'assets':len(result['files_sha256']),'static_only':True}))
