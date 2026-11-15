"""
Tests for the page's look (the Rehearsal Earth theme). Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline tests -v   (Windows)
    .venv/bin/python -m pytest pipeline tests -v              (macOS/Linux)

Checks: the project name everywhere it is shown; text contrast of at least 4.5:1
(measured in the browser on every view, at desktop and phone width, and for every
colour pair in style.css, including the six station colours); chart colours readable
on their panels; each station's colour on its hub card, tab, title and charts; the
animations switched off under prefers-reduced-motion; no image files or web fonts;
and no sideways scrolling on a 390 px phone.
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
from test_formulas import EDGE, needs_edge, NO_LIVE_TILES, wait_for_server  # noqa: E402

APP = ROOT / "app"
CSS = (APP / "style.css").read_text(encoding="utf-8")
HTML = (APP / "index.html").read_text(encoding="utf-8")
MIN_CONTRAST = 4.5


# --- Colour maths (WCAG 2) ------------------------------------------------------------

def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def css_var(name):
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", CSS).group(1)


# --- style.css on its own --------------------------------------------------------------

def test_every_text_colour_on_every_background():
    # Includes text the browser check cannot see: chart labels drawn on the canvas
    # (--text and --muted on --panel) and the column names shown before table cells on phones.
    texts = ["text", "muted", "heading", "accent", "link", "moon", "strong", "weak", *STATION_COLOURS.values()]
    backgrounds = ["bg-0", "bg-1", "bg-2", "panel", "panel-2", "input"]
    for t in texts:
        for b in backgrounds:
            assert contrast(css_var(t), css_var(b)) >= MIN_CONTRAST, f"--{t} on --{b}"
    assert contrast(css_var("strip-text"), css_var("strip-bg")) >= MIN_CONTRAST
    assert contrast("#04122b", css_var("accent")) >= MIN_CONTRAST          # pressed site button
    for colour in STATION_COLOURS.values():                                 # buttons filled with a station colour
        assert contrast("#04122b", css_var(colour)) >= MIN_CONTRAST, colour
    assert contrast("#1f2937", "#ffffff") >= MIN_CONTRAST and contrast("#0b4f8a", "#ffffff") >= MIN_CONTRAST  # map attribution


def test_no_image_files_or_web_fonts():
    assert "url(" not in CSS and "@import" not in CSS and "@font-face" not in CSS
    assert not re.search(r"<img|<picture|<image|href=\"[^\"]+\.(png|jpe?g|gif|webp)", HTML, re.I)   # icons are inline SVG
    sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)"', HTML)
    assert sheets == ["style.css", "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"]
    assert "fonts.googleapis" not in HTML


def test_animations_are_gentle_and_switched_off_for_reduced_motion():
    code = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)          # ignore comments
    animations = [a.strip() for a in re.findall(r"animation:\s*([^;]+);", code)]
    running = [a for a in animations if a != "none"]
    # The star layers drift very slowly (looping, transform only); the rover illustration in Try it
    # sways very slowly; a view fades in once, briefly.
    assert running == ["drift-far 240s linear infinite", "drift-near 160s linear infinite",
                       "drift-bright 600s linear infinite", "rover-sway 14s ease-in-out infinite alternate",
                       "view-in 0.25s ease-out 1"]
    # Moving transitions only inside the rover illustration (turning it, and its sizes changing).
    for selector in re.findall(r"([^{}]+)\{[^{}]*transition: transform", code):
        assert all(part.strip().startswith((".rover", ".rv-", ".scene-svg")) for part in selector.split(",")), selector
    reduced = " ".join(re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", code, re.S))
    assert re.search(r"\.stars \{ animation: none; \}", reduced)
    assert ".rover-sway { animation: none; }" in reduced and ".scene-svg * { transition: none; }" in reduced
    assert re.search(r"\.view:not\(\[hidden\]\) \{ animation: none; \}", code)


NAME = "Rehearsal Earth"
SUBTITLE = "An engineering analog atlas for rehearsing the Moon and Mars on Earth"
STATION_COLOURS = {"thermal": "c-thermal", "terrain": "c-terrain", "tryit": "c-tryit",
                   "gravity-drop": "c-drop", "mission": "c-mission", "validation": "c-validation", "sources": "c-sources"}


def test_new_name_everywhere_it_is_shown():
    assert f"<title>{NAME}</title>" in HTML
    assert re.search(rf"<h1[^>]*>{NAME}</h1>", HTML)                                  # hero
    assert f'<p class="subtitle">{SUBTITLE}</p>' in HTML
    assert f'<a class="brand" href="#start" aria-label="{NAME}, back to the start page">{NAME}</a>' in HTML   # top bar
    footer = HTML.split("<footer>")[1]
    assert NAME in footer and "Made for NASA Space Apps Challenge 2026 - not affiliated with or endorsed by NASA" in footer
    assert "Where on Earth can we rehearse the Moon and Mars, and how far can we trust it?" in HTML   # question kept
    readme = (ROOT / "notes" / "README.md").read_text(encoding="utf-8")
    assert readme.splitlines()[0] == f"# {NAME}: notes" and SUBTITLE in readme
    # The old name is not shown anywhere on the page any more.
    for name in ("index.html", "app.js", "map.js", "explain.js", "formulas.js"):
        assert "Engineering Analog Atlas" not in (APP / name).read_text(encoding="utf-8"), name
    assert 'id="numbers"' in HTML                             # the sources table is kept


def test_hero_is_centred_and_calm():
    hero = re.search(r"\.hero \{([^}]*)\}", CSS).group(1)
    title = re.search(r"\.hero h1 \{([^}]*)\}", CSS).group(1)
    assert "text-align: center" in hero
    assert "font-weight: 400" in title and "letter-spacing: 0.06em" in title and "uppercase" in title
    # No hero paragraph pins itself to the left: each is centred with auto side margins.
    for rule in re.findall(r"\.hero (?:\.\w+|> p) \{([^}]*)\}", CSS):
        m = re.search(r"margin: ([^;]+);", rule)
        if m:
            assert "auto" in m.group(1), rule


def test_chart_colours_readable_on_their_panels():
    # Bars and lines are graphics: at least 3:1 against the chart panel (WCAG 1.4.11).
    for colour in ("c-thermal", "c-terrain", "moon"):
        assert contrast(css_var(colour), css_var("panel")) >= 3, colour
    # The station bars must also look different from the orange Moon/Mars reference bar.
    for colour in ("c-thermal", "c-terrain"):
        assert css_var(colour).lower() != css_var("moon").lower()


# --- In the browser -------------------------------------------------------------------------

# A test page that opens the real page in a frame of a given width and, on each tab,
# measures the contrast of every visible piece of text against what is behind it.
HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:1200px;border:0"></iframe><pre id="out"></pre>
<script>
const parse = (c) => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
  const p = m[1].split(",").map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
const lum = (c) => { const l = c.slice(0, 3).map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]; };
const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const root = w.getComputedStyle(d.documentElement);
  const bases = ["--bg-0", "--bg-1", "--bg-2"].map((v) => { const h = root.getPropertyValue(v).trim();
    return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(1); });
  const out = { width: d.defaultView.innerWidth, scrollWidth: {}, worst: [] };
  for (const x of d.querySelectorAll("details")) x.open = true;   // check the collapsed text too
  const openAll = () => { for (const b of d.querySelectorAll('.reveal-btn[aria-expanded="false"]')) b.click(); };
  openAll();                                                       // and everything behind "Show the numbers"
  for (const tab of ["start", "hub", "thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]) {
    w.location.hash = tab;
    await new Promise((r) => setTimeout(r, 400));   // wait for the view and its fade-in
    openAll();
    out.scrollWidth[tab] = (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth);
    for (const e of d.body.querySelectorAll("*")) {
      const own = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      const isInput = e.matches("input, select");
      if ((!own && !isInput) || !e.getClientRects().length) continue;
      const cs = w.getComputedStyle(e);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      // Background layers from this element up to the page, then the page's navy.
      const layers = [];
      for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
        const bg = parse(w.getComputedStyle(n).backgroundColor);
        if (bg && bg[3] > 0) { layers.push(bg); if (bg[3] === 1) break; }
      }
      for (const base of bases) {
        let bg = base;
        for (const layer of layers.slice().reverse()) bg = over(layer, bg);
        const fg = over(parse(cs.color), bg);
        const r = ratio(fg, bg);
        if (r < 4.5) out.worst.push({ tab, tag: e.tagName, id: e.id, cls: String(e.className).slice(0, 40),
          text: (e.textContent || e.value || "").trim().slice(0, 40), ratio: Math.round(r * 100) / 100 });
      }
    }
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


def browse(tmp_path, width, extra_args=()):
    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    if not (root / "app").exists():
        (root / "app").symlink_to(APP, target_is_directory=True)
    (root / "check.html").write_text(HARNESS.replace("WIDTH", str(width)), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        return subprocess.run(
            [EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / 'browser'}", *extra_args,
             "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{port}/check.html"],
            capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    finally:
        server.terminate()


def result(page):
    return json.loads(re.search(r'<pre id="out">(.*?)</pre>', page, re.S).group(1).replace("&quot;", '"').replace("&amp;", "&"))


@needs_edge
@pytest.mark.parametrize("width", [1280, 390])
def test_text_contrast_on_every_tab(tmp_path, width):
    out = result(browse(tmp_path, width))
    assert out["width"] == width
    assert out["worst"] == [], f"text below {MIN_CONTRAST}:1: {out['worst'][:5]}"


@needs_edge
def test_no_sideways_scrolling_on_a_phone(tmp_path):
    out = result(browse(tmp_path, 390))
    assert out["scrollWidth"] == {v: 390 for v in ["start", "hub", "thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]}


@needs_edge
def test_animation_off_under_reduced_motion(tmp_path):
    probe = """<!doctype html><meta charset="utf-8"><iframe id="f" src="app/index.html"></iframe><pre id="out"></pre>
