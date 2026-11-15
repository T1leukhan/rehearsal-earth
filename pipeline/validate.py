"""
validate.py - Three checks on the atlas scores. Nothing is tuned: the checks use
the same files and the same scoring code as score.py, and report what comes out.

Inputs:  app/data/config.json, thermal.json, terrain.json, sources.json
         data/raw/appeears/*.csv   (only to look for an Amazon control point)
Output:  app/data/validation.json  (shown on the page's Validation tab)

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\validate.py     (Windows)
    .venv/bin/python pipeline/validate.py               (macOS/Linux)

The three checks:
  1. Benchmarks: sites that NASA already names as analogs. Do they rank near
     the top for the metric they are known for?
  2. Negative control: an Amazon point should NOT look like the Moon or Mars.
     Also: can one metric alone make two different sites look alike?
  3. Sensitivity: change every tolerance by -20% and +20%. How many score
     labels (strong, partial, weak) change, and how do the rankings change?

At the end it lists what we WOULD change, without changing anything.
"""

import csv
import json
from pathlib import Path

import thermal as thermal_py
from score import TERRAIN, label, label_and_score, load_inputs, score, scored_rows

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "app" / "data"
APPEEARS_DIR = PROJECT_ROOT / "data" / "raw" / "appeears"
OUT_PATH = DATA / "validation.json"

# "Near the top" means rank 1 or 2 among the sites that have a value.
NEAR_TOP_RANK = 2

# The sensitivity check multiplies every tolerance by these factors (-20% and +20%).
FACTORS = [0.8, 1.2]

# The four comparisons in the atlas: (body, metric).
CHECKS = [("moon", "thermal_swing_K"), ("mars", "mean_temperature_K"), ("moon", "slope_deg"), ("moon", "roughness_m")]

# Benchmarks: what each source names the site for, and which atlas comparisons
# match that. The quotes themselves are in sources.json. "not_measured" is what the
# source names the site for that no number in this atlas measures.
BENCHMARKS = {
    "atacama": {"sources": ["nasa_planetary_analogs", "nasa_arads"], "named_as": "Mars analog",
                "known_for": [("mars", "mean_temperature_K")], "not_measured": "extreme dryness and soil chemistry"},
    "haughton": {"sources": ["nasa_planetary_analogs"], "named_as": "Mars analog",
                 "known_for": [("mars", "mean_temperature_K")], "not_measured": "impact-crater terrain for Martian EVAs"},
    "dryvalleys": {"sources": ["ntrs_20100003844"], "named_as": "Mars analog",
                   "known_for": [("mars", "mean_temperature_K")], "not_measured": "ground ice like the Phoenix landing plains"},
    "maunakea": {"sources": ["ntrs_20110008363"], "named_as": "lunar analog",
                 "known_for": [("moon", "thermal_swing_K"), ("moon", "slope_deg"), ("moon", "roughness_m")],
                 "not_measured": "lunar resource (ISRU) field testing"},
}

UNITS = {"thermal_swing_K": "K", "mean_temperature_K": "K", "slope_deg": "°", "roughness_m": "m"}


def find_row(rows, body, metric):
    return next(r for r in rows if r["body"] == body and r["metric"] == metric)


def key(body, metric):
    return f"{body}/{metric}"


# --- Check 1: benchmarks ------------------------------------------------------------

def rank_entry(row):
    """The numbers for one comparison, copied from the scored row."""
    return {"rank": row.get("rank"), "of": row.get("of"), "earth": row["earth"], "ref": row["ref"],
            "gap": row["gap"], "score": row["score"], "label": row["label"]}


def leader(rows_by_site, body, metric):
    """The site ranked 1 for this comparison, and its row."""
    for site, rows in rows_by_site.items():
        r = find_row(rows, body, metric)
        if r.get("rank") == 1:
            return site, r
    return None, None


