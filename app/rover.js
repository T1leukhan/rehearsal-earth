// rover.js - the sizes of the rover illustration in the "Try it" station.
// Illustration only: nothing here is measured data. Every size is worked out from the
// calculator inputs (mass, contact area, beam length) by the short formulas below, and
// the sinking depths come from the ground pressures the calculator already shows
// (groundPressurePa in formulas.js, with the gravity values from config.json).
// Tested by tests/test_rover_model.py.

// The starting example of the calculator: the rover is drawn at its "normal" size here.
const ROVER_DEFAULT = { massKg: 200, areaM2: 0.06, lengthM: 2 };
const ROVER_WHEELS = 6;   // six equal wheels share the contact area

// Sizes of the default rover in CSS pixels (the 3D model) - team drawing choices.
const ROVER_BASE_PX = {
  bodyLength: 120, bodyWidth: 72, bodyHeight: 30,
  wheelDiameter: 34, wheelWidth: 16,
  boomLength: 56,
};

// How far each scale may go, so the drawing always stays on screen and readable.
const ROVER_LIMITS = { body: [0.6, 1.6], wheel: [0.5, 2], boom: [0.4, 2.5] };

// The ground scenes (side views) draw the rover at this fraction of the 3D model size.
const SCENE_SCALE = 0.5;
// Sinking depth in scene units for each kPa of ground pressure ...
const SINK_PER_KPA = 0.2;
// ... but the deepest wheel never sinks more than this share of its diameter.
// If it would, all three depths shrink together, so they keep the same ratio.
const SINK_MAX_SHARE = 0.6;

// Keep x between lo and hi.
function clamp(x, lo, hi) {
  return Math.min(hi, Math.max(lo, x));
}

// The scales of the drawing, worked out from the inputs. An input is null when it is
// missing or outside its limits; that part is then drawn at its default size (scale 1)
// and marked as neutral.
//   body:  scale = cube root of (mass / 200 kg). A heavier rover of the same build has
//          more volume, and volume grows with the cube of each side.
//   wheel: scale = square root of (contact area per wheel / 0.01 m²). Each wheel gets
//          area / 6, and an area grows with the square of each side, so the wheel's
//          diameter and width both grow with the square root.
//   boom:  scale = beam length / 2 m (a straight line grows with the length itself).
// Each scale is then kept inside ROVER_LIMITS.
function roverScales(massKg, areaM2, lengthM) {
  const d = ROVER_DEFAULT, lim = ROVER_LIMITS;
  const massOk = isNumber(massKg) && massKg > 0;
  const areaOk = isNumber(areaM2) && areaM2 > 0;
  const lengthOk = isNumber(lengthM) && lengthM > 0;
  return {
    body: massOk ? clamp(Math.cbrt(massKg / d.massKg), lim.body[0], lim.body[1]) : 1,
    wheel: areaOk ? clamp(Math.sqrt((areaM2 / ROVER_WHEELS) / (d.areaM2 / ROVER_WHEELS)), lim.wheel[0], lim.wheel[1]) : 1,
    boom: lengthOk ? clamp(lengthM / d.lengthM, lim.boom[0], lim.boom[1]) : 1,
    // Neutral: the body and wheels need both the mass and the area; the boom needs the length.
    neutral: !(massOk && areaOk),
    boomNeutral: !lengthOk,
  };
}

// The sizes in pixels of the 3D model: each base size times its scale.
function roverSizesPx(scales) {
  const b = ROVER_BASE_PX;
  return {
    bodyLength: b.bodyLength * scales.body,
    bodyWidth: b.bodyWidth * scales.body,
    bodyHeight: b.bodyHeight * scales.body,
    wheelDiameter: b.wheelDiameter * scales.wheel,
    wheelWidth: b.wheelWidth * scales.wheel,
    boomLength: b.boomLength * scales.boom,
  };
}

// How deep each wheel is drawn into the ground in the scenes, in scene units.
// pressuresPa: { earth, moon, mars } in Pa, from groundPressurePa.
// wheelDiameter: the wheel diameter in the scene (scene units).
// depth = pressure in kPa × one shared factor, so the three depths have exactly the
// same ratio as the three pressures. The factor is SINK_PER_KPA, or smaller if the
// deepest wheel would otherwise sink more than SINK_MAX_SHARE of its diameter.
function sinkDepths(pressuresPa, wheelDiameter) {
  const kpa = {};
  let deepest = 0;
  for (const world of ["earth", "moon", "mars"]) {
    kpa[world] = pressuresPa[world] / 1000;
    deepest = Math.max(deepest, kpa[world]);
  }
  let factor = SINK_PER_KPA;
  const maxDepth = SINK_MAX_SHARE * wheelDiameter;
  if (deepest * factor > maxDepth) factor = maxDepth / deepest;
  return { earth: kpa.earth * factor, moon: kpa.moon * factor, mars: kpa.mars * factor, factor };
}
