"""
Tests for the Terrain tab of the page. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)

The page is opened in the same headless browser as test_formulas.py (Edge,
Chrome or Chromium), with "#terrain" so the Terrain tab is open.
"""

import html
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_formulas import EDGE, LONG, SHORT, needs_edge, NO_LIVE_TILES, wait_for_server

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
TERRAIN = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
MOON = json.loads((DATA / "moon_terrain.json").read_text(encoding="utf-8"))
CARDS = json.loads((DATA / "cards.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    """The page's HTML after it has drawn, opened at #terrain (one browser run for all tests)."""
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=ROOT / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        profile = tmp_path_factory.mktemp("browser")
        return subprocess.run(
            [EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={profile}",
             "--virtual-time-budget=8000", "--dump-dom", f"http://127.0.0.1:{port}/#terrain"],
            capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
    finally:
        server.terminate()


def text_of(page, element_id):
    """Plain text inside the element with this id (up to the end of its section)."""
    found = re.search(rf'id="{element_id}"[^>]*>(.*?)(</section>|<div id="terrain-card")', page, re.S)
    assert found, f"#{element_id} not found"
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", found.group(1)))).strip()


@needs_edge
def test_page_loads_and_terrain_tab_is_open(page):
    assert 'id="error" class="error" hidden' in page
    assert re.search(r'id="thermal"[^>]*hidden', page)
    assert not re.search(r'id="terrain"[^>]*hidden', page)
    assert re.search(r'aria-selected="true"[^>]*id="tab-terrain"', page)


@needs_edge
def test_malapert_reference_and_sources(page):
    refs = text_of(page, "terrain-refs")
    area = MOON["areas"]["whole_site"]
    assert f"{area['slope_deg']['median']} °" in refs
    assert f"{area['roughness_m']['median']} m" in refs
    assert f"median {MOON['original_5m_slope']['median_deg']}°" in refs
    assert "Site23_final_adj_5mpp_surf.tif" in refs and MOON["caveats_source"]["url"] in refs


@needs_edge
def test_two_charts_and_their_notes(page):
    assert 'id="chart-slope"' in page and 'id="chart-rough"' in page
    assert "90th percentile slope" in text_of(page, "slope-note")
    assert "median roughness" in text_of(page, "rough-note")


@needs_edge
def test_notes_say_what_was_asked(page):
    notes = text_of(page, "terrain-notes")
    # The page writes numbers the JavaScript way: 5.0 -> "5".
    assert f"averaged from {MOON['map']['pixel_m']:g} m to {MOON['averaging']['resolution_m']:g} m" in notes
    cov = TERRAIN["srtm_coverage"]
    assert f"between {cov['north_deg']:g}° N and {-cov['south_deg']:g}° S" in notes
    assert SHORT["haughton"] in notes and SHORT["dryvalleys"] in notes and "cannot be assessed" in notes
    km = round(TERRAIN["sites"]["altiplano"]["offset_m"]["straight_line"] / 1000, 1)
    assert f"{SHORT['altiplano']} terrain square is centred {km} km from its thermal point" in notes
    assert "No Mars terrain reference was used" in notes


@needs_edge
def test_terrain_card_uses_the_four_boxes_and_strip(page):
    card = re.search(r'id="terrain-card"[^>]*>(.*?)</article>', page, re.S).group(1)
    for title in ("Strong match", "Breaks down", "Not testable on Earth", "How engineers use it",
                  "What no Earth site can reproduce"):
        assert title in card
    # The first site opened is the first card in the Thermal tab; its terrain text is shown.
    title = re.search(r"<h3>([^<]+)</h3>", card).group(1)
    site = next(k for k, name in LONG.items() if name == title)   # card titles use the long name
    data = next(c for c in CARDS["cards"] if c["site"] == site)["terrain"]
    for line in data["how_engineers_use_it"]:
        assert html.escape(line, quote=False) in card


@needs_edge
def test_site_buttons_for_every_site(page):
    box = page.split('id="terrain-sites"')[1].split("</div>")[0]
    buttons = re.findall(r'data-site="(\w+)"', box)
    assert sorted(buttons) == sorted(c["site"] for c in CARDS["cards"])


@needs_edge
def test_sources_table_scores_show_label_and_score(page):
    table = page.split('id="numbers"')[1]
    shown = re.findall(r"<td[^>]*>Score: [^<]*</td><td[^>]*>([^<]*)</td>", table)
    assert shown, "no Score rows in the sources table"
    for cell in shown:
        assert re.fullmatch(r"(strong|partial|weak) \(\d\.\d\d\)", cell), cell
