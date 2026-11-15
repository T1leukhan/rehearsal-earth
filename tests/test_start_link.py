"""
Tests for getting back to the start page. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

1. From the hub and from every station, one click on the title "Rehearsal Earth" or on the
   "Start page" link in the top bar opens the start page, with focus on its title.
   The hub also has a "Back to start page" link.
2. The browser's Back and Forward buttons move correctly between the start page (both the
   bare address and #start), the hub and a station.
3. "Skip intro" and "Begin exploration" never hide the start page: it stays reachable.
4. The whole journey (start, hub, every station, back to the start) gives no console errors.
Every browser run here records console errors, uncaught errors, rejected promises and failed
script loads (see test_start_and_hub.py), and each test checks there were none.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE  # noqa: E402
from test_start_and_hub import CATCH, READ_PAGE, STATIONS, serve_and_dump, site_with  # noqa: E402

APP = ROOT / "app"
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")

HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>""" + READ_PAGE + """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const STATIONS = """ + json.dumps(STATIONS) + """;
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { clicks: {}, history: [], skip: {}, journey: [] };
  const go = async (hash) => { w.location.hash = hash; await sleep(150); };
  const click = async (sel) => { d.querySelector(sel).click(); await sleep(150); };
  // Wait until a fresh load of the page has drawn its view (app.js sets data-view on <body>).
  const loaded = async () => { for (let i = 0; i < 100; i++) { await sleep(100);
    const doc = document.getElementById("f").contentDocument;
    if (doc && doc.body && doc.body.dataset.view && doc.getElementById("station-bar")) return; } };
  const shown = (sel) => { const e = d.querySelector(sel); return !!e && e.getClientRects().length > 0; };
  try {
    // 1. One click back to the start page, from the hub and from every station.
    out.brandName = d.querySelector("#topbar .brand").getAttribute("aria-label");
    for (const v of ["hub", ...STATIONS]) {
      const r = {};
      await go(v);
      r.linksShown = shown("#topbar .brand") && shown("#topbar .start-link") && shown("#topbar .hub-link");
      await click("#topbar .brand");      r.brand = state(d);
      await go(v);
      await click("#topbar .start-link"); r.startLink = state(d);
      if (v === "hub") { await go("hub"); r.backLinkShown = shown("#hub .back-start"); await click("#hub .back-start"); r.backLink = state(d); }
      out.clicks[v] = r;
    }
    // 2. Back and Forward: bare address -> hub -> station, then back and forward again.
    w.location.href = w.location.href.split("#")[0]; await sleep(300); await loaded();   // a fresh visit to the bare address
    const d2 = () => document.getElementById("f").contentDocument;
    const note = (label) => out.history.push([label, state(d2()), w.location.hash]);
    note("bare address");
    d2().querySelector("#start .btn-primary").click(); await sleep(150); note("begin exploration");
    d2().querySelector('#hub a.btn[href="#thermal"]').click(); await sleep(150); note("open thermal");
    w.history.back(); await sleep(150);    note("back 1");
    w.history.back(); await sleep(150);    note("back 2");
    w.history.forward(); await sleep(150); note("forward 1");
    w.history.forward(); await sleep(150); note("forward 2");
    d2().querySelector("#topbar .start-link").click(); await sleep(150); note("start link");
    w.history.back(); await sleep(150);    note("back 3");
    w.history.forward(); await sleep(150); note("forward 3");
    // 3. Skip intro and Begin exploration never hide the start page.
    d2().querySelector("#start .skip-intro").click(); await sleep(150);
    out.skip.afterSkip = state(d2());
    d2().querySelector("#topbar .brand").click(); await sleep(150);
    out.skip.backToStart = state(d2());
    d2().querySelector("#start .btn-primary").click(); await sleep(150);
    w.location.href = w.location.href.split("#")[0]; await sleep(300); await loaded();   // load the bare address again
    out.skip.freshVisit = state(document.getElementById("f").contentDocument);
    // 4. The whole journey: start, hub, every station in turn, then back to the start.
    const d3 = document.getElementById("f").contentDocument;
    d3.querySelector("#start .btn-primary").click(); await sleep(150); out.journey.push(state(d3).views[0]);
    d3.querySelector('#hub a.btn[href="#thermal"]').click(); await sleep(150); out.journey.push(state(d3).views[0]);
    for (let i = 1; i < STATIONS.length; i++) { d3.querySelector(".view:not([hidden]) .journey .next").click(); await sleep(150); out.journey.push(state(d3).views[0]); }
    d3.querySelector("#topbar .brand").click(); await sleep(150); out.journey.push(state(d3).views[0]);
    out.journeyFocus = state(d3).focus;
    out.scrollWidth = (d3.documentElement.scrollWidth + d3.defaultView.innerWidth - d3.documentElement.clientWidth);
  } catch (err) { (w.__errors || (w.__errors = [])).push("harness: " + err.message); }
  // Errors from every page load in this frame (the catcher is re-installed on each load).
  out.errors = (document.getElementById("f").contentWindow.__errors || []).concat(window.__frameErrors || []);
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000), { once: true });   // run the steps once; the frame reloads during them
// Keep errors from earlier page loads too: copy them out before the frame reloads.
document.getElementById("f").addEventListener("load", () => {
  const w = document.getElementById("f").contentWindow;
  w.addEventListener("pagehide", () => { window.__frameErrors = (window.__frameErrors || []).concat(w.__errors || []); });
});
</script>"""


