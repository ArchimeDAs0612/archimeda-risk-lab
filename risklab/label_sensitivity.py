"""Supplemental frozen protocol: regularization scale and misspecified maturity."""
import time
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from .selection_experiment import observe, fit_visible, maturity_probability, weighted_estimates
from .contracts import RAW_FEATURES, SCORE_FEATURES
from .generate import simulate, DAY, ORIGIN
from .data import build_samples
from .models import probabilities, metrics
from .pipeline import save_json, sha
from .study_contracts import workspace_path, label_config
from .field_intelligence import digest


def outcome_delay_observation(frame, truth, asof, audit_probability, seed):
    """Evaluator only: risk changes label delay. Exposes two contrasting pi's."""
    y=np.asarray(truth,int);rng=np.random.default_rng(seed)
    audit=np.where(frame.action.eq('decline'),audit_probability,1.)
    low=np.where(y==1,10.,2.);high=np.where(y==1,25.,15.)
    maturity=np.clip(((asof-frame.decision_ts.to_numpy())/DAY-low)/(high-low),0,1)
    audited=rng.random(len(frame))<audit
    visible=frame.copy()
    seen=audited & (frame.decision_ts.to_numpy()+rng.uniform(low,high)*DAY<=asof)
    visible['observed']=seen;visible['risk_label']=np.where(seen,y,np.nan)
    visible['inclusion_probability']=audit*maturity_probability(frame.decision_ts,asof,2,15)
    oracle_pi=audit*maturity
    return visible,oracle_pi


def run_sensitivity(config,out):
    label_config(config);out=workspace_path(out)
    if config['arms']!=['observed','ipw_raw','ipw_normalized'] or config['delay_by_outcome_days']!={'0':[2,15],'1':[10,25]}:
        raise ValueError('unregistered supplemental design')
    if out.exists() and any(out.iterdir()):raise ValueError('choose empty output')
    out.mkdir(parents=True,exist_ok=True);start=time.perf_counter();save_json(out/'protocol.json',config)
    events,labels=simulate(config);sample=build_samples(events,labels)
    truth=sample.risk_label.to_numpy(int);frame=sample.drop(columns=['risk_label','label_available_ts'])
    day=(frame.decision_ts-ORIGIN)/DAY;parts={};oracle={};visible={}
    boundaries=[('train',0,config['train_end_day'],config['train_asof_day']),
                ('select',config['select_start_day'],config['select_end_day'],config['select_asof_day']),
                ('test',config['test_start_day'],config['days'],config['evaluation_asof_day'])]
    for i,(name,lo,hi,asof) in enumerate(boundaries):
        mask=((day>=lo)&(day<hi)).to_numpy();parts[name]=frame.loc[mask].reset_index(drop=True);oracle[name]=truth[mask]
        visible[name]=observe(parts[name],oracle[name],ORIGIN+asof*DAY,config['audit_probability'],2,15,config['seed']+51+i)
    with threadpool_limits(1):
        bundles={name:fit_visible(visible['train'],RAW_FEATURES+SCORE_FEATURES,name!='observed',config['seed'],name=='ipw_normalized') for name in config['arms']}
    thresholds={};selection={};coefficients={}
    for name,bundle in bundles.items():
        p=probabilities(bundle,parts['select']);thresholds[name]=float(np.quantile(p,.9))
        selection[name]=weighted_estimates(visible['select'],p,thresholds[name]);coefficients[name]=bundle['model'].coef_.tolist()
    winner=max(selection,key=lambda k:(selection[k]['ap'],k))
    frozen=dict(winner=winner,thresholds=thresholds,selection=selection,coefficients=coefficients,protocol_sha256=digest(config))
    save_json(out/'frozen_selection.json',frozen)
    predictions={name:probabilities(b,parts['test']) for name,b in bundles.items()}
    models={name:metrics(oracle['test'],p,thresholds[name]) for name,p in predictions.items()}
    test=parts['test'];y=oracle['test'];p=predictions[winner];t=thresholds[winner]
    # Longer observation horizon gives strictly positive evaluator-known pi for
    # the risk-dependent delay. It does not make that pi known to the learner.
    asof=ORIGIN+(config['days']+12)*DAY;trials=[]
    for i in range(min(config['audit_repeats'],300)):
        wrong,correct_pi=outcome_delay_observation(test,y,asof,config['audit_probability'],32100+i)
        correct=wrong.copy();correct['inclusion_probability']=correct_pi
        trials.append(dict(repetition=i,naive=float(wrong.loc[wrong.observed,'risk_label'].mean()),
                           misspecified=weighted_estimates(wrong,p,t),evaluator_known=weighted_estimates(correct,p,t)))
    result=dict(protocol=config,frozen=frozen,models=models,oracle_rate=float(y.mean()),
                outcome_dependent_trials=trials,
                delay_summary={name:float(np.mean([r[name]['prevalence'] for r in trials])) for name in ['misspecified','evaluator_known']},
                naive_mean=float(np.mean([r['naive'] for r in trials])),
                raw_weight_sum=float((1/visible['train'].loc[visible['train'].observed,'inclusion_probability']).sum()),
                normalized_weight_sum=int(visible['train'].observed.sum()),
                source_sha256=sha(Path(__file__)),elapsed_seconds=time.perf_counter()-start,
                limitations=['unknown outcome-dependent pi is NOT_IDENTIFIED in actual use',
                             'evaluator-known weighting is a simulator diagnostic, not available correction',
                             'same observed preprocessing, normalized weights fix total loss scale but do not prove equal optimal regularization',
                             'one independent simulator seed; repeated observation draws are not independent target populations'])
    save_json(out/'result.json',result);return result
