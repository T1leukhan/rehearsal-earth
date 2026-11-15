"""
Tests for the "Gravity Drop" panel. Run from the project folder:
    .venv/bin/python -m pytest pipeline tests -v

The formulas live in app/formulas.js, so they are run in the same headless browser
as pipeline/test_formulas.py and checked against values worked out by hand.
"""

import json
import math
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from test_formulas import EDGE, needs_edge, run_js, NO_LIVE_TILES, wait_for_server  # noqa: E402

CONFIG = json.loads((ROOT / "app" / "data" / "config.json").read_text(encoding="utf-8"))
G = {body: CONFIG["gravity_m_s2"][body]["value"] for body in ("earth", "moon", "mars")}


# --- The formulas, against hand-calculated values ---------------------------------

def test_gravity_values_are_the_ones_in_config():
    assert G == {"earth": 9.81, "moon": 1.62, "mars": 3.71}


@needs_edge
def test_fall_time_by_hand(tmp_path):
    # t = sqrt(2 h / g) for h = 2 m:
    #   Earth sqrt(4 / 9.81) = sqrt(0.4077) = 0.6386 s -> 0.64 s
    #   Moon  sqrt(4 / 1.62) = sqrt(2.4691) = 1.5713 s -> 1.57 s
    #   Mars  sqrt(4 / 3.71) = sqrt(1.0782) = 1.0383 s -> 1.04 s
    answers = run_js(tmp_path, [f"shownDrop(fallTimeS(2, {G[b]}))" for b in ("earth", "moon", "mars")])
    assert answers == [0.64, 1.57, 1.04]


@needs_edge
def test_impact_speed_by_hand(tmp_path):
    # v = sqrt(2 g h) for h = 2 m:
    #   Earth sqrt(2 * 9.81 * 2) = sqrt(39.24) = 6.264 m/s -> 6.26 m/s
    #   Moon  sqrt(2 * 1.62 * 2) = sqrt(6.48)  = 2.546 m/s -> 2.55 m/s
    #   Mars  sqrt(2 * 3.71 * 2) = sqrt(14.84) = 3.852 m/s -> 3.85 m/s
    answers = run_js(tmp_path, [f"shownDrop(impactSpeedMs(2, {G[b]}))" for b in ("earth", "moon", "mars")])
    assert answers == [6.26, 2.55, 3.85]


@needs_edge
def test_formulas_unrounded_and_bad_inputs(tmp_path):
    answers = run_js(tmp_path, [
        "fallTimeS(2, 9.81)", "impactSpeedMs(2, 9.81)",
        "fallTimeS(0, 9.81)", "impactSpeedMs(0, 1.62)",          # no height: no fall, no speed
        "fallTimeS(null, 9.81)", "fallTimeS(-1, 9.81)", "fallTimeS(2, 0)", "impactSpeedMs(2, -1)",
        "dropHeightForSpeedM(impactSpeedMs(2, 1.62), 9.81)",     # same speed as a 2 m Moon drop
    ])
    assert answers[0] == pytest.approx(math.sqrt(4 / 9.81)) and answers[1] == pytest.approx(math.sqrt(39.24))
    assert answers[2] == 0 and answers[3] == 0
    assert answers[4:8] == [None, None, None, None]
    assert answers[8] == pytest.approx(2 * 1.62 / 9.81)          # h_earth = h * g_moon / g_earth = 0.330 m


# --- Input limits -------------------------------------------------------------------

@needs_edge
def test_drop_height_limits(tmp_path):
    lim = "DROP_LIMITS_M.min, DROP_LIMITS_M.max, 'm'"
    answers = run_js(tmp_path, [
        "[DROP_LIMITS_M.min, DROP_LIMITS_M.max]",
        f"rangeMessage(2, {lim})",        # the default is fine
        f"rangeMessage(0.1, {lim})",      # exactly on the lower limit is fine
        f"rangeMessage(20, {lim})",       # exactly on the upper limit is fine
        f"rangeMessage(0.09, {lim})",     # too low
        f"rangeMessage(20.1, {lim})",     # too high
        f"rangeMessage(-2, {lim})",       # negative
        f"rangeMessage(null, {lim})",     # empty box
    ])
    assert answers[0] == [0.1, 20]
    assert answers[1:4] == [None, None, None]
    assert answers[4] == answers[5] == answers[6] == "Unrealistic: use 0.1 to 20 m."
    assert answers[7] == "Enter a number."


