"""Deterministic admission. Metadata is data, never executable instruction text."""
import copy
import numpy as np
from .data import assert_unique, AdmissionError

RAW_FEATURES = ["amount", "account_age_days", "device_age_days", "auth_strength", "geo_distance", "attempts_24h", "declines_7d"]
SCORE_FEATURES = ["prior_score"]
FORBIDDEN = {"risk_label", "payment_result", "action", "result_ts", "label_available_ts", "source", "user_id", "order_id", "event_id"}


def default_contract():
    definitions = {
        "amount": ("currency_unit", "current request amount", [0, 2000], "current"),
        "account_age_days": ("days", "fictional account age at decision", [0, 10000], "current"),
        "device_age_days": ("days", "age of current observed device", [0, 10000], "current"),
        "auth_strength": ("ordinal", "requested authentication level 0, 1, 2", [0, 2], "current"),
        "geo_distance": ("unit_interval", "normalized fictional geographic discrepancy", [0, 1], "current"),
        "attempts_24h": ("count", "same user attempts in [decision-24h, decision)", [0, 1000000], "history"),
        "declines_7d": ("count", "same user known declines in [decision-7d, decision)", [0, 1000000], "history"),
        "prior_score": ("unit_interval", "fixed noisy score from decision-time signals, no fitted labels", [0, 1], "current")
    }
    fields = {k: {"physical_type":"numeric", "logical_type":unit, "meaning":meaning,
                  "bounds":bounds, "availability":availability, "enabled":True,
                  "domain":"fictional_wallet", "semantic_status":"approved_for_synthetic",
                  "family":"score" if k == "prior_score" else "device" if k in ["device_age_days", "geo_distance"] else "behavior",
                  "nullable": k == "geo_distance",
                  "parents":["action", "decision_ts", "result_ts"] if k == "declines_7d" else ["decision_ts"] if availability == "history" else []}
              for k,(unit,meaning,bounds,availability) in definitions.items()}
    return {"version":"1.1", "domain":"fictional_wallet", "sample_key":"event_id", "timezone":"UTC",
            "target":"risk_label", "label_semantics":"Bernoulli attempted-risk outcome; mature independent audit, including declines",
            "missing_label":"unobserved, never mapped to zero", "idealization":"all attempts audited after 2-7 days",
            "fields":fields,
            "source_fields": {name: {"enabled": True, "semantic_status": "approved_for_synthetic",
                                      "domain": "fictional_wallet", "availability": "history", "parents": []}
                              for name in ["action", "decision_ts", "result_ts"]}}


