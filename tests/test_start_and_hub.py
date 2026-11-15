"""
Tests for the start page, the explore hub and the six stations. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

1. The start page's numbers equal values worked out here from the JSON files.
2. Every section and element of the page before the hub can be reached from the hub.
3. Every deep link (#thermal, #terrain, ...) opens the right view.
4. A click-through of the whole journey, which fails on any console error.
"""

import json
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, NO_LIVE_TILES, wait_for_server, LONG, SHORT  # noqa: E402
from test_page_layout import BEFORE_START, OLD_COMMIT, app_at  # noqa: E402

APP = ROOT / "app"
DATA = APP / "data"
STATIONS = ["thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]
VIEWS = ["start", "hub", *STATIONS]
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def js(x):
    """A number written the way the page's JavaScript writes it: 300.0 -> "300", 23.58 -> "23.58"."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def serve_and_dump(root, page, width_label, flags=()):
    """Serve a folder, open one page in the headless browser and return the JSON it writes into <pre id="out">."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        html = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={root / ('b-' + width_label)}",
                               *flags, "--virtual-time-budget=20000", "--dump-dom", f"http://127.0.0.1:{port}/{page}"],
                              capture_output=True, text=True, encoding="utf-8", timeout=150).stdout
    finally:
        server.terminate()
    found = re.search(r'<pre id="out">(.*?)</pre>', html, re.S)
    assert found, html[:500]
    raw = found.group(1)
    for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        raw = raw.replace(a, b)
    return json.loads(raw)


def site_with(app_dir, tmp, name, harness):
    root = tmp / name
    root.mkdir()
    (root / "app").symlink_to(app_dir, target_is_directory=True)
    (root / "h.html").write_text(harness, encoding="utf-8")
    return root


# --- 1. Start page numbers ----------------------------------------------------------------

def expected_findings():
    """The three findings, worked out from the JSON files."""
    thermal, config, cards, terrain, moon = (load(n) for n in ("thermal", "config", "cards", "terrain", "moon_terrain"))
    lunar = config["references"]["moon"]["thermal_swing_K"]["value"]
    swings = {s: t["mean_swing"]["K"] for s, t in thermal["sites"].items() if t["mean_swing"]["K"] is not None}
    best = max(swings, key=swings.get)
    share = f"{100 * swings[best] / lunar:.1f}"

    slopes = [(c["site"], r) for c in cards["cards"] for r in c["comparisons"]
              if r["body"] == "moon" and r["metric"] == "slope_deg" and r["gap"] is not None]
    site, r = min(slopes, key=lambda x: x[1]["gap"])
    sq = terrain["sites"][site]["areas"]["square_10km"]

    every = [(c["site"], x) for c in cards["cards"] for x in c["comparisons"]]
    scored = [(s, x) for s, x in every if x["score"] is not None]
    weak = sum(x["label"] == "weak" for s, x in scored)
    top_site, top = max(scored, key=lambda p: p[1]["score"])
    compare = "flatter than" if r["earth"] < r["ref"] else "steeper than" if r["earth"] > r["ref"] else "as steep as"
    return [
        {"big": f"{share}%",
         "short": f"The best Earth site reaches only {share}% of the Moon's day–night temperature swing.",
         "text": f"Even the best Earth site, {SHORT[best]}, swings {js(swings[best])} K between day and night: "
                 f"{share}% of the Moon's {js(lunar)} K.",
         "href": "#thermal"},
        {"big": f"{js(r['earth'])}° vs {js(r['ref'])}°",
         "short": f"Even the closest Earth terrain is {compare} the Moon's Malapert massif.",
         "text": f"{SHORT[site]} has the median slope closest to Malapert's: {js(r['earth'])}° against {js(r['ref'])}°, "
                 f"a gap of {js(r['gap'])}°, and still scores {r['label']} ({r['score']:.2f}).",
         "context_has": [f"{sq['size_m_ns_ew'][0] / 1000:.1f} × {sq['size_m_ns_ew'][1] / 1000:.1f} km square",
                         f"{js(moon['averaging']['resolution_m'])} m block means"],
         "href": "#terrain"},
        {"big": f"{weak} of {len(scored)} weak",
         "short": "No Earth site is a strong or partial match on any scored comparison." if weak == len(scored)
                  else f"{weak} of {len(scored)} scored comparisons are weak.",
         "text": ("All" if weak == len(scored) else f"{weak} of") + f" {len(scored)} scored comparisons are weak. "
                 f"The highest score is {top['score']:.2f} ({SHORT[top_site]}, {top['name']} vs {top['body']}); "
                 f"{len(every) - len(scored)} more comparisons are not assessed.",
         "href": "#validation"},
    ]


