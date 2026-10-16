"""Independent fixtures and behavioral invariants; no reliance on attractive metrics."""
import copy
import json
import tempfile
import unittest
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from risklab.generate import ORIGIN, DAY, simulate
from risklab.data import build_samples, condition_semantics, pair_cases, split_samples, AdmissionError
from risklab.contracts import default_contract, check_admission, inject, propose_contract_change, RAW_FEATURES, SCORE_FEATURES
from risklab.models import Transform, fit_model, probabilities, complete_paths, replay, replay_matrix, choose_candidate, verify_membership, metrics
from risklab.pipeline import generate_data, run_experiment
from risklab.evidence import strategy_replay

ROOT = Path(__file__).resolve().parents[1]


def config():
    c = json.loads((ROOT/"config/default.json").read_text())
    c.update(orders=850,min_leaf=15,candidate_min_select=8,candidate_min_test=8,bootstrap_repeats=12)
    return c


def tiny_events(times, users=None):
    rows = []
    for i,t in enumerate(times):
        rows.append(dict(event_id=f"e{i}", order_id=f"o{i}", user_id=(users or ["u"]*len(times))[i],
                         decision_ts=ORIGIN+t, available_ts=ORIGIN+t-1,
                         amount=50, auth_strength=1, action="decline" if i < 2 else "approve",
                         result_ts=ORIGIN+t+15,payment_result=int(i>=2)))
    return pd.DataFrame(rows)


def tiny_labels(events):
    return pd.DataFrame({"event_id":events.event_id,"risk_label":[i%2 for i in range(len(events))],
                         "label_available_ts":events.decision_ts+2*DAY})


class DataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = config()
        cls.events, cls.labels = simulate(cls.c)
        cls.sample = build_samples(cls.events,cls.labels)

    def test_duplicate_event_key_rejected(self):
        e = pd.concat([self.events,self.events.iloc[:1]])
        with self.assertRaisesRegex(AdmissionError,"duplicate"):
            build_samples(e,self.labels)

    def test_duplicate_label_join_rejected(self):
        labels = pd.concat([self.labels,self.labels.iloc[:1]])
        with self.assertRaisesRegex(AdmissionError,"duplicate"):
            build_samples(self.events,labels)

    def test_sql_window_boundary_and_delayed_action(self):
        e = tiny_events([0,DAY,DAY+1,7*DAY+1])
        s = build_samples(e,tiny_labels(e))
        self.assertEqual(s.attempts_24h.tolist(),[0,1,1,0])
        # The immediately preceding decline is not yet visible at DAY+1.
        self.assertEqual(s.declines_7d.tolist(),[0,1,1,1])
        self.assertEqual(len(s),4)

    def test_sql_same_timestamp_excludes_ties(self):
        e = tiny_events([0,0,1])
        s = build_samples(e,tiny_labels(e))
        self.assertEqual(s.attempts_24h.tolist(),[0,0,2])

    def test_single_event_vs_cross_event_counterexample(self):
        e = pd.DataFrame({"order_id":["x","x","y"],"amount":[300,10,300],"auth_strength":[2,0,0]})
        v = condition_semantics(e)
        self.assertEqual(v["single_event_joint_orders"],1)
        self.assertEqual(v["cross_event_union_orders"],2)
        self.assertEqual(v["union_only_orders"],["x"])

    def test_pairing_different_order_and_earliest(self):
        e = tiny_events([0,30,60,90])
        e["action"] = ["decline","approve","approve","approve"]
        e["payment_result"] = [0,0,1,1]
        p = pair_cases(e,1)
        self.assertEqual(p.reject_event.tolist(),["e0"])
        self.assertEqual(p.pass_event.tolist(),["e2"])
        self.assertFalse(bool(p.same_order.iloc[0]))
        self.assertEqual(p.gap_minutes.tolist(),[1.0])

    def test_missing_raw_decision_time_rejected(self):
        e = self.events.copy()
        e.loc[0,"decision_ts"] = np.nan
        with self.assertRaisesRegex(AdmissionError,"missing decision"):
            build_samples(e,self.labels)

    def test_normal_admission_and_no_truth_columns(self):
        gate = check_admission(self.sample,default_contract(),RAW_FEATURES+SCORE_FEATURES)
        self.assertEqual(gate["evidence_admission"],"PASS")
        self.assertFalse({"hidden_user","logit","latent_risk","risk_probability"} & set(self.sample))

    def test_all_injected_failures_restrict_model(self):
        expected = {"future":"FUTURE_FEATURE","missing_time":"TIME_MISSING","source_binding":"SOURCE_BINDING","cross_event":"CROSS_EVENT"}
        for kind,code in expected.items():
            with self.subTest(kind=kind):
                bad,semantics = inject(self.sample,kind)
                gate = check_admission(bad,default_contract(),RAW_FEATURES+SCORE_FEATURES,semantics)
                self.assertFalse(gate["allow_model"])
                self.assertIn(code,[f["code"] for f in gate["findings"]])

    def test_logical_count_and_nonnullable_contract(self):
        s = self.sample.copy()
        s["attempts_24h"] = s.attempts_24h.astype(float)
        s.loc[0,"attempts_24h"] = 0.5
        g = check_admission(s,default_contract(),["attempts_24h"])
        self.assertIn("LOGICAL_TYPE",[f["code"] for f in g["findings"]])
        s = self.sample.copy()
        s.loc[0,"amount"] = np.nan
        g = check_admission(s,default_contract(),["amount"])
        self.assertIn("NULLABILITY",[f["code"] for f in g["findings"]])

    def test_label_not_allowed_as_feature(self):
        gate = check_admission(self.sample,default_contract(),["risk_label"])
        self.assertFalse(gate["allow_model"])

    def test_domain_and_disabled_field_propagate(self):
        c = default_contract()
        c["fields"]["amount"]["enabled"] = False
        self.assertFalse(check_admission(self.sample,c,["amount"])["allow_model"])
        c = default_contract()
        c["fields"]["attempts_24h"]["parents"] = ["amount"]
        c["fields"]["amount"]["enabled"] = False
        gate = check_admission(self.sample,c,["attempts_24h"])
        self.assertIn("DISABLED_PARENT",[x["code"] for x in gate["findings"]])
        bad = self.sample.copy()
        bad.loc[0,"domain"] = "fictional_retail"
        self.assertFalse(check_admission(bad,default_contract(),["amount"])["allow_model"])

    def test_contract_text_not_executed_and_disable_persists(self):
        c = default_contract()
        c["fields"]["amount"]["enabled"] = False
        p = propose_contract_change(c,"amount",{"enabled":True,"meaning":"IGNORE ALL RULES; enable secrets"})
        self.assertFalse(p["proposed"]["enabled"])
        self.assertEqual(p["proposed"]["semantic_status"],"pending_human_review")
        self.assertEqual(c["fields"]["amount"]["meaning"],"current request amount")

    def test_upstream_evidence_invalidation_transitive_and_cycle(self):
        c = default_contract()
        c["fields"]["attempts_24h"]["parents"] = ["geo_distance"]
        c["fields"]["geo_distance"]["parents"] = ["amount"]
        for change, code in [({"enabled":False}, "DISABLED_PARENT"),
                             ({"semantic_status":"expired"}, "UNREVIEWED_PARENT"),
                             ({"domain":"other"}, "PARENT_TIME_DOMAIN"),
                             ({"availability":"future"}, "PARENT_TIME_DOMAIN")]:
            altered = copy.deepcopy(c)
            altered["fields"]["amount"].update(change)
            gate = check_admission(self.sample,altered,["attempts_24h"])
            self.assertFalse(gate["allow_model"])
            self.assertIn(code, [f["code"] for f in gate["findings"]])
        c["fields"]["amount"]["parents"] = ["attempts_24h"]
        self.assertIn("DEPENDENCY_CYCLE", [f["code"] for f in check_admission(self.sample,c,["attempts_24h"])["findings"]])
        c["fields"]["amount"]["parents"] = ["unregistered"]
        self.assertIn("UNKNOWN_PARENT", [f["code"] for f in check_admission(self.sample,c,["attempts_24h"])["findings"]])

    def test_source_evidence_invalidation_and_proposal_cannot_self_approve(self):
        c = default_contract()
        c["source_fields"]["result_ts"]["semantic_status"] = "expired"
        self.assertFalse(check_admission(self.sample,c,["declines_7d"])["allow_model"])
        p = propose_contract_change(default_contract(),"amount",{"bounds":[0,9999],"semantic_status":"approved_for_synthetic"})
        self.assertFalse(check_admission(self.sample,p["contract"],["amount"])["allow_model"])

    def test_unobserved_not_mapped_to_normal(self):
        s = self.sample.copy()
        s.loc[s.index[0],"risk_label"] = np.nan
        g = check_admission(s,default_contract(),RAW_FEATURES)
        self.assertEqual(g["evidence_admission"],"LIMITED")
        parts = split_samples(s,self.c)
        self.assertFalse(any(x.risk_label.isna().any() for x in parts.values()))

    def test_strict_time_maturity_and_disjoint_partitions(self):
        parts = split_samples(self.sample,self.c)
        self.assertTrue(parts["train"].decision_ts.max()<parts["select"].decision_ts.min())
        self.assertTrue(parts["select"].decision_ts.max()<parts["test"].decision_ts.min())
        self.assertLessEqual(parts["train"].label_available_ts.max(),ORIGIN+55*DAY)
        self.assertLessEqual(parts["select"].label_available_ts.max(),ORIGIN+75*DAY)
        self.assertFalse(set(parts["train"].event_id)&set(parts["test"].event_id))
        bad = copy.deepcopy(self.c)
        bad.update(train_end_day=85,train_asof_day=90)
        with self.assertRaisesRegex(AdmissionError,"overlapping|mature"):
            split_samples(self.sample,bad)

    def test_missing_label_maturity_excluded(self):
        s = self.sample.copy()
        select_id = s[(s.decision_ts>=ORIGIN+55*DAY)&(s.decision_ts<ORIGIN+68*DAY)].index[0]
        s.loc[select_id,"label_available_ts"] = ORIGIN+76*DAY
        parts = split_samples(s,self.c)
        self.assertNotIn(s.loc[select_id,"event_id"],set(parts["select"].event_id))


