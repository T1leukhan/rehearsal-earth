"""
terrain.py - Slope and roughness for the Earth sites, one SRTM tile each.

Input:   data/raw/S24W070.SRTMGL1.hgt.zip   (SRTMGL1 v3, Atacama)
         data/raw/S21W069.SRTMGL1.hgt.zip   (Altiplano)
         data/raw/N19W156.SRTMGL1.hgt.zip   (Mauna Kea)
         data/earth_points.csv              (each site's thermal point)
Sources: app/data/sources.json              (must list "srtmgl1_v3")
Output:  app/data/terrain.json

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\terrain.py     (Windows)
    .venv/bin/python pipeline/terrain.py               (macOS/Linux)

What it computes:
  * Slope (degrees) at every pixel, from its 4 neighbours (north, south,
    east, west). This is called the "central difference" method.
  * Roughness (meters): in a small square window of about 100 m, fit the
    best flat tilted plane through the heights, subtract it, and take the
    standard deviation of what is left. So a steady slope is NOT roughness;
    only bumps and dips are.
Both are summarised, for each site, for (a) the whole tile and (b) a
10 km x 10 km square centred on the point in SITES below. Edge pixels of
the tile are skipped, because they do not have neighbours on all sides.
"""

import csv
import json
import math
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import rowcol

# --- Settings -------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
POINTS_PATH = PROJECT_ROOT / "data" / "earth_points.csv"
SOURCES_PATH = PROJECT_ROOT / "app" / "data" / "sources.json"
OUT_PATH = PROJECT_ROOT / "app" / "data" / "terrain.json"
SOURCE_ID = "srtmgl1_v3"  # key of this dataset in sources.json

# We treat Earth as a sphere with this mean radius (IUGG value, meters).
# It turns degrees into meters. The error from ignoring Earth's slight
# flattening is well under 1% here.
EARTH_RADIUS_M = 6371008.8

# Roughness window: we want a square about this many meters wide.
ROUGHNESS_TARGET_M = 100.0

# Side length of each study square (meters).
SQUARE_SIDE_M = 10000.0

# One tile and one square per site. The keys are the site names used in
# earth_points.csv and thermal.json, so score.py can match them by name.
# The thermal point stays where earth_points.csv has it; the terrain square
# may sit elsewhere so that it fits inside one SRTM tile.
SITES = {
    "atacama": {
        "tile_zip": "S24W070.SRTMGL1.hgt.zip",
        "square_centre_lat_lon_deg": [-23.5, -69.5],
    },
    "altiplano": {
        "tile_zip": "S21W069.SRTMGL1.hgt.zip",
        "square_centre_lat_lon_deg": [-20.5, -68.5],
        "why_moved": "The thermal point -20.0, -68.0 is the corner where four SRTM tiles meet "
                     "(S20W068, S21W068, S20W069, S21W069), so a 10 km square around it would need "
                     "all four. -20.5, -68.5 is the centre of tile S21W069, so the whole square "
                     "fits inside that one tile.",
    },
    "maunakea": {
        "tile_zip": "N19W156.SRTMGL1.hgt.zip",
        "square_centre_lat_lon_deg": [19.8, -155.5],
    },
}

# SRTM only covers land between these latitudes (NASA CMR collection record
# C2763266360-LPCLOUD: bounding rectangle 60 N to 56 S, and its abstract says
# "all land between 60° N and 56° S latitude"; read on 2026-11-14).
SRTM_NORTH_DEG = 60.0
SRTM_SOUTH_DEG = -56.0
SRTM_COVERAGE_URL = "https://cmr.earthdata.nasa.gov/search/concepts/C2763266360-LPCLOUD.html"

# Sites in earth_points.csv that cannot have SRTM terrain numbers.
# The reason is written from the latitude in main(), not typed here.
NOT_ASSESSED = ["haughton", "dryvalleys"]


def coverage_reason(lat):
    """Why a site at this latitude has no SRTM terrain, or None if SRTM covers it."""
    if lat > SRTM_NORTH_DEG:
        return f"outside SRTM coverage: latitude {lat}° is north of {SRTM_NORTH_DEG:g}° N, SRTM's northern limit"
    if lat < SRTM_SOUTH_DEG:
        return f"outside SRTM coverage: latitude {lat}° is south of {-SRTM_SOUTH_DEG:g}° S, SRTM's southern limit"
    return None