# --- The sentence -----------------------------------------------------------------------

@needs_edge
def test_sentence_for_the_default_drop(tmp_path):
    # Shown values for 2 m: t 0.64 / 1.57 s, v 6.26 / 2.55 / 3.85 m/s.
    # Earth heights matching those speeds: 2.55^2 / 19.62 = 0.3314 -> 0.33 m, 3.85^2 / 19.62 = 0.7555 -> 0.76 m.
    [text] = run_js(tmp_path, ["dropSentence(2, 0.64, 1.57, 6.26, 2.55, 0.33, 0.76)"])
    assert text == ("A 2 m fall takes 1.57/0.64 = 2.5 times as long on the Moon as on Earth and lands at "
                    "2.55 m/s instead of 6.26 m/s, so a landing-gear drop test on Earth matches the Moon's "
                    "impact speed from only 0.33 m (Mars: 0.76 m), but it cannot reproduce the Moon's slower, longer fall.")


# --- The live page ---------------------------------------------------------------------

# Opens the page, reads the panel, types into the height box and presses Drop.
PROBE = """<!doctype html><meta charset="utf-8"><body style="margin:0">
<iframe id="f" src="app/index.html#gravity-drop" style="width:WIDTHpx;height:1200px;border:0"></iframe><pre id="out"></pre>
<script>
const norm = (s) => s.replace(/\\s+/g, " ").trim();
document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const w = document.getElementById("f").contentWindow, d = w.document;
  const out = { lists: {}, landedBefore: {}, landedNow: {} };
  for (const b of ["earth", "moon", "mars"]) out.lists[b] = norm(d.getElementById("out-drop-" + b).textContent);
  out.sentence = d.getElementById("drop-sentence").textContent;
  out.caveat = d.getElementById("drop-caveat").textContent;
  out.inTryIt = d.getElementById("tryit").nextElementSibling.id === "gravity-drop" && !d.getElementById("gravity-drop").hidden;
  out.scrollWidth = (d.documentElement.scrollWidth + d.defaultView.innerWidth - d.documentElement.clientWidth);
  const button = d.getElementById("drop-button");
  out.button = { tag: button.tagName, type: button.type, inForm: button.form && button.form.id };
  for (const b of ["earth", "moon", "mars"]) out.landedBefore[b] = d.getElementById("landed-" + b).textContent;
  button.click();
  for (const b of ["earth", "moon", "mars"]) out.landedNow[b] = d.getElementById("landed-" + b).textContent;
  out.statusNow = d.getElementById("drop-status").textContent;
  setTimeout(() => {   // after the slowest (Moon) fall has ended
  out.landedLater = {}; out.onFloor = {};
  for (const b of ["earth", "moon", "mars"]) {
    out.landedLater[b] = d.getElementById("landed-" + b).textContent;
    const shape = d.querySelector(".shape-" + b), track = shape.parentElement;
    out.onFloor[b] = Math.abs(shape.getBoundingClientRect().bottom - (track.getBoundingClientRect().top + track.clientHeight)) < 1;
  }
  out.statusLater = d.getElementById("drop-status").textContent;
  const box = d.getElementById("in-drop");
  out.messages = [];
  for (const value of ["0.05", "25", "", "0.1", "20", "2"]) {
    box.value = value;
    box.dispatchEvent(new w.Event("input"));
    out.messages.push([value, d.getElementById("msg-drop").textContent, box.getAttribute("aria-invalid"),
                       d.getElementById("drop-sentence").textContent === ""]);
  }
  document.getElementById("out").textContent = JSON.stringify(out);
  }, 2500);
}, 3000));
</script>"""