def benchmark_check(rows_by_site, sources, not_assessed):
    """For each benchmark: its rank on every comparison, and whether it is near the top
    on the comparisons it is known for, with a reason built from the numbers."""
    results = []
    for site, b in BENCHMARKS.items():
        rows = rows_by_site[site]
        ranks = {key(bd, m): rank_entry(find_row(rows, bd, m)) for bd, m in CHECKS}
        findings = []
        for bd, m in b["known_for"]:
            e = ranks[key(bd, m)]
            name = find_row(rows, bd, m)["name"]
            u = UNITS[m]
            if e["rank"] is None:
                findings.append({"comparison": key(bd, m), "near_top": None,
                                 "text": f"{name} vs {bd.capitalize()}: not assessed ({not_assessed.get(site, 'no value')})."})
                continue
            near = e["rank"] <= NEAR_TOP_RANK
            text = (f"{name} vs {bd.capitalize()}: rank {e['rank']} of {e['of']}; {site} {e['earth']} {u} vs "
                    f"{e['ref']} {u}, gap {e['gap']} {u}, {label_and_score(e['label'], e['score'])}.")
            if not near:
                top_site, top = leader(rows_by_site, bd, m)
                text += (f" Not near the top: the closest site, {top_site}, has {top['earth']} {u} "
                         f"(gap {top['gap']} {u}).")
                if e["rank"] == e["of"]:
                    text += f" {site} has the largest gap of all {e['of']} sites on this metric."
            elif e["label"] == "weak":
                text += " Near the top, but still a weak match."
            findings.append({"comparison": key(bd, m), "near_top": near, "text": text})
        results.append({
            "site": site, "named_as": b["named_as"],
            "sources": [{"id": sid, "url": sources[sid]["url"], "quote": sources[sid]["quotes"][site]} for sid in b["sources"]],
            "ranks": ranks, "findings": findings,
            "not_measured": f"The source names {site} for {b['not_measured']}, which no number in this atlas measures.",
        })
    return results


# --- Check 2: negative control and single-metric matches -----------------------------

def find_control_rows(folder):
    """Rows for an Amazon control point in any CSV in the AppEEARS folder, and the files checked."""
    files = sorted(folder.glob("*.csv"))
    rows = []
    for f in files:
        with f.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if "amazon" in (r.get("ID", "") + r.get("Category", "")).lower():
                    rows.append(r)
    return rows, [f.name for f in files]


def control_check(folder, config, thermal, terrain, rows_by_site, tau):
    """Score the Amazon control with the same rules and tau, then rank it among the sites."""
    control_rows, checked = find_control_rows(folder)
    if not control_rows:
        return {"status": "pending: control request not finished", "files_checked": checked}

    summary = thermal_py.site_summary(control_rows)   # same QC rules as thermal.py
    name = control_rows[0]["ID"]
    values = {"thermal_swing_K": summary["mean_swing"]["K"], "mean_temperature_K": summary["mean_temperature"]["K"],
              "slope_deg": None, "roughness_m": None}
    result = {"status": "done", "site": name, "records": summary["records"],
              "values": {"mean_swing_K": values["thermal_swing_K"], "mean_temperature_K": values["mean_temperature_K"]},
              "comparisons": {}}
    for bd, m in CHECKS[:2]:   # the control has no terrain tile
        ref = config["references"][bd][m]["value"]
        t = tau[(bd, m)]
        x = values[m]
        s = score(x, ref, t)
        gap = None if x is None else round(abs(x - ref), 2)
        # Rank among the atlas sites plus the control (1 = smallest gap). Tau is not changed by the control.
        gaps = [find_row(rows, bd, m)["gap"] for rows in rows_by_site.values()]
        gaps = [g for g in gaps if g is not None]
        rank = None if gap is None else 1 + sum(g < gap for g in gaps)
        result["comparisons"][key(bd, m)] = {
            "earth": x, "ref": ref, "gap": gap, "score": None if s is None else round(s, 2),
            "label": label(s, config["labels"]["strong"], config["labels"]["partial"]),
            "rank": rank, "of": None if gap is None else len(gaps) + 1}
    return result