# --- Step 1: read the heights ---------------------------------------------

def read_tile(zip_path):
    """Read one tile. Returns a dict with the heights and facts about the grid."""
    # Find the name of the .hgt file inside the zip (e.g. S24W070.hgt).
    inner_name = zipfile.ZipFile(zip_path).namelist()[0]

    # "/vsizip/" lets rasterio read a file inside a zip without unzipping it.
    with rasterio.open(f"/vsizip/{zip_path.as_posix()}/{inner_name}") as src:
        z = src.read(1).astype(np.float64)  # whole numbers -> decimals
        nodata = src.nodata
        pixel_x_deg, pixel_y_deg = src.res  # pixel width and height, in degrees
        bounds = src.bounds
        transform = src.transform  # links row/column numbers to lon/lat

    # Mark missing pixels as NaN ("not a number") so they are never used.
    missing = 0
    if nodata is not None:
        is_missing = z == nodata
        missing = int(is_missing.sum())
        z[is_missing] = np.nan

    # Latitude at the centre of each row (row 0 is the north edge).
    # transform.f = latitude of the top edge, transform.e = change per row.
    row_lats = transform.f + (np.arange(z.shape[0]) + 0.5) * transform.e

    return {
        "z": z, "row_lats": row_lats, "px_deg": pixel_x_deg, "py_deg": pixel_y_deg,
        "bounds": bounds, "transform": transform, "missing": missing,
        "inner_name": inner_name,
    }


# --- Step 2: pixel size in meters -----------------------------------------

def pixel_size_m(pixel_x_deg, pixel_y_deg, row_lats):
    """Turn the pixel size from degrees into meters.

    North-south: 1 degree of latitude = (pi / 180) * R meters, everywhere.
    East-west:   1 degree of longitude shrinks toward the poles, so we
                 multiply by cos(latitude). This is different for each row.
    """
    meters_per_degree = math.pi / 180 * EARTH_RADIUS_M
    dy = pixel_y_deg * meters_per_degree                                 # one number
    dx = pixel_x_deg * meters_per_degree * np.cos(np.radians(row_lats))  # one per row
    return dx, dy


# --- Step 3: slope ---------------------------------------------------------

def slope_degrees(z, dx, dy):
    """Slope at every pixel, using its 4 neighbours.

    east-west rise per meter   = (east height - west height)   / (2 * dx)
    north-south rise per meter = (north height - south height) / (2 * dy)
    slope = arctan( sqrt(ew^2 + ns^2) ), turned into degrees.

    The result has the same shape as z. Edge pixels are NaN (no neighbours).
    """
    east = z[1:-1, 2:]
    west = z[1:-1, :-2]
    north = z[:-2, 1:-1]
    south = z[2:, 1:-1]

    dx_inner = dx[1:-1, np.newaxis]  # one dx per row, lined up with the rows

    rise_ew = (east - west) / (2 * dx_inner)
    rise_ns = (north - south) / (2 * dy)

    slope = np.full(z.shape, np.nan)
    slope[1:-1, 1:-1] = np.degrees(np.arctan(np.sqrt(rise_ew**2 + rise_ns**2)))
    return slope


# --- Step 4: roughness (tilt removed) -------------------------------------

def window_pixels(target_m, pixel_m):
    """Odd window width (in pixels) closest to target_m. Odd = it has a centre pixel."""
    n = 2 * round((target_m / pixel_m - 1) / 2) + 1
    return max(n, 3)


