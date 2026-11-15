"""
Tests for the site map (app/map.js). Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)

The page is opened in the same headless browser as test_formulas.py. Each
marker's element carries data-site, data-lat and data-lon, so the HTML the
browser returns can be checked against the JSON files.

The tests never load live NASA GIBS tiles, so they do not depend on the network or
its timing. Each test serves a copy of the app whose tile address points at a small
local tile server (every tile is the same plain picture). One test makes that server
refuse every tile and checks the "Map tiles could not load" message.
"""

import json
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

import pytest

from test_formulas import EDGE, LONG, needs_edge, wait_for_server

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
DATA = APP / "data"
THERMAL = json.loads((DATA / "thermal.json").read_text(encoding="utf-8"))
TERRAIN = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
CONFIG = json.loads((DATA / "config.json").read_text(encoding="utf-8"))

MARKER = re.compile(r'class="(site-marker|square-marker)[^"]*" data-site="(\w+)" data-kind="(\w+)" '
                    r'data-lat="([-\d.]+)" data-lon="([-\d.]+)"')

# A test page that opens the real page in a frame, clicks a marker and a button,
# and writes what happened into <pre id="out">.
HARNESS = """<!doctype html><meta charset="utf-8">
<iframe id="f" src="app/index.html" style="width:800px;height:900px"></iframe>
<pre id="out"></pre>
<script>
document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const d = document.getElementById("f").contentDocument;
  const out = {};
  const icon = d.querySelector('#map .site-marker[data-site="atacama"]');
  if (!icon) { out.error = "no map"; }
  else {
    icon.closest(".leaflet-marker-icon").click();
    out.card = d.querySelector("#card h3").textContent;
    out.terrainCard = d.querySelector("#terrain-card h3").textContent;
    out.popup = (d.querySelector(".leaflet-popup-content") || {}).textContent || "";
    d.querySelector('#sites button[data-site="dryvalleys"]').click();
    out.selected = [...d.querySelectorAll("#map .selected")].map((m) => m.dataset.site + ":" + m.dataset.kind);
    out.card2 = d.querySelector("#card h3").textContent;
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


# The tile address in map.js, and the local address the test copy uses instead.
GIBS_LINE = re.compile(r'const GIBS_URL = "[^"]+";')
LOCAL_TILES = 'const GIBS_URL = "/tiles/{z}/{y}/{x}.jpeg";'

# A tiny web server for the test folder: /tiles/... answers with one plain picture
# (or "404 not found" when started with "fail"); everything else is a normal file.
TILE_SERVER = """
import http.server, sys
port, mode, tile = int(sys.argv[1]), sys.argv[2], open(sys.argv[3], "rb").read()
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/tiles/"):
            return super().do_GET()
        if mode == "fail":
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(tile)))
        self.end_headers()
        self.wfile.write(tile)
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def plain_png(size=256, rgb=(16, 32, 64)):
    """A one-colour PNG picture, made by hand (no image library needed)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def browse(tmp_path, path, extra_args=(), tiles="ok"):
    """Serve a folder holding a copy of the app (tiles from the local server) and the test pages,
    and return the browser's HTML for path. tiles="fail" makes every tile request fail."""
    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    if not (root / "app").exists():
        shutil.copytree(APP, root / "app")
        map_js = root / "app" / "map.js"
        code, found = GIBS_LINE.subn(LOCAL_TILES, map_js.read_text(encoding="utf-8"))
        assert found == 1, "the GIBS_URL line in map.js was not found"
        map_js.write_text(code, encoding="utf-8")
    (root / "harness.html").write_text(HARNESS, encoding="utf-8")
    (root / "tile.png").write_bytes(plain_png())
    (root / "tile_server.py").write_text(TILE_SERVER, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "tile_server.py", str(port), tiles, "tile.png"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        return subprocess.run(
            [EDGE, "--headless", "--disable-gpu", f"--user-data-dir={tmp_path / 'browser'}", *extra_args,
             "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{port}/{path}"],
            capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
    finally:
        server.terminate()


def markers_or_skip(page):
    """All marker (class, site, kind, lat, lon) found on the page; skip if Leaflet could not load."""
    if "map library could not load" in page:
        pytest.skip("Leaflet could not load (no internet?)")
    return [(c, s, k, float(lat), float(lon)) for c, s, k, lat, lon in MARKER.findall(page)]


# --- No coordinates typed into the page code --------------------------------------

def test_no_hardcoded_coordinates():
    coords = set()
    for t in THERMAL["sites"].values():
        coords |= {t["latitude"], t["longitude"]}
    for s in TERRAIN["sites"].values():
        coords |= set(s["square_centre_lat_lon_deg"])
    for name in ("map.js", "app.js", "index.html"):
        code = (APP / name).read_text(encoding="utf-8")
        literals = {float(n) for n in re.findall(r"(?<![\w.#-])-?\d+(?:\.\d+)?(?![\w.])", code)}
        # Signed values: e.g. -20.5 is a coordinate, a 20 px icon size is not.
        signed = {n for n in literals if n in coords and (n < 0 or not float(n).is_integer())}
        assert not signed, f"{name} contains coordinate-like numbers {signed}"


# --- The map on the page ---------------------------------------------------------

@needs_edge
def test_marker_count_and_coordinates_match_the_json(tmp_path):
    found = markers_or_skip(browse(tmp_path, "app/index.html"))
    thermal = {s: (lat, lon) for c, s, k, lat, lon in found if k == "thermal"}
    squares = {s: (lat, lon) for c, s, k, lat, lon in found if k == "square"}
    # One thermal marker per site, at the thermal.json point.
    assert len([m for m in found if m[2] == "thermal"]) == len(THERMAL["sites"])
    assert thermal == {s: (t["latitude"], t["longitude"]) for s, t in THERMAL["sites"].items()}
    # A square marker wherever the terrain square is not on the thermal point.
    expected = {s: tuple(v["square_centre_lat_lon_deg"]) for s, v in TERRAIN["sites"].items()
                if v["offset_m"]["straight_line"] > 0}
    assert squares == expected == {"altiplano": (-20.5, -68.5)}


@needs_edge
def test_colours_follow_the_bands_in_config(tmp_path):
    page = browse(tmp_path, "app/index.html")
    found = markers_or_skip(page)
    lunar = CONFIG["references"]["moon"]["thermal_swing_K"]["value"]
    bands = CONFIG["map_bands"]["bands"]
    for cls, site, kind, lat, lon in found:
        if kind != "thermal":
            continue
        pct = 100 * THERMAL["sites"][site]["mean_swing"]["K"] / lunar
        band = next(i for i, b in enumerate(bands)
                    if (b["min_percent"] is None or pct >= b["min_percent"])
                    and (b["max_percent"] is None or pct < b["max_percent"]))
        assert re.search(rf'class="site-marker band-{band}[^"]*" data-site="{site}"', page)
    legend = re.search(r'id="map-legend"[^>]*>(.*?)</div>', page, re.S).group(1)
    for b in bands:
        assert b["label"].replace("'", "&#39;") in legend or b["label"] in legend


@needs_edge
def test_line_and_gibs_attribution(tmp_path):
    page = browse(tmp_path, "app/index.html")
    markers_or_skip(page)
    assert len(re.findall(r'class="[^"]*square-link', page)) == 1
    # The base map is NASA GIBS imagery, credited as NASA asks.
    assert 'href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api">NASA GIBS</a>' in page
    assert "part of NASA's ESDIS" in page.replace("&#39;", "'")


@needs_edge
def test_clicking_a_marker_selects_the_site(tmp_path):
    page = browse(tmp_path, "harness.html")
    out = json.loads(re.search(r'<pre id="out">(.*?)</pre>', page, re.S).group(1).replace("&quot;", '"'))
    if out.get("error") == "no map":
        pytest.skip("Leaflet could not load (no internet?)")
    a = THERMAL["sites"]["atacama"]
    assert out["card"] == LONG["atacama"] and out["terrainCard"] == LONG["atacama"]   # card titles use the long name
    assert f"Mean day–night swing: {a['mean_swing']['K']} K" in out["popup"]
    assert f"Mean temperature: {a['mean_temperature']['C']} °C" in out["popup"]
    slope = TERRAIN["sites"]["atacama"]["areas"]["square_10km"]["slope_deg"]["median"]
    assert f"Median terrain slope: {slope} °" in out["popup"]
    # Clicking a site button highlights that site's marker only.
    assert out["card2"] == LONG["dryvalleys"] and out["selected"] == ["dryvalleys:thermal"]


def test_map_js_uses_the_verified_gibs_address():
    # The tests swap the tile address for a local one, so check the real one here.
    code = (APP / "map.js").read_text(encoding="utf-8")
    assert GIBS_LINE.findall(code) == ['const GIBS_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/'
                                       'BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";']
    assert "maxNativeZoom: 8" in code


@needs_edge
def test_tiles_load_from_the_test_server(tmp_path):
    page = browse(tmp_path, "app/index.html")
    markers_or_skip(page)
    loaded = re.findall(r'<img[^>]*class="leaflet-tile leaflet-tile-loaded"[^>]*src="([^"]+)"', page)
    loaded += re.findall(r'<img[^>]*src="([^"]+)"[^>]*class="leaflet-tile leaflet-tile-loaded"', page)
    assert loaded and all(re.search(r"/tiles/\d+/\d+/\d+\.jpeg$", src) for src in loaded)
    assert 'id="map-message" hidden' in page                    # no failure message when tiles load


@needs_edge
def test_page_works_when_tiles_fail(tmp_path):
    page = browse(tmp_path, "app/index.html", tiles="fail")
    markers_or_skip(page)
    assert re.search(r'id="map-message">Map tiles could not load', page)
    assert re.search(r'id="card"[^>]*><article', page) and re.search(r'id="terrain-card"[^>]*><article', page)


@needs_edge
def test_page_works_when_leaflet_fails(tmp_path):
    page = browse(tmp_path, "app/index.html", ["--host-resolver-rules=MAP cdnjs.cloudflare.com ~NOTFOUND"])
    assert re.search(r'id="map-message">The map library could not load', page)
    assert 'id="error" class="error" hidden' in page
    assert re.search(r'id="card"[^>]*><article', page) and re.search(r'id="terrain-card"[^>]*><article', page)


@needs_edge
def test_map_moves_to_the_open_tab(tmp_path):
    page = browse(tmp_path, "app/index.html#terrain")
    markers_or_skip(page)
    slot = re.search(r'<div class="map-slot" data-tab="(\w+)">\s*(?:<!--.*?-->\s*)?<div id="map-box"', page, re.S)
    assert slot and slot.group(1) == "terrain"


# A test page that reads the map's starting view: every marker must be inside the
# map with at least the padding to spare, and the zoom must be the tightest that fits.
FIT_HARNESS = """<!doctype html><meta charset="utf-8">
<iframe id="f" src="app/index.html" style="width:800px;height:900px"></iframe>
<pre id="out"></pre>
<script>
document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = {};
  const map = w.eval("siteMap");
  if (!map) { out.error = "no map"; }
  else {
    const pad = w.eval("MAP_PADDING_PX");
    const bounds = w.eval("markerBounds");
    const box = d.getElementById("map").getBoundingClientRect();
    out.zoom = map.getZoom();
    out.tightest = map.getBoundsZoom(bounds, false, w.L.point(2 * pad, 2 * pad));
    out.pad = pad;
    // Distance from each marker's centre to the nearest map edge, in pixels.
    out.edges = [...d.querySelectorAll("#map .leaflet-marker-icon")].map((m) => {
      const r = m.getBoundingClientRect();
      const x = r.left + r.width / 2 - box.left, y = r.top + r.height / 2 - box.top;
      return Math.min(x, y, box.width - x, box.height - y);
    });
    out.zoomIn = !!d.querySelector("#map .leaflet-control-zoom-in");
    out.zoomOut = !!d.querySelector("#map .leaflet-control-zoom-out");
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


@needs_edge
def test_starting_view_fits_all_markers_with_padding(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "fit.html").write_text(FIT_HARNESS, encoding="utf-8")
    page = browse(tmp_path, "fit.html")
    out = json.loads(re.search(r'<pre id="out">(.*?)</pre>', page, re.S).group(1).replace("&quot;", '"'))
    if out.get("error") == "no map":
        pytest.skip("Leaflet could not load (no internet?)")
    assert out["zoomIn"] and out["zoomOut"]                       # zoom controls kept
    assert len(out["edges"]) == len(THERMAL["sites"]) + 1          # 5 sites + the Altiplano square
    assert min(out["edges"]) >= out["pad"] - 1                     # every marker inside, with padding
    # Tightest fit: the zoom is the largest that still shows every marker
    # (capped at 4), to the nearest quarter step (zoomSnap 0.25).
    assert out["zoom"] == min(out["tightest"], 4)
