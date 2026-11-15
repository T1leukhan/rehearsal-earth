"""
Tests for the night-sky background. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

1. The sky is decoration only: hidden from screen readers, never clickable, behind the
   content, and it causes no layout shift and no sideways scrolling.
2. Its only movement is the slow star drift (transform only, 120 s or longer loops),
   and every animation stops under prefers-reduced-motion.
3. Contrast against the brightest part of the sky: the sky is drawn on its own (text,
   cards and star layers hidden) at desktop and phone screen size. The sky stays still
   while the page scrolls, so a text block can pass over every sky row from where it sits
   on the screen at the top of the page up to where it sits when the page is scrolled all
   the way down. Every text block on the sky is measured against the brightest sky pixel
   in that whole area (its columns, all those rows), so every scroll position is covered.
   Text on a solid card is measured against the card. The star layers are left out: a
   star is a point of light, not the background of a text block.
4. No repaints while scrolling: Chrome is driven through its debugging pipe, a real scroll
   gesture is made while Chrome records a trace, and the trace must show no Paint and no
   Layout during the scroll. A page that recolours itself on every scroll must show paints,
   which proves the check can see them.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, NO_LIVE_TILES, wait_for_server  # noqa: E402

APP = ROOT / "app"
CSS = (APP / "style.css").read_text(encoding="utf-8")
HTML = (APP / "index.html").read_text(encoding="utf-8")
VIEWS = ["start", "hub", "thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"]
SIZES = {1280: 800, 390: 844}          # desktop and phone screen sizes (width: height)
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


# --- 1 and 2: in the code ---------------------------------------------------------------------

def test_sky_is_decoration_only():
    sky = re.search(r'<div class="sky" aria-hidden="true">(.*?)\n  </div>', HTML, re.S)
    assert sky, "the sky must be one aria-hidden block"
    assert "<img" not in sky.group(1) and "<video" not in sky.group(1)
    rule = re.search(r"\.sky \{([^}]*)\}", CSS).group(1)
    for part in ("position: fixed", "z-index: -1", "pointer-events: none", "overflow: hidden"):
        assert part in rule
    code = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert "background-attachment: fixed" not in code       # it makes browsers repaint on scroll
    assert "url(" not in code and "@import" not in code    # no image files, no outside resources


def test_star_drift_is_slow_transform_only_and_stops_for_reduced_motion():
    code = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    drifts = re.findall(r"animation: (drift-\w+) (\d+)s linear infinite;", code)
    assert sorted(name for name, _ in drifts) == ["drift-bright", "drift-far", "drift-near"]
    assert all(int(seconds) >= 120 for _, seconds in drifts)
    for name, _ in drifts:
        frames = re.search(rf"@keyframes {name} \{{(.*?)\}}\s*\}}", code, re.S).group(1)
        assert "transform" in frames and "opacity" not in frames       # moves only; never flashes
    reduced = " ".join(re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", code, re.S))
    assert re.search(r"\.stars \{ animation: none; \}", reduced)


# --- Browser helpers -----------------------------------------------------------------------------

def serve(root):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_for_server(port)
    return server, port


def site(tmp_path, name, files):
    root = tmp_path / name
    root.mkdir()
    (root / "app").symlink_to(APP, target_is_directory=True)
    for file, text in files.items():
        (root / file).write_text(text, encoding="utf-8")
    return root


# Reads every visible text block on every view (all hidden parts opened): its columns,
# its colour and the backgrounds of the boxes behind it, up to the first solid one.
TEXT_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html" style="width:WIDTHpx;height:HEIGHTpx;border:0"></iframe><pre id="out"></pre>
<script>
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { blocks: [], scrollWidth: {}, scrollHeight: {}, loadShift: 0, skyShifts: 0, shiftSources: 0 };
  // Layout shifts: those while the start page loads, and whether any moved part belongs to the sky.
  let loading = true;
  new w.PerformanceObserver((list) => { for (const e of list.getEntries()) {
    if (loading && !e.hadRecentInput) out.loadShift += e.value;
    for (const s of e.sources || []) { out.shiftSources++; if (s.node && s.node.nodeType === 1 && s.node.closest(".sky")) out.skyShifts++; }
  } }).observe({ type: "layout-shift", buffered: true });
  await sleep(50);
  loading = false;
  for (const v of VIEWS) {
    w.location.hash = v; await sleep(400);
    for (const x of d.querySelectorAll("details")) x.open = true;
    for (const b of d.querySelectorAll('.reveal-btn[aria-expanded="false"]')) b.click();
    out.scrollWidth[v] = (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth);
    out.scrollHeight[v] = d.documentElement.scrollHeight;
    for (const e of d.body.querySelectorAll("*")) {
      if (e.closest(".sky")) continue;
      const own = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if ((!own && !e.matches("input, select")) || !e.getClientRects().length) continue;
      const cs = w.getComputedStyle(e);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      const layers = [];
      let solid = false;
      for (let n = e; n && n !== d.body; n = n.parentElement) {
        const bg = w.getComputedStyle(n).backgroundColor;
        const m = bg.match(/rgba?\\(([^)]+)\\)/);
        if (!m) continue;
        const p = m[1].split(",").map(Number);
        const a = p.length > 3 ? p[3] : 1;
        if (a > 0) { layers.push([p[0], p[1], p[2], a]); if (a === 1) { solid = true; break; } }
      }
      const r = e.getBoundingClientRect();
      out.blocks.push({ view: v, x0: Math.max(0, Math.floor(r.left)), x1: Math.min(WIDTH, Math.ceil(r.right)),
        top: Math.floor(r.top + w.scrollY), bottom: Math.ceil(r.bottom + w.scrollY),
        color: cs.color, layers, solid, text: (e.textContent || e.value || "").trim().slice(0, 40) });
    }
  }
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000));
</script>""".replace("VIEWS", json.dumps(VIEWS))

