"""V0.2 independent entity layer, strict as-of SQL and train-only case geometry."""
import json
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from .generate import simulate, DAY
from .data import AdmissionError, assert_unique, build_samples, pair_cases
from .contracts import default_contract

WINDOWS = {'1h':3600, '24h':DAY, '7d':7*DAY}
WINDOW_FEATURES = [f'user_attempts_{w}' for w in WINDOWS] + [f'user_amount_{w}' for w in WINDOWS]
ENTITY_FEATURES = ['user_devices_7d','user_tools_7d','device_users_7d','tool_users_7d']
PAYLOAD_FEATURES = ['client_latency_ms','client_emulator']
EXTENDED_FEATURES = WINDOW_FEATURES + ENTITY_FEATURES + PAYLOAD_FEATURES


def simulate_entities(config):
    """Extend unchanged v1 events. Entity sharing never uses labels or hidden propensity."""
    events, labels = simulate(config)
    rng = np.random.default_rng(config['seed']+202)
    assignments = {}
    devices, tools, accounts, payload = [], [], [], []
    for row in events.itertuples():
        if row.order_id not in assignments:
            user = int(row.user_id[1:])
            device = f'shared_d{int(rng.integers(0,45)):03d}' if rng.random()<0.13 else row.device_id
            tool = f'shared_p{int(rng.integers(0,35)):03d}' if rng.random()<0.10 else f'p{user:04d}_{int(rng.integers(0,3))}'
            assignments[row.order_id] = (device,tool,f'a{user:04d}_{int(rng.integers(0,2))}')
        device,tool,account = assignments[row.order_id]
        devices.append(device);tools.append(tool);accounts.append(account)
        payload.append(json.dumps({'client':{'os':str(rng.choice(['ios','android','web'])),
                        'emulator':bool(rng.random()<0.04), 'latency_ms':float(rng.gamma(2,65))},
                        'network':{'transport':str(rng.choice(['wifi','cellular']))},
                        'tags':['synthetic','independent']},separators=(',',':')))
    events = events.assign(linked_device_id=devices,payment_tool_id=tools,account_id=accounts,
                           context_json=payload,geo_available_ts=events.available_ts,
                           device_available_ts=events.available_ts,tool_available_ts=events.available_ts)
    edges = pd.concat([events[['event_id','user_id','decision_ts',field]].rename(columns={field:'entity_id'}).assign(entity_type=kind)
                       for field,kind in [('order_id','order'),('account_id','account'),('linked_device_id','device'),('payment_tool_id','payment_tool')]],ignore_index=True)
    tables = {kind:edges[edges.entity_type==kind].groupby('entity_id').agg(first_seen_ts=('decision_ts','min'),
              observed_users=('user_id','nunique'),observed_events=('event_id','size')).reset_index() for kind in ['order','account','device','payment_tool']}
    return events,labels,edges,tables


def validate_events(events):
    assert_unique(events,'event_id','enriched events')
    required={'event_id','order_id','user_id','account_id','linked_device_id','payment_tool_id','decision_ts','available_ts','geo_available_ts','device_available_ts','tool_available_ts','context_json','result_ts'}
    if not required<=set(events): raise AdmissionError('missing enriched event schema')
    for key in ['order_id','user_id','account_id','linked_device_id','payment_tool_id']:
        if events[key].isna().any(): raise AdmissionError('missing entity key: '+key)
    for field in ['decision_ts','available_ts','geo_available_ts','device_available_ts','tool_available_ts','result_ts']:
        if not pd.api.types.is_numeric_dtype(events[field]) or pd.api.types.is_bool_dtype(events[field]):
            raise AdmissionError('timestamp must be numeric epoch seconds, not text/bool: '+field)
        try: values=events[field].to_numpy(dtype=float)
        except (ValueError,TypeError): raise AdmissionError('non-numeric event time: '+field)
        if not np.isfinite(values).all(): raise AdmissionError('missing/nonfinite event time: '+field)
        if field not in ('decision_ts','result_ts') and (values>events.decision_ts).any():
            raise AdmissionError('decision-time availability violated: '+field)
    if (events.result_ts<events.decision_ts).any(): raise AdmissionError('result precedes decision')
    return {'status':'PASS','events':len(events),'duplicate_event_keys':0,'time_and_availability':'PASS','policy':'reject ambiguous keys/times; never silently deduplicate or backdate'}


