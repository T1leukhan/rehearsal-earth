"""
Tests for the page layout: the Sources tab, its filter, the per-tab source counts and
the collapsed sections. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline tests -v   (Windows)
    .venv/bin/python -m pytest pipeline tests -v              (macOS/Linux)

These tests live outside pipeline/ so the pipeline folder is not changed by layout work.
They compare the page with the page as it was before the layout change (commit 99aaf15),
so nothing that was on the old page can go missing.
"""

import json
import re
import socket
import subprocess
import sys
import tarfile
import io
import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, NO_LIVE_TILES, wait_for_server, LONG, SHORT  # noqa: E402  (same browser as the other page tests)

APP = ROOT / "app"
DATA = APP / "data"
OLD_COMMIT = "99aaf15"   # the last commit before the Sources tab
BEFORE_START = "a7210ab" # "Save before start page": the last commit before the start page and hub
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


# --- Expected per-tab counts, worked out from the JSON files ---------------------------------
# One row per number in the Sources table. A row belongs to a tab when that tab shows or uses it:
#   References: the Moon/Mars reference values and gravity.
#   Thermal: temperature references, gravity and beam materials (Try it), thermal tolerances,
#            each site's 4 temperature rows and its scored thermal comparisons.
#   Terrain: terrain references, gravity, terrain tolerances, each site's terrain rows
#            (or its "not assessed" row) and its scored terrain comparisons.
#   Validation: every tolerance used in the sensitivity check, and the benchmark sources.
#   Try it: the Moon's swing, gravity, beam materials and each site's mean swing.
#   Gravity Drop: gravity.

def mission_rankings(config):
    return {t["ranking"] for t in config["mission_match"]["tasks"] if t["ranking"]}


def site_terrain_mission(terrain, thermal):
    return sum(2 if site in terrain["sites"] else 1 for site in thermal["sites"])


def expected_counts():
    config, thermal, terrain, cards, validation = (load(n) for n in ("config", "thermal", "terrain", "cards", "validation"))
    terrain_metrics = {"slope_deg", "roughness_m"}
    bodies = len(config["references"])
    temp_refs = 3                                  # Moon swing, Mars mean temperature, Mars second source
    terrain_refs = 2 * bodies                      # slope and roughness for each body
    gravity = len(config["gravity_m_s2"])
    materials = len(config["materials"])
    taus = {k: v for k, v in cards["tau"].items() if v is not None}
    thermal_taus = sum(k.split("/")[1] not in terrain_metrics for k in taus)
    terrain_taus = len(taus) - thermal_taus
    benchmarks = sum(len(b["sources"]) for b in validation["benchmarks"])
    site_thermal = 4 * len(thermal["sites"])
    site_terrain = 0
    for site in thermal["sites"]:
        t = terrain["sites"].get(site)
        if t is None:
            site_terrain += 1                          # one "not assessed" row
        else:
            site_terrain += 4 + (t["offset_m"]["straight_line"] > 0)   # 4 statistics (+ square centre)
    scored = [r for c in cards["cards"] for r in c["comparisons"] if r["score"] is not None]
    thermal_scores = sum(r["metric"] not in terrain_metrics for r in scored)
    terrain_scores = len(scored) - thermal_scores
    counts = {
        "references": temp_refs + terrain_refs + gravity,
        "thermal": temp_refs + gravity + materials + thermal_taus + site_thermal + thermal_scores,
        "terrain": terrain_refs + gravity + terrain_taus + site_terrain + terrain_scores,
        "validation": len(taus) + benchmarks,
        "tryit": 1 + gravity + materials + len(thermal["sites"]),
        "gravity-drop": gravity,
        # Mission Match: the Moon's swing, the Mars mean temperature, Malapert's median slope,
        # gravity, each site's mean swing and mean temperature, each site's median and 90th
        # percentile slope (or its "not assessed" row), and the scores of the three rankings it reuses.
        "mission": 3 + gravity + 2 * len(thermal["sites"]) + site_terrain_mission(terrain, thermal)
                   + sum(r["score"] is not None and f"{r['body']}/{r['metric']}" in mission_rankings(config)
                         for c in cards["cards"] for r in c["comparisons"]),
    }
    counts["all"] = (temp_refs + terrain_refs + gravity + materials + len(taus) + benchmarks
                     + site_thermal + site_terrain + len(scored))
    return counts


