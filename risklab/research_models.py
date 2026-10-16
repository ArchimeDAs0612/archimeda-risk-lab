"""V0.2 comparable feature inputs, frozen selection, rank metrics and limited diagnostics."""
import hashlib
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_curve,precision_recall_curve
from .models import fit_model,probabilities,Transform,metrics
from .contracts import RAW_FEATURES,SCORE_FEATURES
from .entities import EXTENDED_FEATURES,WINDOW_FEATURES,ENTITY_FEATURES,PAYLOAD_FEATURES
from .evidence import paired_ap_interval
from .generate import ORIGIN,DAY

FULL = RAW_FEATURES+SCORE_FEATURES+EXTENDED_FEATURES


def rank_metrics(y,p,threshold):
    result=metrics(y,p,threshold)
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    if len(np.unique(y))<2:
        return dict(result,ks=None,pr_auc_trapezoid=None,lift_top_decile=None,top_decile_coverage=None)
    fpr,tpr,_=roc_curve(y,p)
    precision,recall,_=precision_recall_curve(y,p)
    top=p>=np.quantile(p,.90)
    result.update(ks=float(np.max(tpr-fpr)),pr_auc_trapezoid=float(np.trapezoid(precision[::-1],recall[::-1])),
                  lift_top_decile=float(y[top].mean()/y.mean()),top_decile_coverage=float(top.mean()))
    return result


def definitions():
    return {'score_lr':(SCORE_FEATURES,'lr'),'raw_lr':(RAW_FEATURES,'lr'),
      'hybrid_lr':(RAW_FEATURES+SCORE_FEATURES,'lr'),'raw_tree':(RAW_FEATURES,'tree'),
      'hybrid_tree':(RAW_FEATURES+SCORE_FEATURES,'tree'),'enriched_tree':(FULL,'tree'),
      'score_forest':(SCORE_FEATURES,'forest'),'raw_forest':(RAW_FEATURES,'forest'),'hybrid_forest':(RAW_FEATURES+SCORE_FEATURES,'forest'),'enriched_lr':(FULL,'lr'),'enriched_forest':(FULL,'forest'),
      'without_velocity_lr':([c for c in FULL if c not in WINDOW_FEATURES+['attempts_24h','declines_7d']],'lr'),
      'without_entity_lr':([c for c in FULL if c not in ENTITY_FEATURES],'lr'),
      'without_payload_lr':([c for c in FULL if c not in PAYLOAD_FEATURES],'lr'),
      'without_device_and_entity_lr':([c for c in FULL if c not in ['device_age_days','geo_distance']+ENTITY_FEATURES],'lr')}