<script>document.getElementById("f").addEventListener("load",()=>setTimeout(()=>{const w=document.getElementById("f").contentWindow;
const d=w.document;document.getElementById("out").textContent=[...d.querySelectorAll(".stars")].map((e)=>w.getComputedStyle(e).animationName).join(" ")+" "+w.getComputedStyle(d.getElementById("start")).animationName;},1000));</script>"""
    root = tmp_path / "site"
    root.mkdir()
    (root / "app").symlink_to(APP, target_is_directory=True)
    (root / "probe.html").write_text(probe, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        names = {}
        for label, flags in (("normal", []), ("reduced", ["--force-prefers-reduced-motion"])):
            page = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / label}", *flags,
                                   "--virtual-time-budget=5000", "--dump-dom", f"http://127.0.0.1:{port}/probe.html"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
            names[label] = re.search(r'<pre id="out">(.*?)</pre>', page).group(1)
    finally:
        server.terminate()
    assert names == {"normal": "drift-far drift-near drift-bright view-in", "reduced": "none none none none"}   # all motion stops


# --- Station colours in the browser ---------------------------------------------------------

COLOUR_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:1280px;height:900px;border:0"></iframe><pre id="out"></pre>
<script>
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const root = w.getComputedStyle(d.documentElement);
  const rgb = (c) => { const e = d.createElement("i"); e.style.color = c; d.body.append(e);
    const v = w.getComputedStyle(e).color; e.remove(); return v; };
  const out = { palette: {}, card: {}, icon: {}, finding: {}, tab: {}, title: {}, label: {} };
  for (const v of ["c-thermal", "c-terrain", "c-tryit", "c-drop", "c-mission", "c-validation", "c-sources", "moon"])
    out.palette[v] = rgb(root.getPropertyValue("--" + v).trim());
  for (const c of d.querySelectorAll(".station-card")) {
    out.icon[c.dataset.station] = w.getComputedStyle(c.querySelector(".icon")).color;
    out.card[c.dataset.station] = w.getComputedStyle(c).getPropertyValue("--station").trim();
    out.label[c.dataset.station] = c.querySelector("h2").textContent;
  }
  for (const f of d.querySelectorAll(".finding")) out.finding[f.querySelector("a").getAttribute("href")] =
    w.getComputedStyle(f.querySelector(".kicker")).color;
  for (const s of ["thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]) {
    w.location.hash = s;
    await new Promise((r) => setTimeout(r, 400));
    const tab = d.querySelector('#station-bar [aria-selected="true"]');
    out.tab[s] = { id: tab.id, text: tab.textContent, border: w.getComputedStyle(tab).borderTopColor };
    out.title[s] = w.getComputedStyle(d.getElementById(s + "-title"), "::before").backgroundColor;
  }
  const bars = (name) => w.eval(name + ".data.datasets[0].backgroundColor");
  out.charts = { swing: bars("chart"), temperature: bars("chart2"), slope: bars("slopeChart"), rough: bars("roughChart") };
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>"""