def roughness_detrended(z, n):
    """Roughness in every n x n window, after removing the best-fit plane.

    Inside a window, give each pixel coordinates x (column offset) and
    y (row offset), both running from -half to +half. The best plane is
        height = a + b*x + c*y
    Because x and y are centred, the least-squares answer is simple:
        a = mean height,  b = sum(x*z) / sum(x^2),  c = sum(y*z) / sum(y^2)
    The leftover ("residual") sum of squares is then
        RSS = sum(z^2) - sum(z)^2/N - sum(x*z)^2/sum(x^2) - sum(y*z)^2/sum(y^2)
    and roughness = sqrt(RSS / N), with N = n*n pixels in the window.

    We get those sums for every window at once by adding up shifted
    copies of the grid. The result has the same shape as z; pixels too
    close to the edge for a full window are NaN.
    """
    half = n // 2
    rows, cols = z.shape
    out_rows, out_cols = rows - 2 * half, cols - 2 * half

    sum_z = np.zeros((out_rows, out_cols))
    sum_zz = np.zeros((out_rows, out_cols))
    sum_xz = np.zeros((out_rows, out_cols))
    sum_yz = np.zeros((out_rows, out_cols))
    for i in range(n):
        y = i - half  # row offset from the window centre
        for j in range(n):
            x = j - half  # column offset from the window centre
            piece = z[i:i + out_rows, j:j + out_cols]
            sum_z += piece
            sum_zz += piece * piece
            sum_xz += x * piece
            sum_yz += y * piece

    count = n * n
    # sum of x^2 over the window = n * (sum of k^2 for k = -half..half)
    sum_xx = n * sum(k * k for k in range(-half, half + 1))
    sum_yy = sum_xx  # square window, so the same

    rss = sum_zz - sum_z**2 / count - sum_xz**2 / sum_xx - sum_yz**2 / sum_yy
    rss = np.clip(rss, 0, None)  # tiny negatives from rounding -> 0

    rough = np.full(z.shape, np.nan)
    rough[half:rows - half, half:cols - half] = np.sqrt(rss / count)
    return rough


# --- Step 5: the 10 km square ---------------------------------------------

def square_window(tile, dx, dy, lat, lon):
    """Row and column ranges of the square, centred on latitude lat, longitude lon.

    We use an odd number of pixels on each side so the centre point sits
    in the middle of one pixel.
    """
    centre_row, centre_col = rowcol(tile["transform"], lon, lat)
    dx_c = float(dx[centre_row])
    half_rows = round((SQUARE_SIDE_M / dy - 1) / 2)
    half_cols = round((SQUARE_SIDE_M / dx_c - 1) / 2)

    rows = slice(centre_row - half_rows, centre_row + half_rows + 1)
    cols = slice(centre_col - half_cols, centre_col + half_cols + 1)

    # Stop if the square does not fit inside the tile.
    n_rows, n_cols = tile["z"].shape
    if rows.start < 0 or cols.start < 0 or rows.stop > n_rows or cols.stop > n_cols:
        raise SystemExit("The 10 km square does not fit inside this tile.")

    return {
        "centre_row": centre_row, "centre_col": centre_col, "dx_centre": dx_c,
        "rows": rows, "cols": cols,
        "size_px": [2 * half_rows + 1, 2 * half_cols + 1],
        "size_m": [round((2 * half_rows + 1) * dy, 1), round((2 * half_cols + 1) * dx_c, 1)],
    }


# --- Step 6: statistics ----------------------------------------------------

def summarise(slope, rough, rows, cols, dy, dx_ew, n):
    """Slope and roughness statistics for one area (rows x cols).

    NaN-aware: missing pixels are left out, never filled in.
    dx_ew is the east-west pixel size to report (one number) for this area.
    """
    s = slope[rows, cols]
    r = rough[rows, cols]
    return {
        "resolution_m_ns_ew": [round(dy, 2), round(dx_ew, 2)],
        "slope_deg": {
            "mean": round(float(np.nanmean(s)), 2),
            "median": round(float(np.nanmedian(s)), 2),
            "p90": round(float(np.nanpercentile(s, 90)), 2),
            "window_px": 3,
            "window_m_ns_ew": [round(3 * dy, 1), round(3 * dx_ew, 1)],
            "pixels_used": int(np.isfinite(s).sum()),
        },
        "roughness_m": {
            "median": round(float(np.nanmedian(r)), 2),
            "window_px": n,
            "window_m_ns_ew": [round(n * dy, 1), round(n * dx_ew, 1)],
            "pixels_used": int(np.isfinite(r).sum()),
        },
    }


# --- Step 7: planned squares away from the thermal point -------------------

