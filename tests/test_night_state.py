"""Recovery checks use isolated temporary state; never interrupt running processes."""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from scripts.night_state import next_action, save


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/'state.json'
        self.now = datetime.fromisoformat('2026-10-16T04:00:00+08:00')
        self.state = dict(run_id='fixture', workspace=str(self.root),
                          started_at='2026-10-16T03:13:40+08:00', deadline_at='2026-10-16T11:13:40+08:00',
                          status='RUNNING', stop_marker=False, active_jobs=[], last_valid={'version':'v0.1'},
                          items=[dict(id='N1',status='DONE',depends_on=[]),
                                 dict(id='N2',status='READY_TO_RESUME',depends_on=['N1'],next_action='validate')])
        save(self.path,self.state)

    def test_readonly_resume_skips_done_and_preserves_last_valid(self):
        before = self.path.read_bytes()
        self.assertEqual(next_action(self.path,self.root,self.now)['item'],'N2')
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(json.loads(before)['last_valid'],{'version':'v0.1'})

    def test_atomic_previous_snapshot_and_deadline_immutable(self):
        changed = copy.deepcopy(self.state); changed['status']='READY_TO_RESUME'
        save(self.path,changed)
        self.assertEqual(json.loads(self.path.with_suffix('.previous.json').read_text()),self.state)
        changed['deadline_at']='2026-10-17T11:13:40+08:00'
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'immutable'):
            save(self.path,changed)
        self.assertEqual(self.path.read_bytes(),before)

    def test_stop_deadline_active_jobs_and_workspace_guards(self):
        self.assertEqual(next_action(self.path,self.root,datetime.fromisoformat(self.state['deadline_at']))['reason'],'deadline')
        for field,value,expected in [('stop_marker',True,'STOP'),('status','DONE','STOP'),
                                     ('active_jobs',[{'pid':123,'identity':'fixture-only'}],'INSPECT_SAVED_JOBS')]:
            altered = copy.deepcopy(self.state); altered[field]=value
            save(self.path,altered)
            self.assertEqual(next_action(self.path,self.root,self.now)['action'],expected)
        with self.assertRaisesRegex(ValueError,'workspace mismatch'):
            next_action(self.path,self.root/'other',self.now)
