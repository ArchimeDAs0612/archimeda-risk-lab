"""Maintenance must preserve published navigation and fail closed on new history."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from urllib.parse import unquote

from scripts.check_scope import changed_paths, requires_research
from scripts.prepare_release import candidate_files

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('incremental_audit', ROOT/'scripts/audit_release.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class MaintenanceTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def initialize(self, root):
        self.git(root, 'init', '-q')
        self.git(root, 'config', 'user.name', 'Fixture')
        self.git(root, 'config', 'user.email', 'fixture@example.invalid')
        (root/'README.md').write_text('safe reviewed fixture')
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'reviewed baseline')
        return self.git(root, 'rev-parse', 'HEAD')

    def test_new_secret_deleted_later_still_blocks_incremental_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = self.initialize(root)
            secret = 'gh' + 'p_' + 'x'*40
            (root/'removed.txt').write_text(secret)
            self.git(root, 'add', '.')
            self.git(root, 'commit', '-qm', 'unsafe new content')
            unsafe = self.git(root, 'rev-parse', 'HEAD')
            self.git(root, 'rm', '-q', 'removed.txt')
            self.git(root, 'commit', '-qm', 'remove content')
            receipt = audit.audit(root, base=base)
            self.assertFalse(receipt['release_ready'])
            self.assertEqual(receipt['git_commits_checked'], 2)
            self.assertIn({'file': 'history:'+unsafe+':removed.txt', 'reason': 'recognizable_token'}, receipt['findings'])
            self.assertNotIn(secret, json.dumps(receipt))

    def test_new_tracked_private_directory_and_symlink_not_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = self.initialize(root)
            (root/'.lab-run').mkdir()
            (root/'.lab-run/state.txt').write_text('gh'+'p_'+'x'*40)
            (root/'link').symlink_to('README.md')
            self.git(root, 'add', '.')
            receipt = audit.audit(root, base=base)
            self.assertFalse(receipt['release_ready'])
            reasons = {x['reason'] for x in receipt['findings']}
            self.assertTrue({'recognizable_token', 'symlink_requires_removal'} <= reasons)

    def test_unknown_or_divergent_baseline_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.initialize(root)
            self.git(root, 'checkout', '-qb', 'other')
            (root/'other.md').write_text('other')
            self.git(root, 'add', '.'); self.git(root, 'commit', '-qm', 'other branch')
            other = self.git(root, 'rev-parse', 'HEAD')
            self.git(root, 'checkout', '-q', '-')
            for base in ['f'*40, other]:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = audit.main(['--root', str(root), '--base', base])
                self.assertEqual(status, 1)
                self.assertFalse(json.loads(output.getvalue())['release_ready'])
                self.assertNotIn(str(root), output.getvalue())

    def test_safe_increment_does_not_repeat_reviewed_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = self.initialize(root)
            (root/'README.md').write_text('changed safe explanation')
            self.git(root, 'add', '.'); self.git(root, 'commit', '-qm', 'explanation')
            receipt = audit.audit(root, base=base)
            self.assertTrue(receipt['release_ready'])
            self.assertEqual(receipt['mode'], 'incremental')
            self.assertEqual(receipt['reviewed_base'], base)
            self.assertEqual(receipt['git_commits_checked'], 1)
            self.assertEqual(receipt['files_checked'], 1)

    def test_reverted_research_changes_are_not_misclassified_as_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); base = self.initialize(root)
            (root/'risklab').mkdir(); (root/'risklab/new.py').write_text('synthetic = True')
            self.git(root, 'add', '.'); self.git(root, 'commit', '-qm', 'research change')
            self.git(root, 'rm', '-q', 'risklab/new.py'); self.git(root, 'commit', '-qm', 'revert')
            self.assertTrue(requires_research(changed_paths(root, base)))

    def test_unknown_paths_require_research_while_known_maintenance_reuses_evidence(self):
        self.assertFalse(requires_research(['README.md', 'studies/payment-cases.md', 'scripts/audit_release.py']))
        for path in ['risklab/models.py', 'config/experiment.json', 'requirements-lock.txt',
                     'tests/test_research_models.py', 'scripts/unknown.py', 'docs/new.py', 'docs/RC1_STUDY_PLAN.json', 'LICENSE', 'artifacts/rc1/result.json']:
            self.assertTrue(requires_research([path]), path)

    def test_reader_links_resolve_inside_public_allowlist(self):
        public = set(candidate_files(ROOT))
        docs = ['README.md', 'AGENTS.md', 'CHECKPOINT.md', 'docs/GITHUB_FIRST.md', 'docs/PUBLICATION_STATUS.md']
        docs += sorted(p.relative_to(ROOT).as_posix() for p in (ROOT/'studies').glob('*.md'))
        self.assertEqual(len([p for p in docs if p.startswith('studies/')]), 6)
        for name in docs:
            self.assertIn(name, public)
            for url in re.findall(r'\[[^\]]*\]\(([^)]+)\)', (ROOT/name).read_text()):
                if url.startswith(('https://', 'http://', '#')):
                    continue
                target = ((ROOT/name).parent/unquote(url.split('#')[0])).resolve()
                relative = target.relative_to(ROOT).as_posix()
                self.assertTrue(relative in public or (target.is_dir() and any(p.startswith(relative+'/') for p in public)), (name, url))