def distance_m(lat1, lon1, lat2, lon2):
    """Distance along the Earth's surface between two points (sphere, great circle).

    Uses the haversine formula, which stays accurate for short distances.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def square_fits(centre_lat, centre_lon, side_m, bounds):
    """True if a side_m square centred on the point lies inside the tile bounds."""
    half_lat = side_m / 2 / (math.pi / 180 * EARTH_RADIUS_M)
    half_lon = half_lat / math.cos(math.radians(centre_lat))
    return (bounds["south"] < centre_lat - half_lat and centre_lat + half_lat < bounds["north"]
            and bounds["west"] < centre_lon - half_lon and centre_lon + half_lon < bounds["east"])


def offset_from_thermal(thermal_point, square_centre):
    """How far the terrain square's centre is from the thermal point, worked out here."""
    (t_lat, t_lon), (s_lat, s_lon) = thermal_point, square_centre
    return {
        "offset_deg_lat_lon": [round(s_lat - t_lat, 4), round(s_lon - t_lon, 4)],
        "offset_m": {
            "north_south": round(distance_m(t_lat, t_lon, s_lat, t_lon)),
            "east_west_at_square": round(distance_m(s_lat, t_lon, s_lat, s_lon)),
            "straight_line": round(distance_m(t_lat, t_lon, s_lat, s_lon)),
        },
    }