@needs_edge
def test_each_station_wears_its_colour(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "app").symlink_to(APP, target_is_directory=True)
    (root / "colour.html").write_text(COLOUR_HARNESS, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        out = result(subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / 'b'}",
                                     "--virtual-time-budget=10000", "--dump-dom", f"http://127.0.0.1:{port}/colour.html"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=120).stdout)
    finally:
        server.terminate()
    pal = out["palette"]
    assert len(set(pal.values())) == 8                       # seven station colours plus the orange, all different
    labels = {"thermal": "Thermal", "terrain": "Terrain", "tryit": "Try it", "gravity-drop": "Gravity Drop", "mission": "Mission Match",
              "validation": "Validation", "sources": "Sources"}
    for station, var in STATION_COLOURS.items():
        colour = pal[var]
        assert out["icon"][station] == colour                 # hub card icon
        assert out["label"][station] == labels[station]       # the text label stays next to the colour
        assert out["tab"][station] == {"id": f"tab-{station}", "text": labels[station], "border": colour}
        assert out["title"][station] == colour                # the bar beside the station title
    for href, colour in out["finding"].items():               # finding cards use their station's colour
        assert colour == pal[STATION_COLOURS[href.lstrip("#")]]
    # Charts: the Moon/Mars reference bar stays orange; the Earth bars use the station colour
    # (the selected site at full strength, the others lighter).
    hexes = {k: css_var(v).lower() for k, v in STATION_COLOURS.items()}
    moon = css_var("moon").lower()
    assert out["charts"]["swing"][0].lower() == moon and out["charts"]["slope"][0].lower() == moon
    for chart, station in (("swing", "thermal"), ("temperature", "thermal"), ("slope", "terrain"), ("rough", "terrain")):
        bars = out["charts"][chart][1:] if chart != "temperature" else out["charts"][chart]
        assert {b.lower()[:7] for b in bars} == {hexes[station]}, chart
