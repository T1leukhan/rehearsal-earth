"""
get_tile.py - Download ONE SRTM elevation tile from NASA Earthdata.

Dataset: SRTMGL1 version 3 (NASA SRTM, 1 arc-second, about 30 m per pixel).
Target point: latitude -23.5, longitude -69.5 (Atacama Desert, Chile).

How to run (from the project folder):
    .venv\\Scripts\\python.exe pipeline\\get_tile.py

The script:
  1. Searches NASA's catalog for the tile that covers our point (no login needed).
  2. Prints the file name and size, then asks you to type "y" to continue.
  3. Logs in to NASA Earthdata (see log_in below).
  4. Downloads the file into data/raw/.

Login: if the environment variables EARTHDATA_USERNAME and
EARTHDATA_PASSWORD are set, the script uses them. Otherwise it asks you
to type your username and password. It never prints or saves them.
"""

import os
from pathlib import Path

import earthaccess

# The point we want, in degrees. South and west are negative.
LATITUDE = -23.5
LONGITUDE = -69.5

# data/raw/ sits next to the pipeline/ folder, in the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FOLDER = PROJECT_ROOT / "data" / "raw"


def log_in():
    """Log in to NASA Earthdata. Returns True if it worked.

    We only check WHETHER the variables are set. We never print their
    values, so the password never shows up on screen or in a log.
    """
    has_username = bool(os.environ.get("EARTHDATA_USERNAME"))
    has_password = bool(os.environ.get("EARTHDATA_PASSWORD"))

    if has_username and has_password:
        print("Logging in with EARTHDATA_USERNAME and EARTHDATA_PASSWORD...")
        try:
            auth = earthaccess.login(strategy="environment")
            if auth is not None and auth.authenticated:
                return True
        except Exception:
            # We do not print the error, in case it repeats the login details.
            pass
        print("That login did not work. Switching to typed login.")
    else:
        print("EARTHDATA_USERNAME / EARTHDATA_PASSWORD not set. Using typed login.")

    # Fallback: earthaccess asks you to type your username and password.
    # persist=False means it does NOT save them to a .netrc file.
    auth = earthaccess.login(strategy="interactive", persist=False)
    return auth is not None and auth.authenticated


def main():
    # Step 1: ask NASA's catalog (called CMR) which files cover our point.
    # Note: earthaccess wants the point as (longitude, latitude), x before y.
    results = earthaccess.search_data(
        short_name="SRTMGL1",
        version="003",
        point=(LONGITUDE, LATITUDE),
    )

    if len(results) == 0:
        print("No SRTMGL1 tile found for this point. Nothing downloaded.")
        raise SystemExit(1)

    if len(results) > 1:
        # This can happen if the point sits exactly on a tile edge.
        print(f"Note: {len(results)} tiles matched. Using only the first one.")

    tile = results[0]

    # Step 2: show the file name and size before downloading anything.
    # The file name is the last part of the download web address.
    links = tile.data_links()
    file_name = links[0].split("/")[-1]
    size_mb = tile.size  # earthaccess reports the size in megabytes (MB)

    print(f"File name: {file_name}")
    print(f"Size:      {size_mb:.1f} MB")
    print(f"Save to:   {RAW_FOLDER}")

    answer = input("Download this file? Type y and press Enter: ")
    if answer.strip().lower() != "y":
        print("Cancelled. Nothing downloaded.")
        raise SystemExit(0)

    # Step 3: log in (environment variables first, then typed login).
    if not log_in():
        print("Login failed. Nothing downloaded.")
        raise SystemExit(1)

    # Step 4: download into data/raw/ (the folder is created if missing).
    RAW_FOLDER.mkdir(parents=True, exist_ok=True)
    saved = earthaccess.download([tile], local_path=str(RAW_FOLDER))

    if saved:
        print(f"Saved: {saved[0]}")
    else:
        print("Download failed. Check your login and try again.")
        raise SystemExit(1)


# Run main() only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    main()
