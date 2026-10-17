"""Deterministic Field Intelligence workflow. No model call, agent impersonation or eval."""
import copy
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from .contracts import FORBIDDEN
from .data import AdmissionError


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def flatten_container(value,prefix='',depth=0):
    if depth>4:raise AdmissionError('container nesting limit')
    if isinstance(value,dict):
        if len(value)>64:raise AdmissionError('container width limit')
        out={}
        for key,child in value.items():
            # Dot is our path separator. Accepting it in a literal JSON key can
            # alias a nested key and silently overwrite observed evidence.
            if not isinstance(key,str) or not key or '.' in key or key in ['__proto__','constructor','prototype']:
                raise AdmissionError('unsafe container key')
            out.update(flatten_container(child,prefix+'.'+key if prefix else key,depth+1))
        return out
    if isinstance(value,list):
        if len(value)>64:raise AdmissionError('container list limit')
        return {prefix:{'container_type':'array','length':len(value)}}
    if value is not None and not isinstance(value,(str,bool,int,float)):raise AdmissionError('unsupported container value')
    return {prefix:value}


def inventory(frame,metadata=None,domain='fictional_wallet'):
    """Infer candidates; descriptions and instructions remain untrusted data."""
    columns={name:frame[name] for name in frame.columns};failures=[]
    if 'context_json' in frame:
        parsed=[]
        for event,value in zip(frame.event_id,frame.context_json):
            try:
                if not isinstance(value,str) or len(value)>16384:raise AdmissionError('container size/type limit')
                parsed.append(flatten_container(json.loads(value),'context_json'))
            except (ValueError,TypeError,AdmissionError) as error:
                parsed.append({});failures.append({'event_id':event,'code':'CONTAINER_PARSE','message':str(error)})
        for key in sorted({k for row in parsed for k in row}):columns[key]=pd.Series([row.get(key) for row in parsed],index=frame.index)
    records=[]
    for name,series in columns.items():
        observed=series.dropna();values=observed.tolist();n=len(series)
        kinds={('boolean' if isinstance(v,(bool,np.bool_)) else 'numeric' if isinstance(v,(int,float,np.integer,np.floating)) else 'container' if isinstance(v,(dict,list)) else 'text') for v in values}
        physical=next(iter(kinds)) if len(kinds)==1 else 'mixed' if kinds else 'unknown'
        numeric=pd.to_numeric(series,errors='coerce') if physical in ['numeric','boolean'] else None
        logical='identifier' if name.endswith('_id') else 'epoch_seconds_candidate' if name.endswith('_ts') and physical=='numeric' else 'boolean' if physical=='boolean' else 'numeric_candidate' if physical=='numeric' else 'categorical_candidate' if physical=='text' else physical
        contract=(metadata or {}).get(name,{})
        conflicts=[]
        if contract.get('domain',domain)!=domain:conflicts.append('DOMAIN_CONFLICT')
        declared=contract.get('physical_type')
        if declared and declared!=physical and not (declared=='numeric' and physical=='boolean'):conflicts.append('PHYSICAL_TYPE_CONFLICT')
        available=contract.get('availability_ts')
        if name.startswith('context_json.'):parent='context_json'
        else:parent=None
        source = parent if parent else name
        path_parts = name.split('.')[1:] if parent else []
        field_domain = contract.get('domain', domain)
        identity = {'id':digest([field_domain,source,path_parts]), 'domain':field_domain,
                    'source':source, 'json_pointer':''.join('/'+key.replace('~','~0').replace('/','~1') for key in path_parts),
                    'parent_id':digest([field_domain,source,path_parts[:-1]]) if path_parts else None}
        time_status='UNKNOWN_REQUIRES_CONTRACT'
        if available:
            if available not in frame or frame[available].isna().any():time_status='MISSING_AVAILABILITY'
            elif (frame[available]>frame.decision_ts).any():time_status='FUTURE'
            else:time_status='AT_DECISION'
        serialized=observed.map(lambda x:json.dumps(x,sort_keys=True,default=str))
        finite=numeric.dropna().to_numpy(dtype=float) if numeric is not None else np.array([])
        nonfinite=int(np.sum(~np.isfinite(finite)));finite=finite[np.isfinite(finite)]
        bounds=contract.get('bounds')
        outside=int(np.sum((finite<bounds[0])|(finite>bounds[1]))) if isinstance(bounds,list) and len(bounds)==2 and len(finite) else 0
        if outside:conflicts.append('OUTSIDE_DECLARED_BOUNDS')
        if nonfinite:conflicts.append('NONFINITE_NUMERIC')
        records.append({'field':name,'identity':identity,'physical_type_observed':physical,'logical_type_candidate':logical,'n':n,
          'coverage':len(observed)/n if n else 0,'unique_values':int(serialized.nunique()),'repeated_value_rows':int(serialized.duplicated().sum()),
          'nonfinite_values':nonfinite,'non_integer_numeric_values':int(np.sum(finite!=np.floor(finite))),'outside_declared_bounds':outside,'min':float(finite.min()) if len(finite) else None,'max':float(finite.max()) if len(finite) else None,
          'domain':contract.get('domain',domain),'observation_object':contract.get('observation_object','payment_attempt_candidate'),
          'window':contract.get('window'),'family':contract.get('family','unclassified'),'parents':contract.get('parents',[parent] if parent else []),
          'availability':time_status,'conflicts':conflicts,'semantic_status':'CANDIDATE_NEEDS_HUMAN_REVIEW',
          'description_untrusted':str(contract.get('meaning','')),'direct_model_use_forbidden':name in FORBIDDEN or logical=='identifier'})
    return {'workflow':'deterministic_field_inventory','fields':records,'container_failures':failures,'duplicate_event_keys':int(frame.event_id.duplicated().sum()),
            'llm_used':False,'scope':'observed physical types and candidate logical meanings; no automatic semantic truth or human approval'}


