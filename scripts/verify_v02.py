"""Independent CSV/JSON audit without importing the research or sklearn implementations."""
import argparse,csv,hashlib,json,math,struct
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text())
def read(path):
    with path.open() as file:return list(csv.DictReader(file))
def numeric(row,name):
    value=row.get(name,'')
    return None if value=='' else float(value)
def close(a,b):return a is None and b is None or a is not None and b is not None and math.isclose(a,b,abs_tol=1e-10,rel_tol=1e-10)


def independently_ranked(rows,model,threshold):
    groups=defaultdict(lambda:[0,0]);total=sum(int(r['risk_label']) for r in rows);n=len(rows);negative=n-total
    for row in rows:
        groups[float(row[model])][0]+=1;groups[float(row[model])][1]+=int(row['risk_label'])
    seen=hits=0;ap=ks=area=0.;last_precision=1.
    for score in sorted(groups,reverse=True):
        count,positive=groups[score];seen+=count;hits+=positive;precision=hits/seen
        ap+=positive/total*precision;area+=positive/total*(last_precision+precision)/2;last_precision=precision
        ks=max(ks,hits/total-(seen-hits)/negative)
    neg_before=0;u=0.
    for score in sorted(groups):
        count,positive=groups[score];ng=count-positive;u+=positive*(neg_before+.5*ng);neg_before+=ng
    scores=sorted(float(r[model]) for r in rows);where=.9*(n-1);lo=int(math.floor(where));hi=int(math.ceil(where));quantile=scores[lo]+(scores[hi]-scores[lo])*(where-lo)
    top=[r for r in rows if float(r[model])>=quantile]
    return {'ap':ap,'pr_auc_trapezoid':area,'auc':u/(total*negative),'ks':ks,
      'lift_top_decile':sum(int(r['risk_label']) for r in top)/len(top)/(total/n),
      'top_decile_coverage':len(top)/n,'flagged':sum(float(r[model])>=threshold for r in rows),
      'brier':sum((float(r[model])-int(r['risk_label']))**2 for r in rows)/n}


def path_member(row,candidate,drop=None):
    prep=candidate['preprocessing']
    for i,term in enumerate(candidate['path']['predicates']):
        if i==drop:continue
        name=term['transformed_feature']
        if name.endswith('__missing'):value=int(numeric(row,name[:-9]) is None)
        else:value=numeric(row,name);value=prep['train_medians'][name] if value is None else value
        value=struct.unpack('f',struct.pack('f',value))[0]
        if term['operator']=='<=':ok=value<=term['threshold']
        elif term['operator']=='>':ok=value>term['threshold']
        else:raise ValueError('unknown predicate')
        if not ok:return False
    return True


