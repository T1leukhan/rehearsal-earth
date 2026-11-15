"""
moon_terrain.py - Slope and roughness for the LOLA Site23 (Malapert massif) map.

Input:   data/raw/moon/Site23_final_adj_5mpp_surf.tif   (heights, 5 m pixels)
         data/raw/moon/Site23_final_adj_5mpp_slp.tif    (LOLA's own 5 m slope)
Sources: app/data/sources.json                          (must list "lola_5mpp_site23")
Output:  app/data/moon_terrain.json

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\moon_terrain.py     (Windows)
    .venv/bin/python pipeline/moon_terrain.py               (macOS/Linux)

Why we average first:
  The Earth heights (SRTM) have pixels of about 30 m. Slope depends on pixel
  size: smaller pixels see steeper little bumps. To compare like with like,
  we turn the 5 m Moon heights into 30 m heights by averaging each 6 x 6
  block of pixels (6 x 5 m = 30 m) into one pixel. 4200 / 6 = 700 exactly,
  so the 30 m map is 700 x 700 pixels with nothing left over.

Then we use the SAME slope and roughness functions as pipeline/terrain.py
(imported from it), with the same 3 x 3 window.

The map's grid (south polar stereographic) is in meters, so the pixel size
in meters is read straight from the file; no degree-to-meter step is needed.
"""

import json
import math
from pathlib import Path

import numpy as np
import rasterio

# Reuse the Earth functions so both sides use exactly the same method.
from terrain import ROUGHNESS_TARGET_M, roughness_detrended, slope_degrees, summarise, window_pixels

# --- Settings -------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_DIR = PROJECT_ROOT / "data" / "raw" / "moon"
SURF_PATH = IN_DIR / "Site23_final_adj_5mpp_surf.tif"
SLP_PATH = IN_DIR / "Site23_final_adj_5mpp_slp.tif"
SOURCES_PATH = PROJECT_ROOT / "app" / "data" / "sources.json"
OUT_PATH = PROJECT_ROOT / "app" / "data" / "moon_terrain.json"
SOURCE_ID = "lola_5mpp_site23"  # key of this dataset in sources.json

TARGET_PIXEL_M = 30.0   # about the Earth SRTM pixel size

# Where the first two caveats come from (read on 2026-11-14).
CAVEAT_SOURCE_URL = "https://pgda.gsfc.nasa.gov/products/78"

CAVEATS = [
    "Slope uncertainty: LOLA's median RMS slope error is about 1.5 to 2.5 degrees. The product page "
    "says 'The LDEM height and slope uncertainties within the RoIs are similar across all the sites "
    "with a median RMS Z error ~ 0.30 - 0.50 m and a median RMS slope error ~ 1.5 - 2.5°' "
    f"({CAVEAT_SOURCE_URL}). This is a median over the regions of interest of all sites, "
    "not a value for each Site23 pixel.",
    "Interpolated heights: about 90 percent of the 5 m pixels are interpolated, not direct LOLA "
    "measurements. The product page says 'the fraction of interpolated 5-m pixels in these polar "
    f"LDEMs is necessarily large (~90%)' ({CAVEAT_SOURCE_URL}). This is for the polar maps in "
    "general; the share for Site23 alone was not computed.",
    "Block means: the 30 m heights are averages of 6 x 6 blocks of 5 m pixels. This smooths "
    "the surface and can lower the slope; compare with original_5m_slope.",
    "Different areas: the Moon value covers the whole 21 km x 21 km Site23 map near the south pole "
    "(about 85.6 to 86.3 S); the Earth value in terrain.json covers a 10 km x 10 km square.",
    "Projection: map meters are 0.10 to 0.15 percent longer than true ground meters at this site "
    "(polar stereographic, true scale at the pole). This was not corrected.",
]


# --- Step 1: read the heights ---------------------------------------------

