"""
Tests for progressive disclosure and the satellite map. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

1. Every station opens with one big figure and one plain sentence, worked out from the data.
2. Tables, formulas, worked lines and raw numbers start hidden behind "Show the numbers"
   buttons, which are real buttons, open and close, and say whether they are open.
3. Card boxes show one line each, with "Show details" for the rest, and stay open
   (in memory) when another site is picked.
4. The Sources station is one click away from every station.
5. The map uses NASA GIBS tiles at level 8 or below, with NASA's credit.
"""

import json
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
STATIONS = ["thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]
GIBS = re.compile(r"^https://gibs\.earthdata\.nasa\.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/"
                  r"GoogleMapsCompatible_Level8/(\d+)/(\d+)/(\d+)\.jpeg$")
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def js(x):
    return str(int(x)) if float(x).is_integer() else repr(float(x))


HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const shown = (e) => !!e && e.getClientRects().length > 0;
  const out = { leads: {}, hiddenFirst: {}, buttons: {}, sourcesLink: {}, errors: [] };
  // Things that must wait behind a button, with the station they are in.
  const behind = { thermal: ["#refs", "#chart-note", "#chart2-note", "#card .card-head p"],
    terrain: ["#terrain-refs", "#slope-note", "#rough-note", "#terrain-card .card-head p"],
    tryit: ["#panel-pressure .formula", "#out-pressure .worked", "#pressure-note", "#panel-expansion .formula", "#out-expansion .worked"],
    "gravity-drop": ["#panel-drop .formula", "#out-drop-earth .worked"],
    validation: ["#val-bench", "#val-findings", "#val-single", "#val-sens", "#val-changes"] };
  for (const s of ["thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]) {
    w.location.hash = s; await sleep(300);
    out.leads[s] = { figure: d.getElementById(s + "-figure").textContent, sentence: d.getElementById(s + "-sentence").textContent,
                     visible: shown(d.getElementById(s + "-figure")) };
    out.hiddenFirst[s] = (behind[s] || []).map((sel) => [sel, shown(d.querySelector(sel))]);
    // Every button in the station: a real button, closed at first, opens its target, closes again.
    out.buttons[s] = [];
    for (const b of d.querySelectorAll(`#${s} .reveal-btn`)) {
      if (!shown(b)) continue;
      const target = d.getElementById(b.getAttribute("aria-controls"));
      const before = { expanded: b.getAttribute("aria-expanded"), label: b.querySelector(".reveal-action").textContent };
      b.click();
      const open = { expanded: b.getAttribute("aria-expanded"), label: b.querySelector(".reveal-action").textContent, cls: target.classList.contains("is-open") };
      b.click();
      out.buttons[s].push({ tag: b.tagName, type: b.type, target: !!target, before, open,
        closedAgain: b.getAttribute("aria-expanded") === "false" && !target.classList.contains("is-open") });
    }
    // After opening everything, the hidden things show.
    for (const b of d.querySelectorAll(`#${s} .reveal-btn[aria-expanded="false"]`)) b.click();
    out.hiddenFirst[s] = out.hiddenFirst[s].map(([sel, first]) => [sel, first, shown(d.querySelector(sel))]);
    for (const b of d.querySelectorAll(`#${s} .reveal-btn[aria-expanded="true"]`)) b.click();
    const link = d.querySelector(`#${s} a.tab-sources`);
    out.sourcesLink[s] = { link: !!link && shown(link) && link.getAttribute("href") === "#sources",
                           tab: shown(d.getElementById("tab-sources")) };
  }
  // Cards: one visible line per box; "Show details" shows the rest; it stays open for the next site.
  w.location.hash = "thermal"; await sleep(300);
  const boxLines = () => [...d.querySelectorAll("#card .box, #card .strip")].map((box) =>
    [box.querySelector("h4, strong").textContent, [...box.querySelectorAll("li")].filter(shown).length, box.querySelectorAll("li").length]);
  out.cardBefore = boxLines();
  const how = [...d.querySelectorAll("#card .box")].find((b) => b.querySelector("h4").textContent === "How engineers use it");
  how.querySelector(".reveal-btn").click();
  out.cardOpened = boxLines();
  d.querySelector('#sites button[data-site="atacama"]').click(); await sleep(100);
  out.cardOtherSite = boxLines();
  out.cardSite = d.querySelector("#card h3").textContent;
  // The map: tile addresses and the credit.
  out.tiles = [...d.querySelectorAll("#map img.leaflet-tile")].map((i) => i.src);
  out.credit = (d.querySelector("#map .leaflet-control-attribution") || {}).textContent || "";
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
                               "--virtual-time-budget=20000", "--dump-dom", f"http://127.0.0.1:{port}/h.html"],
                              capture_output=True, text=True, encoding="utf-8", timeout=150).stdout
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
    tmp = tmp_path_factory.mktemp("disclosure")
    return {1280: browse(tmp, 1280), 390: browse(tmp, 390)}


