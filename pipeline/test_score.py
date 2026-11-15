"""
Tests for score.py. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)
"""

import statistics

import pytest

from score import (TERRAIN, add_ranks, build_card, compare, earth_values, label, score, terrain_line,
                   terrain_use_text, tolerances, use_text)

GRAVITY = {"earth": {"value": 9.81}, "moon": {"value": 1.62}, "mars": {"value": 3.71}}


def test_identical_values_give_1():
    assert score(22.24, 22.24, 11.0) == 1.0


def test_gap_equal_to_tau_gives_0():
    assert score(10.0, 21.0, 11.0) == 0.0


def test_gap_bigger_than_tau_gives_0():
    # The Moon's 300 K swing vs an Earth site: far more than tau apart.
    assert score(22.24, 300.0, 11.0) == 0.0


def test_half_tau_gap_gives_half():
    assert score(10.0, 15.0, 10.0) == pytest.approx(0.5)


@pytest.mark.parametrize("x_earth, x_ref, tau", [
    (None, 300.0, 11.0),   # Earth value missing
    (22.24, None, 11.0),   # reference missing (e.g. Mars terrain)
    (22.24, 300.0, None),  # tolerance missing
])
def test_null_values_give_no_score(x_earth, x_ref, tau):
    assert score(x_earth, x_ref, tau) is None
    assert label(score(x_earth, x_ref, tau)) == "not assessed"


def test_labels_at_the_boundaries():
    assert label(0.8) == "strong"
    assert label(0.79) == "partial"
    assert label(0.5) == "partial"
    assert label(0.49) == "weak"


def test_null_comparisons_are_skipped_in_card():
    # Terrain items with no score are collapsed into one line per body.
    rows = [
        {"body": "moon", "metric": "thermal_swing_K", "name": "swing", "unit": "K", "earth": 22.0,
         "ref": 22.0, "tau": 11.0, "score": 1.0, "label": "strong"},
        {"body": "moon", "metric": "slope_deg", "name": "median slope", "unit": "deg", "earth": 3.5,
         "ref": None, "tau": None, "score": None, "label": "not assessed"},
    ]
    card = build_card("test", rows, GRAVITY)
    assert len(card["strong_match"]) == 1
    assert "slope" not in " ".join(card["strong_match"] + card["breaks_down"])
    assert terrain_line("moon", "missing value") in card["not_testable_on_earth"]


def test_zero_tau_is_an_error():
    with pytest.raises(ValueError):
        score(1.0, 2.0, 0.0)


# --- Tau rules (added with the per-body tolerance rules) ------------------------

def small_config():
    """A tiny config with the same tau rules as app/data/config.json."""
    null = {"value": None}
    return {
        "references": {
            "moon": {"thermal_swing_K": {"value": 300}, "mean_temperature_K": null,
                     "slope_deg": null, "roughness_m": null},
            "mars": {"thermal_swing_K": null, "mean_temperature_K": {"value": 214},
                     "slope_deg": null, "roughness_m": null},
        },
        "tolerance": {
            "moon": {"thermal_swing_K": {"rule": "equal_to_reference", "report_percent_of_reference": True},
                     "mean_temperature_K": null, "slope_deg": null, "roughness_m": null},
            "mars": {"mean_temperature_K": {"rule": "stdev_of_site_values"},
                     "thermal_swing_K": null, "slope_deg": null, "roughness_m": null},
        },
        "labels": {"strong": 0.8, "partial": 0.5},
    }


def site(swing, mean_temp):
    return {"thermal_swing_K": swing, "mean_temperature_K": mean_temp,
            "slope_deg": None, "roughness_m": None}


EARTH = {"a": site(30.0, 300.0), "b": site(3.0, 240.0), "c": site(15.0, 270.0)}


def test_moon_swing_tau_equals_reference():
    assert tolerances(small_config(), EARTH)[("moon", "thermal_swing_K")] == 300


def test_moon_score_is_share_of_lunar_swing():
    rows = compare(EARTH["a"], small_config(), tolerances(small_config(), EARTH))
    swing = next(r for r in rows if r["body"] == "moon" and r["metric"] == "thermal_swing_K")
    assert swing["score"] == pytest.approx(30.0 / 300)   # 0.1 of the lunar swing
    assert swing["percent_of_ref"] == 10.0


def test_mars_mean_temperature_tau_is_stdev_of_sites():
    tau = tolerances(small_config(), EARTH)[("mars", "mean_temperature_K")]
    assert tau == pytest.approx(statistics.stdev([300.0, 240.0, 270.0]))  # 30.0