def run(tmp_path, width):
    app_copy = tmp_path / f"app-{width}"
    shutil.copytree(APP, app_copy)
    index = app_copy / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("<head>", "<head>\n" + CATCH, 1), encoding="utf-8")
    root = site_with(app_copy, tmp_path, f"start-link-{width}", HARNESS.replace("WIDTH", str(width)))
    return serve_and_dump(root, "h.html", f"s{width}")


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("startlink")
    return {1280: run(tmp, 1280), 390: run(tmp, 390)}


START = {"views": ["start"], "focus": "start-title"}


def is_start(state):
    return {"views": state["views"], "focus": state["focus"]} == START and state["barHidden"]


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_one_click_back_to_the_start_page(pages, width):
    out = pages[width]
    assert out["brandName"] == "Rehearsal Earth, back to the start page"
    assert set(out["clicks"]) == {"hub", *STATIONS}
    for view, r in out["clicks"].items():
        assert r["linksShown"], view                     # title, "Start page" and "Explore hub" all visible
        assert is_start(r["brand"]), (view, r["brand"])
        assert is_start(r["startLink"]), (view, r["startLink"])
    hub = out["clicks"]["hub"]
    assert hub["backLinkShown"] and is_start(hub["backLink"])


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_back_and_forward_buttons(pages, width):
    got = [(label, s["views"][0], s["focus"], h) for label, s, h in pages[width]["history"]]
    assert got == [
        ("bare address", "start", "BODY", ""),
        ("begin exploration", "hub", "hub-title", "#hub"),
        ("open thermal", "thermal", "thermal-title", "#thermal"),
        ("back 1", "hub", "hub-title", "#hub"),
        ("back 2", "start", "start-title", ""),          # Back reaches the bare address: the start page
        ("forward 1", "hub", "hub-title", "#hub"),
        ("forward 2", "thermal", "thermal-title", "#thermal"),
        ("start link", "start", "start-title", "#start"),
        ("back 3", "thermal", "thermal-title", "#thermal"),
        ("forward 3", "start", "start-title", "#start"),
    ]


@needs_browser
def test_skip_intro_never_hides_the_start_page(pages):
    skip = pages[1280]["skip"]
    assert skip["afterSkip"]["views"] == ["thermal"]
    assert is_start(skip["backToStart"])
    assert skip["freshVisit"]["views"] == ["start"]      # a new visit still opens on the start page


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_whole_journey_and_no_console_errors(pages, width):
    out = pages[width]
    assert out["journey"] == ["hub", *STATIONS, "start"]
    assert out["journeyFocus"] == "start-title"
    assert out["scrollWidth"] == width
    assert out["errors"] == [], out["errors"]
