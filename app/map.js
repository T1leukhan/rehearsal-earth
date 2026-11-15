// map.js - the site map, shared by the Thermal and Terrain tabs.
// Uses Leaflet (loaded from a CDN in index.html) with NASA GIBS satellite imagery
// (Blue Marble: Next Generation, Web Mercator tiles, levels 0 to 8).
// Every coordinate and number comes from the JSON files in DATA (see app.js):
//   thermal points ......... thermal.json  sites.<site>.latitude / longitude
//   terrain square centre .. terrain.json  sites.<site>.square_centre_lat_lon_deg
//   swing, temperature ..... thermal.json  sites.<site>.mean_swing.K / mean_temperature.C
//   Moon swing ............. config.json   references.moon.thermal_swing_K.value
//   colour bands ........... config.json   map_bands
//   median slope ........... terrain.json  sites.<site>.areas.square_10km.slope_deg.median
// If Leaflet or the tiles cannot load, a message is shown and the rest of the page works.

let siteMap = null;   // the Leaflet map, or null if Leaflet did not load
let markerBounds = null;   // the box around every marker, used for the starting view
const MAP_PADDING_PX = 24;   // space kept between the outer markers and the map edge
const GIBS_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
// NASA asks users of GIBS imagery to credit GIBS, part of NASA's ESDIS.
const GIBS_CREDIT = 'Imagery: <a href="https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api">NASA GIBS</a> ' +
  "(Blue Marble: Next Generation), part of NASA's ESDIS";

// Every point to draw: one thermal point per site, plus a terrain square centre
// wherever it is not on the thermal point (today: Altiplano).
function mapPoints() {
  const points = [];
  for (const [site, t] of Object.entries(DATA.thermal.sites)) {
    points.push({ site, kind: "thermal", lat: t.latitude, lon: t.longitude });
    const ter = DATA.terrain.sites[site];
    if (ter) {
      const [lat, lon] = ter.square_centre_lat_lon_deg;
      if (lat !== t.latitude || lon !== t.longitude) points.push({ site, kind: "square", lat, lon });
    }
  }
  return points;
}

// The site's mean swing as a percent of the Moon's swing, or null.
function swingPercent(site) {
  const swing = DATA.thermal.sites[site].mean_swing.K;
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  return swing === null ? null : (100 * swing) / lunar;
}

// Which colour band (0, 1, 2) a percent falls in, using config.json map_bands; null if not assessed.
function bandOf(percent) {
  if (percent === null) return null;
  const bands = DATA.config.map_bands.bands;
  for (let i = 0; i < bands.length; i++) {
    const b = bands[i];
    if ((b.min_percent === null || percent >= b.min_percent) && (b.max_percent === null || percent < b.max_percent)) return i;
  }
  return null;
}

// Show a short message under the map (used when the map or its tiles fail).
function mapMessage(text) {
  const box = document.getElementById("map-message");
  box.textContent = text;
  box.hidden = false;
}

// The popup for one point, built from page elements (not HTML strings).
function popupContent(point) {
  const t = DATA.thermal.sites[point.site];
  const ter = DATA.terrain.sites[point.site];
  const lunar = DATA.config.references.moon.thermal_swing_K.value;
  const pct = swingPercent(point.site);
  const box = el("div", "popup");
  box.append(el("strong", "", point.kind === "square" ? `${siteName(point.site)}: terrain square centre` : siteName(point.site)));
  const lines = [
    `Mean day–night swing: ${fmt(t.mean_swing.K, "K")}` + (pct === null ? "" : ` (${pct.toFixed(1)}% of the Moon's ${lunar} K)`),
    `Mean temperature: ${fmt(t.mean_temperature.C, "°C")}`,
  ];
  if (ter) {
    lines.push(`Median terrain slope: ${fmt(ter.areas.square_10km.slope_deg.median, "°")} (10 km square)`);
    if (point.kind === "square") {
      lines.push(`${(ter.offset_m.straight_line / 1000).toFixed(1)} km from the thermal point`);
    }
  } else {
    const gap = DATA.terrain.not_assessed.find((x) => x.site === point.site);
    lines.push(`Median terrain slope: not assessed${gap ? ` (${gap.reason})` : ""}`);
  }
  for (const line of lines) box.append(el("div", "", line));
  return box;
}

