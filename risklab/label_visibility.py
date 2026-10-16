"""Fixed-model selective-label evaluation; oracle is synthetic, never imputed truth.

This is an identification experiment, not reject inference or policy uplift.
All regimes and the audit probability are fixed before their metrics are read.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .models import metrics
from .pipeline import save_json, sha


def identification_bounds(observed_y, observed, flagged):
    y=np.asarray(observed_y,dtype=float)
    observed=np.asarray(observed,dtype=bool)
    flagged=np.asarray(flagged,dtype=bool)
    if len(y)!=len(observed) or len(y)!=len(flagged) or not len(y):
        raise ValueError('invalid bound inputs')
    if not np.isfinite(y[observed]).all() or not np.isin(y[observed],[0,1]).all():
        raise ValueError('observed outcomes must be binary')
    positive=int(y[observed].sum()); total=len(y)
    unknown=int((~observed).sum())
    caught=int(y[observed & flagged].sum())
    uf=int((~observed & flagged).sum()); un=int((~observed & ~flagged).sum())
    lower=(caught/(positive+un) if positive+un else 1.) if positive+unknown else None
    upper=((caught+uf)/(positive+uf) if positive+uf else 0.) if positive+unknown else None
    return dict(n=total,observed=int(observed.sum()),unknown=unknown,
        prevalence=[positive/total,(positive+unknown)/total],
        recall=[lower,upper],point_identified=unknown==0,
        scope='sharp binary-outcome bounds with fixed decisions; unknown outcomes never zero-filled')


def analyze_visibility(frame, scores, threshold, seed=20261016):
    y=frame.risk_label.to_numpy(dtype=int); scores=np.asarray(scores,dtype=float)
    if len(scores)!=len(frame):raise ValueError('score alignment mismatch')
    observed_non_decline=frame.action.ne('decline').to_numpy()
    settled=frame.payment_result.eq(1).to_numpy()
    rng=np.random.default_rng(seed)
    random_decline_audit=observed_non_decline | (rng.random(len(frame))<.25)
    regimes={'full_independent_audit':np.ones(len(frame),dtype=bool),
             'non_declined_only':observed_non_decline,'settled_only':settled,
             'random_25pct_decline_audit':random_decline_audit}
    rows=[]
    flagged=scores>=threshold
    for name,observed in regimes.items():
        # Hide first: all deployable bounds receive only visible outcomes.
        visible=np.where(observed,y,np.nan)
        row=dict(regime=name,observed=int(observed.sum()),missing=int((~observed).sum()),
            naive_observed_metrics=metrics(y[observed],scores[observed],threshold),
            bounds=identification_bounds(visible,observed,flagged))
        if name=='random_25pct_decline_audit':
            propensity=np.where(observed_non_decline,1.,.25)
            weights=1/propensity[observed]
            # Ratio estimate has sampling error, not equality with the oracle.
            row['known_design_ipw_prevalence']=float(np.sum(weights*y[observed])/weights.sum())
            row['ipw_scope']='known randomized audit design only; deterministic missingness has zero propensity and is not IPW-identifiable'
        rows.append(row)
    return dict(oracle=metrics(y,scores,threshold),regimes=rows,
        conclusion='Observed-subset AP/recall describe different populations. Missing outcomes do not identify attempted-population metrics or policy gain.',
        policy_scope='No counterfactual behavioral outcomes; even complete synthetic oracle is not causal business evidence.',
        seed=seed,audit_probability=.25,model_selection='frozen before visibility analysis; no retraining or reselection')


def run_label_study(data_dir,out):
    data_dir=Path(data_dir);out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('output must be absent or empty')
    result=json.loads((data_dir/'result.json').read_text())
    sample=pd.read_csv(data_dir/'samples.csv',float_precision='round_trip').set_index('event_id')
    predictions=pd.read_csv(data_dir/'predictions.csv',float_precision='round_trip')
    if predictions.event_id.duplicated().any():raise ValueError('duplicate prediction identity')
    frame=sample.loc[predictions.event_id].reset_index()
    if not np.array_equal(frame.risk_label.to_numpy(),predictions.risk_label.to_numpy()):
        raise ValueError('labels/predictions misaligned')
    frozen=result['frozen_selection']['models'];winner=frozen['selected_model']
    analysis=analyze_visibility(frame,predictions[winner].to_numpy(),frozen['thresholds'][winner])
    analysis['provenance']=dict(model=winner,inputs={name:sha(data_dir/name) for name in ['result.json','samples.csv','predictions.csv','frozen_selection.json']})
    save_json(out/'result.json',analysis)
    from .report import shell,table
    rows=[dict(regime=r['regime'],observed=r['observed'],missing=r['missing'],
          ap=r['naive_observed_metrics']['ap'],recall=r['naive_observed_metrics'].get('recall'),
          prevalence_bounds=str(r['bounds']['prevalence']),recall_bounds=str(r['bounds']['recall'])) for r in analysis['regimes']]
    body='<p class="notice">固定模型；独立模拟审计仅作 oracle 对照。观测子集指标不能冒充全部尝试的泛化能力；未知标签不填零。</p>'
    body+=table(rows,[(k,k) for k in rows[0]])
    body+='<p>随机拒绝审计的已知抽样概率允许描述 IPW；确定性缺失的零概率区域无法靠权重识别。没有真实策略因果收益。</p>'
    (out/'index.html').write_text(shell('Selective-label identification study',body),encoding='utf-8')
    return analysis
