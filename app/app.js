// app.js - the start page, hub and stations of Rehearsal Earth.
// It reads the JSON files in data/ (made by the Python pipeline) and draws, on each
// tab: the references, bar charts and a card for the chosen site; plus a shared
// sources table.

let DATA = {};       // the JSON files, once loaded
let chart = null;    // swing chart (Chart.js)
let chart2 = null;   // mean temperature chart (Chart.js)
let siteOrder = [];  // site names, in the order shown in the swing chart
let tempOrder = [];  // site names, in the order shown in the temperature chart
let terrainOrder = [];  // site names, in the order shown in the terrain charts
let slopeChart = null;  // median slope chart (Terrain tab)
let roughChart = null;  // median roughness chart (Terrain tab)
let selectedSite = null;  // the site picked with the buttons

// ---- Small helpers ----------------------------------------------------------

// Show a number with its unit, or "not assessed" if it is missing (null).
function fmt(value, unit) {
  return value === null || value === undefined ? "not assessed" : `${value} ${unit}`;
}

// A score label with its score next to it, e.g. "weak (0.07)"; the score is shown, never recomputed.
function labelScore(label, score) {
  return score === null || score === undefined ? label : `${label} (${score.toFixed(2)})`;
}

// A collapsed section: a heading with a "Show details" control, closed by default.
// <details> works with the keyboard (Tab, then Enter or Space) and prints when open.
function collapsible(title, content) {
  const d = el("details", "more");
  const summary = el("summary");
  summary.append(el("span", "more-title", title), el("span", "more-action", "Show details"));
  d.append(summary, content);
  return d;
}

// Make a page element: el("p", "note", "text") -> <p class="note">text</p>
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// A clickable link that opens in a new tab.
function link(url) {
  const a = el("a", "", url);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

// A short link for the Sources table: "host / file", e.g.
// "pgda.gsfc.nasa.gov / Site23_final_adj_5mpp_surf.tif". The full URL stays in the
// link's title (shown on hover) and in hidden text that screen readers read.
function shortLink(url) {
  const u = new URL(url);
  const parts = u.pathname.split("/").filter((p) => p !== "");     // path pieces, no empty ones
  let name = parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  name += u.search;                                                 // keep "?p=…" pages apart
  const label = name ? `${u.hostname} / ${name}` : u.hostname;
  const a = link(url);
  a.textContent = "";
  a.title = url;
  a.className = "short-url";
  const seen = el("span", "", label);
  seen.setAttribute("aria-hidden", "true");                         // screen readers skip the short label...
  a.append(seen, el("span", "sr-only", url));                       // ...and read the full URL instead
  return a;
}

// ---- Progressive disclosure: "Show the numbers" and "Show details" buttons -----------
// Each button opens or closes the element named in its aria-controls by adding the
// class "is-open" (style.css hides closed content). Nothing is ever removed from the page.
// Card boxes are rebuilt when another site is picked, so which ones are open is kept
// here, in memory only (it is forgotten when the page reloads).
const openBoxes = new Set();
let revealCount = 0;   // gives every button made by the code its own id to point at

function revealButton(targetId, what, kind = "numbers") {
  const b = el("button", "reveal-btn");
  b.type = "button";
  b.dataset.kind = kind;
  b.setAttribute("aria-controls", targetId);
  b.setAttribute("aria-expanded", "false");
  b.append(el("span", "reveal-action", kind === "details" ? "Show details" : "Show the numbers"),
    el("span", "reveal-what", ` · ${what}`));
  return b;
}

// "target" can be passed in when the button and its target are not on the page yet.
function setRevealOpen(button, open, target = document.getElementById(button.getAttribute("aria-controls"))) {
  target.classList.toggle("is-open", open);
  button.setAttribute("aria-expanded", String(open));
  const details = button.dataset.kind === "details";
  button.querySelector(".reveal-action").textContent =
    open ? (details ? "Hide details" : "Hide the numbers") : (details ? "Show details" : "Show the numbers");
  if (button.dataset.remember) {
    if (open) openBoxes.add(button.dataset.remember); else openBoxes.delete(button.dataset.remember);
  }
}

function setUpReveals() {
  document.addEventListener("click", (e) => {
    const button = e.target.closest(".reveal-btn");
    if (button) setRevealOpen(button, button.getAttribute("aria-expanded") !== "true");
  });
}

// Read a color from the CSS variables, so the chart follows light/dark mode.
function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ---- 1. References -------------------------------------------------------------

function showReferences() {
  const moon = DATA.config.references.moon.thermal_swing_K;
  const slides = DATA.sources[moon.source_id];
  document.getElementById("thermal-key").textContent =
    `Key caveat: the Moon's ${moon.value} K swing is a reference value from NASA slides ` +
    `(${slides.organization}, ${slides.date.slice(0, 4)}), not a measurement.`;
  const mars = DATA.config.references.mars.mean_temperature_K;
  const box = document.getElementById("refs");

  const items = [
    ["Moon, equator: day–night swing", fmt(moon.value, "K"), moon.detail, moon.source_url],
    ["Mars, global mean temperature", fmt(mars.value, "K"),
      `${mars.detail}; second source: ${mars.second_source.value_C} °C`, mars.source_url],
  ];
  for (const [title, value, detail, url] of items) {
    const ref = el("div", "ref");
    ref.append(el("div", "small", title), el("div", "big", value), el("div", "small", detail));
    const src = el("div", "small", "Source: ");
    src.append(link(url));
    ref.append(src);
    box.append(ref);
  }
}

// ---- 2. Bar chart --------------------------------------------------------------

function showChart() {
  const sites = DATA.thermal.sites;
  const lunar = DATA.config.references.moon.thermal_swing_K.value;

  // Biggest swing first. Sites with no swing (null) go last.
  siteOrder = Object.keys(sites).sort(
    (a, b) => (sites[b].mean_swing.K ?? -1) - (sites[a].mean_swing.K ?? -1));

  const labels = ["Moon (reference)", ...siteOrder.map(siteName)];   // names.js turns keys into names
  const values = [lunar, ...siteOrder.map((s) => sites[s].mean_swing.K)];

  chart = new Chart(document.getElementById("chart"), {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: barColors(null), borderRadius: 4 }] },
    options: {
      indexAxis: "y",              // horizontal bars: easier to read on a phone
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const v = ctx.raw;
              if (v === null) return "not assessed";
              return ctx.dataIndex === 0 ? `${v} K` : `${v} K = ${(100 * v / lunar).toFixed(1)}% of the Moon's swing`;
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, title: { display: true, text: "Mean day–night swing (K)", color: cssColor("--muted") },
             ticks: { color: cssColor("--muted") }, grid: { color: cssColor("--line") } },
        y: { ticks: { color: cssColor("--text") }, grid: { display: false } },
      },
      // Clicking a site's bar opens its card.
      onClick: (event, bars) => {
        if (bars.length && bars[0].index > 0) selectSite(siteOrder[bars[0].index - 1]);
      },
    },
  });

  const r = DATA.thermal.resolution;
  document.getElementById("chart-note").textContent =
    `Earth bars: mean of day minus night land surface temperature, ${r.pixel}, ${r.window}, ` +
    `${r.time_window}, ${r.period[0]} to ${r.period[1]}. Tap a bar or a button below to open a site.`;
}

// Moon bar orange (the reference colour), site bars in the station's colour
// (amber for Thermal, teal for Terrain); the chosen site is fully coloured, the others lighter.
function barColors(selected) {
  return [cssColor("--moon"), ...siteColors(siteOrder, selected, "--c-thermal")];
}

function siteColors(order, selected, colourVar) {
  const colour = cssColor(colourVar);
  return order.map((s) => (selected && s !== selected ? colour + "66" : colour));
}

// A Chart.js plugin that draws one dashed vertical line, e.g. "Mars 214 K".
const referenceLine = {
  id: "referenceLine",
  afterDatasetsDraw(c, args, opts) {
    const x = c.scales.x.getPixelForValue(opts.value);
    const { top, bottom } = c.chartArea;
    const ctx = c.ctx;
    ctx.save();
    ctx.strokeStyle = opts.color;
    ctx.fillStyle = opts.color;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.font = "600 12px system-ui, sans-serif";
    ctx.fillText(opts.label, x + 6, top + 12);
    ctx.restore();
  },
};

// ---- 2b. Mean temperature chart with the Mars line ------------------------------

function showTempChart() {
  const sites = DATA.thermal.sites;
  const mars = DATA.config.references.mars.mean_temperature_K.value;

  // Coldest first (closest to Mars). Sites with no value (null) go last.
  tempOrder = Object.keys(sites).sort(
    (a, b) => (sites[a].mean_temperature.K ?? Infinity) - (sites[b].mean_temperature.K ?? Infinity));

  chart2 = new Chart(document.getElementById("chart2"), {
    type: "bar",
    data: {
      labels: tempOrder.map(siteName),
      datasets: [{ data: tempOrder.map((s) => sites[s].mean_temperature.K),
                   backgroundColor: siteColors(tempOrder, null, "--c-thermal"), borderRadius: 4 }],
    },
    plugins: [referenceLine],
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        referenceLine: { value: mars, label: `Mars ${mars} K`, color: cssColor("--moon") },
        tooltip: {
          callbacks: {
            // Every number shown comes from thermal.json or cards.json.
            label: (ctx) => {
              const site = tempOrder[ctx.dataIndex];
              const t = sites[site].mean_temperature;
              const row = DATA.cards.cards.find((c) => c.site === site).comparisons
                .find((r) => r.body === "mars" && r.metric === "mean_temperature_K");
              return t.K === null ? "not assessed" : `${t.K} K (${t.C} °C), gap to Mars ${row.gap} K`;
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, title: { display: true, text: "Mean temperature (K)", color: cssColor("--muted") },
             ticks: { color: cssColor("--muted") }, grid: { color: cssColor("--line") } },
        y: { ticks: { color: cssColor("--text") }, grid: { display: false } },
      },
      onClick: (event, bars) => {
        if (bars.length) selectSite(tempOrder[bars[0].index]);
      },
    },
  });

  const r = DATA.thermal.resolution;
  const m = DATA.config.references.mars.mean_temperature_K;
  document.getElementById("chart2-note").textContent =
    `Earth bars: mean of all kept day and night land surface temperatures, ${r.pixel}, ${r.window}, ` +
    `${r.time_window}, ${r.period[0]} to ${r.period[1]}; clear-sky only, so not a true 24-hour mean. ` +
    `Dashed line: Mars, ${m.detail}.`;
}

// ---- 3. Site buttons and the card -------------------------------------------

function showSiteButtons(boxId, order) {
  const box = document.getElementById(boxId);
  for (const site of order) {
    const b = el("button", "", siteName(site));
    b.dataset.site = site;
    b.setAttribute("aria-pressed", "false");
    b.addEventListener("click", () => selectSite(site));
    box.append(b);
  }
}

function selectSite(site) {
  selectedSite = site;
  for (const b of document.querySelectorAll("#sites button, #terrain-sites button, #tryit-sites button")) {
    b.setAttribute("aria-pressed", String(b.dataset.site === site));
  }
  chart.data.datasets[0].backgroundColor = barColors(site);
  chart.update();
  chart2.data.datasets[0].backgroundColor = siteColors(tempOrder, site, "--c-thermal");
  chart2.update();
  for (const c of [slopeChart, roughChart]) {
    c.data.datasets[0].backgroundColor = [cssColor("--moon"), ...siteColors(terrainOrder, site, "--c-terrain")];
    c.update();
  }
  highlightMarker(site);
  showCard(site);
  showTerrainCard(site);
  updateTryIt();   // the expansion sentence compares the Moon with this site
}