// The legend under the map: the three bands, "not assessed" if needed, and the square marker.
function showMapLegend() {
  const legend = document.getElementById("map-legend");
  const add = (cls, text) => {
    const item = el("span", "legend-item");
    item.append(el("span", cls), document.createTextNode(text));
    legend.append(item);
  };
  DATA.config.map_bands.bands.forEach((b, i) => add(`site-marker band-${i}`, b.label));
  if (Object.keys(DATA.thermal.sites).some((s) => swingPercent(s) === null)) add("site-marker band-none", "swing not assessed");
  if (mapPoints().some((p) => p.kind === "square")) add("square-marker", "terrain square centre (line to its thermal point)");
}

function setUpMap() {
  showMapLegend();
  if (typeof L === "undefined") {
    mapMessage("The map library could not load (offline?). The rest of the page works.");
    document.getElementById("map").hidden = true;
    return;
  }
  // zoomControl keeps the + / - buttons. zoomSnap 0.25 lets the starting view
  // use quarter zoom steps, so fitting the markers leaves only the padding spare.
  siteMap = L.map("map", { zoomControl: true, zoomSnap: 0.25, scrollWheelZoom: false, worldCopyJump: false });
  // NASA GIBS WMTS tiles. The address is row then column ({y}/{x}), as NASA's
  // capabilities file gives it. This layer exists only up to level 8, so closer
  // zoom levels reuse (enlarge) the level-8 tiles instead of asking for tiles that do not exist.
  const tiles = L.tileLayer(GIBS_URL, {
    maxNativeZoom: 8,
    maxZoom: 10,
    attribution: GIBS_CREDIT,
  }).addTo(siteMap);
  // One message, however many tiles fail.
  tiles.once("tileerror", () => mapMessage("Map tiles could not load (offline?). The markers and the rest of the page still work."));

  const points = mapPoints();
  for (const p of points) {
    const band = p.kind === "thermal" ? bandOf(swingPercent(p.site)) : null;
    const cls = p.kind === "thermal" ? `site-marker band-${band === null ? "none" : band}` : "square-marker";
    // The marker's own element carries the site and its coordinates, so tests can check them.
    const html = `<span class="${cls}" data-site="${p.site}" data-kind="${p.kind}" data-lat="${p.lat}" data-lon="${p.lon}"></span>`;
    const marker = L.marker([p.lat, p.lon], {
      icon: L.divIcon({ className: "marker-wrap", html, iconSize: [20, 20], iconAnchor: [10, 10] }),
      title: p.kind === "thermal" ? siteName(p.site) : `${siteName(p.site)} terrain square`,
      alt: siteName(p.site),
      keyboard: true,
    }).addTo(siteMap);
    marker.bindPopup(() => popupContent(p));
    marker.on("click", () => selectSite(p.site));
    if (p.kind === "square") {
      const t = DATA.thermal.sites[p.site];
      L.polyline([[t.latitude, t.longitude], [p.lat, p.lon]], { className: "square-link", weight: 2, dashArray: "4 4" }).addTo(siteMap);
    }
  }
  // Starting view: the smallest view that shows every marker, plus the padding.
  markerBounds = L.latLngBounds(points.map((p) => [p.lat, p.lon]));
  fitAllMarkers();
}

// Show every marker with a little padding (the starting view).
function fitAllMarkers() {
  siteMap.fitBounds(markerBounds, { padding: [MAP_PADDING_PX, MAP_PADDING_PX], maxZoom: 4 });
}

// Make the chosen site's markers stand out (called from selectSite in app.js).
function highlightMarker(site) {
  for (const m of document.querySelectorAll("#map .site-marker, #map .square-marker")) {
    m.classList.toggle("selected", m.dataset.site === site);
  }
}

// The map lives in one box that moves to the open station, above its site buttons.
// Views without a map (start page, hub, other stations) send it back to its off-screen
// parking place, where it stays laid out so Leaflet can always measure it.
function moveMapTo(tabName) {
  const slot = document.querySelector(`.map-slot[data-tab="${tabName}"]`) || document.getElementById("map-park");
  const box = document.getElementById("map-box");
  if (slot && box.parentElement !== slot) slot.append(box);
  if (siteMap) siteMap.invalidateSize();   // Leaflet must re-measure after moving
}
