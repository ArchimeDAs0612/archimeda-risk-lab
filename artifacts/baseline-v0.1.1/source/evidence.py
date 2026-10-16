"""Uncertainty and limited falsification; never a production authorization engine."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from .models import replay, fit_model, choose_candidate


def interval(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return [float(x) for x in np.quantile(values, [0.025, 0.975])] if len(values) else [None, None]


def cluster_indices(frame, rng):
    groups = list(frame.groupby("user_id", sort=True).indices.values())
    return np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])


def candidate_summary(frame, mask, config, seed):
    y = frame.risk_label.to_numpy(dtype=int)
    mask = np.asarray(mask, dtype=bool)
    rate = float(y[mask].mean()) if mask.any() else None
    complement = float(y[~mask].mean()) if (~mask).any() else None
    diffs = []
    rng = np.random.default_rng(seed)
    for _ in range(config["bootstrap_repeats"]):
        idx = cluster_indices(frame, rng)
        m, v = mask[idx], y[idx]
        if m.any() and (~m).any():
            diffs.append(v[m].mean()-v[~m].mean())
    return {"n":int(mask.sum()), "risk_count":int(y[mask].sum()), "coverage":float(mask.mean()),
            "risk_rate":rate, "complement_risk_rate":complement,
            "enrichment_vs_all":rate/float(y.mean()) if rate is not None and y.mean() else None,
            "difference":rate-complement if rate is not None and complement is not None else None,
            "difference_cluster_ci95":interval(diffs), "bootstrap_valid":len(diffs),
            "uncertainty_scope":"user-cluster bootstrap of fixed candidate; selection interval is descriptive after search"}


def paired_ap_interval(frame, scores_a, scores_b, config):
    y = frame.risk_label.to_numpy(dtype=int)
    rng = np.random.default_rng(config["seed"]+14)
    values = []
    for _ in range(config["bootstrap_repeats"]):
        i = cluster_indices(frame, rng)
        if len(np.unique(y[i]))==2:
            values.append(average_precision_score(y[i], scores_a[i])-average_precision_score(y[i], scores_b[i]))
    return {"estimate":float(average_precision_score(y, scores_a)-average_precision_score(y, scores_b)),
            "ci95":interval(values), "valid_repeats":len(values), "resampling":"paired user clusters"}


def stratified_countercheck(frame, mask):
    """Common source × prespecified amount bands; descriptive, not causal matching."""
    x = frame.assign(candidate=np.asarray(mask), amount_band=pd.cut(frame.amount, [0, 20, 60, 150, np.inf], right=False).astype(str))
    rows = []
    for (source, band), group in x.groupby(["source", "amount_band"], observed=True):
        a, b = group[group.candidate], group[~group.candidate]
        if len(a)>=5 and len(b)>=5:
            rows.append({"source":source, "amount_band":band, "candidate_n":len(a), "control_n":len(b),
                         "candidate_rate":float(a.risk_label.mean()), "control_rate":float(b.risk_label.mean()),
                         "difference":float(a.risk_label.mean()-b.risk_label.mean())})
    weights = [r["candidate_n"] for r in rows]
    return {"cells":rows, "retained_candidate_n":sum(weights), "total_candidate_n":int(np.sum(mask)),
            "weighted_difference":float(np.average([r["difference"] for r in rows], weights=weights)) if weights else None,
            "scope":"source and amount only; unmatched cells excluded; residual confounding remains"}


def rediscovery(train, selection, original_mask, columns, config):
    rng = np.random.default_rng(config["seed"]+20)
    records = []
    for repetition in range(3):
        # Bootstrap subjects, not transactions; selection stays fixed and final test unseen.
        boot = train.iloc[cluster_indices(train, rng)].copy()
        model = fit_model(boot, columns, "tree", config, seed=config["seed"]+repetition+1)
        path = choose_candidate(model, selection, config)
        mask = replay(model, selection, path)
        union = int(np.sum(original_mask | mask))
        records.append({"repetition":repetition, "selection_jaccard":float(np.sum(original_mask & mask)/union) if union else 1.0,
                        "selection_n":int(mask.sum()), "path":path})
    return {"scope":"3 training user-bootstrap rediscoveries evaluated on fixed selection; not population stability proof", "runs":records}


def strategy_replay(frame, candidate_mask, costs):
    """Illustrative deny/allow policy on fully audited synthetic attempts; review unchanged."""
    y = frame.risk_label.to_numpy(dtype=int)
    amount = frame.amount.to_numpy()
    old = frame.action.eq("decline").to_numpy()
    new = old | np.asarray(candidate_mask)
    def summary(deny):
        return {"declines":int(deny.sum()), "risky_allowed":int(np.sum((~deny)&(y==1))),
                "legitimate_declined":int(np.sum(deny&(y==0))),
                "modeled_cost":float(np.sum(amount[(~deny)&(y==1)])*costs["risk_loss_multiplier"]
                    + np.sum(deny&(y==0))*costs["legitimate_decline_cost"]
                    + np.sum(frame.action.eq("review").to_numpy() & ~deny)*costs["review_cost"])}
    return {"baseline":summary(old), "candidate_decline_first":summary(new), "assumptions":costs,
            "scope":"all risky allowed attempts incur amount loss; declines prevent all loss; no behavioral response; review no protection; synthetic scenario only",
            "priority":"candidate or baseline decline > existing review > approve", "authorization":"NOT_GRANTED"}
