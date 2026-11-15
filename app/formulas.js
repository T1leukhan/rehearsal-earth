// formulas.js - the two formulas used by the "Try it" panel.
// They live in their own file so the tests (pipeline/test_formulas.py) can load
// exactly the same code the page uses.

// Is x a usable number? (not null, not empty, not "abc")
function isNumber(x) {
  return typeof x === "number" && Number.isFinite(x);
}

// Ground pressure p = m * g / A, in pascals (Pa = N/m²).
// m: rover mass in kg, g: gravity in m/s², A: wheel contact area in m².
// Returns null if an input is missing, the mass is negative or the area is not above 0.
function groundPressurePa(massKg, g, areaM2) {
  if (!isNumber(massKg) || !isNumber(g) || !isNumber(areaM2)) return null;
  if (massKg < 0 || areaM2 <= 0) return null;
  return (massKg * g) / areaM2;
}

// Thermal expansion dL = alpha * L * dT, returned in millimetres.
// alpha: expansion coefficient in 1/K, L: beam length in m, dT: temperature swing in K.
// Returns null if an input is missing (for example a site with no measured swing).
function expansionMm(alphaPerK, lengthM, dTK) {
  if (!isNumber(alphaPerK) || !isNumber(lengthM) || !isNumber(dTK)) return null;
  if (lengthM < 0) return null;
  return alphaPerK * lengthM * dTK * 1000;   // * 1000 turns metres into millimetres
}

// ---- Gravity Drop panel ----------------------------------------------------------
// Allowed drop heights in metres (a short message is shown outside this range).
const DROP_LIMITS_M = { min: 0.1, max: 20 };

// Fall time t = sqrt(2 h / g), in seconds, for an ideal fall (no air resistance).
// h: drop height in m, g: gravity in m/s². Returns null for missing or impossible inputs.
function fallTimeS(heightM, g) {
  if (!isNumber(heightM) || !isNumber(g) || heightM < 0 || g <= 0) return null;
  return Math.sqrt((2 * heightM) / g);
}

// Impact speed v = sqrt(2 g h), in m/s, for the same ideal fall.
function impactSpeedMs(heightM, g) {
  if (!isNumber(heightM) || !isNumber(g) || heightM < 0 || g <= 0) return null;
  return Math.sqrt(2 * g * heightM);
}

// The other way round: the height h = v² / (2 g) that gives impact speed v under gravity g.
// Used to say how high an Earth drop test must be to match the Moon's impact speed.
function dropHeightForSpeedM(speedMs, g) {
  if (!isNumber(speedMs) || !isNumber(g) || speedMs < 0 || g <= 0) return null;
  return (speedMs * speedMs) / (2 * g);
}