def probe(tmp_path, width, flags=()):
    root = tmp_path / f"site-{width}-{len(flags)}"
    root.mkdir()
    (root / "app").symlink_to(ROOT / "app", target_is_directory=True)
    (root / "probe.html").write_text(PROBE.replace("WIDTH", str(width)), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        page = subprocess.run([EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={root / 'browser'}", *flags,
                               "--virtual-time-budget=8000", "--dump-dom", f"http://127.0.0.1:{port}/probe.html"],
                              capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
    finally:
        server.terminate()
    found = re.search(r'<pre id="out">(.*?)</pre>', page, re.S)
    assert found, page[:500]
    return json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


@pytest.fixture(scope="module")
def pages(tmp_path_factory):
    if not EDGE:
        pytest.skip("No Edge, Chrome or Chromium found")
    tmp = tmp_path_factory.mktemp("drop")
    return {"desktop": probe(tmp, 1280), "phone": probe(tmp, 390),
            "reduced": probe(tmp, 1280, ["--force-prefers-reduced-motion"])}


@needs_edge
def test_panel_shows_formulas_with_worked_lines(pages):
    page = pages["desktop"]
    assert page["inTryIt"]                                   # its own station, right after Try it, open at #gravity-drop
    expected = {"earth": ("0.64 s", "6.26 m/s"), "moon": ("1.57 s", "2.55 m/s"), "mars": ("1.04 s", "3.85 m/s")}
    for body, (t, v) in expected.items():
        text = page["lists"][body]
        assert f"t = √(2 × 2 m ÷ {G[body]} m/s²) = {t}" in text
        assert f"v = √(2 × {G[body]} m/s² × 2 m) = {v}" in text
    assert page["sentence"].startswith("A 2 m fall takes 1.57/0.64 = 2.5 times as long on the Moon")
    assert "no air resistance" in page["caveat"] and "Mars's thin air" in page["caveat"] and "the Moon has none" in page["caveat"]


@needs_edge
def test_drop_box_limits_on_the_page(pages):
    messages = pages["desktop"]["messages"]
    assert messages == [
        ["0.05", "Unrealistic: use 0.1 to 20 m.", "true", True],
        ["25", "Unrealistic: use 0.1 to 20 m.", "true", True],
        ["", "Enter a number.", "true", True],
        ["0.1", "", "false", False],
        ["20", "", "false", False],
        ["2", "", "false", False],
    ]


@needs_edge
def test_drop_button_is_a_keyboard_button(pages):
    # A real <button type="submit"> in the form: Tab reaches it, Enter and Space press it.
    assert pages["desktop"]["button"] == {"tag": "BUTTON", "type": "submit", "inForm": "drop-form"}


@needs_edge
def test_animation_runs_normally_and_is_skipped_for_reduced_motion(pages):
    normal, reduced = pages["desktop"], pages["reduced"]
    # Normally the shapes are still falling right after the click: nothing has landed yet.
    assert all(v == "" for v in normal["landedNow"].values())
    assert normal["statusNow"].startswith("Falling")
    # With reduced motion the results are there at once.
    assert reduced["landedNow"] == {"earth": "Earth: landed after 0.64 s", "moon": "Moon: landed after 1.57 s",
                                    "mars": "Mars: landed after 1.04 s"}
    assert reduced["statusNow"] == "All three landed: Earth 0.64 s, Moon 1.57 s, Mars 1.04 s."
    # When the falls are over, every shape is on the floor and every result is shown, in both cases.
    for page in (normal, reduced):
        assert page["landedLater"] == reduced["landedNow"]
        assert page["onFloor"] == {"earth": True, "moon": True, "mars": True}
        assert page["statusLater"] == reduced["statusNow"]


@needs_edge
def test_panel_fits_a_phone(pages):
    assert pages["phone"]["scrollWidth"] == 390
    assert pages["phone"]["lists"] == pages["desktop"]["lists"]
