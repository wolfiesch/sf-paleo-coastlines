/// <reference types="node" />

import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import type { PaleoRenderContext, PaleoTimeSlice } from "../types";
import { createPaleoCoastlineLayers } from "./paleoCoastlineLayer";

const baseContext: PaleoRenderContext = {
  paleoTimeSliceId: "20k_years_ago",
  showPaleoUncertainty: true,
  showTerrainFootprints: false,
  showBaySourceFootprints: false,
  showRivers: false,
  showSourceQualityGaps: false,
  showSourceSeams: false,
  paleoWaterLevelMeters: -120,
  terrainDetail: "ultra",
  terrainSurfaceSmoothing: "smooth",
  terrainTextureMode: "survey",
  terrainSourceMode: "best",
  selectedTerrainSourceId: "best_available_gate_shelf_fusion",
  sceneProfile: "emergence",
  showPlaceLabels: true,
  currentYearsBP: 20000,
};

function loadSlice(): PaleoTimeSlice {
  return JSON.parse(
    readFileSync(path.join(process.cwd(), "public/data/paleo-coastlines/slices/20k_years_ago.json"), "utf8"),
  ) as PaleoTimeSlice;
}

describe("paleo coastline terrain layers", () => {
  it("renders only the fused best-available terrain in Best source mode", () => {
    const layers = createPaleoCoastlineLayers([loadSlice()], baseContext) as { id: string }[];
    const terrainLayerIds = layers
      .map((layer) => layer.id)
      .filter((id) => id.startsWith("paleo-terrain-") && !id.startsWith("paleo-terrain-footprints-"));

    expect(terrainLayerIds).toEqual(["paleo-terrain-best_available_gate_shelf_fusion"]);
  });
});