def fit_research(train,columns,kind,config):
    if kind!='forest':return fit_model(train,columns,kind,config)
    prep=Transform(columns).fit(train)
    model=RandomForestClassifier(n_estimators=config.get('forest_trees',60),max_depth=6,min_samples_leaf=max(5,config['min_leaf']//2),
          max_features='sqrt',n_jobs=1,random_state=config['seed'])
    model.fit(prep.apply(train),train.risk_label.astype(int))
    return {'prep':prep,'scaler':None,'model':model,'kind':'forest'}


def model_fingerprint(bundle):
    model=bundle['model']
    value={'prep':bundle['prep'].metadata(),'kind':bundle['kind'],'params':model.get_params()}
    if bundle['scaler'] is not None:value['scaler']={'mean':bundle['scaler'].mean_.tolist(),'scale':bundle['scaler'].scale_.tolist()}
    if bundle['kind']=='lr':value.update(coefficients=model.coef_.tolist(),intercept=model.intercept_.tolist())
    else:
        trees=model.estimators_ if bundle['kind']=='forest' else [model]
        value['trees']=[{'feature':t.tree_.feature.tolist(),'threshold':t.tree_.threshold.tolist(),'value':t.tree_.value.tolist(),
                         'children_left':t.tree_.children_left.tolist(),'children_right':t.tree_.children_right.tolist()} for t in trees]
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def population_stability(train,other,columns):
    rows=[]
    for c in columns:
        a=train[c].dropna().to_numpy(dtype=float);b=other[c].dropna().to_numpy(dtype=float)
        inner=np.unique(np.quantile(a,np.linspace(.1,.9,9)))
        bins=np.r_[-np.inf,inner,np.inf]
        pa=np.histogram(a,bins)[0].astype(float);pb=np.histogram(b,bins)[0].astype(float)
        # Explicit additive smoothing avoids infinite PSI in empty bins.
        pa=(pa+.5)/(pa.sum()+.5*len(pa));pb=(pb+.5)/(pb.sum()+.5*len(pb))
        rows.append({'feature':c,'psi':float(np.sum((pb-pa)*np.log(pb/pa))),
          'train_missing':float(train[c].isna().mean()),'other_missing':float(other[c].isna().mean()),'bin_edges_finite':inner.tolist()})
    return {'features':rows,'fit_scope':'quantile bins frozen on train; .5 count smoothing; missingness separate','scope':'descriptive distribution change, not a universal drift threshold'}


def leakage_probe(frame,columns,availability=None):
    """Finite auditable alerts: forbidden/ID names, perfect label proxy, known future time."""
    alerts=[]
    for name in columns:
        if name in ['risk_label','payment_result','action','label_available_ts','result_ts','source'] or name.endswith('_id'):
            alerts.append({'field':name,'code':'FORBIDDEN_OR_ID'})
        if name in frame and pd.api.types.is_numeric_dtype(frame[name]):
            valid=frame[name].notna() & frame.risk_label.notna()
            x=frame.loc[valid,name].to_numpy(dtype=float);y=frame.loc[valid,'risk_label'].to_numpy(dtype=float)
            if len(x)>10 and x.std()>0 and y.std()>0:
                corr=float(np.mean((x-x.mean())*(y-y.mean()))/(x.std()*y.std()))
                if abs(corr)>.98:alerts.append({'field':name,'code':'NEAR_PERFECT_LABEL_PROXY','correlation':corr})
        time=(availability or {}).get(name)
        if time and (time not in frame or frame[time].isna().any() or (frame[time]>frame.decision_ts).any()):
            alerts.append({'field':name,'code':'FUTURE_OR_UNKNOWN_AVAILABILITY'})
    return {'alerts':alerts,'scope':'finite diagnostics; absence of alerts does not prove no proxy/leakage'}


def source_transfer(parts,config):
    rows=[]
    for source in sorted(parts['train'].source.unique()):
        train=parts['train'][parts['train'].source==source]
        if len(train)<50 or train.risk_label.nunique()<2:continue
        bundle=fit_research(train,RAW_FEATURES,'lr',config)
        # Threshold chosen only on the matching selection source.
        select=parts['select'][parts['select'].source==source]
        if len(select)==0:continue
        threshold=float(np.quantile(probabilities(bundle,select),.9))
        for target in sorted(parts['test'].source.unique()):
            test=parts['test'][parts['test'].source==target]
            rows.append({'train_source':source,'test_source':target,'metrics':rank_metrics(test.risk_label,probabilities(bundle,test),threshold)})
    return {'runs':rows,'scope':'fixed raw LR train-on-source/test-on-source diagnostic; same vs cross-source comparison is descriptive, not causal'}


def train_models(parts,config):
    bundles,scores,thresholds,selection={}, {}, {}, {}
    for name,(columns,kind) in definitions().items():
        bundle=fit_research(parts['train'],columns,kind,config);bundles[name]=bundle
        scores[name]={split:probabilities(bundle,parts[split]) for split in ('train','select')}
        thresholds[name]=float(np.quantile(scores[name]['select'],1-config['review_fraction']))
        selection[name]=rank_metrics(parts['select'].risk_label,scores[name]['select'],thresholds[name])
    winner=max(selection,key=lambda name:(selection[name]['ap'],name))
    frozen={'selected_model':winner,'selection_rule':'maximum selection AP among predeclared models; name tie break',
      'thresholds':thresholds,'selection_metrics':selection,'model_fingerprints':{n:model_fingerprint(b) for n,b in bundles.items()},
      'preprocessing':{n:b['prep'].metadata() for n,b in bundles.items()},
      'feature_inputs':{n:c for n,(c,k) in definitions().items()},'fit_scope':'train only; selection decides winner and thresholds; final labels not read'}
    return bundles,scores,frozen


def evaluate_models(parts,bundles,scores,frozen,config):
    comparisons={};temporal=[];subgroups=[]
    for name,bundle in bundles.items():
        scores[name]['test']=probabilities(bundle,parts['test']);threshold=frozen['thresholds'][name]
        comparisons[name]={s:rank_metrics(f.risk_label,scores[name][s],threshold) for s,f in parts.items()}
        midpoint=(config['test_start_day']+config['days'])/2
        for band,mask in [(f"{config['test_start_day']}-{midpoint}d",parts['test'].decision_ts<ORIGIN+midpoint*DAY),(f"{midpoint}-{config['days']}d",parts['test'].decision_ts>=ORIGIN+midpoint*DAY)]:
            temporal.append({'model':name,'band':band,'metrics':rank_metrics(parts['test'].loc[mask,'risk_label'],scores[name]['test'][mask],threshold)})
        seen=parts['test'].user_id.isin(parts['train'].user_id)
        for label,mask in [('seen_user',seen),('new_user',~seen)]:
            subgroups.append({'model':name,'group':label,'metrics':rank_metrics(parts['test'].loc[mask,'risk_label'],scores[name]['test'][mask],threshold)})
    winner=frozen['selected_model']
    gain=paired_ap_interval(parts['test'],scores[winner]['test'],scores['score_lr']['test'],config)
    ablations=[]
    for name in ['without_velocity_lr','without_entity_lr','without_payload_lr','without_device_and_entity_lr']:
        ablations.append({'removed_model':name,'reference':'enriched_lr','selection_ap_difference':comparisons['enriched_lr']['select']['ap']-comparisons[name]['select']['ap'],
                         'final_paired_ap':paired_ap_interval(parts['test'],scores['enriched_lr']['test'],scores[name]['test'],config),
                         'scope':'predeclared input removal, not causal importance; prior_score retains a correlated summary of raw signals; no test-driven model selection'})
    return {'comparison':comparisons,'temporal':temporal,'subject_generalization':subgroups,'winner_ap_gain_vs_score':gain,'ablations':ablations,
            'drift':{s:population_stability(parts['train'],parts[s],FULL) for s in ['select','test']},'source_transfer':source_transfer(parts,config),
            'leakage_diagnostics':leakage_probe(parts['train'],FULL,{'geo_distance':'geo_available_ts'}),
            'matched_forest_inputs':{name:paired_ap_interval(parts['test'],scores['enriched_forest']['test'],scores[name]['test'],config) for name in ['score_forest','raw_forest','hybrid_forest']},
            'metric_definitions':{'ap':'average precision (step PR area)','pr_auc_trapezoid':'trapezoidal precision-recall area; distinct from AP','ks':'max TPR-FPR over tied thresholds; diagnostic, not a deployment threshold',
             'lift_top_decile':'risk rate at scores >= evaluation 90th percentile divided by evaluation base rate; ties may exceed 10%','threshold':'selected on selection scores, frozen for all evaluations'}}
