"""Exact-commit delivery verification plus anonymous public access. Read-only."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request


def judge(repo,head,runs,expected,repository,pages=None):
    checks={'public_repository':repo.get('private') is False,
            'correct_repository':repo.get('full_name','').lower()==repository.lower(),
            'default_main':repo.get('default_branch')=='main',
            'remote_commit_matches':head.get('object',{}).get('sha')==expected}
    candidates=[r for r in runs.get('workflow_runs',[]) if r.get('head_sha')==expected
                and r.get('head_branch')=='main' and r.get('path')=='.github/workflows/check.yml']
    latest=max(candidates,key=lambda r:(r.get('run_number',0),r.get('run_attempt',1)),default={})
    checks['same_commit_ci_success']=latest.get('status')=='completed' and latest.get('conclusion')=='success'
    if pages is not None:
        checks['pages_commit_matches']=pages.get('commit')==expected
        checks['pages_static_only']=pages.get('static_only') is True and pages.get('backend') is False
        checks['pages_http_verified']=pages.get('http_verified') is True
    return dict(status='DELIVERED / PUBLISHED' if all(checks.values()) else 'LOCAL COMPLETE / PUBLICATION BLOCKED',
                checks=checks,repository=repo.get('html_url'),commit=expected,ci_url=latest.get('html_url'),
                scope='GitHub metadata plus independent anonymous public HTTP; research quality governed by experiment verification')


def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'risk-decision-lab-publication-verifier','Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=30) as response:
        return response.read(),response.headers.get('Content-Type','')


def api_json(path,sources):
    """Only a proven shared anonymous quota limit permits authorized CLI reads.

    No tokens are read/printed here; gh uses the user's existing authentication.
    Permission errors, arbitrary 403s and missing resources remain failures.
    """
    try:
        value=json.loads(fetch('https://api.github.com/'+path)[0])
        sources.add('anonymous_api')
        return value
    except urllib.error.HTTPError as error:
        if error.code!=403 or error.headers.get('X-RateLimit-Remaining')!='0':
            raise
        value=json.loads(subprocess.check_output(['gh','api',path],text=True,timeout=30))
        sources.add('authorized_cli_after_confirmed_anonymous_rate_limit')
        return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',default='ArchimeDAs0612/archimeda-risk-lab')
    parser.add_argument('--expected-commit',required=True)
    parser.add_argument('--pages-url')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repository) or not re.fullmatch(r'[0-9a-f]{40}',args.expected_commit):
        parser.error('invalid repository or full commit SHA')
    base='repos/'+args.repository
    load=lambda url:json.loads(fetch(url)[0])
    sources=set()
    try:
        repo=api_json(base,sources);head=api_json(base+'/git/ref/heads/main',sources)
        runs=api_json(base+'/actions/runs?head_sha='+args.expected_commit+'&per_page=30',sources)
        # No Authorization/cookie/CLI credential is used for public HTML access.
        public_url='https://github.com/'+args.repository
        request=urllib.request.Request(public_url,headers={'User-Agent':'risk-decision-lab-public-access-check'})
        with urllib.request.urlopen(request,timeout=30) as response:
            public_http=response.status==200 and response.geturl().rstrip('/').lower()==public_url.lower()
        pages=None
        if args.pages_url:
            if not args.pages_url.startswith('https://'):
                raise ValueError('Pages requires HTTPS')
            url=args.pages_url.rstrip('/')
            pages=load(url+'/site-provenance.json')
            body,kind=fetch(url+'/')
            pages['http_verified']='text/html' in kind and b'archimeda risk lab' in body.lower()
        result=judge(repo,head,runs,args.expected_commit,args.repository,pages)
        result['checks']['anonymous_public_repository_http']=public_http
        result['status']='DELIVERED / PUBLISHED' if all(result['checks'].values()) else 'LOCAL COMPLETE / PUBLICATION BLOCKED'
        result['anonymous_public_access']=public_http
        result['metadata_sources']=sorted(sources)
    except Exception as exc:
        result=dict(status='LOCAL COMPLETE / PUBLICATION BLOCKED',error=type(exc).__name__,metadata_sources=sorted(sources))
    text=json.dumps(result,indent=2)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(text)
    print(text,end='')
    return 0 if result['status']=='DELIVERED / PUBLISHED' else 1


if __name__=='__main__':
    raise SystemExit(main())
