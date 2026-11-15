"""
Tests for validate.py and the Validation tab. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)
"""

import csv
import html
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import validate as v
from score import load_inputs, scored_rows
from test_formulas import EDGE, SHORT, needs_edge, NO_LIVE_TILES, wait_for_server

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
OUT = json.loads((DATA / "validation.json").read_text(encoding="utf-8"))
CARDS = {c["site"]: c for c in json.loads((DATA / "cards.json").read_text(encoding="utf-8"))["cards"]}
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
THERMAL = json.loads((DATA / "thermal.json").read_text(encoding="utf-8"))

CONFIG, THERMAL_IN, TERRAIN_IN = load_inputs()
EARTH, TAU, ROWS = scored_rows(CONFIG, THERMAL_IN, TERRAIN_IN)


def card_row(site, comparison):
    body, metric = comparison.split("/")
    return next(r for r in CARDS[site]["comparisons"] if r["body"] == body and r["metric"] == metric)


# --- 1. Benchmarks ----------------------------------------------------------------

def test_benchmarks_are_the_four_named_sites_with_listed_sources():
    assert [b["site"] for b in OUT["benchmarks"]] == ["atacama", "haughton", "dryvalleys", "maunakea"]
    for b in OUT["benchmarks"]:
        for src in b["sources"]:
            entry = SOURCES[src["id"]]                      # listed in sources.json
            assert src["url"] == entry["url"] and src["url"].startswith("https://")
            assert src["quote"] == entry["quotes"][b["site"]]


def test_benchmark_ranks_are_the_ranks_on_the_cards():
    for b in OUT["benchmarks"]:
        for comparison, r in b["ranks"].items():
            c = card_row(b["site"], comparison)
            assert (r["rank"], r["of"], r["earth"], r["ref"], r["gap"], r["score"]) == \
                   (c.get("rank"), c.get("of"), c["earth"], c["ref"], c["gap"], c["score"])


def test_near_top_follows_the_rule():
    for b in OUT["benchmarks"]:
        for f in b["findings"]:
            r = b["ranks"][f["comparison"]]
            expected = None if r["rank"] is None else r["rank"] <= OUT["rules"]["near_top_rank"]
            assert f["near_top"] == expected
            if expected is False:
                assert "Not near the top" in f["text"]


def test_every_number_in_findings_comes_from_the_cards():
    for b in OUT["benchmarks"]:
        allowed = set()
        for comparison in b["ranks"]:
            for site in CARDS:
                c = card_row(site, comparison)
                allowed |= {x for x in (c["earth"], c["ref"], c["gap"], c["score"], c.get("rank"), c.get("of")) if x is not None}
        for f in b["findings"]:
            for n in re.findall(r"-?\d+(?:\.\d+)?", f["text"]):
                assert float(n) in allowed, f"{n} in '{f['text']}'"


# --- 2. Negative control ---------------------------------------------------------------

def test_control_is_pending_with_no_numbers():
    rows, files = v.find_control_rows(v.APPEEARS_DIR)
    if rows:
        pytest.skip("an Amazon control is present; the pending case does not apply")
    assert OUT["control"] == {"status": "pending: control request not finished", "files_checked": files}


