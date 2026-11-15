"""
thermal.py - Day/night temperature swing from MODIS land surface temperature.

Input:   data/raw/appeears/*MOD11A2-061-results.csv   (AppEEARS point sample)
Sources: app/data/sources.json                       (must list "mod11a2_v061")
Output:  app/data/thermal.json

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\thermal.py

What the data is:
  MOD11A2 gives, for each 1 km pixel and each 8-day period, the AVERAGE
  clear-sky daytime and night-time land surface temperature (kelvin),
  seen by the Terra satellite. So "day minus night" is the difference of
  two 8-day averages, not the true hottest-minus-coldest of one day.

Scale factor:
  The file stores whole numbers; temperature (K) = stored number * 0.02.
  AppEEARS has ALREADY applied this, so the CSV values are in kelvin.
  A value of 0 means "no data" (fill value).

Quality (QC) rule - a temperature is KEPT only if:
  * it is not the fill value 0, and inside the valid range 150-1310.7 K
  * QC bits 0-1 = 00 (good quality), OR
    QC bits 0-1 = 01 (other quality) AND bits 6-7 = 00 (average LST error <= 1 K)
  Everything else is DROPPED and counted.
"""

import csv
import json
from collections import Counter
from pathlib import Path

# --- Settings -------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IN_DIR = PROJECT_ROOT / "data" / "raw" / "appeears"
SOURCES_PATH = PROJECT_ROOT / "app" / "data" / "sources.json"
OUT_PATH = PROJECT_ROOT / "app" / "data" / "thermal.json"
SOURCE_ID = "mod11a2_v061"  # key of this dataset in sources.json

# From the AppEEARS product description for MOD11A2.061 (LST_Day_1km, LST_Night_1km).
SCALE_FACTOR = 0.02      # kelvin per stored unit (already applied by AppEEARS)
FILL_VALUE = 0           # means "no temperature"
VALID_MIN_K = 150.0
VALID_MAX_K = 1310.7

KELVIN_TO_CELSIUS = 273.15  # degrees C = K - 273.15

# Column names in the AppEEARS CSV.
P = "MOD11A2_061_"
COL = {
    "day": P + "LST_Day_1km", "night": P + "LST_Night_1km",
    "qc_day": P + "QC_Day", "qc_night": P + "QC_Night",
    "bits_day": P + "QC_Day_bitmask", "bits_night": P + "QC_Night_bitmask",
}


# --- Step 1: find and read the file ----------------------------------------

def find_input():
    """List the CSV files in data/raw/appeears and return the MOD11A2 one."""
    files = sorted(IN_DIR.glob("*.csv"))
    print("Files found in data/raw/appeears:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    matches = [f for f in files if "MOD11A2-061" in f.name]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly 1 MOD11A2-061 results file, found {len(matches)}.")
    return matches[0]


# --- Step 2: quality check -------------------------------------------------

def decode_qc(qc):
    """Split the 8-bit QC number into its 4 two-bit flags.

    bits 0-1: overall quality (00 good, 01 other, 10 cloud, 11 not produced)
    bits 2-3: data quality,  bits 4-5: emissivity error,  bits 6-7: LST error
    """
    return {
        "overall": qc & 0b11,
        "data_quality": (qc >> 2) & 0b11,
        "emissivity_error": (qc >> 4) & 0b11,
        "lst_error": (qc >> 6) & 0b11,
    }


def check_value(text, qc_text, bitmask_text):
    """Return (temperature in K or None, reason). reason is "kept" or why it was dropped."""
    qc = int(float(qc_text))

    # Safety check: our bit decoding must agree with AppEEARS's own bit string.
    if format(qc, "#010b") != bitmask_text:
        raise SystemExit(f"QC {qc} does not match AppEEARS bitmask {bitmask_text}.")

    if text in ("", "NaN"):
        return None, "fill"
    value = float(text)
    if value == FILL_VALUE:
        return None, "fill"
    if not VALID_MIN_K <= value <= VALID_MAX_K:
        return None, "out_of_range"

    flags = decode_qc(qc)
    if flags["overall"] == 0b00:
        return value, "kept"
    if flags["overall"] == 0b01 and flags["lst_error"] == 0b00:
        return value, "kept"
    if flags["overall"] == 0b01:
        return None, "qc_lst_error_over_1K"
    return None, "qc_not_produced"


# --- Step 3: per-site statistics -------------------------------------------