# The sky on its own, at screen size: everything else and the star dots hidden.
SKY_HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0;background:#000">
<iframe id="f" src="app/index.html#VIEW" style="width:WIDTHpx;height:HEIGHTpx;border:0;display:block"></iframe>
<script>document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const d = document.getElementById("f").contentDocument;
  d.head.insertAdjacentHTML("beforeend", "<style>body > *:not(.sky) { visibility: hidden !important; } .stars { display: none !important; }</style>");
  window.scrollTo(0, 0);
}, 2000));</script>"""


def rgb(text):
    p = [float(x) for x in re.match(r"rgba?\(([^)]+)\)", text).group(1).split(",")]
    return p[:3] + [p[3] if len(p) > 3 else 1.0]


def luminance(c):
    c = np.asarray(c, dtype=float)[..., :3] / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def over(top, under):
    a = top[3]
    return [top[i] * a + under[i] * (1 - a) for i in range(3)] + [1.0]


def contrast(a, b):
    la, lb = sorted((float(luminance(a)), float(luminance(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def sky_image(tmp_path, width, view):
    """The sky alone as an array of pixels (height x width x 3), rendered by the browser."""
    import rasterio
    height = SIZES[width]
    root = site(tmp_path, f"sky-{view}-{width}", {"sky.html": SKY_HARNESS.replace("VIEW", view)
                                                    .replace("WIDTH", str(width)).replace("HEIGHT", str(height))})
    server, port = serve(root)
    shot = root / "sky.png"
    try:
        subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, "--hide-scrollbars",
                        "--force-prefers-reduced-motion", f"--user-data-dir={root / 'b'}",
                        f"--window-size={max(width, 500)},{height}", "--virtual-time-budget=6000",
                        f"--screenshot={shot}", f"http://127.0.0.1:{port}/sky.html"],
                       capture_output=True, timeout=90)
    finally:
        server.terminate()
    with rasterio.open(shot) as src:
        pixels = np.moveaxis(src.read()[:3], 0, -1)
    return pixels[:height, :width]


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """For each width: the text blocks, and for each column the brightest sky pixel."""
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    pytest.importorskip("rasterio")
    tmp = tmp_path_factory.mktemp("sky")
    result = {}
    for width, height in SIZES.items():
        root = site(tmp, f"text-{width}", {"h.html": TEXT_HARNESS.replace("WIDTH", str(width)).replace("HEIGHT", str(height))})
        server, port = serve(root)
        try:
            page = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={root / 'b'}",
                                   "--virtual-time-budget=30000", "--dump-dom", f"http://127.0.0.1:{port}/h.html"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
        finally:
            server.terminate()
        raw = re.search(r'<pre id="out">(.*?)</pre>', page, re.S).group(1)
        for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
            raw = raw.replace(a, b)
        out = json.loads(raw)
        out["sky"] = {kind: sky_image(tmp, width, kind) for kind in ("start", "hub")}   # the start page has its own sky
        out["height"] = height
        result[width] = out
    return result


def worst_cases(out):
    """Every text block's contrast against what is behind it, worst first."""
    cases = []
    for b in out["blocks"]:
        layers = [list(map(float, l)) for l in b["layers"]]
        if b["solid"]:
            bg = layers[-1][:3] + [1.0]
            for layer in reversed(layers[:-1]):
                bg = over(layer, bg)
        else:
            # Screen rows this block can cover: from its place with the page at the top (top..bottom)
            # up to its place with the page scrolled all the way down (top - furthest scroll).
            sky = out["sky"]["start" if b["view"] == "start" else "hub"]
            furthest = max(0, out["scrollHeight"][b["view"]] - out["height"])
            y0, y1 = max(0, b["top"] - furthest), min(out["height"], max(b["bottom"], 1))
            x0, x1 = b["x0"], max(b["x1"], b["x0"] + 1)
            area = sky[max(0, min(y0, out["height"] - 1)):max(y1, y0 + 1), x0:x1]
            lum = luminance(area)
            y, x = np.unravel_index(lum.argmax(), lum.shape)
            bg = list(map(float, area[y, x])) + [1.0]
            for layer in reversed(layers):
                bg = over(layer, bg)
        fg = over(rgb(b["color"]), bg)
        cases.append((round(contrast(fg, bg), 2), b["view"], b["text"], b["solid"]))
    return sorted(cases)