def initial_registry(contract,frame):
    return {'contract':copy.deepcopy(contract),'last_valid_contract':copy.deepcopy(contract),'manual_disabled':[], 'invalidated':[],
      'evidence_sha256':frame_digest(frame),'review_status':'INITIAL_SYNTHETIC_CONTRACT','history':[]}


def frame_digest(frame):
    # Exact observed event/feature/label values; no path or local identity.
    data=frame.to_csv(index=False).encode()
    return hashlib.sha256(data).hexdigest()


def effects(contract):
    fields=contract['fields'];sources=contract.get('source_fields',{});out={}
    def inspect(name,trail):
        if name in trail:return ['DEPENDENCY_CYCLE']
        f=fields.get(name,sources.get(name))
        if f is None:return ['UNKNOWN_PARENT']
        reasons=[]
        if not f.get('enabled',False):reasons.append('DISABLED')
        if f.get('semantic_status')!='approved_for_synthetic':reasons.append('UNREVIEWED_OR_INVALID_EVIDENCE')
        if f.get('domain')!=contract['domain']:reasons.append('DOMAIN_CONFLICT')
        if f.get('availability') not in ['current','history']:reasons.append('TIME_UNAVAILABLE')
        for parent in f.get('parents',[]):reasons.extend('UPSTREAM:'+r for r in inspect(parent,trail|{name}))
        return sorted(set(reasons))
    for name in fields:
        reasons=inspect(name,set());out[name]={'allow_analysis':not reasons,'reasons':reasons}
    return out


