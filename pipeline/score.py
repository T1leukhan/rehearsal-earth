"""
score.py - Score how well each Earth site matches the Moon and Mars references.

Inputs:  app/data/config.json   (reference values, tolerances, labels)
         app/data/thermal.json  (Earth day-night swing per site)
         app/data/terrain.json  (Earth slope and roughness, where we have it)
Output:  app/data/cards.json    (per site: a thermal card and a terrain card, four boxes each)

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\score.py

The score for one number:
    s = max(0, 1 - |x_earth - x_ref| / tau)
  * x_earth = the Earth site's value, x_ref = the Moon or Mars value
  * tau ("tolerance") = how big a gap still counts as somewhat similar
  * s = 1 means identical; s = 0 means the gap is tau or more.
Tau rules (set per body and metric in config.json):
  * "equal_to_reference": tau = x_ref. Used for the Moon swing, so for a
    site below the lunar swing, s = x_earth / x_ref = share of it reproduced.
  * "stdev_of_site_values": tau = sample standard deviation of the sites'
    values (sites with no value are left out). Used for the Mars mean
    temperature (5 sites) and the Moon slope and roughness (3 sites).
  * otherwise tau = the "value" in config.json (null = not assessed).
Labels: strong if s >= 0.8, partial if 0.5 <= s < 0.8, weak if s < 0.5.
If any of x_earth, x_ref or tau is missing (null), there is no score:
the comparison is "not assessed" and is never guessed.
"""

import json
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "app" / "data"

# The numbers we compare, with their units and a readable name.
METRICS = {
    "thermal_swing_K": ("day-night temperature swing", "K"),
    "slope_deg": ("median slope", "deg"),
    "roughness_m": ("median roughness", "m"),
    "mean_temperature_K": ("mean temperature", "K"),
}

# Terrain metrics with no score are collapsed into one line per body on the cards.
TERRAIN = {"slope_deg", "roughness_m"}


def terrain_line(body, reason):
    """The one card line for all unscored terrain metrics against one body."""
    return f"Not assessed: terrain (slope, roughness) vs {body.capitalize()} ({reason})"


# --- The score itself -------------------------------------------------------

def score(x_earth, x_ref, tau):
    """Similarity from 0 to 1. Returns None if any input is missing."""
    if x_earth is None or x_ref is None or tau is None:
        return None
    if tau <= 0:
        raise ValueError("tau must be greater than 0")
    return max(0.0, 1 - abs(x_earth - x_ref) / tau)


def label_and_score(lab, s):
    """A label with its score next to it, e.g. "weak (0.07)", for the card text.

    s is the score already stored on the row (rounded to 0.01); nothing is re-scored here.
    """
    return lab if s is None else f"{lab} ({s:.2f})"


def label(s, strong=0.8, partial=0.5):
    """Turn a score into a word."""
    if s is None:
        return "not assessed"
    if s >= strong:
        return "strong"
    if s >= partial:
        return "partial"
    return "weak"


# --- Collect the Earth values -----------------------------------------------

def earth_values(thermal, terrain):
    """Return {site: {metric: value or None}} from thermal.json and terrain.json.

    Terrain is matched to a site by its name (the key in terrain.json "sites"),
    not by position: a terrain square may sit away from the thermal point.
    """
    values = {}
    for site, t in thermal["sites"].items():
        square = terrain["sites"].get(site, {}).get("areas", {}).get("square_10km")
        values[site] = {
            "thermal_swing_K": t["mean_swing"]["K"],
            "slope_deg": square["slope_deg"]["median"] if square else None,
            "roughness_m": square["roughness_m"]["median"] if square else None,
            "mean_temperature_K": t["mean_temperature"]["K"],
        }
    return values


def tolerances(config, earth):
    """Tau for every (body, metric) pair, following the rule in config.json."""
    tau = {}
    for body, refs in config["references"].items():
        for metric in METRICS:
            rule = config["tolerance"][body][metric]
            if rule.get("rule") == "equal_to_reference":
                tau[(body, metric)] = refs[metric]["value"]
            elif rule.get("rule") == "stdev_of_site_values":
                values = [v[metric] for v in earth.values() if v[metric] is not None]
                # Sample standard deviation: divide by (n - 1). Needs at least 2 sites.
                tau[(body, metric)] = statistics.stdev(values) if len(values) >= 2 else None
            else:
                tau[(body, metric)] = rule.get("value")
    return tau


