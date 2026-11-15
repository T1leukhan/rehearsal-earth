"""
Tests for the "Try it" formulas. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v

The formulas live in app/formulas.js (JavaScript), so we run that exact file in
a headless browser and read the answers back. The project has no Node and no
build step, so a browser is the simplest way. We use Microsoft Edge if it is
installed, otherwise Google Chrome or Chromium (they take the same options).
On macOS/Linux run:  .venv/bin/python -m pytest pipeline -v
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
CONFIG = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
THERMAL = json.loads((DATA / "thermal.json").read_text(encoding="utf-8"))
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))

def find_browser():
    """Return the path of the first headless-capable browser we find, or "" if none."""
    # Programs on the PATH (Windows and Linux names).
    for name in ["msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"]:
        if shutil.which(name):
            return shutil.which(name)
    # Usual install places on Windows and macOS.
    places = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for place in places:
        if Path(place).exists():
            return place
    return ""


# The name EDGE is kept so the tests below do not change; it may be Chrome.
EDGE = find_browser()

def site_names():
    """The page's display names, read from app/names.js: {key: (short name, long name)}.
    The data keeps its keys (e.g. "atacama"); the page shows these names instead."""
    code = (ROOT / "app" / "names.js").read_text(encoding="utf-8")
    return {k: (short, long) for k, short, long in
            re.findall(r'(\w+): \{ short: "([^"]+)", long: "([^"]+)" \}', code)}


SHORT = {k: v[0] for k, v in site_names().items()}   # e.g. "atacama" -> "Atacama Desert"
LONG = {k: v[1] for k, v in site_names().items()}    # e.g. "atacama" -> "Atacama Desert (Chile)"


def wait_for_server(port, timeout_s=30):
    """Wait until the local test web server on this port accepts connections.
    (A fixed one-second pause was not always enough when the computer was busy.)"""
    import socket
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"the test web server on port {port} did not start within {timeout_s} s")


# Page tests never fetch live map tiles: these hosts are made to fail at once, so no test
# waits on the network or depends on its timing. (test_page_map.py serves its own tiles,
# and the old page versions used OpenStreetMap tiles.)
NO_LIVE_TILES = "--host-resolver-rules=MAP gibs.earthdata.nasa.gov ~NOTFOUND, MAP tile.openstreetmap.org ~NOTFOUND"


def run_js(tmp_path, cases):
    """Run each JS expression in `cases` with formulas.js and explain.js loaded; return the answers."""
    page = tmp_path / "run.html"
    page.write_text(
        '<!doctype html><meta charset="utf-8">'
        '<script src="' + (ROOT / "app" / "formulas.js").as_uri() + '"></script>'
        '<script src="' + (ROOT / "app" / "explain.js").as_uri() + '"></script>'
        "<pre id=out></pre><script>"
        "const cases = " + json.dumps(cases) + ";"
        "document.getElementById('out').textContent = JSON.stringify(cases.map(c => eval(c)));"
        "</script>",
        encoding="utf-8",
    )
    result = subprocess.run(
        [EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / 'edge'}",
         "--dump-dom", page.as_uri()],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    found = re.search(r"<pre id=\"out\">(.*?)</pre>", result.stdout, re.S)
    assert found, "The browser did not return the answers:\n" + result.stdout[:500]
    return json.loads(found.group(1))


needs_edge = pytest.mark.skipif(not EDGE, reason="No Edge, Chrome or Chromium found")


# --- (1) Ground pressure p = m * g / A -----------------------------------------

@needs_edge
def test_ground_pressure_by_hand(tmp_path):
    answers = run_js(tmp_path, [
        "groundPressurePa(200, 1.62, 0.06)",   # 200 * 1.62 / 0.06 = 5400 Pa
        "groundPressurePa(100, 9.81, 0.5)",    # 100 * 9.81 / 0.5  = 1962 Pa
        "groundPressurePa(0, 3.71, 0.1)",      # no mass, no pressure
    ])
    assert answers[0] == pytest.approx(5400)
    assert answers[1] == pytest.approx(1962)
    assert answers[2] == 0


@needs_edge
def test_ground_pressure_bad_inputs_give_null(tmp_path):
    answers = run_js(tmp_path, [
        "groundPressurePa(null, 9.81, 0.06)",  # mass box empty
        "groundPressurePa(200, 9.81, 0)",      # area 0 would divide by zero
        "groundPressurePa(200, 9.81, -1)",     # negative area
        "groundPressurePa(-5, 9.81, 0.06)",    # negative mass
    ])
    assert answers == [None, None, None, None]


@needs_edge
def test_ground_pressure_uses_config_gravity(tmp_path):
    # The page passes config.json's gravity; check every body against Python.
    g = CONFIG["gravity_m_s2"]
    answers = run_js(tmp_path, [f"groundPressurePa(200, {g[b]['value']}, 0.06)" for b in g])
    for body, p in zip(g, answers):
        assert p == pytest.approx(200 * g[body]["value"] / 0.06)


# --- (2) Thermal expansion dL = alpha * L * dT, in mm ----------------------------

@needs_edge
def test_expansion_by_hand(tmp_path):
    answers = run_js(tmp_path, [
        "expansionMm(2.26e-5, 2, 300)",   # 2.26e-5 * 2 m * 300 K = 0.01356 m = 13.56 mm
        "expansionMm(1e-5, 1, 1)",        # 1e-5 m = 0.01 mm
        "expansionMm(1.54e-5, 0, 300)",   # zero length, no growth
    ])
    assert answers[0] == pytest.approx(13.56)
    assert answers[1] == pytest.approx(0.01)
    assert answers[2] == 0


@needs_edge
def test_expansion_missing_swing_gives_null(tmp_path):
    answers = run_js(tmp_path, ["expansionMm(2.26e-5, 2, null)", "expansionMm(2.26e-5, null, 300)"])
    assert answers == [None, None]


@needs_edge
def test_expansion_for_every_site_and_material(tmp_path):
    # Every material in config.json times every site swing in thermal.json, plus the Moon.
    swings = [s["mean_swing"]["K"] for s in THERMAL["sites"].values()]
    swings.append(CONFIG["references"]["moon"]["thermal_swing_K"]["value"])
    pairs = [(m["alpha_per_K"], dt) for m in CONFIG["materials"].values() for dt in swings]
    answers = run_js(tmp_path, [f"expansionMm({a}, 2, {json.dumps(dt)})" for a, dt in pairs])
    for (alpha, dt), mm in zip(pairs, answers):
        if dt is None:
            assert mm is None
        else:
            assert mm == pytest.approx(alpha * 2 * dt * 1000)


# --- The coefficients in config.json match their source --------------------------

def nist_alpha(fit, T):
    """Slope of NIST's fit y = a + bT + cT^2 + dT^3 + eT^4 (y in units of 1e-5), as alpha in 1/K."""
    slope = fit["b"] + 2 * fit["c"] * T + 3 * fit["d"] * T ** 2 + 4 * fit["e"] * T ** 3
    return slope * 1e-5


