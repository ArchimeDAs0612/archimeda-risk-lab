"""Train and stress-test models of ordered, decision-time synthetic event histories."""
import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from scipy.sparse import csr_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

from .study_contracts import workspace_path

SEED = 40817
SYMBOLS = 4
MAX_LENGTH = 10
PHASES = (("train", 2400), ("validation", 600), ("stable_oot", 1000), ("reversed_oot", 1000))
FEATURE_DECAY = 1.5


def visible_symbols(events, decision):
    """Raw events are (occurred, available, symbol). Equal cutoff is excluded."""
    if any(seen < when or symbol not in range(SYMBOLS) for when, seen, symbol in events):
        raise ValueError("invalid event availability or symbol")
    visible = sorted((when, symbol) for when, seen, symbol in events
                     if when < decision and seen < decision)
    if len({when for when, _ in visible}) != len(visible):
        raise ValueError("ambiguous visible event order")
    return tuple(symbol for _, symbol in visible)


@dataclass(frozen=True)
class Example:
    subject: int
    decision: int
    mature: int
    history: tuple
    label: int


def simulate():
    rng = np.random.default_rng(SEED)
    phases = {}
    subject = 0
    for phase, size in PHASES:
        rows = []
        for _ in range(size):
            decision = 1024 + 32 * subject
            sequence = rng.integers(SYMBOLS, size=rng.integers(5, MAX_LENGTH + 1)).tolist()
            pairs = list(zip(sequence, sequence[1:]))
            orientation = pairs.count((0, 1)) - pairs.count((1, 0))
            sign = -1 if phase == "reversed_oot" else 1
            probability = expit(-1.9 + .48 * sequence.count(2) + sign * 1.9 * orientation)
            label = int(rng.random() < probability)
            events = [(decision - len(sequence) + i, decision - len(sequence) + i, symbol)
                      for i, symbol in enumerate(sequence)]
            # Decoys: a corrected historical event and an event exactly at decision time.
            # Both carry information about the label and must be invisible to every model.
            events += [(decision - 15, decision + 3, label), (decision, decision, label)]
            rows.append(Example(subject, decision, decision + 3, visible_symbols(events, decision), label))
            subject += 1
        phases[phase] = rows
    return phases


def encode(histories):
    """Counts and counts of all directed adjacent pairs, without using IDs or times."""
    counts = np.zeros((len(histories), SYMBOLS), dtype=int)
    pairs = np.zeros((len(histories), SYMBOLS ** 2), dtype=int)
    for i, history in enumerate(histories):
        counts[i] = np.bincount(history, minlength=SYMBOLS)
        for previous, current in zip(history, history[1:]):
            pairs[i, SYMBOLS * previous + current] += 1
    return counts, np.column_stack((counts, pairs))


def attention_input(histories):
    """For each current token, summarize earlier symbols using a fixed relative lag bias."""
    current = np.zeros((len(histories), MAX_LENGTH), dtype=int)
    prior = np.zeros((len(histories), MAX_LENGTH, SYMBOLS))
    for i, history in enumerate(histories):
        memory = np.zeros(SYMBOLS)
        for j, symbol in enumerate(history):
            current[i, j] = symbol
            prior[i, j] = memory
            memory *= np.exp(-FEATURE_DECAY)
            memory[symbol] += 1
    return current, prior


def attention_scores(params, counts, inputs):
    # One categorical causal attention head: a learned query/key-type score
    # plus the fixed lag bias, and a learned value for each ordered type pair.
    current, prior = inputs
    shape = (SYMBOLS, SYMBOLS)
    split = 1 + SYMBOLS
    query = params[split:split + SYMBOLS ** 2].reshape(shape)
    value = params[split + SYMBOLS ** 2:].reshape(shape)
    mass = prior * np.exp(query[current])
    denom = mass.sum(axis=-1, keepdims=True)
    weights = np.divide(mass, denom, out=np.zeros_like(mass), where=denom > 0)
    values = value[current]
    pooled = (weights * values).sum(axis=-1)
    logits = params[0] + np.einsum("ij,j->i", counts, params[1:split]) + pooled.sum(axis=1)
    return logits, weights, values, pooled


def attention_objective(params, counts, inputs, y):
    logits, weights, values, pooled = attention_scores(params, counts, inputs)
    residual = (expit(logits) - y) / len(y)
    loss = np.mean(np.logaddexp(0, logits) - y * logits)
    # Sum over subjects and positions of each current symbol to differentiate
    # the embedding tables; padding and the first event have zero weights.
    weighted = residual[:, None, None] * weights
    current = inputs[0]
    q_grad = weighted * (values - pooled[:, :, None])
    grad = np.r_[residual.sum(), np.einsum("ij,i->j", counts, residual),
                 np.stack([q_grad[current == i].sum(axis=0) for i in range(SYMBOLS)]).ravel(),
                 np.stack([weighted[current == i].sum(axis=0) for i in range(SYMBOLS)]).ravel()]
    penalty = .002
    grad[1:] += penalty * params[1:]
    return loss + .5 * penalty * np.square(params[1:]).sum(), grad