def test_control_found_is_scored_with_the_same_rules(tmp_path):
    # A fake control: Atacama's own rows renamed "amazon". It must score and rank exactly like Atacama.
    src = v.APPEEARS_DIR / "atlas-thermal-MOD11A2-061-results.csv"
    if not src.exists():
        pytest.skip("AppEEARS file not on this computer")
    with src.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = [dict(r, ID="amazon", Category="control") for r in reader if r["ID"] == "atacama"]
    with (tmp_path / "control.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    out = v.control_check(tmp_path, CONFIG, THERMAL_IN, TERRAIN_IN, ROWS, TAU)
    assert out["status"] == "done" and out["site"] == "amazon"
    assert out["values"]["mean_swing_K"] == THERMAL["sites"]["atacama"]["mean_swing"]["K"]
    for comparison, r in out["comparisons"].items():
        c = card_row("atacama", comparison)
        assert (r["gap"], r["score"], r["rank"]) == (c["gap"], c["score"], c["rank"])
        assert r["of"] == c["of"] + 1          # ranked among the sites plus the control


def test_single_metric_numbers_and_ties():
    s = OUT["single_metric"]
    assert s["pair"] == ["maunakea", "atacama"]
    for comparison, m in s["per_metric"].items():
        a, b = card_row("maunakea", comparison), card_row("atacama", comparison)
        assert m["difference"] == round(abs(a["earth"] - b["earth"]), 2)
        assert m["closer"] == ("maunakea" if a["gap"] < b["gap"] else "atacama" if b["gap"] < a["gap"] else "tie")
    # Ties are found from the data: every reported tie is real, and every real tie is reported.
    found = {(t["comparison"], t["value"], tuple(sorted(t["sites"]))) for t in s["ties"]}
    expected = set()
    for comparison in s["per_metric"]:
        values = {}
        for site in CARDS:
            x = card_row(site, comparison)["earth"]
            if x is not None:
                values.setdefault(x, []).append(site)
        expected |= {(comparison, x, tuple(sorted(sites))) for x, sites in values.items() if len(sites) > 1}
    assert found == expected


# --- 3. Sensitivity --------------------------------------------------------------------

def test_factor_one_changes_nothing(monkeypatch):
    monkeypatch.setattr(v, "FACTORS", [1.0])
    run = v.sensitivity_check(CONFIG, ROWS, TAU)["runs"][0]
    assert run["label_changes"] == 0 and run["max_score_change"] == 0
    assert all(r["score_rank_changes"] == 0 for r in run["rankings"].values())


def test_label_changes_are_counted():
    # One comparison: gap 4.5, tau 10 -> score 0.55 (partial). x0.8 -> 0.4375 (weak); x1.2 -> 0.625 (partial).
    config = {"labels": {"strong": 0.8, "partial": 0.5}}
    rows = {"a": [{"body": "moon", "metric": "slope_deg", "earth": 10.0, "ref": 14.5}],
            "b": [{"body": "moon", "metric": "slope_deg", "earth": 14.5, "ref": 14.5}]}
    out = v.sensitivity_check(config, rows, {("moon", "slope_deg"): 10.0})
    minus, plus = out["runs"]
    assert minus["label_changes"] == 1 and minus["changed"][0] == {
        "site": "a", "comparison": "moon/slope_deg", "from": "partial", "to": "weak",
        "from_score": 0.55, "to_score": 0.44}          # 1 - 4.5/10 and 1 - 4.5/8 = 0.4375
    assert plus["label_changes"] == 0


def test_sensitivity_counts_match_the_file():
    fresh = v.sensitivity_check(CONFIG, ROWS, TAU)
    assert fresh == OUT["sensitivity"]
    for run in OUT["sensitivity"]["runs"]:
        assert all(r["gap_rank_changes"] == 0 for r in run["rankings"].values())


def test_would_change_list_is_not_applied():
    # The suggestions are only text: the tolerances in the file are the ones the cards use.
    cards_tau = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))["tau"]
    assert OUT["tau"] == cards_tau
    assert OUT["would_change_not_applied"]


# --- The Validation tab -------------------------------------------------------------------

@needs_edge
def test_validation_tab(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=ROOT / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        page = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / 'browser'}",
             "--virtual-time-budget=8000", "--dump-dom", f"http://127.0.0.1:{port}/#validation"],
            capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
    finally:
        server.terminate()

    def text(element_id):
        m = re.search(rf'id="{element_id}"[^>]*>(.*?)</(p|table|ul)>', page, re.S)
        assert m, f"#{element_id} not found"
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()

    assert 'id="error" class="error" hidden' in page
    assert not re.search(r'id="validation"[^>]*hidden', page)
    bench = text("val-bench")
    for b in OUT["benchmarks"]:
        assert SHORT[b["site"]] in bench                    # the table shows the site's name
        # Each rank cell shows the label with its score, e.g. "5 of 5 · weak (0.00)".
        for r in b["ranks"].values():
            if r["rank"] is not None:
                assert f"{r['rank']} of {r['of']} · {r['label']} ({r['score']:.2f})" in bench
    if OUT["control"]["status"] != "done":
        control = text("val-control")
        assert control == f"Amazon control: {OUT['control']['status']}."
        assert not re.search(r"\d", control)                     # no numbers while pending
    sens = text("val-sens")
    for run in OUT["sensitivity"]["runs"]:
        assert f"{run['label_changes']} of {run['labels_compared']}" in sens
    assert len(re.findall(r"<li>", page.split('id="val-would"')[1].split("</ul>")[0])) == len(OUT["would_change_not_applied"])


def test_every_label_in_the_findings_shows_its_score():
    bare = re.compile(r"\b(strong|partial|weak)\b(?! \(\d\.\d\d\))(?! match)")
    for b in OUT["benchmarks"]:
        for f in b["findings"]:
            assert not bare.search(f["text"]), f["text"]
            r = b["ranks"][f["comparison"]]
            if r["score"] is not None:
                assert f"{r['label']} ({r['score']:.2f})" in f["text"]
