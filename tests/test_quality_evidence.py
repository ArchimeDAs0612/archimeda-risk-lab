"""A green security status must not hide drift, scan errors or unreviewed risk."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.quality_evidence import summarize


class QualityEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        (root/'risklab').mkdir(); (root/'scripts').mkdir()
        (root/'risklab/a.py').write_text('value = 1\n')
        coverage = dict(files={'risklab/a.py':{}}, meta={'version':'fixture'},
                        totals=dict(num_statements=1,covered_lines=1,missing_lines=0,
                                    num_branches=0,covered_branches=0,percent_covered=100))
        bandit = dict(errors=[],metrics={'risklab/a.py':{},'_totals':{}},results=[])
        return coverage, bandit

    def test_missing_module_or_scan_error_prevents_green_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); coverage, bandit = self.fixture(root)
            bandit['errors'] = ['parser error']
            with self.assertRaises(ValueError): summarize(root,coverage,bandit,{'findings':[]})
            bandit['errors'] = []
            (root/'risklab/unexecuted.py').write_text('value = 2\n')
            with self.assertRaises(ValueError): summarize(root,coverage,bandit,{'findings':[]})

    def test_review_is_bound_to_file_content_and_cannot_accept_high_severity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); coverage, bandit = self.fixture(root)
            bandit['results'] = [dict(filename='risklab/a.py',test_id='B000',line_number=1,
                                      issue_severity='LOW',issue_text='fixture risk')]
            review = {'findings':[dict(file='risklab/a.py',test_id='B000',line=1,
                                      sha256=hashlib.sha256((root/'risklab/a.py').read_bytes()).hexdigest(),
                                      rationale='fixture limited review')]}
            self.assertFalse(summarize(root,coverage,bandit,{'findings':[]})['security_gate_passed'])
            self.assertTrue(summarize(root,coverage,bandit,review)['security_gate_passed'])
            bandit['results'][0]['issue_severity'] = 'HIGH'
            self.assertFalse(summarize(root,coverage,bandit,review)['security_gate_passed'])
            bandit['results'][0]['issue_severity'] = 'LOW'
            (root/'risklab/a.py').write_text('changed = 3\n')
            self.assertFalse(summarize(root,coverage,bandit,review)['security_gate_passed'])
