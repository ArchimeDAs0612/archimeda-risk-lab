"""Actual V0.2 research run: entity data -> gates -> frozen studies -> evidence -> workbench."""
import hashlib,json,platform,time
from pathlib import Path
import numpy as np
import pandas as pd
from .entities import simulate_entities,build_enriched_samples,enriched_contract,case_analysis
from .contracts import check_admission,inject,RAW_FEATURES,SCORE_FEATURES
from .data import split_samples,AdmissionError
from .research_models import FULL,train_models,evaluate_models
from .patterns import discover,evaluate_patterns,policy_replay,path_spec,transformed_rule_frame,predicate_mask
from .field_intelligence import workflow_demo
from .pipeline import save_json,sha,code_manifest
from .report import render_report


def provenance(config,data,out,injection):
    import importlib.metadata
    from . import __version__
    return {'version':__version__,'simulator_version':'persistent-device-v2','config':config,'config_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
      'data_sha256':{p.name:sha(p) for p in sorted(data.iterdir()) if p.is_file()},'code_sha256':code_manifest(),
      'ui_sha256':{p.name:sha(p) for p in Path(__file__).with_name('web').glob('*') if p.is_file()},
      'python':platform.python_version(),'dependencies':{n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','scikit-learn']},
      'injection':injection,'scope':'independent synthetic CPU experiment; no external data, paid service or model API'}


def run_research(config,out,data_dir=None,injection=None,render=True,field_registry=None):
    if injection not in [None,'future','missing_time','source_binding','cross_event','duplicate','malformed_context','late_tool','field_invalidation']:
        raise AdmissionError('unknown research injection')
    start=time.perf_counter();out=Path(out)
    if out.exists() and any(out.iterdir()):raise AdmissionError('research output must be absent or empty; do not mix evidence')
    out.mkdir(parents=True,exist_ok=True);data=out/'data';data.mkdir(exist_ok=True)
    if data_dir is None:
        events,labels,edges,tables=simulate_entities(config);contract=enriched_contract()
        edges.to_csv(data/'entity_edges.csv',index=False)
        for name,table in tables.items():table.to_csv(data/(name+'.csv'),index=False)
    else:
        supplied=Path(data_dir);events=pd.read_csv(supplied/'events.csv',float_precision='round_trip');labels=pd.read_csv(supplied/'labels.csv',float_precision='round_trip');contract=json.loads((supplied/'contract.json').read_text())
    if injection=='duplicate':events=pd.concat([events,events.iloc[:1]],ignore_index=True)
    elif injection=='malformed_context':events.loc[events.index[0],'context_json']='{"client":'
    elif injection=='late_tool':events.loc[events.index[0],'tool_available_ts']=events.iloc[0].decision_ts+1
    elif injection=='field_invalidation':contract['source_fields']['context_json']['semantic_status']='invalidated'
    events.to_csv(data/'events.csv',index=False);labels.to_csv(data/'labels.csv',index=False);save_json(data/'contract.json',contract);save_json(data/'config.json',config)
    try:
        sample,quality=build_enriched_samples(events,labels)
        if field_registry is not None:
            from .field_intelligence import frame_digest
            registry=json.loads(Path(field_registry).read_text()) if not isinstance(field_registry,dict) else field_registry
            if registry['evidence_sha256']!=frame_digest(sample):
                raise AdmissionError('STALE_FIELD_EVIDENCE: registry does not match current observed input')
            contract=registry['contract']
            save_json(data/'contract.json',contract)
        semantics={'implementation':'single_event'}
        if injection in ['future','missing_time','source_binding','cross_event']:sample,semantics=inject(sample,injection)
        gate=check_admission(sample,contract,FULL,semantics)
    except AdmissionError as error:
        sample=None;quality={'status':'BLOCKED','reason':str(error)}
        gate={'evidence_admission':'BLOCKED','allow_model':False,'findings':[{'severity':'BLOCKED','code':'ENRICHED_INPUT','message':str(error)}]}
    save_json(out/'quality.json',quality);save_json(out/'admission.json',gate)
    if sample is not None:sample.to_csv(out/'samples.csv',index=False)
    result={'execution':'SUCCESS','admission':gate,'provenance':provenance(config,data,out,injection),'production_authorization':'NOT_GRANTED'}
    if not gate['allow_model']:
        result.update(candidate_verdict='NOT_EVALUATED',model_comparison=None,elapsed_seconds=time.perf_counter()-start)
        save_json(out/'result.json',result);render_report(result,out/'index.html');return result
    parts=split_samples(sample,config)
    bundles,scores,model_frozen=train_models(parts,config)
    candidates,pattern_frozen,membership=discover(parts,bundles,config)
    frozen={'models':model_frozen,'pattern':pattern_frozen,'split_ids_sha256':{s:hashlib.sha256('\n'.join(f.event_id).encode()).hexdigest() for s,f in parts.items()},
            'boundary':'Persisted before any final model metrics, candidate risk estimates, subgroup/case labels or final comparisons.'}
    save_json(out/'frozen_selection.json',frozen)
    from .model_artifact import export_model, predict_json
    model_receipts = {}
    for name, bundle in bundles.items():
        artifact = export_model(bundle, model_frozen['thresholds'][name])
        save_json(out/'models'/(name+'.json'), artifact)
        loaded = json.loads((out/'models'/(name+'.json')).read_text())
        error = float(np.max(np.abs(predict_json(loaded, parts['select']) - scores[name]['select'])))
        if error > 1e-12:
            raise AssertionError('saved model inference diverges: '+name)
        model_receipts[name] = {'sha256':sha(out/'models'/(name+'.json')), 'selection_max_abs_error':error,
            'format':'inspectable JSON; binary Lab LR/CART/forest only; no pickle'}
    models=evaluate_models(parts,bundles,scores,model_frozen,config)
    patterns,masks=evaluate_patterns(parts,bundles,candidates,pattern_frozen,membership,config)
    analysis,geometry=case_analysis(events,sample,parts,config['seed'])
    field=workflow_demo(sample,parts['train'],contract,out/'field')
    scenarios={}
    for name,kwargs in [('union_decline',{}),('intersection_decline',{'mode':'and'}),('union_review',{'candidate_action':'review'}),('raised_amount',{'amount_threshold':300.})]:
        scenario,actions=policy_replay(parts['test'],masks['test'],config['cost_assumptions'],**kwargs);scenarios[name]=scenario
    test=parts['test'];predictions=test[['event_id','user_id','risk_label','amount','action','decision_ts','source']].copy()
    predictions['candidate']=masks['test']
    for name in scores:predictions[name]=scores[name]['test']
    predictions.to_csv(out/'predictions.csv',index=False)
    all_predictions=[]
    for s,frame in parts.items():
        p=frame[['event_id','risk_label','user_id','source','amount']].copy();p['split']=s;p['candidate']=masks[s]
        for name in scores:p[name]=scores[name][s]
        all_predictions.append(p)
    pd.concat(all_predictions,ignore_index=True).to_csv(out/'all_predictions.csv',index=False)
    result.update(frozen_selection=frozen,models=models,patterns=patterns,candidate_verdict=patterns['verdict'],case_analysis=analysis,
      splits={s:{'n':len(f),'risk_count':int(f.risk_label.sum()),'base_rate':float(f.risk_label.mean())} for s,f in parts.items()},
      entity_counts={'orders':int(events.order_id.nunique()),'accounts':int(events.account_id.nunique()),'devices':int(events.linked_device_id.nunique()),'tools':int(events.payment_tool_id.nunique())},
      saved_model_validation=model_receipts,
      field_workflow={'llm_used':False,'inventory_fields':len(field['inventory']['fields']),'records':len(field['workflow']['records']),'blocked_changes':sum(x['result']['status']=='BLOCKED' for x in field['workflow']['records']),
        'human_review':'pending; no human approval synthesized'},strategies=scenarios,elapsed_seconds=time.perf_counter()-start)
    save_json(out/'result.json',result)
    if render:
        from .workbench import build_workbench
        build_workbench(result,sample,parts,test,field,geometry,out)
    return result


def run_research_demo(config,out):
    """Bounded real normal/abnormal/repair suite; no scheduler or concurrent execution."""
    from .field_intelligence import run_change
    from .report import shell,table
    start=time.perf_counter();out=Path(out)
    if out.exists() and any(out.iterdir()):raise AdmissionError('demo output must be absent or empty')
    out.mkdir(parents=True,exist_ok=True)
    normal=run_research(config,out/'normal')
    rows=[{'branch':'normal','admission':'PASS','candidate':normal['candidate_verdict'],'link':'normal/index.html'}]
    for injection in ['duplicate','malformed_context','late_tool','field_invalidation','future','missing_time','source_binding','cross_event']:
        name='bad_'+injection;bad=run_research(config,out/name,injection=injection)
        if bad['admission']['allow_model'] or bad['candidate_verdict']!='NOT_EVALUATED':raise AssertionError('bad branch not restricted: '+injection)
        rows.append({'branch':name,'admission':bad['admission']['evidence_admission'],'candidate':bad['candidate_verdict'],'link':name+'/index.html'})
    sample=pd.read_csv(out/'normal/samples.csv',float_precision='round_trip')
    registry=json.loads((out/'normal/field/registry.json').read_text())
    changed,record=run_change(registry,{'operation':'disable','field':'linked_device_id'},sample)
    save_json(out/'disabled_registry.json',changed);save_json(out/'disable_record.json',record)
    bad=run_research(config,out/'disabled_downstream',data_dir=out/'normal/data',field_registry=changed)
    if bad['admission']['allow_model']:raise AssertionError('field workflow failed to restrict downstream')
    rows.append({'branch':'disabled_downstream','admission':'BLOCKED','candidate':'NOT_EVALUATED','link':'disabled_downstream/index.html'})
    repaired=run_research(config,out/'repaired',data_dir=out/'normal/data')
    compare={key:normal[key]==repaired[key] for key in ['frozen_selection','models','patterns','strategies','case_analysis']}
    if not all(compare.values()):raise AssertionError('repair evidence differs: '+str(compare))
    rows.append({'branch':'repaired','admission':'PASS','candidate':repaired['candidate_verdict'],'link':'repaired/index.html'})
    summary={'branches':rows,'repair_comparison':compare,'elapsed_seconds':time.perf_counter()-start,'scope':'sequential bounded engineering smoke; blocked branches save actual received samples and reasons, never train'}
    save_json(out/'demo.json',summary)
    body='<p class="notice">全部入口来自真实执行；异常分支不产生模型或候选结论。</p>'
    body+=table(rows,[('branch','分支'),('admission','证据准入'),('candidate','候选结论')])
    body+='<h2>实际运行报告</h2><ul>'+''.join('<li><a href="'+r['link']+'">'+r['branch']+'</a></li>' for r in rows)+'</ul>'
    body+='<h2>修复完整重跑</h2><p>'+json.dumps(compare,ensure_ascii=False)+'</p><p>字段工具输出的禁用注册表已真正接入研究链，阻断受影响特征的训练。解除显式禁用需要独立人工处理；修复分支使用未被修改的有效输入。</p>'
    (out/'index.html').write_text(shell('V0.2 实验分支与失败恢复',body),encoding='utf-8')
    return summary