# --- Build one card -----------------------------------------------------------

def compare(site_values, config, tau):
    """Every (body, metric) comparison for one site, with score and label."""
    rows = []
    for body, refs in config["references"].items():
        for metric, (name, unit) in METRICS.items():
            ref = refs[metric]["value"]
            t = tau[(body, metric)]
            earth = site_values[metric]
            s = score(earth, ref, t)
            row = {
                "body": body, "metric": metric, "name": name, "unit": unit,
                "earth": earth, "ref": ref, "tau": None if t is None else round(t, 2),
                "gap": None if earth is None or ref is None else round(abs(earth - ref), 2),
                "score": None if s is None else round(s, 2),
                "label": label(s, config["labels"]["strong"], config["labels"]["partial"]),
            }
            if ref is None:
                row["note"] = refs[metric].get("note")  # why the reference is missing
            elif earth is None:
                row["note"] = "no value for this site"
            # Optionally show the Earth value as a percent of the reference.
            if config["tolerance"][body][metric].get("report_percent_of_reference"):
                row["percent_of_ref"] = None if earth is None or not ref else round(100 * earth / ref, 1)
            rows.append(row)
    return rows


def describe(row):
    """One line of text for a comparison that has a score."""
    gap = abs(row["earth"] - row["ref"])
    body = row["body"].capitalize()
    text = (f"{row['name'].capitalize()} vs {body}: "
            f"Earth {row['earth']} {row['unit']}, {body} {row['ref']} {row['unit']}, "
            f"gap {gap:.2f} vs tolerance {row['tau']:.2f} {row['unit']} "
            f"-> {label_and_score(row['label'], row['score'])}")
    if row.get("percent_of_ref") is not None:
        text += f"; the site's {row['name']} is {row['percent_of_ref']}% of the {body}'s"
    return text


def add_ranks(rows_by_site):
    """Rank the sites for each (body, metric): rank 1 = smallest gap to the reference.

    Adds "rank" and "of" (how many sites were ranked) to each row that has a gap.
    """
    pairs = {(r["body"], r["metric"]) for rows in rows_by_site.values() for r in rows}
    for body, metric in pairs:
        ranked = [r for rows in rows_by_site.values() for r in rows
                  if r["body"] == body and r["metric"] == metric and r["gap"] is not None]
        ranked.sort(key=lambda r: r["gap"])
        for position, r in enumerate(ranked, start=1):
            r["rank"], r["of"] = position, len(ranked)


def find(rows, body, metric):
    """The comparison row for one body and metric."""
    return next(r for r in rows if r["body"] == body and r["metric"] == metric)


def use_text(rows, site_thermal, config):
    """'How engineers use it': built only from numbers in the JSON files.

    Every number here is copied from thermal.json, config.json or the
    comparison rows (which are saved in cards.json).
    """
    rules = config["use_rules"]
    partial = config["labels"]["partial"]
    lines = []

    moon = find(rows, "moon", "thermal_swing_K")
    if moon["gap"] is None:
        lines.append("Moon swing: not assessed.")
    else:
        lines.append(f"Moon swing: rank {moon['rank']} of {moon['of']}. Swing {moon['earth']} K is "
                     f"{moon['percent_of_ref']}% of the Moon's {moon['ref']} K, a gap of {moon['gap']} K.")

    mars = find(rows, "mars", "mean_temperature_K")
    if mars["gap"] is None:
        lines.append("Mars mean temperature: not assessed.")
    else:
        lines.append(f"Mars mean temperature: rank {mars['rank']} of {mars['of']}. Mean {mars['earth']} K "
                     f"vs Mars {mars['ref']} K, a gap of {mars['gap']} K.")

    low = site_thermal["lowest_temperature"]
    limit_c = rules["cold_soak_below_C"]
    if low["C"] is None:
        lines.append("Lowest temperature: not assessed.")
    else:
        lines.append(f"Lowest temperature: {low['C']} °C ({low['when']} average over one composite period, "
                     f"starting {low['date']}).")
        if low["C"] < limit_c:
            lines.append(f"Supports: cold-soak testing down to {low['C']} °C, below the {limit_c} °C threshold.")
        else:
            lines.append(f"Does not support cold-soak testing: {low['C']} °C is not below the {limit_c} °C threshold.")

    # Anything that scored partial or strong is something the site supports.
    for r in rows:
        if r["label"] in ("strong", "partial"):
            lines.append(f"Supports: {r['name']} testing for the {r['body'].capitalize()} "
                         f"({label_and_score(r['label'], r['score'])}).")

    limit_pct = rules["thermal_cycling_min_percent_of_moon"]
    pct = moon.get("percent_of_ref")
    if pct is not None and pct < limit_pct:
        lines.append(f"Cannot support lunar thermal cycling: swing is {pct}% of the Moon's, "
                     f"under the {limit_pct}% limit.")
    if mars["score"] is not None and mars["score"] < partial:
        lines.append(f"Cannot stand in for the Mars mean temperature: score {mars['score']} "
                     f"is below the {partial} needed for partial.")
    return lines


