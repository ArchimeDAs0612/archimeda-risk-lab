"""Complete-path candidate research, falsification and safe boolean policy replay."""
import copy
import numpy as np
import pandas as pd
from .models import complete_paths,replay,verify_membership,choose_candidate
from .evidence import candidate_summary,stratified_countercheck,rediscovery
from .research_models import FULL
from .contracts import FORBIDDEN
from .data import AdmissionError


def plain_summary(frame,mask):
    mask=np.asarray(mask,dtype=bool);y=frame.risk_label.to_numpy(dtype=int)
    return {'n':int(mask.sum()),'risk_count':int(y[mask].sum()),'coverage':float(mask.mean()),
            'risk_rate':float(y[mask].mean()) if mask.any() else None,'enrichment':float(y[mask].mean()/y.mean()) if mask.any() and y.mean() else None}


def discover(parts,bundles,config):
    candidates=[];membership={}
    for model in ['raw_tree','enriched_tree']:
        bundle=bundles[model];paths=complete_paths(bundle)
        membership[model]={s:verify_membership(bundle,frame,paths) for s,frame in parts.items() if s!='test'}
        for path in paths:
            train=plain_summary(parts['train'],replay(bundle,parts['train'],path))
            select=plain_summary(parts['select'],replay(bundle,parts['select'],path))
            candidates.append({'id':model+':'+str(path['leaf_id']),'model':model,'path':path,'train':train,'select':select,
                'eligible_selection_support':select['n']>=config['candidate_min_select'],
                'preprocessing':bundle['prep'].metadata()})
    eligible=[c for c in candidates if c['eligible_selection_support']]
    chosen=max(eligible or candidates,key=lambda c:((c['select']['risk_rate'] or 0) if eligible else c['train']['risk_rate'],c['select']['n'],c['id']))
    frozen={'candidate':copy.deepcopy(chosen),'candidate_count':len(candidates),'selection_rule':'all full leaves from two predeclared training CARTs; highest selection risk rate with minimum support; count/name tie breaks',
            'selection_status':'ELIGIBLE' if eligible else 'INSUFFICIENT_SELECTION_SUPPORT','production_authorization':'NOT_GRANTED'}
    return candidates,frozen,membership


def verdict(summary,selection_n,config):
    ci=summary['difference_cluster_ci95']
    return 'SUPPORTED_FOR_INVESTIGATION' if selection_n>=config['candidate_min_select'] and summary['n']>=config['candidate_min_test'] and summary['risk_count']>=5 and ci[0] is not None and ci[0]>0 else 'INSUFFICIENT_SUPPORT'


def evaluate_patterns(parts,bundles,candidates,frozen,membership,config):
    chosen=frozen['candidate'];bundle=bundles[chosen['model']];path=chosen['path']
    for model in membership:
        membership[model]['test']=verify_membership(bundles[model],parts['test'],complete_paths(bundles[model]))
    masks={s:replay(bundle,frame,path) for s,frame in parts.items()}
    summary={s:candidate_summary(frame,masks[s],config,config['seed']+31+i) for i,(s,frame) in enumerate(parts.items())}
    for split in ['train','select']:
        summary[split]['uncertainty_scope']='post-search descriptive interval on training/selection; not independent confirmation'
    evaluations=[]
    for c in candidates:
        b=bundles[c['model']];evaluations.append({'id':c['id'],'test_descriptive':plain_summary(parts['test'],replay(b,parts['test'],c['path'])),
          'scope':'multiple-candidate final table is descriptive only; winner frozen before final labels'})
    simplifications=[];sensitivity=[]
    for i,term in enumerate(path['predicates']):
        smaller=dict(path,predicates=[p for j,p in enumerate(path['predicates']) if j!=i]);mask=replay(bundle,parts['test'],smaller)
        simplifications.append({'dropped_index':i,'dropped_term':term,'full_conditions_retained_in_parent':path['predicates'],
          'new_conditions':smaller['predicates'],'added_n':int((mask & ~masks['test']).sum()),'removed_n':int((~mask & masks['test']).sum()),
          'summary':candidate_summary(parts['test'],mask,config,config['seed']+40+i),'scope':'post-freeze new candidate, diagnostic only; needs fresh holdout before promotion'})
        for direction in [-1,1]:
            modified=copy.deepcopy(path);modified['predicates'][i]['threshold']+=direction*max(abs(term['threshold'])*.1,.1)
            changed=replay(bundle,parts['test'],modified)
            sensitivity.append({'term_index':i,'direction':direction,'threshold':modified['predicates'][i]['threshold'],
              'changed_members':int(np.sum(changed!=masks['test'])),'summary':plain_summary(parts['test'],changed),
              'scope':'predeclared threshold perturbation; not used for selection'})
    feature_sensitivity=[]
    for field in sorted({p['transformed_feature'].replace('__missing','') for p in path['predicates']}):
        f=parts['test'].copy();f[field]=bundle['prep'].medians[bundle['prep'].columns.index(field)]
        altered=replay(bundle,f,path)
        feature_sensitivity.append({'feature':field,'changed_members':int(np.sum(altered!=masks['test'])), 'summary':plain_summary(parts['test'],altered),
                                    'scope':'replace field with training median; descriptive dependence, not causal effect'})
    original=choose_candidate(bundles['raw_tree'],parts['select'],config)
    original_mask=replay(bundles['raw_tree'],parts['test'],original)
    original_summary=candidate_summary(parts['test'],original_mask,config,config['seed']+90)
    return {'selected':frozen,'summary':summary,'verdict':verdict(summary['test'],chosen['select']['n'],config),
      'all_candidates':candidates,'final_descriptive_candidates':evaluations,'membership':membership,'simplifications':simplifications,
      'countercheck':stratified_countercheck(parts['test'],masks['test']),'threshold_sensitivity':sensitivity,'feature_sensitivity':feature_sensitivity,
      'rediscovery':rediscovery(parts['train'],parts['select'],masks['select'],bundle['prep'].columns,config),
      'legacy_raw_candidate':{'path':original,'summary':original_summary,'verdict':verdict(original_summary,int(replay(bundles['raw_tree'],parts['select'],original).sum()),config)},
      'limits':'Selected candidate only is confirmatory for this prespecified final window; other leaves/simplifications are post-selection descriptions, not independent discoveries. No causal benefit.'},masks


