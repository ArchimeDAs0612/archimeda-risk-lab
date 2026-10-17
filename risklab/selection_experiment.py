"""Extend selective-label study with actual weighted fitting and label maturity.

Oracle outcomes are isolated in an evaluator object. Training and selection
receive only observed labels and known randomized inclusion probabilities.
No use of payment success or later-pass proxies as a surrogate truth label.
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .contracts import RAW_FEATURES, SCORE_FEATURES
from .data import build_samples
from .generate import simulate, DAY, ORIGIN
from .models import Transform, probabilities, metrics
from .label_visibility import identification_bounds
from .pipeline import save_json, sha
from .field_intelligence import digest


def maturity_probability(decision_ts, asof, minimum, maximum):
    if not 0 <= minimum < maximum:
        raise ValueError('delay bounds invalid')
    age = (asof-np.asarray(decision_ts))/DAY
    return np.clip((age-minimum)/(maximum-minimum), 0, 1)


def observe(frame, truth, asof, audit_probability, delay_min, delay_max, seed):
    if not 0 <= audit_probability <= 1:
        raise ValueError('invalid audit probability')
    forbidden = {'risk_label', 'label_available_ts', 'oracle', 'hidden_propensity'}
    if forbidden & set(frame):
        raise ValueError('observation input must exclude oracle labels and maturity fields')
    if len(truth) != len(frame):
        raise ValueError('truth alignment mismatch')
    rng = np.random.default_rng(seed)
    audit_pi = np.where(frame.action.eq('decline'), audit_probability, 1.)
    maturity = maturity_probability(frame.decision_ts, asof, delay_min, delay_max)
    # Audit independent of outcome given known action; delay uniform independent
    # of outcome given current timestamp. Payment success is a separate event.
    audited = rng.random(len(frame)) < audit_pi
    arrival = frame.decision_ts.to_numpy()+rng.uniform(delay_min, delay_max, len(frame))*DAY
    observed = audited & (arrival <= asof)
    visible = frame.copy()
    visible['risk_label'] = np.where(observed, truth, np.nan)
    visible['observed'] = observed
    visible['inclusion_probability'] = audit_pi*maturity
    return visible


def identifiable(frame):
    pi = frame.inclusion_probability.to_numpy(float)
    return bool(np.isfinite(pi).all() and (pi > 0).all() and (pi <= 1).all())


def weighted_estimates(visible, p, threshold):
    if not identifiable(visible):
        return dict(status='NOT_IDENTIFIED', reason='zero or invalid inclusion probability in target population')
    seen = visible.observed.to_numpy(bool)
    y = visible.loc[seen, 'risk_label'].to_numpy(float)
    if not len(y) or not np.isfinite(y).all() or not np.isin(y, [0, 1]).all():
        raise ValueError('observed binary labels required')
    w = 1/visible.loc[seen, 'inclusion_probability'].to_numpy(float)
    flag = np.asarray(p)[seen] >= threshold
    return dict(status='KNOWN_DESIGN_ESTIMATE', prevalence=float(np.sum(w*y)/w.sum()),
                recall=float(np.sum(w*y*flag)/np.sum(w*y)) if np.sum(w*y) else None,
                precision=float(np.sum(w*y*flag)/np.sum(w*flag)) if np.sum(w*flag) else None,
                ap=float(average_precision_score(y, np.asarray(p)[seen], sample_weight=w)) if len(np.unique(y)) == 2 else None,
                effective_sample_size=float(w.sum()**2/np.sum(w*w)), max_weight=float(w.max()),
                scope='Hajek ratio and weighted AP; known positive audit*maturity design, finite-sample error remains')


def fit_visible(visible, columns, weighted, seed):
    if weighted and not identifiable(visible):
        raise ValueError('cannot IPW fit target with zero probability')
    train = visible.loc[visible.observed].copy()
    prep = Transform(columns).fit(train)
    x = prep.apply(train)
    w = 1/train.inclusion_probability.to_numpy(float) if weighted else np.ones(len(train))
    # Identical unweighted observed-train preprocessing in both arms isolates
    # loss reweighting; neither oracle nor final information is supplied.
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=1., solver='liblinear', max_iter=1000, random_state=seed)
    model.fit(scaler.transform(x), train.risk_label.to_numpy(int), sample_weight=w)
    return dict(prep=prep, scaler=scaler, model=model, kind='lr')


def policy_summary(frame, y, candidate, legitimate_cost, action):
    baseline = frame.action.eq('decline').to_numpy()
    deny = baseline | candidate if action == 'decline' else baseline
    review = ((frame.action.eq('review').to_numpy()) | (candidate if action == 'review' else False)) & ~deny
    allowed_risk = (~deny) & (y == 1)
    disturbance = deny & (y == 0)
    return dict(action=action, declines=int(deny.sum()), reviews=int(review.sum()),
                legitimate_declines=int(disturbance.sum()), legitimate_reviews=int((review & (y==0)).sum()),
                risky_allowed=int(allowed_risk.sum()), risk_amount_exposed=float(frame.amount.to_numpy()[allowed_risk].sum()),
                simulated_cost=float(frame.amount.to_numpy()[allowed_risk].sum()+legitimate_cost*disturbance.sum()+.5*review.sum()),
                assumptions=dict(legitimate_decline_cost=legitimate_cost, review_cost=.5, risk_amount_loss=1., decline_prevents_all_loss=True,
                                 review_protection=0., behavior_change=False))


def run_selection_study(config, out):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('choose an empty output')
    out.mkdir(parents=True, exist_ok=True); tic = time.perf_counter()
    save_json(out/'protocol.json', config)
    events, labels = simulate(config)
    all_sample = build_samples(events, labels)
    # Only this simulator boundary sees truth. All model functions receive the
    # redacted visible frame; truth arrays stay separate through final selection.
    truth = all_sample.risk_label.to_numpy(int)
    features = all_sample.drop(columns=['risk_label', 'label_available_ts'])
    day = (features.decision_ts-ORIGIN)/DAY
    boundaries = {'train': (0, config['train_end_day'], config['train_asof_day']),
                  'select': (config['select_start_day'], config['select_end_day'], config['select_asof_day']),
                  'test': (config['test_start_day'], config['days'], config['evaluation_asof_day'])}
    parts, oracle, observed = {}, {}, {}
    for i, (name, (lo, hi, asof_day)) in enumerate(boundaries.items()):
        mask = ((day >= lo) & (day < hi)).to_numpy()
        parts[name] = features.loc[mask].reset_index(drop=True); oracle[name] = truth[mask]
        observed[name] = observe(parts[name], oracle[name], ORIGIN+asof_day*DAY, config['audit_probability'],
                                 config['delay_min_days'], config['delay_max_days'], config['seed']+i+51)
    columns = RAW_FEATURES+SCORE_FEATURES
    with threadpool_limits(1):
        bundles = {name: fit_visible(observed['train'], columns, weighted, config['seed'])
                   for name, weighted in [('observed_lr', False), ('ipw_lr', True)]}
    thresholds, select_metrics = {}, {}
    for name, bundle in bundles.items():
        p = probabilities(bundle, observed['select'])
        thresholds[name] = float(np.quantile(p, 1-config['review_fraction']))
        select_metrics[name] = weighted_estimates(observed['select'], p, thresholds[name])
    winner = max(select_metrics, key=lambda name: (select_metrics[name]['ap'], name))
    frozen = dict(winner=winner, thresholds=thresholds, selection=select_metrics, columns=columns,
                  fitted={name: dict(preprocessing=b['prep'].metadata(), coef=b['model'].coef_.tolist(), intercept=b['model'].intercept_.tolist()) for name, b in bundles.items()},
                  protocol_sha256=digest(config), oracle_used_for_selection=False)
    save_json(out/'frozen_selection.json', frozen)
    results = {}
    for name, bundle in bundles.items():
        p = probabilities(bundle, parts['test']); threshold = thresholds[name]
        visible = observed['test']; seen = visible.observed.to_numpy(bool)
        results[name] = dict(naive=metrics(visible.loc[seen, 'risk_label'], p[seen], threshold),
                             corrected=weighted_estimates(visible, p, threshold),
                             oracle_evaluation_only=metrics(oracle['test'], p, threshold))
    p = probabilities(bundles[winner], parts['test']); threshold = thresholds[winner]
    repeats = []
    for repetition in range(config['audit_repeats']):
        visible = observe(parts['test'], oracle['test'], ORIGIN+config['evaluation_asof_day']*DAY,
                          config['audit_probability'], config['delay_min_days'], config['delay_max_days'], 8100+repetition)
        seen = visible.observed.to_numpy(bool)
        corrected = weighted_estimates(visible, p, threshold)
        repeats.append(dict(repetition=repetition, naive_rate=float(visible.loc[seen, 'risk_label'].mean()),
                            corrected_rate=corrected['prevalence'], corrected_ap=corrected['ap'], observed=int(seen.sum())))
    failures = []
    for name, audit, asof in [('deterministic_decline', 0., config['evaluation_asof_day']),
                              ('early_censoring', config['audit_probability'], config['days'])]:
        visible = observe(parts['test'], oracle['test'], ORIGIN+asof*DAY, audit,
                          config['delay_min_days'], config['delay_max_days'], 7001)
        failures.append(dict(name=name, correction=weighted_estimates(visible, p, threshold),
                             zero_probability=int((visible.inclusion_probability==0).sum()),
                             bounds=identification_bounds(visible.risk_label, visible.observed, p>=threshold)))
    failures.extend([dict(name='outcome_dependent_unknown_delay', correction=dict(status='NOT_IDENTIFIED', reason='unknown P(observed|X,Y); audit propensity alone is insufficient')),
                     dict(name='settled_only', correction=dict(status='NOT_IDENTIFIED', reason='payment failure depends on risk and declined attempts never settle'))])
    y = oracle['test']; policies = []
    for cost in config['costs']:
        for policy in ['baseline', 'decline', 'review']:
            policies.append(policy_summary(parts['test'], y, np.zeros(len(y), bool) if policy=='baseline' else p>=threshold, cost,
                                           'decline' if policy=='baseline' else policy) | {'name': policy})
    seen_users = parts['test'].user_id.isin(parts['train'].user_id).to_numpy()
    subgroups = {name: metrics(y[mask], p[mask], threshold) for name, mask in [('seen_subject', seen_users), ('unseen_subject', ~seen_users)]}
    result = dict(protocol=config, frozen=frozen, models=results, audit_repeats=repeats, nonidentification=failures,
                  visibility={name: dict(n=len(f), observed=int(f.observed.sum()), min_probability=float(f.inclusion_probability.min())) for name,f in observed.items()},
                  separate_events=dict(payment_success=int(parts['test'].payment_result.sum()), risk_truth=int(y.sum()),
                                       observed_labels=int(observed['test'].observed.sum()),
                                       later_pass_proxy_used_as_truth=False),
                  policy_scenarios=policies, cold_start=subgroups, elapsed_seconds=time.perf_counter()-tic,
                  provenance=dict(source_sha256=sha(Path(__file__)), generator_sha256=sha(Path(__file__).with_name('generate.py')), seed=config['seed']),
                  limitations=['synthetic outcome and randomized audit assumptions', 'ratio correction is not exact truth',
                               'audit repeats measure selection sampling, not independent populations', 'no real intervention or causal uplift'])
    save_json(out/'result.json', result)
    # Reusable local holdout for bounded monitor experiments; no new model fitting.
    holdout = parts['test'].copy(); holdout['evaluation_truth'] = y; holdout['frozen_score'] = p
    holdout.to_csv(out/'monitor_holdout.csv', index=False)
    return result
