"""
Tests for the Mission Match station. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

Every verdict, sentence and honesty line is worked out here again, independently, from
the JSON files, and must match the page exactly:
- the verdict badges follow the existing ranks in cards.json (rank 1, rank 2, otherwise);
- every number in every sentence is one stored in the JSON files (or, for the drop task,
  computed from the stored gravity with the Gravity Drop formulas);
- the team rules are in config.json, each with a reason.
The whole-page journey with its console-error check (tests/test_start_and_hub.py) also
clicks through every Mission Match task.
"""

import json
import math
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, NO_LIVE_TILES, wait_for_server, LONG, SHORT  # noqa: E402

APP = ROOT / "app"
DATA = APP / "data"
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


CONFIG, CARDS, TERRAIN, THERMAL = load("config"), load("cards"), load("terrain"), load("thermal")
MM = CONFIG["mission_match"]


def js(x):
    """A number written the way JavaScript writes it: 300.0 -> "300", 23.58 -> "23.58"."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def label_score(label, score):
    return label if score is None else f"{label} ({score:.2f})"


def row(site, key):
    body, metric = key.split("/")
    card = next(c for c in CARDS["cards"] if c["site"] == site)
    return next(r for r in card["comparisons"] if r["body"] == body and r["metric"] == metric)


def shown(x):
    """The Gravity Drop rounding: 2 decimals."""
    return float(f"{x:.2f}")


# --- The rules in config.json -------------------------------------------------------------

def test_team_rules_are_in_config_with_reasons():
    assert [t["id"] for t in MM["tasks"]] == ["climb", "swing", "cold", "drop"]
    assert [t["ranking"] for t in MM["tasks"]] == ["moon/slope_deg", "moon/thermal_swing_K", "mars/mean_temperature_K", None]
    for t in MM["tasks"]:
        assert t["title"] and t["reason"] and ". " not in t["reason"]   # one sentence
    v = MM["verdicts"]
    assert (v["best_rank"], v["best"], v["partial_rank"], v["partial"], v["otherwise"]) == \
        (1, "Best stand-in on this atlas", 2, "Partial help", "Not useful for this")
    assert v["reason"]
    # Each ranked task reuses a comparison that already has ranks in cards.json.
    for t in MM["tasks"]:
        if t["ranking"]:
            assert any(row(c["site"], t["ranking"]).get("rank") is not None for c in CARDS["cards"])


# --- What the page must show, worked out from the JSON files --------------------------------

def expected_task(task):
    """(lead figure, lead sentence, [(site, verdict, badge, sentence, honesty)]) for one task."""
    v = MM["verdicts"]
    if task["ranking"] is None:
        g = CONFIG["gravity_m_s2"]
        h = task["example_height_m"]
        t_e, t_m = shown(math.sqrt(2 * h / g["earth"]["value"])), shown(math.sqrt(2 * h / g["moon"]["value"]))
        v_m = shown(math.sqrt(2 * g["moon"]["value"] * h))
        h_eq = shown(v_m ** 2 / (2 * g["earth"]["value"]))
        sentence = (f"Same gravity as every Earth site ({js(g['earth']['value'])} m/s²): a {js(h)} m fall takes {js(t_e)} s here "
                    f"but {js(t_m)} s on the Moon; dropping from {js(h_eq)} m matches the Moon's impact speed of {js(v_m)} m/s, "
                    "but not its fall time.")
        honesty = "Honesty check: no Earth site can be scored for this task, because gravity is the same at all of them."
        sites = sorted(THERMAL["sites"], key=lambda s: -1 if THERMAL["sites"][s]["mean_swing"]["K"] is None
                       else THERMAL["sites"][s]["mean_swing"]["K"], reverse=True)   # the swing chart's order
        return (f"0 of {len(sites)}",
                f"Earth sites can rehearse a lunar fall: gravity is {js(g['earth']['value'])} m/s² at every one of them.",
                [(s, "none", v["otherwise"], sentence, honesty) for s in sites], None)

    rows = [(c["site"], row(c["site"], task["ranking"])) for c in CARDS["cards"]]
    # cards.json leaves "rank" out (or null) when a comparison is not assessed.
    ranked = sorted([x for x in rows if x[1].get("rank") is not None], key=lambda x: x[1]["rank"])
    unranked = [x for x in rows if x[1].get("rank") is None]
    best_site, best = ranked[0]
    only = "only " if best["label"] == "weak" else ""
    lead = (SHORT[best_site], f"is this atlas's best stand-in for “{task['title'].lower()}”, and still {only}"
                       f"{label_score(best['label'], best['score'])}.")
    out = []
    for site, r in ranked + unranked:
        if r.get("rank") is None:
            kind, badge = "none", v["otherwise"]
        else:
            kind, badge = {v["best_rank"]: ("best", v["best"]), v["partial_rank"]: ("partial", v["partial"])}.get(
                r["rank"], ("none", v["otherwise"]))
        if r["earth"] is None or r.get("rank") is None:
            gap = next((x for x in TERRAIN["not_assessed"] if x["site"] == site), None)
            sentence = f"Not assessed: {gap['reason'] if gap else 'no ' + r['name'] + ' for this site'}."
        elif task["id"] == "climb":
            p90 = TERRAIN["sites"][site]["areas"]["square_10km"]["slope_deg"]["p90"]
            pct = CONFIG["use_rules"]["slope_climbing_percentile"]
            sentence = (f"Median slope {js(r['earth'])}° vs Malapert's {js(r['ref'])}° (a gap of {js(r['gap'])}°); "
                        f"its steepest {100 - pct}% of ground reaches {js(p90)}°, "
                        f"{'at least as steep as' if p90 >= r['ref'] else 'gentler than'} Malapert's typical slope.")
        elif task["id"] == "swing":
            share = f"{100 * r['earth'] / r['ref']:.1f}"
            sentence = f"Day–night swing {js(r['earth'])} K, {'only ' if float(share) < 100 else ''}{share}% of the Moon's {js(r['ref'])} K."
        else:
            sentence = (f"Mean temperature {js(r['earth'])} K, {js(r['gap'])} K "
                        f"{'warmer' if r['earth'] > r['ref'] else 'colder'} than Mars's {js(r['ref'])} K.")
        honesty = (f"Honesty check: even the best stand-in here, {SHORT[best_site]}, {'is only' if best['label'] == 'weak' else 'scores'} "
                   f"{label_score(best['label'], best['score'])} for this task")
        if site == best_site:
            honesty += "."
        elif r["score"] is None:
            honesty += f"; {SHORT[site]} has no score."
        else:
            honesty += f"; {SHORT[site]} scores {label_score(r['label'], r['score'])}."
        out.append((site, kind, badge, sentence, honesty))
    return (*lead, out, ranked)


# --- The page ---------------------------------------------------------------------------------

HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html#mission" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { header: d.getElementById("mission-question").textContent, tasks: {}, picker: [] };
  for (const b of d.querySelectorAll("#task-picker button")) out.picker.push({ tag: b.tagName, type: b.type,
    title: b.querySelector(".task-title").textContent, icon: !!b.querySelector(".task-icon svg"),
    iconHidden: b.querySelector(".task-icon svg").getAttribute("aria-hidden") });
  for (const b of d.querySelectorAll("#task-picker button")) {
    b.click(); await sleep(50);
    out.tasks[b.dataset.task] = {
      pressed: [...d.querySelectorAll("#task-picker button")].filter((x) => x.getAttribute("aria-pressed") === "true").map((x) => x.dataset.task),
      rule: d.getElementById("task-rule").textContent,
      figure: d.getElementById("mission-figure").textContent, sentence: d.getElementById("mission-sentence").textContent,
      verdicts: [...d.querySelectorAll("#verdicts > li")].map((li) => ({ site: li.dataset.site, kind: li.dataset.verdict,
        title: li.querySelector("h3").textContent,
        badge: li.querySelector(".badge").textContent, sentence: li.querySelector(".verdict-sentence").textContent,
        honesty: li.querySelector(".honesty").textContent,
        numbersHidden: li.querySelector("ul.reveal").getClientRects().length === 0,
        numbers: [...li.querySelectorAll("ul.reveal li")].map((x) => x.textContent),
        button: li.querySelector(".reveal-btn").getAttribute("aria-expanded") })) };
  }
  out.scrollWidth = (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth);
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


def browse(tmp_path, width):
    root = tmp_path / f"site-{width}"
    root.mkdir()
    (root / "app").symlink_to(APP, target_is_directory=True)
    (root / "h.html").write_text(HARNESS.replace("WIDTH", str(width)), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        html = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={root / 'b'}",
                               "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{port}/h.html"],
                              capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    finally:
        server.terminate()
    raw = re.search(r'<pre id="out">(.*?)</pre>', html, re.S).group(1)
    for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        raw = raw.replace(a, b)
    return json.loads(raw)


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("mission")
    return {1280: browse(tmp, 1280), 390: browse(tmp, 390)}


@needs_browser
def test_header_and_task_buttons(pages):
    out = pages[1280]
    assert out["header"] == "What do you want to rehearse?"
    assert [p["title"] for p in out["picker"]] == [t["title"] for t in MM["tasks"]]
    for p in out["picker"]:
        assert p["tag"] == "BUTTON" and p["type"] == "button" and p["icon"] and p["iconHidden"] == "true"


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_every_verdict_matches_the_data(pages, width):
    for task in MM["tasks"]:
        shown_task = pages[width]["tasks"][task["id"]]
        figure, sentence, expected, _ = expected_task(task)
        assert shown_task["pressed"] == [task["id"]]
        assert shown_task["rule"] == f"Team rule for “{task['title']}”: {task['reason']}."
        assert (shown_task["figure"], shown_task["sentence"]) == (figure, sentence)
        got = [(x["site"], x["kind"], x["badge"], x["sentence"], x["honesty"]) for x in shown_task["verdicts"]]
        assert got == expected, task["id"]
        assert [x["title"] for x in shown_task["verdicts"]] == [LONG[x["site"]] for x in shown_task["verdicts"]]


@needs_browser
def test_badges_follow_the_existing_ranks(pages):
    for task in MM["tasks"]:
        if task["ranking"] is None:
            continue
        for x in pages[1280]["tasks"][task["id"]]["verdicts"]:
            rank = row(x["site"], task["ranking"]).get("rank")
            assert x["kind"] == ("best" if rank == 1 else "partial" if rank == 2 else "none"), (task["id"], x["site"])
        # Exactly one best stand-in and one partial help per ranked task (ranks 1 and 2 exist).
        kinds = [x["kind"] for x in pages[1280]["tasks"][task["id"]]["verdicts"]]
        assert kinds.count("best") == 1 and kinds.count("partial") == 1


@needs_browser
def test_every_number_in_a_sentence_is_stored(pages):
    # Allowed numbers: every value stored in cards.json, terrain.json slope statistics and config.json
    # (plus the shares and Gravity Drop values that the page computes from them, checked exactly above).
    stored = set()

    def collect(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            stored.add(round(float(x), 2))
        elif isinstance(x, dict):
            for v in x.values():
                collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)
    for doc in (CARDS, TERRAIN, CONFIG):
        collect(doc)
    for task in MM["tasks"]:
        _, _, expected, _ = expected_task(task)
        computed = set()
        for site, _, _, sentence, _ in expected:
            for n in re.findall(r"\d+(?:\.\d+)?", sentence):
                computed.add(float(n))
        for x in pages[1280]["tasks"][task["id"]]["verdicts"]:
            for n in re.findall(r"\d+(?:\.\d+)?", x["sentence"] + " " + x["honesty"]):
                value = float(n)
                assert round(value, 2) in stored or value in computed, f"{n} in {x['sentence']!r}"


@needs_browser
def test_numbers_hidden_behind_a_button(pages):
    for task in MM["tasks"]:
        for x in pages[1280]["tasks"][task["id"]]["verdicts"]:
            assert x["numbersHidden"] and x["button"] == "false" and x["numbers"]
            if task["ranking"]:
                r = row(x["site"], task["ranking"])
                assert x["numbers"][1].startswith(f"Tolerance (tau) ")
                assert ("not assessed" if r.get("rank") is None else f"rank {r['rank']} of {r['of']}") in x["numbers"][1]


@needs_browser
def test_mission_match_fits_a_phone(pages):
    assert pages[390]["scrollWidth"] == 390