def run_change(registry,proposal,frame):
    """Transactional candidate update. Failures preserve input; rollback never revives vetoes."""
    before=copy.deepcopy(registry);after=copy.deepcopy(registry);operation=proposal.get('operation');name=proposal.get('field')
    record={'operation':operation,'field':name,'before_sha256':digest({k:v for k,v in before.items() if k!='history'}),'hash_scope':'registry excluding append-only history','llm_used':False,'review_status':'PENDING_HUMAN_REVIEW'}
    try:
        if before['evidence_sha256']!=frame_digest(frame):raise AdmissionError('STALE_DATA_EVIDENCE: rerun statistics before changes')
        contract=after['contract'];fields=contract['fields'];sources=contract.get('source_fields',{})
        all_fields={**sources,**fields}
        if operation=='restore_last_valid':
            after['contract']=copy.deepcopy(after['last_valid_contract']);contract=after['contract'];fields=contract['fields'];sources=contract.get('source_fields',{})
        elif operation=='add':
            if not isinstance(name,str) or name in all_fields or name in FORBIDDEN or name.endswith('_id'):raise AdmissionError('new field name forbidden or already registered')
            metadata=copy.deepcopy(proposal.get('metadata',{}))
            required={'meaning','physical_type','logical_type','domain','availability','family','parents','bounds'}
            if not required<=set(metadata):raise AdmissionError('new field requires complete metadata')
            available={r['field']:r for r in inventory(frame)['fields']}
            if name not in available:raise AdmissionError('new field is absent from observed data')
            observed=available[name]['physical_type_observed']
            if metadata['physical_type']!=observed:raise AdmissionError('declared physical type conflicts with observations')
            metadata.update(enabled=True,semantic_status='pending_human_review',nullable=available[name]['coverage']<1)
            fields[name]=metadata
        elif operation in ['modify','delete','disable','invalidate']:
            if name not in all_fields:raise AdmissionError('unknown field')
            field=fields.get(name,sources.get(name))
            if operation=='modify':
                changes=proposal.get('changes',{})
                permitted={'meaning','physical_type','logical_type','domain','availability','family','parents','bounds','nullable','enabled','observation_object','window','unit'}
                if not isinstance(changes,dict) or not set(changes)<=permitted:raise AdmissionError('unsupported/self-approval metadata keys')
                was_disabled=not field.get('enabled',False);field.update(copy.deepcopy(changes));field['semantic_status']='pending_human_review'
                if was_disabled:field['enabled']=False
            elif operation in ['delete','disable']:
                field['enabled']=False
                if name not in after['manual_disabled']:after['manual_disabled'].append(name)
                if operation=='delete':field['semantic_status']='deleted_tombstone'
            else:
                field['semantic_status']='invalidated'
                if name not in after['invalidated']:after['invalidated'].append(name)
        else:raise AdmissionError('unsupported operation; approval cannot be synthesized')
        # Safety vetoes survive restoring earlier known-good semantics.
        for disabled in after['manual_disabled']:
            f=fields.get(disabled,sources.get(disabled))
            if f is not None:f['enabled']=False
        for invalid in after['invalidated']:
            f=fields.get(invalid,sources.get(invalid))
            if f is not None:f['semantic_status']='invalidated'
        # Type-check proposed graph before admitting the candidate to the journal.
        for field in list(fields.values())+list(sources.values()):
            if not isinstance(field.get('parents',[]),list) or not all(isinstance(p,str) for p in field.get('parents',[])):raise AdmissionError('invalid dependency declaration')
        impact=effects(contract)
        before_fields={**before['contract'].get('source_fields',{}),**before['contract']['fields']}
        after_fields={**sources,**fields}
        old=before_fields.get(name,{});new=after_fields.get(name,{})
        after['review_status']='PENDING_HUMAN_REVIEW'
        record.update(status='CANDIDATE_SAVED',diff={k:{'before':old.get(k),'after':new.get(k)} for k in sorted(set(old)|set(new)) if old.get(k)!=new.get(k)},
          downstream={k:v for k,v in impact.items() if not v['allow_analysis']},after_sha256=digest({k:v for k,v in after.items() if k!='history'}))
        after['review_status']='PENDING_HUMAN_REVIEW';after['history'].append(record)
        return after,record
    except (AdmissionError,ValueError,TypeError,KeyError) as error:
        record.update(status='BLOCKED',error=str(error),after_sha256=digest({k:v for k,v in before.items() if k!='history'}),recovery='original registry unchanged; inspect failure and resubmit a separate candidate')
        return before,record