function showCard(site) {
  const card = DATA.cards.cards.find((c) => c.site === site);
  const t = DATA.thermal.sites[site];
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  const swing = t.mean_swing.K;

  const root = el("article", "card");

  // Heading with the site's key numbers.
  const head = el("div", "card-head");
  head.append(el("h3", "", siteLongName(site)));
  const pct = swing === null ? "" : ` (${(100 * swing / lunar).toFixed(1)}% of the Moon's)`;
  head.append(el("p", "",
    `${t.latitude}°, ${t.longitude}° · mean swing ${fmt(swing, "K")}${pct} · ` +
    `mean temperature ${fmt(t.mean_temperature.K, "K")} (${fmt(t.mean_temperature.C, "°C")}) · ` +
    `${t.records_with_swing} of ${t.records} 8-day records with a swing`));
  root.append(head);
  hideCardNumbers(head, "thermal");
  fillCard(root, card, "thermal");
  document.getElementById("card").replaceChildren(root);
}

// The line of raw numbers under a card's site name goes behind "Show the numbers".
function hideCardNumbers(head, which) {
  const numbers = head.querySelector("p");
  const wrap = el("div", "reveal");
  wrap.id = `card-numbers-${++revealCount}`;
  numbers.replaceWith(wrap);
  wrap.append(numbers);
  const b = revealButton(wrap.id, "this site's figures");
  b.dataset.remember = `${which}:figures`;
  head.insertBefore(b, wrap);
  if (openBoxes.has(b.dataset.remember)) setRevealOpen(b, true, wrap);
}

// A list that shows its first line; the other lines wait behind "Show details".
// "remember" names the list, so it stays open when another site is picked.
function shortList(box, lines, remember) {
  const ul = el("ul");
  lines.forEach((line, i) => ul.append(el("li", i === 0 ? "" : "more-line", line)));
  ul.id = `list-${++revealCount}`;
  ul.classList.add("short-list");
  box.append(ul);
  if (lines.length > 1) {
    const b = revealButton(ul.id, `${lines.length - 1} more`, "details");
    b.dataset.remember = remember;
    box.append(b);
    if (openBoxes.has(remember)) setRevealOpen(b, true, ul);
  }
}

// The four boxes (filled straight from cards.json) and the Earth-limits strip.
// Used by the Thermal card and the Terrain card ("which" says which one).
function fillCard(root, boxesFrom, which) {
  const boxes = el("div", "boxes");
  const parts = [
    ["Strong match", "strong", boxesFrom.strong_match],
    ["Breaks down", "breaks", boxesFrom.breaks_down],
    ["Not testable on Earth", "", boxesFrom.not_testable_on_earth],
    ["How engineers use it", "", boxesFrom.how_engineers_use_it],
  ];
  for (const [title, cls, lines] of parts) {
    const box = el("div", `box ${cls}`);
    box.append(el("h4", "", title));
    shortList(box, lines, `${which}:${title}`);
    boxes.append(box);
  }
  root.append(boxes);

  // The Earth-limits strip: the same on every card.
  root.append(earthLimitsStrip(which));
}

function earthLimitsStrip(which) {
  const g = DATA.config.gravity_m_s2;
  const strip = el("div", "strip");
  strip.append(el("strong", "", "What no Earth site can reproduce"));
  shortList(strip, [
    `Gravity: Earth ${g.earth.value} m/s² vs Moon ${g.moon.value} m/s² and Mars ${g.mars.value} m/s².`,
    "Vacuum: the Moon has almost no atmosphere; Earth's air carries heat and drag.",
    "Thin atmosphere: Mars's air is far thinner than Earth's.",
    "Radiation: Earth's atmosphere and magnetic field shield the surface from much of the space radiation that reaches the Moon and Mars.",
  ], `${which}:limits`);
  return strip;
}

// ---- 3b. "Try it" panel ------------------------------------------------------------
// The formulas themselves are in formulas.js. Gravity, alpha and the swings all
// come from the JSON files; only mass, area, material and length are typed in.

// Read a number box; an empty or bad box gives null.
function readInput(id) {
  const text = document.getElementById(id).value;
  return text.trim() === "" ? null : Number(text);
}

// Write alpha as "22.6×10⁻⁶ /K" so it is easy to read.
function fmtAlpha(alpha) {
  return `${Number((alpha * 1e6).toPrecision(3))}×10⁻⁶ /K`;
}

// One result line: a bold value and the worked sum under it.
function resultItem(title, value, worked) {
  const li = el("li");
  li.append(el("span", "", `${title}: `), el("span", "val", value));
  if (worked) li.append(el("span", "worked", worked));
  return li;
}

// Check a number box against its limits in config.json. Shows a short message
// under the box and returns the number, or null if it is empty or unrealistic.
function checkedInput(id, limits, unit) {
  const value = readInput(id);
  const message = rangeMessage(value, limits.min, limits.max, unit);
  document.getElementById(id.replace("in-", "msg-")).textContent = message || "";
  document.getElementById(id).setAttribute("aria-invalid", String(message !== null));
  return message === null ? value : null;
}

// The site with the lowest mean temperature in thermal.json (sites with no value are skipped).
function coldestSite() {
  let coldest = null;
  for (const [site, t] of Object.entries(DATA.thermal.sites)) {
    const k = t.mean_temperature.K;
    if (k === null) continue;
    if (coldest === null || k < DATA.thermal.sites[coldest].mean_temperature.K) coldest = site;
  }
  return coldest;
}

function setUpTryIt() {
  const select = document.getElementById("in-material");
  for (const [key, mat] of Object.entries(DATA.config.materials)) {
    const option = el("option", "", mat.name);
    option.value = key;
    select.append(option);
  }
  select.value = "aluminum";   // starting example: aluminum beam

  // Let the browser know the limits too (from config.json).
  const lim = DATA.config.try_it_limits;
  for (const [id, key] of [["in-mass", "mass_kg"], ["in-area", "area_m2"], ["in-length", "length_m"]]) {
    document.getElementById(id).min = lim[key].min;
    document.getElementById(id).max = lim[key].max;
  }
  for (const id of ["in-mass", "in-area", "in-material", "in-length"]) {
    document.getElementById(id).addEventListener("input", updateTryIt);
  }
  setUpRover();
  updateTryIt();
}

function updateTryIt() {
  const lim = DATA.config.try_it_limits;
  const mass = checkedInput("in-mass", lim.mass_kg, "kg");
  const area = checkedInput("in-area", lim.area_m2, "m²");
  const length = checkedInput("in-length", lim.length_m, "m");
  const mat = DATA.config.materials[document.getElementById("in-material").value];

  // (1) Ground pressure on Earth, the Moon and Mars, shown in kPa with 1 decimal.
  const g = DATA.config.gravity_m_s2;
  const pressureList = document.getElementById("out-pressure");
  const shown = {};   // the kPa values as displayed, used by the sentence
  const pressuresPa = {};   // the same pressures in Pa, used by the rover drawing
  pressureList.replaceChildren();
  for (const [body, label] of [["earth", "Earth"], ["moon", "Moon"], ["mars", "Mars"]]) {
    const p = mass === null || area === null ? null : groundPressurePa(mass, g[body].value, area);
    pressuresPa[body] = p;
    if (p === null) {
      pressureList.append(resultItem(label, "check the mass and area above"));
    } else {
      shown[body] = shownKpa(p);
      pressureList.append(resultItem(label, `${shown[body]} kPa`,
        `${mass} kg × ${g[body].value} m/s² ÷ ${area} m² ÷ 1000 = ${shown[body]} kPa`));
    }
  }
  document.getElementById("pressure-sentence").textContent =
    Object.keys(shown).length === 3 ? pressureSentence(shown.earth, shown.moon, shown.mars) : "";
  if (Object.keys(shown).length < 3) {
    setLead("tryit", "–", "Enter a rover mass and a contact area to compare Earth with the Moon.");
  } else if (shown.moon === 0) {
    setLead("tryit", "–", "These pressures are too small to compare at the precision shown.");
  } else {
    const times = (shown.earth / shown.moon).toFixed(1);
    setLead("tryit", `${times}×`, `On Earth this rover presses ${times} times harder on the ground than it would on the Moon.`);
  }
  updateRover(mass, area, length, pressuresPa);
  document.getElementById("pressure-note").textContent =
    `g from config.json (NASA fact sheets): Earth ${g.earth.value}, Moon ${g.moon.value}, Mars ${g.mars.value} m/s². ` +
    "Assumes the rover stands still with its weight spread evenly over the contact area.";

  // (2) Thermal expansion for the Moon's swing and each site's mean swing.
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  const rows = [["Moon", "Moon (reference swing)", lunar]];
  for (const site of siteOrder) rows.push([site, siteName(site), DATA.thermal.sites[site].mean_swing.K]);

  const expList = document.getElementById("out-expansion");
  const shownMmBy = {};   // the mm values as displayed, used by the sentence
  expList.replaceChildren();
  for (const [key, name, swing] of rows) {
    const dL = length === null ? null : expansionMm(mat.alpha_per_K, length, swing);
    if (swing === null) {
      shownMmBy[key] = null;
      expList.append(resultItem(name, "not assessed (no measured swing)"));
    } else if (dL === null) {
      expList.append(resultItem(name, "check the beam length above"));
    } else {
      shownMmBy[key] = shownMm(dL);
      expList.append(resultItem(name, `${shownMmBy[key]} mm`,
        `${fmtAlpha(mat.alpha_per_K)} × ${length} m × ${swing} K × 1000 mm/m = ${shownMmBy[key]} mm`));
    }
  }
  // The sentence compares the Moon with the site picked above ("Pick a site").
  const site = selectedSite || siteOrder[0];
  const cold = coldestSite();
  document.getElementById("expansion-sentence").textContent =
    length === null ? "" : expansionSentence(siteName(site), shownMmBy.Moon, shownMmBy[site],
      cold === null ? null : siteName(cold), shownMmBy[cold]);

  const r = DATA.thermal.resolution;
  const note = document.getElementById("expansion-note");
  note.replaceChildren(
    `α for ${mat.name} = ${fmtAlpha(mat.alpha_per_K)}, the slope of NIST's expansion fit at ` +
    `${DATA.config.materials_note.temperature_K} K (fit covers ${DATA.config.materials_note.fit_range_K.join("–")} K). ` +
    `Earth ΔT = mean day–night swing, ${r.pixel}, ${r.window}, ${r.time_window}, ${r.period[0]} to ${r.period[1]}; ` +
    `Moon ΔT = ${lunar} K. The Moon's swing goes outside the fit range and α is smaller when cold, ` +
    "so the Moon line is a constant-α estimate. Pick a site above to change the comparison. Source: ");
  note.append(link(mat.source_url));
}

// ---- 3b1. The rover illustration (Try it) -----------------------------------------------
// A generic six-wheel rover drawn with CSS 3D transforms: every part is a "box" made of six
// flat faces turned into place. The sizes come from rover.js (roverScales, roverSizesPx),
// and the three ground scenes under it use sinkDepths with the pressures of the calculator.
// Coordinates in px: x points forward, y points down (as on screen), z points to the viewer,
// and the ground is at y = 0.

const ROVER_VIEW_START = { x: -18, y: -34 };   // tilt and turn of the camera, in degrees
const roverView = { x: ROVER_VIEW_START.x, y: ROVER_VIEW_START.y };
const roverParts = {};   // name -> box, made once by setUpRover
const roverScene = {};   // world -> the SVG pieces of its ground scene
const SCENE_GROUND_Y = 48;   // the ground line of each scene, in scene units
const MAST_PX = { height: 46, head: [16, 9, 12] };   // the mast keeps one size (team choice)

// One box: a holder that is moved into place, and six faces.
function makeBox(cls) {
  const holder = el("div", "rv-part " + cls);
  const faces = {};
  for (const side of ["front", "back", "left", "right", "top", "bottom"]) {
    faces[side] = el("div", "rv-face rv-" + side);
    holder.append(faces[side]);
  }
  document.getElementById("rover-3d").append(holder);
  return { holder, faces };
}

