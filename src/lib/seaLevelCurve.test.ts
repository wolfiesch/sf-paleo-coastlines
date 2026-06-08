import { describe, expect, it } from "vitest";
import {
  MAX_YEARS_BP,
  MIN_YEARS_BP,
  seaLevelForYearsBP,
  yearsBPForSeaLevel,
} from "./seaLevelCurve";

describe("seaLevelForYearsBP", () => {
  it("matches the project slice anchors exactly", () => {
    expect(seaLevelForYearsBP(0)).toBe(0);
    expect(seaLevelForYearsBP(5000)).toBe(-3);
    expect(seaLevelForYearsBP(10000)).toBe(-56);
    expect(seaLevelForYearsBP(20000)).toBe(-120);
  });

  it("linearly interpolates between control points", () => {
    // Between [2000,-1] and [3000,-1.8], the midpoint is -1.4.
    expect(seaLevelForYearsBP(2500)).toBeCloseTo(-1.4, 5);
  });

  it("clamps outside the supported range", () => {
    expect(seaLevelForYearsBP(-500)).toBe(0);
    expect(seaLevelForYearsBP(99999)).toBe(-120);
  });

  it("decreases monotonically as years increase", () => {
    let prev = Infinity;
    for (let y = MIN_YEARS_BP; y <= MAX_YEARS_BP; y += 250) {
      const level = seaLevelForYearsBP(y);
      expect(level).toBeLessThanOrEqual(prev);
      prev = level;
    }
  });
});

describe("yearsBPForSeaLevel", () => {
  it("round-trips at anchors", () => {
    expect(yearsBPForSeaLevel(0)).toBeCloseTo(0, 5);
    expect(yearsBPForSeaLevel(-56)).toBeCloseTo(10000, 5);
    expect(yearsBPForSeaLevel(-120)).toBeCloseTo(20000, 5);
  });

  it("clamps outside the supported range", () => {
    expect(yearsBPForSeaLevel(5)).toBe(MIN_YEARS_BP);
    expect(yearsBPForSeaLevel(-999)).toBe(MAX_YEARS_BP);
  });

  it("interpolates the inverse between control points", () => {
    // Between [8000,-28] and [9000,-42], depth -35 sits at t=0.5:
    // t = (-35 - -28) / (-42 - -28) = -7 / -14 = 0.5
    // year = 8000 + 0.5 * (9000 - 8000) = 8500.
    expect(yearsBPForSeaLevel(-35)).toBeCloseTo(8500, 5);
    // Round-trip through a non-anchor year to exercise both directions.
    expect(yearsBPForSeaLevel(seaLevelForYearsBP(7500))).toBeCloseTo(7500, 5);
  });
});
