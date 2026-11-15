# Rehearsal Earth

**An engineering analog atlas for rehearsing the Moon and Mars on Earth.**
Our entry for the NASA Space Apps Challenge 2026. Not affiliated with or endorsed by NASA.

## The question

> Where on Earth can we rehearse the Moon and Mars, and how far can we trust it?

Before a rover or a lander flies, engineers test it somewhere on Earth that is as close as
possible to where it is going. No place on Earth is a perfect match. Rehearsal Earth uses
NASA data to measure how close five well-known Earth test sites really are to one Moon
reference and one Mars reference, using engineering numbers (temperature swing, mean
temperature, slope and roughness of the ground), and shows where the analogy breaks.

The five Earth sites are Atacama Desert (Chile), Altiplano (Bolivia/Chile), Mauna Kea (Hawaii),
Haughton Crater (Devon Island, Canada) and Dry Valleys (Antarctica).

Short answer from our own data: **every one of the 16 comparisons we could score is a weak
match.** The best Earth site reaches only 7.9% of the Moon's day–night temperature swing,
and the closest Earth terrain is flatter than the Moon reference. The page shows these
results with every number, its source and its limits, and never fills a gap with a guess:
anything we could not measure is shown as **not assessed**.

## What the page contains

The whole project is one static web page (`app/index.html`). Every view has its own web
address, so the browser's Back and Forward buttons work, and every view can be linked.

| View | Address | What you see |
|---|---|---|
| Start page | `#start` (or no address) | The question, three headline findings worked out from the data, and buttons to begin. |
| Explore hub | `#hub` | Seven stations, each with a short description. |
| Thermal | `#thermal` | Day–night temperature swing of each Earth site against the Moon, and mean temperature against Mars, with charts, site cards and the satellite map. |
| Terrain | `#terrain` | Slope and roughness of the ground against the Moon's Malapert massif, with charts, site cards and the satellite map. |
| Try it | `#tryit` | Rover calculator: ground pressure p = m g / A on Earth, the Moon and Mars, and thermal expansion ΔL = α L ΔT of a beam for each site's swing. A generic six-wheel rover illustration follows the inputs. |
| Gravity Drop | `#gravity-drop` | Fall time t = √(2h/g) and impact speed v = √(2gh) from the same height on Earth, the Moon and Mars. |
| Mission Match | `#mission` | Pick a task (climb steep slopes, survive big temperature swings, stay as cold as Mars, land from a drop) and see which site, if any, can stand in for it. |
| Validation | `#validation` | Benchmarks, a negative control, single-metric checks and a tolerance sensitivity test. |
| Sources | `#sources` | Every number on the page, where it comes from, its window and resolution, and a link to the source. |

**Satellite map** (Thermal and Terrain): the five thermal points, plus the Altiplano terrain
square (which is not on its thermal point, see Limits), drawn on NASA GIBS imagery
(Blue Marble: Next Generation, zoom levels 0 to 8) with the Leaflet map library. Each site is
coloured by its swing as a share of the Moon's swing. If the map cannot load, a message is
shown and the rest of the page works.

The page uses SI units throughout, works on a phone (390 px wide) and with the keyboard,
keeps text contrast at 4.5:1 or more, and turns off its gentle animations when the visitor
asks for reduced motion.

## Data

Every number on the page traces back to one of these sources (all listed with their
identifiers in `app/data/sources.json`; full references in `REFERENCES.md`).

