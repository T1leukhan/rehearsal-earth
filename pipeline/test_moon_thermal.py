"""
Tests for moon_thermal.py. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)
"""

import json
from pathlib import Path

import numpy as np
import pytest

import moon_thermal as mt

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
OUT = json.loads((DATA / "moon_thermal.json").read_text(encoding="utf-8"))
CONFIG = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


# --- Map layout and scale -----------------------------------------------------

def test_row_latitudes():
    # Each row is 1/4 degree tall, starting at 90 N.
    assert mt.row_latitude(0) == 89.875
    assert mt.row_latitude(359) == 0.125     # just north of the equator
    assert mt.row_latitude(360) == -0.125    # just south of the equator
    assert mt.row_latitude(719) == -89.875


def test_band_rows_are_minus5_to_plus5():
    rows = mt.band_rows(-5, 5)
    assert rows == list(range(340, 380))     # 10 degrees x 4 rows per degree = 40 rows
    assert mt.row_latitude(rows[0]) == 4.875 and mt.row_latitude(rows[-1]) == -4.875


def test_scale_and_nodata():
    raw = np.array([[17058, -32768, 0, 1]], dtype="<i2")
    kelvin = mt.to_kelvin(raw)
    assert kelvin[0, 0] == pytest.approx(341.16)   # 17058 x 0.02
    assert np.isnan(kelvin[0, 1])                  # -32768 means no data
    assert kelvin[0, 2] == 0
    assert kelvin[0, 3] == pytest.approx(0.02)


# --- Statistics ---------------------------------------------------------------

def test_stats_by_hand():
    # 3 values with data out of 4: 100, 200, 300 K.
    # Linear percentiles: p5 = 100 + 0.1 x 100 = 110, p95 = 200 + 0.9 x 100 = 290.
    s = mt.band_stats(np.array([[100.0, 200.0, np.nan, 300.0]]))
    assert s["pixels_total"] == 4 and s["pixels_with_data"] == 3
    assert s["share_with_data_percent"] == 75.0
    assert s["median_K"] == 200.0
    assert s["p5_K"] == pytest.approx(110.0)
    assert s["p95_K"] == pytest.approx(290.0)


def test_no_data_gives_null_not_a_guess():
    s = mt.band_stats(np.full((2, 3), np.nan))
    assert s["share_with_data_percent"] == 0.0
    assert s["median_K"] is None and s["p5_K"] is None and s["p95_K"] is None
    assert mt.observed_range({"p95_K": None}, {"p5_K": 94.0}) is None


def test_observed_range_is_day_p95_minus_night_p5():
    assert mt.observed_range({"p95_K": 355.78}, {"p5_K": 94.0}) == 261.78


# --- The written file ---------------------------------------------------------

def test_json_has_window_resolution_and_source():
    assert OUT["resolution_m"] == mt.PIXEL_M
    assert OUT["band"]["lat_min_deg"] == -5 and OUT["band"]["lat_max_deg"] == 5
    # 10 degrees of a 1737.4 km radius circle = 303,233.5 m.
    assert OUT["band"]["window_m_ns"] == pytest.approx(10 * np.pi * 1737400 / 180, abs=0.1)
    assert OUT["source_id"] in SOURCES
    assert "moon_thermal.json" in SOURCES[OUT["source_id"]]["used_by"]


def test_observed_range_is_labelled_and_matches():
    r = OUT["observed_range_K"]
    assert r["label"] == "observed range across both maps, not a daily swing"
    assert r["value"] == pytest.approx(OUT["day"]["p95_K"] - OUT["night"]["p5_K"])


def test_no_daily_swing_in_the_file():
    # A daily swing must not be computed: no key may be called "swing".
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    assert not [k for k in keys(OUT) if "swing" in k.lower()]


@pytest.mark.parametrize("words", ["Local-time drift", "Different months", "7.6 km", "Empty pixels"])
def test_caveats_are_written(words):
    assert any(words in c for c in OUT["caveats"])


def test_missing_list_matches_nulls():
    nulls = [f"{m}.{k}" for m in ("day", "night") for k in ("median_K", "p5_K", "p95_K") if OUT[m][k] is None]
    assert OUT["missing"] == nulls


# --- config.json and sources.json ---------------------------------------------

def test_config_keeps_300_K_slide_figure():
    swing = CONFIG["references"]["moon"]["thermal_swing_K"]
    assert swing["value"] == 300
    assert swing["source_id"] == "msfc_lunar_environment_2008"


def test_config_diviner_references_match_json():
    ref = CONFIG["references"]["moon"]["diviner_equator_K"]
    for m in ("day", "night"):
        assert ref[m]["median"] == OUT[m]["median_K"]
        assert ref[m]["p5"] == OUT[m]["p5_K"]
        assert ref[m]["p95"] == OUT[m]["p95_K"]
        assert ref[m]["share_with_data_percent"] == OUT[m]["share_with_data_percent"]
        assert ref[m]["local_time_h"] == OUT[m]["local_time_h"]
    assert ref["observed_range"] == {"value": OUT["observed_range_K"]["value"],
                                     "label": OUT["observed_range_K"]["label"]}
    assert ref["resolution_m"] == OUT["resolution_m"]
    assert ref["window_m_ns"] == OUT["band"]["window_m_ns"]
    assert ref["source_id"] == OUT["source_id"]
    assert ref["source_url"] == SOURCES[ref["source_id"]]["doi_url"]


@pytest.mark.parametrize("key", ["lro_diviner_gdr_l3", "lola_5mpp_site23"])
def test_moon_sources_listed_with_urls(key):
    s = SOURCES[key]
    assert s["file_urls"] and all(u.startswith("https://") for u in s["file_urls"])
    assert s["folder_url"].startswith("https://")
    for url in s["file_urls"]:
        assert url.startswith(s["folder_url"])


def test_unverified_lola_doi_is_null():
    assert SOURCES["lola_5mpp_site23"]["doi"] is None


# --- Rebuild from the raw files, if they are on this computer -----------------

RAW = [mt.IN_DIR / m["file"] for m in mt.MAPS.values()]


@pytest.mark.skipif(not all(p.exists() for p in RAW), reason="raw Diviner maps not in data/raw/moon")
def test_raw_files_rebuild_the_committed_numbers():
    rows = mt.band_rows(mt.LAT_MIN, mt.LAT_MAX)
    for name, info in mt.MAPS.items():
        stats = mt.band_stats(mt.to_kelvin(mt.read_map(mt.IN_DIR / info["file"]))[rows, :])
        for key, value in stats.items():
            assert OUT[name][key] == value, f"{name}.{key}"