def fit_models(histories, y):
    counts, ordered = encode(histories)
    models = dict(
        count_tree=DecisionTreeClassifier(max_depth=4, min_samples_leaf=30, random_state=SEED).fit(counts, y),
        count_lr=LogisticRegression(C=1, max_iter=400).fit(csr_matrix(counts), y),
        transition_lr=LogisticRegression(C=1, max_iter=400).fit(csr_matrix(ordered), y),
    )
    initial = np.zeros(1 + SYMBOLS + 2 * SYMBOLS ** 2)
    fit = minimize(attention_objective, initial, args=(counts, attention_input(histories), y),
                   jac=True, method="L-BFGS-B", bounds=[(-6, 6)] * len(initial),
                   options={"maxiter": 200, "ftol": 1e-10})
    if not fit.success:
        raise RuntimeError("attention optimizer did not converge: " + str(fit.message))
    return models, fit.x


def predict(fits, histories):
    models, params = fits
    counts, ordered = encode(histories)
    scores = {name: model.predict_proba(csr_matrix(ordered if name == "transition_lr" else counts))[:, 1]
              for name, model in models.items()}
    logits, *_ = attention_scores(params, counts, attention_input(histories))
    scores["causal_attention"] = expit(logits)
    return scores


def paired_interval(labels, a, b):
    rng = np.random.default_rng(SEED + 3)
    diffs = []
    for _ in range(200):
        indices = rng.integers(len(labels), size=len(labels))
        if len(np.unique(labels[indices])) == 2:
            diffs.append(average_precision_score(labels[indices], a[indices]) -
                         average_precision_score(labels[indices], b[indices]))
    return dict(estimate=float(average_precision_score(labels, a) - average_precision_score(labels, b)),
                ci95=np.quantile(diffs, [.025, .975]).tolist(), valid_repeats=len(diffs))


def summarize(rows, scores):
    y = np.array([row.label for row in rows])
    return dict(n=len(rows), positives=int(y.sum()), prevalence=float(y.mean()),
                ap={name: float(average_precision_score(y, s)) for name, s in scores.items()},
                paired_transition_minus_count_lr=paired_interval(y, scores["transition_lr"], scores["count_lr"]))


def run():
    phases = simulate()
    output = dict(seed=SEED, alphabet=["A", "B", "C", "D"], history_length=[5, MAX_LENGTH],
                  model_fit_phase="train", threshold_selection=False, synthetic=True,
                  score_metric="average precision", bootstrap_unit="independent subject; fitted models fixed",
                  cohorts={}, evaluations={})
    for phase, rows in phases.items():
        encoded = [[r.subject, r.decision, r.mature, list(r.history), r.label] for r in rows]
        digest = hashlib.sha256(json.dumps(encoded, separators=(",", ":")).encode()).hexdigest()
        output["cohorts"][phase] = dict(subject_range=[rows[0].subject, rows[-1].subject],
                                        first_decision=rows[0].decision, last_decision=rows[-1].decision,
                                        last_label_available=rows[-1].mature, n=len(rows),
                                        positives=sum(r.label for r in rows), rows_sha256=digest)
    with threadpool_limits(limits=1):
        train = phases["train"]
        fits = fit_models([r.history for r in train], np.array([r.label for r in train]))
        models, params = fits
        alphabet = output["alphabet"]
        coef = models["transition_lr"].coef_[0, SYMBOLS:].reshape(SYMBOLS, SYMBOLS)
        output["fit"] = dict(
            transition_coefficients={prev + nxt: float(coef[i, j])
                                     for i, prev in enumerate(alphabet) for j, nxt in enumerate(alphabet)},
            tree_max_depth=models["count_tree"].max_depth,
            tree_min_leaf=models["count_tree"].min_samples_leaf,
            lr_C=models["transition_lr"].C,
            attention_log_lag_decay=FEATURE_DECAY,
            attention_parameters=len(params), attention_optimizer="L-BFGS-B",
            attention_l2=.002, attention_parameter_bounds=[-6, 6], attention_converged=True,
            shuffle_seed=SEED + 2, bootstrap_seed=SEED + 3,
        )
        for phase in ("validation", "stable_oot", "reversed_oot"):
            rows = phases[phase]
            histories = [r.history for r in rows]
            scores = predict(fits, histories)
            output["evaluations"][phase] = summarize(rows, scores)
            if phase == "stable_oot":
                rng = np.random.default_rng(SEED + 2)
                shuffled = [rng.permutation(history).tolist() for history in histories]
                fresh = predict(fits, shuffled)
                control = summarize(rows, fresh)
                control["max_count_score_change"] = float(max(
                    np.max(np.abs(scores[name] - fresh[name])) for name in ("count_tree", "count_lr")))
                output["evaluations"]["stable_oot_within_subject_shuffle"] = control
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="output JSON path within the current workspace")
    args = parser.parse_args()
    path = workspace_path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run(), indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
