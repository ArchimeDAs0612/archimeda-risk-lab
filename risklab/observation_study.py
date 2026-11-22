"""Can an intake channel win model selection by predicting label visibility?"""
import argparse
import json

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from .study_contracts import workspace_path


SEEDS = (3119, 7741, 2903)
WINDOWS = (6000, 3000, 4000)
VIEWS = {"signal": (0, 1), "channel": (2,), "combined": (0, 1, 2)}


def generate(seed):
    """One instrument per tick. Channel has no arrow into the fault mechanism."""
    rng = np.random.default_rng(seed)
    size = sum(WINDOWS)
    signal = rng.normal(size=(size, 2))
    channel = rng.binomial(1, 0.3, size)
    log_odds = -2.15 + (1.1 * signal[:, 0] - 0.7 * signal[:, 1])
    fault = rng.random(size) < 1 / (1 + np.exp(-log_odds))
    capture_draw = rng.random(size)
    return {
        "x": np.column_stack((signal, channel)),
        "fault": fault,
        "ticket": fault & (capture_draw < np.where(channel == 1, 0.93, 0.05)),
        "swapped_ticket": fault & (capture_draw < np.where(channel == 0, 0.93, 0.05)),
        "audit": rng.random(size) < 0.25,
    }


def fit_candidates(features, tickets):
    fits = {}
    for name, columns in VIEWS.items():
        model = LogisticRegression(C=1.0, solver="liblinear", max_iter=250, random_state=0)
        fits[name] = model.fit(features[:, columns], tickets)
    return fits


def score_views(models, features):
    # AP and ROC-AUC need only ranks. The linear predictor preserves those ranks.
    return {key: np.sum(features[:, VIEWS[key]] * model.coef_[0], axis=1) + model.intercept_[0]
            for key, model in models.items()}


def evaluate(target, predictions):
    return {
        "rows": len(target), "positives": int(target.sum()),
        "ap": round(float(average_precision_score(target, predictions)), 6),
        "auc": round(float(roc_auc_score(target, predictions)), 6),
    }


def select_models(features, tickets, audit_rows, audited_faults, selection_features,
                  selection_tickets):
    """Only independently inspected validation outcomes enter audit selection."""
    models = fit_candidates(features, tickets)
    scores = score_views(models, selection_features)
    audits = {name: evaluate(audited_faults, s[audit_rows]) for name, s in scores.items()}
    proxies = {name: evaluate(selection_tickets, s) for name, s in scores.items()}
    # Fixed iteration order resolves equal rounded AP.
    winners = {key: max(VIEWS, key=lambda v: metrics[v]["ap"])
               for key, metrics in (("ticket", proxies), ("audit", audits))}
    return models, {"winners": winners, "ticket": proxies, "audit": audits}


def run_seed(seed):
    data = generate(seed)
    end, mid = WINDOWS[0], sum(WINDOWS[:2])
    train = slice(0, end)
    selection = slice(end, mid)
    final = slice(mid, None)
    audit = data["audit"][selection]
    models, chosen = select_models(
        data["x"][train], data["ticket"][train], audit, data["fault"][selection][audit],
        data["x"][selection], data["ticket"][selection])
    scores = score_views(models, data["x"][final])
    evaluation = {name: {outcome: evaluate(data[outcome][final], pred)
                         for outcome in ("ticket", "swapped_ticket", "fault")}
                  for name, pred in scores.items()}
    return {"seed": seed, "selection": chosen, "final": evaluation}


def run():
    return {"protocol": "instrument-intake-v1", "window_sizes_train_select_final": WINDOWS,
            "unit": "one independent synthetic instrument at one decision tick",
            "audit_probability": 0.25, "seeds": [run_seed(seed) for seed in SEEDS]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    output = workspace_path(parser.parse_args().out)
    result = run()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