// Put a box with its centre at (x, y, z), of size X (length) by Y (height) by Z (width),
// tilted by tilt degrees (positive: front end down).
function placeBox(box, x, y, z, X, Y, Z, tilt = 0) {
  box.holder.style.transform = `translate3d(${x}px, ${y}px, ${z}px) rotateZ(${tilt}deg)`;
  const face = (f, w, h, turn) => {
    f.style.width = `${w}px`;
    f.style.height = `${h}px`;
    f.style.left = `${-w / 2}px`;
    f.style.top = `${-h / 2}px`;
    f.style.transform = turn;
  };
  face(box.faces.front, X, Y, `translateZ(${Z / 2}px)`);
  face(box.faces.back, X, Y, `rotateY(180deg) translateZ(${Z / 2}px)`);
  face(box.faces.right, Z, Y, `rotateY(90deg) translateZ(${X / 2}px)`);
  face(box.faces.left, Z, Y, `rotateY(-90deg) translateZ(${X / 2}px)`);
  face(box.faces.top, X, Z, `rotateX(90deg) translateZ(${Y / 2}px)`);
  face(box.faces.bottom, X, Z, `rotateX(-90deg) translateZ(${Y / 2}px)`);
}

// One wheel: two round sides and a tread of flat strips around the axle (the z axis).
const TREAD_STRIPS = 10;
function makeWheel() {
  const holder = el("div", "rv-part rv-wheel");
  const sides = [el("div", "rv-disc"), el("div", "rv-disc")];
  const strips = [];
  for (let i = 0; i < TREAD_STRIPS; i++) strips.push(el("div", "rv-tread"));
  holder.append(...strips, ...sides);
  document.getElementById("rover-3d").append(holder);
  return { holder, sides, strips };
}

function placeWheel(wheel, x, y, z, diameter, width) {
  wheel.holder.style.transform = `translate3d(${x}px, ${y}px, ${z}px)`;
  wheel.sides.forEach((d, i) => {
    d.style.width = d.style.height = `${diameter}px`;
    d.style.left = d.style.top = `${-diameter / 2}px`;
    d.style.transform = `translateZ(${(i === 0 ? 1 : -1) * width / 2}px)`;
  });
  // Each strip lies flat at the bottom of the circle, then is turned around the axle.
  const strip = (Math.PI * diameter) / TREAD_STRIPS + 1;   // + 1 px so the strips touch
  wheel.strips.forEach((t, i) => {
    t.style.width = `${strip}px`;
    t.style.height = `${width}px`;
    t.style.left = `${-strip / 2}px`;
    t.style.top = `${-width / 2}px`;
    t.style.transform = `rotateZ(${(360 * i) / TREAD_STRIPS}deg) translateY(${diameter / 2}px) rotateX(90deg)`;
  });
}

// SVG pieces are made with createElementNS (plain createElement does not draw in SVG).
function svg(tag, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
}

function setUpRover() {
  // The 3D model: ground, body, deck, mast and camera head, boom arm and hand,
  // two side rockers with a strut each, and six wheels.
  const ground = el("div", "rv-ground");
  document.getElementById("rover-3d").append(ground);
  for (const name of ["body", "deck", "mast", "head", "boom", "hand", "rockerL", "rockerR", "strutL", "strutR"]) {
    roverParts[name] = makeBox("rv-" + name.replace(/[LR]$/, ""));
  }
  roverParts.wheels = [];
  for (let i = 0; i < ROVER_WHEELS; i++) roverParts.wheels.push(makeWheel());

  // The three ground scenes: a side view of the rover with its wheels in the ground.
  const list = document.getElementById("rover-scenes");
  for (const [world, label] of [["earth", "Earth"], ["moon", "Moon"], ["mars", "Mars"]]) {
    const li = el("li", "rover-scene");
    li.dataset.world = world;
    const pic = svg("svg", { viewBox: "0 0 140 70", class: "scene-svg", "aria-hidden": "true", focusable: "false" });
    const rover = svg("g", { class: "scene-rover" });
    // Unit shapes, sized and moved with CSS transforms so they change smoothly.
    const body = svg("rect", { x: -0.5, y: -0.5, width: 1, height: 1, class: "scene-body" });
    const mast = svg("rect", { x: -0.5, y: -1, width: 1, height: 1, class: "scene-body" });
    const wheels = [0, 1, 2].map(() => svg("circle", { cx: 0, cy: 0, r: 1, class: "scene-wheel" }));
    rover.append(mast, body, ...wheels);
    // The ground is drawn after the rover, so it covers the part of each wheel below its surface.
    const soil = svg("rect", { x: 0, y: SCENE_GROUND_Y, width: 140, height: 70 - SCENE_GROUND_Y, class: "scene-soil" });
    const surface = svg("line", { x1: 0, y1: SCENE_GROUND_Y, x2: 140, y2: SCENE_GROUND_Y, class: "scene-surface" });
    pic.append(rover, soil, surface);
    const name = el("p", "scene-name", label);
    const kpa = el("p", "scene-kpa");
    li.append(name, pic, kpa);
    list.append(li);
    roverScene[world] = { rover, body, mast, wheels, kpa };
  }

  // Turning the model: drag with a mouse, pen or finger, or use the arrow keys.
  const stage = document.getElementById("rover-stage");
  let last = null;   // where the pointer was on the previous move
  stage.addEventListener("pointerdown", (e) => {
    last = { x: e.clientX, y: e.clientY };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("is-dragging");
  });
  stage.addEventListener("pointermove", (e) => {
    if (last === null) return;
    turnRover(-(e.clientY - last.y) * 0.3, (e.clientX - last.x) * 0.5);
    last = { x: e.clientX, y: e.clientY };
  });
  const stop = () => { last = null; stage.classList.remove("is-dragging"); };
  stage.addEventListener("pointerup", stop);
  stage.addEventListener("pointercancel", stop);   // for example when a finger starts scrolling the page
  stage.addEventListener("keydown", (e) => {
    const steps = { ArrowLeft: [0, -10], ArrowRight: [0, 10], ArrowUp: [-5, 0], ArrowDown: [5, 0] };
    if (!steps[e.key]) return;
    e.preventDefault();   // the arrow keys turn the model instead of scrolling the page
    turnRover(steps[e.key][0], steps[e.key][1]);
  });
  document.getElementById("rover-reset").addEventListener("click", () => {
    roverView.x = ROVER_VIEW_START.x;
    roverView.y = ROVER_VIEW_START.y;
    showRoverView();
  });
  showRoverView();
}

// Turn the camera by dx degrees of tilt and dy degrees around the vertical axis.
// The tilt stays between looking from the side and looking steeply down.
function turnRover(dx, dy) {
  roverView.x = clamp(roverView.x + dx, -70, 5);
  roverView.y = (roverView.y + dy) % 360;
  showRoverView();
}

function showRoverView() {
  const turn = document.getElementById("rover-turn");
  turn.style.transform = `rotateX(${roverView.x}deg) rotateY(${roverView.y}deg)`;
  turn.dataset.view = `${Math.round(roverView.x)},${Math.round(roverView.y)}`;
}

// Redraw the model, the scenes and the text description from the calculator inputs.
// mass, area and length are null when that box is empty or unrealistic; pressuresPa
// holds the calculator's pressures in Pa (null when they cannot be worked out).
function updateRover(mass, area, length, pressuresPa) {
  const scales = roverScales(mass, area, length);
  const px = roverSizesPx(scales);
  const P = roverParts;
  const D = px.wheelDiameter, W = px.wheelWidth;

  // Wheels: three on each side, spaced so they never touch each other.
  const pitch = Math.max(0.42 * px.bodyLength, 1.15 * D);
  const sideZ = px.bodyWidth / 2 + W / 2 + 4;
  const xs = [-pitch, 0, pitch];
  P.wheels.forEach((w, i) => placeWheel(w, xs[i % 3], -D / 2, i < 3 ? sideZ : -sideZ, D, W));
  // Side rockers through the wheel hubs, and a strut from each rocker up to the body.
  const bodyBottom = -(D + 6);
  const bodyY = bodyBottom - px.bodyHeight / 2;
  const bodyTop = bodyBottom - px.bodyHeight;
  for (const [r, s, z] of [[P.rockerL, P.strutL, sideZ - W / 2 - 2], [P.rockerR, P.strutR, -(sideZ - W / 2 - 2)]]) {
    placeBox(r, 0, -D / 2, z, 2 * pitch, 4, 4);
    placeBox(s, 0, (bodyBottom - D / 2) / 2, z, 5, D / 2 + 6, 4);
  }
  // Body with a slightly wider deck on top.
  placeBox(P.body, 0, bodyY, 0, px.bodyLength, px.bodyHeight, px.bodyWidth);
  placeBox(P.deck, 0, bodyTop - 2, 0, px.bodyLength * 1.06, 4, px.bodyWidth * 1.12);
  // Mast near the front on one side, with a small camera head on top.
  const mastX = px.bodyLength * 0.3, mastZ = -px.bodyWidth * 0.25;
  placeBox(P.mast, mastX, bodyTop - 4 - MAST_PX.height / 2, mastZ, 5, MAST_PX.height, 5);
  const [hx, hy, hz] = MAST_PX.head;
  placeBox(P.head, mastX + 3, bodyTop - 4 - MAST_PX.height - hy / 2, mastZ, hx, hy, hz);
  // Boom arm from the front of the body, its length set by the beam length, tilted 20° down.
  const tilt = 20, rad = (tilt * Math.PI) / 180;
  const shoulderX = px.bodyLength / 2, shoulderY = bodyY + px.bodyHeight * 0.15, armZ = px.bodyWidth * 0.2;
  placeBox(P.boom, shoulderX + (px.boomLength / 2) * Math.cos(rad), shoulderY + (px.boomLength / 2) * Math.sin(rad),
    armZ, px.boomLength, 5, 5, tilt);
  placeBox(P.hand, shoulderX + px.boomLength * Math.cos(rad), shoulderY + px.boomLength * Math.sin(rad), armZ, 9, 9, 9, tilt);

  // Centre the whole rover in the stage (it is longer at the front because of the boom).
  const front = shoulderX + px.boomLength * Math.cos(rad) + 5, rear = -(pitch + D / 2);
  const top = bodyTop - 4 - MAST_PX.height - hy;
  const model = document.getElementById("rover-3d");
  model.style.transform = `translate3d(${-(front + rear) / 2}px, ${-top / 2}px, 0)`;
  // The ground under the rover grows with it.
  const ground = model.querySelector(".rv-ground");
  const gl = 2 * (pitch + D) + 80, gw = 2 * sideZ + W + 80;
  ground.style.width = `${gl}px`;
  ground.style.height = `${gw}px`;
  ground.style.left = `${-gl / 2}px`;
  ground.style.top = `${-gw / 2}px`;

  const stage = document.getElementById("rover-stage");
  stage.dataset.state = scales.neutral ? "neutral" : "ready";
  stage.dataset.boom = scales.boomNeutral ? "neutral" : "ready";
  stage.dataset.sizes = JSON.stringify({ scales, px });   // read by the tests

  // The ground scenes: the side view at SCENE_SCALE, each sinking by its world's pressure.
  const valid = !scales.neutral && ["earth", "moon", "mars"].every((w) => isNumber(pressuresPa[w]));
  const sD = D * SCENE_SCALE, sPitch = pitch * SCENE_SCALE;
  const depths = valid ? sinkDepths(pressuresPa, sD) : { earth: 0, moon: 0, mars: 0, factor: 0 };
  const sBodyL = px.bodyLength * SCENE_SCALE, sBodyH = px.bodyHeight * SCENE_SCALE;
  for (const [world, sc] of Object.entries(roverScene)) {
    const depth = depths[world];
    sc.rover.style.transform = `translate(70px, ${SCENE_GROUND_Y + depth}px)`;
    sc.wheels.forEach((c, i) => { c.style.transform = `translate(${(i - 1) * sPitch}px, ${-sD / 2}px) scale(${sD / 2})`; });
    const bodyCy = -(sD + 3 + sBodyH / 2);
    sc.body.style.transform = `translate(0px, ${bodyCy}px) scale(${sBodyL}, ${sBodyH})`;
    sc.mast.style.transform = `translate(${sBodyL * 0.3}px, ${bodyCy - sBodyH / 2}px) scale(2.5, ${MAST_PX.height * SCENE_SCALE})`;
    sc.rover.parentNode.dataset.depth = depth;   // read by the tests
    sc.kpa.textContent = valid ? `${shownKpa(pressuresPa[world])} kPa` : "– kPa";   // short, so the scene keeps its height (the description says why)
  }
  document.getElementById("rover-scenes").dataset.factor = depths.factor;

  document.getElementById("rover-desc").textContent = roverDescription(mass, area, length, scales, pressuresPa, valid);
}

