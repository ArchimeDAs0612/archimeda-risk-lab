"""Bounded local benchmarks; independent timing and Python-allocation passes.

Use the same CLI on before/after commits for an optimization comparison. This
script does not load executable code from a user-supplied baseline path.
"""
import argparse
import copy
import json
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from risklab.contracts import RAW_FEATURES, SCORE_FEATURES
from risklab.entities import simulate_entities, build_enriched_samples
from risklab.field_intelligence import initial_registry, frame_digest
from risklab.field_incremental import materialize
from risklab.models import fit_model, complete_paths, replay, verify_membership
from risklab.pipeline import save_json, sha
from risklab.study_contracts import workspace_path


def median_time(call, repeats=5):
    values=[]
    for _ in range(repeats):
        start=time.perf_counter();call();values.append(time.perf_counter()-start)
    return dict(median=statistics.median(values), measurements=values)


def python_peak(call):
    tracemalloc.start()
    try:
        call();return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def run(data, out):
    data=workspace_path(data);out=workspace_path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('choose an empty benchmark output')
    import pandas as pd
    source=pd.read_csv(data/'samples.csv',float_precision='round_trip')
    registry=json.loads((data/'field/registry.json').read_text())
    if len(source)<6000 or frame_digest(source)!=registry['evidence_sha256']:
        raise ValueError('accepted source evidence with at least 6000 rows required')
    contract=registry['contract'];rows=[]
    with threadpool_limits(1):
        fitted=fit_model(source.iloc[:600],RAW_FEATURES+SCORE_FEATURES,'tree',{'seed':20261018,'tree_depth':4,'min_leaf':20})
        rules=complete_paths(fitted)
        for n in [300,1500,6000]:
            frame=source.iloc[:n].copy();state=initial_registry(copy.deepcopy(contract),frame)
            before=materialize(state,frame)
            changed=copy.deepcopy(state);changed['contract']['fields']['amount']['unit']='benchmark-only-new-unit'
            # This measures invalidation after a verified metadata-only fixture,
            # not automatic semantic approval of a real user change.
            full=lambda:materialize(changed,frame)
            incremental=lambda:materialize(changed,frame,before)
            a=full();b=incremental()
            if a['fields']!=b['fields']:
                raise AssertionError('incremental result differs from full recomputation')
            events,labels,_,_=simulate_entities(dict(seed=20261018,orders=n,days=120))
            construction=lambda:build_enriched_samples(events,labels)
            def replay_batch():
                for _ in range(100):
                    for rule in rules:replay(fitted,frame,rule)
            membership=verify_membership(fitted,frame,rules)
            if not membership['all_paths_equal']:
                raise AssertionError('complete paths differ from tree membership')
            rows.append(dict(rows=n,event_rows=len(events),field_full=median_time(full),field_incremental=median_time(incremental),
                             field_python_peak_bytes=python_peak(full),recomputed=b['recomputed'],reused=b['reused'],
                             equal_field_results=True,data_construction=median_time(construction,3),
                             data_python_peak_bytes=python_peak(construction),
                             pattern_100_batches=median_time(replay_batch,3),pattern_count=len(rules),membership=membership))
    result=dict(sizes=rows,python=platform.python_version(),platform=platform.system(),
                source_sha256=sha(Path(__file__)),field_source_sha256=sha(Path(materialize.__code__.co_filename)),
                scope='fixed serial workloads, no timeout claims; tracemalloc excludes native allocations and total RSS; timings vary by host',
                before_commit='d2a31d0c5c82779b2d18b04de546916819bb6fa4')
    out.mkdir(parents=True,exist_ok=True);save_json(out/'result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();result=run(args.data,args.out)
    print(json.dumps({'status':'SAVED','sizes':[r['rows'] for r in result['sizes']]}))
