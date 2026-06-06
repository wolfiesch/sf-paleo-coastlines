import { GeoJsonLayer, PolygonLayer, ScatterplotLayer } from "deck.gl";
import { TerrainLayer } from "@deck.gl/geo-layers";
import type {
  PaleoCoastlineFeature,
  PaleoCoastlineProperties,
  PaleoRenderContext,
  PaleoTerrainConfig,
  PaleoTimeSlice,
  TerrainDetailLevel,
  TerrainTextureMode,
} from "../types";
import { terrainRevealExtension } from "./terrainRevealExtension";

interface WaterPlaneFeature {
  label: string;
  seaLevelMeters: number;
  polygon: [number, number, number][];
}

interface PickedPaleoFeature {
  properties: PaleoCoastlineProperties;
}

interface EmergencePoint {
  position: [number, number, number];
  offsetMeters: number;
}

type GeoJsonCoordinates = number[] | GeoJsonCoordinates[];

const DEPTH_CONTOUR_BAND_METERS = 30;

function lineRoleLabel(role: PaleoCoastlineProperties["line_role"]): string {
  if (role === "lower_sea_level_bound") return "Lower sea-level bound";
  if (role === "higher_sea_level_bound") return "Higher sea-level bound";
  if (role === "waterline_probe") return "Current waterline probe";
  return "Best estimate";
}

function probeLineColor(feature: PickedPaleoFeature, activeWaterLevel: number): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const fade = Math.max(0, 1 - Math.abs(offsetMeters) / 20);
  const alpha = Math.round(80 + fade * 165);

  if (Math.abs(offsetMeters) <= 2.5) return [255, 255, 255, 250];
  if (offsetMeters > 0) return [255, 220, 118, alpha];
  return [62, 214, 255, Math.max(70, alpha - 20)];
}

function getLineColor(feature: PickedPaleoFeature, activeWaterLevel: number): [number, number, number, number] {
  if (feature.properties.line_role === "waterline_probe") return probeLineColor(feature, activeWaterLevel);
  if (feature.properties.line_role === "estimate") return [70, 220, 238, 235];
  if (feature.properties.line_role === "lower_sea_level_bound") return [114, 184, 255, 125];
  return [255, 207, 92, 125];
}

function getLineWidth(feature: PickedPaleoFeature, activeWaterLevel: number): number {
  if (feature.properties.line_role === "waterline_probe") {
    const offsetMeters = Math.abs(feature.properties.elevation_m - activeWaterLevel);
    if (offsetMeters <= 2.5) return 3.4;
    return offsetMeters <= 10 ? 1.8 : 1.15;
  }
  return feature.properties.line_role === "estimate" ? 3 : 1.5;
}

function depthContourColor(feature: PickedPaleoFeature, activeWaterLevel: number): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const distance = Math.abs(offsetMeters);
  const fade = Math.max(0, 1 - distance / DEPTH_CONTOUR_BAND_METERS);
  if (distance <= 2.5) return [255, 255, 255, 235];
  if (offsetMeters > 0) return [255, 218, 96, Math.round(72 + fade * 92)];
  return [42, 125, 176, Math.round(56 + fade * 86)];
}

function depthContourWidth(feature: PickedPaleoFeature, activeWaterLevel: number): number {
  const distance = Math.abs(feature.properties.elevation_m - activeWaterLevel);
  if (distance <= 2.5) return 2.8;
  return Math.abs(feature.properties.elevation_m % 10) < 0.1 ? 1.25 : 0.7;
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

  return probe.contours.features.filter((feature) => Math.abs(feature.properties.elevation_m - level) <= DEPTH_CONTOUR_BAND_METERS);
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

function textureForTerrain(terrain: PaleoTerrainConfig, mode: TerrainTextureMode): string {
  if (mode === "color") return terrain.textures?.depthColor ?? terrain.texture;
  if (mode === "hybrid") return terrain.textures?.surveySonarHybrid ?? terrain.textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  if (mode === "sonar") return terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  if (mode === "survey") return terrain.textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  return terrain.textures?.shadedRelief ?? terrain.texture;
}

function addZToCoordinates(coordinates: unknown, zMeters: number): unknown {
  if (!Array.isArray(coordinates)) return coordinates;
  if (
    coordinates.length >= 2
    && typeof coordinates[0] === "number"
    && typeof coordinates[1] === "number"
  ) {
    return [coordinates[0], coordinates[1], zMeters];
  }

  return (coordinates as GeoJsonCoordinates[]).map((item) => addZToCoordinates(item, zMeters));
}

function extractPositions(coordinates: unknown): number[][] {
  if (!Array.isArray(coordinates)) return [];
  if (
    coordinates.length >= 2
    && typeof coordinates[0] === "number"
    && typeof coordinates[1] === "number"
  ) {
    return [coordinates as number[]];
  }

  return coordinates.flatMap((item) => extractPositions(item));
}

function elevatedFeature(feature: PaleoCoastlineFeature, terrain: PaleoTerrainConfig | null): PaleoCoastlineFeature {
  if (!terrain) return feature;

  const zOffset = feature.properties.line_role === "waterline_probe" ? 1.8 : 1.2;
  const zMeters = feature.properties.elevation_m * terrain.verticalExaggeration + zOffset;
  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: addZToCoordinates(feature.geometry.coordinates, zMeters),
    },
  };
}

