"""
moon_thermal.py - Lunar equatorial temperatures from two LRO Diviner maps.

Input:   data/raw/moon/dgdr_tbol_avg_cyl_20100121d_004_img.img  (daytime map)
         data/raw/moon/dgdr_tbol_avg_cyl_20100107n_004_img.img  (nighttime map)
Sources: app/data/sources.json                                  (must list "lro_diviner_gdr_l3")
Output:  app/data/moon_thermal.json

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\moon_thermal.py     (Windows)
    .venv/bin/python pipeline/moon_thermal.py               (macOS/Linux)

What the data is (from the .lbl labels next to each file):
  Each map is "bolometric temperature" in kelvin, 720 rows x 1440 columns,
  4 pixels per degree (7580.8 m per pixel at the equator), covering the
  whole Moon. Each pixel is a 16-bit whole number; kelvin = number * 0.02.
  The number -32768 means "no data".

What we report, for the band from latitude -5 to +5 (all longitudes):
  share of pixels that have data, and the median, 5th and 95th percentile,
  separately for the daytime map and the nighttime map.

What we do NOT report: a daily swing. The two maps are from different
months and each pixel was seen at an unknown local time (see CAVEATS), so
"day minus night" is only an observed range across both maps.
"""

import json
from pathlib import Path

import numpy as np

# --- Settings -------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_DIR = PROJECT_ROOT / "data" / "raw" / "moon"
SOURCES_PATH = PROJECT_ROOT / "app" / "data" / "sources.json"
OUT_PATH = PROJECT_ROOT / "app" / "data" / "moon_thermal.json"
SOURCE_ID = "lro_diviner_gdr_l3"  # key of this dataset in sources.json

# Both maps, with the local-time range and dates from their labels.
MAPS = {
    "day": {
        "file": "dgdr_tbol_avg_cyl_20100121d_004_img.img",
        "local_time_h": [6, 18],
        "period_utc": ["2010-01-21T01:00:00", "2010-02-17T09:00:00"],
    },
    "night": {
        "file": "dgdr_tbol_avg_cyl_20100107n_004_img.img",
        "local_time_h": [18, 6],
        "period_utc": ["2010-01-07T10:00:00", "2010-02-03T18:00:00"],
    },
}

# Map layout, from the labels (identical in both files).
ROWS, COLS = 720, 1440
PIXELS_PER_DEG = 4
SCALE_FACTOR = 0.02            # kelvin per stored unit
NODATA = -32768                # stored number that means "no data"
PIXEL_M = 7580.837606          # pixel size at the equator (MAP_SCALE)
MOON_RADIUS_M = 1737400.0      # A_AXIS_RADIUS = 1737.4 km

# The band we look at.
LAT_MIN, LAT_MAX = -5.0, 5.0

CAVEATS = [
    "Local-time drift: the labels say LRO's orbit gives 'a drift in local time across each map', "
    "and the files do not store each pixel's local time. Daytime values are somewhere between "
    "06:00 and 18:00 local time and nighttime values somewhere between 18:00 and 06:00, "
    "not at noon or midnight.",
    "Different months: the daytime map covers 2010-01-21 to 2010-02-17 and the nighttime map "
    "covers 2010-01-07 to 2010-02-03 (UTC). They overlap but are not the same period.",
    "7.6 km pixels: each pixel is 7580.8 m across at the equator (4 pixels per degree).",
    "Empty pixels: many pixels have no data (-32768). Statistics use only pixels with data; "
    "the share of pixels with data is reported for each map.",
    "Observed range is not a daily swing: day p95 minus night p5 compares two different "
    "groups of pixels, seen at different local times in different months.",
]


# --- Step 1: read a map ----------------------------------------------------

def read_map(path):
    """Read one Diviner .img file into a 720 x 1440 grid of whole numbers.

    The file has no header: just 720 * 1440 numbers, each 2 bytes,
    little-endian ("<i2"), row by row from the north pole down.
    """
    raw = np.fromfile(path, dtype="<i2")
    if raw.size != ROWS * COLS:
        raise SystemExit(f"{path.name}: expected {ROWS * COLS} values, found {raw.size}.")
    return raw.reshape(ROWS, COLS)


def to_kelvin(raw):
    """Turn stored numbers into kelvin, with NaN ("not a number") where there is no data."""
    kelvin = raw.astype(np.float64) * SCALE_FACTOR
    kelvin[raw == NODATA] = np.nan
    return kelvin


# --- Step 2: find the rows inside the band ---------------------------------

def row_latitude(row):
    """Latitude (deg) of the centre of a row.

    Row 0's top edge is at 90 N and each row is 1/4 degree tall,
    so row 0's centre is at 90 - 0.125 = 89.875.
    """
    return 90.0 - (row + 0.5) / PIXELS_PER_DEG


def band_rows(lat_min, lat_max):
    """All rows whose centre latitude is between lat_min and lat_max (inclusive)."""
    rows = []
    for row in range(ROWS):
        if lat_min <= row_latitude(row) <= lat_max:
            rows.append(row)
    return rows


