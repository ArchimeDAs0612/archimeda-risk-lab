import argparse
import json
import time
from pathlib import Path
from .pipeline import generate_data, run_experiment, save_json
from .report import render_demo


def main():
    parser = argparse.ArgumentParser(description="Independent synthetic payment-risk evidence chain")
    parser.add_argument("command", choices=["generate", "run", "demo"])
    parser.add_argument("--config", default="config/default.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--data")
    parser.add_argument("--inject", choices=["future", "missing_time", "source_binding", "cross_event"])
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        parser.error("output directory must be absent or empty; choose a new run path")
    if args.command == "generate":
        generate_data(config, out)
        print(json.dumps({"generated":str(out)}, ensure_ascii=False))
    elif args.command == "run":
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
