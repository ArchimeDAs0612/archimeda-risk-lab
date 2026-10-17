"""Rolling-origin model/Pattern validation and falsifiable drift monitoring.

All outcomes here are independent simulator audits, not observed production
labels. Controlled monitor shifts deliberately operate inside an evaluator.
"""
import time
import math
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from .contracts import RAW_FEATURES, SCORE_FEATURES
from .data import split_samples
from .entities import simulate_entities, build_enriched_samples
from .external_credit import fit_credit, discover_rule, rule_summary
from .models import probabilities, replay, complete_paths, verify_membership, metrics
from .research_models import rank_metrics
from .evidence import paired_ap_interval
from .pipeline import save_json, sha
from .field_intelligence import digest
from .study_contracts import workspace_path, bounded_integer


def ecdf_distance(a, b):
    """Two-sample KS statistic with exact ties; no unneeded asymptotic p-value."""
    a = np.sort(np.asarray(a, float)); b = np.sort(np.asarray(b, float))
    if not len(a) or not len(b) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('finite nonempty monitoring samples required')
    points = np.concatenate([a, b])
    return float(np.max(np.abs(np.searchsorted(a, points, side='right')/len(a)-np.searchsorted(b, points, side='right')/len(b))))


def monitor_statistics(reference, batch, features):
    if len(batch) == 0 or len(reference) == 0:
        raise ValueError('monitor requires reference and batch observations')
    distances = {name: ecdf_distance(reference[name], batch[name]) for name in features}
    ref_brier = np.mean((reference.score-reference.risk_label)**2)
    brier = np.mean((batch.score-batch.risk_label)**2)
    return dict(feature_distance=max(distances.values()), per_feature=distances,
                label_rate_difference=float(abs(batch.risk_label.mean()-reference.risk_label.mean())),
                brier_difference=float(abs(brier-ref_brier)))


def conditional_shift(batch):
    """Evaluation-only adversary: same X, same base rate, reversed score association."""
    changed = batch.copy()
    positives = int(batch.risk_label.sum())
    changed['risk_label'] = 0
    idx = np.argsort(batch.score.to_numpy(), kind='stable')[:positives]
    changed.iloc[idx, changed.columns.get_loc('risk_label')] = 1
    return changed


