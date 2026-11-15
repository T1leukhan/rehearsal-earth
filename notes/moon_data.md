# Moon data (downloaded 2026-11-13)

Raw files are in `data/raw/moon/` (git-ignored). Both datasets are listed in
`app/data/sources.json` as `lro_diviner_gdr_l3` (DOI 10.17189/wj0s-w188) and
`lola_5mpp_site23` (no dataset DOI found, so `null`). The Diviner equatorial
statistics are in `app/data/moon_thermal.json`, written by
`pipeline/moon_thermal.py`. The LOLA Site23 slope and roughness (heights
averaged to 30 m with 6 x 6 block means) are in `app/data/moon_terrain.json`,
written by `pipeline/moon_terrain.py`.

Each file's size was read with an HTTP HEAD request before downloading and
checked against the downloaded size afterwards. All 8 matched. No login was needed.

## Files

### LRO Diviner Level 3 bolometric temperature maps (lunar temperature)

Folder: https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/

| File | Bytes |
|---|---|
| [dgdr_tbol_avg_cyl_20100121d_004_img.img](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100121d_004_img.img) | 2,073,600 |
| [dgdr_tbol_avg_cyl_20100121d_004_img.lbl](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100121d_004_img.lbl) | 4,346 |
| [dgdr_tbol_avg_cyl_20100121d_004_img.xml](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100121d_004_img.xml) | 11,447 |
| [dgdr_tbol_avg_cyl_20100107n_004_img.img](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100107n_004_img.img) | 2,073,600 |
| [dgdr_tbol_avg_cyl_20100107n_004_img.lbl](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100107n_004_img.lbl) | 4,346 |
| [dgdr_tbol_avg_cyl_20100107n_004_img.xml](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gdr_l3/2010/cylindrical/img/dgdr_tbol_avg_cyl_20100107n_004_img.xml) | 11,447 |

What the labels and files say:

| | Daytime map (`20100121d`) | Nighttime map (`20100107n`) |
|---|---|---|
| Quantity | Bolometric temperature | Bolometric temperature |
| Observation dates | 2010-01-21 01:00 to 2010-02-17 09:00 UTC | 2010-01-07 10:00 to 2010-02-03 18:00 UTC |
| Local time range (label) | 06:00 to 18:00 | 18:00 to 06:00 |
| Product created | 2011-04-04 | 2011-04-15 |
| Shape (lines x samples) | 720 x 1440 | 720 x 1440 |
| Data type | 16-bit signed integer, little-endian, no header | same |
| Scale | K = DN x 0.02 + 0 | same |
| Nodata | -32768 | -32768 |
| Nodata pixels | 711,532 of 1,036,800 (68.63%) | 600,168 of 1,036,800 (57.89%) |
| Min / max (after x 0.02) | 33.56 K / 412.58 K | 27.16 K / 291.56 K |
| Grid | 4 pixels per degree, 7580.8 m/pixel at the equator | same |
| Coverage | 90S to 90N, 0 to 360E, simple cylindrical | same |

The min and max agree with the labels' DERIVED_MINIMUM / DERIVED_MAXIMUM to
within one 0.02 K step.

### LOLA 5 m/pixel maps, Site23 (Malapert massif, lunar south pole)

Folder: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/
README: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README

| File | Bytes | Server Last-Modified |
|---|---|---|
| [Site23_final_adj_5mpp_slp.tif](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/Site23_final_adj_5mpp_slp.tif) | 70,586,810 | 2020-06-08 |
| [Site23_final_adj_5mpp_surf.tif](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/Site23_final_adj_5mpp_surf.tif) | 70,586,804 | 2020-06-12 |

| | Slope (`slp`) | Surface height (`surf`) |
|---|---|---|
| Units | degrees (README: "Slope (degrees)") | meters (README: "surface height Z (meters)") |
| Shape | 4200 x 4200, 1 band | 4200 x 4200, 1 band |
| Data type | float32 | float32 |
| Nodata | NaN (no NaN pixels found) | NaN (no NaN pixels found) |
| Min / max | 0.0198 / 76.18 deg | 901.99 / 5173.56 m |
| Pixel size | 5 m x 5 m | 5 m x 5 m |
| Map | South polar stereographic, x -11000 to 10000 m, y 111000 to 132000 m (21 km x 21 km) | same |

The GeoTIFF metadata has no unit for the slope (the band is just named `z`).
The unit comes from the README. The value range (0 to 76) agrees with degrees
and rules out radians.

The README says the `surf` heights had "interpolation filling empty pix". It
also asks users to cite Barker et al. 2021,
https://doi.org/10.1016/j.pss.2020.105119

## Caveats (read before computing anything)

1. **Local-time drift.** The Diviner maps are not noon or midnight maps. The
   label says LRO's orbit causes "a drift in local time across each map", and
   the files do not store the local time of each pixel. The daytime map is
   somewhere between 06:00 and 18:00, the nighttime map somewhere between
   18:00 and 06:00. A "swing" from them is daytime minus nighttime at unknown
   local times, not the true maximum minus minimum.
2. **Different months.** The daytime map covers 2010-01-21 to 2010-02-17, and
   the nighttime map covers 2010-01-07 to 2010-02-03. They overlap but are not
   the same period.
3. **7.6 km pixels.** Each Diviner pixel is about 7.6 km across at the equator
   (4 pixels per degree). Any lunar temperature must say `resolution_m: 7580.8`.
   That is far coarser than the Earth MODIS thermal data (1 km).
4. **Gaps.** Most Diviner pixels are empty (68.6% day, 57.9% night). The
   chosen equatorial point may have no value in one or both maps. If so, it is
   **not assessed**.
5. **The nighttime map reaches 291.56 K.** The 18:00 to 06:00 window includes
   times just after sunset and just before sunrise, so "night" values near the
   edges of that window can still be warm.
6. **5 m slope vs 30 m Earth slope.** The LOLA slope is on 5 m pixels. The
   Earth slope in `app/data/terrain.json` is from SRTM at about 30.9 m x 28.3 m
   pixels, using a 3 x 3 window (about 92.7 m x 85.0 m). Slopes usually get steeper as
   pixels get smaller, so the two cannot be compared directly. They must be put
   on the same pixel size and window first, or shown side by side with their
   `window_m` and `resolution_m`.
7. **Interpolated heights.** Some `surf` pixels are filled by interpolation
   (README), so not every pixel is a direct LOLA measurement. The `slp` file
   was not checked for this.