// The words a screen reader hears for the model. Uses the numbers shown on the page.
function roverDescription(mass, area, length, scales, pressuresPa, valid) {
  const start = "Generic six-wheel rover (illustration)";
  if (!valid) {
    return `${start}, shown in its neutral state: the mass or the contact area is not valid, ` +
      "so no sizes or pressures are drawn. Change the inputs above to update it.";
  }
  const lim = ROVER_LIMITS;
  // "1.50 times the 200 kg size", plus a note when the scale reached one of its limits.
  const times = (s, range, what) => {
    const t = `${s.toFixed(2)} times ${what}`;
    if (s === range[0]) return `${t} (the smallest size drawn)`;
    if (s === range[1]) return `${t} (the largest size drawn)`;
    return t;
  };
  const perWheel = Number((area / ROVER_WHEELS).toPrecision(3));
  const kpa = { earth: shownKpa(pressuresPa.earth), moon: shownKpa(pressuresPa.moon), mars: shownKpa(pressuresPa.mars) };
  const names = { earth: "Earth", moon: "the Moon", mars: "Mars" };
  const order = Object.keys(kpa).sort((a, b) => pressuresPa[b] - pressuresPa[a]);
  const boom = scales.boomNeutral
    ? "The boom arm is drawn at its default size because the beam length is not valid."
    : `The boom arm follows the ${length} m beam, drawn at ${times(scales.boom, lim.boom, "the 2 m length")}.`;
  return `${start} for a ${mass} kg rover on ${area} m² of wheel contact, shared by six equal wheels ` +
    `of ${perWheel} m² each. The body is drawn at ${times(scales.body, lim.body, "the 200 kg size")} ` +
    `and each wheel at ${times(scales.wheel, lim.wheel, "the default wheel size")}. ${boom} ` +
    `Ground pressure: Earth ${kpa.earth} kPa, Moon ${kpa.moon} kPa, Mars ${kpa.mars} kPa. ` +
    `Sinking depth is drawn to one shared scale for the three worlds, so the wheels sink deepest on ` +
    `${names[order[0]]} and least on ${names[order[2]]}.`;
}

// ---- 3b2. "Gravity Drop" panel -------------------------------------------------------
// Fall time and impact speed for the same drop on Earth, the Moon and Mars.
// The formulas are in formulas.js, the sentence in explain.js; gravity comes from config.json.

const DROP_BODIES = [["earth", "Earth"], ["moon", "Moon"], ["mars", "Mars"]];
let dropRun = 0;       // counts drops, so an older drop's animation stops when a new one starts

function setUpDrop() {
  const cols = document.getElementById("drop-cols");
  for (const [body, label] of DROP_BODIES) {
    const col = el("div", "drop-col");
    col.append(el("h3", "", label));
    // The falling shape is only decoration: the numbers below say the same thing.
    const track = el("div", "drop-track");
    track.setAttribute("aria-hidden", "true");
    track.append(el("div", `drop-shape shape-${body}`));
    const landed = el("p", "landed");
    landed.id = `landed-${body}`;
    const list = el("ul", "results");
    list.id = `out-drop-${body}`;
    col.append(track, landed, list);
    cols.append(col);
  }
  const g = DATA.config.gravity_m_s2;
  document.getElementById("drop-caveat").textContent =
    "Ideal fall with no air resistance: Earth's air and Mars's thin air would change real falls, and the Moon has none. " +
    `g from config.json (NASA fact sheets): Earth ${g.earth.value}, Moon ${g.moon.value}, Mars ${g.mars.value} m/s².`;
  document.getElementById("in-drop").addEventListener("input", updateDrop);
  // The button is a form's submit button, so Enter in the height box also drops.
  document.getElementById("drop-form").addEventListener("submit", (event) => {
    event.preventDefault();
    startDrop();
  });
  updateDrop();
}

// The drop height typed in, or null (with a message) if it is empty or out of range.
function dropHeight() {
  const h = readInput("in-drop");
  const message = rangeMessage(h, DROP_LIMITS_M.min, DROP_LIMITS_M.max, "m");
  document.getElementById("msg-drop").textContent = message || "";
  document.getElementById("in-drop").setAttribute("aria-invalid", String(message !== null));
  return message === null ? h : null;
}

// Fill the three columns and the sentence from the typed height.
function updateDrop() {
  resetShapes();
  const h = dropHeight();
  const g = DATA.config.gravity_m_s2;
  const shown = {};   // times and speeds as displayed, used by the sentence
  for (const [body] of DROP_BODIES) {
    const list = document.getElementById(`out-drop-${body}`);
    list.replaceChildren();
    if (h === null) {
      list.append(resultItem("Fall time", "check the drop height above"));
      continue;
    }
    const gb = g[body].value;
    shown[body] = { t: shownDrop(fallTimeS(h, gb)), v: shownDrop(impactSpeedMs(h, gb)) };
    list.append(
      resultItem("Fall time", `${shown[body].t} s`, `t = √(2 × ${h} m ÷ ${gb} m/s²) = ${shown[body].t} s`),
      resultItem("Impact speed", `${shown[body].v} m/s`, `v = √(2 × ${gb} m/s² × ${h} m) = ${shown[body].v} m/s`));
  }
  const sentence = document.getElementById("drop-sentence");
  if (h === null) {
    sentence.textContent = "";
    setLead("gravity-drop", "–", `Enter a drop height from ${DROP_LIMITS_M.min} to ${DROP_LIMITS_M.max} m to compare the falls.`);
  } else {
    // The Earth drop heights that give the Moon's and Mars's impact speeds (from the shown speeds).
    const hForMoon = shownDrop(dropHeightForSpeedM(shown.moon.v, g.earth.value));
    const hForMars = shownDrop(dropHeightForSpeedM(shown.mars.v, g.earth.value));
    sentence.textContent = dropSentence(h, shown.earth.t, shown.moon.t, shown.earth.v, shown.moon.v, hForMoon, hForMars);
    const times = (shown.moon.t / shown.earth.t).toFixed(1);
    setLead("gravity-drop", `${times}×`, `A fall from ${h} m takes ${times} times as long on the Moon as on Earth.`);
  }
}

// Put every shape back at the top and clear the "landed" lines.
function resetShapes() {
  dropRun += 1;   // stops any drop that is still running
  for (const [body] of DROP_BODIES) {
    document.querySelector(`.shape-${body}`).style.transform = "translateY(0)";
    document.getElementById(`landed-${body}`).textContent = "";
  }
  document.getElementById("drop-status").textContent = "";
}