# --- Browser runs -------------------------------------------------------------------------

# Opens the page in a frame and reports: the table rows, the text on the page, the per-tab
# links, what each filter shows, what the link click does, the key caveats and the
# collapsed sections.
HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="APP/index.html" style="width:WIDTHpx;height:1200px;border:0"></iframe><pre id="out"></pre>
<script>
const norm = (s) => s.replace(/\\s+/g, " ").trim();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  // Pages with stations show one view at a time; open a view by its address and wait for it.
  const go = async (name) => { if (d.getElementById("station-bar")) { w.location.hash = name; await sleep(100); } };
  const out = {};
  out.rows = [...d.querySelectorAll("#numbers tbody tr")].map((tr) =>
    // A short Sources link counts as its full URL (kept in its title), so old and new rows compare.
    [...tr.children].map((td) => { const a = td.querySelector("a.short-url");
      return a ? a.title : norm(td.textContent); }).join(" | "));
  out.shortLinks = [...d.querySelectorAll("#numbers a.short-url")].map((a) => ({
    href: a.href, title: a.title, label: a.querySelector("[aria-hidden=true]")?.textContent,
    spoken: a.querySelector(".sr-only")?.textContent,
    srWidth: a.querySelector(".sr-only")?.getBoundingClientRect().width }));
  // Share of the table's width taken by the Source URL column (measured while the table is shown).
  const urlShare = () => d.querySelector("#numbers th:nth-child(5)").getBoundingClientRect().width /
    d.getElementById("numbers").getBoundingClientRect().width;
  out.urlColumnShare = urlShare();
  // Every piece of text on the page, one text node at a time (scripts and styles left out).
  const walker = d.createTreeWalker(d.body, w.NodeFilter.SHOW_TEXT);
  out.texts = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.parentElement.closest("script, style")) continue;
    const t = norm(n.textContent);
    if (t) out.texts.push(t);
  }
  out.bodyText = norm(d.body.textContent);
  const has = (sel) => !!d.querySelector(sel);
  if (has("#source-filter")) {
    out.links = {};
    for (const a of d.querySelectorAll("a.tab-sources")) out.links[a.dataset.filter] = a.textContent;
    out.filters = {};
    for (const b of d.querySelectorAll("#source-filter button")) {
      b.click();
      out.filters[b.dataset.filter] = [...d.querySelectorAll("#numbers tbody tr:not(.group)")].filter((r) => !r.hidden).length;
    }
    out.linkClicks = {};
    for (const a of d.querySelectorAll("a.tab-sources")) {
      await go(a.closest("[role=tabpanel]").id);     // open the station the link is in
      a.click();
      await sleep(100);
      out.linkClicks[a.dataset.filter] = { tab: d.querySelector('[role=tab][aria-selected=true]').id,
        pressed: d.querySelector("#source-filter [aria-pressed=true]").dataset.filter,
        sourcesHidden: d.getElementById("sources").hidden, focus: d.activeElement.id };
    }
    out.urlColumnShare = urlShare();     // the Sources station is open now
    out.sourcesScrollWidth = (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth);
    const tabs = d.querySelector(".tabs");
    out.tabsFit = tabs.scrollWidth <= tabs.clientWidth;   // every tab visible without scrolling the tab bar
    const cell = d.querySelector("#numbers tbody tr:not(.group) td");
    out.cellDisplay = w.getComputedStyle(cell).display;
    out.details = [...d.querySelectorAll("details.more")].map((x) => ({
      open: x.open, summaryFirst: x.firstElementChild.tagName, title: x.querySelector(".more-title").textContent,
      action: x.querySelector(".more-action").textContent, text: norm(x.textContent) }));
    const key = (id) => { const e = d.getElementById(id); return { text: norm(e.textContent), inDetails: !!e.closest("details") }; };
    out.keys = { thermal: key("thermal-key"), terrain: key("terrain-key"),
                 eightDay: [...d.querySelectorAll("#thermal .note.key")].map((e) => ({ text: norm(e.textContent), inDetails: !!e.closest("details") })) };
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3500));
</script>"""


def run(tmp_path, app_dir, width, label):
    root = tmp_path / f"site-{label}"
    root.mkdir()
    (root / "app").symlink_to(app_dir, target_is_directory=True)
    (root / "h.html").write_text(HARNESS.replace("APP", "app").replace("WIDTH", str(width)), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        page = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / ('b-' + label)}",
                               "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{port}/h.html"],
                              capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    finally:
        server.terminate()
    raw = re.search(r'<pre id="out">(.*?)</pre>', page, re.S).group(1)
    for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        raw = raw.replace(a, b)
    return json.loads(raw)


def app_at(commit, tmp_path_factory):
    """The app folder as it was at a commit, unpacked from git."""
    try:
        data = subprocess.run(["git", "-C", str(ROOT), "archive", commit, "app"],
                              capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip(f"git commit {commit} not available")
    folder = tmp_path_factory.mktemp(f"at-{commit}")
    tarfile.open(fileobj=io.BytesIO(data)).extractall(folder, filter="data")
    return folder / "app"


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("pages")
    return {"old": run(tmp, app_at(OLD_COMMIT, tmp_path_factory), 1280, "old"),
            "before_start": run(tmp, app_at(BEFORE_START, tmp_path_factory), 1280, "before_start"),
            "new": run(tmp, APP, 1280, "new"),
            "phone": run(tmp, APP, 390, "phone")}


# Deliberate renames: the per-station source links ("tab" became "station" with the hub),
# and the project name and subtitle (now "Rehearsal Earth").
RENAMES = {
    "Engineering Analog Atlas": "Rehearsal Earth",
    "The Next Frontier: where on Earth can we rehearse the Moon and Mars?":
        "An engineering analog atlas for rehearsing the Moon and Mars on Earth",
    # The map's OpenStreetMap credit was replaced by NASA GIBS's with the satellite imagery.
    "©": "Imagery:", "OpenStreetMap": "NASA GIBS", "contributors": "part of NASA's ESDIS",
}


def with_names(text, names):
    """Write every site key in a text as its display name (names.js): the page now shows names,
    not keys. Web addresses are left exactly as they are (they are not names)."""
    if re.match(r"https?://|[\w.-]+\.[a-z]+ / ", text):   # a full address or a short "host / file" link label
        return text
    return re.sub(r"\b[a-z]+\b", lambda m: names.get(m.group(0), m.group(0)), text)


def named_row(row):
    """An old Sources row as the page writes it now: long names in "Earth site" headings, short names elsewhere."""
    names = LONG if row.startswith("Earth site: ") else SHORT
    return " | ".join(with_names(cell, names) for cell in row.split(" | "))


def renamed(text):
    text = RENAMES.get(text, text)
    return re.sub(r"Sources for this tab: (\d+) numbers, see the Sources tab",
                  r"Sources for this station: \1 numbers, see the Sources station", text)


# --- The tests ----------------------------------------------------------------------------

@needs_browser
def test_every_old_table_row_is_in_the_sources_tab(pages):
    new = Counter(pages["new"]["rows"])
    for before in ("old", "before_start"):
        old = Counter(named_row(r) for r in pages[before]["rows"])
        missing = old - new
        assert not missing, f"rows missing from the Sources station: {list(missing)[:3]}"
        assert old == new                  # and no row was added or changed


@needs_browser
def test_per_tab_counts_match_the_data(pages):
    expected = expected_counts()
    new = pages["new"]
    assert new["filters"] == expected
    for station in ("thermal", "terrain", "tryit", "gravity-drop", "mission", "validation"):
        assert new["links"][station] == f"Sources for this station: {expected[station]} numbers, see the Sources station"


@needs_browser
def test_link_opens_the_sources_tab_with_the_filter(pages):
    for tab, click in pages["new"]["linkClicks"].items():
        # Sources opens with that station's filter, and keyboard focus moves to the table's heading.
        assert click == {"tab": "tab-sources", "pressed": tab, "sourcesHidden": False, "focus": "sources-heading"}


@needs_browser
def test_nothing_on_the_old_page_is_lost(pages):
    # Every piece of text on the page before the Sources tab, and on the page just before
    # the start page and hub, is still somewhere on the new page (possibly inside a
    # collapsed section or in another station).
    new_text = pages["new"]["bodyText"]
    for before in ("old", "before_start"):
        # Site keys are now written as names (short, or long in card titles).
        lost = [t for t in pages[before]["texts"]
                if with_names(renamed(t), SHORT) not in new_text and with_names(renamed(t), LONG) not in new_text]
        assert not lost, f"text from {before} no longer on the page: {lost[:3]}"


@needs_browser
def test_long_notes_are_collapsed_and_reachable(pages):
    details = pages["new"]["details"]
    assert sorted(d["title"] for d in details) == ["About this calculation", "All terrain notes", "LOLA data-quality caveats"]
    for d in details:
        assert d["open"] is False and d["summaryFirst"] == "SUMMARY" and d["action"] == "Show details"
    lola = next(d for d in details if d["title"] == "LOLA data-quality caveats")
    moon_terrain = load("moon_terrain")
    assert moon_terrain["caveats"][0] in lola["text"] and moon_terrain["caveats"][1] in lola["text"]


@needs_browser
def test_key_caveats_stay_visible(pages):
    keys = pages["new"]["keys"]
    config, terrain = load("config"), load("terrain")
    moon = config["references"]["moon"]["thermal_swing_K"]["value"]
    assert keys["thermal"]["text"].startswith(f"Key caveat: the Moon's {moon} K swing is a reference value from NASA slides")
    km = round(terrain["sites"]["altiplano"]["offset_m"]["straight_line"] / 1000, 1)
    cov = terrain["srtm_coverage"]
    assert f"{SHORT['altiplano']} terrain square is {km} km from its thermal point" in keys["terrain"]["text"]
    assert f"SRTM covers {cov['north_deg']:g}° N to {-cov['south_deg']:g}° S" in keys["terrain"]["text"]
    assert any("difference of two 8-day averages" in k["text"] for k in keys["eightDay"])
    assert not keys["thermal"]["inDetails"] and not keys["terrain"]["inDetails"]
    assert not any(k["inDetails"] for k in keys["eightDay"])


@needs_browser
def test_sources_tab_on_a_phone(pages):
    phone = pages["phone"]
    assert phone["sourcesScrollWidth"] == 390          # no sideways scrolling
    assert phone["tabsFit"] and pages["new"]["tabsFit"] # all four tabs visible on phone and desktop
    assert phone["cellDisplay"] == "block"             # rows stacked, as before
    assert phone["filters"] == expected_counts()       # filter works at phone width too


def short_label(url):
    """The label the page should show: host name, " / ", then the last part of the path."""
    from urllib.parse import unquote, urlsplit
    u = urlsplit(url)
    parts = [p for p in u.path.split("/") if p]
    name = (unquote(parts[-1]) if parts else "") + (f"?{u.query}" if u.query else "")
    return f"{u.hostname} / {name}" if name else u.hostname


@needs_browser
def test_sources_links_are_short_with_the_full_url_kept(pages):
    links = pages["new"]["shortLinks"]
    old_urls = [cell for row in pages["old"]["rows"] for cell in row.split(" | ") if cell.startswith("http")]
    assert len(links) == len(old_urls)                      # every URL cell became a short link
    for a, url in zip(links, old_urls):
        assert a["title"] == url and a["spoken"] == url      # full URL on hover and for screen readers
        assert a["href"] == url                              # still links to the full URL
        assert a["label"] == short_label(url)
        assert a["srWidth"] <= 1                             # the full URL is not drawn on screen
    assert "pgda.gsfc.nasa.gov / Site23_final_adj_5mpp_surf.tif" in [a["label"] for a in links]


@needs_browser
def test_url_column_is_wider_on_desktop(pages):
    # The Source URL column takes at least a quarter of the table's width on desktop,
    # more than it did before.
    old, new = pages["old"]["urlColumnShare"], pages["new"]["urlColumnShare"]
    assert new >= 0.25 and new > old, (old, new)
