"""Benchmark: how often does the model alone produce a buildable plan, versus the
model + Naqsha's checker/repair loop?  Also scores room detection and size accuracy
against ground truth (NN.json next to each sketch).

Run:  python -m bench.run [rows|coords] [folder]     (default: rows, bench/sketches)
  rows   = Naqsha: model reads rooms row by row, our layout solver places them
  coords = naive baseline: model must output room coordinates itself
"""
import base64
import json
import sys
from pathlib import Path

from server import llm, plan as P


def score(pred, truth):
    """Room recall (name match) and mean absolute size error (ft) over matched rooms."""
    matched, placed, err = 0, 0, []
    for t in truth["rooms"]:
        try:
            p = P.find_room(pred, t["name"])
        except P.PlanError:
            continue
        matched += 1
        err.append((abs(p["w"] - t["w"]) + abs(p["h"] - t["h"])) / 2)
        if all(abs(p[k] - t[k]) <= 1.0 for k in ("x", "y", "w", "h")):
            placed += 1
    n = len(truth["rooms"])
    return matched / n, (sum(err) / len(err) if err else None), placed / n


def main(folder, mode):
    folder = Path(folder)
    rows = []
    for img in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")):
        truth_f = img.with_suffix(".json")
        b64 = base64.b64encode(img.read_bytes()).decode()
        try:
            plan, log, errs = llm.read_sketch(b64, mode=mode)
        except llm.ModelError as e:
            rows.append({"sketch": img.name, "error": str(e)})
            print(img.name, "FAILED", e)
            continue
        first = log[0]
        row = {"sketch": img.name,
               "raw_valid": first.get("raw_errors", 1) == 0,
               "after_snap_valid": not first.get("errors"),
               "final_valid": not errs,
               "repair_rounds": len(log) - 1,
               "secs": round(sum(s.get("secs", 0) for s in log), 1)}
        if truth_f.exists():
            row["room_recall"], row["size_err_ft"], row["placed_right"] = score(plan, json.loads(truth_f.read_text()))
        rows.append(row)
        print(json.dumps(row))
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    pct = lambda k: f"{100 * sum(r[k] for r in ok) / n:.0f}%" if n else "-"
    summary = {"mode": mode, "sketches": n, "model_only_valid": pct("raw_valid"), "plus_snap_valid": pct("after_snap_valid"),
               "plus_checker_loop_valid": pct("final_valid")}
    rec = [r["room_recall"] for r in ok if "room_recall" in r]
    se = [r["size_err_ft"] for r in ok if r.get("size_err_ft") is not None]
    if rec:
        summary["room_recall"] = f"{100 * sum(rec) / len(rec):.0f}%"
    if se:
        summary["mean_size_error_ft"] = round(sum(se) / len(se), 2)
    pl = [r["placed_right"] for r in ok if "placed_right" in r]
    if pl:
        summary["rooms_placed_correctly"] = f"{100 * sum(pl) / len(pl):.0f}%"
    print("\nSUMMARY", json.dumps(summary, indent=1))
    (folder / f"results_{mode}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "rows"
    main(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parent / "sketches", mode)