function startDrop() {
  const h = dropHeight();
  if (h === null) return;
  resetShapes();
  const g = DATA.config.gravity_m_s2;
  const times = {};
  for (const [body] of DROP_BODIES) times[body] = fallTimeS(h, g[body].value);

  // Short drops are slowed down by one factor for all three, so the Earth fall lasts
  // at least 0.6 s and the differences are easy to see. The proportions stay the same.
  const slow = Math.max(1, 0.6 / times.earth);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const status = document.getElementById("drop-status");
  const landedAll = () => {
    status.textContent = "All three landed: " +
      DROP_BODIES.map(([body, label]) => `${label} ${shownDrop(times[body])} s`).join(", ") + ".";
  };

  // Each shape falls the same distance in pixels: from the top of its track to the floor.
  const shapes = {}, distance = {}, done = {};
  for (const [body] of DROP_BODIES) {
    shapes[body] = document.querySelector(`.shape-${body}`);
    distance[body] = shapes[body].parentElement.clientHeight - shapes[body].offsetHeight;
  }
  const land = (body, label) => {
    shapes[body].style.transform = `translateY(${distance[body]}px)`;
    document.getElementById(`landed-${body}`).textContent = `${label}: landed after ${shownDrop(times[body])} s`;
    done[body] = true;
  };

  if (reduced) {
    // No animation: the shapes are shown on the floor and the results straight away.
    for (const [body, label] of DROP_BODIES) land(body, label);
    landedAll();
    return;
  }

  status.textContent = slow > 1 ? `Falling, slowed down ${slow.toFixed(1)}× so it is easy to see (same proportions).` : "Falling at real speed.";
  const run = dropRun;
  const start = performance.now();
  // A timer lands each shape at its fall time, so the results always appear,
  // even if the browser draws few frames (for example in a background tab).
  for (const [body, label] of DROP_BODIES) {
    setTimeout(() => {
      if (run !== dropRun) return;                // a newer drop (or a new height) took over
      land(body, label);
      if (DROP_BODIES.every(([b]) => done[b])) landedAll();
    }, times[body] * slow * 1000);
  }
  // Between those moments, move the shapes once per screen frame. A body falling from
  // rest covers distance × (t / T)² after t seconds, where T is its full fall time,
  // so the motion speeds up like a real fall.
  function step() {
    if (run !== dropRun) return;
    const t = Math.max(0, (performance.now() - start) / 1000 / slow);   // seconds of "real" fall so far
    for (const [body] of DROP_BODIES) {
      if (!done[body]) shapes[body].style.transform = `translateY(${distance[body] * Math.min(1, t / times[body]) ** 2}px)`;
    }
    if (!DROP_BODIES.every(([body]) => done[body])) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ---- 3b3. Mission Match -----------------------------------------------------------------
// The visitor picks a task; every Earth site gets a verdict from a ranking that already
// exists (cards.json), using the team rules in config.json mission_match. Every sentence
// is built from numbers in the JSON files. No new score, tolerance or ranking.

// Small line icons for the tasks (drawn here, no image files).
const SVG = (paths) => `<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">${paths}</svg>`;
const TASK_ICONS = {
  climb: SVG('<path d="M3 27 13 9l6 9 4-5 6 14z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>'),
  swing: SVG('<circle cx="11" cy="16" r="5" fill="currentColor"/><path d="M11 4v3M11 25v3M2 16h3M17 16h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M27 9a8 8 0 1 0 0 14 7 7 0 0 1 0-14z" fill="none" stroke="currentColor" stroke-width="2"/>'),
  cold: SVG('<path d="M16 3v26M5 9.5l22 13M5 22.5l22-13M12 5l4 3 4-3M12 27l4-3 4 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'),
  drop: SVG('<path d="M10 4h12v8l-6 5-6-5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M16 19v7m-4-3 4 4 4-4M4 29h24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'),
};

let missionTask = null;   // the task picked (kept in memory only)

// One site's row for a comparison such as "moon/slope_deg", straight from cards.json.
function comparisonRow(site, key) {
  const [body, metric] = key.split("/");
  return DATA.cards.cards.find((c) => c.site === site).comparisons.find((r) => r.body === body && r.metric === metric);
}

// Does this comparison have a rank? (cards.json leaves "rank" out, or null, when not assessed.)
const hasRank = (r) => r.rank !== null && r.rank !== undefined;

// The verdict for an existing rank (no rank: not assessed).
function verdictFor(rank) {
  const v = DATA.config.mission_match.verdicts;
  if (rank === v.best_rank) return ["best", v.best];
  if (rank === v.partial_rank) return ["partial", v.partial];
  return ["none", v.otherwise];
}

function setUpMission() {
  const picker = document.getElementById("task-picker");
  for (const task of DATA.config.mission_match.tasks) {
    const b = el("button", "task");
    b.type = "button";
    b.dataset.task = task.id;
    b.setAttribute("aria-pressed", "false");
    const icon = el("span", "task-icon");
    icon.innerHTML = TASK_ICONS[task.id] || "";   // a fixed drawing from above, not data
    b.append(icon, el("span", "task-title", task.title));
    b.addEventListener("click", () => showTask(task.id));
    picker.append(b);
  }
  showTask(DATA.config.mission_match.tasks[0].id);
}

function showTask(id) {
  missionTask = id;
  const task = DATA.config.mission_match.tasks.find((t) => t.id === id);
  for (const b of document.querySelectorAll("#task-picker button")) b.setAttribute("aria-pressed", String(b.dataset.task === id));
  document.getElementById("task-rule").textContent = `Team rule for “${task.title}”: ${task.reason}.`;
  const list = document.getElementById("verdicts");
  list.replaceChildren();
  if (task.ranking === null) dropVerdicts(task, list);
  else rankedVerdicts(task, list);
}

// Tasks that reuse a ranking: rank 1 first, then the rest, then sites that are not assessed.
function rankedVerdicts(task, list) {
  const rows = DATA.cards.cards.map((c) => ({ site: c.site, r: comparisonRow(c.site, task.ranking) }));
  const ranked = rows.filter((x) => hasRank(x.r)).sort((a, b) => a.r.rank - b.r.rank);
  const unranked = rows.filter((x) => !hasRank(x.r));
  const best = ranked[0];
  setLead("mission", siteName(best.site),
    `is this atlas's best stand-in for “${task.title.toLowerCase()}”, and still ${best.r.label === "weak" ? "only " : ""}` +
    `${labelScore(best.r.label, best.r.score)}.`);
  for (const x of [...ranked, ...unranked]) {
    const [kind, text] = !hasRank(x.r) ? ["none", DATA.config.mission_match.verdicts.otherwise] : verdictFor(x.r.rank);
    const honesty = `Honesty check: even the best stand-in here, ${siteName(best.site)}, ${best.r.label === "weak" ? "is only" : "scores"} ` +
      `${labelScore(best.r.label, best.r.score)} for this task` +
      (x === best ? "." : x.r.score === null ? `; ${siteName(x.site)} has no score.` : `; ${siteName(x.site)} scores ${labelScore(x.r.label, x.r.score)}.`);
    list.append(verdictItem(x.site, kind, text, taskSentence(task, x.site, x.r), honesty, taskNumbers(task, x.site, x.r)));
  }
}

// One plain sentence per site, built only from numbers in the JSON files.
function taskSentence(task, site, r) {
  if (r.earth === null || !hasRank(r)) {
    const gap = DATA.terrain.not_assessed.find((x) => x.site === site);
    return `Not assessed: ${gap ? gap.reason : `no ${r.name} for this site`}.`;
  }
  if (task.id === "climb") {
    const p90 = DATA.terrain.sites[site].areas.square_10km.slope_deg.p90;
    const pct = DATA.config.use_rules.slope_climbing_percentile;
    return `Median slope ${r.earth}° vs Malapert's ${r.ref}° (a gap of ${r.gap}°); its steepest ${100 - pct}% of ground ` +
      `reaches ${p90}°, ${p90 >= r.ref ? "at least as steep as" : "gentler than"} Malapert's typical slope.`;
  }
  if (task.id === "swing") {
    const share = (100 * r.earth / r.ref).toFixed(1);
    return `Day–night swing ${r.earth} K, ${Number(share) < 100 ? "only " : ""}${share}% of the Moon's ${r.ref} K.`;
  }
  // "cold": the gap between the site's mean temperature and Mars's.
  return `Mean temperature ${r.earth} K, ${r.gap} K ${r.earth > r.ref ? "warmer" : "colder"} than Mars's ${r.ref} K.`;
}

// The values behind one verdict, for "Show the numbers".
function taskNumbers(task, site, r) {
  const res = DATA.thermal.resolution;
  const lines = [
    `${r.name}: Earth ${fmt(r.earth, r.unit)}, reference ${fmt(r.ref, r.unit)}, gap ${fmt(r.gap, r.unit)}`,
    `Tolerance (tau) ${fmt(r.tau, r.unit)}; score ${r.score === null ? "not assessed" : labelScore(r.label, r.score)}; ` +
      `rank ${hasRank(r) ? `${r.rank} of ${r.of}` : "not assessed"} (cards.json)`,
  ];
  if (task.id === "climb" && DATA.terrain.sites[site]) {
    const sq = DATA.terrain.sites[site].areas.square_10km;
    lines.push(`90th percentile slope ${fmt(sq.slope_deg.p90, "°")}: ${km(sq.size_m_ns_ew[0])} × ${km(sq.size_m_ns_ew[1])} km square, ` +
      `${sq.resolution_m_ns_ew.join(" × ")} m pixels, ${sq.slope_deg.window_m_ns_ew.join(" × ")} m window`);
  }
  if (task.id !== "climb") {
    lines.push(`Earth value: ${res.pixel}, ${res.window}, ${res.time_window}, ${res.period[0]} to ${res.period[1]}`);
  }
  return lines;
}

// "Land from a drop": no site can be ranked, because gravity is the same everywhere on Earth.
function dropVerdicts(task, list) {
  const g = DATA.config.gravity_m_s2;
  const h = task.example_height_m;
  const tE = shownDrop(fallTimeS(h, g.earth.value)), tM = shownDrop(fallTimeS(h, g.moon.value));
  const vE = shownDrop(impactSpeedMs(h, g.earth.value)), vM = shownDrop(impactSpeedMs(h, g.moon.value));
  const hEq = shownDrop(dropHeightForSpeedM(vM, g.earth.value));
  setLead("mission", `0 of ${siteOrder.length}`,
    `Earth sites can rehearse a lunar fall: gravity is ${g.earth.value} m/s² at every one of them.`);
  const sentence = `Same gravity as every Earth site (${g.earth.value} m/s²): a ${h} m fall takes ${tE} s here but ${tM} s ` +
    `on the Moon; dropping from ${hEq} m matches the Moon's impact speed of ${vM} m/s, but not its fall time.`;
  const honesty = "Honesty check: no Earth site can be scored for this task, because gravity is the same at all of them.";
  const numbers = [
    `Gravity: Earth ${g.earth.value} m/s², Moon ${g.moon.value} m/s² (config.json, NASA fact sheets)`,
    `Fall time t = √(2h / g) from ${h} m: Earth ${tE} s, Moon ${tM} s`,
    `Impact speed v = √(2gh) from ${h} m: Earth ${vE} m/s, Moon ${vM} m/s`,
    `Earth height for the Moon's impact speed h = v² / (2g) = ${vM}² ÷ (2 × ${g.earth.value}) = ${hEq} m`,
    "Ideal fall with no air resistance (as in Gravity Drop)",
  ];
  for (const site of siteOrder) {
    list.append(verdictItem(site, "none", DATA.config.mission_match.verdicts.otherwise, sentence, honesty, numbers));
  }
}

function verdictItem(site, kind, badgeText, sentence, honesty, numbers) {
  const li = el("li", "verdict");
  li.dataset.verdict = kind;
  li.dataset.site = site;
  const head = el("div", "verdict-head");
  head.append(el("h3", "", siteLongName(site)), el("span", `badge badge-${kind}`, badgeText));
  li.append(head, el("p", "verdict-sentence", sentence), el("p", "honesty", honesty));
  const more = el("ul", "reveal notes");
  more.id = `verdict-numbers-${++revealCount}`;
  for (const line of numbers) more.append(el("li", "", line));
  li.append(revealButton(more.id, "the values behind this verdict"), more);
  return li;
}

// ---- 3c. Terrain tab ------------------------------------------------------------
// Numbers come from terrain.json (Earth sites), moon_terrain.json (Malapert) and
// cards.json (scores and card text). Nothing is computed here except km from m.

const km = (m) => (m / 1000).toFixed(1);

function showTerrainReferences() {
  const mt = DATA.moon_terrain;
  const area = mt.areas.whole_site;
  const k = mt.averaging.block_px;
  const box = document.getElementById("terrain-refs");
  const S = DATA.sources[mt.source_id];
  const surfUrl = S.file_urls.find((u) => u.endsWith("/" + mt.map.file));   // the height map used
  const scale = `${mt.averaging.resolution_m} m pixels (${k} × ${k} block means of ${mt.map.pixel_m} m LOLA heights)`;
  const items = [
    ["Moon, Malapert massif: median slope", fmt(area.slope_deg.median, "°"),
      `mean ${area.slope_deg.mean}°, 90th percentile ${area.slope_deg.p90}°; ${scale}; ` +
      `${area.slope_deg.window_m_ns_ew.join(" × ")} m window. LOLA's own ${mt.original_5m_slope.resolution_m} m ` +
      `slope map: median ${mt.original_5m_slope.median_deg}°.`, surfUrl],
    ["Moon, Malapert massif: median roughness", fmt(area.roughness_m.median, "m"),
      `tilt removed in a ${area.roughness_m.window_m_ns_ew.join(" × ")} m window; ${scale}.`, surfUrl],
    ["LOLA data quality", null, `${mt.caveats[0]} ${mt.caveats[1]}`, mt.caveats_source.url],
  ];
  for (const [title, value, detail, url] of items) {
    const ref = el("div", "ref");
    ref.append(el("div", "small", title));
    if (value !== null) {
      ref.append(el("div", "big", value), el("div", "small", detail));
    } else {
      // The quality box has no single number: its long caveats are collapsed behind "Show details".
      ref.append(collapsible("LOLA data-quality caveats", el("div", "small", detail)));
    }
    const src = el("div", "small", "Source: ");
    src.append(link(url));
    ref.append(src);
    box.append(ref);
  }
}

// A Chart.js plugin that draws a diamond on each bar, e.g. at the 90th percentile.
const percentileMarkers = {
  id: "percentileMarkers",
  afterDatasetsDraw(c, args, opts) {
    const ctx = c.ctx;
    ctx.save();
    ctx.fillStyle = opts.color;
    ctx.strokeStyle = cssColor("--panel");
    opts.values.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const x = c.scales.x.getPixelForValue(v);
      const y = c.scales.y.getPixelForValue(i);
      ctx.beginPath();
      ctx.moveTo(x, y - 8); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 8); ctx.lineTo(x - 6, y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    });
    ctx.restore();
  },
};

// One horizontal bar chart: the Moon first, then the Earth sites in terrainOrder.
function terrainChart(canvasId, moonValue, siteValue, unit, axisTitle, markers) {
  const labels = [MOON_TERRAIN_NAME, ...terrainOrder.map((s) => (siteValue(s) === null ? `${siteName(s)} (not assessed)` : siteName(s)))];
  const values = [moonValue, ...terrainOrder.map(siteValue)];
  // Make the axis long enough for the bars and the markers.
  const longest = Math.max(...values.filter((v) => v !== null), ...(markers || []).filter((v) => v !== null));
  return new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: [cssColor("--moon"), ...siteColors(terrainOrder, null, "--c-terrain")], borderRadius: 4 }] },
    plugins: markers ? [percentileMarkers] : [],
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        percentileMarkers: markers ? { values: markers, color: cssColor("--text") } : undefined,
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.raw === null) return "not assessed";
              const p90 = markers ? `, 90th percentile ${markers[ctx.dataIndex]} ${unit}` : "";
              return `median ${ctx.raw} ${unit}${p90}`;
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, suggestedMax: longest * 1.05,
             title: { display: true, text: axisTitle, color: cssColor("--muted") },
             ticks: { color: cssColor("--muted") }, grid: { color: cssColor("--line") } },
        y: { ticks: { color: cssColor("--text") }, grid: { display: false } },
      },
      onClick: (event, bars) => {
        if (bars.length && bars[0].index > 0) selectSite(terrainOrder[bars[0].index - 1]);
      },
    },
  });
}