def k_and_c(kelvin, is_difference=False):
    """Give a temperature in both K and degrees C.

    A DIFFERENCE (like a swing) is the same number in K and in C.
    A TEMPERATURE needs 273.15 subtracted.
    """
    if kelvin is None:
        return {"K": None, "C": None}
    celsius = kelvin if is_difference else kelvin - KELVIN_TO_CELSIUS
    return {"K": round(kelvin, 2), "C": round(celsius, 2)}


def site_summary(rows):
    """Turn one site's rows into its swing statistics and record series."""
    series = []                      # [date, day K, night K, swing K]
    dropped = {"day": Counter(), "night": Counter()}
    swings = []                      # (swing K, date)
    temps = []                       # (temperature K, date, "day"/"night")

    for row in rows:
        day, day_reason = check_value(row[COL["day"]], row[COL["qc_day"]], row[COL["bits_day"]])
        night, night_reason = check_value(row[COL["night"]], row[COL["qc_night"]], row[COL["bits_night"]])
        if day_reason != "kept":
            dropped["day"][day_reason] += 1
        if night_reason != "kept":
            dropped["night"][night_reason] += 1

        swing = None
        if day is not None and night is not None:
            swing = day - night
            swings.append((swing, row["Date"]))
        if day is not None:
            temps.append((day, row["Date"], "day"))
        if night is not None:
            temps.append((night, row["Date"], "night"))

        series.append([row["Date"], day, night, None if swing is None else round(swing, 2)])

    mean_swing = sum(s for s, _ in swings) / len(swings) if swings else None
    biggest = max(swings) if swings else (None, None)
    lowest = min(temps) if temps else (None, None, None)
    # Mean temperature: average of every kept day AND night value together.
    mean_temp = sum(t for t, _, _ in temps) / len(temps) if temps else None

    return {
        "latitude": float(rows[0]["Latitude"]),
        "longitude": float(rows[0]["Longitude"]),
        "records": len(rows),
        "records_with_swing": len(swings),
        "mean_swing": k_and_c(mean_swing, is_difference=True),
        "largest_swing": {**k_and_c(biggest[0], is_difference=True), "date": biggest[1]},
        "lowest_temperature": {**k_and_c(lowest[0]), "date": lowest[1], "when": lowest[2]},
        "mean_temperature": {**k_and_c(mean_temp), "values_used": len(temps)},
        "dropped": {"day": dict(dropped["day"]), "night": dict(dropped["night"])},
        "swing_null_dates": [d for d, _, _, s in series if s is None],
        "series_columns": ["date", "day_K", "night_K", "swing_K"],
        "series": series,
    }


# --- Step 4: hand-check ----------------------------------------------------

def print_hand_check(rows, site):
    """Pick the first record at `site` where day and night are both good-quality (QC 0)."""
    for row in rows:
        if row["ID"] == site and row[COL["qc_day"]] == "0.0" and row[COL["qc_night"]] == "0.0" \
                and float(row[COL["day"]]) > 0 and float(row[COL["night"]]) > 0:
            break
    else:
        print(f"\nNo fully good record for {site}; no hand-check.")
        return

    day_text, night_text = row[COL["day"]], row[COL["night"]]
    day, night = float(day_text), float(night_text)
    print(f"\n=== Swing hand-check: {site}, 8-day record starting {row['Date']} ===")
    print(f"Raw CSV values: LST_Day_1km = {day_text}, LST_Night_1km = {night_text}")
    print(f"QC_Day = {row[COL['qc_day']]} ({row[COL['bits_day']]}), "
          f"QC_Night = {row[COL['qc_night']]} ({row[COL['bits_night']]}) -> both good quality, kept")
    print(f"1) AppEEARS already scaled them. Stored numbers in the original file:")
    print(f"     day   {day_text} / {SCALE_FACTOR} = {round(day / SCALE_FACTOR)}")
    print(f"     night {night_text} / {SCALE_FACTOR} = {round(night / SCALE_FACTOR)}")
    print(f"   and back: {round(day / SCALE_FACTOR)} x {SCALE_FACTOR} = {day:.2f} K, "
          f"{round(night / SCALE_FACTOR)} x {SCALE_FACTOR} = {night:.2f} K")
    print(f"2) swing = day - night = {day:.2f} - {night:.2f} = {day - night:.2f} K")
    print(f"3) in Celsius: day = {day:.2f} - 273.15 = {day - KELVIN_TO_CELSIUS:.2f} C, "
          f"night = {night:.2f} - 273.15 = {night - KELVIN_TO_CELSIUS:.2f} C")
    print(f"   swing = {day - KELVIN_TO_CELSIUS:.2f} - ({night - KELVIN_TO_CELSIUS:.2f}) "
          f"= {(day - KELVIN_TO_CELSIUS) - (night - KELVIN_TO_CELSIUS):.2f} C  (same as in K)")


