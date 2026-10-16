import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PackagedCliTests(unittest.TestCase):
    def test_bundled_configs_match_explicit_repository_defaults(self):
        root=Path(__file__).resolve().parents[1]
        for name in ['default.json','research.json']:
            self.assertEqual(json.loads((root/'config'/name).read_text()),
                             json.loads((root/'risklab/config'/name).read_text()))

    def test_default_generation_outside_checkout_has_no_cwd_config_dependency(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,PYTHONPATH=str(root))
            result=subprocess.run([sys.executable,'-W','error','-m','risklab','generate','--out','generated'],
                cwd=tmp,env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((Path(tmp)/'generated/events.csv').is_file())
            self.assertFalse((Path(tmp)/'config').exists())