function emergencePointsForWaterLevel(
  features: PaleoCoastlineFeature[],
  terrain: PaleoTerrainConfig | null,
  activeWaterLevel: number,
): EmergencePoint[] {
  if (!terrain) return [];

  const points: EmergencePoint[] = [];
  for (const feature of features) {
    if (feature.properties.line_role !== "waterline_probe") continue;
    const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
    if (offsetMeters <= 0 || offsetMeters > 15) continue;

    const positions = extractPositions(feature.geometry.coordinates);
    const stride = Math.max(1, Math.ceil(positions.length / 18));
    const zMeters = feature.properties.elevation_m * terrain.verticalExaggeration + 3.4;

    for (let index = 0; index < positions.length; index += stride) {
      const position = positions[index];
      if (typeof position[0] !== "number" || typeof position[1] !== "number") continue;
      points.push({
        position: [position[0], position[1], zMeters],
        offsetMeters,
      });
      if (points.length >= 1800) return points;
    }
  }

  return points;
}

export function createPaleoCoastlineLayers(data: PaleoTimeSlice[], context: PaleoRenderContext) {
  const slice = selectedSlice(data, context);
  if (!slice) return [];

  const activeWaterLevel = context.paleoWaterLevelMeters ?? slice.seaLevelMeters;
  const waterSlice = {
    ...slice,
    seaLevelMeters: activeWaterLevel,
  };

  const terrain = primaryTerrainForSlice(slice);
  const rawProbeFeatures = probeFeaturesForWaterLevel(data, slice, activeWaterLevel);
  const activeProbeFeatures = rawProbeFeatures.filter((feature) => Math.abs(feature.properties.elevation_m - activeWaterLevel) <= 2.5);
  const emergencePoints = emergencePointsForWaterLevel(rawProbeFeatures, terrain, activeWaterLevel);
  const features = [
    ...slice.coastline.features,
    ...activeProbeFeatures,
    ...(context.showPaleoUncertainty ? slice.uncertainty.features : []),
  ].map((feature) => elevatedFeature(feature, terrain));
  const depthContourFeatures = rawProbeFeatures.map((feature) => elevatedFeature(feature, terrain));

  const terrainLayers = terrainStackForSlice(slice).map((terrain, index) =>
    new TerrainLayer({
      id: `paleo-terrain-${terrain.sourceId}`,
      elevationData: terrain.elevationData,
      texture: textureForTerrain(terrain, context.terrainTextureMode),
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
      _subLayerProps: {
        mesh: {
          extensions: [terrainRevealExtension],
          terrainRevealBandMeters: isBroadTerrain(terrain) ? 28 : 44,
          terrainRevealEnabled: true,
          terrainRevealStrength: isBroadTerrain(terrain) ? 0.24 : 0.42,
          terrainRevealWaterLevelZ: activeWaterLevel * terrain.verticalExaggeration,
        },
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
    getFillColor: [24, 112, 166, 76],
    getLineColor: [188, 248, 255, 185],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
  });

  const depthContourLayer = new GeoJsonLayer<PaleoCoastlineProperties>({
    id: "paleo-depth-contours",
    data: {
      type: "FeatureCollection",
      features: depthContourFeatures,
    } as never,
    pickable: false,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 0.5,
    getLineColor: (feature) => depthContourColor(feature, activeWaterLevel),
    getLineWidth: (feature) => depthContourWidth(feature, activeWaterLevel),
  });

  const emergenceLayer = new ScatterplotLayer<EmergencePoint>({
    id: "paleo-emergence-glints",
    data: emergencePoints,
    pickable: false,
    stroked: true,
    filled: true,
    radiusUnits: "meters",
    radiusMinPixels: 2.2,
    radiusMaxPixels: 7,
    getPosition: (item) => item.position,
    getRadius: (item) => 180 + (15 - item.offsetMeters) * 14,
    getFillColor: (item) => {
      const alpha = Math.round(135 + (15 - item.offsetMeters) * 7);
      return [255, 232, 92, alpha];
    },
    getLineColor: [255, 255, 255, 190],
    getLineWidth: 1,
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
    getLineColor: (feature) => getLineColor(feature, activeWaterLevel),
    getLineWidth: (feature) => getLineWidth(feature, activeWaterLevel),
    autoHighlight: true,
    highlightColor: [255, 255, 255, 180],
  });

  return [...terrainLayers, waterLayer, depthContourLayer, coastlineLayer, emergenceLayer];
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
