"""Standalone field inspection; no Sesta workspace or package is needed."""
import argparse
from pathlib import Path
from PIL import Image
from pathology_tools.packets import prepare, sha
from pathology_tools.rounds import start_inspection, invoke, save_review, inspection_lock
from pathology_tools.packets import dump
from pathology_tools.inspection import recorded_policy, replay_legacy_native, steps
from pathology_tools.native_workbench import batches
from pathology_tools.source import raster_rgb

POLICY = {"framework":"Sol's Hammer","model":"gpt-6.2-sol","tier":"ultrafast",
          "effort":"xhigh","batch":4,"workflow":"batched-triage-v2",
          "instruction":"Triage each independent field efficiently. Keep satisfactory results. "
                        "Identify the major error and use one targeted repair when warranted."}

def schedule(bench):
    size = bench.policy["batch"]
    for keys in batches(bench.fields, size):
        yield "select", keys
    pending = []
    for k in sorted(bench.fields, key=lambda key: bench.proposals[key] == "baseline"):
        if bench.selections[k]["choice"] == "baseline" and not bench.summaries[k]["flags"]:
            bench.finish(k, triaged=True)
        else:
            pending.append(k)
    for keys in batches(pending, size):
        yield "review", keys
    for key in pending:
        if not bench.reviews[key]["edits"]:
            bench.finish(key)
    for keys in batches([k for k in pending if bench.reviews[k]["edits"]], size):
        yield "confirm", keys


def inspect_batches(paths, output, replay_only=False):
    record = recorded_policy(output, POLICY)
    if not record or "protocol" in record:
        return steps(paths,output,POLICY,replay_only,schedule=schedule)
    policy = record["policy"]
    if (Path(output)/"transport.json").exists():
        if not replay_only:
            raise ValueError("Use --replay-only for a sealed native run or choose a fresh output")
        return replay_legacy_native(paths,output,policy)
    fields, output = start_inspection(paths, output, policy)
    def batches(ids):
        for i in range(0, len(ids), policy["batch"]):
            yield i//policy["batch"] + 1, ids[i:i+policy["batch"]]
    proposals = {}
    for i, ids in batches(list(fields)):
        first = invoke(output/f"select-{i:02}", ids, fields, "select", {}, policy, replay_only)
        proposals.update({r["field"]:r["choice"] for r in first})
    # Review proposed interventions first, then unchanged fields for typing errors.
    queue = sorted(fields, key=lambda k: proposals[k]=="baseline")
    final = {}
    for i, ids in batches(queue):
        review = invoke(output/f"review-{i:02}", ids, fields, "review", proposals, policy, replay_only)
        final.update(save_review(fields, output, proposals, review))
    dump(output/"decisions.json", final)
    return final

def main():
    p = argparse.ArgumentParser(description=__doc__,
        epilog='Use sols-hammer workbench --help to choose a nuclear review mode. The older hybrid command runs the single-operator workflow. The compose command is also available.')
    sub = p.add_subparsers(dest="command",required=True)
    from pathology_tools import modes
    review = sub.add_parser("workbench", help="細胞核判讀 · 工具導引／模型導引／混合")
    modes.configure(review)
    make = sub.add_parser("prepare")
    make.add_argument("--image",type=Path,required=True)
    make.add_argument("--field",type=Path,required=True)
    make.add_argument("--classifier",type=Path)
    make.add_argument("--origin",nargs=2,type=int,metavar=("X","Y"),default=(0,0),
                      help="Position of the supplied field in the full level-zero source")
    make.add_argument("--reference-image",type=Path,help="Aligned native slide or canonical RGB raster at level zero")
    make.add_argument("--legacy-packet",action="store_true",help="Reconstruct the five frozen pilot candidates")
    make.add_argument("--mpp",nargs=2,type=float,metavar=("X","Y"),help="Known source micrometres per pixel")
    see = sub.add_parser("inspect")
    see.add_argument("--fields",type=Path,nargs="+",required=True)
    see.add_argument("--output",type=Path,required=True)
    see.add_argument("--codex-session",type=Path,help="Operate the workbench in a single live Codex session using this configuration")
    see.add_argument("--replay-only",action="store_true",help="Use only sealed model decisions")
    args = p.parse_args()
    if args.command == "workbench":
        return modes.start(review, args, "sol", False)
    if args.command=="prepare":
        with Image.open(args.image) as im:
            if max(im.size)>1024:
                p.error("Pass a field of at most 1024 pixels per side")
            if args.legacy_packet:
                import numpy as np
                rgb = np.asarray(im.convert("RGB"))
            else:
                rgb = raster_rgb(im)
        prepare(rgb,args.origin,args.image.stem,args.field,args.classifier,sha(args.image),
                reference=args.reference_image,mpp=args.mpp,legacy=args.legacy_packet)
    else:
        if args.codex_session:
            if args.replay_only:
                p.error("A live Codex session requires a fresh output")
            from pathology_tools.codex_session import run
            print(run(args.fields,args.output,POLICY,args.codex_session,schedule=schedule))
            return
        if len(set(f.name for f in args.fields)) != len(args.fields):
            p.error("Each field needs a unique directory name")
        with inspection_lock(args.output):
            inspect_batches(args.fields,args.output,args.replay_only)

if __name__=="__main__":
    main()
