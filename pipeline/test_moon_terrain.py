"""
Tests for moon_terrain.py. Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

import moon_terrain as mt
import terrain

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
OUT = json.loads((DATA / "moon_terrain.json").read_text(encoding="utf-8"))
CONFIG = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


# --- Same functions as the Earth side -------------------------------------------

def test_reuses_terrain_functions():
    # Not copies: the very same functions as pipeline/terrain.py.
    assert mt.slope_degrees is terrain.slope_degrees
    assert mt.roughness_detrended is terrain.roughness_detrended
    assert mt.summarise is terrain.summarise


# --- Block means --------------------------------------------------------------

def test_block_size_5m_to_30m():
    assert mt.block_size(5.0, 30.0) == 6


def test_block_mean_by_hand():
    z = np.array([[1.0, 3.0, 10.0, 10.0],
                  [5.0, 7.0, 10.0, 30.0]])
    # Left block: (1+3+5+7)/4 = 4. Right block: (10+10+10+30)/4 = 15.
    assert mt.block_mean(z, 2).tolist() == [[4.0, 15.0]]


def test_block_mean_drops_leftover_and_keeps_gaps():
    z = np.ones((5, 5))
    z[0, 0] = np.nan
    out = mt.block_mean(z, 2)
    assert out.shape == (2, 2)          # the 5th row and column do not fill a block
    assert np.isnan(out[0, 0])          # a block with a gap stays a gap, never filled
    assert out[1, 1] == 1.0


# --- Slope and roughness on a 30 m grid -----------------------------------------

def test_tilted_plane_slope_and_zero_roughness():
    # Heights rise 15 m per 30 m pixel along columns: slope = arctan(0.5) = 26.565 deg.
    rows, cols = np.mgrid[0:5, 0:5]
    z = 15.0 * cols
    slope = mt.slope_degrees(z, np.full(5, 30.0), 30.0)
    assert slope[2, 2] == pytest.approx(math.degrees(math.atan(0.5)))
    rough = mt.roughness_detrended(z, 3)
    assert rough[2, 2] == pytest.approx(0.0, abs=1e-9)   # a flat tilted plane has no roughness


def test_slope_matches_numpy_gradient():
    rng = np.random.default_rng(1)
    z = rng.normal(1000, 5, (5, 5))
    slope = mt.slope_degrees(z, np.full(5, 30.0), 30.0)
    d_rows, d_cols = np.gradient(z, 30.0)
    expected = np.degrees(np.arctan(np.hypot(d_rows, d_cols)))
    assert slope[1:-1, 1:-1] == pytest.approx(expected[1:-1, 1:-1])


def test_roughness_matches_numpy_lstsq():
    rng = np.random.default_rng(2)
    patch = rng.normal(1000, 2, (3, 3))
    rough = mt.roughness_detrended(patch, 3)
    y, x = np.mgrid[-1:2, -1:2]
    a = np.column_stack([np.ones(9), x.ravel(), y.ravel()])
    coef, *_ = np.linalg.lstsq(a, patch.ravel(), rcond=None)
    leftover = patch.ravel() - a @ coef
    assert rough[1, 1] == pytest.approx(np.sqrt(np.mean(leftover**2)))


# --- The written file ---------------------------------------------------------

def test_json_states_block_size_resolution_and_window():
    assert OUT["map"]["pixel_m"] == 5.0
    assert OUT["averaging"]["block_px"] == 6
    assert OUT["averaging"]["resolution_m"] == 30.0
    assert OUT["averaging"]["shape_rows_cols"] == [700, 700]   # 4200 / 6
    area = OUT["areas"]["whole_site"]
    assert area["resolution_m_ns_ew"] == [30.0, 30.0]
    for key in ("slope_deg", "roughness_m"):
        assert area[key]["window_px"] == 3
        assert area[key]["window_m_ns_ew"] == [90.0, 90.0]
        assert area[key]["pixels_used"] == 698 * 698           # edge pixels skipped


def test_json_has_requested_statistics():
    s = OUT["areas"]["whole_site"]["slope_deg"]
    for key in ("mean", "median", "p90"):
        assert isinstance(s[key], float)
    assert isinstance(OUT["areas"]["whole_site"]["roughness_m"]["median"], float)
    assert OUT["original_5m_slope"]["resolution_m"] == 5.0
    assert isinstance(OUT["original_5m_slope"]["median_deg"], float)


@pytest.mark.parametrize("words", ["1.5 to 2.5 degrees", "about 90 percent"])
def test_caveats_are_written(words):
    assert any(words in c for c in OUT["caveats"])


def test_caveat_numbers_have_a_listed_source():
    url = OUT["caveats_source"]["url"]
    assert url == "https://pgda.gsfc.nasa.gov/products/78"
    assert url == SOURCES["lola_5mpp_site23"]["product_page_url"]
    # Both caveats name the page they come from.
    assert sum(url in c for c in OUT["caveats"]) == 2


def test_source_is_listed():
    assert OUT["source_id"] == "lola_5mpp_site23"
    assert "moon_terrain.json" in SOURCES["lola_5mpp_site23"]["used_by"]


# --- config.json ----------------------------------------------------------------

def test_config_moon_terrain_matches_json():
    moon = CONFIG["references"]["moon"]
    area = OUT["areas"]["whole_site"]
    assert moon["slope_deg"]["value"] == area["slope_deg"]["median"]
    assert moon["slope_deg"]["mean"] == area["slope_deg"]["mean"]
    assert moon["slope_deg"]["p90"] == area["slope_deg"]["p90"]
    assert moon["slope_deg"]["original_5m_median"] == OUT["original_5m_slope"]["median_deg"]
    assert moon["roughness_m"]["value"] == area["roughness_m"]["median"]
    for key in ("slope_deg", "roughness_m"):
        assert moon[key]["resolution_m"] == OUT["averaging"]["resolution_m"]
        assert moon[key]["window_m"] == area[key]["window_m_ns_ew"][0]
        assert moon[key]["source_id"] in SOURCES
        assert moon[key]["source_url"] in SOURCES[moon[key]["source_id"]]["file_urls"]


def test_no_terrain_tolerance_invented():
    # The Moon terrain tau comes from a rule (Earth spread or the Moon's own value), never a typed-in number.
    assert CONFIG["tolerance"]["moon"]["slope_deg"]["rule"] == "stdev_of_site_values"
    assert CONFIG["tolerance"]["moon"]["roughness_m"]["rule"] == "equal_to_reference"
    for key in ("slope_deg", "roughness_m"):
        assert "value" not in CONFIG["tolerance"]["moon"][key]
        # Mars has no terrain reference, so nothing to score against.
        assert CONFIG["references"]["mars"][key]["value"] is None


# --- Rebuild from the raw files, if they are on this computer -----------------

@pytest.mark.skipif(not (mt.SURF_PATH.exists() and mt.SLP_PATH.exists()),
                    reason="raw LOLA files not in data/raw/moon")
def test_raw_files_rebuild_the_committed_numbers():
    z5, info = mt.read_heights(mt.SURF_PATH)        # also checks the grid is in meters
    assert info["pixel_m"] == 5.0
    z30 = mt.block_mean(z5, 6)
    slope = mt.slope_degrees(z30, np.full(z30.shape[0], 30.0), 30.0)
    rough = mt.roughness_detrended(z30, 3)
    stats = mt.summarise(slope, rough, slice(None), slice(None), 30.0, 30.0, 3)
    assert stats["slope_deg"] == OUT["areas"]["whole_site"]["slope_deg"]
    assert stats["roughness_m"] == OUT["areas"]["whole_site"]["roughness_m"]
