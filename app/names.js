// names.js - how site names are written on the page. Display only.
// The data files keep their short keys (for example "atacama"), and every piece of code
// that looks a site up still uses the key. This file only turns a key into words:
//   short form: chart labels, site buttons, map popups, tables and sentences
//   long form:  card titles (and Mission Match verdict titles)

const SITE_NAMES = {
  atacama: { short: "Atacama Desert", long: "Atacama Desert (Chile)" },
  altiplano: { short: "Altiplano", long: "Altiplano (Bolivia/Chile)" },
  maunakea: { short: "Mauna Kea", long: "Mauna Kea (Hawaii)" },
  haughton: { short: "Haughton Crater", long: "Haughton Crater (Devon Island, Canada)" },
  dryvalleys: { short: "Dry Valleys", long: "Dry Valleys (Antarctica)" },
  // The negative-control site, used by Validation once its data request has finished.
  amazon: { short: "Amazon rainforest", long: "Amazon rainforest (negative control)" },
};

// The Moon's terrain reference (Malapert massif, near the lunar south pole).
const MOON_TERRAIN_NAME = "Moon: Malapert massif";

// The short name for a site key; an unknown key is shown as it is.
function siteName(key) {
  return SITE_NAMES[key] ? SITE_NAMES[key].short : key;
}

// The long name, with its region, for card titles.
function siteLongName(key) {
  return SITE_NAMES[key] ? SITE_NAMES[key].long : key;
}

// Sentences stored in the data (for example in validation.json) name sites by their key.
// This writes each key as its short name; every other word and every number stays the same.
function withNames(text) {
  return text.replace(/\b[a-z]+\b/g, (word) => (SITE_NAMES[word] ? SITE_NAMES[word].short : word));
}