def terrain_use_text(rows, site_terrain, reason, config):
    """'How engineers use it' for the Terrain tab: built only from numbers in the JSON files.

    rows are the terrain comparison rows (saved in cards.json); site_terrain is the
    site's entry in terrain.json, or None if the site has no terrain numbers.
    """
    if site_terrain is None:
        return [f"Terrain: not assessed ({reason})."]

    rules = config["use_rules"]
    partial = config["labels"]["partial"]
    g = config["gravity_m_s2"]
    square = site_terrain["areas"]["square_10km"]
    p90 = square["slope_deg"]["p90"]
    pct = rules["slope_climbing_percentile"]
    lines = []

    slope = find(rows, "moon", "slope_deg")
    rough = find(rows, "moon", "roughness_m")
    lines.append(f"Moon slope: rank {slope['rank']} of {slope['of']}. Median slope {slope['earth']}° vs "
                 f"Malapert {slope['ref']}°, a gap of {slope['gap']}°; {pct}th percentile slope {p90}°.")
    lines.append(f"Moon roughness: rank {rough['rank']} of {rough['of']}. Median roughness {rough['earth']} m "
                 f"vs Malapert {rough['ref']} m, a gap of {rough['gap']} m.")

    # Slope climbing: is at least the steepest tenth of the square as steep as typical Malapert ground?
    if p90 >= slope["ref"]:
        lines.append(f"Supports: slope-climbing tests at the Malapert median slope of {slope['ref']}°: "
                     f"the site's {pct}th percentile slope is {p90}°, so its steepest tenth is at least that steep.")
    else:
        lines.append(f"Cannot support slope-climbing tests at the Malapert median slope of {slope['ref']}°: "
                     f"the site's {pct}th percentile slope is only {p90}°.")

    # Anything that scored partial or strong is something the site supports.
    for r in rows:
        if r["label"] in ("strong", "partial"):
            lines.append(f"Supports: {r['name']} testing for the {r['body'].capitalize()} "
                         f"({label_and_score(r['label'], r['score'])}).")
    for r in (slope, rough):
        if r["score"] is not None and r["score"] < partial:
            lines.append(f"Cannot stand in for the Malapert {r['name']}: score {r['score']} "
                         f"is below the {partial} needed for partial.")

    # Things no terrain number here can cover.
    lines.append(f"Cannot reproduce lunar loads: Earth gravity is {g['earth']['value']} m/s² vs the Moon's "
                 f"{g['moon']['value']} m/s², so wheel loads, sinkage and traction on these slopes are not lunar values.")
    lines.append("Cannot test lunar dust: this atlas has no dust or regolith grain data, so dust is not assessed.")
    return lines


def none_line(scored, missing, usual):
    """Text for an empty "Strong match" or "Breaks down" box.

    If nothing on this card was scored at all, say why and point to the other
    tab; otherwise use the usual wording. The reasons are the notes already
    on the missing comparison rows, so no new wording is invented here.
    """
    if scored:
        return usual
    reasons = dict.fromkeys(r.get("note") or "missing value" for r in missing)
    return f"No scored metric on this tab: {'; '.join(reasons)}; see the other tab"