@needs_browser
@pytest.mark.parametrize("width", list(SIZES))
def test_text_contrast_against_the_brightest_sky(measured, width):
    cases = worst_cases(measured[width])
    assert len(cases) > 500
    on_sky = [c for c in cases if not c[3]]
    assert on_sky, "some text must sit straight on the sky"
    print(f"\nwidth {width}: minimum {cases[0][0]}:1 ({cases[0][1]}: '{cases[0][2]}'); "
          f"minimum on the sky {on_sky[0][0]}:1 ({on_sky[0][1]}: '{on_sky[0][2]}')")
    assert cases[0][0] >= 4.5, cases[:5]


@needs_browser
@pytest.mark.parametrize("width", list(SIZES))
def test_no_sideways_scroll_and_no_layout_shift(measured, width):
    out = measured[width]
    assert out["scrollWidth"] == {v: width for v in VIEWS}
    assert out["skyShifts"] == 0              # no part of the sky ever moves the layout
    assert out["loadShift"] == 0              # the start page does not shift while it loads


# --- 4: no repaints while scrolling ------------------------------------------------------------

class Chrome:
    """A headless browser controlled through its debugging pipe (no extra packages needed)."""

    def __init__(self, profile):
        cmd_r, self.cmd_w = os.pipe()
        self.res_r, res_w = os.pipe()

        def child():                  # Chrome reads commands on file 3 and answers on file 4
            os.dup2(cmd_r, 3)
            os.dup2(res_w, 4)
        self.proc = subprocess.Popen([EDGE, "--headless", "--remote-debugging-pipe", "--hide-scrollbars", NO_LIVE_TILES,
                                      "--window-size=1280,800", f"--user-data-dir={profile}", "about:blank"],
                                     preexec_fn=child, pass_fds=(3, 4),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(cmd_r)
        os.close(res_w)
        self.buf, self.next_id, self.waiting = b"", 0, []

    def read(self):
        while b"\0" not in self.buf:
            chunk = os.read(self.res_r, 1 << 20)
            if not chunk:
                raise RuntimeError("the browser closed")
            self.buf += chunk
        message, self.buf = self.buf.split(b"\0", 1)
        return json.loads(message)

    def send(self, method, params=None, session=None):
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        os.write(self.cmd_w, json.dumps(message).encode() + b"\0")
        while True:
            m = self.read()
            if m.get("id") == self.next_id:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.waiting.append(m)

    def wait_for(self, event):
        for i, m in enumerate(self.waiting):
            if m.get("method") == event:
                return self.waiting.pop(i)
        while True:
            m = self.read()
            if m.get("method") == event:
                return m
            self.waiting.append(m)


def trace_scroll(profile, url, before=None):
    """Scroll the page with a real gesture (from the empty left margin, so no button is touched)
    while tracing; return how far it scrolled and how many Paint and Layout events happened."""
    c = Chrome(profile)
    try:
        target = c.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = c.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        c.send("Page.enable", session=s)
        c.send("Page.navigate", {"url": url}, session=s)
        c.wait_for("Page.loadEventFired")
        # Let the page settle before measuring. The test blocks live map tiles, so the map
        # shows its "tiles could not load" message once they fail; wait for that (up to 10 s),
        # because it appearing during the scroll would be a layout change of its own.
        for _ in range(100):
            shown = c.send("Runtime.evaluate", {"expression": "!document.getElementById('map-message').hidden",
                                                "returnByValue": True}, session=s)["result"]["value"]
            if shown:
                break
            time.sleep(0.1)
        time.sleep(2.5)                                  # the charts' entry animation and the fade-in finish
        if before:
            c.send("Runtime.evaluate", {"expression": before}, session=s)
        c.send("Tracing.start", {"categories": "devtools.timeline,disabled-by-default-devtools.timeline",
                                 "transferMode": "ReportEvents"})
        time.sleep(0.5)
        c.send("Runtime.evaluate", {"expression": "console.timeStamp('scroll-start')"}, session=s)
        c.send("Input.synthesizeScrollGesture", {"x": 30, "y": 400, "yDistance": -1500, "speed": 1000,
                                                 "gestureSourceType": "touch"}, session=s)
        c.send("Runtime.evaluate", {"expression": "console.timeStamp('scroll-end')"}, session=s)
        scrolled = c.send("Runtime.evaluate", {"expression": "scrollY", "returnByValue": True}, session=s)["result"]["value"]
        c.send("Tracing.end")
        events = []
        while True:
            m = c.read() if not c.waiting else c.waiting.pop(0)
            if m.get("method") == "Tracing.dataCollected":
                events += m["params"]["value"]
            if m.get("method") == "Tracing.tracingComplete":
                break
    finally:
        c.proc.kill()
    marks = {e["args"]["data"]["message"]: e["ts"] for e in events if e.get("name") == "TimeStamp"}
    during = [e for e in events if marks["scroll-start"] <= e.get("ts", 0) <= marks["scroll-end"]]
    return scrolled, sum(e["name"] == "Paint" for e in during), sum(e["name"] == "Layout" for e in during)


needs_pipe = pytest.mark.skipif(not EDGE or os.name == "nt", reason="needs a Chromium browser and a Unix pipe")


@pytest.fixture(scope="module")
def server_url(tmp_path_factory):
    root = site(tmp_path_factory.mktemp("trace"), "site", {})
    server, port = serve(root)
    yield f"http://127.0.0.1:{port}/app/index.html"
    server.terminate()


@needs_pipe
@pytest.mark.parametrize("view", ["start", "thermal", "tryit", "mission"])
def test_no_repaint_or_layout_while_scrolling(tmp_path, server_url, view):
    scrolled, paints, layouts = trace_scroll(tmp_path / "b", f"{server_url}#{view}")
    assert scrolled > 200                       # the page really scrolled
    assert (paints, layouts) == (0, 0)


@needs_pipe
def test_the_trace_can_see_repaints(tmp_path, server_url):
    # Control: a page that recolours its sky on every scroll event must show paints.
    recolour = ("addEventListener('scroll', () => { document.querySelector('.sky-base').style.background = "
                "'rgb(10,' + (Math.round(scrollY) % 40) + ',48)'; })")
    scrolled, paints, _ = trace_scroll(tmp_path / "b", f"{server_url}#thermal", before=recolour)
    assert scrolled > 200 and paints > 10
