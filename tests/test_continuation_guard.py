"""Isolated recovery fixtures; never stop or relaunch the actual research chat."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.continuation_guard import Busy, decide, digest, exclusive, probe
from scripts.night_state import save


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'lab'
        self.root.mkdir()
        self.path = self.root / 'state.json'
        self.now = datetime.now(timezone.utc)
        self.state = dict(run_id='isolated-fixture', workspace=str(self.root),
                          started_at=(self.now - timedelta(hours=1)).isoformat(),
                          deadline_at=(self.now + timedelta(hours=5)).isoformat(),
                          status='IDLE', active_jobs=[], retry_counts={},
                          items=[dict(id='N6', status='DONE', depends_on=[]),
                                 dict(id='N7', status='READY_TO_RESUME', depends_on=['N6'],
                                      next_action='evaluate frozen candidate'),
                                 dict(id='N9', status='READY_TO_RESUME', depends_on=['N6'],
                                      next_action='validate field evidence')])
        self.observation = dict(source='native_task_inspection', observed_at=self.now.isoformat(),
                                inventory_complete=True, other_writers='NONE', original_execution='STOPPED')
        self.evidence = {'valid': True}

    def decision(self):
        return decide(self.state, self.root, self.observation, self.now, self.evidence)

    def test_running_original_does_not_restart(self):
        self.observation['original_execution'] = 'RUNNING'
        self.assertEqual(self.decision()['action'], 'SKIP')

    def test_unknown_or_partial_inventory_fails_closed(self):
        for key, val in [('original_execution', 'UNKNOWN'), ('other_writers', 'UNKNOWN'),
                         ('inventory_complete', False)]:
            with self.subTest(key=key):
                changed = dict(self.observation, **{key: val})
                self.assertEqual(decide(self.state, self.root, changed, self.now, self.evidence)['action'], 'SKIP')

    def test_stale_future_missing_and_wrong_source_observations(self):
        for delta in [-61, 1]:
            self.observation['observed_at'] = (self.now + timedelta(seconds=delta)).isoformat()
            self.assertEqual(self.decision()['action'], 'SKIP')
        self.observation['observed_at'] = self.now.isoformat()
        self.observation['source'] = 'pid_age_guess'
        self.assertEqual(self.decision()['action'], 'SKIP')
        self.assertEqual(decide(self.state, self.root, now=self.now)['action'], 'SKIP')

    def test_completed_readonly_and_disables_schedule(self):
        for item in self.state['items']:
            item['status'] = 'DONE'
        save(self.path, self.state)
        before = self.path.read_bytes()
        result = self.decision()
        self.assertEqual(result['action'], 'COMPLETED')
        self.assertTrue(result['disable_schedule'])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / '.lab-run').exists())

    def test_completion_requires_evidence_not_folders_or_status(self):
        self.state['status'] = 'DONE'
        self.assertEqual(self.decision()['action'], 'SKIP')
        for item in self.state['items']:
            item['status'] = 'DONE'
        self.evidence['valid'] = False
        self.assertEqual(self.decision()['action'], 'SKIP')

    def test_exact_deadline_stops_and_is_not_reset(self):
        deadline = self.state['deadline_at']
        save(self.path, self.state)
        changed = copy.deepcopy(self.state)
        changed['deadline_at'] = (self.now + timedelta(hours=6)).isoformat()
        with self.assertRaisesRegex(ValueError, 'immutable'):
            save(self.path, changed)
        result = decide(self.state, self.root, self.observation,
                        datetime.fromisoformat(deadline), self.evidence)
        self.assertEqual(result['action'], 'STOP')
        self.assertEqual(json.loads(self.path.read_text())['deadline_at'], deadline)

    def test_saved_jobs_never_assumed_dead_from_age(self):
        self.state['active_jobs'] = [{'pid': 99999999, 'started_at': '2000-01-01T00:00:00Z'}]
        self.assertEqual(self.decision()['action'], 'SKIP')

    def test_blocked_or_unauthorized_branch_yields_independent_work(self):
        self.state['items'][1]['status'] = 'BLOCKED'
        self.assertEqual(self.decision()['milestone'], 'N9')
        self.state['items'][1]['status'] = 'READY_TO_RESUME'
        self.state['items'][1]['requires_authorization'] = True
        self.assertEqual(self.decision()['milestone'], 'N9')

    def test_no_dependency_bypass_or_repeated_failure(self):
        self.state['items'][1]['depends_on'] = ['unknown']
        self.state['retry_counts']['N9'] = 2
        self.assertEqual(self.decision()['action'], 'BLOCKED')

    def test_manual_stop(self):
        self.state['stop_marker'] = True
        self.assertEqual(self.decision()['action'], 'STOP')

    def test_resume_descriptor_keeps_exact_action_budget_and_no_writes(self):
        save(self.path, self.state)
        before = self.path.read_bytes()
        result = self.decision()
        self.assertEqual(result['action'], 'READY')
        self.assertEqual(result['next'], 'evaluate frozen candidate')
        self.assertEqual(result['deadline_at'], self.state['deadline_at'])
        self.assertTrue(result['requires_held_lock'])
        self.assertEqual(result['mode'], 'Checkpoint-based continuation')
        self.assertEqual(self.path.read_bytes(), before)

    def test_workspace_mismatch_and_duplicate_milestones(self):
        with self.assertRaisesRegex(ValueError, 'workspace mismatch'):
            decide(self.state, self.root / 'other')
        self.state['items'].append(self.state['items'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.decision()

    def test_cross_process_mutex_and_exception_release(self):
        code = ('from scripts.continuation_guard import exclusive, Busy\n'
                'import sys\n'
                'try:\n'
                ' with exclusive(sys.argv[1], "child-fixture"):\n'
                '  print("ACQUIRED")\n'
                'except Busy:\n'
                ' print("BUSY")\n')
        cwd = Path(__file__).resolve().parents[1]
        def child():
            return subprocess.run([sys.executable, '-c', code, str(self.root)], cwd=cwd,
                                  capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        with self.assertRaisesRegex(RuntimeError, 'fixture interruption'):
            with exclusive(self.root, 'parent-fixture') as identity:
                self.assertEqual(identity['source'], 'POSIX flock')
                self.assertEqual(child(), 'BUSY')
                raise RuntimeError('fixture interruption')
        self.assertEqual(child(), 'ACQUIRED')
        # Unlocked stale metadata never needs deletion/age-based stealing.
        self.assertTrue((self.root / '.lab-run/writer.lock').exists())

    def test_probe_real_hashes_corruption_and_readonly(self):
        artifact = self.root / 'accepted'
        artifact.mkdir()
        (artifact / 'result.json').write_text('{"fixture": true}')
        (self.root / 'accepted-code.py').write_text('# accepted fixture\n')
        manifest = self.root / 'release-manifest.sha256'
        manifest.write_text(digest(self.root / 'accepted-code.py') + '  accepted-code.py\n')
        archive = self.root.parent / 'accepted.zip'
        archive.write_bytes(b'fixture-only release bytes')
        self.state['last_valid'] = dict(artifact='accepted',
            result_sha256=digest(artifact / 'result.json'), code_sha256={'accepted-code.py': digest(self.root/'accepted-code.py')},
            ui_sha256={}, manifest_sha256=digest(manifest), archive='accepted.zip', archive_sha256=digest(archive))
        for item in self.state['items']:
            item['status'] = 'DONE'
        save(self.path, self.state)
        before = self.path.read_bytes()
        self.assertEqual(probe(self.path, self.root)['decision']['action'], 'COMPLETED')
        self.assertEqual(self.path.read_bytes(), before)
        (self.root / 'accepted-code.py').write_text('# corrupted fixture\n')
        self.assertEqual(probe(self.path, self.root)['decision']['action'], 'SKIP')

    def test_abnormal_fixture_exit_releases_os_lock(self):
        code = ('from scripts.continuation_guard import exclusive\nimport os, sys\n'
                'with exclusive(sys.argv[1], "crash-fixture"):\n os._exit(7)\n')
        child = subprocess.run([sys.executable, '-c', code, str(self.root)],
                               cwd=Path(__file__).resolve().parents[1], timeout=10)
        self.assertEqual(child.returncode, 7)
        with exclusive(self.root, 'recovery-fixture') as identity:
            self.assertEqual(identity['execution_id'], 'recovery-fixture')


if __name__ == '__main__':
    unittest.main()
