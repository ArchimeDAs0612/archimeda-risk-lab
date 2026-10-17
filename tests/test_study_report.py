import tempfile
import unittest
from pathlib import Path
from risklab.study_report import render_study


class StudyReportTests(unittest.TestCase):
    def test_report_destination_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            output=Path(elsewhere)/'index.html'
            with self.assertRaises(ValueError):render_study({},'fields',output)
            self.assertFalse(output.exists())
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as inside:
            root=Path(inside)
            with tempfile.TemporaryDirectory() as elsewhere:
                (root/'link').symlink_to(elsewhere,target_is_directory=True)
                with self.assertRaises(ValueError):render_study({},'fields',root/'link/index.html')

    def test_untrusted_evidence_cannot_close_script_container(self):
        value='</script><script>attack()</script>'
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as inside:
            output=Path(inside)/'index.html';render_study({'evidence':value},'fields',output)
            text=output.read_text()
            self.assertNotIn(value,text)
            self.assertIn('\\u003c/script\\u003e',text)


if __name__=='__main__':unittest.main()
