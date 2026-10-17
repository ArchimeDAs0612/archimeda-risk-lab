"""UCI observational credit study: frozen splits, selection, and exact leaf replay.

Raw data remain outside public artifacts. Identical observed feature profiles
share a split and bootstrap cluster; these are NOT claimed to be real entities.
No final labels enter fitting, calibration, threshold selection or rule choice.
"""
import copy
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from scipy.special import expit, logit
from scipy.sparse import csr_matrix
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from .models import (fit_model, complete_paths, replay, verify_membership, probabilities,
                     calibration)
from .research_models import rank_metrics
from .pipeline import save_json, sha
from .field_intelligence import digest


NAMES = ['LIMIT_BAL', 'SEX', 'EDUCATION', 'MARRIAGE', 'AGE', 'PAY_0', 'PAY_2',
         'PAY_3', 'PAY_4', 'PAY_5', 'PAY_6'] + [f'BILL_AMT{i}' for i in range(1, 7)] + [f'PAY_AMT{i}' for i in range(1, 7)]
STATUS = NAMES[5:11]
BILLS = NAMES[11:17]
PAYMENTS = NAMES[17:23]
FINANCIAL = ['LIMIT_BAL'] + STATUS + BILLS + PAYMENTS
INPUTS = {'status_only': STATUS, 'financial': FINANCIAL,
          'without_status': [x for x in FINANCIAL if x not in STATUS],
          'without_bills': [x for x in FINANCIAL if x not in BILLS],
          'without_payments': [x for x in FINANCIAL if x not in PAYMENTS]}


def read_credit(path, expected_sha256=None):
    if expected_sha256 and sha(path) != expected_sha256:
        raise ValueError('data checksum differs from registered source; do not silently update')
    raw = pd.read_csv(path)
    if list(raw) != ['ID'] + [f'X{i}' for i in range(1, 24)] + ['Y']:
        raise ValueError('unexpected UCI schema')
    if raw.ID.isna().any() or raw.ID.duplicated().any():
        raise ValueError('missing/duplicate record ID')
    if raw.isna().any().any() or not np.isfinite(raw.to_numpy(float)).all():
        raise ValueError('missing/nonfinite source values require a new data review')
    if not raw.Y.isin([0, 1]).all():
        raise ValueError('nonbinary target')
    return raw.rename(columns=dict(zip([f'X{i}' for i in range(1, 24)], NAMES), Y='risk_label'))


def profile_keys(frame):
    # Explicit numeric serialization is row-order and pandas-version invariant.
    return np.array([hashlib.sha256(json.dumps([float(v) for v in row],
                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()
                    for row in frame[NAMES].to_numpy()])


def assign_splits(frame, seed):
    keys = profile_keys(frame)
    u = np.array([int(hashlib.sha256(f'{seed}:{k}'.encode()).hexdigest()[:16], 16) / 2**64 for k in keys])
    labels = np.select([u < .6, u < .7, u < .8], ['train', 'calibration', 'select'], default='test')
    return frame.assign(profile_key=keys, split=labels).sort_values('ID').reset_index(drop=True)


class CreditEncoder:
    """Train-only one-hot repayment codes, including undocumented -2/0 as codes.

    Nominal status avoids silently interpreting -2 as better repayment than -1.
    Numeric amounts use the existing train-only median/missing transform later.
    """
    def fit(self, train):
        self.categorical = OneHotEncoder(handle_unknown='ignore', sparse_output=False,
                                         dtype=np.float32).fit(train[STATUS])
        self.names = self.categorical.get_feature_names_out(STATUS).tolist()
        return self

    def transform(self, frame):
        result = frame.drop(columns=STATUS).copy()
        values = self.categorical.transform(frame[STATUS])
        for i, name in enumerate(self.names):
            result[name] = values[:, i]
        return result

    def columns(self, source):
        return [c for c in source if c not in STATUS] + [n for n in self.names if any(n.startswith(c+'_') for c in source if c in STATUS)]


def fit_credit(train, columns, kind, seed, config):
    if kind in ('lr', 'tree'):
        return fit_model(train, columns, kind, dict(config, seed=seed))
    from .models import Transform
    prep = Transform(columns).fit(train)
    if kind == 'forest':
        model = RandomForestClassifier(n_estimators=120, max_depth=7, min_samples_leaf=35,
                                       max_features='sqrt', n_jobs=1, random_state=seed)
    elif kind == 'hist_gradient':
        model = HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=15,
                                               min_samples_leaf=35, learning_rate=.07,
                                               l2_regularization=1., early_stopping=False,
                                               random_state=seed)
    else:
        raise ValueError('unregistered model')
    model.fit(prep.apply(train), train.risk_label.to_numpy(int))
    return dict(prep=prep, scaler=None, model=model, kind=kind)


def paired_profile_interval(frame, a, b, repeats, seed):
    y = frame.risk_label.to_numpy(int)
    groups = list(frame.groupby('profile_key', sort=True).indices.values())
    rng = np.random.default_rng(seed)
    differences = []
    for _ in range(repeats):
        idx = np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))])
        if len(np.unique(y[idx])) == 2:
            differences.append(average_precision_score(y[idx], a[idx]) - average_precision_score(y[idx], b[idx]))
    return dict(estimate=float(average_precision_score(y, a)-average_precision_score(y, b)),
                ci95=np.quantile(differences, [.025, .975]).tolist(), repeats=len(differences),
                unit='paired identical-feature-profile clusters, not verified clients',
                scope='conditional sampling uncertainty of frozen models; no temporal transport inference')