# --- Main -------------------------------------------------------------------

def main():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    if SOURCE_ID not in sources:
        raise SystemExit(f"'{SOURCE_ID}' is missing from {SOURCES_PATH}. Add it first.")
    src = sources[SOURCE_ID]

    in_file = find_input()
    with in_file.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Group rows by site ID, keeping the order they appear in.
    site_ids = list(dict.fromkeys(r["ID"] for r in rows))
    sites = {s: site_summary([r for r in rows if r["ID"] == s]) for s in site_ids}

    # Totals of dropped values, over all sites.
    total = {"day": Counter(), "night": Counter()}
    for s in sites.values():
        for side in ("day", "night"):
            total[side].update(s["dropped"][side])

    not_assessed = [
        "local observation time of each day/night value (view-time layers not in the file)",
        "AppEEARS request ID (not recorded)",
    ]
    for name, s in sites.items():
        if s["records_with_swing"] == 0:
            not_assessed.append(f"{name}: no record with both day and night kept")

    dates = sorted(r["Date"] for r in rows)
    result = {
        "product": {
            "name": src["dataset"], "short_name": src["short_name"],
            "version": src["version"], "doi_url": src["doi_url"], "citation": src["citation"],
        },
        "source_id": SOURCE_ID,
        "input_file": in_file.name,
        "resolution": {
            "pixel": "nominal 1 km (MODIS sinusoidal grid)",
            "window": "1 pixel per site (AppEEARS point sample)",
            "time_window": "8-day composite per record (date = first day)",
            "period": [dates[0], dates[-1]],
        },
        "scale_factor": {
            "value": SCALE_FACTOR, "fill_value": FILL_VALUE,
            "valid_range_K": [VALID_MIN_K, VALID_MAX_K],
            "note": "already applied by AppEEARS: CSV values are kelvin",
        },
        "method": {
            "swing": "day LST minus night LST for each 8-day record (difference of 8-day clear-sky "
                     "averages from Terra, not a true daily max minus min)",
            "lowest_temperature": "lowest kept 8-day average LST (day or night)",
            "mean_temperature": "mean of all kept day and night 8-day LST values together "
                                "(clear-sky only, two times of day, so not a true 24-hour mean)",
            "units": "K and degrees C; a swing is the same number in both",
            "qc_rule": "keep if QC bits 0-1 = 00, or bits 0-1 = 01 with bits 6-7 = 00 "
                       "(average LST error <= 1 K); drop fill (0), out-of-range and all others",
        },
        "dropped_total": {"day": dict(total["day"]), "night": dict(total["night"])},
        "sites": sites,
        "not_assessed": not_assessed,
    }

    OUT_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")

    # Print a short summary (the full series is in the JSON file).
    print(f"\nRecords: {len(rows)} ({len(site_ids)} sites x {len(rows) // len(site_ids)} dates), "
          f"{dates[0]} to {dates[-1]}")
    print(f"Dropped day values:   {sum(total['day'].values())}  {dict(total['day'])}")
    print(f"Dropped night values: {sum(total['night'].values())}  {dict(total['night'])}")
    print(f"\n{'site':11s} {'swings':>6s} {'mean swing':>12s} {'largest swing (date)':>24s} "
          f"{'lowest K / C (date, when)':>36s} {'mean temp K / C (n)':>24s}")
    for name, s in sites.items():
        ms, lg, lo = s["mean_swing"], s["largest_swing"], s["lowest_temperature"]
        mt = s["mean_temperature"]
        print(f"{name:11s} {s['records_with_swing']:6d} {str(ms['K']):>9s} K "
              f"{str(lg['K']):>9s} K ({lg['date']}) "
              f"{str(lo['K']):>8s} / {str(lo['C']):>7s} ({lo['date']}, {lo['when']}) "
              f"{str(mt['K']):>8s} / {str(mt['C']):>7s} ({mt['values_used']})")
    print(f"\nWrote {OUT_PATH}")

    print_hand_check(rows, "atacama")


if __name__ == "__main__":
    main()