def predicate_mask(frame,spec,allowed=None,medians=None):
    """Strict JSON AST, no eval/execution; finite depth and size, no target/source/ID access."""
    allowed=set(FULL if allowed is None else allowed);nodes=[0]
    def walk(term,depth):
        nodes[0]+=1
        if depth>8 or nodes[0]>64 or not isinstance(term,dict):raise AdmissionError('rule structure/size invalid')
        if set(term) in ({'all'},{'any'}):
            key=next(iter(term));children=term[key]
            if not isinstance(children,list) or not children:raise AdmissionError('empty/invalid rule group')
            values=[walk(c,depth+1) for c in children]
            return np.logical_and.reduce(values) if key=='all' else np.logical_or.reduce(values)
        if set(term)=={'not'}:return ~walk(term['not'],depth+1)
        if set(term)!={'field','op','value'}:raise AdmissionError('unknown rule shape')
        name,op,value=term['field'],term['op'],term['value']
        if not isinstance(name,str) or name not in allowed or name in FORBIDDEN or name not in frame:raise AdmissionError('rule field not admitted')
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value):raise AdmissionError('rule value must be finite numeric')
        x=frame[name].to_numpy(dtype=float)
        if np.isnan(x).any():
            if medians is None or name not in medians:raise AdmissionError('rule missingness requires frozen train mapping')
            x=np.where(np.isnan(x),medians[name],x)
        operations={'>':np.greater,'>=':np.greater_equal,'<':np.less,'<=':np.less_equal,'==':np.equal}
        if not isinstance(op,str) or op not in operations:raise AdmissionError('unsupported rule operator')
        return operations[op](x,value)
    return walk(spec,0)


def path_spec(path,preprocessing):
    """Convert a conditional model path to the user-rule AST.

    A root-only tree has a valid unconditional model path, but no conditional
    user rule. Use complete_path_mask for that case; empty user groups remain
    forbidden, including after JSON serialization.
    """
    if not isinstance(path,dict) or not isinstance(path.get('predicates'),list):
        raise AdmissionError('invalid model path')
    if not path['predicates']:
        raise AdmissionError('unconditional model path requires complete_path_mask')
    names=preprocessing['output_columns']
    for p in path['predicates']:
        if not isinstance(p,dict) or not {'feature_index','transformed_feature','operator','threshold'}<=set(p):
            raise AdmissionError('invalid model predicate')
        if type(p['feature_index']) is not int or p['feature_index']<0 or p['feature_index']>=len(names) or names[p['feature_index']]!=p['transformed_feature']:
            raise AdmissionError('path/preprocessing mismatch')
        if p['operator'] not in ['<=','>'] or isinstance(p['threshold'],bool) or not isinstance(p['threshold'],(int,float)) or not np.isfinite(p['threshold']):
            raise AdmissionError('invalid model predicate operator/threshold')
    return {'all':[{'field':p['transformed_feature'],'op':p['operator'],'value':p['threshold']} for p in path['predicates']]}