def single_metric_check(rows_by_site, a="maunakea", b="atacama"):
    """Compare two sites one metric at a time, and find metrics where two sites tie."""
    lines, per_metric = [], {}
    for bd, m in CHECKS:
        ra, rb = find_row(rows_by_site[a], bd, m), find_row(rows_by_site[b], bd, m)
        u = UNITS[m]
        if ra["earth"] is None or rb["earth"] is None:
            continue
        closer = a if ra["gap"] < rb["gap"] else b if rb["gap"] < ra["gap"] else "tie"
        diff = round(abs(ra["earth"] - rb["earth"]), 2)
        per_metric[key(bd, m)] = {a: rank_entry(ra), b: rank_entry(rb), "difference": diff, "closer": closer}
        lines.append(f"{ra['name']} vs {bd.capitalize()}: {a} {ra['earth']} {u} (rank {ra['rank']} of {ra['of']}), "
                     f"{b} {rb['earth']} {u} (rank {rb['rank']} of {rb['of']}); {diff} {u} apart; closer: {closer}.")
    wins = {s: sum(v["closer"] == s for v in per_metric.values()) for s in (a, b)}
    lines.append(f"{a} is closer on {wins[a]} of {len(per_metric)} metrics and {b} on {wins[b]}.")

    # One site can rank first on one terrain metric and last on another.
    for site in (a, b):
        slope, rough = find_row(rows_by_site[site], "moon", "slope_deg"), find_row(rows_by_site[site], "moon", "roughness_m")
        if slope.get("rank") and rough.get("rank") and slope["rank"] != rough["rank"]:
            lines.append(f"{site} ranks {slope['rank']} of {slope['of']} on slope but {rough['rank']} of "
                         f"{rough['of']} on roughness, so one terrain metric alone does not show a terrain match.")

    # Ties: two different sites with the same value on one metric cannot be told apart by it.
    ties = []
    for bd, m in CHECKS:
        seen = {}
        for site, rows in rows_by_site.items():
            v = find_row(rows, bd, m)["earth"]
            if v is not None:
                seen.setdefault(v, []).append(site)
        for v, sites in seen.items():
            if len(sites) > 1:
                ties.append({"comparison": key(bd, m), "value": v, "sites": sites})
                lines.append(f"{' and '.join(sites)} have the same {find_row(rows_by_site[sites[0]], bd, m)['name']} "
                             f"({v} {UNITS[m]}), so that metric alone cannot tell them apart.")
    return {"pair": [a, b], "per_metric": per_metric, "closer_count": wins, "ties": ties, "lines": lines}


# --- Check 3: sensitivity of labels and rankings to tau -------------------------------

def competition_ranks(values):
    """{site: rank} with 1 = highest score; equal scores share a rank (1, 1, 3)."""
    return {s: 1 + sum(o > v for o in values.values()) for s, v in values.items()}


def sensitivity_check(config, rows_by_site, tau):
    """Multiply every tau by each factor; count label changes and ranking changes."""
    strong, partial = config["labels"]["strong"], config["labels"]["partial"]

    def run(factor):
        out = {}
        for site, rows in rows_by_site.items():
            for r in rows:
                t = tau[(r["body"], r["metric"])]
                s = score(r["earth"], r["ref"], None if t is None else t * factor)
                out[(site, r["body"], r["metric"])] = s
        return out

    base = run(1.0)
    report = []
    for f in FACTORS:
        new = run(f)
        changed = []
        for k, s0 in base.items():
            l0, l1 = label(s0, strong, partial), label(new[k], strong, partial)
            if l0 != l1:
                changed.append({"site": k[0], "comparison": key(k[1], k[2]), "from": l0, "to": l1,
                                "from_score": round(s0, 2), "to_score": round(new[k], 2)})
        scored = [k for k, s in base.items() if s is not None]
        rankings = {}
        for bd, m in CHECKS:
            b0 = {k[0]: base[k] for k in scored if k[1:] == (bd, m)}
            b1 = {k[0]: new[k] for k in scored if k[1:] == (bd, m)}
            r0, r1 = competition_ranks(b0), competition_ranks(b1)
            # Ranking by gap (the atlas's ranking) does not use tau, so it cannot change.
            # Scores stop at 0, so sites far from the reference all tie at 0; ranking
            # changes by score mostly come from sites joining or leaving that tie.
            rankings[key(bd, m)] = {"sites": len(b0), "gap_rank_changes": 0,
                                    "score_rank_changes": sum(r0[s] != r1[s] for s in r0),
                                    "zero_scores_before": sum(v == 0 for v in b0.values()),
                                    "zero_scores_after": sum(v == 0 for v in b1.values()),
                                    "score_ranks_before": r0, "score_ranks_after": r1}
        report.append({
            "factor": f, "label_changes": len(changed), "labels_compared": len(scored), "changed": changed,
            "max_score_change": round(max(abs(new[k] - base[k]) for k in scored), 2),
            "rankings": rankings,
        })
    labels_now = {}
    for k in base:
        if base[k] is not None:
            lab = label(base[k], strong, partial)
            labels_now[lab] = labels_now.get(lab, 0) + 1
    return {"factors": FACTORS, "labels_now": labels_now, "runs": report}