def wilson_lower(positive, n):
    if n == 0:
        return 0.
    z = 1.96
    p = positive/n
    return float((p+z*z/(2*n)-z*np.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n))


def fixed_capacity(y, scores, identities, fraction=.1):
    """Prespecified quota; deterministic ID tie-break never uses outcome labels."""
    y, scores, identities = np.asarray(y), np.asarray(scores), np.asarray(identities)
    if len(set(identities)) != len(y) or len(scores) != len(y) or not 0 < fraction <= 1:
        raise ValueError('invalid capacity inputs')
    n = int(np.floor(len(y)*fraction))
    selected = np.lexsort((identities, -scores))[:n]
    return dict(capacity=n, positives=int(y[selected].sum()),
                precision=float(y[selected].mean()) if n else None,
                recall=float(y[selected].sum()/y.sum()) if y.sum() else None,
                scope='fixed floor(N*fraction) capacity, descending score then record ID; no label-based tie selection')


def discover_rule(train, select, columns, config, seed):
    bundle = fit_credit(train, columns, 'tree', seed, config)
    paths = complete_paths(bundle)
    rows = []
    for path in paths:
        mask = replay(bundle, select, path)
        n = int(mask.sum())
        positives = int(select.loc[mask, 'risk_label'].sum())
        rows.append(dict(path=path, selection_n=n, selection_positives=positives,
                         wilson_lower=wilson_lower(positives, n),
                         eligible=n >= config['candidate_min_select']))
    eligible = [r for r in rows if r['eligible']]
    if not eligible:
        raise ValueError('no rule satisfies frozen selection support; report failure, never relax')
    chosen = max(eligible, key=lambda r: (r['wilson_lower'], r['selection_n'], -r['path']['leaf_id']))
    return bundle, chosen['path'], rows


def rule_summary(frame, mask, baseline=None):
    mask = np.asarray(mask, bool)
    y = frame.risk_label.to_numpy(int)
    n = int(mask.sum())
    result = dict(n=n, positives=int(y[mask].sum()), coverage=float(mask.mean()),
                  rate=float(y[mask].mean()) if n else None,
                  enrichment=float(y[mask].mean()/y.mean()) if n and y.mean() else None)
    if baseline is not None:
        result.update(overlap=int((mask & baseline).sum()), added=int((mask & ~baseline).sum()),
                      removed=int((~mask & baseline).sum()),
                      jaccard=float((mask & baseline).sum()/(mask | baseline).sum()) if (mask | baseline).any() else 1.)
    return result


