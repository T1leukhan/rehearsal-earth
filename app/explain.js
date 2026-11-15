// explain.js - rounding, input limits and the plain-English lines of the "Try it" panel.
// The sentences only use numbers that are already shown on the page, so every
// number a reader sees can be checked against the results above it.
// Tested by pipeline/test_formulas.py.

// Pressure as shown on the page: kPa with 1 decimal (e.g. 5400 Pa -> 5.4).
function shownKpa(pressurePa) {
  return Number((pressurePa / 1000).toFixed(1));
}

// Expansion as shown on the page: 3 significant figures (e.g. 13.56 -> 13.6).
function shownMm(mm) {
  return Number(mm.toPrecision(3));
}

// Check one input against its limits. Returns null if fine, or a short message.
function rangeMessage(value, min, max, unit) {
  if (value === null || !Number.isFinite(value)) return "Enter a number.";
  if (value < min || value > max) return `Unrealistic: use ${min} to ${max} ${unit}.`;
  return null;
}

// "On Earth this rover presses 6.1 times harder than on the Moon ..."
// Inputs are the kPa values exactly as displayed.
function pressureSentence(earthKpa, moonKpa, marsKpa) {
  if (moonKpa === 0 || marsKpa === 0) {
    return "These pressures are below 0.1 kPa, too small to compare at the precision shown.";
  }
  const vsMoon = (earthKpa / moonKpa).toFixed(1);
  const vsMars = (earthKpa / marsKpa).toFixed(1);
  return `On Earth this rover presses ${earthKpa}/${moonKpa} = ${vsMoon} times harder than on the Moon ` +
    `and ${earthKpa}/${marsKpa} = ${vsMars} times harder than on Mars, ` +
    "so, other things equal, an Earth soil test overstates wheel sinkage.";
}

// "On the Moon this beam grows N mm, vs M mm at atacama ..." plus a second
// sentence for the site with the lowest mean temperature (coldSite).
// Inputs are the mm values exactly as displayed; a mm value is null if that
// site has no measured swing.
function expansionSentence(site, moonMm, siteMm, coldSite, coldMm) {
  let text;
  if (siteMm === null) {
    text = `${site} has no measured swing, so its thermal cycling is not assessed.`;
  } else {
    const percent = (100 * siteMm / moonMm).toFixed(1);
    text = `On the Moon this beam grows ${moonMm} mm, vs ${siteMm} mm at ${site}, ` +
      `so ${site} tests only ${siteMm}/${moonMm} = ${percent}% of the thermal cycling.`;
  }

  // The coldest site: the one with the lowest mean temperature in thermal.json.
  if (coldSite === null || coldSite === undefined) return text;   // no site has a mean temperature
  if (coldSite === site) {
    text += ` ${site} is also the site with the lowest mean temperature.`;
  } else if (coldMm === null) {
    text += ` ${coldSite}, the site with the lowest mean temperature, has no measured swing, so it is not assessed.`;
  } else {
    const coldPercent = (100 * coldMm / moonMm).toFixed(1);
    text += ` ${coldSite}, the site with the lowest mean temperature, grows ${coldMm} mm, ` +
      `so it tests only ${coldMm}/${moonMm} = ${coldPercent}% of the lunar cycling.`;
  }
  return text;
}

// Gravity Drop values as shown on the page: 2 decimals (0.6386 s -> 0.64 s).
function shownDrop(x) {
  return Number(x.toFixed(2));
}

// One sentence for the Gravity Drop panel. Every input is a number exactly as
// displayed: h in m, the fall times in s, the impact speeds in m/s, and the Earth
// drop heights that match the Moon's and Mars's impact speeds, in m.
function dropSentence(h, tEarth, tMoon, vEarth, vMoon, hForMoon, hForMars) {
  const ratio = (tMoon / tEarth).toFixed(1);
  return `A ${h} m fall takes ${tMoon}/${tEarth} = ${ratio} times as long on the Moon as on Earth ` +
    `and lands at ${vMoon} m/s instead of ${vEarth} m/s, so a landing-gear drop test on Earth ` +
    `matches the Moon's impact speed from only ${hForMoon} m (Mars: ${hForMars} m), ` +
    "but it cannot reproduce the Moon's slower, longer fall.";
}
