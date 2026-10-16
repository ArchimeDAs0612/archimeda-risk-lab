import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts.verify_publication import judge
from scripts.build_pages import build


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.sha='a'*40
        self.repo=dict(private=False,full_name='Owner/Lab',default_branch='main',html_url='https://github.com/Owner/Lab')
        self.head={'object':{'sha':self.sha}}
        self.run=dict(head_sha=self.sha,head_branch='main',path='.github/workflows/check.yml',status='completed',conclusion='success',run_number=1)

    def result(self,run=None,pages=None):
        return judge(self.repo,self.head,{'workflow_runs':[self.run if run is None else run]},self.sha,'owner/lab',pages)

    def test_public_exact_commit_and_ci_required_for_delivery(self):
        self.assertEqual(self.result()['status'],'DELIVERED / PUBLISHED')
        self.repo['private']=True
        self.assertEqual(self.result()['status'],'LOCAL COMPLETE / PUBLICATION BLOCKED')
        self.repo['private']=False;self.head['object']['sha']='b'*40
        self.assertFalse(self.result()['checks']['remote_commit_matches'])

    def test_success_on_other_commit_branch_or_workflow_cannot_count(self):
        for key,value in [('head_sha','b'*40),('head_branch','feature'),('path','.github/workflows/other.yml'),('conclusion','failure'),('status','in_progress')]:
            run=dict(self.run,**{key:value})
            self.assertFalse(self.result(run)['checks']['same_commit_ci_success'])

    def test_new_failed_run_and_stale_pages_prevent_false_delivery(self):
        failed=dict(self.run,run_number=2,conclusion='failure')
        result=judge(self.repo,self.head,{'workflow_runs':[self.run,failed]},self.sha,'owner/lab')
        self.assertFalse(result['checks']['same_commit_ci_success'])
        pages=dict(commit='b'*40,static_only=True,backend=False,http_verified=True)
        self.assertFalse(self.result(pages=pages)['checks']['pages_commit_matches'])

    def test_static_build_excludes_private_state_and_tracks_actual_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            required=['demo/index.html','README.md','LICENSE','artifacts/rc1/seed-summary.json','artifacts/rc1/seed-20261018/result.json',
                      'artifacts/rc1/research/normal/index.html','artifacts/rc1/research/normal/result.json',
                      'artifacts/rc1/research/normal/frozen_selection.json','artifacts/rc1/research/normal/field/workflow.json',
                      'artifacts/rc1/label-visibility/index.html','artifacts/rc1/label-visibility/result.json',
                      'artifacts/rc1/field-tools/transcript.json','artifacts/rc1/field-tools/evaluation.json']
            for name in required:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('<a href="../README.md">Risk Decision Lab</a>')
            (root/'docs').mkdir()
            private=root/'.lab-run/private.json';private.parent.mkdir();private.write_text('private fixture only')
            with patch('scripts.build_pages.subprocess.check_output',return_value='a'*40+'\n'):
                result=build(Path(tmp)/'site',root)
            self.assertEqual(result['commit'],'a'*40)
            self.assertNotIn('.lab-run/private.json',result['files_sha256'])
            self.assertFalse((Path(tmp)/'site/.lab-run').exists())
            self.assertIn('href="README.md"',(Path(tmp)/'site/index.html').read_text())
            self.assertTrue(result['static_only']);self.assertFalse(result['backend'])