def rule_variants(bundle, path, train):
    variants = {'full': copy.deepcopy(path), 'drop_last': dict(origin_leaf_id=path['leaf_id'],
                predicates=copy.deepcopy(path['predicates'][:-1]), kind='new_simplified_candidate')}
    scale = bundle['prep'].apply(train).std(axis=0)
    for name, sign in [('threshold_minus', -1), ('threshold_plus', 1)]:
        changed = dict(origin_leaf_id=path['leaf_id'], predicates=copy.deepcopy(path['predicates']), kind='new_perturbed_candidate')
        for term in changed['predicates']:
            if term['transformed_feature'] in ['LIMIT_BAL']+BILLS+PAYMENTS:
                term['threshold'] += sign*.05*float(scale[term['feature_index']])
        variants[name] = changed
    return variants


def counterchecks(frame, mask, limit_edges):
    rows = []
    band = pd.cut(frame.LIMIT_BAL, limit_edges, include_lowest=True)
    for group, sub in frame.assign(band=band, candidate=mask).groupby('band', observed=True):
        a, b = sub[sub.candidate], sub[~sub.candidate]
        supported = len(a) >= 20 and len(b) >= 20
        rows.append(dict(band=str(group), candidate_n=len(a), control_n=len(b), supported=supported,
                         difference=float(a.risk_label.mean()-b.risk_label.mean()) if supported else None))
    matched = sum(r['candidate_n'] for r in rows if r['supported'])
    profile_counts = frame.loc[mask, 'profile_key'].value_counts()
    return dict(limit_strata=rows, common_support_candidate_n=matched, candidate_n=int(mask.sum()),
                common_support_fraction=matched/int(mask.sum()) if mask.any() else None,
                max_identical_profile_share=float(profile_counts.iloc[0]/mask.sum()) if mask.any() else None,
                source_proxy='not identifiable: one source and no collection-site field',
                missingness='original numeric source has no NA; nonstandard repayment codes retained explicitly',
                scope='descriptive credit-limit adjustment only; neither causal matching nor true entity control')