@pytest.mark.parametrize("key", list(CONFIG["materials"]))
def test_alpha_matches_nist_fit(key):
    mat = CONFIG["materials"][key]
    fit = mat["nist_fit"]
    T = CONFIG["materials_note"]["temperature_K"]
    # The fit measures length change from 293 K, so it must be about 0 at 293 K.
    # This catches a mistyped coefficient.
    y = fit["a"] + fit["b"] * T + fit["c"] * T ** 2 + fit["d"] * T ** 3 + fit["e"] * T ** 4
    assert abs(y) < 0.5
    # alpha is stored to 3 significant figures, so allow 0.5% for rounding.
    assert mat["alpha_per_K"] == pytest.approx(nist_alpha(fit, T), rel=0.005)


@pytest.mark.parametrize("key", list(CONFIG["materials"]))
def test_every_material_has_a_listed_source(key):
    mat = CONFIG["materials"][key]
    assert mat["source_url"].startswith("https://")
    assert mat["source_url"] in SOURCES[mat["source_id"]]["pages"]


# --- Display, input limits and the plain-English sentences (explain.js) ---------

LIMITS = CONFIG["try_it_limits"]


def numbers_in(text):
    """Every number written in a sentence, e.g. '6.1 times' -> 6.1."""
    return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]


@needs_edge
def test_display_rounding(tmp_path):
    answers = run_js(tmp_path, ["shownKpa(5400)", "shownKpa(12366.67)", "shownKpa(324)",
                                "shownMm(13.56)", "shownMm(0.0133)"])
    assert answers == [5.4, 12.4, 0.3, 13.6, 0.0133]