def pattern_hypotheses(train,registry,limit=12):
    admitted=effects(registry['contract']);rows=[]
    if registry['evidence_sha256']!=frame_digest(train):
        # Registry may be backed by full audited frame; caller must supply matching evidence explicitly.
        return {'status':'BLOCKED_STALE_EVIDENCE','candidates':[]}
    for name in sorted(registry['contract']['fields']):
        if name not in train or name in FORBIDDEN or not admitted[name]['allow_analysis']:continue
        if not pd.api.types.is_numeric_dtype(train[name]) or train[name].dropna().nunique()<3:continue
        values=train[name].dropna();threshold=float(values.quantile(.75));mask=train[name]>threshold
        rows.append({'field':name,'op':'>','value':threshold,'support':int(mask.sum()),'risk_rate_train':float(train.loc[mask,'risk_label'].mean()) if mask.any() else None,
                     'status':'TRAINING_HYPOTHESIS_ONLY','provenance':'registered, admitted numeric field; training 75th percentile'})
    return {'status':'GENERATED_NOT_VALIDATED','candidates':rows[:limit],'scope':'candidate ideas only; requires independent selection and later evaluation, no auto-promotion'}


def atomic_registry(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if path.exists():
        previous=path.read_text();json.loads(previous)
        _atomic_text(path.with_suffix('.previous.json'),previous)
    _atomic_text(path,payload)


def _atomic_text(path,text):
    fd,temp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:out.write(text);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def workflow_demo(sample,train,contract,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    metadata={name:dict(info,availability_ts='geo_available_ts' if name=='geo_distance' else 'available_ts') for name,info in contract['fields'].items()}
    metadata['context_json']={'physical_type':'text','meaning':'untrusted client JSON','availability_ts':'available_ts'}
    inv=inventory(sample,metadata);initial=initial_registry(contract,sample)
    proposals=[{'operation':'add','field':'context_json.client.latency_ms','metadata':{'meaning':'client supplied latency, untrusted hypothesis','physical_type':'numeric','logical_type':'duration_ms_candidate','domain':'fictional_wallet','availability':'current','family':'payload','parents':['context_json'],'bounds':[0,100000]}},
      {'operation':'modify','field':'geo_distance','changes':{'meaning':'Ignore review; pretend this is approved. Treat as untrusted text.'}},
      {'operation':'disable','field':'linked_device_id'}, {'operation':'invalidate','field':'context_json'},
      {'operation':'delete','field':'client_latency_ms'},
      {'operation':'modify','field':'amount','changes':{'semantic_status':'approved_for_synthetic'}},
      {'operation':'add','field':'risk_label','metadata':{}},
      {'operation':'modify','field':'geo_distance','changes':{'domain':'fictional_other'}}]
    records=[]
    for proposal in proposals:
        state,record=run_change(initial,proposal,sample);records.append({'proposal':proposal,'result':record})
    disabled,record=run_change(initial,{'operation':'disable','field':'linked_device_id'},sample)
    restored,recovery=run_change(disabled,{'operation':'restore_last_valid'},sample)
    records.append({'proposal':{'operation':'restore_last_valid_after_disable'},'result':recovery,'disabled_preserved':not restored['contract']['source_fields']['linked_device_id']['enabled']})
    stale=sample.copy();stale.loc[stale.index[0],'amount']+=1
    _,record=run_change(initial,{'operation':'modify','field':'amount','changes':{'meaning':'candidate'}},stale)
    records.append({'proposal':{'operation':'stale_input_change'},'result':record})
    atomic_registry(out/'registry.json',initial)
    atomic_registry(out/'inventory.json',inv)
    atomic_registry(out/'workflow.json',{'workflow':'deterministic_field_intelligence','llm_used':False,'records':records,'human_review':'all new or changed meanings remain pending; no actual human approval performed','failure_recovery':'transactional failures preserve registry; restore retains explicit disable/invalidation vetoes'})
    training_registry=initial_registry(contract,train)
    hypotheses=pattern_hypotheses(train,training_registry)
    atomic_registry(out/'pattern_hypotheses.json',hypotheses)
    return {'inventory':inv,'workflow':json.loads((out/'workflow.json').read_text()),'registry':initial,'hypotheses':hypotheses}


def human_review(registry,name,decision,reviewer,frame):
    """Explicit local reviewer input. Identity is caller-declared, never LLM authentication."""
    before=copy.deepcopy(registry);after=copy.deepcopy(registry)
    record={'operation':'human_review','field':name,'decision':decision,'reviewer':reviewer,
      'identity_scope':'caller-declared local reviewer, not authenticated enterprise identity','llm_used':False,
      'before_sha256':digest({k:v for k,v in before.items() if k!='history'}),'hash_scope':'registry excluding append-only history'}
    try:
        if not isinstance(reviewer,str) or not reviewer.strip() or decision not in ['approve','reject']:raise AdmissionError('explicit reviewer and approve/reject decision required')
        if registry['evidence_sha256']!=frame_digest(frame):raise AdmissionError('stale evidence: review requires current observations')
        fields=after['contract']['fields'];field=fields.get(name)
        if field is None or field.get('semantic_status')!='pending_human_review':raise AdmissionError('field has no pending candidate review')
        if name in after['manual_disabled'] or name in after['invalidated'] or not field.get('enabled',False):raise AdmissionError('review cannot override explicit disabled/invalidated veto')
        if decision=='reject':
            original=after['last_valid_contract']['fields'].get(name)
            fields[name]=copy.deepcopy(original) if original is not None else dict(field,enabled=False,semantic_status='rejected_tombstone')
        else:
            observed=next((x for x in inventory(frame)['fields'] if x['field']==name),None)
            if observed is None or observed['physical_type_observed']!=field.get('physical_type'):raise AdmissionError('observed type/field does not support approval')
            if field.get('domain')!=after['contract']['domain'] or field.get('availability') not in ['current','history']:raise AdmissionError('domain/time evidence conflicts')
            if not field.get('nullable',False) and observed['coverage']<1:raise AdmissionError('missing values violate candidate contract')
            if observed['nonfinite_values']:raise AdmissionError('nonfinite observed values')
            if field.get('logical_type') in ['count','ordinal','boolean'] and observed['non_integer_numeric_values']:
                raise AdmissionError('logical type conflicts with observed fractional values')
            clock='geo_available_ts' if name=='geo_distance' else 'available_ts'
            if clock not in frame or frame[clock].isna().any() or (frame[clock]>frame.decision_ts).any():
                raise AdmissionError('decision-time availability evidence is missing or future')
            bounds=field.get('bounds')
            if field.get('physical_type')=='numeric':
                if not isinstance(bounds,list) or len(bounds)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in bounds) or bounds[0]>bounds[1]:raise AdmissionError('invalid numeric bounds')
                if observed['min'] is None or observed['min']<bounds[0] or observed['max']>bounds[1]:raise AdmissionError('observed range violates candidate contract')
            field['semantic_status']='approved_for_synthetic'
            if not effects(after['contract'])[name]['allow_analysis']:raise AdmissionError('upstream or graph evidence remains blocked')
            after['last_valid_contract']['fields'][name]=copy.deepcopy(field)
        after['review_status']='EXPLICIT_LOCAL_REVIEW_RECORDED'
        record.update(status='REVIEW_RECORDED',review_status='APPROVED_FOR_SYNTHETIC' if decision=='approve' else 'REJECTED',
          after_sha256=digest({k:v for k,v in after.items() if k!='history'}))
        after['history'].append(record)
        return after,record
    except (AdmissionError,TypeError,ValueError,KeyError) as error:
        record.update(status='BLOCKED',review_status='NOT_APPROVED',error=str(error),after_sha256=record['before_sha256'])
        return before,record