| Dataset | Used for | Source URL | Date | Resolution | Citation |
|---|---|---|---|---|---|
| NASA SRTM Global 1 arc second V003 (SRTMGL1) | Earth slope and roughness (Atacama, Altiplano, Mauna Kea) | <https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003> | published 2013; tiles S24W070, S21W069, N19W156 accessed 2026-11-08 | 1 arc-second, about 30.9 m × 28.3 m at our sites | NASA JPL (2013). NASA Shuttle Radar Topography Mission Global 1 arc second [Data set]. NASA LP DAAC. |
| MODIS/Terra Land Surface Temperature/Emissivity 8-Day L3 Global 1km SIN Grid V061 (MOD11A2), via NASA AppEEARS | Earth day–night swing and mean temperature (all 5 sites) | <https://doi.org/10.5067/MODIS/MOD11A2.061> | 8-day records from 2022-12-27 to 2025-12-27; accessed 2026-11-08 | nominal 1 km pixel, 8-day composite, 1 pixel per site | Wan, Z., Hook, S., Hulley, G. (2021). MOD11A2 V061 [Data set]. NASA LP DAAC. |
| LRO Diviner Level 3 Gridded Data Product (bolometric temperature) | Moon equator temperatures, shown as extra references (not scored) | <https://doi.org/10.17189/wj0s-w188> | day map 2010-01-21 to 2010-02-17, night map 2010-01-07 to 2010-02-03 (UTC); accessed 2026-11-13 | 4 pixels per degree, 7580.8 m per pixel at the equator | Paige, D., Sullivan, M., Williams, J-P. (2022). Lunar Reconnaissance Orbiter Diviner Derived Data Bundle 1. NASA PDS. |
| LOLA 5 m/pixel maps, Site23 (Malapert massif) | Moon slope and roughness reference | <https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site23/> | files dated 2020-06-08 (slope) and 2020-06-12 (heights) | 5 m pixels, 21 km × 21 km; averaged to 30 m here | Barker et al. (2021), "Improved LOLA elevation maps for south pole landing sites: Error estimates and their impact on illumination conditions", <https://doi.org/10.1016/j.pss.2020.105119> (no dataset DOI; the README asks users to cite this paper) |
| Environment Challenges for Exploration of the Moon (NASA MSFC slides) | Moon day–night swing reference, 300 K | <https://ntrs.nasa.gov/citations/20080013552> | 2008-01-23 | one reference value (equator) | Minow, J. I., et al. (2008). NASA Marshall Space Flight Center. NTRS 20080013552. |
| NASA NSSDC Mars Fact Sheet | Mars mean temperature 214 K; Mars gravity | <https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html> | checked 2026-11-08 | one global value | NASA NSSDC Mars Fact Sheet |
| NASA NSSDC Moon Fact Sheet | Moon gravity 1.62 m/s² | <https://nssdc.gsfc.nasa.gov/planetary/factsheet/moonfact.html> | checked 2026-11-08 | one surface value | NASA NSSDC Moon Fact Sheet |
| NASA NSSDC Earth Fact Sheet | Earth gravity 9.81 m/s² (standard gravity 9.80665, rounded) | <https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html> | checked 2026-11-08 | one standard value | NASA NSSDC Earth Fact Sheet |
| NIST Cryogenic Material Properties (linear expansion fits) | Beam expansion coefficients (aluminum 6061-T6, 304 stainless steel, Ti-6Al-4V) | <https://trc.nist.gov/cryogenics/materials/materialproperties.htm> | fit coefficients copied 2026-11-09 | fits valid 4–300 K; α taken at 293 K | NIST Cryogenics Technologies Group |
| SpaceRef article on Mars temperature | second Mars temperature value (−60 °C), shown beside the NASA value | <https://spaceref.com/?p=24443> | could not be read on 2026-11-08 (HTTP 403); value as given by the team | one value | — |

The validation benchmarks quote four NASA pages and papers (NASA Science "10 Things to Know
About Planetary Analogs", the NASA ARADS page, NTRS 20100003844 and NTRS 20110008363); see
`REFERENCES.md`.

## Method

### 1. Measure each Earth site (Python scripts in `pipeline/`)

- **Temperature** (`thermal.py`): MODIS/Terra land surface temperature (MOD11A2 v061),
  one 1 km pixel per site, 8-day composites from 2022-12-27 to 2025-12-27. For each record:
  *swing = day temperature − night temperature*. A quality filter keeps only values with an
  average error of 1 K or less. The site's mean swing and mean temperature (of all kept day
  and night values) are reported.