# --- Step 3: statistics ----------------------------------------------------

def band_stats(kelvin_band):
    """Share of pixels with data, and median / 5th / 95th percentile of those pixels (K)."""
    values = kelvin_band[~np.isnan(kelvin_band)]   # keep only pixels with data
    total = kelvin_band.size
    if values.size == 0:
        # No data at all: every statistic is missing.
        return {"pixels_total": total, "pixels_with_data": 0, "share_with_data_percent": 0.0,
                "median_K": None, "p5_K": None, "p95_K": None}
    return {
        "pixels_total": int(total),
        "pixels_with_data": int(values.size),
        "share_with_data_percent": round(100 * values.size / total, 2),
        "median_K": round(float(np.median(values)), 2),
        "p5_K": round(float(np.percentile(values, 5)), 2),
        "p95_K": round(float(np.percentile(values, 95)), 2),
    }


def observed_range(day, night):
    """Day 95th percentile minus night 5th percentile, or None if either is missing."""
    if day["p95_K"] is None or night["p5_K"] is None:
        return None
    return round(day["p95_K"] - night["p5_K"], 2)


# --- Step 4: one hand-check ------------------------------------------------

def hand_check(raw, rows):
    """Print one pixel's stored number, the scale, and the kelvin value, worked by hand."""
    # Start at the row closest to the equator and take its first pixel with data.
    rows_by_closeness = sorted(rows, key=lambda r: abs(row_latitude(r)))
    for row in rows_by_closeness:
        for col in range(COLS):
            if raw[row, col] != NODATA:
                dn = int(raw[row, col])
                lon = (col + 0.5) / PIXELS_PER_DEG
                print(f"Pixel: row {row}, column {col} -> latitude {row_latitude(row):.3f}, "
                      f"longitude {lon:.3f} E")
                print(f"1) stored number (DN) = {dn}")
                print(f"2) scale factor       = {SCALE_FACTOR} K per DN")
                print(f"3) temperature        = {dn} x {SCALE_FACTOR} = {dn * SCALE_FACTOR:.2f} K")
                print(f"Script's value for this pixel: {to_kelvin(raw)[row, col]:.2f} K")
                return
    print("No pixel with data in the band, so no hand-check.")


# --- Main ------------------------------------------------------------------

def main():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if SOURCE_ID not in sources:
        raise SystemExit(f"{SOURCE_ID} is not listed in sources.json, so its numbers may not be used.")

    rows = band_rows(LAT_MIN, LAT_MAX)
    print(f"Band {LAT_MIN} to {LAT_MAX} deg: rows {rows[0]}-{rows[-1]} ({len(rows)} rows x {COLS} columns)")

    results = {}
    raws = {}
    for name, info in MAPS.items():
        path = IN_DIR / info["file"]
        print(f"Reading {path.name} ({path.stat().st_size:,} bytes)")
        raw = read_map(path)
        raws[name] = raw
        stats = band_stats(to_kelvin(raw)[rows, :])
        results[name] = {"file": info["file"], "local_time_h": info["local_time_h"],
                         "period_utc": info["period_utc"], **stats}
        print(f"  {name:5}: {stats['share_with_data_percent']}% of pixels have data, "
              f"median {stats['median_K']} K, p5 {stats['p5_K']} K, p95 {stats['p95_K']} K")

    spread = observed_range(results["day"], results["night"])
    print(f"Observed range across both maps (day p95 - night p5), not a daily swing: {spread} K")

    # List every missing value, so the gaps are visible.
    missing = [f"{name}.{key}" for name in results for key in ("median_K", "p5_K", "p95_K")
               if results[name][key] is None]

    out = {
        "body": "moon",
        "source_id": SOURCE_ID,
        "band": {
            "lat_min_deg": LAT_MIN, "lat_max_deg": LAT_MAX, "lon_deg": [0, 360],
            "rows": [rows[0], rows[-1]],
            # Band height in meters: 10 degrees of the Moon's circumference.
            "window_m_ns": round((LAT_MAX - LAT_MIN) * np.pi * MOON_RADIUS_M / 180, 1),
            "window_note": "all longitudes, so the band goes once around the Moon",
        },
        "resolution_m": PIXEL_M,
        "resolution_note": "pixel size at the equator; 4 pixels per degree",
        "scale_factor_K_per_DN": SCALE_FACTOR,
        "nodata_DN": NODATA,
        "statistics_method": "pixels with data only; median and percentiles by numpy (linear interpolation); rounded to 0.01 K",
        "day": results["day"],
        "night": results["night"],
        "observed_range_K": {
            "value": spread,
            "label": "observed range across both maps, not a daily swing",
            "method": "day p95_K minus night p5_K",
        },
        "missing": missing,
        "caveats": CAVEATS,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")

    print("\n=== Hand-check: daytime map ===")
    hand_check(raws["day"], rows)


# Run main() only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    main()
