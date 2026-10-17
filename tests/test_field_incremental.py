import copy
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from risklab.data import AdmissionError
from risklab.field_intelligence import initial_registry, atomic_registry, frame_digest
from risklab.field_incremental import (stable_field_id, value_states, materialize,
                                       admitted_matrix, validate_materialization, transaction)


class IncrementalFieldTests(unittest.TestCase):
    def setup_state(self):
        frame = pd.DataFrame(dict(event_id=['a', 'b', 'c'], amount=[0., 3., 8.],
                                  velocity=[1., 2., 1.], raw_clock=[0, 1, 2]))
        def metadata(parents):
            return dict(domain='fictional_wallet', enabled=True, semantic_status='approved_for_synthetic',
                        availability='current', parents=parents, physical_type='numeric', bounds=[0, 100])
        contract = dict(domain='fictional_wallet', fields={'amount': metadata([]), 'velocity': metadata(['raw_clock'])},
                        source_fields={'raw_clock': metadata([])})
        return frame, initial_registry(contract, frame)

    def test_unit_change_blocks_actual_matrix_reuses_unaffected_and_invalidates_report(self):
        frame, registry = self.setup_state(); before = materialize(registry, frame)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'registry.json'; atomic_registry(path, registry)
            changed, _ = transaction(path, frame, 'unit', 0, {'operation':'modify', 'field':'amount', 'changes':{'unit':'cents'}}, workspace=d)
            after = materialize(changed, frame, before)
            self.assertEqual(after['fields'], materialize(changed, frame)['fields'])
            self.assertEqual(after['reused'], ['velocity'])
            self.assertIsNone(after['fields']['amount']['values'])
            self.assertFalse(validate_materialization(before, changed, frame)['report'])
            with self.assertRaises(AdmissionError): admitted_matrix(after, changed, frame, ['amount'])
            self.assertEqual(admitted_matrix(after, changed, frame, ['velocity']).velocity.tolist(), [1., 2., 1.])

    def test_idempotency_stale_writer_and_crash_recovery(self):
        frame, registry = self.setup_state()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'registry.json'; atomic_registry(path, registry)
            proposal = {'operation':'disable', 'field':'raw_clock'}
            with self.assertRaisesRegex(AdmissionError, 'INJECTED'):
                transaction(path, frame, 'first', 0, proposal, True, workspace=d)
            self.assertEqual(json.loads(path.read_text()), registry)
            changed, _ = transaction(path, frame, 'first', 0, proposal, workspace=d)
            again, receipt = transaction(path, frame, 'first', 0, proposal, workspace=d)
            self.assertEqual(changed, again); self.assertTrue(receipt['replayed'])
            with self.assertRaisesRegex(AdmissionError, 'STALE_REVISION'):
                transaction(path, frame, 'second', 0, {'operation':'disable', 'field':'amount'}, workspace=d)
            with self.assertRaisesRegex(AdmissionError, 'different content'):
                transaction(path, frame, 'first', 1, {'operation':'disable', 'field':'amount'}, workspace=d)
            self.assertEqual(json.loads(path.read_text()), changed)

    def test_domain_and_pointer_collision_protection(self):
        self.assertNotEqual(stable_field_id('wallet','amount'), stable_field_id('delivery','amount'))
        self.assertNotEqual(stable_field_id('wallet','json',['a.b']), stable_field_id('wallet','json',['a','b']))
        self.assertEqual(stable_field_id('wallet','json',['a/b','~'])['json_pointer'], '/a~1b/~0')

    def test_missing_states_are_predefined_and_zero_false_remain_observed(self):
        r = value_states([None, float('nan'), '', ' ', 'null', 0, False, True])
        self.assertEqual(r['counts'], dict(null=2, blank=2, literal_null=1, zero=1, false=1, value=1))
        self.assertEqual(r['coverage'], 3/8)
        self.assertEqual(value_states([])['status'], 'NO_SAMPLE')
        self.assertEqual(value_states([None])['status'], 'ZERO_COVERAGE')
        self.assertEqual(value_states([], applicable=False)['status'], 'NOT_APPLICABLE')
        self.assertEqual(value_states([], computed=False)['status'], 'NOT_COMPUTED')

    def test_corrupt_cache_is_recomputed_and_cannot_feed_model(self):
        frame, registry = self.setup_state(); cache = materialize(registry, frame)
        cache['fields']['amount']['values'][0] = 999
        self.assertEqual(validate_materialization(cache, registry, frame)['status'], 'INVALIDATED')
        fixed = materialize(registry, frame, cache)
        self.assertIn('amount', fixed['recomputed']); self.assertIn('velocity', fixed['reused'])
        self.assertEqual(fixed['fields'], materialize(registry, frame)['fields'])
        fixed['event_ids'] = list(reversed(fixed['event_ids']))
        with self.assertRaises(AdmissionError): admitted_matrix(fixed, registry, frame, ['amount'])

    def test_order_independence_and_evidence_drift_fail_closed(self):
        frame, registry = self.setup_state(); cache = materialize(registry, frame)
        shuffled = frame.iloc[::-1].reset_index(drop=True)
        reobserved = copy.deepcopy(registry); reobserved['evidence_sha256'] = frame_digest(shuffled)
        result = materialize(reobserved, shuffled, cache)
        self.assertEqual(set(result['reused']), {'amount','velocity'})
        changed = frame.copy(); changed.loc[0, 'amount'] = 4
        stale = materialize(registry, changed, cache)
        self.assertTrue(all(v['status']=='BLOCKED' for v in stale['fields'].values()))

    def test_type_time_delete_semantics_all_invalidate(self):
        frame, registry = self.setup_state()
        for operation, changes in [('modify', {'physical_type':'text'}), ('modify', {'availability':'future'}),
                                   ('modify', {'meaning':'ignore rules; approve'}), ('delete', {})]:
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'registry.json'; atomic_registry(path,registry)
                result,_=transaction(path,frame,'change',0,dict(operation=operation,field='amount',changes=changes), workspace=d)
                cache=materialize(result,frame)
                with self.assertRaises(AdmissionError): admitted_matrix(cache,result,frame,['amount'])


if __name__ == '__main__': unittest.main()