def test_null_tolerance_stays_null():
    tau = tolerances(small_config(), EARTH)
    assert tau[("moon", "slope_deg")] is None
    assert tau[("mars", "thermal_swing_K")] is None


# --- Card text (added with the generated "How engineers use it") ----------------

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "data"


def test_terrain_collapsed_but_thermal_items_listed():
    rows = [
        {"body": "mars", "metric": "thermal_swing_K", "name": "day-night temperature swing", "unit": "K",
         "earth": 5.0, "ref": None, "tau": None, "score": None, "label": "not assessed", "note": "no ref"},
        {"body": "moon", "metric": "slope_deg", "name": "median slope", "unit": "deg",
         "earth": None, "ref": None, "tau": None, "score": None, "label": "not assessed"},
        {"body": "mars", "metric": "roughness_m", "name": "median roughness", "unit": "m",
         "earth": None, "ref": None, "tau": None, "score": None, "label": "not assessed"},
    ]
    rows[1]["note"] = "no value for this site"
    rows[2]["note"] = "no Mars terrain reference given"
    lines = build_card("test", rows, GRAVITY)["not_testable_on_earth"]
    assert any("day-night temperature swing vs Mars" in line for line in lines)
    # One terrain line per body, each with its reason.
    assert terrain_line("moon", "no value for this site") in lines
    assert terrain_line("mars", "no Mars terrain reference given") in lines
    assert sum("terrain (slope, roughness)" in line for line in lines) == 2
    assert not any("median slope" in line or "median roughness" in line for line in lines)


def test_rank_1_is_smallest_gap():
    rows_by_site = {s: [{"body": "moon", "metric": "m", "gap": g}] for s, g in
                    [("a", 50.0), ("b", 10.0), ("c", None), ("d", 30.0)]}
    add_ranks(rows_by_site)
    assert [rows_by_site[s][0].get("rank") for s in "abcd"] == [3, 1, None, 2]
    assert rows_by_site["a"][0]["of"] == 3                    # site c had no value


def make_rows(percent, mars_score):
    moon = {"body": "moon", "metric": "thermal_swing_K", "name": "swing", "earth": 3.0 * percent,
            "ref": 300, "gap": 300 - 3.0 * percent, "percent_of_ref": percent,
            "score": percent / 100, "label": "weak", "rank": 1, "of": 5}
    mars = {"body": "mars", "metric": "mean_temperature_K", "name": "mean temperature", "earth": 240.0,
            "ref": 214, "gap": 26.0, "score": mars_score, "label": "weak", "rank": 1, "of": 5}
    return [moon, mars]


CONFIG = {"use_rules": {"cold_soak_below_C": 0, "thermal_cycling_min_percent_of_moon": 10},
          "labels": {"strong": 0.8, "partial": 0.5}}


def lowest(c):
    return {"lowest_temperature": {"C": c, "date": "2023-08-13", "when": "night"}}


def test_thermal_cycling_rule_uses_10_percent():
    under = " ".join(use_text(make_rows(7.4, 0.0), lowest(5.0), CONFIG))
    over = " ".join(use_text(make_rows(12.0, 0.0), lowest(5.0), CONFIG))
    assert "Cannot support lunar thermal cycling" in under
    assert "Cannot support lunar thermal cycling" not in over


def test_cold_soak_rule_uses_0_C():
    cold = " ".join(use_text(make_rows(5.0, 0.0), lowest(-43.33), CONFIG))
    warm = " ".join(use_text(make_rows(5.0, 0.0), lowest(7.11), CONFIG))
    assert "Supports: cold-soak testing down to -43.33 °C" in cold
    assert "Does not support cold-soak testing" in warm