- **Terrain** (`terrain.py`): SRTM 1 arc-second elevation (about 30.9 m × 28.3 m pixels at our
  sites), a 10 km × 10 km square per site. *Slope* comes from the 4 neighbours of each pixel;
  *roughness* is the standard deviation of the heights left after removing the best-fit tilted
  plane in each 3 × 3 window (about 93 m × 85 m). We report medians and the 90th percentile.

### 2. Set the references

| Reference | Value | Where it comes from |
|---|---|---|
| Moon day–night swing | 300 K | NASA Marshall Space Flight Center slides (about 400 K by day to under 100 K by night) |
| Moon slope (median) | 17.81° | LOLA 5 m heights of Site23, Malapert massif, averaged to 30 m, 90 m window |
| Moon roughness (median) | 0.36 m | the same map and window |
| Mars mean temperature | 214 K | NASA NSSDC Mars Fact Sheet |
| Gravity | Earth 9.81, Moon 1.62, Mars 3.71 m/s² | NASA NSSDC fact sheets (the Mars value is the team's; NSSDC lists 3.73 mean and 3.69 at the equator) |

LRO Diviner temperature maps of the lunar equator are shown as additional Moon references
(day median 331.9 K, night median 95.84 K) but are **not used in any score**: their pixels were
seen at unknown local times in different months (see Limits).

### 3. Score each comparison (`score.py`)

For one number, with *x*<sub>Earth</sub> the site's value and *x*<sub>ref</sub> the Moon or Mars value:

```
s = max(0, 1 − |x_Earth − x_ref| / τ)
```

- *s* = 1 means identical; *s* = 0 means the gap is τ (the tolerance) or more.
- **Labels:** strong if *s* ≥ 0.8, partial if 0.5 ≤ *s* < 0.8, weak if *s* < 0.5.
- **Tolerance τ**, one rule per comparison, set in `app/data/config.json`:

| Comparison | Rule | τ |
|---|---|---|
| Moon swing | τ = the Moon's swing itself, so *s* = the share of the Moon's swing a site reproduces | 300 K |
| Moon slope | sample standard deviation of the 3 sites' median slopes | 5.6° |
| Moon roughness | τ = the Moon's own median roughness | 0.36 m |
| Mars mean temperature | sample standard deviation of the 5 sites' mean temperatures | 23.92 K |

If the Earth value, the reference or τ is missing, there is no score: the comparison is
**not assessed**, never guessed. Sites are ranked by their gap to the reference (rank 1 =
smallest gap).

### 4. Check the scores (`validate.py`)

The same files and the same scoring code, with nothing tuned. Results below.

## Results

| Site | Moon swing | Mars mean temperature | Moon slope | Moon roughness |
|---|---|---|---|---|
| Mauna Kea | 23.58 K, weak (0.08), rank 1 of 5 | 287.37 K, weak (0.00), rank 4 of 5 | 13.94°, weak (0.31), rank 1 of 3 | 0.81 m, weak (0.00), rank 3 of 3 |
| Atacama Desert | 22.24 K, weak (0.07), rank 2 of 5 | 297.32 K, weak (0.00), rank 5 of 5 | 5.37°, weak (0.00), rank 2 of 3 | 0.71 m, weak (0.03), rank 2 of 3 |
| Altiplano | 5.8 K, weak (0.02), rank 3 of 5 | 281.93 K, weak (0.00), rank 3 of 5 | 3.41°, weak (0.00), rank 3 of 3 | 0.71 m, weak (0.03), rank 1 of 3 |
| Haughton Crater | 2.06 K, weak (0.01), rank 4 of 5 | 251.14 K, weak (0.00), rank 2 of 5 | not assessed | not assessed |
| Dry Valleys | 0.86 K, weak (0.00), rank 5 of 5 | 242.37 K, weak (0.00), rank 1 of 5 | not assessed | not assessed |

References: Moon swing 300 K, Mars mean temperature 214 K, Moon slope 17.81°, Moon roughness
0.36 m. Altiplano and Atacama have the same median roughness (0.71 m); the page lists the
tie. Mean temperature against the Moon and swing, slope and roughness against Mars are
not assessed, because there is no reference value for them.

## Validation: the honest findings

1. **All scores are weak.** All 16 scored comparisons are labelled weak. The highest score is
   0.31 (Mauna Kea's slope against the Moon).
2. **Benchmarks.** We checked four sites that NASA sources already name as analogs: does each
   rank near the top (rank 1 or 2) for what it is known for?
   - Dry Valleys (Mars analog, NTRS 20100003844): rank 1 of 5 on Mars mean temperature. Near the top, but still weak.
   - Haughton Crater (Mars analog, NASA Science page): rank 2 of 5 on Mars mean temperature. Near the top, but still weak.
   - **Atacama Desert does not rank near the top.** It is named as a Mars analog (NASA Science
     page and the ARADS page), but on Mars mean temperature it ranks 5 of 5 (297.32 K against
     214 K, the largest gap of all five sites). **Why:** the sources name Atacama for extreme
     dryness and soil chemistry, which no number in this atlas measures.
   - **Mauna Kea does not rank near the top on roughness.** It is named as a lunar analog
     (NTRS 20110008363) and ranks 1 of 5 on the Moon swing and 1 of 3 on slope, but 3 of 3 on
     roughness (0.81 m against 0.36 m). **Why:** the source names Mauna Kea for lunar resource
     (ISRU) field testing, which no number in this atlas measures.
   We did not change any tolerance to move either site.
3. **Negative control (Amazon rainforest): pending.** The control request was not finished,
   so there is no control result. The page says so instead of showing a number.
4. **Single-metric check.** Mauna Kea is closer to the references than Atacama on 3 of 4 metrics,
   but Mauna Kea ranks 1 of 3 on slope and 3 of 3 on roughness, so one terrain metric alone does
   not show a terrain match.
5. **Sensitivity.** With every tolerance changed by −20% and +20%, 0 of the 16 labels change
   (they are all weak either way). The largest score change is 0.17. Ranking by gap never
   changes; at −20%, all five Moon-swing scores fall to 0 and tie.

What we would change (listed on the page, **not** applied): add metrics for dryness and soil
chemistry and for ISRU testing, finish the Amazon request and rerun `validate.py`, show the
scores beside the labels, and add a polar elevation dataset for Haughton Crater and Dry Valleys.

## Limits

- **What Earth cannot reproduce.** The best Earth swing (Mauna Kea, 23.58 K) is 7.9% of the
  Moon's 300 K. The closest site to Mars's mean temperature (Dry Valleys) is still 28.37 K warmer.
  Gravity is the same at every Earth site: a drop test on Earth can match the Moon's impact speed
  from a lower height, but it cannot reproduce the Moon's slower, longer fall. The same rover
  presses on the ground about 6.1 times harder on Earth than on the Moon (32.7 kPa against 5.4 kPa
  for the Try it starting example of 200 kg on 0.06 m²), so an Earth soil test overstates wheel
  sinkage, other things equal.
- **7.6 km Diviner pixels.** Each LRO Diviner pixel is 7580.8 m across at the equator, against
  1 km for the Earth MODIS data. Most Diviner pixels in our band are empty (20.52% have data by day,
  29.28% by night).
- **Local-time drift.** LRO's orbit gives a drift in local time across each Diviner map, and the
  files do not store the local time of each pixel: day values are somewhere between 06:00 and
  18:00, night values between 18:00 and 06:00, and the two maps cover different months. So the
  Diviner day-minus-night range (261.78 K) is not a daily swing. The Earth MODIS values are also
  8-day clear-sky averages at two times of day, not a true daily maximum minus minimum.
- **One Moon target.** The terrain reference is one 21 km × 21 km map: Site23, Malapert massif,
  near the lunar south pole, not the equator where the temperature reference applies. About
  90% of the polar 5 m LOLA pixels are interpolated, and LOLA's median slope error is about
  1.5–2.5°.
- **SRTM coverage 60° N to 56° S.** Haughton Crater (75.4° N) and Dry Valleys (77.5° S) are outside
  it, so their slope and roughness are not assessed.
- **Altiplano square 76.2 km from its thermal point.** The Altiplano thermal point (−20.0, −68.0)
  is the corner where four SRTM tiles meet, so its 10 km terrain square is centred at
  (−20.5, −68.5), inside one tile, 76,235 m from the thermal point. The map shows both.
- **No Mars terrain reference.** Slope and roughness against Mars are not assessed.
- **Slope depends on pixel size.** The Moon heights were averaged from 5 m to 30 m pixels to match
  SRTM; this smooths the surface (LOLA's own 5 m slope median is 17.86°, against 17.81° at 30 m).
- **Gravity Drop ignores air resistance.** It shows ideal falls; Earth's air and Mars's thin air
  would change real falls, and the Moon has none.
- **Mission Match rules are team rules.** The verdicts ("Best stand-in on this atlas" for rank 1,
  "Partial help" for rank 2, "Not useful for this" otherwise) are our choices; they reuse the
  existing rankings and add no new score. The same goes for the map colour bands, the Try it
  input limits and the "how engineers use it" rules: team choices, not measured data.
- **Material expansion.** One expansion coefficient at 293 K is used for every swing; the Moon's
  swing goes outside NIST's 4–300 K fit range.
- **Rover illustration.** It is a drawing, not a soil simulation: wheel size follows contact area
  (six equal wheels assumed), body size follows mass, and sinking depth is drawn in proportion
  to ground pressure.

## How to run it

The page needs no build step and no installation. From the project folder:

```
cd app
python3 -m http.server
```

Then open <http://localhost:8000/> in a browser. (The charts and the map load Chart.js and
Leaflet from public CDNs, so an internet connection is needed for those; the rest of the page
works without them.)

## How to rebuild the data (optional)

The JSON files the page reads are already in `app/data/`. To rebuild them you need the raw
datasets in `data/raw/` (not in git; see `REFERENCES.md` for where to get them) and a Python 3
environment with `numpy`, `rasterio` and `earthaccess` (we used numpy 2.5.4, rasterio 1.5.2
and earthaccess 0.19.0). The scripts, in order:

```
.venv/bin/python pipeline/thermal.py       # thermal.json
.venv/bin/python pipeline/terrain.py       # terrain.json
.venv/bin/python pipeline/moon_thermal.py  # moon_thermal.json
.venv/bin/python pipeline/moon_terrain.py  # moon_terrain.json
.venv/bin/python pipeline/score.py         # cards.json
.venv/bin/python pipeline/validate.py      # validation.json
```

`pipeline/get_tile.py` downloads an SRTM tile from NASA Earthdata (it needs an Earthdata login).

## Tests

```
.venv/bin/python -m pytest pipeline tests
```

There are 244 tests (pytest 9.2.0); all pass. The page tests open the page in headless
Microsoft Edge, Google Chrome or Chromium (whichever is installed); without one they are skipped.

- `pipeline/test_*.py` check the data pipeline: scoring, thermal and terrain methods, the Moon
  files, validation, the formulas worked out by hand (pressure, expansion, fall time, impact
  speed), and that the datasets, materials and benchmark sources are listed in `sources.json`.
- `tests/test_*.py` check the page: the start page, hub and every station, Back and Forward,
  the map (with a local tile server, so no internet is needed), Mission Match, Gravity Drop, the
  rover illustration, site names, contrast of 4.5:1 or more, phone layout, no sideways
  scrolling, no layout shift, no repaints while scrolling, reduced motion and no console errors.

## Project layout

```
app/              the web page: index.html, style.css and plain JavaScript (no frameworks)
app/data/         JSON files written by the pipeline and read by the page
app/data/sources.json   every dataset, with its source URL and citation
pipeline/         Python scripts that turn raw datasets into the JSON files, and their tests
tests/            tests of the page in a headless browser
notes/            notes on the Moon datasets
REFERENCES.md     every dataset, library, NASA page and paper used
```