// The 10 km square of a site in terrain.json, or null if the site has none.
function terrainSquare(site) {
  const t = DATA.terrain.sites[site];
  return t ? t.areas.square_10km : null;
}

function showTerrainCharts() {
  const mt = DATA.moon_terrain.areas.whole_site;
  // Steepest median slope first; sites with no terrain numbers go last.
  terrainOrder = Object.keys(DATA.thermal.sites).sort((a, b) =>
    (terrainSquare(b)?.slope_deg.median ?? -1) - (terrainSquare(a)?.slope_deg.median ?? -1));

  const slopeOf = (s) => terrainSquare(s)?.slope_deg.median ?? null;
  const p90Of = (s) => terrainSquare(s)?.slope_deg.p90 ?? null;
  const roughOf = (s) => terrainSquare(s)?.roughness_m.median ?? null;

  slopeChart = terrainChart("chart-slope", mt.slope_deg.median, slopeOf, "°", "Median slope (°)",
    [mt.slope_deg.p90, ...terrainOrder.map(p90Of)]);
  roughChart = terrainChart("chart-rough", mt.roughness_m.median, roughOf, "m", "Median roughness (m)", null);

  const any = terrainSquare(terrainOrder[0]);
  const res = any.resolution_m_ns_ew;
  const moonRes = DATA.moon_terrain.averaging.resolution_m;
  document.getElementById("slope-note").textContent =
    `Bars: median slope. ◆ = 90th percentile slope (10% of the area is steeper). Earth: 10 km squares, ` +
    `SRTM pixels about ${res[0]} × ${res[1]} m, 3 × 3 window. Moon: whole ${km(DATA.moon_terrain.map.size_m[0])} km ` +
    `Site23 map, ${moonRes} m pixels, 3 × 3 window. Tap a bar or a button below to open a site.`;
  document.getElementById("rough-note").textContent =
    `Bars: median roughness, the standard deviation of heights after removing the local tilt in each 3 × 3 window ` +
    `(about ${any.roughness_m.window_m_ns_ew.join(" × ")} m on Earth, ` +
    `${DATA.moon_terrain.areas.whole_site.roughness_m.window_m_ns_ew.join(" × ")} m on the Moon).`;
}

function showTerrainCard(site) {
  const card = DATA.cards.cards.find((c) => c.site === site);
  const t = DATA.terrain.sites[site];
  const root = el("article", "card");
  const head = el("div", "card-head");
  head.append(el("h3", "", siteLongName(site)));
  if (t) {
    const sq = t.areas.square_10km;
    head.append(el("p", "",
      `${km(sq.size_m_ns_ew[0])} × ${km(sq.size_m_ns_ew[1])} km square centred ${sq.centre_lat_lon_deg[0]}°, ` +
      `${sq.centre_lat_lon_deg[1]}° · median slope ${fmt(sq.slope_deg.median, "°")} ` +
      `(90th percentile ${fmt(sq.slope_deg.p90, "°")}) · median roughness ${fmt(sq.roughness_m.median, "m")} · ` +
      `${sq.resolution_m_ns_ew.join(" × ")} m pixels, ${sq.slope_deg.pixels_used} pixels`));
  } else {
    const gap = DATA.terrain.not_assessed.find((x) => x.site === site);
    head.append(el("p", "", `Terrain not assessed: ${gap ? gap.reason : "no terrain data"}.`));
  }
  root.append(head);
  hideCardNumbers(head, "terrain");
  fillCard(root, card.terrain, "terrain");
  document.getElementById("terrain-card").replaceChildren(root);
}

function showTerrainNotes() {
  // Key caveats, always visible (the full list below is collapsed).
  const cov0 = DATA.terrain.srtm_coverage;
  const moved = Object.entries(DATA.terrain.sites).filter(([, t]) => t.offset_m.straight_line > 0)
    .map(([site, t]) => `the ${siteName(site)} terrain square is ${(t.offset_m.straight_line / 1000).toFixed(1)} km from its thermal point`);
  const outside = DATA.terrain.not_assessed.map((x) => siteName(x.site)).join(" and ");
  document.getElementById("terrain-key").textContent =
    `Key caveats: ${moved.join("; ")}; SRTM covers ${cov0.north_deg}° N to ${-cov0.south_deg}° S, so ${outside} are not assessed.`;
  const mt = DATA.moon_terrain;
  const cov = DATA.terrain.srtm_coverage;
  const k = mt.averaging.block_px;
  const earthRes = terrainSquare(terrainOrder[0]).resolution_m_ns_ew;
  const ul = document.getElementById("terrain-notes");
  const add = (text, url) => {
    const li = el("li", "", text);
    if (url) { li.append(" Source: "); li.append(link(url)); }
    ul.append(li);
  };

  add(`The Moon heights were averaged from ${mt.map.pixel_m} m to ${mt.averaging.resolution_m} m ` +
    `(${k} × ${k} block means) so they match the Earth SRTM data (${earthRes.join(" × ")} m pixels); both sides then use the ` +
    `same slope and roughness method. LOLA's own ${mt.original_5m_slope.resolution_m} m slope map has a median ` +
    `of ${mt.original_5m_slope.median_deg}°, close to the ${mt.areas.whole_site.slope_deg.median}° at ` +
    `${mt.averaging.resolution_m} m.`);

  const gaps = DATA.terrain.not_assessed.map((x) => `${siteName(x.site)} (${x.latitude_deg}°)`).join(" and ");
  add(`SRTM only covers land between ${cov.north_deg}° N and ${-cov.south_deg}° S, so ${gaps} cannot be assessed.`,
    cov.source_url);

  for (const [site, t] of Object.entries(DATA.terrain.sites)) {
    const o = t.offset_m;
    if (o.straight_line === 0) continue;
    add(`The ${siteName(site)} terrain square is centred ${km(o.straight_line)} km from its thermal point ` +
      `(${t.square_centre_lat_lon_deg.join(", ")} vs ${t.thermal_point_lat_lon_deg.join(", ")}). ${t.why_moved}`);
  }

  add("No Mars terrain reference was used, so Mars slope and roughness are not assessed.");

  const tau = DATA.cards.tau;
  const reason = DATA.cards.tau_reason;
  add(`Tolerance (tau) for slope: ${tau["moon/slope_deg"]}°. ${reason["moon/slope_deg"]}`);
  add(`Tolerance (tau) for roughness: ${tau["moon/roughness_m"]} m. ${reason["moon/roughness_m"]}`);
  add(`The Moon values cover the whole ${km(mt.map.size_m[0])} × ${km(mt.map.size_m[1])} km Site23 map near ` +
    `the south pole; each Earth value covers a 10 km square.`);
}

// ---- 3e. Validation tab --------------------------------------------------------------
// Everything here is copied from validation.json (written by pipeline/validate.py).

// A simple table: headers, then rows of cells (a cell may be text or a page element).
function fillTable(id, headers, rows) {
  const table = document.getElementById(id);
  const head = el("tr");
  for (const h of headers) head.append(el("th", "", h));
  table.append(el("thead"));
  table.tHead.append(head);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    row.forEach((cell, i) => {
      const td = el("td");
      if (cell instanceof Node) td.append(cell); else td.textContent = cell;
      td.dataset.label = headers[i];   // phones show the column name (see style.css)
      tr.append(td);
    });
    body.append(tr);
  }
  table.append(body);
}

function showValidation() {
  const v = DATA.validation;
  document.getElementById("val-rules").textContent =
    `Results exactly as computed by validate.py with the same scoring code as the cards; no parameter was tuned. ` +
    `"Near the top" means rank ${v.rules.near_top_rank} or better; rank 1 = smallest gap to the reference.`;

  // 1. Benchmarks: rank on every comparison, then the findings.
  const comps = [["moon/thermal_swing_K", "Moon swing"], ["mars/mean_temperature_K", "Mars mean temperature"],
                 ["moon/slope_deg", "Moon slope"], ["moon/roughness_m", "Moon roughness"]];
  const rankText = (r) => (r.rank === null ? "not assessed" : `${r.rank} of ${r.of} · ${labelScore(r.label, r.score)}`);
  fillTable("val-bench", ["Site", "Named as", ...comps.map((c) => c[1])],
    v.benchmarks.map((b) => {
      const named = el("span", "", `${b.named_as}: `);
      b.sources.forEach((src, i) => { if (i) named.append(", "); named.append(link(src.url)); });
      return [siteName(b.site), named, ...comps.map(([k]) => rankText(b.ranks[k]))];
    }));
  const findings = document.getElementById("val-findings");
  for (const b of v.benchmarks) {
    // Stored sentences name sites by key; withNames (names.js) writes the names instead.
    for (const f of b.findings) findings.append(el("li", "", `${siteName(b.site)}: ${withNames(f.text)}`));
    findings.append(el("li", "", withNames(b.not_measured)));
  }

  // 2. Negative control: no numbers until the control has been scored.
  const c = v.control;
  const control = document.getElementById("val-control");
  if (c.status !== "done") {
    control.textContent = `Amazon control: ${c.status}.`;
  } else {
    const parts = Object.entries(c.comparisons).map(([k, r]) =>
      `${k}: rank ${r.rank ?? "—"} of ${r.of ?? "—"}, gap ${r.gap}, ${labelScore(r.label, r.score)}`);
    control.textContent = `Amazon control (${siteName(c.site)}, ${c.records} records): ${parts.join("; ")}.`;
  }
  const single = document.getElementById("val-single");
  for (const line of v.single_metric.lines) single.append(el("li", "", withNames(line)));

  // 3. Sensitivity: label changes and ranking changes for each factor.
  const now = Object.entries(v.sensitivity.labels_now).map(([lab, n]) => `${n} ${lab}`).join(", ");
  document.getElementById("val-labels").textContent = `Score labels now: ${now}.`;
  const rows = [];
  for (const run of v.sensitivity.runs) {
    const pct = `${run.factor > 1 ? "+" : "−"}${Math.round(Math.abs(run.factor - 1) * 100)}%`;
    for (const [k, r] of Object.entries(run.rankings)) {
      rows.push([`${pct} (×${run.factor})`, k, `${run.label_changes} of ${run.labels_compared} (all metrics)`,
        `${r.gap_rank_changes} of ${r.sites}`, `${r.score_rank_changes} of ${r.sites}`,
        `${r.zero_scores_before} → ${r.zero_scores_after}`]);
    }
  }
  fillTable("val-sens", ["Tolerance change", "Comparison", "Label changes", "Gap-rank changes",
    "Score-rank changes", "Sites at score 0"], rows);
  const changes = document.getElementById("val-changes");
  for (const run of v.sensitivity.runs) {
    for (const c of run.changed) {
      changes.append(el("li", "", `×${run.factor}: ${siteName(c.site)}, ${c.comparison}: ` +
        `${labelScore(c.from, c.from_score)} → ${labelScore(c.to, c.to_score)}`));
    }
  }
  if (!changes.children.length) changes.append(el("li", "", "No label changes at either tolerance change."));

  const would = document.getElementById("val-would");
  for (const line of v.would_change_not_applied) would.append(el("li", "", withNames(line)));
}

// ---- 3d. Views: start page, hub and six stations ---------------------------------------
// The address decides the view: #start, #hub, #thermal, #terrain, #tryit, #gravity-drop,
// #validation or #sources. Every link just changes the address, so deep links and the
// browser's Back button work.

