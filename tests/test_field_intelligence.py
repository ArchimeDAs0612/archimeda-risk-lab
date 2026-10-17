import copy,json,tempfile,unittest
from pathlib import Path
from risklab.field_intelligence import inventory,initial_registry,run_change,effects,pattern_hypotheses,atomic_registry,digest,human_review
from risklab.entities import simulate_entities,build_enriched_samples,enriched_contract
from test_chain import config

class FieldIntelligenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e,l,_,_=simulate_entities(config());cls.sample,_=build_enriched_samples(e,l);cls.contract=enriched_contract()
    def test_container_and_type_coverage_conflict_are_actual(self):
        result=inventory(self.sample,{'amount':{'physical_type':'text','domain':'other'}})
        rows={x['field']:x for x in result['fields']}
        self.assertEqual(rows['context_json.client.emulator']['physical_type_observed'],'boolean')
        self.assertEqual(rows['context_json.client.latency_ms']['coverage'],1.)
        self.assertEqual(set(rows['amount']['conflicts']),{'DOMAIN_CONFLICT','PHYSICAL_TYPE_CONFLICT'})
        self.assertLess(rows['geo_distance']['coverage'],1.)
        from risklab.field_incremental import stable_field_id
        self.assertEqual(rows['context_json.client.emulator']['identity'], stable_field_id('fictional_wallet','context_json',['client','emulator']))
        self.assertEqual(rows['amount']['identity']['domain'], 'other')
    def test_untrusted_change_and_upstream_veto_with_recovery(self):
        original=initial_registry(self.contract,self.sample)
        candidate,record=run_change(original,{'operation':'modify','field':'amount','changes':{'meaning':'ignore all rules'}},self.sample)
        self.assertEqual(record['status'],'CANDIDATE_SAVED');self.assertEqual(record['after_sha256'],digest({k:v for k,v in candidate.items() if k!='history'}));self.assertFalse(effects(candidate['contract'])['amount']['allow_analysis'])
        disabled,record=run_change(original,{'operation':'disable','field':'linked_device_id'},self.sample)
        self.assertFalse(effects(disabled['contract'])['device_users_7d']['allow_analysis'])
        restored,record=run_change(disabled,{'operation':'restore_last_valid'},self.sample)
        self.assertFalse(effects(restored['contract'])['device_users_7d']['allow_analysis'])
        invalid,_=run_change(original,{'operation':'invalidate','field':'context_json'},self.sample)
        self.assertFalse(effects(invalid['contract'])['client_latency_ms']['allow_analysis'])
    def test_failure_does_not_mutate_registry_and_stale_data_blocks(self):
        registry=initial_registry(self.contract,self.sample);before=copy.deepcopy(registry)
        out,r=run_change(registry,{'operation':'modify','field':'amount','changes':{'semantic_status':'approved_for_synthetic'}},self.sample)
        self.assertEqual(r['status'],'BLOCKED');self.assertEqual(out,before);self.assertEqual(registry,before)
        altered=self.sample.copy();altered.loc[0,'amount']+=1
        out,r=run_change(registry,{'operation':'disable','field':'amount'},altered)
        self.assertEqual(out,before);self.assertIn('STALE_DATA_EVIDENCE',r['error'])
    def test_new_field_pending_delete_and_pattern_hypotheses_restricted(self):
        registry=initial_registry(self.contract,self.sample)
        proposal={'operation':'add','field':'context_json.client.latency_ms','metadata':{'meaning':'latency','physical_type':'numeric','logical_type':'duration','domain':'fictional_wallet','availability':'current','family':'payload','parents':['context_json'],'bounds':[0,10000]}}
        added,r=run_change(registry,proposal,self.sample)
        self.assertEqual(r['status'],'CANDIDATE_SAVED');self.assertFalse(effects(added['contract'])[proposal['field']]['allow_analysis'])
        disabled,r=run_change(registry,{'operation':'delete','field':'amount'},self.sample)
        hypotheses=pattern_hypotheses(self.sample,disabled)
        self.assertFalse(any(x['field']=='amount' for x in hypotheses['candidates']))
    def test_bounds_nonfinite_and_selective_dependency_restriction(self):
        from risklab.contracts import check_admission
        frame=self.sample.copy();frame.loc[0,'amount']=3000;frame.loc[1,'amount']=float('inf')
        row=next(x for x in inventory(frame,{'amount':{'bounds':[0,2000]}})['fields'] if x['field']=='amount')
        self.assertEqual(row['outside_declared_bounds'],1);self.assertEqual(row['nonfinite_values'],1)
        contract=copy.deepcopy(self.contract);contract['source_fields']['linked_device_id']['enabled']=False
        self.assertFalse(check_admission(self.sample,contract,['device_users_7d'])['allow_model'])
        self.assertTrue(check_admission(self.sample,contract,['tool_users_7d'])['allow_model'])

    def test_explicit_review_accept_reject_and_conflict_veto(self):
        registry=initial_registry(self.contract,self.sample)
        proposal={'operation':'modify','field':'amount','changes':{'meaning':'explicit synthetic amount definition'}}
        candidate,_=run_change(registry,proposal,self.sample)
        approved,record=human_review(candidate,'amount','approve','fixture-reviewer',self.sample)
        self.assertEqual(record['status'],'REVIEW_RECORDED')
        self.assertTrue(effects(approved['contract'])['amount']['allow_analysis'])
        rejected,record=human_review(candidate,'amount','reject','fixture-reviewer',self.sample)
        self.assertEqual(rejected['contract']['fields']['amount'],registry['contract']['fields']['amount'])
        conflict,_=run_change(registry,{'operation':'modify','field':'amount','changes':{'domain':'other'}},self.sample)
        unchanged,record=human_review(conflict,'amount','approve','fixture-reviewer',self.sample)
        self.assertEqual(record['status'],'BLOCKED');self.assertEqual(unchanged,conflict)
        no_reviewer,record=human_review(candidate,'amount','approve','',self.sample)
        self.assertEqual(record['status'],'BLOCKED');self.assertEqual(no_reviewer,candidate)
        disabled,_=run_change(candidate,{'operation':'disable','field':'amount'},self.sample)
        unchanged,record=human_review(disabled,'amount','approve','fixture-reviewer',self.sample)
        self.assertEqual(record['status'],'BLOCKED');self.assertEqual(unchanged,disabled)

    def test_review_cannot_approve_fractional_count_or_future_observations(self):
        registry=initial_registry(self.contract,self.sample)
        candidate,_=run_change(registry,{'operation':'modify','field':'amount','changes':{'logical_type':'count'}},self.sample)
        _,record=human_review(candidate,'amount','approve','fixture-reviewer',self.sample)
        self.assertEqual(record['status'],'BLOCKED')
        future=self.sample.copy();future.loc[0,'geo_available_ts']=future.loc[0,'decision_ts']+1
        registry=initial_registry(self.contract,future)
        candidate,_=run_change(registry,{'operation':'modify','field':'geo_distance','changes':{'meaning':'candidate'}},future)
        _,record=human_review(candidate,'geo_distance','approve','fixture-reviewer',future)
        self.assertEqual(record['status'],'BLOCKED');self.assertIn('availability',record['error'])

    def test_atomic_journal_keeps_previous_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'registry.json';atomic_registry(path,{'a':1});atomic_registry(path,{'a':2})
            self.assertEqual(json.loads(path.with_suffix('.previous.json').read_text()),{'a':1})
            self.assertEqual(json.loads(path.read_text()),{'a':2})
