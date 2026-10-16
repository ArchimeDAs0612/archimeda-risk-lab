"""Explicit source/evidence allowlist for a clean, locally reviewable RC.

Never copies Git metadata, credentials, private state or developer logs. This
does not publish; run audit_release.py against the candidate and Git history.
"""
import argparse
import hashlib
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
TEXT={'.py','.sql','.json','.csv','.html','.md','.txt','.js','.cjs','.css','.yml','.yaml'}


def candidate_files(root):
    root=Path(root)
    names={'.gitignore','README.md','CHECKPOINT.md','CHANGELOG.md','LICENSE','pyproject.toml',
           'requirements.txt','requirements-lock.txt','package.json'}
    for directory in ['risklab','config','examples','scripts','tests','.github',
                      'artifacts/rc1','artifacts/reference','artifacts/baseline-v0.1.1']:
        for path in (root/directory).rglob('*'):
            if path.is_file() and path.suffix in TEXT and '__pycache__' not in path.parts:
                relative=path.relative_to(root)
                # Preserve the actual failure results; avoid repeated raw data.
                if directory=='artifacts/rc1' and 'data' in relative.parts and any(p.startswith('bad_') or p=='disabled_downstream' for p in relative.parts):
                    continue
                names.add(relative.as_posix())
    for pattern in ['RC1_*','INTERVIEW_GUIDE.md','licenses.md','third-party-licenses.txt','playwright-dev-licenses.txt']:
        names.update(p.relative_to(root).as_posix() for p in (root/'docs').glob(pattern) if p.is_file())
    names.add('demo/index.html')
    for name in names:
        path=root/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('missing/nonregular release input: '+name)
    return sorted(names)


def prepare(out):
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('release output must be absent or empty')
    lines=[]
    for name in candidate_files(ROOT):
        source=ROOT/name;target=out/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        lines.append(hashlib.sha256(source.read_bytes()).hexdigest()+'  '+name+'\n')
    (out/'release-rc1-manifest.sha256').write_text(''.join(lines),encoding='utf-8')
    return len(lines)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();print(prepare(args.out))