# What a page looks like: which view shows, what is focused, the findings, the hub links,
# where every id and section heading lives.
READ_PAGE = """
const viewOf = (e) => { const v = e.closest(".view"); if (v) return v.id;
  for (const c of ["station-bar", "map-park", "topbar"]) if (e.closest("#" + c)) return c;
  return e.closest("footer") ? "footer" : "page"; };
const state = (d) => ({
  views: [...d.querySelectorAll(".view")].filter((v) => !v.hidden).map((v) => v.id),
  focus: d.activeElement.id || d.activeElement.tagName,
  tab: (d.querySelector('#station-bar [aria-selected="true"]') || {}).id || null,
  barHidden: d.getElementById("station-bar").hidden,
  title: d.title,
  h1: [...d.querySelectorAll("h1")].filter((h) => h.offsetParent).map((h) => h.textContent),
});
"""

HUB_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:1280px;height:1000px;border:0"></iframe><pre id="out"></pre>
<script>""" + READ_PAGE + """
document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = {};
  out.ids = [...d.querySelectorAll("[id]")].map((e) => e.id);
  out.headings = [...d.querySelectorAll("main section > h2")].map((h) => h.textContent.trim());
  if (d.getElementById("hub")) {
    out.state = state(d);
    out.where = {};
    for (const e of d.querySelectorAll("[id]")) out.where[e.id] = viewOf(e);
    out.titles = {};
    for (const h of d.querySelectorAll(".view h1, .view section > h2")) out.titles[h.textContent.trim()] = viewOf(h);
    out.hubLinks = [...d.querySelectorAll("#hub .station-card a.btn")].map((a) => a.getAttribute("href"));
    out.cards = [...d.querySelectorAll("#hub .station-card")].map((c) => ({ name: c.querySelector("h2").textContent,
      icon: !!c.querySelector("svg.icon[aria-hidden=true]"), desc: c.querySelector("p").textContent,
      open: c.querySelector("a.btn").textContent, label: c.querySelector("a.btn").getAttribute("aria-labelledby") }));
    out.findings = [...d.querySelectorAll("#findings .finding")].map((f) => ({ big: f.querySelector(".big").textContent,
      short: f.querySelector(".short").textContent, text: f.querySelector(".detail").textContent,
      context: f.querySelector(".note").textContent, href: f.querySelector("a.proof").getAttribute("href"),
      shortVisible: f.querySelector(".short").getClientRects().length > 0,
      detailVisible: f.querySelector(".detail").getClientRects().length > 0 }));
    out.start = { title: d.getElementById("start-title").textContent, question: d.querySelector("#start .question").textContent,
      begin: d.querySelector("#start .btn-primary").getAttribute("href"), skip: d.querySelector("#start .skip-intro").getAttribute("href"),
      hint: d.querySelector("#start .hint").textContent, footer: d.querySelector("footer .disclaimer").textContent };
    out.mapSlots = [...d.querySelectorAll(".map-slot")].map((m) => viewOf(m));
    out.siteButtons = [...d.querySelectorAll(".sites")].map((m) => viewOf(m));
    out.keys = {};
    for (const id of ["thermal-key", "terrain-key", "drop-caveat", "val-rules"]) {
      const e = d.getElementById(id);
      out.keys[id] = { view: viewOf(e), inDetails: !!e.closest("details"), text: e.textContent };
    }
    out.eightDay = [...d.querySelectorAll(".note.key")].filter((e) => e.textContent.includes("8-day")).map((e) => viewOf(e));
    out.journey = {};
    for (const s of d.querySelectorAll(".station")) out.journey[s.id] = {
      back: !!s.querySelector('.station-head a.back[href="#hub"]'), lead: s.querySelector(".station-head .lead").textContent,
      next: (s.querySelector(".journey .next") || {}).textContent, nextHref: (s.querySelector(".journey .next") || { getAttribute: () => null }).getAttribute("href") };
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


@pytest.fixture(scope="module")
def hub_pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("hub")
    pages = {}
    for label, app_dir in (("new", APP), ("old", app_at(OLD_COMMIT, tmp_path_factory)),
                           ("before_start", app_at(BEFORE_START, tmp_path_factory))):
        pages[label] = serve_and_dump(site_with(app_dir, tmp, label, HUB_HARNESS), "h.html", label)
    return pages


@needs_browser
def test_start_page_numbers_come_from_the_data(hub_pages):
    shown = hub_pages["new"]["findings"]
    expected = expected_findings()
    assert len(shown) == 3
    for s, e in zip(shown, expected):
        assert s["big"] == e["big"] and s["short"] == e["short"] and s["href"] == e["href"]
        assert s["text"] == e["text"]                      # the longer sentence is kept, behind "Show the numbers"
        assert s["shortVisible"] and not s["detailVisible"]
        for part in e.get("context_has", []):
            assert part in s["context"]


@needs_browser
def test_start_page_wording_and_buttons(hub_pages):
    start = hub_pages["new"]["start"]
    assert start["title"] == "Rehearsal Earth"
    assert start["question"] == "Where on Earth can we rehearse the Moon and Mars, and how far can we trust it?"
    assert start["begin"] == "#hub" and start["skip"] == "#thermal"
    assert start["hint"].startswith("How to explore:")
    assert start["footer"] == "Made for NASA Space Apps Challenge 2026 - not affiliated with or endorsed by NASA"
    # The page opens on the start page, with no station bar.
    assert hub_pages["new"]["state"]["views"] == ["start"] and hub_pages["new"]["state"]["barHidden"]


@needs_browser
def test_hub_has_seven_stations_with_icons(hub_pages):
    new = hub_pages["new"]
    assert new["hubLinks"] == [f"#{s}" for s in STATIONS]
    assert [c["name"] for c in new["cards"]] == ["Thermal", "Terrain", "Try it", "Gravity Drop", "Mission Match", "Validation", "Sources"]
    for c, s in zip(new["cards"], STATIONS):
        assert c["icon"] and c["desc"] and c["open"] == "Open" and c["label"] == f"open-{s} hub-{s}"


@needs_browser
def test_every_old_section_is_reachable_from_the_hub(hub_pages):
    new = hub_pages["new"]
    reachable = {h.lstrip("#") for h in new["hubLinks"]} | {"start", "hub"}
    # Every element id of the earlier pages is still on the page, inside a station the hub links to
    # (or in the station bar, the footer, the map's parking place or the error line).
    for before in ("old", "before_start"):
        for element_id in hub_pages[before]["ids"]:
            assert element_id in new["where"], f"#{element_id} from {before} is gone"
            assert new["where"][element_id] in reachable | {"station-bar", "map-park", "footer", "page"}, element_id
        # Every section heading is in a station the hub links to (a station title may add a subtitle).
        for heading in hub_pages[before]["headings"]:
            homes = {v for t, v in new["titles"].items() if t == heading or t.startswith(heading + ":")}
            assert homes & set(STATIONS), f"section '{heading}' from {before} is not in a station"
    # The map waits in its parking place; its slots and the site buttons are inside stations.
    assert new["where"]["map-box"] == "map-park"
    assert sorted(new["mapSlots"]) == ["terrain", "thermal"]
    assert sorted(new["siteButtons"]) == ["terrain", "thermal", "tryit"]


@needs_browser
def test_each_station_has_back_next_and_its_key_caveats(hub_pages):
    new = hub_pages["new"]
    for i, s in enumerate(STATIONS):
        j = new["journey"][s]
        assert j["back"] and j["lead"].startswith("What you will see here:")
        if i + 1 < len(STATIONS):
            assert j["nextHref"] == f"#{STATIONS[i + 1]}" and j["next"].startswith("Next station:")
        else:
            assert j["nextHref"] == "#hub"
    keys = new["keys"]
    assert {k: (v["view"], v["inDetails"]) for k, v in keys.items()} == {
        "thermal-key": ("thermal", False), "terrain-key": ("terrain", False),
        "drop-caveat": ("gravity-drop", False), "val-rules": ("validation", False)}
    assert new["eightDay"] == ["thermal"]


# --- 3. Deep links -------------------------------------------------------------------------

DEEP_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0"><div id="frames"></div><pre id="out"></pre>
<script>""" + READ_PAGE + """
const names = NAMES, out = {};
for (const name of names) {
  const f = document.createElement("iframe");
  f.style.cssText = "width:1000px;height:700px;border:0";
  f.src = "app/index.html#" + name;
  f.addEventListener("load", () => setTimeout(() => {
    out[name] = state(f.contentDocument);
    if (Object.keys(out).length === names.length) document.getElementById("out").textContent = JSON.stringify(out);
  }, 3000));
  document.getElementById("frames").append(f);
}
</script>"""


@needs_browser
def test_every_deep_link_opens_its_view(tmp_path):
    names = VIEWS + ["no-such-view"]
    root = site_with(APP, tmp_path, "deep", DEEP_HARNESS.replace("NAMES", json.dumps(names)))
    out = serve_and_dump(root, "h.html", "deep")
    for name in VIEWS:
        assert out[name]["views"] == [name], name
        if name in STATIONS:
            assert out[name]["tab"] == f"tab-{name}" and not out[name]["barHidden"]
            assert out[name]["title"].endswith("· Rehearsal Earth")
        else:
            assert out[name]["tab"] is None and out[name]["barHidden"]
        assert len(out[name]["h1"]) == 1          # exactly one visible main heading per view
    assert out["no-such-view"]["views"] == ["start"]   # an unknown address falls back to the start page


# --- 4. The whole journey, failing on any console error ------------------------------------

# Put first in <head>: records console errors, uncaught errors, rejected promises and
# failed loads of the page's own scripts and stylesheets.
CATCH = """<script>
window.__errors = [];
const __consoleError = console.error;
console.error = (...a) => { window.__errors.push("console.error: " + a.join(" ")); __consoleError(...a); };
addEventListener("error", (e) => {
  if (e instanceof ErrorEvent) window.__errors.push("error: " + e.message);
  else if (e.target && /^(SCRIPT|LINK)$/.test(e.target.tagName)) window.__errors.push("failed to load: " + (e.target.src || e.target.href));
}, true);
addEventListener("unhandledrejection", (e) => window.__errors.push("rejection: " + e.reason));
</script>"""

JOURNEY_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>""" + READ_PAGE + """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const steps = [], cols = {};
  const columns = (sel) => w.getComputedStyle(d.querySelector(sel)).gridTemplateColumns.split(" ").length;
  const note = (label) => steps.push([label, state(d)]);
  const click = async (sel) => { d.querySelector(sel).click(); await sleep(150); };
  try {
    note("load");                                           cols.findings = columns("#findings");
    await click("#start .btn-primary");                     note("begin"); cols.hub = columns("#hub .hub-grid");
    await click('#hub a.btn[href="#thermal"]');             note("open thermal");
    await click('#sites button[data-site="atacama"]');
    for (const s of ["terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]) {
      await click(".view:not([hidden]) .journey .next");    note("next " + s);
      if (s === "terrain") { await click('#terrain-sites button[data-site="maunakea"]'); d.querySelector("#terrain details.more summary").click(); }
      if (s === "tryit") { const m = d.getElementById("in-mass"); m.value = "300"; m.dispatchEvent(new w.Event("input")); await click('#tryit-sites button[data-site="dryvalleys"]'); }
      if (s === "gravity-drop") { await click("#drop-button"); await sleep(2500); }
      if (s === "mission") {   // try every task and open one verdict's numbers
        for (const b of d.querySelectorAll("#task-picker button")) { b.click(); await sleep(50); }
        await click("#verdicts .reveal-btn");
      }
      if (s === "sources") { for (const b of d.querySelectorAll("#source-filter button")) b.click(); }
    }
    await click("#sources .journey .next");                 note("finish");
    w.history.back(); await sleep(150);                     note("back");
    w.history.forward(); await sleep(150);                  note("forward");
    await click('#hub a.btn[href="#validation"]');
    const tab = d.getElementById("tab-validation");
    tab.focus();
    tab.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })); await sleep(150);
                                                            note("arrow right");
    await click('#tab-thermal');                            note("tab thermal");
    await click('#thermal a.tab-sources');                  note("sources link");
    await click('#topbar .brand');                          note("brand");
    await click('#start .skip-intro');                      note("skip intro");
  } catch (err) { w.__errors.push("harness: " + err.message); }
  // After every station has been opened, look for any visited mark anywhere on the page:
  // an id or class mentioning "visit", the word "visited", a tick character, or a tick
  // drawn by CSS before or after any element (for example on the station tabs).
  const marks = [];
  for (const e of d.querySelectorAll("*")) {
    if (/visit/i.test(e.id + " " + e.getAttribute("class"))) marks.push("attribute on " + (e.id || e.tagName));
    for (const pseudo of ["::before", "::after"]) {
      const c = w.getComputedStyle(e, pseudo).content;
      if (/✓|✔|visit/i.test(c)) marks.push(pseudo + " on " + (e.id || e.tagName));
    }
  }
  if (/visited|✓|✔/i.test(d.body.textContent)) marks.push("text: " + d.body.textContent.match(/.{0,30}(visited|✓|✔).{0,30}/i)[0]);
  const out = { steps, cols, errors: w.__errors, marks,
    filter: d.querySelector("#source-filter [aria-pressed=true]").dataset.filter,
    scrollWidth: (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth) };
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


def journey(tmp_path, width, flags=()):
    app_copy = tmp_path / f"app-{width}"
    shutil.copytree(APP, app_copy)
    index = app_copy / "index.html"
    html = index.read_text(encoding="utf-8")
    index.write_text(html.replace("<head>", "<head>\n" + CATCH, 1), encoding="utf-8")
    root = site_with(app_copy, tmp_path, f"journey-{width}", JOURNEY_HARNESS.replace("WIDTH", str(width)))
    return serve_and_dump(root, "h.html", f"j{width}", flags)


EXPECTED_JOURNEY = [
    # step, the view shown, where keyboard focus is
    ("load", "start", "BODY"),
    ("begin", "hub", "hub-title"),
    ("open thermal", "thermal", "thermal-title"),
    ("next terrain", "terrain", "terrain-title"),
    ("next tryit", "tryit", "tryit-title"),
    ("next gravity-drop", "gravity-drop", "gravity-drop-title"),
    ("next mission", "mission", "mission-title"),
    ("next validation", "validation", "validation-title"),
    ("next sources", "sources", "sources-title"),
    ("finish", "hub", "hub-title"),
    ("back", "sources", "sources-title"),
    ("forward", "hub", "hub-title"),
    ("arrow right", "sources", "tab-sources"),        # arrow keys keep focus on the tabs
    ("tab thermal", "thermal", "thermal-title"),
    ("sources link", "sources", "sources-heading"),
    ("brand", "start", "start-title"),
    ("skip intro", "thermal", "thermal-title"),
]


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_whole_journey_without_console_errors(tmp_path, width):
    out = journey(tmp_path, width)
    assert out["errors"] == [], out["errors"]
    got = [(label, s["views"], s["focus"]) for label, s in out["steps"]]
    assert got == [(label, [view], focus) for label, view, focus in EXPECTED_JOURNEY]
    assert out["marks"] == [], out["marks"]                   # no visited label, counter or tick anywhere
    assert out["filter"] == "thermal"                        # the Thermal sources link set the filter
    assert out["scrollWidth"] == width                       # nothing scrolls sideways
    # Findings and hub cards: three across on desktop, stacked in one column on a phone.
    assert out["cols"] == ({"findings": 3, "hub": 3} if width > 600 else {"findings": 1, "hub": 1})


@needs_browser
def test_journey_under_reduced_motion(tmp_path):
    out = journey(tmp_path, 1280, ["--force-prefers-reduced-motion"])
    assert out["errors"] == []
    assert [s["views"][0] for _, s in out["steps"]] == [view for _, view, _ in EXPECTED_JOURNEY]