def expected_leads():
    thermal, config, cards, validation = (load(n) for n in ("thermal", "config", "cards", "validation"))
    lunar = config["references"]["moon"]["thermal_swing_K"]["value"]
    swings = {s: t["mean_swing"]["K"] for s, t in thermal["sites"].items() if t["mean_swing"]["K"] is not None}
    best = max(swings, key=swings.get)
    share = f"{100 * swings[best] / lunar:.1f}"
    slopes = [(c["site"], r) for c in cards["cards"] for r in c["comparisons"]
              if r["body"] == "moon" and r["metric"] == "slope_deg" and r["earth"] is not None]
    steep_site, steep = max(slopes, key=lambda p: p[1]["earth"])
    runs = validation["sensitivity"]["runs"]
    changes = max(r["label_changes"] for r in runs)
    compared = runs[0]["labels_compared"]
    # Try it starts at 200 kg on 0.06 m2: Earth 32.7 kPa, Moon 5.4 kPa as shown -> 6.1 times.
    # Gravity Drop starts at 2 m: Moon 1.57 s, Earth 0.64 s as shown -> 2.5 times.
    return {
        "thermal": (f"{share}%", f"Even {SHORT[best]}, the Earth site with the biggest day–night swing, gets only {share}% of the Moon's swing."),
        "terrain": (f"{js(steep['ref'])}°", f"That is the typical (median) slope at Malapert on the Moon; "
                                            f"the steepest Earth site, {SHORT[steep_site]}, has {js(steep['earth'])}°."),
        "tryit": ("6.1×", "On Earth this rover presses 6.1 times harder on the ground than it would on the Moon."),
        "gravity-drop": ("2.5×", "A fall from 2 m takes 2.5 times as long on the Moon as on Earth."),
        # Mission Match opens on its first task, "Climb steep slopes": rank 1 on the existing slope ranking.
        "mission": (SHORT[min(slopes, key=lambda p: p[1]["rank"])[0]], None),
        "validation": (f"{changes} of {compared}", None),
        "sources": (None, "numbers on this page, each with the area and resolution it was measured at and a link to its source."),
    }


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_each_station_leads_with_one_big_figure(pages, width):
    out = pages[width]
    for station, (figure, sentence) in expected_leads().items():
        lead = out["leads"][station]
        assert lead["visible"], station
        if figure is not None:
            assert lead["figure"] == figure, station
        if sentence is not None:
            assert lead["sentence"] == sentence, station
    assert out["leads"]["sources"]["figure"].isdigit()
    assert "score labels" in out["leads"]["validation"]["sentence"]


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_numbers_start_hidden_and_open_with_a_button(pages, width):
    out = pages[width]
    for station, items in out["hiddenFirst"].items():
        for selector, first, after in items:
            assert not first, f"{selector} shows before 'Show the numbers'"
            assert after, f"{selector} does not show after opening"
    total = 0
    for station, buttons in out["buttons"].items():
        for b in buttons:
            total += 1
            assert b["tag"] == "BUTTON" and b["type"] == "button" and b["target"], station
            assert b["before"]["expanded"] == "false" and b["before"]["label"] in ("Show the numbers", "Show details")
            hide = "Hide the numbers" if b["before"]["label"] == "Show the numbers" else "Hide details"
            assert b["open"] == {"expanded": "true", "label": hide, "cls": True}, station
            assert b["closedAgain"], station
    assert total >= 20


@needs_browser
def test_card_boxes_show_one_line_and_remember_details(pages):
    out = pages[1280]
    for title, visible, total in out["cardBefore"]:
        assert visible == min(1, total), title             # one short line per box by default
    opened = {t: (v, n) for t, v, n in out["cardOpened"]}
    assert opened["How engineers use it"][0] == opened["How engineers use it"][1]   # "Show details" shows every line
    assert out["cardSite"] == LONG["atacama"]           # card titles use the long name
    other = {t: (v, n) for t, v, n in out["cardOtherSite"]}
    assert other["How engineers use it"][0] == other["How engineers use it"][1]     # still open for the next site
    assert other["Breaks down"][0] == min(1, other["Breaks down"][1])               # the others stay short


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_sources_one_click_from_every_station(pages, width):
    for station, s in pages[width]["sourcesLink"].items():
        assert s["tab"], station                          # the Sources tab in the station bar
        if station != "sources":
            assert s["link"], station                     # and the "Sources for this station" link


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_phone_and_desktop_do_not_scroll_sideways(pages, width):
    assert pages[width]["scrollWidth"] == width


@needs_browser
def test_map_uses_nasa_gibs_tiles_with_credit(pages):
    out = pages[1280]
    if not out["tiles"]:
        pytest.skip("Leaflet could not load (no internet?)")
    for src in out["tiles"]:
        found = GIBS.match(src)
        assert found, src
        assert int(found.group(1)) <= 8                  # the layer stops at level 8
    assert "NASA GIBS" in out["credit"] and "ESDIS" in out["credit"]
    assert "OpenStreetMap" not in out["credit"]