def read_thermal_points():
    """Each site's thermal point from earth_points.csv, as {site: [lat, lon]}."""
    points = {}
    with open(POINTS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            points[row["ID"]] = [float(row["Latitude"]), float(row["Longitude"])]
    return points


# --- Step 8: hand-check ----------------------------------------------------

def print_hand_check(z, row_lats, dx, dy, slope, r, c):
    """Print a 3x3 patch and work out the centre slope step by step."""
    patch = z[r - 1:r + 2, c - 1:c + 2]
    print("\n=== Slope hand-check ===")
    print(f"Centre pixel: row {r}, column {c}, latitude {row_lats[r]:.5f}")
    print("3 x 3 patch of heights (m), north at the top, east on the right:")
    for line in patch:
        print("   " + "  ".join(f"{v:6.0f}" for v in line))

    north, south = patch[0, 1], patch[2, 1]
    west, east = patch[1, 0], patch[1, 2]
    dx_r = dx[r]

    rise_ew = (east - west) / (2 * dx_r)
    rise_ns = (north - south) / (2 * dy)
    steep = math.sqrt(rise_ew**2 + rise_ns**2)
    angle = math.degrees(math.atan(steep))

    print(f"\nPixel size: dy = {dy:.3f} m (north-south), dx = {dx_r:.3f} m (east-west at this latitude)")
    print(f"1) east-west rise   = (east - west) / (2*dx) = ({east:.0f} - {west:.0f}) / (2*{dx_r:.3f}) = {rise_ew:.5f}")
    print(f"2) north-south rise = (north - south) / (2*dy) = ({north:.0f} - {south:.0f}) / (2*{dy:.3f}) = {rise_ns:.5f}")
    print(f"3) steepness = sqrt({rise_ew:.5f}^2 + {rise_ns:.5f}^2) = {steep:.5f}")
    print(f"4) slope = arctan({steep:.5f}) = {angle:.3f} degrees")
    print(f"Script's value for this pixel: {slope[r, c]:.3f} degrees")


# --- Main -------------------------------------------------------------------

def site_terrain(site, plan, thermal_point):
    """Slope and roughness for one site: its whole tile and its 10 km square.

    Returns (result for terrain.json, things needed for the hand-check).
    """
    zip_path = RAW_DIR / plan["tile_zip"]
    tile = read_tile(zip_path)
    z, row_lats = tile["z"], tile["row_lats"]
    dx, dy = pixel_size_m(tile["px_deg"], tile["py_deg"], row_lats)

    slope = slope_degrees(z, dx, dy)

    mean_pixel_m = (dy + float(dx.mean())) / 2
    n = window_pixels(ROUGHNESS_TARGET_M, mean_pixel_m)
    rough = roughness_detrended(z, n)

    lat, lon = plan["square_centre_lat_lon_deg"]
    sq = square_window(tile, dx, dy, lat, lon)
    b = tile["bounds"]
    bounds = {"west": round(b.left, 6), "east": round(b.right, 6),
              "south": round(b.bottom, 6), "north": round(b.top, 6)}
    everything = slice(None)  # ":" = all rows / all columns

    result = {
        "tile": {
            "file": f"{zip_path.name} ({tile['inner_name']} inside)",
            "bounds_deg": bounds,
            "shape_rows_cols": list(z.shape),
            "pixel_deg": tile["px_deg"],
            "missing_pixels": tile["missing"],
        },
        "thermal_point_lat_lon_deg": thermal_point,
        "square_centre_lat_lon_deg": [lat, lon],
        **offset_from_thermal(thermal_point, [lat, lon]),
        "square_fits_in_tile": square_fits(lat, lon, SQUARE_SIDE_M, bounds),
        "areas": {
            "whole_tile": {
                "description": "whole 1 x 1 degree tile, edge pixels skipped",
                **summarise(slope, rough, everything, everything, dy, float(dx.mean()), n),
                "resolution_note": "east-west pixel size is the tile average; "
                                   f"it ranges {dx.min():.2f}-{dx.max():.2f} m",
            },
            "square_10km": {
                "description": "square centred on square_centre_lat_lon_deg",
                "centre_lat_lon_deg": [lat, lon],
                "size_px_rows_cols": sq["size_px"],
                "size_m_ns_ew": sq["size_m"],
                **summarise(slope, rough, sq["rows"], sq["cols"], dy, sq["dx_centre"], n),
            },
        },
    }
    if "why_moved" in plan:
        result["why_moved"] = plan["why_moved"]
    check = (z, row_lats, dx, dy, slope, sq["centre_row"], sq["centre_col"])
    return result, check


def main():
    # Rule: every number must trace to a dataset listed in sources.json.
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if SOURCE_ID not in sources:
        raise SystemExit(f"'{SOURCE_ID}' is missing from {SOURCES_PATH}. Add it first.")

    thermal_points = read_thermal_points()

    sites = {}
    for site, plan in SITES.items():
        print(f"\n##### {site}: {plan['tile_zip']} #####")
        sites[site], check = site_terrain(site, plan, thermal_points[site])
        sq = sites[site]["areas"]["square_10km"]
        print(f"10 km square at {sq['centre_lat_lon_deg']}: {sq['size_px_rows_cols']} px, "
              f"slope mean {sq['slope_deg']['mean']} / median {sq['slope_deg']['median']} / "
              f"p90 {sq['slope_deg']['p90']} deg, roughness median {sq['roughness_m']['median']} m, "
              f"{sq['slope_deg']['pixels_used']} pixels used")
        # Hand-check the centre pixel of this site's 10 km square.
        print_hand_check(*check)

    result = {
        "source_id": SOURCE_ID,
        "earth_model": f"sphere, radius {EARTH_RADIUS_M} m",
        "square_side_m": SQUARE_SIDE_M,
        "methods": {
            "slope": "central difference: 4 neighbours (N, S, E, W) in a 3x3 window",
            "roughness": "best-fit plane removed in each window (local tilt removed), "
                         "then population standard deviation of the leftover heights",
        },
        "srtm_coverage": {
            "north_deg": SRTM_NORTH_DEG, "south_deg": SRTM_SOUTH_DEG,
            "source_url": SRTM_COVERAGE_URL,
        },
        "sites": sites,
        # Every site with no terrain numbers, so the gaps are visible.
        "not_assessed": [],
    }
    for site in NOT_ASSESSED:
        lat = thermal_points[site][0]
        reason = coverage_reason(lat)
        if reason is None:
            raise SystemExit(f"{site} is inside SRTM coverage; give it a tile instead.")
        result["not_assessed"].append({"site": site, "latitude_deg": lat,
                                       "metrics": ["slope_deg", "roughness_m"], "reason": reason})

    # Every site in earth_points.csv must be either measured or listed as not assessed.
    unlisted = set(thermal_points) - set(sites) - set(NOT_ASSESSED)
    if unlisted:
        raise SystemExit(f"Sites with no terrain entry and no reason: {sorted(unlisted)}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