def parse_context(events):
    latency, emulator = [], []
    for row in events.itertuples():
        try:
            context=json.loads(row.context_json)
            client=context['client']
            value=client['latency_ms'];flag=client['emulator']
            if not isinstance(value,(float,int)) or isinstance(value,bool) or not np.isfinite(value) or value<0 or not isinstance(flag,bool):
                raise ValueError('invalid client type/range')
        except (ValueError,TypeError,KeyError):
            raise AdmissionError('invalid structured context for event '+row.event_id)
        latency.append(float(value));emulator.append(int(flag))
    return pd.DataFrame({'event_id':events.event_id,'client_latency_ms':latency,'client_emulator':emulator})


def build_enriched_samples(events, labels):
    quality=validate_events(events)
    base=build_samples(events,labels)
    query=Path(__file__).with_name('entity_windows.sql').read_text()
    with sqlite3.connect(':memory:') as db:
        events.to_sql('events',db,index=False)
        for field in ['user_id','linked_device_id','payment_tool_id']:
            db.execute(f'CREATE INDEX idx_{field} ON events({field},decision_ts)')
        windows=pd.read_sql_query(query,db)
    sample=base.merge(windows,on='event_id',validate='one_to_one').merge(parse_context(events),on='event_id',validate='one_to_one')
    if len(sample)!=len(events): raise AdmissionError('entity/window join changed event grain')
    return sample,quality


def enriched_contract():
    contract=default_contract()
    for name in EXTENDED_FEATURES:
        contract['fields'][name]={'physical_type':'numeric','logical_type':'count' if name in ENTITY_FEATURES or 'attempts_' in name or name=='client_emulator' else 'continuous',
          'meaning': 'parsed client subfield at decision' if name in PAYLOAD_FEATURES else 'strict historical aggregate [t-window,t); known by current decision',
          'bounds':[0,1 if name=='client_emulator' else 1000000000], 'availability':'current' if name in PAYLOAD_FEATURES else 'history',
          'enabled':True,'semantic_status':'approved_for_synthetic','nullable':False,'domain':'fictional_wallet',
          'family':'payload' if name in PAYLOAD_FEATURES else 'entity' if name in ENTITY_FEATURES else 'velocity',
          'parents':['context_json'] if name in PAYLOAD_FEATURES else ['decision_ts','available_ts'] + (['linked_device_id'] if name in ['user_devices_7d','device_users_7d'] else ['payment_tool_id'] if name in ['user_tools_7d','tool_users_7d'] else []),
          'observation_object':'payment_attempt' if name in PAYLOAD_FEATURES else 'device' if name=='device_users_7d' else 'payment_tool' if name=='tool_users_7d' else 'user',
          'window':None if name in PAYLOAD_FEATURES else {'seconds':next((seconds for suffix,seconds in WINDOWS.items() if name.endswith('_'+suffix)),7*DAY),'interval':'[t-window,t)'}}
    for name in ['available_ts','context_json','linked_device_id','payment_tool_id']:
        contract['source_fields'][name]={'enabled':True,'semantic_status':'approved_for_synthetic','domain':'fictional_wallet','availability':'current','parents':[]}
    contract['version']='2.0'
    return contract