def verify(run):
    result=load(run/'result.json');frozen=load(run/'frozen_selection.json');predictions=read(run/'all_predictions.csv');samples=read(run/'samples.csv');by_id={r['event_id']:r for r in samples};checks={}
    checks['sample_unique_grain']=len(samples)==len(by_id)
    checks['frozen_record_matches_result']=frozen==result['frozen_selection']
    config=result['provenance']['config'];origin=1767225600;day=86400
    parts={s:[r for r in predictions if r['split']==s] for s in ['train','select','test']}
    expected={s:[] for s in parts}
    for r in samples:
        t=float(r['decision_ts']);mature=float(r['label_available_ts']);observed=r['risk_label']!=''
        if not observed:continue
        if t<origin+config['train_end_day']*day and mature<=origin+config['train_asof_day']*day:expected['train'].append(r['event_id'])
        if origin+config['select_start_day']*day<=t<origin+config['select_end_day']*day and mature<=origin+config['select_asof_day']*day:expected['select'].append(r['event_id'])
        if t>=origin+config['test_start_day']*day and mature<=origin+config['evaluation_asof_day']*day:expected['test'].append(r['event_id'])
    for split,rows in parts.items():
        checks[split+'_ids_maturity_independent']=set(expected[split])=={r['event_id'] for r in rows}
        checks[split+'_n']=len(rows)==result['splits'][split]['n']
        checks[split+'_risk_count']=sum(int(r['risk_label']) for r in rows)==result['splits'][split]['risk_count']
        for model,values in result['models']['comparison'].items():
            recalculated=independently_ranked(rows,model,frozen['models']['thresholds'][model])
            for metric,value in recalculated.items():checks[f'{split}_{model}_{metric}']=close(value,values[split][metric])
    winner=max(result['models']['comparison'],key=lambda n:(result['models']['comparison'][n]['select']['ap'],n))
    checks['selection_only_model_winner']=winner==frozen['models']['selected_model']
    final=[by_id[r['event_id']] for r in parts['test']];selected=result['patterns']['selected']['candidate']
    candidate_mask=[path_member(r,selected) for r in final]
    for candidate in result['patterns']['all_candidates']:
        mask=[path_member(r,candidate) for r in final];actual=next(r['test_descriptive'] for r in result['patterns']['final_descriptive_candidates'] if r['id']==candidate['id'])
        checks[candidate['id']+'_n']=sum(mask)==actual['n'];checks[candidate['id']+'_risk_count']=sum(int(r['risk_label']) for r,m in zip(final,mask) if m)==actual['risk_count']
    for simplification in result['patterns']['simplifications']:
        drop=simplification['dropped_index'];mask=[path_member(r,selected,drop) for r in final]
        checks['drop_'+str(drop)+'_added']=sum(m and not o for m,o in zip(mask,candidate_mask))==simplification['added_n']
        checks['drop_'+str(drop)+'_superset']=not any(o and not m for m,o in zip(mask,candidate_mask)) and simplification['removed_n']==0
    for name,scenario in result['strategies'].items():
        config_s=scenario['configuration'];old=[r['action'] for r in final];new=[]
        for r,candidate in zip(final,candidate_mask):
            base=float(r['amount'])>config_s['amount_threshold'] and float(r['auth_strength'])==0
            combine=base or candidate if config_s['mode']=='or' else base and candidate if config_s['mode']=='and' else candidate
            deny=combine if config_s['candidate_action']=='decline' else base
            review=not deny and (float(r['prior_score'])>config_s['review_threshold'] or (config_s['candidate_action']=='review' and combine))
            new.append('decline' if deny else 'review' if review else 'approve')
        for label,actions in [('baseline',old),('scenario',new)]:
            counts={a:actions.count(a) for a in ['decline','review','approve']};legit=sum(a=='decline' and int(r['risk_label'])==0 for r,a in zip(final,actions));risk=sum(a!='decline' and int(r['risk_label'])==1 for r,a in zip(final,actions));costs=config_s['costs']
            loss=sum(float(r['amount']) for r,a in zip(final,actions) if a!='decline' and int(r['risk_label'])==1)
            cost=loss*costs['risk_loss_multiplier']+legit*costs['legitimate_decline_cost']+counts['review']*costs['review_cost']
            actual=scenario[label]
            checks[name+'_'+label+'_counts']=counts=={'decline':actual['declines'],'review':actual['reviews'],'approve':actual['approvals']} and legit==actual['legitimate_declined'] and risk==actual['risky_allowed']
            checks[name+'_'+label+'_cost']=close(cost,actual['modeled_cost'])
        changed=[r['event_id'] for r,a,b in zip(final,old,new) if a!=b]
        checks[name+'_changed_events']=changed==scenario['changed_event_ids']
    for name,h in result['provenance']['code_sha256'].items():checks['source_'+name]=sha(ROOT/name)==h
    for name,h in result['provenance']['data_sha256'].items():checks['data_'+name]=sha(run/'data'/name)==h
    for name,h in result['provenance']['ui_sha256'].items():checks['ui_'+name]=sha(ROOT/'risklab/web'/name)==h
    checks['no_false_llm_claim']=result['field_workflow']['llm_used'] is False
    return {'method':'independent standard-library CSV ranking (ties), ROC/PR/KS/lift/Brier, temporal cohort reconstruction, float32 path sets, policy arithmetic and fingerprints','checks':checks,'passed':sum(checks.values()),'total':len(checks)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('--member-sets',type=Path);args=parser.parse_args();receipt=verify(args.run)
    if args.member_sets:
        result=load(args.run/'result.json');samples={r['event_id']:r for r in read(args.run/'samples.csv')};final=[samples[r['event_id']] for r in read(args.run/'all_predictions.csv') if r['split']=='test']
        sets={c['id']:sorted(r['event_id'] for r in final if path_member(r,c)) for c in result['patterns']['all_candidates']}
        args.member_sets.parent.mkdir(parents=True,exist_ok=True);args.member_sets.write_text(json.dumps(sets,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    if receipt['passed']!=receipt['total']:raise SystemExit(1)