def run_monitor(pool, config):
    features = config['features']
    if features != ['amount', 'prior_score', 'account_age_days']:
        raise ValueError('unregistered monitored features')
    calibration_n = bounded_integer(config['null_calibration_repeats'], 'null repeats', 20, 300)
    evaluation_n = bounded_integer(config['evaluation_repeats'], 'monitor repeats', 20, 200)
    batch_n = bounded_integer(config['subjects_per_batch'], 'subjects per batch', 10, 100)
    bounded_integer(config['seed'], 'monitor seed', 0, 2**32-1)
    if config['scenarios'] != ['null', 'population_mix', 'label_prior', 'conditional_relationship']:
        raise ValueError('unregistered monitor scenarios')
    if not math.isclose(config['alpha'], .05, rel_tol=0, abs_tol=0):
        raise ValueError('unregistered alarm quantile')
    users = sorted(pool.user_id.unique())
    rng = np.random.default_rng(config['seed'])
    users = np.array(users)[rng.permutation(len(users))]
    reference = pool[pool.user_id.isin(users[:len(users)//2])].copy().reset_index(drop=True)
    evaluation = pool[~pool.user_id.isin(users[:len(users)//2])].copy().reset_index(drop=True)
    groups_ref = list(reference.groupby('user_id', sort=True).indices.values())
    groups_eval = list(evaluation.groupby('user_id', sort=True).indices.values())
    if not groups_ref or not groups_eval:
        raise ValueError('monitor needs disjoint nonempty subject pools')
    def draw(frame, groups, weights=None):
        selected = rng.choice(len(groups), size=batch_n, replace=True, p=weights)
        return frame.iloc[np.concatenate([groups[i] for i in selected])].reset_index(drop=True)
    null = [monitor_statistics(reference, draw(reference, groups_ref), features) for _ in range(min(calibration_n, 300))]
    names = ['feature_distance', 'label_rate_difference', 'brier_difference']
    thresholds = {name: float(np.quantile([r[name] for r in null], .95)) for name in names}
    amount_mean = np.array([evaluation.iloc[g].amount.mean() for g in groups_eval])
    risk_mean = np.array([evaluation.iloc[g].risk_label.mean() for g in groups_eval])
    mixture = np.where(amount_mean > reference.amount.median(), 5., 1.); mixture /= mixture.sum()
    prior = 1+20*risk_mean; prior /= prior.sum()
    trials = []
    for repetition in range(min(evaluation_n, 200)):
        baseline = draw(evaluation, groups_eval)
        batches = dict(null=baseline, population_mix=draw(evaluation, groups_eval, mixture),
                       label_prior=draw(evaluation, groups_eval, prior), conditional_relationship=conditional_shift(baseline))
        for scenario, batch in batches.items():
            statistics = monitor_statistics(reference, batch, features)
            trials.append(dict(repetition=repetition, scenario=scenario, n=len(batch),
                               alarms={k: statistics[k] > thresholds[k] for k in names},
                               statistics=statistics, risk_rate=float(batch.risk_label.mean())))
    summary = {}
    for name in config['scenarios']:
        rows = [r for r in trials if r['scenario'] == name]
        summary[name] = dict(batches=len(rows), alarm_rates={k: float(np.mean([r['alarms'][k] for r in rows])) for k in names},
                             mean_risk_rate=float(np.mean([r['risk_rate'] for r in rows])))
    return dict(thresholds=thresholds, summary=summary, trials=trials,
                reference_users=len(groups_ref), evaluation_users=len(groups_eval), users_disjoint=True,
                calibration_scope='reference-user cluster bootstrap, maximum feature KS jointly calibrated, individual 95% thresholds; no universal error guarantee',
                limits=['resampled synthetic pool, not new real cohorts', 'label alarms require mature representative labels',
                        'pure feature monitoring cannot detect arbitrary conditional-outcome shifts',
                        'label-prior resampling also changes covariates through correlation; it is not isolated label shift identification'])


def run_rolling(config, out):
    out = workspace_path(out)
    bounded_integer(config['orders'], 'orders', 1000, 30000)
    bounded_integer(config['days'], 'days', 150, 180)
    bounded_integer(config['bootstrap_repeats'], 'bootstrap repeats', 20, 300)
    bounded_integer(config['seed'], 'seed', 0, 2**32-1)
    bounded_integer(config['tree_depth'], 'tree depth', 1, 6)
    bounded_integer(config['min_leaf'], 'minimum leaf', 10, 2000)
    bounded_integer(config['candidate_min_select'], 'candidate support', 10, 2000)
    if not math.isclose(config['review_fraction'], .1, rel_tol=0, abs_tol=0):
        raise ValueError('unregistered review fraction')
    if config['train_ends'] != [40, 70, 100] or config['models'] != ['lr', 'forest', 'hist_gradient']:
        raise ValueError('unregistered rolling design')
    if (config['maturity_gap'], config['selection_days'], config['test_days']) != (7, 15, 15):
        raise ValueError('rolling boundaries differ from registered design')
    if out.exists() and any(out.iterdir()):
        raise ValueError('choose empty output')
    out.mkdir(parents=True, exist_ok=True); start = time.perf_counter()
    save_json(out/'protocol.json', config)
    events, labels, _, _ = simulate_entities(config)
    sample, quality = build_enriched_samples(events, labels)
    columns = RAW_FEATURES+SCORE_FEATURES
    windows = []; first_rule = None; used_test_ids = set()
    with threadpool_limits(1):
        for train_end in config['train_ends']:
            select_start = train_end+7; select_end = select_start+15; test_start = select_end+7; test_end = test_start+15
            current = dict(config, train_end_day=train_end, train_asof_day=select_start,
                           select_start_day=select_start, select_end_day=select_end, select_asof_day=test_start,
                           test_start_day=test_start, days=test_end, evaluation_asof_day=test_end+7)
            parts = split_samples(sample, current)
            test_ids = set(parts['test'].event_id)
            if used_test_ids & test_ids:
                raise AssertionError('rolling test windows overlap')
            used_test_ids |= test_ids
            models = {kind: fit_credit(parts['train'], columns, kind, config['seed'], config) for kind in config['models']}
            select_scores = {kind: probabilities(model, parts['select']) for kind, model in models.items()}
            thresholds = {kind: float(np.quantile(p, .9)) for kind,p in select_scores.items()}
            selection = {kind: rank_metrics(parts['select'].risk_label,p,thresholds[kind]) for kind,p in select_scores.items()}
            winner = max(selection,key=lambda k:(selection[k]['ap'],k))
            rule_model, rule, candidates = discover_rule(parts['train'],parts['select'],columns,config,config['seed'])
            if first_rule is None:
                first_rule = (rule_model, rule)
            frozen = dict(winner=winner, thresholds=thresholds, selection=selection, rule=rule, candidates=candidates,
                           preprocessing=rule_model['prep'].metadata(),
                           split_ids={s:digest(sorted(f.event_id)) for s,f in parts.items()})
            save_json(out/f'frozen-{train_end}.json',frozen)
            test = parts['test']; y = test.risk_label.to_numpy(int)
            scores = {kind: probabilities(model,test) for kind,model in models.items()}
            comparisons = {kind: rank_metrics(y,p,thresholds[kind]) for kind,p in scores.items()}
            selected = replay(rule_model,test,rule); original = replay(first_rule[0],test,first_rule[1])
            seen = test.user_id.isin(parts['train'].user_id).to_numpy()
            windows.append(dict(train_end=train_end, select_interval=[select_start,select_end], test_interval=[test_start,test_end],
                                splits={s:len(f) for s,f in parts.items()}, frozen=frozen, models=comparisons,
                                paired_hgb_minus_lr=paired_ap_interval(test,scores['hist_gradient'],scores['lr'],config),
                                refit_rule=rule_summary(test,selected), original_rule_transfer=rule_summary(test,original),
                                new_vs_original_membership=rule_summary(test,selected,original),
                                exact_membership=verify_membership(rule_model,test,complete_paths(rule_model)),
                                cold_start={name:metrics(y[mask],scores[winner][mask],thresholds[winner]) for name,mask in [('seen',seen),('unseen',~seen)]}))
            last_pool = test.assign(score=scores[winner])
            save_json(out/'rolling-results.json', dict(windows=windows, protocol=config))
        last_pool.to_csv(out/'monitor-pool.csv', index=False)
        monitor = run_monitor(last_pool,config['monitor'])
    result = dict(protocol=config, windows=windows, monitor=monitor, quality=quality,
                  elapsed_seconds=time.perf_counter()-start, source_sha256=sha(Path(__file__)),
                  limitations=['synthetic temporal evaluation only', 'expanding training histories are dependent',
                               'three folds are not three independent business domains', 'no final-window model or threshold reselection'])
    save_json(out/'result.json',result)
    return result
