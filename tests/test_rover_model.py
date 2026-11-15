"""
Tests for the rover illustration in the Try it station (app/rover.js and app.js).
Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

1. The model's sizes come from the inputs by the documented formulas (worked out again here
   in Python): body scale = cube root of (mass / 200 kg), wheel scale = square root of
   (area per wheel / 0.01 m²) with six equal wheels, boom scale = beam length / 2 m, each
   kept inside its limits; every size in px = base size × scale.
2. The three sinking depths have the same ratio as the three ground pressures p = m g / A
   (gravity from config.json), in the drawn numbers and on screen.
3. Invalid inputs show the neutral state, and the "Unrealistic" messages stay.
4. The text description matches the numbers; the kPa under each scene are the calculator's.
5. The model turns with the arrow keys and a drag, "Reset view" brings it back, the sway
   stops for reduced motion, nothing moves on the page when the inputs change, nothing
   scrolls sideways, and the panel text keeps 4.5:1 contrast.
6. Capitalisation: no label, heading or sentence starts with a lower-case "rover".
Console errors are recorded in every run (see test_start_and_hub.py); the whole journey
through every station is checked in test_start_link.py.
"""

import json
import math
from decimal import ROUND_HALF_UP, Decimal
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE  # noqa: E402
from test_start_and_hub import CATCH, serve_and_dump, site_with  # noqa: E402

APP = ROOT / "app"
CONFIG = json.loads((APP / "data" / "config.json").read_text(encoding="utf-8"))
G = {w: CONFIG["gravity_m_s2"][w]["value"] for w in ("earth", "moon", "mars")}
needs_browser = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")

# The documented formulas, written again in Python (rover.js holds the same numbers).
BASE_PX = {"bodyLength": 120, "bodyWidth": 72, "bodyHeight": 30, "wheelDiameter": 34, "wheelWidth": 16, "boomLength": 56}
LIMITS = {"body": (0.6, 1.6), "wheel": (0.5, 2), "boom": (0.4, 2.5)}
SINK_PER_KPA, SINK_MAX_SHARE, SCENE_SCALE = 0.2, 0.6, 0.5


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def expected_scales(mass, area, length):
    return {"body": clamp((mass / 200) ** (1 / 3), *LIMITS["body"]),
            "wheel": clamp(math.sqrt((area / 6) / (0.06 / 6)), *LIMITS["wheel"]),
            "boom": clamp(length / 2, *LIMITS["boom"])}


def expected_px(scales):
    part = {"bodyLength": "body", "bodyWidth": "body", "bodyHeight": "body",
            "wheelDiameter": "wheel", "wheelWidth": "wheel", "boomLength": "boom"}
    return {k: BASE_PX[k] * scales[part[k]] for k in BASE_PX}


def pressures_pa(mass, area):
    return {w: mass * G[w] / area for w in G}


