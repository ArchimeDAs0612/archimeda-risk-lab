import json,re,tempfile,unittest
from pathlib import Path
import pandas as pd
from risklab.research import run_research
from risklab.field_intelligence import run_change
from risklab.generate import ORIGIN,DAY
from test_chain import config

class ResearchChainTests(unittest.TestCase):
    def test_end_to_end_repair_and_final_label_isolation_with_real_workbench(self):
        c=config();c['forest_trees']=10
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);normal=run_research(c,root/'normal');repair=run_research(c,root/'repair')
            self.assertEqual(normal['frozen_selection'],repair['frozen_selection'])
            self.assertEqual(normal['models'],repair['models']);self.assertEqual(normal['patterns'],repair['patterns'])
            html=(root/'normal/index.html').read_text();data=json.loads(re.search(r'<script id="research-data" type="application/json">(.*?)</script>',html,re.S).group(1))
            self.assertEqual(len(data['events']),len(pd.read_csv(root/'normal/samples.csv')))
            self.assertIn('run-policy',html);self.assertIn('field-change',html)
            labels=pd.read_csv(root/'normal/data/labels.csv',float_precision='round_trip');events=pd.read_csv(root/'normal/data/events.csv',float_precision='round_trip')
            ids=set(events.loc[events.decision_ts>=ORIGIN+c['test_start_day']*DAY,'event_id']);mask=labels.event_id.isin(ids)
            labels.loc[mask,'risk_label']=1-labels.loc[mask,'risk_label'];labels.to_csv(root/'normal/data/labels.csv',index=False)
            changed=run_research(c,root/'changed',data_dir=root/'normal/data')
            self.assertEqual(normal['frozen_selection'],changed['frozen_selection'])
            self.assertNotEqual(normal['models']['comparison']['raw_lr']['test']['ap'],changed['models']['comparison']['raw_lr']['test']['ap'])
    def test_enriched_bad_inputs_never_train(self):
        c=config();c['forest_trees']=10
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ['duplicate','late_tool','malformed_context','field_invalidation','future','missing_time','source_binding','cross_event']:
                with self.subTest(kind=kind):
                    out=Path(tmp)/kind;r=run_research(c,out,injection=kind)
                    self.assertEqual(r['admission']['evidence_admission'],'BLOCKED');self.assertIsNone(r['model_comparison'])
                    self.assertEqual(r['candidate_verdict'],'NOT_EVALUATED');self.assertFalse((out/'frozen_selection.json').exists())
    def test_roundtrip_field_tool_output_restricts_actual_research(self):
        c=config();c['forest_trees']=10
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run_research(c,root/'normal')
            sample=pd.read_csv(root/'normal/samples.csv',float_precision='round_trip');registry=json.loads((root/'normal/field/registry.json').read_text())
            disabled,record=run_change(registry,{'operation':'disable','field':'linked_device_id'},sample)
            self.assertEqual(record['status'],'CANDIDATE_SAVED')
            blocked=run_research(c,root/'blocked',data_dir=root/'normal/data',field_registry=disabled)
            self.assertFalse(blocked['admission']['allow_model']);self.assertFalse((root/'blocked/frozen_selection.json').exists())
            self.assertIn('DISABLED_PARENT',[x['code'] for x in blocked['admission']['findings']])
    def test_untrusted_script_text_cannot_break_embedded_json(self):
        c=config();c['forest_trees']=10
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run_research(c,root/'normal')
            events=pd.read_csv(root/'normal/data/events.csv',float_precision='round_trip')
            marker='</script><script>window.bad=true</script>'
            context=json.loads(events.loc[0,'context_json']);context['client']['os']=marker;events.loc[0,'context_json']=json.dumps(context)
            events.to_csv(root/'normal/data/events.csv',index=False)
            run_research(c,root/'untrusted',data_dir=root/'normal/data')
            html=(root/'untrusted/index.html').read_text();self.assertNotIn(marker,html)
            data=json.loads(re.search(r'<script id="research-data" type="application/json">(.*?)</script>',html,re.S).group(1))
            self.assertEqual(json.loads(data['events'][0]['context_json'])['client']['os'],marker)