const STATIONS = ["thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "sources"];
const VIEWS = ["start", "hub", ...STATIONS];
let focusAfterRoute = null;   // an element id to focus after the next view change (else the view's title)
let keepFocusOn = null;       // the station tab the arrow keys moved to (focus stays on it)

function showView(name, moveFocus) {
  for (const v of VIEWS) document.getElementById(v).hidden = v !== name;
  document.body.dataset.view = name;   // style.css shows the Moon and Earth's horizon on the start page only
  const isStation = STATIONS.includes(name);
  document.getElementById("station-bar").hidden = !isStation;
  document.getElementById("topbar").hidden = name === "start";
  for (const tab of document.querySelectorAll('#station-bar [role="tab"]')) {
    const on = tab.getAttribute("aria-controls") === name;
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
  }
  // Charts drawn while hidden have no size; resize them now that they show.
  for (const c of [chart, chart2, slopeChart, roughChart]) if (c) c.resize();
  moveMapTo(name);   // the shared map follows the open station
  const title = document.getElementById(`${name}-title`);
  document.title = name === "start" ? "Rehearsal Earth" : `${title.textContent} · Rehearsal Earth`;
  if (!moveFocus) return;
  window.scrollTo(0, 0);
  // Keyboard and screen-reader users land on the new view's title (or a chosen element).
  // (Changing the address can move focus to the page itself, so focus is always set again here.)
  const target = keepFocusOn || document.getElementById(focusAfterRoute || `${name}-title`);
  if (target) target.focus({ preventScroll: true });
  focusAfterRoute = null;
  keepFocusOn = null;
}

// The view named in the address. The bare address (no "#") is the start page, so the
// browser's Back button can always return to it.
function viewFromAddress() {
  const name = location.hash.slice(1);
  if (name === "") return "start";
  return VIEWS.includes(name) ? name : null;
}

function setUpViews() {
  const tabs = [...document.querySelectorAll('#station-bar [role="tab"]')];
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => { location.hash = tab.getAttribute("aria-controls"); });
    // Left and right arrow keys move between station tabs.
    tab.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      next.focus();
      keepFocusOn = next;
      location.hash = next.getAttribute("aria-controls");
    });
  });
  // Any change of address (a link, a tab, Back or Forward) shows the matching view.
  window.addEventListener("hashchange", () => {
    const name = viewFromAddress();
    if (name) showView(name, true);
  });
  showView(viewFromAddress() || "start", false);   // a deep link opens its view directly
}

// ---- 3d2. Station openers: one big figure and one plain sentence ---------------------
// Worked out from the JSON files; Try it and Gravity Drop update theirs as you type.

function setLead(station, figure, sentence) {
  document.getElementById(`${station}-figure`).textContent = figure;
  document.getElementById(`${station}-sentence`).textContent = sentence;
}

// The Earth site with the largest mean day–night swing (sites without one are skipped).
function biggestSwingSite() {
  let best = null;
  for (const [site, t] of Object.entries(DATA.thermal.sites)) {
    if (t.mean_swing.K === null) continue;
    if (best === null || t.mean_swing.K > DATA.thermal.sites[best].mean_swing.K) best = site;
  }
  return best;
}

function showLeads() {
  // Thermal: the best site's share of the Moon's swing.
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  const best = biggestSwingSite();
  const share = (100 * DATA.thermal.sites[best].mean_swing.K / lunar).toFixed(1);
  setLead("thermal", `${share}%`,
    `Even ${siteName(best)}, the Earth site with the biggest day–night swing, gets only ${share}% of the Moon's swing.`);

  // Terrain: Malapert's median slope and the steepest Earth site's.
  let steepest = null;
  for (const card of DATA.cards.cards) {
    const cmp = card.comparisons.find((x) => x.body === "moon" && x.metric === "slope_deg");
    if (cmp.earth === null) continue;
    if (steepest === null || cmp.earth > steepest.cmp.earth) steepest = { site: card.site, cmp };
  }
  setLead("terrain", `${steepest.cmp.ref}°`,
    `That is the typical (median) slope at Malapert on the Moon; the steepest Earth site, ` +
    `${siteName(steepest.site)}, has ${steepest.cmp.earth}°.`);

  // Validation: how many score labels change when every tolerance changes.
  const v = DATA.validation;
  const runs = v.sensitivity.runs;
  const changes = Math.max(...runs.map((r) => r.label_changes));
  const compared = runs[0].labels_compared;
  const sizes = runs.map((r) => `${Math.round(Math.abs(r.factor - 1) * 100)}% ${r.factor < 1 ? "smaller" : "larger"}`);
  const when = `when every tolerance is made ${sizes.join(" or ")}`;
  setLead("validation", `${changes} of ${compared}`,
    changes === 0 ? `Not one of the ${compared} score labels changes ${when}.` :
      `Up to ${changes} of the ${compared} score labels change ${when}.`);
  document.getElementById("val-sens-summary").textContent =
    changes === 0 ? `No score label changes ${when}.` : `Up to ${changes} of ${compared} score labels change ${when}.`;
  const near = v.benchmarks.filter((b) => b.findings.some((f) => f.near_top)).length;
  document.getElementById("val-bench-summary").textContent =
    `${near} of the ${v.benchmarks.length} sites NASA already uses as analogs rank near the top ` +
    `(rank ${v.rules.near_top_rank} or better) on at least one comparison.`;

  // Sources: how many numbers the table lists.
  setLead("sources", `${sourceCounts.all}`,
    "numbers on this page, each with the area and resolution it was measured at and a link to its source.");
}

// ---- 3e. Start page: three headline findings, computed from the JSON files -----------

function finding(kicker, big, short, text, context, href, linkText) {
  const li = el("li", "finding");
  li.dataset.station = href.slice(1);   // the card takes the colour of the station it links to
  li.append(el("p", "kicker", kicker), el("p", "big", big), el("p", "short", short));
  const more = el("div", "reveal");
  more.id = `finding-numbers-${++revealCount}`;
  more.append(el("p", "detail", text), el("p", "note", context));
  li.append(revealButton(more.id, "the figures behind it"), more);
  const a = el("a", "proof", linkText);
  a.href = href;
  li.append(a);
  return li;
}

function showFindings() {
  const list = document.getElementById("findings");
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  const r = DATA.thermal.resolution;

  // (1) The Earth site with the largest mean day–night swing, as a share of the Moon's swing.
  let best = null;
  for (const [site, t] of Object.entries(DATA.thermal.sites)) {
    if (t.mean_swing.K === null) continue;
    if (best === null || t.mean_swing.K > DATA.thermal.sites[best].mean_swing.K) best = site;
  }
  const swing = DATA.thermal.sites[best].mean_swing.K;
  const share = (100 * swing / lunar).toFixed(1);
  list.append(finding("Temperature swing", `${share}%`,
    `The best Earth site reaches only ${share}% of the Moon's day–night temperature swing.`,
    `Even the best Earth site, ${siteName(best)}, swings ${swing} K between day and night: ${share}% of the Moon's ${lunar} K.`,
    `Mean day–night swing, ${r.pixel}, ${r.window}, ${r.time_window}, ${r.period[0]} to ${r.period[1]}. ` +
    "The Moon's swing is a reference value from NASA slides.",
    "#thermal", "See the proof in the Thermal station →"));

  // (2) The Earth site whose median slope is closest to Malapert's (smallest gap on the cards).
  let closest = null;
  for (const card of DATA.cards.cards) {
    const cmp = card.comparisons.find((x) => x.body === "moon" && x.metric === "slope_deg");
    if (cmp.gap === null) continue;
    if (closest === null || cmp.gap < closest.cmp.gap) closest = { site: card.site, cmp };
  }
  const sq = DATA.terrain.sites[closest.site].areas.square_10km;
  const mt = DATA.moon_terrain;
  const c = closest.cmp;
  const compare = c.earth < c.ref ? "flatter than" : c.earth > c.ref ? "steeper than" : "as steep as";
  list.append(finding("Terrain slope", `${c.earth}° vs ${c.ref}°`,
    `Even the closest Earth terrain is ${compare} the Moon's Malapert massif.`,
    `${siteName(closest.site)} has the median slope closest to Malapert's: ${c.earth}° against ${c.ref}°, ` +
    `a gap of ${c.gap}°, and still scores ${labelScore(c.label, c.score)}.`,
    `Earth: ${(sq.size_m_ns_ew[0] / 1000).toFixed(1)} × ${(sq.size_m_ns_ew[1] / 1000).toFixed(1)} km square, ` +
    `${sq.resolution_m_ns_ew.join(" × ")} m pixels, ${sq.slope_deg.window_m_ns_ew.join(" × ")} m window. ` +
    `Moon: ${mt.averaging.resolution_m} m block means, ${mt.areas.whole_site.slope_deg.window_m_ns_ew.join(" × ")} m window.`,
    "#terrain", "See the proof in the Terrain station →"));

  // (3) How many scored comparisons are weak, and the highest score of all.
  const scored = [], unscored = [];
  for (const card of DATA.cards.cards) {
    for (const cmp of card.comparisons) (cmp.score === null ? unscored : scored).push({ site: card.site, cmp });
  }
  const weak = scored.filter((x) => x.cmp.label === "weak").length;
  const top = scored.reduce((a, b) => (b.cmp.score > a.cmp.score ? b : a));
  const lead = weak === scored.length ? `All ${scored.length} scored comparisons are weak.` :
    `${weak} of ${scored.length} scored comparisons are weak.`;
  const lab = DATA.config.labels;
  list.append(finding("Match scores", `${weak} of ${scored.length} weak`,
    weak === scored.length ? "No Earth site is a strong or partial match on any scored comparison." :
      `${weak} of ${scored.length} scored comparisons are weak.`,
    `${lead} The highest score is ${top.cmp.score.toFixed(2)} (${siteName(top.site)}, ${top.cmp.name} vs ${top.cmp.body}); ` +
    `${unscored.length} more comparisons are not assessed.`,
    `Score ${DATA.cards.formula}; strong at ${lab.strong} or more, partial at ${lab.partial} or more, otherwise weak.`,
    "#validation", "See how it holds up in the Validation station →"));
}

// ---- 4. Sources table ------------------------------------------------------------

