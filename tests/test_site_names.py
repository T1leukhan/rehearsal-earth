"""
Tests for the display names (app/names.js). Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

The data keeps its keys (for example "atacama"); the page shows names instead.
1. Every site key in the data files has a short and a long display name.
2. No raw key appears in the visible text of any view, with every "Show the numbers",
   "Show details" and collapsed section opened, every Mission Match task tried and
   every site's card opened. Web addresses are the only exception (they are not names).
3. Chart labels, site buttons, card titles and map popups use the names.
"""

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, LONG, SHORT, NO_LIVE_TILES, wait_for_server  # noqa: E402

APP = ROOT / "app"
DATA = APP / "data"
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def all_site_keys():
    """Every site key the data files use."""
    thermal, terrain, cards, validation = (load(n) for n in ("thermal", "terrain", "cards", "validation"))
    keys = set(thermal["sites"]) | set(terrain["sites"]) | {c["site"] for c in cards["cards"]}
    keys |= {x["site"] for x in terrain["not_assessed"]} | {b["site"] for b in validation["benchmarks"]}
    if validation["control"].get("site"):
        keys.add(validation["control"]["site"])
    return keys


def test_every_site_key_has_a_display_name():
    expected_long = {"dryvalleys": "Dry Valleys (Antarctica)", "haughton": "Haughton Crater (Devon Island, Canada)",
                     "altiplano": "Altiplano (Bolivia/Chile)", "maunakea": "Mauna Kea (Hawaii)",
                     "atacama": "Atacama Desert (Chile)"}
    for key in all_site_keys():
        assert key in SHORT and key in LONG, key
        # The short form is the long form without its region in brackets.
        assert LONG[key].startswith(SHORT[key]) and SHORT[key] != key
    for key, long in expected_long.items():
        assert LONG[key] == long and SHORT[key] == long.split(" (")[0]
    assert "amazon" in SHORT                 # the negative-control site, for when its data arrives
    code = (APP / "names.js").read_text(encoding="utf-8")
    assert 'const MOON_TERRAIN_NAME = "Moon: Malapert massif";' in code


def test_data_files_still_use_the_keys():
    # The names live in the page code only: no data file contains them.
    for path in DATA.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for long in LONG.values():
            assert long not in text, (path.name, long)


HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KEYS = new RegExp("\\\\b(" + KEYLIST + ")\\\\b");
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { found: [], seen: 0 };
  const isAddress = (t) => /^(https?:\\/\\/|[\\w.-]+\\.[a-z]+ \\/ )/.test(t.trim());
  // Every text that is drawn on screen, except web addresses.
  const check = (where) => {
    const walker = d.createTreeWalker(d.body, w.NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const el = n.parentElement, t = n.textContent;
      if (!t.trim() || el.closest("script, style") || !el.getClientRects().length) continue;
      const cs = w.getComputedStyle(el);
      if (cs.visibility === "hidden") continue;
      if (isAddress(t) || el.closest("a.short-url")) continue;
      out.seen++;
      const m = t.match(KEYS);
      if (m) out.found.push(where + ": " + m[0] + " in '" + t.trim().slice(0, 80) + "'");
    }
  };
  const openAll = () => {
    for (const x of d.querySelectorAll("details")) x.open = true;
    for (const b of d.querySelectorAll('.reveal-btn[aria-expanded="false"]')) b.click();
  };
  for (const v of ["start", "hub", "thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]) {
    w.location.hash = v; await sleep(250); openAll(); check(v);
  }
  // Every site's card, in Thermal and Terrain.
  for (const station of ["thermal", "terrain"]) {
    w.location.hash = station; await sleep(250);
    for (const b of d.querySelectorAll(`#${station} .sites button`)) { b.click(); await sleep(30); openAll(); check(station + " card " + b.dataset.site); }
  }
  // Every Mission Match task.
  w.location.hash = "mission"; await sleep(250);
  for (const b of d.querySelectorAll("#task-picker button")) { b.click(); await sleep(30); openAll(); check("mission " + b.dataset.task); }
  // Chart labels (drawn on the canvas, so read from the charts).
  out.labels = w.eval("({ swing: chart.data.labels, temperature: chart2.data.labels, slope: slopeChart.data.labels, rough: roughChart.data.labels })");
  out.buttons = [...d.querySelectorAll("#sites button")].map((b) => [b.dataset.site, b.textContent]);
  w.location.hash = "thermal"; await sleep(250);
  d.querySelector('#sites button[data-site="dryvalleys"]').click(); await sleep(30);
  out.cardTitle = d.querySelector("#card h3").textContent;
  out.terrainCardTitle = d.querySelector("#terrain-card h3").textContent;
  // A map popup, if the map library loaded.
  const icon = d.querySelector('#map .site-marker[data-site="maunakea"]');
  if (icon) {
    icon.closest(".leaflet-marker-icon").click(); await sleep(100);
    out.popup = (d.querySelector(".leaflet-popup-content") || {}).textContent || "";
    out.markerTitle = icon.closest(".leaflet-marker-icon").getAttribute("title");
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


def browse(tmp_path, width):
    root = tmp_path / f"site-{width}"
    root.mkdir()
    (root / "app").symlink_to(APP, target_is_directory=True)
    keylist = "|".join(sorted(all_site_keys() | set(SHORT)))
    (root / "h.html").write_text(HARNESS.replace("WIDTH", str(width)).replace("KEYLIST", json.dumps(keylist)),
                                 encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        html = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={root / 'b'}",
                               "--virtual-time-budget=30000", "--dump-dom", f"http://127.0.0.1:{port}/h.html"],
                              capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
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
    tmp = tmp_path_factory.mktemp("names")
    return {1280: browse(tmp, 1280), 390: browse(tmp, 390)}


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_no_raw_key_in_any_visible_text(pages, width):
    out = pages[width]
    assert out["seen"] > 500                       # the check really read the page
    assert out["found"] == [], out["found"][:5]


@needs_browser
def test_charts_buttons_cards_and_popups_use_names(pages):
    out = pages[1280]
    thermal = load("thermal")["sites"]
    assert out["labels"]["swing"][0] == "Moon (reference)"          # the lunar equator reference, not Malapert
    assert set(out["labels"]["swing"][1:]) == {SHORT[k] for k in thermal}
    assert set(out["labels"]["temperature"]) == {SHORT[k] for k in thermal}
    for chart in ("slope", "rough"):
        labels = out["labels"][chart]
        assert labels[0] == "Moon: Malapert massif"
        assert {re.sub(r" \(not assessed\)$", "", x) for x in labels[1:]} == {SHORT[k] for k in thermal}
    assert all(text == SHORT[key] for key, text in out["buttons"])
    assert out["cardTitle"] == LONG["dryvalleys"] and out["terrainCardTitle"] == LONG["dryvalleys"]
    if "popup" not in out:
        pytest.skip("Leaflet could not load (no internet?)")
    assert out["popup"].startswith(SHORT["maunakea"]) and out["markerTitle"] == SHORT["maunakea"]
