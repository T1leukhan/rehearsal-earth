"""
Tests for terrain.py (three Earth sites). Run from the project folder:
    .venv\\Scripts\\python.exe -m pytest pipeline -v   (Windows)
    .venv/bin/python -m pytest pipeline -v              (macOS/Linux)
"""

import json
import math
import re
from pathlib import Path

import pytest

import terrain

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"
TERRAIN = json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))
THERMAL = json.loads((DATA / "thermal.json").read_text(encoding="utf-8"))
SOURCES = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
SITES = TERRAIN["sites"]


def tile_box(name):
    """Bounds of an SRTM tile from its name. S21W069 = 21 S to 20 S, 69 W to 68 W.

    The name gives the south-west corner; each tile is 1 x 1 degree.
    """
    m = re.match(r"([NS])(\d\d)([EW])(\d\d\d)", name)
    south = int(m.group(2)) * (1 if m.group(1) == "N" else -1)
    west = int(m.group(4)) * (1 if m.group(3) == "E" else -1)
    return south, south + 1, west, west + 1


# --- Which sites, which squares ------------------------------------------------

def test_three_sites_with_the_requested_centres():
    centres = {s: v["square_centre_lat_lon_deg"] for s, v in SITES.items()}
    assert centres == {"atacama": [-23.5, -69.5], "altiplano": [-20.5, -68.5], "maunakea": [19.8, -155.5]}


def test_every_other_site_is_listed_as_not_assessed():
    others = set(THERMAL["sites"]) - set(SITES)
    assert {x["site"] for x in TERRAIN["not_assessed"]} == others == {"haughton", "dryvalleys"}


def test_srtm_coverage_matches_its_listed_source():
    cov = TERRAIN["srtm_coverage"]
    src = SOURCES["srtmgl1_v3"]
    assert [cov["north_deg"], cov["south_deg"]] == [src["coverage_lat_deg"]["north"], src["coverage_lat_deg"]["south"]]
    assert cov["source_url"] == src["coverage_source"]


def test_coverage_reasons():
    assert terrain.coverage_reason(75.4) == "outside SRTM coverage: latitude 75.4° is north of 60° N, SRTM's northern limit"
    assert terrain.coverage_reason(-77.5) == "outside SRTM coverage: latitude -77.5° is south of 56° S, SRTM's southern limit"
    assert terrain.coverage_reason(-20.5) is None          # Altiplano: covered
    assert terrain.coverage_reason(59.9) is None
    for gap in TERRAIN["not_assessed"]:
        assert gap["reason"] == terrain.coverage_reason(gap["latitude_deg"])
        assert gap["latitude_deg"] == THERMAL["sites"][gap["site"]]["latitude"]


@pytest.mark.parametrize("site", ["atacama", "altiplano", "maunakea"])
def test_square_centre_inside_its_tile_by_name_and_footprint(site):
    s = SITES[site]
    lat, lon = s["square_centre_lat_lon_deg"]
    south, north, west, east = tile_box(s["tile"]["file"])
    assert south < lat < north and west < lon < east              # from the tile name
    b = s["tile"]["bounds_deg"]
    assert b["south"] < lat < b["north"] and b["west"] < lon < b["east"]   # from the file itself
    assert s["square_fits_in_tile"] is True


@pytest.mark.parametrize("site", ["atacama", "altiplano", "maunakea"])
def test_statistics_and_pixel_counts(site):
    sq = SITES[site]["areas"]["square_10km"]
    rows, cols = sq["size_px_rows_cols"]
    for key in ("mean", "median", "p90"):
        assert isinstance(sq["slope_deg"][key], float)
    assert isinstance(sq["roughness_m"]["median"], float)
    assert 0 < sq["slope_deg"]["pixels_used"] <= rows * cols
    assert 0 < sq["roughness_m"]["pixels_used"] <= rows * cols
    # Each side is close to 10 km.
    assert all(abs(m - 10000) < 50 for m in sq["size_m_ns_ew"])


def test_atacama_numbers_unchanged():
    # The values committed before terrain.py handled three sites.
    sq = SITES["atacama"]["areas"]["square_10km"]
    assert (sq["slope_deg"]["mean"], sq["slope_deg"]["median"], sq["slope_deg"]["p90"]) == (7.67, 5.37, 17.78)
    assert sq["roughness_m"]["median"] == 0.71
    assert sq["slope_deg"]["pixels_used"] == 114019


# --- Offset between the terrain square and the thermal point ---------------------

def test_distance_by_hand():
    # Half a degree of latitude = 0.5 * pi / 180 * R.
    assert terrain.distance_m(-20.0, -68.0, -20.5, -68.0) == pytest.approx(
        0.5 * math.pi / 180 * terrain.EARTH_RADIUS_M)
    assert terrain.distance_m(10.0, 20.0, 10.0, 20.0) == 0


def test_thermal_points_are_unchanged():
    for site, s in SITES.items():
        t = THERMAL["sites"][site]
        assert s["thermal_point_lat_lon_deg"] == [t["latitude"], t["longitude"]]
    assert SITES["altiplano"]["thermal_point_lat_lon_deg"] == [-20.0, -68.0]


def test_altiplano_offset_and_reason():
    a = SITES["altiplano"]
    assert a["offset_deg_lat_lon"] == [-0.5, -0.5]
    o = a["offset_m"]
    assert o["north_south"] == round(0.5 * math.pi / 180 * terrain.EARTH_RADIUS_M)
    assert o["east_west_at_square"] < o["north_south"] < o["straight_line"]
    assert o["straight_line"] == pytest.approx(math.hypot(o["north_south"], o["east_west_at_square"]), rel=0.01)
    assert "four SRTM tiles" in a["why_moved"]
    # The thermal point itself is a tile corner, so a square around it would not fit.
    assert not terrain.square_fits(-20.0, -68.0, 10000, a["tile"]["bounds_deg"])


@pytest.mark.parametrize("site", ["atacama", "maunakea"])
def test_other_squares_sit_on_the_thermal_point(site):
    assert SITES[site]["offset_m"] == {"north_south": 0, "east_west_at_square": 0, "straight_line": 0}
    assert "why_moved" not in SITES[site]


# --- Sources ----------------------------------------------------------------------

def test_every_tile_is_a_listed_source():
    urls = SOURCES["srtmgl1_v3"]["file_urls"]
    for s in SITES.values():
        name = s["tile"]["file"].split(" ")[0]
        assert any(u.endswith("/" + name) for u in urls), name
