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
  showWaterSurface: true,
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

    // The fused tileset intentionally renders as two layers: broad z8-12 over
    // the full extent plus a z13+ twin confined to the detail box.
    expect(terrainLayerIds).toEqual([
      "paleo-terrain-best_available_gate_shelf_fusion",
      "paleo-terrain-best_available_gate_shelf_fusion-detail",
    ]);
  });

  it("renders the water surface plane immediately after the terrain stack", () => {
    const layers = createPaleoCoastlineLayers([loadSlice()], baseContext) as { id: string }[];
    const layerIds = layers.map((layer) => layer.id);
    const lastTerrainIndex = layerIds.reduce(
      (last, id, index) => (id.startsWith("paleo-terrain-") && !id.startsWith("paleo-terrain-footprints-") ? index : last),
      -1,
    );

    expect(layerIds[lastTerrainIndex + 1]).toBe("paleo-water-surface");
  });

  it("hides the water surface plane when toggled off", () => {
    const layers = createPaleoCoastlineLayers(
      [loadSlice()],
      { ...baseContext, showWaterSurface: false },
    ) as { id: string; props: { visible?: boolean } }[];
    const waterSurface = layers.find((layer) => layer.id === "paleo-water-surface");

    expect(waterSurface?.props.visible).toBe(false);
  });
});
