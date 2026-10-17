import copy
import json
from pathlib import Path
import tempfile
import unittest
from risklab.study_contracts import workspace_path, bounded_integer, credit_config, label_config


class StudyContractTests(unittest.TestCase):
    def test_workspace_escape_absolute_parent_and_symlink(self):
        with tempfile.TemporaryDirectory() as outer:
            root=Path(outer)/'workspace';root.mkdir()
            outside=Path(outer)/'private';outside.write_text('unrelated')
            (root/'link').symlink_to(outside)
            self.assertEqual(workspace_path(root/'runs'/'new', root), (root/'runs'/'new').resolve())
            for p in [root/'..'/'private', outside, root/'link', root]:
                with self.assertRaises(ValueError): workspace_path(p,root)

    def test_repeat_limits_reject_instead_of_silently_lowering(self):
        for value in [True, -1, 0, 1001, 2.5, '300', float('inf')]:
            with self.assertRaises(ValueError): bounded_integer(value,'repeats',1,1000)
        self.assertEqual(bounded_integer(300,'repeats',1,1000),300)

    def test_prespecified_config_accepted_bad_budget_rejected(self):
        root=Path(__file__).resolve().parents[1]
        credit=json.loads((root/'config/credit_protocol.json').read_text())
        labels=json.loads((root/'config/label_protocol.json').read_text())
        credit_config(credit);label_config(labels)
        for source,validator,key in [(credit,credit_config,'bootstrap_repeats'),(labels,label_config,'orders')]:
            bad=copy.deepcopy(source);bad[key]=1000000000
            with self.assertRaises(ValueError):validator(bad)
        bad=copy.deepcopy(labels);bad['select_start_day']=1
        with self.assertRaises(ValueError):label_config(bad)


if __name__=='__main__':unittest.main()
