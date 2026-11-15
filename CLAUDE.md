# CLAUDE.md

## Project

The **Engineering Analog Atlas** is our entry for NASA Space Apps 2026. It is a
static web page that compares Earth sites with one Moon reference site and one
Mars reference site. It compares them using engineering numbers: slope,
roughness and temperature swing.

## Layout

```
pipeline/        Python scripts that turn raw datasets into small JSON files
app/             The web page: plain HTML, CSS and JavaScript
app/data/        JSON files written by the pipeline and read by the page
app/data/sources.json  Every dataset we use, with its source URL
```

## Rules

### 1. Units and context
- Use SI units (m, K, s, and so on) and degrees for angles.
- Every number must state the **window size** (the area it was measured over)
  and the **resolution** (meters per pixel) of the data behind it.
  Example: `slope_deg: 12.4, window_m: 100, resolution_m: 5`.

### 2. Every number has a source
- Every number traces back to a dataset listed in `app/data/sources.json`.
- Each entry in `sources.json` has a source URL.
- If a number cannot be traced to a listed dataset, it does not go in the app.

### 3. Never invent data
- If a value is missing or we have not measured it, write `null` in JSON, or
  the words **not assessed** on the page.
- Do not guess, estimate from memory, or fill gaps with typical values.
- List every missing value (which site, which metric) so we can see the gaps.

### 4. How the pieces fit
- Python scripts in `pipeline/` read datasets and write small JSON files to
  `app/data/`.
- The page in `app/` is plain HTML, CSS and JavaScript.
- No build step: no bundlers, no npm, no frameworks. Opening the HTML file
  (or serving the folder) must be enough.

### 5. Code style
- Keep code short and simple.
- Write comments that a high-school student can follow: say what each step
  does and why.
- Prefer clear names and plain loops over clever tricks.

### 6. Checking work
- After each task, run the check the user describes for that task.
- Report the result in one line, for example:
  `Check: python pipeline/build.py -> wrote 3 files, 0 errors.`
- If the check fails or could not be run, say so in that line.