def read_heights(path):
    """Read the height map and check that its pixels are square and in meters."""
    with rasterio.open(path) as src:
        if src.crs.linear_units not in ("metre", "meter"):
            raise SystemExit(f"{path.name}: grid units are {src.crs.linear_units}, not meters.")
        t = src.transform
        if t.b != 0 or t.d != 0:
            raise SystemExit(f"{path.name}: the grid is rotated; this script does not handle that.")
        pixel_x_m, pixel_y_m = src.res
        if pixel_x_m != pixel_y_m:
            raise SystemExit(f"{path.name}: pixels are not square ({pixel_x_m} x {pixel_y_m} m).")
        z = src.read(1).astype(np.float64)
        nodata = src.nodata
        info = {"shape": z.shape, "pixel_m": pixel_x_m, "bounds": tuple(src.bounds),
                "crs": src.crs.to_proj4()}

    # Mark missing pixels as NaN so they are never used. (NaN nodata is already NaN.)
    if nodata is not None and not math.isnan(nodata):
        z[z == nodata] = np.nan
    info["missing_pixels"] = int(np.isnan(z).sum())
    return z, info


# --- Step 2: average to about 30 m -----------------------------------------

def block_size(pixel_m, target_m):
    """Whole number of pixels per block side closest to target_m."""
    return max(1, round(target_m / pixel_m))