@needs_edge
def test_input_limits(tmp_path):
    m, a, l = LIMITS["mass_kg"], LIMITS["area_m2"], LIMITS["length_m"]
    answers = run_js(tmp_path, [
        f"rangeMessage(200, {m['min']}, {m['max']}, 'kg')",          # fine
        f"rangeMessage({m['min']}, {m['min']}, {m['max']}, 'kg')",   # exactly on the limit is fine
        f"rangeMessage(0.5, {m['min']}, {m['max']}, 'kg')",          # too light
        f"rangeMessage(6000, {m['min']}, {m['max']}, 'kg')",         # too heavy
        f"rangeMessage(0.0001, {a['min']}, {a['max']}, 'm²')",       # contact area too small
        f"rangeMessage(25, {l['min']}, {l['max']}, 'm')",            # beam too long
        f"rangeMessage(null, {l['min']}, {l['max']}, 'm')",          # empty box
    ])
    assert answers[0] is None and answers[1] is None
    assert answers[2] == answers[3] == "Unrealistic: use 1 to 5000 kg."
    assert answers[4] == "Unrealistic: use 0.001 to 5 m²."
    assert answers[5] == "Unrealistic: use 0.1 to 20 m."
    assert answers[6] == "Enter a number."


@needs_edge
def test_pressure_sentence_for_the_example(tmp_path):
    # 200 kg on 0.06 m2: Earth 32.7, Moon 5.4, Mars 12.4 kPa as displayed.
    [text] = run_js(tmp_path, ["pressureSentence(32.7, 5.4, 12.4)"])
    assert text == ("On Earth this rover presses 32.7/5.4 = 6.1 times harder than on the Moon "
                    "and 32.7/12.4 = 2.6 times harder than on Mars, "
                    "so, other things equal, an Earth soil test overstates wheel sinkage.")


@needs_edge
def test_expansion_sentence_for_the_example(tmp_path):
    # 2 m aluminum beam: Moon 13.6 mm, atacama 1.01 mm, dryvalleys 0.0389 mm as displayed.
    [text, same, cold_missing, site_missing] = run_js(tmp_path, [
        "expansionSentence('atacama', 13.6, 1.01, 'dryvalleys', 0.0389)",
        "expansionSentence('dryvalleys', 13.6, 0.0389, 'dryvalleys', 0.0389)",  # picked site is the coldest
        "expansionSentence('atacama', 13.6, 1.01, 'nowhere', null)",            # coldest has no swing
        "expansionSentence('nowhere', 13.6, null, 'dryvalleys', 0.0389)",       # picked site has no swing
    ])
    assert text == ("On the Moon this beam grows 13.6 mm, vs 1.01 mm at atacama, "
                    "so atacama tests only 1.01/13.6 = 7.4% of the thermal cycling. "
                    "dryvalleys, the site with the lowest mean temperature, grows 0.0389 mm, "
                    "so it tests only 0.0389/13.6 = 0.3% of the lunar cycling.")
    assert same.endswith("dryvalleys is also the site with the lowest mean temperature.")
    assert same.count("0.0389/13.6") == 1
    assert cold_missing.endswith("has no measured swing, so it is not assessed.")
    assert site_missing.startswith("nowhere has no measured swing")
    assert "0.0389/13.6 = 0.3% of the lunar cycling" in site_missing


def coldest_site():
    """The site with the lowest mean temperature in thermal.json, worked out in Python."""
    temps = {s: v["mean_temperature"]["K"] for s, v in THERMAL["sites"].items()
             if v["mean_temperature"]["K"] is not None}
    return min(temps, key=temps.get)


@needs_edge
def test_pressure_sentence_numbers_come_from_displayed_values(tmp_path):
    # Many rovers inside the limits: every number in the sentence must be a
    # displayed kPa value or a ratio of two displayed values (1 decimal).
    g = {b: CONFIG["gravity_m_s2"][b]["value"] for b in ("earth", "moon", "mars")}
    cases = []
    for mass, area in [(1, 5), (1, 0.001), (200, 0.06), (900, 0.4), (5000, 0.001), (5000, 5)]:
        shown = [f"shownKpa(groundPressurePa({mass}, {g[b]}, {area}))" for b in g]
        cases.append("[" + ", ".join(shown) + ", pressureSentence(" + ", ".join(shown) + ")]")
    for earth, moon, mars, text in run_js(tmp_path, cases):
        if moon == 0:
            assert "too small to compare" in text
            continue
        allowed = [earth, moon, mars, round(earth / moon, 1), round(earth / mars, 1)]
        for n in numbers_in(text):
            assert any(abs(n - a) < 0.051 for a in allowed), f"{n} in '{text}' not from {allowed}"
        assert f"{earth}/{moon} = " in text and f"{earth}/{mars} = " in text


