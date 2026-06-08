/**
 * Relative sea-level curve for the central California coast, last 20,000 years.
 *
 * Control points are anchored to the project's four science time slices
 * (0/0, 5000/-3, 10000/-56, 20000/-120 m) and shaped between anchors to follow
 * the post-glacial rise of Lambeck et al. 2014 (PNAS). These are approximate
 * relative heights; local RSL differs from global eustatic sea level, and this
 * curve does not model glacio-isostatic adjustment or tectonic motion.
 */
export const RSL_CONTROL_POINTS: ReadonlyArray<readonly [yearsBP: number, meters: number]> = [
  [0, 0], [1000, -0.5], [2000, -1], [3000, -1.8], [4000, -2.4], [5000, -3],
  [6000, -8], [7000, -16], [8000, -28], [9000, -42], [10000, -56],
  [11000, -64], [12000, -72], [13000, -80], [14000, -88], [15000, -95],
  [16000, -101], [17000, -107], [18000, -112], [19000, -116], [20000, -120],
];

export const MIN_YEARS_BP = RSL_CONTROL_POINTS[0][0];
export const MAX_YEARS_BP = RSL_CONTROL_POINTS[RSL_CONTROL_POINTS.length - 1][0];
const MAX_DEPTH_M = RSL_CONTROL_POINTS[RSL_CONTROL_POINTS.length - 1][1];

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

/** Sea-level meters (relative to present) for a given years-before-present. */
export function seaLevelForYearsBP(yearsBP: number): number {
  const y = clamp(yearsBP, MIN_YEARS_BP, MAX_YEARS_BP);
  for (let i = 1; i < RSL_CONTROL_POINTS.length; i += 1) {
    const [y1, m1] = RSL_CONTROL_POINTS[i];
    if (y <= y1) {
      const [y0, m0] = RSL_CONTROL_POINTS[i - 1];
      if (y1 === y0) return m1;
      const t = (y - y0) / (y1 - y0);
      return m0 + t * (m1 - m0);
    }
  }
  return MAX_DEPTH_M;
}

/** Inverse: years-before-present for a given sea-level depth. The curve is
 * monotonic (deeper = older), so this is well-defined. */
export function yearsBPForSeaLevel(meters: number): number {
  const m = clamp(meters, MAX_DEPTH_M, 0);
  for (let i = 1; i < RSL_CONTROL_POINTS.length; i += 1) {
    const [y1, m1] = RSL_CONTROL_POINTS[i];
    // meters decrease as index increases, so search for the bracketing pair.
    if (m >= m1) {
      const [y0, m0] = RSL_CONTROL_POINTS[i - 1];
      if (m1 === m0) return y0;
      const t = (m - m0) / (m1 - m0);
      return y0 + t * (y1 - y0);
    }
  }
  return MAX_YEARS_BP;
}
