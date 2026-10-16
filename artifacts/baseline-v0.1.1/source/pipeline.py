"""One complete experiment with explicit train, selection, and final evaluation stages."""
import hashlib
import json
import platform
import time
from pathlib import Path
import importlib.metadata
import numpy as np
import pandas as pd
from .generate import simulate, DAY, ORIGIN
from .data import build_samples, split_samples, pair_cases, condition_semantics, AdmissionError
from .contracts import default_contract, check_admission, inject, RAW_FEATURES, SCORE_FEATURES
from .models import fit_model, probabilities, metrics, complete_paths, choose_candidate, replay, verify_membership, calibration
from .evidence import candidate_summary, paired_ap_interval, stratified_countercheck, rediscovery, strategy_replay


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate_data(config, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    events, labels = simulate(config)
    events.to_csv(out/"events.csv", index=False)
    labels.to_csv(out/"labels.csv", index=False)
    save_json(out/"contract.json", default_contract())
    save_json(out/"generation.json", {"config":config, "events":len(events), "data_version":"synthetic-v1",
                                    "mechanism":"risklab/generate.py", "label_visibility":"idealized independent audit, all attempts"})
    return out


def code_manifest():
    root = Path(__file__).resolve().parent.parent
    files = sorted(list((root/"risklab").glob("*.py"))+list((root/"risklab").glob("*.sql")))
    return {str(p.relative_to(root)):sha(p) for p in files}


def run_experiment(config, data_dir, out, injection=None):
    start = time.perf_counter()
    data_dir, out = Path(data_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    events = pd.read_csv(data_dir/"events.csv")
    labels = pd.read_csv(data_dir/"labels.csv")
    contract = json.loads((data_dir/"contract.json").read_text())
    try:
        sample = build_samples(events, labels)
        semantics = {"implementation":"single_event"}
        if injection:
            sample, semantics = inject(sample, injection)
        gate = check_admission(sample, contract, RAW_FEATURES+SCORE_FEATURES, semantics)
    except AdmissionError as error:
        sample = events.copy()
        gate = {"evidence_admission":"BLOCKED", "allow_model":False,
                "findings":[{"severity":"BLOCKED", "code":"INPUT_CONSTRUCTION", "message":str(error)}],
                "scope":"raw input failed schema/key/time construction; no model or candidate evaluated"}
    provenance = {"config":config, "config_sha256":hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                  "data_sha256":{p.name:sha(p) for p in data_dir.iterdir() if p.is_file()},
                  "code_sha256":code_manifest(), "python":platform.python_version(),
                  "dependencies":{n:importlib.metadata.version(n) for n in ["numpy", "pandas", "scipy", "scikit-learn", "joblib", "threadpoolctl"]},
                  "sqlite_version":__import__("sqlite3").sqlite_version,
                  "injection":injection, "execution_scope":"local CPU, no external data or model service"}
    sample.to_csv(out/("input_events.csv" if any(f["code"] == "INPUT_CONSTRUCTION" for f in gate["findings"]) else "samples.csv"), index=False)
    result = {"execution":"SUCCESS", "admission":gate, "production_authorization":"NOT_GRANTED", "provenance":provenance}
    save_json(out/"admission.json", gate)
    if not gate["allow_model"]:
        result.update(candidate_verdict="NOT_EVALUATED", model_comparison=None, elapsed_seconds=time.perf_counter()-start)
        save_json(out/"result.json", result)
        from .report import render_report
        render_report(result, out/"report.html")
        return result
    parts = split_samples(sample, config)
    train, selection, test = parts["train"], parts["select"], parts["test"]
    split_info = {}
    for name, frame in parts.items():
        split_info[name] = {"n":len(frame), "positives":int(frame.risk_label.sum()), "base_rate":float(frame.risk_label.mean()),
                            "decision_min":int(frame.decision_ts.min()), "decision_max":int(frame.decision_ts.max()),
                            "max_label_available":int(frame.label_available_ts.max()),
                            "event_ids_sha256":hashlib.sha256("\n".join(frame.event_id).encode()).hexdigest(),
                            "new_subjects":int((~frame.user_id.isin(train.user_id)).sum()),
                            "new_subject_count":int(frame.loc[~frame.user_id.isin(train.user_id), "user_id"].nunique())}
    definitions = {"score_lr":(SCORE_FEATURES,"lr"), "raw_lr":(RAW_FEATURES,"lr"),
                   "hybrid_lr":(RAW_FEATURES+SCORE_FEATURES,"lr"), "raw_tree":(RAW_FEATURES,"tree"),
                   "hybrid_tree":(RAW_FEATURES+SCORE_FEATURES,"tree"),
                   "without_device_lr":([c for c in RAW_FEATURES if c not in ["device_age_days", "geo_distance"]],"lr")}
    bundles, scores, thresholds, comparisons, model_meta = {}, {}, {}, {}, {}
    for name,(columns,kind) in definitions.items():
        bundle = fit_model(train, columns, kind, config)
        bundles[name] = bundle
        scores[name] = {part:probabilities(bundle, frame) for part,frame in parts.items() if part != "test"}
        # Quantile chosen on selection scores only; ties can exceed nominal review budget.
        thresholds[name] = float(np.quantile(scores[name]["select"], 1-config["review_fraction"]))
        comparisons[name] = {part:metrics(frame.risk_label, scores[name][part], thresholds[name]) for part,frame in parts.items() if part != "test"}
        model_meta[name] = {"kind":kind, "parameters":bundle["model"].get_params(), "preprocessing":bundle["prep"].metadata(),
                            "lr_coefficients":bundle["model"].coef_[0].tolist() if kind == "lr" else None,
                            "lr_intercept":float(bundle["model"].intercept_[0]) if kind == "lr" else None,
                            "scaler_mean":bundle["scaler"].mean_.tolist() if bundle["scaler"] is not None else None,
                            "scaler_scale":bundle["scaler"].scale_.tolist() if bundle["scaler"] is not None else None}
    # Candidate extraction deliberately uses the prespecified raw tree, not the best test model.
    tree = bundles["raw_tree"]
    path = choose_candidate(tree, selection, config)
    paths = complete_paths(tree)
    membership = {part:verify_membership(tree, frame, paths) for part,frame in parts.items()}
    selected_model = max(definitions, key=lambda name:comparisons[name]["select"]["ap"])
    frozen = {"candidate_model":"raw_tree", "candidate":path, "preprocessing":tree["prep"].metadata(),
              "selected_model_by_selection_ap":selected_model, "thresholds":thresholds,
              "selection_boundary":"no final labels used to select candidate, model, or thresholds",
              "candidate_policy":"maximize selection risk rate among leaves with minimum support; rate/n/leaf deterministic tie break"}
    # This artifact is persisted BEFORE any final test candidate calculations.
    save_json(out/"frozen_selection.json", frozen)
    for name, bundle in bundles.items():
        scores[name]["test"] = probabilities(bundle, test)
        comparisons[name]["test"] = metrics(test.risk_label, scores[name]["test"], thresholds[name])
    comparisons["constant"] = {part:metrics(frame.risk_label, np.full(len(frame), train.risk_label.mean()), 1.0) for part,frame in parts.items()}
    candidate = {part:candidate_summary(frame, replay(tree, frame, path), config, config["seed"]+i)
                 for i,(part,frame) in enumerate(parts.items())}
    sel, final = candidate["select"], candidate["test"]
    supports = (sel["n"]>=config["candidate_min_select"] and final["n"]>=config["candidate_min_test"]
                and final["risk_count"]>=5 and final["difference_cluster_ci95"][0] is not None
                and final["difference_cluster_ci95"][0]>0)
    verdict = "SUPPORTED_FOR_INVESTIGATION" if supports else "INSUFFICIENT_SUPPORT"
    masks = {part:replay(tree,frame,path) for part,frame in parts.items()}
    # Dropping an upstream term creates a NEW candidate. Re-evaluate, never inherit leaf evidence.
    simplified = dict(path, predicates=path["predicates"][1:])
    simple_mask = replay(tree, test, simplified)
    simplification = {"new_candidate":simplified, "evaluation":candidate_summary(test,simple_mask,config,config["seed"]+8),
                      "added_events":test.loc[simple_mask & ~masks["test"], "event_id"].tolist(),
                      "removed_events":test.loc[~simple_mask & masks["test"], "event_id"].tolist(),
                      "scope":"post-evaluation diagnostic; not eligible for promotion without a new holdout"}
    # Label permutation negative controls use training data and selection only.
    controls = []
    rng = np.random.default_rng(config["seed"]+30)
    for i in range(3):
        shuffled = train.copy()
        shuffled["risk_label"] = rng.permutation(shuffled.risk_label.to_numpy())
        null = fit_model(shuffled, RAW_FEATURES, "lr", config)
        controls.append(metrics(selection.risk_label, probabilities(null,selection), 0.5))
    prediction_rows = []
    for part,frame in parts.items():
        view = frame[["event_id", "user_id", "source", "decision_ts", "risk_label", "amount", "action"]].copy()
        view["split"] = part
        view["candidate"] = masks[part]
        for name in definitions:
            view[name] = scores[name][part]
        prediction_rows.append(view)
    pd.concat(prediction_rows).to_csv(out/"predictions.csv", index=False)
    pair_records = {}
    for window in [1, 6, config["pair_window_hours"]]:
        paired = pair_cases(events, window)
        paired.to_csv(out/f"pairs_{window}h.csv", index=False)
        pair_records[str(window)] = {"pairs":len(paired), "same_order":int(paired.same_order.sum()),
                                     "different_order":int((~paired.same_order).sum()),
                                     "unique_later_events":int(paired.pass_event.nunique())}
    subgroups = {}
    for seen in [True, False]:
        mask = test.user_id.isin(train.user_id).to_numpy() == seen
        subgroups["seen_subject" if seen else "new_subject"] = {name:metrics(test.loc[mask,"risk_label"], scores[name]["test"][mask], thresholds[name]) for name in definitions}
    drift = {part:{"source_rates":frame.groupby("source").risk_label.agg(["size", "mean"]).reset_index().to_dict("records"),
                  "missingness":{name:float(frame[name].isna().mean()) for name in RAW_FEATURES}}
             for part,frame in parts.items()}
    result.update(splits=split_info, excluded_from_windows=len(sample)-sum(len(x) for x in parts.values()),
                  model_comparison=comparisons, model_metadata=model_meta, frozen_selection=frozen,
                  candidate=candidate, candidate_verdict=verdict, membership=membership, simplification=simplification,
                  ap_gain=paired_ap_interval(test, scores[selected_model]["test"], scores["score_lr"]["test"], config),
                  countercheck={part:stratified_countercheck(frame,masks[part]) for part,frame in parts.items()},
                  rediscovery=rediscovery(train,selection,masks["select"],RAW_FEATURES,config),
                  permutation_controls=controls, subgroup_metrics=subgroups, drift=drift,
                  calibration={name:calibration(test.risk_label,scores[name]["test"]) for name in definitions},
                  case_pairing=pair_records, condition_semantics=condition_semantics(events),
                  policy_scenario=strategy_replay(test,masks["test"],config["cost_assumptions"]),
                  elapsed_seconds=time.perf_counter()-start)
    save_json(out/"all_tree_paths.json", {"paths":paths, "preprocessing":tree["prep"].metadata()})
    save_json(out/"result.json", result)
    from .report import render_report
    render_report(result, out/"report.html")
    return result
