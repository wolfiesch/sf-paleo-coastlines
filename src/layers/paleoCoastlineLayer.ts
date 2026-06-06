import { GeoJsonLayer, PolygonLayer } from "deck.gl";
import { TerrainLayer } from "@deck.gl/geo-layers";
import type {
  PaleoCoastlineFeature,
  PaleoCoastlineProperties,
  PaleoRenderContext,
  PaleoTerrainConfig,
  PaleoTimeSlice,
  TerrainDetailLevel,
} from "../types";

interface WaterPlaneFeature {
  label: string;
  seaLevelMeters: number;
  polygon: [number, number, number][];
}

interface PickedPaleoFeature {
  properties: PaleoCoastlineProperties;
}

function lineRoleLabel(role: PaleoCoastlineProperties["line_role"]): string {
  if (role === "lower_sea_level_bound") return "Lower sea-level bound";
  if (role === "higher_sea_level_bound") return "Higher sea-level bound";
  if (role === "waterline_probe") return "Current waterline probe";
  return "Best estimate";
}

function getLineColor(feature: PickedPaleoFeature): [number, number, number, number] {
  if (feature.properties.line_role === "waterline_probe") return [255, 255, 255, 245];
  if (feature.properties.line_role === "estimate") return [70, 220, 238, 235];
  if (feature.properties.line_role === "lower_sea_level_bound") return [114, 184, 255, 125];
  return [255, 207, 92, 125];
}

function getLineWidth(feature: PickedPaleoFeature): number {
  if (feature.properties.line_role === "waterline_probe") return 2.5;
  return feature.properties.line_role === "estimate" ? 3 : 1.5;
}

function selectedSlice(data: PaleoTimeSlice[], context: PaleoRenderContext): PaleoTimeSlice | null {
  return data.find((item) => item.id === context.paleoTimeSliceId)
    ?? data.find((item) => item.id === "20k_years_ago")
    ?? null;
}

function terrainStackForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig[] {
  if (slice.terrains?.length) return slice.terrains;
  return slice.terrain ? [slice.terrain] : [];
}

function primaryTerrainForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig | null {
  return terrainStackForSlice(slice)[0] ?? null;
}

function waterPlaneForSlice(slice: PaleoTimeSlice): WaterPlaneFeature[] {
  const terrain = primaryTerrainForSlice(slice);
  if (!terrain) return [];

  const [west, south, east, north] = terrain.bounds;
  const elevation = slice.seaLevelMeters * terrain.verticalExaggeration;

  return [{
    label: slice.label,
    seaLevelMeters: slice.seaLevelMeters,
    polygon: [
      [west, south, elevation],
      [east, south, elevation],
      [east, north, elevation],
      [west, north, elevation],
      [west, south, elevation],
    ],
  }];
}

function nearestProbeLevel(level: number, levels: number[]): number | null {
  if (!levels.length) return null;

  return levels.reduce((nearest, candidate) => (
    Math.abs(candidate - level) < Math.abs(nearest - level) ? candidate : nearest
  ), levels[0]);
}

function probeFeaturesForWaterLevel(
  data: PaleoTimeSlice[],
  slice: PaleoTimeSlice,
  waterLevelMeters: number,
): PaleoCoastlineFeature[] {
  const probe = slice.waterlineProbe ?? data.find((item) => item.waterlineProbe)?.waterlineProbe;
  if (!probe) return [];

  const level = nearestProbeLevel(waterLevelMeters, probe.levelsMeters);
  if (level == null) return [];

  return probe.contours.features.filter((feature) => feature.properties.elevation_m === level);
}

function isBroadTerrain(terrain: PaleoTerrainConfig): boolean {
  return terrain.sourceId.includes("crm") || terrain.sourceId.includes("etopo");
}

function meshMaxErrorForTerrain(
  terrain: PaleoTerrainConfig,
  terrainIndex: number,
  detail: TerrainDetailLevel,
): number {
  if (detail === "fast") {
    return isBroadTerrain(terrain) || terrainIndex === 0 ? 6 : 2.5;
  }

  if (detail === "survey") {
    return isBroadTerrain(terrain) || terrainIndex === 0 ? 1.2 : 0.35;
  }

  return isBroadTerrain(terrain) || terrainIndex === 0 ? 2.5 : 0.8;
}

export function createPaleoCoastlineLayers(data: PaleoTimeSlice[], context: PaleoRenderContext) {
  const slice = selectedSlice(data, context);
  if (!slice) return [];

  const activeWaterLevel = context.paleoWaterLevelMeters ?? slice.seaLevelMeters;
  const waterSlice = {
    ...slice,
    seaLevelMeters: activeWaterLevel,
  };

  const features = [
    ...slice.coastline.features,
    ...probeFeaturesForWaterLevel(data, slice, activeWaterLevel),
    ...(context.showPaleoUncertainty ? slice.uncertainty.features : []),
  ];

  const terrainLayers = terrainStackForSlice(slice).map((terrain, index) =>
    new TerrainLayer({
      id: `paleo-terrain-${terrain.sourceId}`,
      elevationData: terrain.elevationData,
      texture: terrain.texture,
      bounds: terrain.bounds,
      elevationDecoder: terrain.elevationDecoder,
      meshMaxError: meshMaxErrorForTerrain(terrain, index, context.terrainDetail),
      wireframe: false,
      material: {
        ambient: 0.45,
        diffuse: 0.65,
        shininess: 18,
        specularColor: [60, 70, 78],
      },
    }),
  );

  const waterLayer = new PolygonLayer<WaterPlaneFeature>({
    id: "paleo-water",
    data: waterPlaneForSlice(waterSlice),
    pickable: false,
    filled: true,
    stroked: true,
    getPolygon: (item) => item.polygon,
    getFillColor: [30, 125, 185, 88],
    getLineColor: [170, 240, 255, 170],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
  });

  const coastlineLayer = new GeoJsonLayer<PaleoCoastlineProperties>({
    id: "paleo-coastline",
    data: {
      type: "FeatureCollection",
      features,
    } as never,
    pickable: true,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1,
    getLineColor,
    getLineWidth,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 180],
  });

  return [...terrainLayers, waterLayer, coastlineLayer];
}

export function getPaleoTooltip(object: unknown) {
  if (!object || typeof object !== "object" || !("properties" in object)) return null;

  const feature = object as PickedPaleoFeature;
  return {
    text: `${feature.properties.label}\n${lineRoleLabel(feature.properties.line_role)}\nSea level ${feature.properties.elevation_m} m\n${feature.properties.source_label}`,
    style: {
      backgroundColor: "rgba(4, 20, 28, 0.92)",
      color: "#c8fbff",
      fontSize: "13px",
      padding: "8px 10px",
      borderRadius: "6px",
      border: "1px solid rgba(103, 232, 249, 0.35)",
    },
  };
}