@needs_edge
def test_expansion_sentence_numbers_come_from_displayed_values(tmp_path):
    # Every material, every site, shortest and longest beam.
    lunar = CONFIG["references"]["moon"]["thermal_swing_K"]["value"]
    cold = coldest_site()
    cold_swing = THERMAL["sites"][cold]["mean_swing"]["K"]

    def cold_mm(mat, length):
        return f"shownMm(expansionMm({mat['alpha_per_K']}, {length}, {cold_swing}))"

    cases = []
    for mat in CONFIG["materials"].values():
        for length in (LIMITS["length_m"]["min"], 2, LIMITS["length_m"]["max"]):
            for site, s in THERMAL["sites"].items():
                swing = s["mean_swing"]["K"]
                moon = f"shownMm(expansionMm({mat['alpha_per_K']}, {length}, {lunar}))"
                here = "null" if swing is None else f"shownMm(expansionMm({mat['alpha_per_K']}, {length}, {swing}))"
                cases.append(f"[{moon}, {here}, {cold_mm(mat, length)}, "
                             f"expansionSentence('{site}', {moon}, {here}, '{cold}', {cold_mm(mat, length)})]")
    for moon, here, cold_shown, text in run_js(tmp_path, cases):
        allowed = [moon]
        if here is None:
            assert "not assessed" in text
        else:
            allowed += [here, round(100 * here / moon, 1)]
            assert f"grows {moon} mm, vs {here} mm" in text and f"{here}/{moon} = " in text
        allowed += [cold_shown, round(100 * cold_shown / moon, 1)]
        assert cold in text and "lowest mean temperature" in text
        for n in numbers_in(text):
            assert any(abs(n - a) < 0.051 for a in allowed), f"{n} in '{text}' not from {allowed}"


@needs_edge
def test_live_page_sentences_match_its_results(tmp_path):
    # Open the real page (it needs a server to read the JSON files) and check that
    # the sentences use exactly the values the page shows above them.
    import socket
    import sys
    import time
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                              cwd=ROOT / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_for_server(port)
        html = subprocess.run(
            [EDGE, "--headless", "--disable-gpu", NO_LIVE_TILES, f"--user-data-dir={tmp_path / 'edge'}",
             "--virtual-time-budget=8000", "--dump-dom", f"http://127.0.0.1:{port}/"],
            capture_output=True, text=True, encoding="utf-8", timeout=90).stdout
    finally:
        server.terminate()

    def block(element_id):
        found = re.search(rf'id="{element_id}"[^>]*>(.*?)</(ul|p)>', html, re.S)
        assert found, f"#{element_id} not found on the page"
        return found.group(1)

    kpa = [float(v) for v in re.findall(r'class="val">([\d.]+) kPa<', block("out-pressure"))]
    assert kpa == [32.7, 5.4, 12.4]          # starting example: 200 kg, 0.06 m2
    sentence = block("pressure-sentence")
    assert "32.7/5.4 = 6.1 times" in sentence and "32.7/12.4 = 2.6 times" in sentence

    sentence = block("pressure-sentence")
    assert "so, other things equal, an Earth soil test overstates wheel sinkage." in sentence

    # Each row reads "name: <span class="val">1.07 mm</span>"; collect name -> mm.
    rows = re.findall(r'<li><span>([^<:]+?)(?: \(reference swing\))?: </span><span class="val">([\d.]+) mm<',
                      block("out-expansion"))
    shown = {name: float(mm) for name, mm in rows}
    moon = shown["Moon"]
    assert moon == 13.6                      # 2 m aluminum beam, 300 K
    first_site = rows[1][0]                  # the site picked when the page opens
    here = shown[first_site]
    sentence = block("expansion-sentence")
    assert f"grows {moon} mm, vs {here} mm at {first_site}" in sentence
    assert f"{here}/{moon} = {round(100 * here / moon, 1)}%" in sentence
    cold = SHORT[coldest_site()]            # the page writes the site's name, not its key
    assert (f"{cold}, the site with the lowest mean temperature, grows {shown[cold]} mm, "
            f"so it tests only {shown[cold]}/{moon} = {round(100 * shown[cold] / moon, 1)}% "
            "of the lunar cycling.") in sentence