def build_card(site, rows, gravity, use_lines=None):
    """Four boxes. Comparisons with no score are skipped in boxes 1 and 2."""
    scored = [r for r in rows if r["score"] is not None]
    strong = [r for r in scored if r["label"] == "strong"]
    weaker = [r for r in scored if r["label"] != "strong"]  # partial and weak
    missing = [r for r in rows if r["score"] is None]

    g_e, g_m, g_r = gravity["earth"]["value"], gravity["moon"]["value"], gravity["mars"]["value"]
    not_testable = [
        f"Gravity: Earth {g_e} m/s2 vs Moon {g_m} m/s2 and Mars {g_r} m/s2 "
        f"(Earth pulls {g_e / g_m:.1f}x and {g_e / g_r:.1f}x harder). "
        "Anything that depends on weight cannot be reproduced at this site."
    ]
    # Thermal items one by one; terrain items collapsed into one line per body.
    for r in missing:
        if r["metric"] not in TERRAIN:
            not_testable.append(f"Not assessed: {r['name']} vs {r['body'].capitalize()} "
                                f"({r.get('note') or 'missing value'})")
    for body in dict.fromkeys(r["body"] for r in missing if r["metric"] in TERRAIN):
        reasons = dict.fromkeys(r.get("note") or "missing value"
                                for r in missing if r["body"] == body and r["metric"] in TERRAIN)
        not_testable.append(terrain_line(body, "; ".join(reasons)))

    return {
        "site": site,
        "strong_match": [describe(r) for r in strong] or [none_line(scored, missing, "None: no metric scored 0.8 or more.")],
        "breaks_down": [describe(r) for r in weaker] or [none_line(scored, missing, "None of the scored metrics.")],
        "not_testable_on_earth": not_testable,
        "how_engineers_use_it": use_lines or ["Not assessed: no numbers to base this on."],
        "comparisons": rows,
    }


# --- Main ---------------------------------------------------------------------

def load_inputs():
    """config.json, thermal.json and terrain.json, as Python dicts."""
    return tuple(json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
                 for name in ("config", "thermal", "terrain"))


def scored_rows(config, thermal, terrain):
    """Earth values, tau and every site's ranked comparison rows.

    Used by main() below and by validate.py, so both score in exactly the same way.
    """
    earth = earth_values(thermal, terrain)
    tau = tolerances(config, earth)
    rows_by_site = {site: compare(v, config, tau) for site, v in earth.items()}
    add_ranks(rows_by_site)
    return earth, tau, rows_by_site


def main():
    config, thermal, terrain = load_inputs()
    earth, tau, rows_by_site = scored_rows(config, thermal, terrain)

    # Where a site has no terrain numbers, say why (from terrain.json).
    reasons = {x["site"]: x["reason"] for x in terrain["not_assessed"]}
    for site, rows in rows_by_site.items():
        for r in rows:
            if r["metric"] in TERRAIN and r["earth"] is None and site in reasons:
                r["note"] = reasons[site]

    # Two cards per site: thermal (Thermal tab) and terrain (Terrain tab).
    # Both keep all comparison rows in "comparisons", so every number stays traceable.
    cards = []
    for site, rows in rows_by_site.items():
        thermal_rows = [r for r in rows if r["metric"] not in TERRAIN]
        terrain_rows = [r for r in rows if r["metric"] in TERRAIN]
        card = build_card(site, thermal_rows, config["gravity_m_s2"],
                          use_text(thermal_rows, thermal["sites"][site], config))
        card["comparisons"] = rows
        terrain_card = build_card(site, terrain_rows, config["gravity_m_s2"],
                                  terrain_use_text(terrain_rows, terrain["sites"].get(site),
                                                   reasons.get(site), config))
        del terrain_card["comparisons"], terrain_card["site"]
        card["terrain"] = terrain_card
        cards.append(card)

    result = {
        "formula": "s = max(0, 1 - |x_earth - x_ref| / tau)",
        "labels": {"strong": ">= 0.8", "partial": "0.5 to < 0.8", "weak": "< 0.5",
                   "not assessed": "x_earth, x_ref or tau is null"},
        "tau": {f"{b}/{m}": None if t is None else round(t, 2) for (b, m), t in tau.items()},
        "tau_reason": {f"{b}/{m}": rule["reason"]
                       for b, rules in config["tolerance"].items()
                       for m, rule in rules.items() if "reason" in rule},
        "inputs": ["config.json", "thermal.json", "terrain.json"],
        "cards": cards,
    }
    (DATA / "cards.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

    print(f"tau: {result['tau']}")
    for c in cards:
        print(f"\n== {c['site']} ==")
        for label_, part in (("thermal", c), ("terrain", c["terrain"])):
            for box in ("strong_match", "breaks_down", "not_testable_on_earth", "how_engineers_use_it"):
                print(f" [{label_}: {box}]")
                for line in part[box]:
                    print(f"   - {line}")
    print(f"\nWrote {DATA / 'cards.json'}")


if __name__ == "__main__":
    main()