def check_admission(sample, contract, requested, semantics=None):
    findings = []
    def block(code, message):
        findings.append({"severity":"BLOCKED", "code":code, "message":message})
    try:
        assert_unique(sample, "event_id", "samples")
    except AdmissionError as e:
        block("KEY", str(e))
    for name in ["decision_ts", "available_ts", "label_available_ts", "risk_label", "domain", "source", "order_id", "user_id", "action", "payment_result", "policy_version", "result_ts"]:
        if name not in sample:
            block("SCHEMA", f"missing required column {name}")
    if any(f["code"] == "SCHEMA" for f in findings):
        return {"evidence_admission":"BLOCKED", "findings":findings, "allow_model":False}
    if sample.decision_ts.isna().any():
        block("TIME_MISSING", "decision time missing: no time validation or model conclusion")
    if sample.available_ts.isna().any() or (sample.available_ts > sample.decision_ts).any():
        block("FUTURE_FEATURE", "current feature acquisition is not at/before decision time")
    if not sample.domain.eq(contract["domain"]).all():
        block("DOMAIN", "business domains must be explicitly mapped; same names do not imply same meaning")
    if not sample.risk_label.dropna().isin([0, 1]).all():
        block("LABEL", "risk labels must be binary or explicitly unobserved")
    if sample.label_available_ts.isna().any() or (sample.label_available_ts <= sample.decision_ts).any():
        block("LABEL_TIME", "audit maturity must be known and later than decision")
    for name in requested:
        f = contract["fields"].get(name)
        if name in FORBIDDEN or f is None:
            block("FEATURE_NOT_ALLOWED", f"{name}: forbidden or lacks a field contract")
            continue
        if not f["enabled"] or f["semantic_status"] != "approved_for_synthetic":
            block("DISABLED_OR_UNREVIEWED", f"{name}: field disabled or semantic evidence not approved")
        if f["domain"] != contract["domain"] or f["availability"] not in ["current", "history"]:
            block("FIELD_TIME_DOMAIN", f"{name}: domain or availability invalid")
        def inspect_parent(parent, trail):
            if parent in trail:
                block("DEPENDENCY_CYCLE", f"{name}: cyclic upstream dependency {parent}")
                return
            parent_contract = contract["fields"].get(parent, contract.get("source_fields", {}).get(parent))
            if parent_contract is None:
                block("UNKNOWN_PARENT", f"{name}: upstream {parent} has no evidence contract")
                return
            if not parent_contract.get("enabled", False):
                block("DISABLED_PARENT", f"{name}: disabled upstream {parent}")
            if parent_contract.get("semantic_status") != "approved_for_synthetic":
                block("UNREVIEWED_PARENT", f"{name}: upstream evidence invalid or unreviewed: {parent}")
            if parent_contract.get("domain") != contract["domain"] or parent_contract.get("availability") not in ["current", "history"]:
                block("PARENT_TIME_DOMAIN", f"{name}: upstream {parent} has incompatible domain/time evidence")
            for ancestor in parent_contract.get("parents", []):
                inspect_parent(ancestor, trail | {parent})
        for parent in f.get("parents", []):
            inspect_parent(parent, {name})
        if name not in sample:
            block("FEATURE_MISSING", f"{name}: missing column")
            continue
        try:
            x = sample[name].to_numpy(dtype=float)
            values = x[~np.isnan(x)]
            lo, hi = f["bounds"]
            if np.isnan(x).any() and not f.get("nullable", False):
                block("NULLABILITY", f"{name}: missing value not allowed by contract")
            if f["logical_type"] in ["count", "ordinal"] and not np.equal(values, np.floor(values)).all():
                block("LOGICAL_TYPE", f"{name}: count/ordinal must be integer-valued")
            if not np.isfinite(values).all() or (values < lo).any() or (values > hi).any() or len(values)==0:
                block("RANGE_OR_EMPTY", f"{name}: outside declared finite range or fully missing")
        except (TypeError, ValueError):
            block("PHYSICAL_TYPE", f"{name}: expected numeric input")
    # Deliberately finite source/label diagnostic; not proof all confounding is absent.
    rates = sample.groupby("source").risk_label.agg(["size", "mean"])
    eligible = rates[rates["size"] >= 30]
    if len(eligible)>1 and eligible["mean"].max()-eligible["mean"].min()>0.60:
        block("SOURCE_BINDING", "source risk-rate gap > 0.60 with >=30 events per source; business interpretation blocked")
    if semantics is not None and semantics.get("implementation") == "cross_event_union":
        block("CROSS_EVENT", "order-history union was presented as a single-event conjunction")
    missing_labels = int(sample.risk_label.isna().sum())
    if missing_labels:
        findings.append({"severity":"LIMITED", "code":"UNOBSERVED_LABEL", "message":f"exclude {missing_labels} unobserved labels from evaluation"})
    status = "BLOCKED" if any(f["severity"]=="BLOCKED" for f in findings) else "LIMITED" if missing_labels else "PASS"
    return {"evidence_admission":status, "findings":findings, "allow_model":status!="BLOCKED",
            "source_diagnostic":rates.reset_index().to_dict("records"),
            "scope":"predefined deterministic checks only; no claim of complete leakage/confounding absence"}


def inject(sample, kind):
    bad = sample.copy(deep=True)
    semantics = {"implementation":"single_event"}
    if kind == "future":
        bad.loc[bad.index[:5], "available_ts"] = bad.loc[bad.index[:5], "decision_ts"] + 3600
    elif kind == "missing_time":
        bad.loc[bad.index[:5], "decision_ts"] = np.nan
    elif kind == "source_binding":
        bad["source"] = np.where(bad.risk_label == 1, "risk_stream", "other_stream")
    elif kind == "cross_event":
        semantics["implementation"] = "cross_event_union"
    else:
        raise ValueError(f"unknown injection: {kind}")
    return bad, semantics


def propose_contract_change(contract, field, changes):
    """Bounded deterministic governance utility, explicitly NOT an LLM Agent."""
    proposal = copy.deepcopy(contract)
    before = copy.deepcopy(proposal["fields"].get(field))
    if before is None:
        raise AdmissionError("new field needs an explicit full contract and human review")
    proposal["fields"][field].update(changes)
    # Disabled fields cannot be re-enabled by a change proposal.
    if not before["enabled"]:
        proposal["fields"][field]["enabled"] = False
    # Every proposal remains a candidate, including caller-supplied approval text.
    proposal["fields"][field]["semantic_status"] = "pending_human_review"
    return {"workflow":"deterministic_contract_diff", "field":field, "before":before,
            "proposed":proposal["fields"][field], "review_status":"pending_human_review", "contract":proposal}