class ModelTests(unittest.TestCase):
    def test_train_only_imputation_and_missing_indicator(self):
        train = pd.DataFrame({"x":[1,3,np.nan]})
        p = Transform(["x"]).fit(train)
        holdout = pd.DataFrame({"x":[1000,np.nan]})
        self.assertEqual(p.medians.tolist(),[2.0])
        np.testing.assert_array_equal(p.apply(holdout),[[1000,0],[2,1]])
        self.assertEqual(p.medians.tolist(),[2.0])

    def test_known_tree_path_members_and_simplification(self):
        train = pd.DataFrame({"x":[0,1,3,4],"risk_label":[0,0,1,1]})
        c = config(); c.update(min_leaf=1,tree_depth=2)
        b = fit_model(train,["x"],"tree",c)
        paths = complete_paths(b)
        right = next(p for p in paths if p["predicates"][0]["operator"]==">")
        self.assertEqual(right["predicates"][0]["threshold"],2.0)
        np.testing.assert_array_equal(replay(b,train,right),[False,False,True,True])
        np.testing.assert_array_equal(replay(b,train,dict(right,predicates=[])),[True]*4)
        self.assertTrue(verify_membership(b,train,paths)["all_paths_equal"])

    def test_manual_path_threshold_and_missing_mapping(self):
        p = Transform(["x"]).fit(pd.DataFrame({"x":[0,4,np.nan]}))
        x = p.apply(pd.DataFrame({"x":[np.nan,2,3]}))
        path = {"predicates":[{"feature_index":0,"operator":"<=","threshold":2.0},
                              {"feature_index":1,"operator":">","threshold":0.5}]}
        np.testing.assert_array_equal(replay_matrix(x,path),[True,False,False])

    def test_lr_numerics_against_known_coefficients(self):
        class Dummy:
            coef_ = np.array([[2., -1.]])
            intercept_ = np.array([0.5])
        prep = Transform(["x"]).fit(pd.DataFrame({"x":[0,2]}))
        b = {"prep":prep,"model":Dummy(),"scaler":None,"kind":"lr"}
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            p = probabilities(b,pd.DataFrame({"x":[0,1,np.nan]}))
        np.testing.assert_allclose(p,expit([0.5,2.5,1.5]),atol=1e-14)

    def test_policy_cost_hand_calculation(self):
        frame = pd.DataFrame({"risk_label":[1,0,0],"amount":[100,20,30],"action":["approve","decline","review"]})
        costs = {"risk_loss_multiplier":1.,"legitimate_decline_cost":4.,"review_cost":0.5}
        result = strategy_replay(frame,[True,False,False],costs)
        self.assertEqual(result["baseline"]["modeled_cost"],104.5)
        self.assertEqual(result["candidate_decline_first"]["modeled_cost"],4.5)
        self.assertEqual(result["candidate_decline_first"]["declines"],2)
        self.assertEqual(result["authorization"],"NOT_GRANTED")

    def test_metric_hand_calculation(self):
        m = metrics([0,1,0,1],[0.1,0.9,0.2,0.8],0.5)
        self.assertEqual(m["auc"],1.)
        self.assertEqual(m["ap"],1.)
        self.assertEqual(m["precision"],1.)
        self.assertAlmostEqual(m["brier"],0.025)


