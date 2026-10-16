import argparse
import json
import time
from pathlib import Path
from .pipeline import generate_data, run_experiment, save_json
from .report import render_demo


def main():
    parser = argparse.ArgumentParser(description="Independent synthetic payment-risk evidence chain")
    parser.add_argument("command", choices=["generate", "run", "demo", "research", "research-demo", "field-inventory", "field-change", "field-review", "field-workflow", "label-study", "predict"])
    parser.add_argument("--config")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data")
    parser.add_argument("--inject", choices=["future", "missing_time", "source_binding", "cross_event", "duplicate", "malformed_context", "late_tool", "field_invalidation"])
    parser.add_argument("--registry")
    parser.add_argument("--proposal")
    parser.add_argument("--metadata")
    parser.add_argument("--field")
    parser.add_argument("--decision", choices=["approve","reject"])
    parser.add_argument("--reviewer")
    parser.add_argument("--model")
    args = parser.parse_args()
    config = None
    if args.command in ['generate','run','demo','research','research-demo']:
        config_name='research.json' if args.command in ['research','research-demo'] else 'default.json'
        config_path=Path(args.config) if args.config else Path('config')/config_name
        if not args.config and not config_path.exists():
            config_path=Path(__file__).with_name('config')/config_name
        config=json.loads(config_path.read_text())
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be absent or empty; choose a new run path")
    if args.command == 'predict':
        if not args.model or not args.data:
            parser.error('predict requires --model JSON and --data samples.csv')
        import pandas as pd
        from .model_artifact import predict_json
        artifact=json.loads(Path(args.model).read_text());frame=pd.read_csv(args.data,float_precision='round_trip')
        p=predict_json(artifact,frame)
        out.mkdir(parents=True,exist_ok=True)
        predictions=pd.DataFrame({'probability':p,'flagged':p>=artifact['threshold']})
        if 'event_id' in frame:predictions.insert(0,'event_id',frame.event_id)
        predictions.to_csv(out/'predictions.csv',index=False)
        print(json.dumps({'rows':len(frame),'model_format':artifact['format']}))
    elif args.command in ['label-study','field-workflow']:
        if not args.data:parser.error(args.command+' requires --data research-run-directory')
        if args.command=='label-study':
            from .label_visibility import run_label_study
            run_label_study(args.data,out)
        else:
            from .field_workflow import run_field_workflow
            run_field_workflow(args.data,out)
        print(json.dumps({'status':'SAVED','command':args.command}))
    elif args.command == "research-demo":
        from .research import run_research_demo
        print(json.dumps(run_research_demo(config,out),ensure_ascii=False))
    elif args.command == "research":
        from .research import run_research
        r = run_research(config,out,args.data,args.inject,field_registry=args.registry)
        print(json.dumps({"execution":r["execution"],"admission":r["admission"]["evidence_admission"],"candidate":r["candidate_verdict"],"seconds":r["elapsed_seconds"]},ensure_ascii=False))
    elif args.command in ["field-inventory", "field-change", "field-review"]:
        if not args.data:
            parser.error("field tools require --data samples.csv")
        import pandas as pd
        from .field_intelligence import inventory,run_change,human_review,atomic_registry
        frame = pd.read_csv(args.data, float_precision="round_trip")
        out.mkdir(parents=True,exist_ok=True)
        if args.command == "field-inventory":
            metadata = json.loads(Path(args.metadata).read_text()) if args.metadata else None
            atomic_registry(out/"inventory.json",inventory(frame,metadata))
            print(json.dumps({"status":"INVENTORY_SAVED","llm_used":False}))
        elif args.command == "field-review":
            if not args.registry or not args.field or not args.decision or not args.reviewer:
                parser.error("field-review requires --registry, --field, --decision and --reviewer")
            state,record = human_review(json.loads(Path(args.registry).read_text()),args.field,args.decision,args.reviewer,frame)
            atomic_registry(out/"registry.json",state);atomic_registry(out/"review.json",record)
            print(json.dumps({"status":record["status"],"llm_used":False,"review":record["review_status"]}))
        else:
            if not args.registry or not args.proposal:
                parser.error("field-change requires --registry and --proposal")
            state,record = run_change(json.loads(Path(args.registry).read_text()),json.loads(Path(args.proposal).read_text()),frame)
            atomic_registry(out/"registry.json",state);atomic_registry(out/"change.json",record)
            print(json.dumps({"status":record["status"],"llm_used":False,"review":record["review_status"]}))
    elif args.command == "generate":
        generate_data(config, out)
        print(json.dumps({"generated":str(out)}, ensure_ascii=False))
    elif args.command == "run":
        if args.inject not in [None,"future","missing_time","source_binding","cross_event"]:
            parser.error("legacy run supports its original four injection types; use research for enriched failures")
        if not args.data:
            parser.error("run requires --data")
        r = run_experiment(config, args.data, out, args.inject)
        print(json.dumps({"execution":r["execution"],"admission":r["admission"]["evidence_admission"],"candidate":r["candidate_verdict"],"seconds":r["elapsed_seconds"]}, ensure_ascii=False))
    else:
        start = time.perf_counter()
        data = generate_data(config,out/"data")
        branches, results = {}, {}
        for name, injection in [("normal",None), ("bad_future","future"), ("bad_missing_time","missing_time"), ("bad_source_binding","source_binding"), ("bad_cross_event","cross_event"), ("repaired",None)]:
            r = run_experiment(config,data,out/name,injection)
            results[name] = r
            branches[name] = {"admission":r["admission"]["evidence_admission"],"candidate_verdict":r["candidate_verdict"],
                              "codes":[x["code"] for x in r["admission"]["findings"]],"seconds":r["elapsed_seconds"]}
        comparison = {k:results["normal"][k]==results["repaired"][k] for k in ["model_comparison","candidate","frozen_selection","membership","case_pairing"]}
        if not all(comparison.values()):
            raise AssertionError("repair rerun differs from original evidence")
        summary = {"branches":branches,"repair_comparison":comparison,"elapsed_seconds":time.perf_counter()-start}
        save_json(out/"demo.json",summary)
        render_demo(summary,out/"index.html")
        print(json.dumps(summary,ensure_ascii=False))

if __name__ == "__main__":
    main()