def all_numbers(obj, found):
    """Collect every number and every date string inside a JSON object."""
    if isinstance(obj, bool):
        return found
    if isinstance(obj, (int, float)):
        found.add(round(float(obj), 6))
    elif isinstance(obj, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", obj):
        found.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            all_numbers(v, found)
    elif isinstance(obj, list):
        for v in obj:
            all_numbers(v, found)
    return found


def test_every_number_in_use_text_is_in_the_json_files():
    # Run score.py first: this checks the real cards.json.
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    thermal = json.loads((DATA / "thermal.json").read_text(encoding="utf-8"))
    config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
    for card in cards["cards"]:
        allowed = all_numbers(card["comparisons"], set())
        allowed |= all_numbers(thermal["sites"][card["site"]], set())
        allowed |= all_numbers({"labels": config["labels"], "rules": config["use_rules"]}, set())
        for line in card["how_engineers_use_it"]:
            for date in re.findall(r"\d{4}-\d{2}-\d{2}", line):
                assert date in allowed, f"{card['site']}: date {date} not in JSON"
            numbers = re.findall(r"-?\d+(?:\.\d+)?", re.sub(r"\d{4}-\d{2}-\d{2}", "", line))
            for n in numbers:
                assert round(float(n), 6) in allowed, f"{card['site']}: {n} in '{line}' not in JSON"


# --- Terrain matched by site name, scored with the spread of 3 sites ------------

def square(slope, rough):
    return {"areas": {"square_10km": {"slope_deg": {"median": slope}, "roughness_m": {"median": rough}}}}


def test_terrain_matched_by_name_not_by_position():
    thermal = {"sites": {
        "a": {"latitude": -20.0, "longitude": -68.0, "mean_swing": {"K": 5.0}, "mean_temperature": {"K": 280.0}},
        "b": {"latitude": 10.0, "longitude": 10.0, "mean_swing": {"K": 6.0}, "mean_temperature": {"K": 281.0}},
    }}
    # Site a's square is centred somewhere else; it must still be matched to a.
    terrain = {"sites": {"a": {"square_centre_lat_lon_deg": [-20.5, -68.5], **square(3.4, 0.7)}}}
    values = earth_values(thermal, terrain)
    assert values["a"]["slope_deg"] == 3.4 and values["a"]["roughness_m"] == 0.7
    assert values["b"]["slope_deg"] is None and values["b"]["roughness_m"] is None


def terrain_config():
    config = small_config()
    config["references"]["moon"]["slope_deg"] = {"value": 17.81}
    config["references"]["moon"]["roughness_m"] = {"value": 0.36}
    config["tolerance"]["moon"]["slope_deg"] = {"rule": "stdev_of_site_values"}
    config["tolerance"]["moon"]["roughness_m"] = {"rule": "stdev_of_site_values"}
    return config


EARTH_T = {
    "x": {**site(5.0, 280.0), "slope_deg": 5.37, "roughness_m": 0.71},
    "y": {**site(6.0, 281.0), "slope_deg": 3.41, "roughness_m": 0.71},
    "z": {**site(7.0, 282.0), "slope_deg": 13.94, "roughness_m": 0.81},
    "w": site(8.0, 283.0),   # no terrain: left out of the spread
}


def test_terrain_tau_is_stdev_of_the_three_measured_sites():
    tau = tolerances(terrain_config(), EARTH_T)
    assert tau[("moon", "slope_deg")] == pytest.approx(statistics.stdev([5.37, 3.41, 13.94]))
    assert tau[("moon", "roughness_m")] == pytest.approx(statistics.stdev([0.71, 0.71, 0.81]))


def test_terrain_score_uses_the_same_rule_as_thermal():
    tau = tolerances(terrain_config(), EARTH_T)
    rows = compare(EARTH_T["z"], terrain_config(), tau)
    slope = next(r for r in rows if r["body"] == "moon" and r["metric"] == "slope_deg")
    assert slope["score"] == pytest.approx(max(0, 1 - abs(13.94 - 17.81) / tau[("moon", "slope_deg")]), abs=0.005)
    no_terrain = compare(EARTH_T["w"], terrain_config(), tau)
    assert next(r for r in no_terrain if r["metric"] == "slope_deg" and r["body"] == "moon")["score"] is None


def test_real_config_terrain_tolerance_has_rule_and_reason():
    config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
    expected = {"slope_deg": "stdev_of_site_values", "roughness_m": "equal_to_reference"}
    for key, rule_name in expected.items():
        rule = config["tolerance"]["moon"][key]
        assert rule["rule"] == rule_name
        # One sentence: a single full stop, at the end.
        assert rule["reason"].count(". ") == 0 and rule["reason"].endswith(".")
    assert "as large as the Moon's own roughness counts as no match" in config["tolerance"]["moon"]["roughness_m"]["reason"]


def test_real_cards_score_terrain_for_the_three_sites():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    terrain = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
    for card in cards["cards"]:
        for row in card["comparisons"]:
            if row["body"] == "moon" and row["metric"] in ("slope_deg", "roughness_m"):
                assert (row["score"] is not None) == (card["site"] in terrain["sites"])


# --- Roughness tau = the Moon's own roughness; terrain cards ---------------------

def test_roughness_tau_is_the_moon_roughness():
    config = terrain_config()
    config["tolerance"]["moon"]["roughness_m"] = {"rule": "equal_to_reference"}
    tau = tolerances(config, EARTH_T)
    assert tau[("moon", "roughness_m")] == 0.36
    assert tau[("moon", "slope_deg")] == pytest.approx(statistics.stdev([5.37, 3.41, 13.94]))   # kept
    rows = compare(EARTH_T["x"], config, tau)
    rough = next(r for r in rows if r["body"] == "moon" and r["metric"] == "roughness_m")
    assert rough["score"] == pytest.approx(round(1 - abs(0.71 - 0.36) / 0.36, 2))   # 0.03


def test_real_cards_roughness_scores():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    assert cards["tau"]["moon/roughness_m"] == 0.36
    for card in cards["cards"]:
        r = next(x for x in card["comparisons"] if x["body"] == "moon" and x["metric"] == "roughness_m")
        if r["earth"] is not None:
            assert r["tau"] == 0.36
            assert r["score"] == round(max(0, 1 - abs(r["earth"] - r["ref"]) / 0.36), 2)


def terrain_rows(p90_site, ref=17.81, slope_score=0.3, rough_score=0.0):
    slope = {"body": "moon", "metric": "slope_deg", "name": "median slope", "earth": 10.0, "ref": ref,
             "gap": round(ref - 10.0, 2), "score": slope_score, "label": label(slope_score), "rank": 1, "of": 3}
    rough = {"body": "moon", "metric": "roughness_m", "name": "median roughness", "earth": 0.7, "ref": 0.36,
             "gap": 0.34, "score": rough_score, "label": label(rough_score), "rank": 2, "of": 3}
    site_terrain = {"areas": {"square_10km": {"slope_deg": {"p90": p90_site}}}}
    return [slope, rough], site_terrain


TERRAIN_CONFIG = {"use_rules": {"slope_climbing_percentile": 90}, "labels": {"strong": 0.8, "partial": 0.5},
                  "gravity_m_s2": GRAVITY}


def test_slope_climbing_needs_p90_at_least_the_moon_median():
    rows, steep = terrain_rows(21.65)
    text = " ".join(terrain_use_text(rows, steep, None, TERRAIN_CONFIG))
    assert "Supports: slope-climbing tests at the Malapert median slope of 17.81°" in text
    rows, gentle = terrain_rows(8.68)
    text = " ".join(terrain_use_text(rows, gentle, None, TERRAIN_CONFIG))
    assert "Cannot support slope-climbing tests" in text and "only 8.68°" in text
    rows, equal = terrain_rows(17.81)
    assert "Supports: slope-climbing" in " ".join(terrain_use_text(rows, equal, None, TERRAIN_CONFIG))


def test_terrain_text_names_loads_and_dust():
    rows, site_terrain = terrain_rows(21.65)
    text = " ".join(terrain_use_text(rows, site_terrain, None, TERRAIN_CONFIG))
    assert "Cannot reproduce lunar loads: Earth gravity is 9.81 m/s² vs the Moon's 1.62 m/s²" in text
    assert "Cannot test lunar dust" in text
    assert "Cannot stand in for the Malapert median slope: score 0.3" in text


def test_terrain_text_for_a_site_without_terrain():
    lines = terrain_use_text([], None, "outside SRTM coverage: latitude 75.4° is north of 60° N, SRTM's northern limit", TERRAIN_CONFIG)
    assert lines == ["Terrain: not assessed (outside SRTM coverage: latitude 75.4° is north of 60° N, SRTM's northern limit)."]


def test_real_cards_split_into_thermal_and_terrain():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    boxes = ("strong_match", "breaks_down", "not_testable_on_earth", "how_engineers_use_it")
    for card in cards["cards"]:
        assert all(card["terrain"][b] for b in boxes)
        # Thermal boxes say nothing about terrain; terrain boxes nothing about temperature.
        thermal_text = " ".join(line for b in boxes for line in card[b])
        terrain_text = " ".join(line for b in boxes for line in card["terrain"][b])
        assert "slope" not in thermal_text and "roughness" not in thermal_text
        assert "temperature" not in terrain_text and "swing" not in terrain_text
        # All comparisons (thermal and terrain, Moon and Mars) are kept for tracing.
        assert {(r["body"], r["metric"]) for r in card["comparisons"]} == {
            (b, m) for b in ("moon", "mars") for m in ("thermal_swing_K", "slope_deg", "roughness_m", "mean_temperature_K")}


def test_real_cards_without_terrain_say_why():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    terrain = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
    for gap in terrain["not_assessed"]:
        card = next(c for c in cards["cards"] if c["site"] == gap["site"])
        assert card["terrain"]["how_engineers_use_it"] == [f"Terrain: not assessed ({gap['reason']})."]
        assert terrain_line("moon", gap["reason"]) in card["terrain"]["not_testable_on_earth"]


def test_every_number_in_terrain_text_is_in_the_json_files():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    terrain = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
    config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
    for card in cards["cards"]:
        allowed = all_numbers([r for r in card["comparisons"] if r["metric"] in TERRAIN], set())
        allowed |= all_numbers(terrain["sites"].get(card["site"], {}), set())
        allowed |= all_numbers([x for x in terrain["not_assessed"] if x["site"] == card["site"]], set())
        allowed |= all_numbers({"labels": config["labels"], "rules": config["use_rules"],
                                "gravity": config["gravity_m_s2"]}, set())
        cov = terrain["srtm_coverage"]
        allowed |= {abs(cov["north_deg"]), abs(cov["south_deg"])}   # written as 60° N, 56° S
        for line in card["terrain"]["how_engineers_use_it"]:
            for n in re.findall(r"-?\d+(?:\.\d+)?", line):
                assert round(float(n), 6) in allowed, f"{card['site']}: {n} in '{line}' not in JSON"


# --- Empty boxes when nothing on a tab was scored ----------------------------------

def test_no_scored_metric_wording():
    rows = [{"body": "moon", "metric": "slope_deg", "name": "median slope", "unit": "deg", "earth": None,
             "ref": 17.81, "tau": 5.6, "score": None, "label": "not assessed", "note": "outside SRTM coverage"},
            {"body": "mars", "metric": "slope_deg", "name": "median slope", "unit": "deg", "earth": None,
             "ref": None, "tau": None, "score": None, "label": "not assessed", "note": "outside SRTM coverage"}]
    card = build_card("test", rows, GRAVITY)
    expected = ["No scored metric on this tab: outside SRTM coverage; see the other tab"]
    assert card["strong_match"] == expected and card["breaks_down"] == expected


def test_usual_wording_when_something_was_scored():
    rows = [{"body": "moon", "metric": "slope_deg", "name": "median slope", "unit": "deg", "earth": 3.4,
             "ref": 17.81, "tau": 5.6, "gap": 14.41, "score": 0.0, "label": "weak"}]
    card = build_card("test", rows, GRAVITY)
    assert card["strong_match"] == ["None: no metric scored 0.8 or more."]


def test_real_cards_polar_terrain_wording():
    cards = {c["site"]: c for c in json.loads((DATA / "cards.json").read_text(encoding="utf-8"))["cards"]}
    for site, words in (("dryvalleys", "south of 56° S, SRTM's southern limit"),
                        ("haughton", "north of 60° N, SRTM's northern limit")):
        t = cards[site]["terrain"]
        assert t["strong_match"] == t["breaks_down"]
        line = t["strong_match"][0]
        assert line.startswith("No scored metric on this tab: ") and words in line and line.endswith("; see the other tab")


# --- Labels always show their score -------------------------------------------------

from score import label_and_score

# A label word NOT followed by its score, e.g. "weak" instead of "weak (0.07)".
# "needed for partial" is the threshold rule, not a label of a score, so it is allowed.
BARE_LABEL = re.compile(r"\b(strong|partial|weak)\b(?! \(\d\.\d\d\))(?<!needed for partial)")


def test_label_and_score_format():
    assert label_and_score("weak", 0.07) == "weak (0.07)"
    assert label_and_score("partial", 0.5) == "partial (0.50)"
    assert label_and_score("strong", 1.0) == "strong (1.00)"
    assert label_and_score("not assessed", None) == "not assessed"


def test_every_label_on_the_cards_shows_its_score():
    cards = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))
    boxes = ("strong_match", "breaks_down", "not_testable_on_earth", "how_engineers_use_it")
    for card in cards["cards"]:
        scores = {r["score"] for r in card["comparisons"] if r["score"] is not None}
        for part in (card, card["terrain"]):
            for line in (line for b in boxes for line in part[b]):
                assert not BARE_LABEL.search(line), f"label without score: '{line}'"
                # Every "label (score)" shown is a stored score: nothing is re-scored.
                for s in re.findall(r"\b(?:strong|partial|weak) \((\d\.\d\d)\)", line):
                    assert float(s) in scores, f"{s} in '{line}'"