# --- What we would change (printed, not applied) --------------------------------------

def would_change(benchmarks, control, sensitivity, terrain):
    """Suggestions that follow from the results. None of them is applied."""
    out = []
    for b in benchmarks:
        for f in b["findings"]:
            if f["near_top"] is False:
                out.append(f"{b['site']}: does not rank near the top on {f['comparison']}; would not change any "
                           f"tolerance to move it. {b['not_measured']} Would add a metric for that.")
    if control["status"] != "done":
        out.append("Negative control: would finish the Amazon AppEEARS request and rerun validate.py.")
    if all(r["label_changes"] == 0 for r in sensitivity["runs"]):
        now = ", ".join(f"{n} {lab}" for lab, n in sensitivity["labels_now"].items())
        out.append(f"Sensitivity: no label changes at ±20% because the labels now are {now}; "
                   "would show the scores beside the labels so small differences stay visible.")
    if terrain["not_assessed"]:
        sites = " and ".join(x["site"] for x in terrain["not_assessed"])
        out.append(f"Terrain: {sites} have no terrain numbers (outside SRTM); would add a polar elevation dataset.")
    return out


def main():
    config, thermal, terrain = load_inputs()
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    earth, tau, rows_by_site = scored_rows(config, thermal, terrain)
    not_assessed = {x["site"]: x["reason"] for x in terrain["not_assessed"]}

    benchmarks = benchmark_check(rows_by_site, sources, not_assessed)
    control = control_check(APPEEARS_DIR, config, thermal, terrain, rows_by_site, tau)
    single = single_metric_check(rows_by_site)
    sensitivity = sensitivity_check(config, rows_by_site, tau)
    suggestions = would_change(benchmarks, control, sensitivity, terrain)

    result = {
        "inputs": ["config.json", "thermal.json", "terrain.json", "sources.json", "score.py"],
        "rules": {"near_top_rank": NEAR_TOP_RANK, "sensitivity_factors": FACTORS,
                  "ranking": "rank 1 = smallest gap to the reference (as in cards.json)",
                  "note": "results as computed; no parameter was tuned"},
        "tau": {key(*k): None if v is None else round(v, 2) for k, v in tau.items()},
        "benchmarks": benchmarks,
        "control": control,
        "single_metric": single,
        "sensitivity": sensitivity,
        "would_change_not_applied": suggestions,
    }
    OUT_PATH.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print("=== 1. Benchmarks ===")
    for b in benchmarks:
        print(f"{b['site']} ({b['named_as']}):")
        for f in b["findings"]:
            print(f"   - {f['text']}")
    print("\n=== 2. Negative control ===")
    print(f"   {control['status']}" + ("" if control["status"] == "done" else f" (files checked: {', '.join(control['files_checked'])})"))
    for line in single["lines"]:
        print(f"   - {line}")
    print("\n=== 3. Sensitivity (every tau x 0.8 and x 1.2) ===")
    print(f"   labels now: {sensitivity['labels_now']}")
    for r in sensitivity["runs"]:
        print(f"   x{r['factor']}: {r['label_changes']} of {r['labels_compared']} labels change; "
              f"largest score change {r['max_score_change']}")
        for k, v in r["rankings"].items():
            print(f"      {k}: gap-rank changes {v['gap_rank_changes']}, score-rank changes "
                  f"{v['score_rank_changes']} of {v['sites']} (sites at score 0: {v['zero_scores_before']} -> {v['zero_scores_after']})")
    print("\n=== What we would change (NOT changed) ===")
    for s in suggestions:
        print(f"   - {s}")
    print(f"\nWrote {OUT_PATH}")


# Run main() only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    main()