def complete_path_mask(frame,path,preprocessing):
    """Replay a saved complete model path, separately from untrusted user ASTs.

    Root-only CARTs cover every row and have no discriminatory power. The only
    accepted empty complete path is root leaf 0 with positive training support;
    removing every condition from some other leaf is a different candidate.
    This does not authorize the model or promote its statistical conclusion.
    """
    if not isinstance(path,dict) or not isinstance(path.get('predicates'),list):
        raise AdmissionError('invalid model path')
    if not path['predicates']:
        if type(path.get('leaf_id')) is not int or path['leaf_id']!=0 or type(path.get('train_support')) is not int or path['train_support']<=0:
            raise AdmissionError('empty conditions do not identify a complete model root leaf')
        # Validate the same numeric preprocessing as conditional paths before
        # accepting a root leaf; no alternate feature or imputation semantics.
        transformed_rule_frame(frame,preprocessing)
        return np.ones(len(frame),dtype=bool)
    transformed=transformed_rule_frame(frame,preprocessing)
    return predicate_mask(transformed,path_spec(path,preprocessing),preprocessing['output_columns'])


def transformed_rule_frame(frame,preprocessing):
    result=frame.copy()
    for c in preprocessing['input_columns']:
        result[c+'__missing']=result[c].isna().astype(int)
        result[c]=result[c].fillna(preprocessing['train_medians'][c]).astype(np.float32)
    return result


def policy_replay(frame,candidate_mask,costs,mode='or',candidate_action='decline',amount_threshold=210.,review_threshold=.58):
    if mode not in ['or','and','candidate_only'] or candidate_action not in ['decline','review']:
        raise AdmissionError('unsupported strategy configuration')
    for value in [amount_threshold,review_threshold]+list(costs.values()):
        if not isinstance(value,(int,float)) or not np.isfinite(value) or value<0:raise AdmissionError('invalid strategy number')
    if set(costs)!={'risk_loss_multiplier','legitimate_decline_cost','review_cost'} or review_threshold>1:
        raise AdmissionError('invalid strategy cost keys or review probability')
    candidate=np.asarray(candidate_mask,dtype=bool)
    if candidate.ndim!=1 or len(candidate)!=len(frame):raise AdmissionError('strategy mask grain mismatch')
    base=(frame.amount>amount_threshold).to_numpy() & (frame.auth_strength==0).to_numpy()
    combined=base|candidate if mode=='or' else base&candidate if mode=='and' else candidate
    new_decline=combined if candidate_action=='decline' else base
    new_review=((frame.prior_score>review_threshold).to_numpy() | (combined if candidate_action=='review' else False)) & ~new_decline
    new=np.where(new_decline,'decline',np.where(new_review,'review','approve'))
    old=frame.action.to_numpy();y=frame.risk_label.to_numpy(dtype=int);amount=frame.amount.to_numpy()
    def summary(action):
        deny=action=='decline';review=action=='review'
        return {'n':len(frame),'declines':int(deny.sum()),'reviews':int(review.sum()),'approvals':int(np.sum(action=='approve')),
          'risky_allowed':int(np.sum((~deny)&(y==1))),'legitimate_declined':int(np.sum(deny&(y==0))),
          'decline_coverage':float(deny.mean()),'risk_capture':float(np.sum(deny&(y==1))/np.sum(y)) if np.sum(y) else None,
          'modeled_cost':float(np.sum(amount[(~deny)&(y==1)])*costs['risk_loss_multiplier']+np.sum(deny&(y==0))*costs['legitimate_decline_cost']+review.sum()*costs['review_cost'])}
    transition=[{'from':a,'to':b,'n':int(np.sum((old==a)&(new==b)))} for a in ['approve','review','decline'] for b in ['approve','review','decline']]
    return {'baseline':summary(old),'scenario':summary(new),'changed_n':int(np.sum(old!=new)),
      'changed_event_ids':frame.loc[old!=new,'event_id'].tolist(),'transitions':transition,
      'configuration':{'mode':mode,'candidate_action':candidate_action,'amount_threshold':amount_threshold,'review_threshold':review_threshold,'costs':costs},
      'authorization':'NOT_GRANTED','scope':'synthetic fully audited attempted risk; declines prevent all risk amount loss, review no protection, no behavior response or causal claim'},new