def block_mean(z, k):
    """Average each k x k block of pixels into one pixel.

    The grid is cut into k x k blocks; each block's mean becomes one new pixel.
    If a block has any missing (NaN) pixel, the new pixel is NaN too, so we
    never fill gaps. Rows or columns that do not fill a whole block are dropped.
    """
    rows = (z.shape[0] // k) * k
    cols = (z.shape[1] // k) * k
    z = z[:rows, :cols]
    # Reshape to (block row, row inside block, block column, column inside block)
    # and average over the two "inside block" axes.
    return z.reshape(rows // k, k, cols // k, k).mean(axis=(1, 3))


# --- Step 3: hand-checks against plain numpy ---------------------------------

def hand_check_slope(z, pixel_m, slope, r, c):
    """Slope at one pixel, worked out with numpy.gradient on its 3 x 3 patch."""
    patch = z[r - 1:r + 2, c - 1:c + 2]
    print("\n=== Slope hand-check (30 m grid) ===")
    print(f"Centre pixel: row {r}, column {c}. 3 x 3 patch of heights (m), map rows top to bottom:")
    for line in patch:
        print("   " + "  ".join(f"{v:9.3f}" for v in line))
    # numpy.gradient uses (next - previous) / (2 * spacing) at the centre,
    # i.e. the same central difference, but computed by a different function.
    d_rows, d_cols = np.gradient(patch, pixel_m)
    rise_rows, rise_cols = d_rows[1, 1], d_cols[1, 1]
    steep = math.hypot(rise_rows, rise_cols)
    angle = math.degrees(math.atan(steep))
    print(f"1) rise along columns = ({patch[1, 2]:.3f} - {patch[1, 0]:.3f}) / (2*{pixel_m}) = {rise_cols:.5f}")
    print(f"2) rise along rows    = ({patch[2, 1]:.3f} - {patch[0, 1]:.3f}) / (2*{pixel_m}) = {rise_rows:.5f}")
    print(f"3) steepness = sqrt({rise_cols:.5f}^2 + {rise_rows:.5f}^2) = {steep:.5f}")
    print(f"4) slope = arctan({steep:.5f}) = {angle:.4f} degrees")
    print(f"Script's value for this pixel: {slope[r, c]:.4f} degrees")
    return angle


def hand_check_roughness(z, rough, r, c):
    """Roughness of one 3 x 3 patch, using numpy's least-squares plane fit."""
    patch = z[r - 1:r + 2, c - 1:c + 2]
    y, x = np.mgrid[-1:2, -1:2]             # row and column offsets -1, 0, +1
    a = np.column_stack([np.ones(9), x.ravel(), y.ravel()])
    coef, *_ = np.linalg.lstsq(a, patch.ravel(), rcond=None)
    leftover = patch.ravel() - a @ coef     # heights minus the best-fit plane
    value = float(np.sqrt(np.mean(leftover**2)))
    print("\n=== Roughness hand-check (30 m grid, same 3 x 3 patch) ===")
    print(f"Best-fit plane (numpy.linalg.lstsq): height = {coef[0]:.3f} + {coef[1]:.4f}*x + {coef[2]:.4f}*y")
    print("Leftover heights (m): " + ", ".join(f"{v:.4f}" for v in leftover))
    print(f"Roughness = sqrt(mean(leftover^2)) = {value:.4f} m")
    print(f"Script's value for this patch: {rough[r, c]:.4f} m")
    return value


# --- Main ------------------------------------------------------------------

def main():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if SOURCE_ID not in sources:
        raise SystemExit(f"{SOURCE_ID} is not listed in sources.json, so its numbers may not be used.")

    # Heights at 5 m, then block means at about 30 m.
    z5, info = read_heights(SURF_PATH)
    k = block_size(info["pixel_m"], TARGET_PIXEL_M)
    pixel_m = k * info["pixel_m"]
    z30 = block_mean(z5, k)
    print(f"Read {SURF_PATH.name}: {info['shape'][0]} x {info['shape'][1]} pixels of {info['pixel_m']} m")
    print(f"Block size {k} x {k} -> {z30.shape[0]} x {z30.shape[1]} pixels of {pixel_m} m")

    # Same functions as terrain.py. Pixels are square, so dx is the same for every row.
    dx = np.full(z30.shape[0], pixel_m)
    slope = slope_degrees(z30, dx, pixel_m)
    n = window_pixels(ROUGHNESS_TARGET_M, pixel_m)   # same rule as Earth: 3 here
    rough = roughness_detrended(z30, n)
    everything = slice(None)
    stats = summarise(slope, rough, everything, everything, pixel_m, pixel_m, n)

    # LOLA's own 5 m slope map, for comparison.
    with rasterio.open(SLP_PATH) as src:
        slp5 = src.read(1).astype(np.float64)
        slp5_pixel = src.res[0]
    slp5_median = round(float(np.nanmedian(slp5)), 2)

    result = {
        "site": "Site23, Malapert massif, lunar south pole",
        "source_id": SOURCE_ID,
        "map": {
            "file": SURF_PATH.name,
            "shape_rows_cols": list(info["shape"]),
            "pixel_m": info["pixel_m"],
            "bounds_m": info["bounds"],
            "size_m": [info["shape"][0] * info["pixel_m"], info["shape"][1] * info["pixel_m"]],
            "crs": info["crs"],
            "missing_pixels": info["missing_pixels"],
        },
        "averaging": {
            "method": f"block mean of {k} x {k} pixels; a block with any missing pixel would be left missing",
            "block_px": k,
            "resolution_m": pixel_m,
            "shape_rows_cols": list(z30.shape),
        },
        "methods": {
            "slope": "central difference: 4 neighbours in a 3x3 window (slope_degrees from terrain.py)",
            "roughness": "best-fit plane removed in each window, then population standard deviation "
                         "of the leftover heights (roughness_detrended from terrain.py)",
        },
        "areas": {
            "whole_site": {
                "description": "whole Site23 map at 30 m, edge pixels skipped",
                **stats,
            },
        },
        "original_5m_slope": {
            "file": SLP_PATH.name,
            "median_deg": slp5_median,
            "resolution_m": slp5_pixel,
            "pixels_used": int(np.isfinite(slp5).sum()),
            "note": "LOLA's own slope map, not recomputed here; for comparison only",
        },
        "not_assessed": [],
        "caveats": CAVEATS,
        "caveats_source": {
            "url": CAVEAT_SOURCE_URL,
            "for": ["slope uncertainty (median RMS slope error ~1.5-2.5 deg)",
                    "share of interpolated 5 m pixels (~90%)"],
            "checked": "page text read on 2026-11-14",
        },
    }
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["areas"], indent=2))
    print(f"Original 5 m slope median: {slp5_median} deg")
    print(f"\nWrote {OUT_PATH}")

    # Hand-check the centre pixel of the 30 m map.
    r = c = z30.shape[0] // 2
    hand_check_slope(z30, pixel_m, slope, r, c)
    hand_check_roughness(z30, rough, r, c)


# Run main() only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    main()