def run_credit(data, out, config):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('choose an empty output; accepted runs are immutable')
    out.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    save_json(out/'protocol.json', config)
    raw = read_credit(data, config['source_sha256'])
    assigned = assign_splits(raw, config['split_seed'])
    parts = {s: assigned[assigned.split == s].copy().reset_index(drop=True) for s in ['train', 'calibration', 'select', 'test']}
    encoder = CreditEncoder().fit(parts['train'])
    encoded = {s: encoder.transform(f) for s, f in parts.items()}
    provenance = dict(data_sha256=sha(data), protocol_sha256=digest(config), python=platform.python_version(),
                      sklearn=sklearn.__version__, numpy=np.__version__, pandas=pd.__version__,
                      source_sha256={p.name: sha(p) for p in [Path(__file__), Path(__file__).with_name('models.py'), Path(__file__).with_name('research_models.py')]},
                      split_counts={s: len(f) for s, f in parts.items()},
                      split_id_sha256={s: digest(sorted(f.ID.tolist())) for s, f in parts.items()},
                      onehot_categories=[a.tolist() for a in encoder.categorical.categories_],
                      cpu_threads=1, raw_records_published=False)
    save_json(out/'provenance.json', provenance)
    quality = dict(rows=len(raw), unique_ID=int(raw.ID.nunique()), missing=int(raw.isna().sum().sum()),
                   duplicate_feature_rows=int(raw[NAMES].duplicated().sum()),
                   unique_feature_profiles=int(assigned.profile_key.nunique()),
                   conflicting_label_profiles=int((assigned.groupby('profile_key').risk_label.nunique()>1).sum()),
                   repayment_codes={c: sorted(raw[c].unique().tolist()) for c in STATUS},
                   undocumented_education_codes=sorted(set(raw.EDUCATION)-{1, 2, 3, 4}),
                   undocumented_marriage_codes=sorted(set(raw.MARRIAGE)-{1, 2, 3}),
                   split_profile_overlap=any(set(parts[a].profile_key)&set(parts[b].profile_key) for i, a in enumerate(parts) for b in list(parts)[i+1:]),
                   time_claim='single 2005 observation cohort; monthly predictors are not multiple evaluation cohorts',
                   selection='existing card clients; original recruitment probabilities and operational label delays unavailable')
    save_json(out/'quality.json', quality)
    models, selection, thresholds, fit_seconds = {}, {}, {}, {}
    # Predeclared finite matrix: main-input seeds measure algorithm variation;
    # ablations use one primary seed and never nominate a new winner on final.
    with threadpool_limits(limits=1):
        for kind in config['models']:
            for input_name in config['inputs']:
                seeds = config['seeds'] if input_name == 'financial' else [config['primary_seed']]
                for seed in seeds:
                    name = f'{kind}/{input_name}/{seed}'
                    tic = time.perf_counter()
                    bundle = fit_credit(encoded['train'], encoder.columns(INPUTS[input_name]), kind, seed, config)
                    models[name] = bundle
                    p = probabilities(bundle, encoded['select'])
                    threshold = float(np.quantile(p, 1-config['review_fraction']))
                    thresholds[name] = threshold
                    selection[name] = rank_metrics(parts['select'].risk_label, p, threshold)
                    fit_seconds[name] = time.perf_counter()-tic
        choices = [f'{k}/financial/{config["primary_seed"]}' for k in config['models']]
        winner = max(choices, key=lambda k: (selection[k]['ap'], k))
        rule_model, rule, candidates = discover_rule(encoded['train'], encoded['select'], encoder.columns(FINANCIAL), config, config['primary_seed'])
        variants = rule_variants(rule_model, rule, encoded['train'])
        # Calibration has its own dev subset; cost thresholds on select only.
        pcal = probabilities(models[winner], encoded['calibration'])
        calibrator = LogisticRegression(C=1e6, solver='liblinear', max_iter=1000).fit(
            logit(np.clip(pcal, 1e-6, 1-1e-6)).reshape(-1, 1), parts['calibration'].risk_label)
        def calibrate(p):
            z = logit(np.clip(p, 1e-6, 1-1e-6))
            return expit(z*calibrator.coef_[0, 0]+calibrator.intercept_[0])
        select_p = probabilities(models[winner], encoded['select'])
        cost_choices = {}
        for label, p in [('original', select_p), ('calibrated', calibrate(select_p))]:
            cost_choices[label] = {}
            for ratio in config['cost_ratios']:
                grid = np.linspace(0, 1, 101)
                y = parts['select'].risk_label.to_numpy(int)
                costs = [np.mean((p>=t)*(1-y)+(p<t)*y*ratio) for t in grid]
                cost_choices[label][str(ratio)] = float(grid[np.argmin(costs)])
        frozen = dict(winner=winner, selection=selection, thresholds=thresholds,
                       candidates=candidates, chosen_rule=rule, variants=variants,
                       preprocessing=rule_model['prep'].metadata(),
                       cost_choices=cost_choices, calibration_slope=float(calibrator.coef_[0, 0]),
                       calibration_intercept=float(calibrator.intercept_[0]),
                       fit_scope='train; calibration subset for sigmoid only; select for choice; final unseen',
                       protocol_sha256=digest(config))
        save_json(out/'frozen_selection.json', frozen)
        # No final evaluation above this line. Save freeze before any test use.
        test = encoded['test']; final = parts['test']; y = final.risk_label.to_numpy(int)
        predictions = {name: probabilities(b, test) for name, b in models.items()}
        comparison = {name: rank_metrics(y, p, thresholds[name]) for name, p in predictions.items()}
        capacities = {name: fixed_capacity(y, p, final.ID) for name, p in predictions.items()}
        reference = f'lr/financial/{config["primary_seed"]}'
        intervals = {name: paired_profile_interval(final, predictions[name], predictions[reference], config['bootstrap_repeats'], 9821)
                     for name in choices if name != reference}
        membership = {s: verify_membership(rule_model, f, complete_paths(rule_model)) for s, f in encoded.items()}
        full = replay(rule_model, test, rule)
        variants_results = {name: rule_summary(final, replay(rule_model, test, path), full) for name, path in variants.items()}
        fixed_stability = {s: rule_summary(parts[s], replay(rule_model, f, rule)) for s, f in encoded.items()}
        original_select = replay(rule_model, encoded['select'], rule)
        rng = np.random.default_rng(1771)
        groups = list(encoded['train'].groupby('profile_key', sort=True).indices.values())
        rediscovery = []
        for repetition in range(config['rediscovery_repeats']):
            idx = np.concatenate([groups[i] for i in rng.integers(len(groups), size=len(groups))])
            b, path, found = discover_rule(encoded['train'].iloc[idx], encoded['select'], encoder.columns(FINANCIAL), config, 1771+repetition)
            rediscovery.append(dict(repetition=repetition, path=path, candidate_count=len(found),
                                    selection=rule_summary(parts['select'], replay(b, encoded['select'], path), original_select)))
        edges = [-np.inf] + np.unique(np.quantile(parts['train'].LIMIT_BAL, [.25, .5, .75])).tolist() + [np.inf]
        checks = counterchecks(final, full, edges)
        # Transfer stress is an explicit hypothetical coding/amount shift, not OOT.
        shifted = final.copy(); shifted['LIMIT_BAL'] = shifted.LIMIT_BAL*.75
        migration = rule_summary(final, replay(rule_model, encoder.transform(shifted), rule), full)
        selected_p = predictions[winner]; calibrated_p = calibrate(selected_p)
        decisions = []
        for name, p in [('original', selected_p), ('calibrated', calibrated_p)]:
            for ratio in config['cost_ratios']:
                t = cost_choices[name][str(ratio)]; flag = p >= t
                decisions.append(dict(model=name, cost_ratio=ratio, threshold=t, review_n=int(flag.sum()),
                                      legitimate_flagged=int((flag & (y==0)).sum()), missed_defaults=int((~flag & (y==1)).sum()),
                                      assumed_cost_per_client=float(np.mean(flag*(1-y)+(~flag)*y*ratio))))
        slices = []
        for column, masks in [('SEX', [(str(v), final.SEX==v) for v in [1, 2]]),
                              ('AGE', [('under30', final.AGE<30), ('30plus', final.AGE>=30)])]:
            for value, mask in masks:
                slices.append(dict(field=column, value=value, metrics=rank_metrics(y[mask], selected_p[mask], thresholds[winner])))
        train_pred = probabilities(models[reference], encoded['train'])
        b = models[reference]; x = b['scaler'].transform(b['prep'].apply(encoded['train']))
        # Sparse sklearn inference avoids a diagnosed macOS dense-BLAS floating
        # exception without suppressing warnings or changing model parameters.
        reference_error = float(np.max(np.abs(train_pred-b['model'].predict_proba(csr_matrix(x))[:, 1])))
        output = dict(provenance=provenance, quality=quality, winner=winner, models=comparison, fixed_capacity=capacities,
                      paired_ap_vs_lr=intervals, fit_seconds=fit_seconds,
                      pattern=dict(frozen_rule=rule, candidates=candidates, membership=membership,
                                   variants=variants_results, fixed_stability=fixed_stability, rediscovery=rediscovery,
                                   counterchecks=checks, credit_limit_shift_scenario=migration,
                                   baseline_overlap=rule_summary(final, full, selected_p>=thresholds[winner]),
                                   conclusion='frozen exploratory association; variant results are not a new selection step; no causal or temporal claim'),
                      calibration=dict(original=rank_metrics(y, selected_p, thresholds[winner]),
                                       sigmoid=rank_metrics(y, calibrated_p, float(np.quantile(calibrate(select_p), .9))),
                                       original_bins=calibration(y, selected_p), sigmoid_bins=calibration(y, calibrated_p),
                                       slope=float(calibrator.coef_[0, 0]), positive_monotone=bool(calibrator.coef_[0, 0]>0),
                                       decisions=decisions), slices=slices,
                      reference_implementation=dict(lr_probability_max_error=reference_error, tree_membership=membership),
                      elapsed_seconds=time.perf_counter()-start,
                      limitations=config['limits'])
        save_json(out/'result.json', output)
        # Individual derived records remain local; only aggregate evidence is released.
        pd.DataFrame(dict(record_id=final.ID, label=y, **{k.replace('/', '_'): v for k, v in predictions.items()})).to_csv(out/'private_predictions.csv', index=False)
    return output