function showTable() {
  const S = DATA.sources;
  const c = DATA.config;
  const modis = S.mod11a2_v061;
  const r = DATA.thermal.resolution;
  const earthWindow = `${r.pixel}; ${r.time_window}; ${r.period[0]} to ${r.period[1]}`;

  const rows = [];   // each row: [what, value, window and resolution, dataset, url], plus .tags
  const group = (title) => rows.push({ group: title });
  // Which tabs a row belongs to, for the Sources filter and the per-tab counts.
  let tags = [];
  const add = (row) => rows.push(Object.assign(row, { tags: [...tags] }));
  const TERRAIN_METRICS = ["slope_deg", "roughness_m"];

  group("References");
  tags = ["references", "thermal", "tryit", "mission"];   // Try it and Mission Match use the Moon's swing
  const moon = c.references.moon.thermal_swing_K;
  add(["Moon day–night swing (equator)", fmt(moon.value, "K"), "lunar equator; resolution not stated in source",
    S[moon.source_id].dataset, moon.source_url]);
  const mars = c.references.mars.mean_temperature_K;
  tags = ["references", "thermal", "mission"];   // Mission Match: "stay as cold as Mars"
  add(["Mars mean temperature", fmt(mars.value, "K"), "global mean; resolution not stated in source",
    S[mars.source_id].dataset, mars.source_url]);
  tags = ["references", "thermal"];
  add(["Mars mean temperature (second source)", fmt(mars.second_source.value_C, "°C"),
    "global mean; resolution not stated in source", S[mars.second_source.source_id].dataset, mars.second_source.source_url]);
  tags = ["references", "terrain"];
  for (const [body, ref] of Object.entries(c.references)) {
    for (const [key, what, unit] of [["slope_deg", "median slope", "°"], ["roughness_m", "median roughness", "m"]]) {
      const r = ref[key];
      // A terrain reference may come from a different place than ref.name (e.g. the lunar south pole).
      const where = r.site || ref.name;
      // Mission Match ("climb steep slopes") compares with the Moon's median slope.
      tags = body === "moon" && key === "slope_deg" ? ["references", "terrain", "mission"] : ["references", "terrain"];
      add([`${where}: ${what}`, fmt(r.value, unit), r.note,
        r.source_id ? S[r.source_id].dataset : "—", r.source_url || ""]);
    }
  }

  group("Gravity");
  tags = ["references", "thermal", "terrain", "tryit", "gravity-drop", "mission"];   // used by both cards, Try it, Gravity Drop and Mission Match
  const factsheet = { earth: "nssdc_earth_factsheet", moon: "nssdc_moon_factsheet", mars: "nssdc_mars_factsheet" };
  for (const [body, g] of Object.entries(c.gravity_m_s2)) {
    add([`Surface gravity, ${body}`, fmt(g.value, "m/s²"), g.detail || "surface value",
      S[factsheet[body]].dataset, g.source_url]);
  }

  group("Beam materials (Try it panel)");
  tags = ["thermal", "tryit"];
  for (const mat of Object.values(c.materials)) {
    add([`Expansion coefficient α, ${mat.name}`, fmtAlpha(mat.alpha_per_K),
      `at ${c.materials_note.temperature_K} K, from a fit over ${c.materials_note.fit_range_K.join("–")} K`,
      S[mat.source_id].dataset, mat.source_url]);
  }

  group("Tolerances (tau) used in the scores");
  for (const [key, tau] of Object.entries(DATA.cards.tau)) {
    if (tau === null) continue;
    const reason = DATA.cards.tau_reason[key] || "";
    // The unit is the end of the metric name, e.g. "moon/slope_deg" -> deg.
    const unit = { K: "K", deg: "°", m: "m" }[key.split("_").pop()] || "";
    tags = [TERRAIN_METRICS.includes(key.split("/")[1]) ? "terrain" : "thermal", "validation"];
    add([`tau, ${key}`, fmt(tau, unit), reason, "computed by score.py", ""]);
  }

  group("Validation benchmarks (sites NASA names as analogs)");
  tags = ["validation"];
  for (const b of DATA.validation.benchmarks) {
    for (const src of b.sources) {
      add([`${siteName(b.site)}: ${b.named_as}`, "—", `“${src.quote}”`, S[src.id].dataset, src.url]);
    }
  }

  for (const site of siteOrder) {
    const t = DATA.thermal.sites[site];
    group(`Earth site: ${siteLongName(site)} (${t.latitude}°, ${t.longitude}°)`);
    tags = ["thermal", "tryit", "mission"];   // Try it and Mission Match use each site's mean swing
    add(["Mean day–night swing", fmt(t.mean_swing.K, "K"), `${earthWindow}; ${t.records_with_swing} records`, modis.dataset, modis.doi_url]);
    tags = ["thermal"];
    add([`Largest swing (${t.largest_swing.date})`, fmt(t.largest_swing.K, "K"), earthWindow, modis.dataset, modis.doi_url]);
    add([`Lowest temperature (${t.lowest_temperature.date}, ${t.lowest_temperature.when})`,
      `${fmt(t.lowest_temperature.K, "K")} / ${fmt(t.lowest_temperature.C, "°C")}`, earthWindow, modis.dataset, modis.doi_url]);
    tags = ["thermal", "mission"];
    add(["Mean temperature", `${fmt(t.mean_temperature.K, "K")} / ${fmt(t.mean_temperature.C, "°C")}`,
      `${earthWindow}; ${t.mean_temperature.values_used} values`, modis.dataset, modis.doi_url]);
    // Terrain (from terrain.json): the 10 km square's numbers, or why there are none.
    tags = ["terrain", "mission"];   // Mission Match gives the reason for sites without terrain
    const gap = DATA.terrain.not_assessed.find((x) => x.site === site);
    if (gap) add(["Terrain (slope, roughness)", fmt(null, ""), gap.reason, "—", ""]);
    tags = ["terrain"];
    const ter = DATA.terrain.sites[site];
    if (ter) {
      const sq = ter.areas.square_10km;
      const km = (m) => (m / 1000).toFixed(1);
      const [ns, ew] = sq.resolution_m_ns_ew;
      const where = `${km(sq.size_m_ns_ew[0])} × ${km(sq.size_m_ns_ew[1])} km square centred ` +
        `${sq.centre_lat_lon_deg[0]}°, ${sq.centre_lat_lon_deg[1]}°; ${ns} × ${ew} m pixels`;
      const slopeWin = `${sq.slope_deg.window_m_ns_ew.join(" × ")} m window (3 × 3 pixels)`;
      const roughWin = `${sq.roughness_m.window_m_ns_ew.join(" × ")} m window ` +
        `(${sq.roughness_m.window_px} × ${sq.roughness_m.window_px} pixels, tilt removed)`;
      const srtm = [S.srtmgl1_v3.dataset, S.srtmgl1_v3.doi_url];
      tags = ["terrain", "mission"];   // median and 90th percentile slope: Mission Match
      add(["Median slope", fmt(sq.slope_deg.median, "°"), `${where}; ${slopeWin}; ${sq.slope_deg.pixels_used} pixels`, ...srtm]);
      tags = ["terrain"];
      add(["Mean slope", fmt(sq.slope_deg.mean, "°"), `${where}; ${slopeWin}`, ...srtm]);
      tags = ["terrain", "mission"];
      add(["90th percentile slope", fmt(sq.slope_deg.p90, "°"), `${where}; ${slopeWin}`, ...srtm]);
      tags = ["terrain"];
      add(["Median roughness", fmt(sq.roughness_m.median, "m"), `${where}; ${roughWin}; ${sq.roughness_m.pixels_used} pixels`, ...srtm]);
      const [dLat, dLon] = ter.offset_deg_lat_lon;
      if (dLat !== 0 || dLon !== 0) {
        const o = ter.offset_m;
        add(["Terrain square centre",
          `${ter.square_centre_lat_lon_deg[0]}°, ${ter.square_centre_lat_lon_deg[1]}°`,
          `Centred ${Math.abs(dLat)}° (${km(o.north_south)} km) ${dLat < 0 ? "south" : "north"} and ` +
          `${Math.abs(dLon)}° (${km(o.east_west_at_square)} km) ${dLon < 0 ? "west" : "east"} of the ` +
          `thermal point, ${km(o.straight_line)} km in a straight line. ${ter.why_moved || ""}`, ...srtm]);
      }
    }
    const card = DATA.cards.cards.find((x) => x.site === site);
    for (const cmp of card.comparisons.filter((x) => x.score !== null)) {
      tags = [TERRAIN_METRICS.includes(cmp.metric) ? "terrain" : "thermal"];
      // The scores whose ranking a Mission Match task reuses.
      if (DATA.config.mission_match.tasks.some((t) => t.ranking === `${cmp.body}/${cmp.metric}`)) tags.push("mission");
      add([`Score: ${cmp.name} vs ${cmp.body}`, labelScore(cmp.label, cmp.score),
        `tau ${cmp.tau} ${cmp.unit}`, "computed by score.py from the rows above", ""]);
    }
  }

  // Build the table.
  const table = document.getElementById("numbers");
  const headers = ["Number", "Value", "Window and resolution", "Dataset", "Source URL"];
  const headRow = el("tr");
  for (const h of headers) headRow.append(el("th", "", h));
  table.append(el("thead"));
  table.tHead.append(headRow);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    if (row.group) {
      tr.className = "group";
      const td = el("td", "", row.group);
      td.colSpan = 5;
      tr.append(td);
    } else {
      const [what, value, win, dataset, url] = row;
      tr.dataset.tags = row.tags.join(" ");
      tr.append(el("td", "", what), el("td", "num", value), el("td", "", win), el("td", "", dataset));
      const td = el("td");
      if (url) td.append(shortLink(url)); else td.textContent = "—";
      if (url) td.className = "url";
      tr.append(td);
      // On phones each cell shows its column name (see style.css).
      [...tr.children].forEach((cell, i) => (cell.dataset.label = headers[i]));
    }
    body.append(tr);
  }
  table.append(body);

  // How many numbers each filter shows, counted from the rows just built.
  const dataRows = rows.filter((row) => !row.group);
  sourceCounts = { all: dataRows.length };
  for (const name of FILTERS) {
    if (name !== "all") sourceCounts[name] = dataRows.filter((row) => row.tags.includes(name)).length;
  }
}

// ---- 4b. Sources filter and the per-tab "Sources for this tab" links ---------------

const FILTERS = ["all", "thermal", "terrain", "tryit", "gravity-drop", "mission", "validation", "references"];
let sourceCounts = {};   // filter name -> number of rows it shows

// Show only the rows tagged with this filter; a group heading hides when all its rows are hidden.
function applyFilter(name) {
  for (const b of document.querySelectorAll("#source-filter button")) {
    b.setAttribute("aria-pressed", String(b.dataset.filter === name));
  }
  let heading = null, anyShown = false;
  const finishGroup = () => { if (heading) heading.hidden = !anyShown; };
  for (const tr of document.querySelectorAll("#numbers tbody tr")) {
    if (tr.classList.contains("group")) {
      finishGroup();
      heading = tr;
      anyShown = false;
    } else {
      tr.hidden = !(name === "all" || tr.dataset.tags.split(" ").includes(name));
      anyShown = anyShown || !tr.hidden;
    }
  }
  finishGroup();
  document.getElementById("filter-count").textContent =
    `Showing ${sourceCounts[name]} of ${sourceCounts.all} numbers.`;
}

function setUpSources() {
  for (const b of document.querySelectorAll("#source-filter button")) {
    b.addEventListener("click", () => applyFilter(b.dataset.filter));
  }
  applyFilter("all");
  // One compact line at the bottom of each station, opening Sources with that station's filter.
  for (const a of document.querySelectorAll("a.tab-sources")) {
    const name = a.dataset.filter;
    a.textContent = `Sources for this station: ${sourceCounts[name]} numbers, see the Sources station`;
    a.addEventListener("click", () => {
      applyFilter(name);
      focusAfterRoute = "sources-heading";   // the link opens #sources; focus goes to the table's heading
    });
  }
}

// "Show details" / "Hide details" on every collapsed section.
function setUpDetails() {
  for (const d of document.querySelectorAll("details.more")) {
    const action = d.querySelector(".more-action");
    d.addEventListener("toggle", () => { action.textContent = d.open ? "Hide details" : "Show details"; });
  }
}

// ---- Start -----------------------------------------------------------------------

async function start() {
  try {
    const names = ["cards", "thermal", "config", "sources", "terrain", "moon_terrain", "validation"];
    const files = await Promise.all(names.map((n) => fetch(`data/${n}.json`).then((r) => {
      if (!r.ok) throw new Error(`data/${n}.json: HTTP ${r.status}`);
      return r.json();
    })));
    names.forEach((n, i) => (DATA[n] = files[i]));
  } catch (err) {
    const box = document.getElementById("error");
    box.hidden = false;
    box.textContent = `Could not load the data (${err.message}). Run "python -m http.server" in the app folder and open http://localhost:8000.`;
    return;
  }

  showReferences();
  showChart();
  showTempChart();
  showSiteButtons("sites", siteOrder);
  showSiteButtons("tryit-sites", siteOrder);
  setUpTryIt();
  setUpDrop();
  setUpMission();
  showTerrainReferences();
  showTerrainCharts();
  showSiteButtons("terrain-sites", terrainOrder);
  showTerrainNotes();
  // The map is extra: if it breaks, say so and keep the rest of the page working.
  try {
    setUpMap();
  } catch (err) {
    mapMessage(`The map could not be drawn (${err.message}). The rest of the page works.`);
  }
  showValidation();
  showTable();
  setUpSources();
  setUpDetails();
  showFindings();
  showLeads();
  setUpReveals();
  setUpViews();
  selectSite(siteOrder[0]);  // open the first card so the page is never empty
}

start();