class CaseGeometry:
    """Small explicit Lloyd clustering; geometry fitted on training features only."""
    columns=['amount','account_age_days','device_age_days','user_attempts_24h','device_users_7d']
    def fit(self, train, seed=731, k=4):
        x=train[self.columns].to_numpy(dtype=float)
        self.median=np.nanmedian(x,axis=0);x=np.where(np.isnan(x),self.median,x)
        self.mean=x.mean(axis=0);self.scale=x.std(axis=0);self.scale[self.scale==0]=1
        z=(x-self.mean)/self.scale
        rng=np.random.default_rng(seed);centers=[z[int(rng.integers(len(z)))]]
        for _ in range(1,k):
            d=np.min(np.sum((z[:,None,:]-np.array(centers)[None,:,:])**2,axis=2),axis=1)
            centers.append(z[int(np.argmax(d))])
        centers=np.array(centers)
        self.iterations=0
        for _ in range(50):
            assignment=np.argmin(np.sum((z[:,None,:]-centers[None,:,:])**2,axis=2),axis=1)
            updated=np.array([z[assignment==i].mean(axis=0) if (assignment==i).any() else centers[i] for i in range(k)])
            self.iterations+=1
            if np.allclose(updated,centers,rtol=0,atol=1e-8):break
            centers=updated
        self.centers=centers
        self.references=train[['event_id','user_id','order_id']+self.columns].copy()
        self.reference_z=z
        return self
    def transform(self, frame):
        x=frame[self.columns].to_numpy(dtype=float)
        return (np.where(np.isnan(x),self.median,x)-self.mean)/self.scale
    def assign(self,frame):
        z=self.transform(frame)
        return np.argmin(np.sum((z[:,None,:]-self.centers[None,:,:])**2,axis=2),axis=1)
    def similar(self,row,n=5):
        z=self.transform(row)[0]
        distance=np.sqrt(np.sum((self.reference_z-z)**2,axis=1))
        eligible=(self.references.user_id!=row.user_id.iloc[0]).to_numpy()
        ids=np.flatnonzero(eligible)[np.argsort(distance[eligible],kind='stable')[:n]]
        return [dict(event_id=self.references.iloc[i].event_id,distance=float(distance[i])) for i in ids]
    def metadata(self):
        return {'columns':self.columns,'mean':self.mean.tolist(),'scale':self.scale.tolist(),'median':self.median.tolist(),
          'centers_original_units':(self.centers*self.scale+self.mean).tolist(),'fit_scope':'train only; no labels','k':len(self.centers),'iterations':self.iterations,'scope':'descriptive Euclidean clusters, not risk classes'}


def case_analysis(events,sample,parts,seed):
    geometry=CaseGeometry().fit(parts['train'],seed)
    profiles=[]
    for split,frame in parts.items():
        f=frame.assign(cluster=geometry.assign(frame))
        for cluster,g in f.groupby('cluster'):
            profiles.append({'split':split,'cluster':int(cluster),'n':len(g),'risk_rate':float(g.risk_label.mean()),
                             'means':{c:float(g[c].mean()) for c in geometry.columns}})
    pairs=[]
    for hours in [1,6,24,72]:
        p=pair_cases(events,hours)
        pairs.append({'hours':hours,'pairs':len(p),'same_order':int(p.same_order.sum()),'different_order':int((~p.same_order).sum()),'unique_later_events':int(p.pass_event.nunique())})
    cases=[]
    p=pair_cases(events,24)
    for row in p.head(12).to_dict('records'):
        reject=sample.loc[sample.event_id==row['reject_event']]
        success=sample.loc[sample.event_id==row['pass_event']]
        row.update(reject_profile=reject[['amount','auth_strength']+EXTENDED_FEATURES].iloc[0].to_dict(),
                   pass_profile=success[['amount','auth_strength']+EXTENDED_FEATURES].iloc[0].to_dict(),similar_training_cases=geometry.similar(reject))
        cases.append(row)
    strata=[]
    for source,g in sample.groupby('source'):
        strata.append({'source':source,'n':len(g),'risk_rate':float(g.risk_label.mean()),'geo_missing_rate':float(g.geo_distance.isna().mean()),'mean_24h_attempts':float(g.user_attempts_24h.mean())})
    return {'clustering':geometry.metadata(),'cluster_profiles':profiles,'pair_windows':pairs,'cases':cases,'source_profiles':strata,
            'limits':'Earliest later payment success can be many-to-one or another order; no false-decline or causal label. Similarity references training events only; clusters do not prove risk groups.'},geometry