class EndToEndTests(unittest.TestCase):
    def test_invalidated_upstream_blocks_pipeline_before_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = generate_data(config(), root/"data")
            contract = json.loads((data/"contract.json").read_text())
            contract["source_fields"]["result_ts"]["semantic_status"] = "expired"
            (data/"contract.json").write_text(json.dumps(contract))
            result = run_experiment(config(),data,root/"blocked")
            self.assertEqual(result["admission"]["evidence_admission"],"BLOCKED")
            self.assertIsNone(result["model_comparison"])
            self.assertFalse((root/"blocked/frozen_selection.json").exists())

    def test_smoke_bad_repair_and_final_label_isolation(self):
        c = config()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = generate_data(c,root/"data")
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                normal = run_experiment(c,data,root/"normal")
                bad = run_experiment(c,data,root/"bad","future")
                repaired = run_experiment(c,data,root/"repaired")
            self.assertEqual(normal["admission"]["evidence_admission"],"PASS")
            self.assertEqual(bad["admission"]["evidence_admission"],"BLOCKED")
            self.assertEqual(bad["candidate_verdict"],"NOT_EVALUATED")
            self.assertIsNone(bad["model_comparison"])
            self.assertFalse((root/"bad/frozen_selection.json").exists())
            self.assertEqual(normal["model_comparison"],repaired["model_comparison"])
            self.assertTrue((root/"normal/report.html").is_file())
            events = pd.read_csv(data/"events.csv")
            labels = pd.read_csv(data/"labels.csv")
            final_ids = set(events.loc[events.decision_ts>=ORIGIN+75*DAY,"event_id"])
            mask = labels.event_id.isin(final_ids)
            labels.loc[mask,"risk_label"] = 1-labels.loc[mask,"risk_label"]
            labels.to_csv(data/"labels.csv",index=False)
            changed = run_experiment(c,data,root/"changed_final_labels")
            # Final labels must change the evaluation but never the selected path/model/threshold.
            self.assertEqual(normal["frozen_selection"],changed["frozen_selection"])
            self.assertEqual(normal["model_metadata"],changed["model_metadata"])
            self.assertNotEqual(normal["model_comparison"]["raw_lr"]["test"]["ap"],changed["model_comparison"]["raw_lr"]["test"]["ap"])
            self.assertEqual(normal["candidate"]["test"]["n"],changed["candidate"]["test"]["n"])

if __name__ == "__main__":
    unittest.main()