def shown_kpa(pa):
    """The kPa value the way the page writes it (1 decimal, no trailing ".0")."""
    # JavaScript's toFixed(1) rounds an exact half up (278.25 -> 278.3); Python's format would
    # round it to even (278.2), so the exact value of the number is rounded half up here.
    text = str(Decimal(pa / 1000).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return text[:-2] if text.endswith(".0") else text


def js(x):
    return str(int(x)) if float(x).is_integer() else repr(float(x))


# Valid cases: the default, the heavy example, a light one, and both ends of every limit.
VALID = {"default": (200, 0.06, 2), "heavy": (1500, 0.02, 2), "light": (50, 0.5, 6),
         "largest": (5000, 5, 20), "smallest": (1, 0.001, 0.1)}
INVALID = {"empty mass": {"in-mass": ""}, "zero mass": {"in-mass": "0"},
           "area too big": {"in-area": "10"}, "length too long": {"in-length": "50"}}

HARNESS = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html#tryit" style="width:WIDTHpx;height:900px;border:0"></iframe><pre id="out"></pre>
<script>
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const VALID = """ + json.dumps(VALID) + """, INVALID = """ + json.dumps(INVALID) + """;
document.getElementById("f").addEventListener("load", () => setTimeout(async () => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { valid: {}, invalid: {}, keys: {} };
  const stage = d.getElementById("rover-stage");
  const set = async (values) => {
    for (const [id, v] of Object.entries(values)) { const e = d.getElementById(id); e.value = v; e.dispatchEvent(new Event("input")); }
    await sleep(700);   // longer than the 0.35 s change of size
  };
  const where = (sel) => d.querySelector(sel).getBoundingClientRect().top + w.scrollY;
  const read = () => {
    const r = { state: stage.dataset.state, boom: stage.dataset.boom, sizes: JSON.parse(stage.dataset.sizes),
      depth: {}, onScreen: {}, sceneKpa: {}, desc: d.getElementById("rover-desc").textContent,
      list: [...d.querySelectorAll("#out-pressure li")].map((li) => li.textContent),
      msg: { mass: d.getElementById("msg-mass").textContent, area: d.getElementById("msg-area").textContent,
             length: d.getElementById("msg-length").textContent },
      panelTop: where("#panel-rover"), panelHeight: d.getElementById("panel-rover").offsetHeight,
      journeyTop: where("#tryit .journey"), scrollWidth: d.documentElement.scrollWidth,
      clientWidth: d.documentElement.clientWidth };
    for (const li of d.querySelectorAll("#rover-scenes li")) {
      const world = li.dataset.world;
      r.depth[world] = Number(li.querySelector("svg").dataset.depth);
      r.sceneKpa[world] = li.querySelector(".scene-kpa").textContent;
      // On screen: how far below the ground line the bottom of the first wheel is, in CSS px.
      const ground = li.querySelector(".scene-surface").getBoundingClientRect().top;
      const wheel = li.querySelector(".scene-wheel").getBoundingClientRect().bottom;
      const svgBox = li.querySelector("svg");
      r.onScreen[world] = (wheel - ground) / (svgBox.getBoundingClientRect().width / 140);   // back to scene units
    }
    return r;
  };
  try {
    // Headless runs do not advance CSS transitions reliably, so the final sizes are read with
    // transitions off (test_size_changes_are_smooth_in_css checks they exist on the page).
    d.head.insertAdjacentHTML("beforeend", "<style>* { transition: none !important; }</style>");
    out.title = d.getElementById("tryit-title").textContent;
    out.hubText = d.querySelector('#hub [data-station="tryit"] p').textContent;
    out.label = d.getElementById("rover-label").textContent;
    out.note = d.getElementById("rover-note").textContent;
    out.stageRole = [stage.getAttribute("role"), stage.tabIndex, stage.getAttribute("aria-labelledby"), stage.getAttribute("aria-describedby")];
    out.animation = w.getComputedStyle(d.querySelector(".rover-sway")).animationName;
    out.start = read();
    for (const [name, [m, a, l]] of Object.entries(VALID)) {
      await set({ "in-mass": m, "in-area": a, "in-length": l }); out.valid[name] = read();
    }
    for (const [name, values] of Object.entries(INVALID)) {
      await set({ "in-mass": 200, "in-area": 0.06, "in-length": 2 });
      await set(values); out.invalid[name] = read();
    }
    await set({ "in-mass": 200, "in-area": 0.06, "in-length": 2 });
    // Turning: arrow keys, a drag, then "Reset view".
    const turn = d.getElementById("rover-turn");
    stage.focus();
    out.keys.focused = d.activeElement === stage;
    out.keys.start = turn.dataset.view;
    const key = (k) => stage.dispatchEvent(new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    key("ArrowRight"); out.keys.right = turn.dataset.view;
    key("ArrowUp"); out.keys.up = turn.dataset.view;
    out.keys.arrowScrollPrevented = !stage.dispatchEvent(new w.KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
    const r = stage.getBoundingClientRect(), x = r.left + 50, y = r.top + 50;
    const ptr = (type, px, py) => stage.dispatchEvent(new w.PointerEvent(type, { pointerId: 1, clientX: px, clientY: py, bubbles: true, isPrimary: true, pointerType: "mouse", buttons: 1 }));
    out.keys.beforeDrag = turn.dataset.view;
    ptr("pointerdown", x, y); ptr("pointermove", x + 40, y); ptr("pointerup", x + 40, y);
    out.keys.afterDrag = turn.dataset.view;
    ptr("pointermove", x + 200, y);   // not pressed any more: no turning
    out.keys.afterRelease = turn.dataset.view;
    d.getElementById("rover-reset").click(); out.keys.reset = turn.dataset.view;
    // Capitalisation: every text on every view, shown or not.
    out.lowerRover = [];
    for (const n of (function* () { const t = d.createTreeWalker(d.body, w.NodeFilter.SHOW_TEXT); for (let x = t.nextNode(); x; x = t.nextNode()) yield x; })()) {
      if (n.parentElement.closest("script, style")) continue;
      const t = n.textContent.trim();
      if (/^rover\\b/.test(t) || /[.:!?]\\s+rover\\b/.test(t)) out.lowerRover.push(t.slice(0, 80));
    }
    // Contrast of every text in the rover panel against the panel colour under it.
    const rgb = (s) => s.match(/[\\d.]+/g).map(Number);
    const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const bgOf = (e) => { for (; e; e = e.parentElement) { const c = rgb(w.getComputedStyle(e).backgroundColor); if (c.length === 3 || c[3] === 1) return c; } return [0, 0, 0]; };
    out.contrast = [];
    for (const e of d.querySelectorAll("#panel-rover h3, #panel-rover .note, #panel-rover .scene-name, #panel-rover .scene-kpa, #panel-rover .reset-view")) {
      const a = lum(rgb(w.getComputedStyle(e).color)), b = lum(bgOf(e));
      out.contrast.push([e.className || e.tagName, (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)]);
    }
  } catch (err) { (w.__errors || (w.__errors = [])).push("harness: " + err.message); }
  out.errors = w.__errors || [];
  document.getElementById("out").textContent = JSON.stringify(out);
}, 3000), { once: true });
</script>"""


def run(tmp, width, flags=()):
    app_copy = tmp / f"app-{width}-{len(flags)}"
    shutil.copytree(APP, app_copy)
    index = app_copy / "index.html"
    index.write_text(index.read_text(encoding="utf-8").replace("<head>", "<head>\n" + CATCH, 1), encoding="utf-8")
    root = site_with(app_copy, tmp, f"rover-{width}-{len(flags)}", HARNESS.replace("WIDTH", str(width)))
    return serve_and_dump(root, "h.html", f"r{width}{len(flags)}", flags)


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("rover")
    return {1280: run(tmp, 1280), 390: run(tmp, 390),
            "reduced": run(tmp, 1280, ("--force-prefers-reduced-motion",))}


# --- 1. Sizes from the documented formulas --------------------------------------------------

def test_rover_js_holds_the_documented_numbers():
    code = (APP / "rover.js").read_text(encoding="utf-8")
    assert "const ROVER_DEFAULT = { massKg: 200, areaM2: 0.06, lengthM: 2 };" in code
    assert "const ROVER_WHEELS = 6;" in code
    for key, value in BASE_PX.items():
        assert f"{key}: {value}" in code, key
    assert "const ROVER_LIMITS = { body: [0.6, 1.6], wheel: [0.5, 2], boom: [0.4, 2.5] };" in code
    assert f"const SINK_PER_KPA = {SINK_PER_KPA};" in code and f"const SINK_MAX_SHARE = {SINK_MAX_SHARE};" in code
    # The page loads rover.js after formulas.js (it uses isNumber), and before app.js.
    html = (APP / "index.html").read_text(encoding="utf-8")
    assert html.index('src="formulas.js"') < html.index('src="rover.js"') < html.index('src="app.js"')


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_model_sizes_follow_the_inputs(pages, width):
    for name, (m, a, l) in VALID.items():
        got = pages[width]["valid"][name]
        assert got["state"] == "ready" and got["boom"] == "ready", name
        want = expected_scales(m, a, l)
        for k, v in want.items():
            assert got["sizes"]["scales"][k] == pytest.approx(v, rel=1e-12), (name, k)
        for k, v in expected_px(want).items():
            assert got["sizes"]["px"][k] == pytest.approx(v, rel=1e-12), (name, k)
    # The default rover is drawn at the base sizes, the extremes at the limits.
    assert pages[width]["valid"]["default"]["sizes"]["px"] == BASE_PX
    big, small = pages[width]["valid"]["largest"]["sizes"]["scales"], pages[width]["valid"]["smallest"]["sizes"]["scales"]
    assert (big["body"], big["wheel"], big["boom"]) == (1.6, 2, 2.5)
    assert (small["body"], small["wheel"], small["boom"]) == (0.6, 0.5, 0.4)


# --- 2. Sinking depths in the ratio of the pressures -----------------------------------------

@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_sinking_depths_have_the_ratio_of_the_pressures(pages, width):
    for name, (m, a, l) in VALID.items():
        got = pages[width]["valid"][name]
        p = pressures_pa(m, a)
        wheel = expected_px(expected_scales(m, a, l))["wheelDiameter"] * SCENE_SCALE
        factor = min(SINK_PER_KPA, SINK_MAX_SHARE * wheel / (max(p.values()) / 1000))
        for world in G:
            assert got["depth"][world] == pytest.approx(p[world] / 1000 * factor, rel=1e-9), (name, world)
            # The same ratio as the pressures: depth / pressure is one number for all three worlds.
            assert got["depth"][world] / p[world] == pytest.approx(got["depth"]["earth"] / p["earth"], rel=1e-9)
        # On screen too (within 0.25 scene units of drawing and rounding).
        for world in G:
            assert got["onScreen"][world] == pytest.approx(got["depth"][world], abs=0.25), (name, world, got["onScreen"])
        assert got["depth"]["earth"] > got["depth"]["mars"] > got["depth"]["moon"] > 0
        assert max(got["depth"].values()) <= SINK_MAX_SHARE * wheel + 1e-9


# --- 3. Neutral state for invalid inputs -------------------------------------------------------

@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_invalid_inputs_show_the_neutral_state(pages, width):
    inv = pages[width]["invalid"]
    for name in ("empty mass", "zero mass", "area too big"):
        got = inv[name]
        assert got["state"] == "neutral", name
        assert got["sizes"]["px"] == BASE_PX, name                       # drawn at the default size
        assert got["depth"] == {"earth": 0, "moon": 0, "mars": 0}, name   # no sinking drawn
        assert set(got["sceneKpa"].values()) == {"– kPa"}, name
        assert "neutral state" in got["desc"], name
    assert inv["empty mass"]["msg"]["mass"] == "Enter a number."
    assert inv["zero mass"]["msg"]["mass"] == "Unrealistic: use 1 to 5000 kg."       # the old messages stay
    assert inv["area too big"]["msg"]["area"] == "Unrealistic: use 0.001 to 5 m²."
    # A wrong beam length only greys the boom; the rover and its pressures still show.
    beam = inv["length too long"]
    assert beam["state"] == "ready" and beam["boom"] == "neutral"
    assert beam["msg"]["length"] == "Unrealistic: use 0.1 to 20 m."
    assert beam["sizes"]["px"]["boomLength"] == BASE_PX["boomLength"]
    assert "boom arm is drawn at its default size" in beam["desc"]


# --- 4. Description and kPa labels match the numbers --------------------------------------------

@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_description_and_labels_match_the_numbers(pages, width):
    for name, (m, a, l) in VALID.items():
        got = pages[width]["valid"][name]
        kpa = {w: shown_kpa(p) for w, p in pressures_pa(m, a).items()}
        # Under each scene: the calculator's own value, the same as in the results list.
        for world, label in (("earth", "Earth"), ("moon", "Moon"), ("mars", "Mars")):
            assert got["sceneKpa"][world] == f"{kpa[world]} kPa", (name, world)
            assert f"{label}: {kpa[world]} kPa" in got["list"][["earth", "moon", "mars"].index(world)]
        s = expected_scales(m, a, l)
        desc = got["desc"]
        assert desc.startswith(f"Generic six-wheel rover (illustration) for a {js(m)} kg rover on {js(a)} m² of wheel contact"), desc
        assert f"six equal wheels of {js(float(f'{a / 6:.3g}'))} m² each" in desc
        assert f"body is drawn at {s['body']:.2f} times the 200 kg size" in desc
        assert f"each wheel at {s['wheel']:.2f} times the default wheel size" in desc
        assert f"follows the {js(l)} m beam, drawn at {s['boom']:.2f} times the 2 m length" in desc
        assert f"Earth {kpa['earth']} kPa, Moon {kpa['moon']} kPa, Mars {kpa['mars']} kPa" in desc
        assert desc.endswith("deepest on Earth and least on the Moon.")
    assert "(the largest size drawn)" in pages[width]["valid"]["largest"]["desc"]
    assert "(the smallest size drawn)" in pages[width]["valid"]["smallest"]["desc"]


@needs_browser
def test_label_note_and_accessible_model(pages):
    out = pages[1280]
    assert out["label"] == "Generic six-wheel rover (illustration)"
    assert out["note"] == ("Illustration only. Wheel size follows contact area (six equal wheels assumed), body size "
                           "follows mass and sinking depth is drawn in proportion to ground pressure. "
                           "It is not a soil simulation.")
    assert out["stageRole"] == ["img", 0, "rover-label", "rover-desc"]   # focusable, named and described


# --- 5. Turning, motion, layout and contrast ----------------------------------------------------

@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_turning_by_keys_and_drag_and_reset(pages, width):
    k = pages[width]["keys"]
    assert k["focused"] and k["start"] == "-18,-34"
    assert k["right"] == "-18,-24" and k["up"] == "-23,-24"      # 10° per left/right press, 5° per up/down
    assert k["arrowScrollPrevented"]                              # the arrow keys do not scroll the page
    assert k["afterDrag"] == "-18,-4" and k["afterRelease"] == "-18,-4"   # after ArrowDown; a 40 px drag = 20°
    assert k["reset"] == "-18,-34"


def test_focus_ring_sway_and_reduced_motion_in_css():
    css = re.sub(r"/\*.*?\*/", "", (APP / "style.css").read_text(encoding="utf-8"), flags=re.S)
    assert re.search(r"\.rover-stage:focus-visible \{ outline: 3px solid var\(--accent\)", css)
    sway = re.search(r"\.rover-sway \{ animation: rover-sway (\d+)s ease-in-out infinite alternate; \}", css)
    assert sway and int(sway.group(1)) >= 10                        # very slow
    frames = re.search(r"@keyframes rover-sway \{(.*?)\}\s*\}", css, re.S).group(1)
    assert "rotateY(-4deg)" in frames and "rotateY(4deg)" in frames   # a small sway, never a full spin
    reduced = " ".join(re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S))
    assert ".rover-sway { animation: none; }" in reduced


def test_size_changes_are_smooth_in_css():
    css = re.sub(r"/\*.*?\*/", "", (APP / "style.css").read_text(encoding="utf-8"), flags=re.S)
    rule = re.search(r"\.rover-3d, \.rv-part, \.rv-face, \.rv-disc, \.rv-tread, \.rv-ground \{\s*transition: ([^;]+);", css)
    assert rule and all(f"{p} 0.35s" in rule.group(1) for p in ("transform", "width", "height"))
    assert re.search(r"\.scene-svg \* \{ transition: transform 0\.35s ease;", css)


@needs_browser
def test_sway_runs_only_without_reduced_motion(pages):
    assert pages[1280]["animation"] == "rover-sway"
    assert pages["reduced"]["animation"] == "none"


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_no_layout_shift_and_no_sideways_scroll(pages, width):
    out = pages[width]
    states = [out["start"], *out["valid"].values(), *out["invalid"].values()]
    for s in states:
        assert s["scrollWidth"] == s["clientWidth"] >= width - 20   # nothing wider than the window (a scroll bar may take some)
        # The rover panel keeps its height, and everything after it keeps its distance from it,
        # whatever the inputs. (The results text above it already changes length with the numbers.)
        assert s["panelHeight"] == out["start"]["panelHeight"]
        assert s["journeyTop"] - s["panelTop"] == out["start"]["journeyTop"] - out["start"]["panelTop"]


@needs_browser
@pytest.mark.parametrize("width", [1280, 390])
def test_panel_text_contrast(pages, width):
    assert len(pages[width]["contrast"]) >= 8
    for name, ratio in pages[width]["contrast"]:
        assert ratio >= 4.5, (name, ratio)


# --- 6. Capitalisation and errors ------------------------------------------------------------------

@needs_browser
def test_rover_capitalised_at_the_start_of_labels_and_sentences(pages):
    out = pages[1280]
    assert out["title"] == "Try it: Rover calculator"
    assert out["hubText"] == "Rover calculator: ground pressure and beam expansion for your own rover."
    assert out["lowerRover"] == []      # every text node of every view, shown or hidden


@needs_browser
@pytest.mark.parametrize("width", [1280, 390, "reduced"])
def test_no_console_errors(pages, width):
    assert pages[width]["errors"] == [], pages[width]["errors"]
