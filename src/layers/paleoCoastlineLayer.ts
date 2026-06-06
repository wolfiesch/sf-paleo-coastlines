import { GeoJsonLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "deck.gl";
import { TerrainLayer } from "@deck.gl/geo-layers";
import type {
  PaleoCoastlineFeature,
  PaleoCoastlineProperties,
  PaleoRenderContext,
  PaleoTerrainConfig,
  PaleoTimeSlice,
  SceneProfile,
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

interface TerrainFootprint {
  sourceId: string;
  sourceLabel: string;
  note: string;
  category: "noaaBag" | "usgsCsmp" | "usgsOffshore" | "usgsGoldenGate" | "other";
  bounds: [number, number, number, number];
  heightRangeMeters: [number, number];
  polygon: [number, number, number][];
  position: [number, number, number];
}

interface ContourLabel {
  position: [number, number, number];
  text: string;
  elevationMeters: number;
  offsetMeters: number;
  kind: "waterline" | "exposed" | "submerged";
}

type GeoJsonCoordinates = number[] | GeoJsonCoordinates[];

const DEPTH_CONTOUR_BAND_METERS = 30;

interface SceneProfileConfig {
  verticalScale: number;
  waterAlpha: number;
  waterLineAlpha: number;
  terrainAmbient: number;
  terrainDiffuse: number;
  terrainShininess: number;
  terrainReliefStrength: number;
  revealStrengthScale: number;
  submergedStrengthScale: number;
  contourAlphaScale: number;
  contourWidthScale: number;
  emergenceAlphaScale: number;
  emergenceRadiusScale: number;
}

const SCENE_PROFILE_CONFIG: Record<SceneProfile, SceneProfileConfig> = {
  study: {
    verticalScale: 0.95,
    waterAlpha: 84,
    waterLineAlpha: 155,
    terrainAmbient: 0.5,
    terrainDiffuse: 0.55,
    terrainShininess: 12,
    terrainReliefStrength: 0.11,
    revealStrengthScale: 0.78,
    submergedStrengthScale: 0.82,
    contourAlphaScale: 0.78,
    contourWidthScale: 0.9,
    emergenceAlphaScale: 0.7,
    emergenceRadiusScale: 0.82,
  },
  relief: {
    verticalScale: 1.22,
    waterAlpha: 58,
    waterLineAlpha: 205,
    terrainAmbient: 0.34,
    terrainDiffuse: 0.86,
    terrainShininess: 26,
    terrainReliefStrength: 0.34,
    revealStrengthScale: 1.04,
    submergedStrengthScale: 0.95,
    contourAlphaScale: 1.08,
    contourWidthScale: 1.08,
    emergenceAlphaScale: 0.92,
    emergenceRadiusScale: 0.95,
  },
  emergence: {
    verticalScale: 1.12,
    waterAlpha: 42,
    waterLineAlpha: 235,
    terrainAmbient: 0.38,
    terrainDiffuse: 0.78,
    terrainShininess: 22,
    terrainReliefStrength: 0.24,
    revealStrengthScale: 1.28,
    submergedStrengthScale: 1.18,
    contourAlphaScale: 1.22,
    contourWidthScale: 1.18,
    emergenceAlphaScale: 1.18,
    emergenceRadiusScale: 1.18,
  },
};

function sceneConfig(profile: SceneProfile): SceneProfileConfig {
  return SCENE_PROFILE_CONFIG[profile] ?? SCENE_PROFILE_CONFIG.emergence;
}

function scaleAlpha(alpha: number, scale: number): number {
  return Math.max(0, Math.min(255, Math.round(alpha * scale)));
}

function lineRoleLabel(role: PaleoCoastlineProperties["line_role"]): string {
  if (role === "lower_sea_level_bound") return "Lower sea-level bound";
  if (role === "higher_sea_level_bound") return "Higher sea-level bound";
  if (role === "waterline_probe") return "Current waterline probe";
  return "Best estimate";
}

function probeLineColor(feature: PickedPaleoFeature, activeWaterLevel: number, profile: SceneProfileConfig): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const fade = Math.max(0, 1 - Math.abs(offsetMeters) / 20);
  const alpha = Math.round(80 + fade * 165);

  if (Math.abs(offsetMeters) <= 2.5) return [255, 255, 255, scaleAlpha(250, profile.contourAlphaScale)];
  if (offsetMeters > 0) return [255, 220, 118, scaleAlpha(alpha, profile.contourAlphaScale)];
  return [62, 214, 255, scaleAlpha(Math.max(70, alpha - 20), profile.contourAlphaScale)];
}

function getLineColor(feature: PickedPaleoFeature, activeWaterLevel: number, profile: SceneProfileConfig): [number, number, number, number] {
  if (feature.properties.line_role === "waterline_probe") return probeLineColor(feature, activeWaterLevel, profile);
  if (feature.properties.line_role === "estimate") return [70, 220, 238, 235];
  if (feature.properties.line_role === "lower_sea_level_bound") return [114, 184, 255, 125];
  return [255, 207, 92, 125];
}

function getLineWidth(feature: PickedPaleoFeature, activeWaterLevel: number, profile: SceneProfileConfig): number {
  if (feature.properties.line_role === "waterline_probe") {
    const offsetMeters = Math.abs(feature.properties.elevation_m - activeWaterLevel);
    if (offsetMeters <= 2.5) return 3.4 * profile.contourWidthScale;
    return (offsetMeters <= 10 ? 1.8 : 1.15) * profile.contourWidthScale;
  }
  return feature.properties.line_role === "estimate" ? 3 : 1.5;
}

function depthContourColor(feature: PickedPaleoFeature, activeWaterLevel: number, profile: SceneProfileConfig): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const distance = Math.abs(offsetMeters);
  const fade = Math.max(0, 1 - distance / DEPTH_CONTOUR_BAND_METERS);
  if (distance <= 2.5) return [255, 255, 255, scaleAlpha(235, profile.contourAlphaScale)];
  if (offsetMeters > 0) return [255, 218, 96, scaleAlpha(72 + fade * 92, profile.contourAlphaScale)];
  return [42, 125, 176, scaleAlpha(56 + fade * 86, profile.contourAlphaScale)];
}

function depthContourWidth(feature: PickedPaleoFeature, activeWaterLevel: number, profile: SceneProfileConfig): number {
  const distance = Math.abs(feature.properties.elevation_m - activeWaterLevel);
  if (distance <= 2.5) return 2.8 * profile.contourWidthScale;
  return (Math.abs(feature.properties.elevation_m % 10) < 0.1 ? 1.25 : 0.7) * profile.contourWidthScale;
}

function contourLabelColor(label: ContourLabel, profile: SceneProfileConfig): [number, number, number, number] {
  if (label.kind === "waterline") return [255, 255, 255, scaleAlpha(245, profile.contourAlphaScale)];
  if (label.kind === "exposed") return [255, 222, 96, scaleAlpha(215, profile.contourAlphaScale)];
  return [78, 221, 255, scaleAlpha(195, profile.contourAlphaScale)];
}

function contourLabelSize(label: ContourLabel): number {
  return label.kind === "waterline" ? 11 : 10;
}

function contourLabelText(elevationMeters: number, offsetMeters: number): string {
  if (Math.abs(offsetMeters) <= 2.5) return `${elevationMeters} m WL`;
  if (offsetMeters > 0) return `+${Math.round(offsetMeters)} m`;
  return `${Math.round(offsetMeters)} m`;
}

function contourLabelQuota(kind: ContourLabel["kind"]): number {
  if (kind === "waterline") return 8;
  if (kind === "exposed") return 5;
  return 4;
}

function shorelineGlowColor(feature: PickedPaleoFeature, activeWaterLevel: number, strength: "outer" | "inner", profile: SceneProfileConfig): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const distance = Math.abs(offsetMeters);
  const fade = Math.max(0, 1 - distance / 4.5);
  const baseAlpha = strength === "outer" ? 62 : 130;
  const alpha = scaleAlpha(baseAlpha * fade, profile.contourAlphaScale);
  if (offsetMeters > 0) return [255, 221, 104, alpha];
  return strength === "outer" ? [88, 228, 255, alpha] : [232, 255, 255, alpha];
}

function shorelineGlowWidth(feature: PickedPaleoFeature, activeWaterLevel: number, strength: "outer" | "inner", profile: SceneProfileConfig): number {
  const distance = Math.abs(feature.properties.elevation_m - activeWaterLevel);
  const fade = Math.max(0, 1 - distance / 4.5);
  return (strength === "outer" ? 12 + fade * 6 : 5 + fade * 4) * profile.contourWidthScale;
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

function waterPlaneForSlice(slice: PaleoTimeSlice, profile: SceneProfileConfig): WaterPlaneFeature[] {
  const terrain = primaryTerrainForSlice(slice);
  if (!terrain) return [];

  const [west, south, east, north] = terrain.bounds;
  const elevation = terrainZ(terrain, slice.seaLevelMeters, profile);

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
  return terrain.sourceId.includes("crm") || terrain.sourceId.includes("cudem") || terrain.sourceId.includes("etopo");
}

function terrainFootprintCategory(terrain: PaleoTerrainConfig): TerrainFootprint["category"] {
  if (terrain.sourceId.includes("noaa_nos")) return "noaaBag";
  if (terrain.sourceId.includes("csmp")) return "usgsCsmp";
  if (terrain.sourceId.includes("farallon") || terrain.sourceId.includes("rittenburg")) return "usgsOffshore";
  if (terrain.sourceId.includes("ds684")) return "usgsGoldenGate";
  return "other";
}

function terrainFootprintColor(category: TerrainFootprint["category"], alpha: number): [number, number, number, number] {
  if (category === "noaaBag") return [70, 210, 255, alpha];
  if (category === "usgsCsmp") return [255, 208, 92, alpha];
  if (category === "usgsOffshore") return [190, 124, 255, alpha];
  if (category === "usgsGoldenGate") return [110, 255, 170, alpha];
  return [235, 244, 255, alpha];
}

function shortTerrainLabel(terrain: TerrainFootprint): string {
  if (terrain.sourceId.includes("h12109")) return "H12109";
  if (terrain.sourceId.includes("h12110")) return "H12110";
  if (terrain.sourceId.includes("h12111")) return "H12111";
  if (terrain.sourceId.includes("h11965")) return "H11965";
  if (terrain.sourceId.includes("h13334")) return "H13334";
  if (terrain.sourceId.includes("w00477")) return "W00477";
  if (terrain.sourceId.includes("w00614")) return "W00614";
  if (terrain.sourceId.includes("tomales")) return "Tomales";
  if (terrain.sourceId.includes("point_reyes")) return "Point Reyes";
  if (terrain.sourceId.includes("bolinas")) return "Bolinas";
  if (terrain.sourceId.includes("offshore_sf")) return "Offshore SF";
  if (terrain.sourceId.includes("pacifica")) return "Pacifica";
  if (terrain.sourceId.includes("half_moon")) return "Half Moon";
  if (terrain.sourceId.includes("san_gregorio")) return "San Gregorio";
  if (terrain.sourceId.includes("farallon_escarpment")) return "Escarpment";
  if (terrain.sourceId.includes("rittenburg")) return "Rittenburg";
  if (terrain.sourceId.includes("ds684")) return "SF Bar";
  return terrain.sourceLabel.split(",")[0];
}

function terrainFootprintsForSlice(
  slice: PaleoTimeSlice,
  activeWaterLevel: number,
  profile: SceneProfileConfig,
): TerrainFootprint[] {
  const terrain = primaryTerrainForSlice(slice);
  if (!terrain) return [];

  const zMeters = terrainZ(terrain, activeWaterLevel, profile, 26);
  return terrainStackForSlice(slice)
    .filter((item) => !isBroadTerrain(item))
    .map((item) => {
      const [west, south, east, north] = item.bounds;
      return {
        sourceId: item.sourceId,
        sourceLabel: item.sourceLabel,
        note: item.note,
        category: terrainFootprintCategory(item),
        bounds: item.bounds,
        heightRangeMeters: item.heightRangeMeters,
        polygon: [
          [west, south, zMeters],
          [east, south, zMeters],
          [east, north, zMeters],
          [west, north, zMeters],
          [west, south, zMeters],
        ],
        position: [(west + east) / 2, (south + north) / 2, zMeters + 16],
      };
    });
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
  if (mode === "bottom") return terrain.textures?.seafloorCharacter ?? terrain.textures?.surveySonarHybrid ?? terrain.textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  if (mode === "hybrid") return terrain.textures?.surveySonarHybrid ?? terrain.textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  if (mode === "sonar") return terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  if (mode === "survey") return terrain.textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? terrain.textures?.shadedRelief ?? terrain.texture;
  return terrain.textures?.shadedRelief ?? terrain.texture;
}

function elevationDecoderForTerrain(terrain: PaleoTerrainConfig, profile: SceneProfileConfig): PaleoTerrainConfig["elevationDecoder"] {
  return {
    rScaler: terrain.elevationDecoder.rScaler * profile.verticalScale,
    gScaler: terrain.elevationDecoder.gScaler * profile.verticalScale,
    bScaler: terrain.elevationDecoder.bScaler * profile.verticalScale,
    offset: terrain.elevationDecoder.offset * profile.verticalScale,
  };
}

function terrainZ(terrain: PaleoTerrainConfig, elevationMeters: number, profile: SceneProfileConfig, zOffsetMeters = 0): number {
  return (elevationMeters * terrain.verticalExaggeration * profile.verticalScale) + zOffsetMeters;
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

function elevatedFeature(
  feature: PaleoCoastlineFeature,
  terrain: PaleoTerrainConfig | null,
  zOffsetOverride: number | undefined,
  profile: SceneProfileConfig,
): PaleoCoastlineFeature {
  if (!terrain) return feature;

  const zOffset = zOffsetOverride ?? (feature.properties.line_role === "waterline_probe" ? 1.8 : 1.2);
  const zMeters = terrainZ(terrain, feature.properties.elevation_m, profile, zOffset);
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
  profile: SceneProfileConfig,
): EmergencePoint[] {
  if (!terrain) return [];

  const points: EmergencePoint[] = [];
  for (const feature of features) {
    if (feature.properties.line_role !== "waterline_probe") continue;
    const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
    if (offsetMeters <= 0 || offsetMeters > 15) continue;

    const positions = extractPositions(feature.geometry.coordinates);
    const stride = Math.max(1, Math.ceil(positions.length / 18));
    const zMeters = terrainZ(terrain, feature.properties.elevation_m, profile, 3.4);

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

function contourLabelsForWaterLevel(
  features: PaleoCoastlineFeature[],
  terrain: PaleoTerrainConfig | null,
  activeWaterLevel: number,
  profile: SceneProfileConfig,
): ContourLabel[] {
  if (!terrain) return [];

  const candidates: ContourLabel[] = [];

  for (const feature of features) {
    if (feature.properties.line_role !== "waterline_probe") continue;

    const elevationMeters = feature.properties.elevation_m;
    const offsetMeters = elevationMeters - activeWaterLevel;
    const distance = Math.abs(offsetMeters);
    const isWaterline = distance <= 2.5;
    const isNearestTenMeterStep = Math.abs(distance - 10) <= 2.5;
    if (!isWaterline && !isNearestTenMeterStep) continue;

    const positions = extractPositions(feature.geometry.coordinates);
    if (positions.length < 12) continue;

    const midpoint = positions[Math.floor(positions.length / 2)];
    if (typeof midpoint?.[0] !== "number" || typeof midpoint?.[1] !== "number") continue;

    const kind: ContourLabel["kind"] = isWaterline ? "waterline" : offsetMeters > 0 ? "exposed" : "submerged";
    candidates.push({
      position: [midpoint[0], midpoint[1], terrainZ(terrain, elevationMeters, profile, isWaterline ? 12 : 9)],
      text: contourLabelText(elevationMeters, offsetMeters),
      elevationMeters,
      offsetMeters,
      kind,
    });
  }

  const quotas: Record<ContourLabel["kind"], number> = {
    waterline: 0,
    exposed: 0,
    submerged: 0,
  };
  const occupiedCells = new Set<string>();

  return candidates
    .sort((a, b) => {
      if (a.kind === "waterline" && b.kind !== "waterline") return -1;
      if (a.kind !== "waterline" && b.kind === "waterline") return 1;
      return Math.abs(a.offsetMeters) - Math.abs(b.offsetMeters);
    })
    .filter((label) => {
      if (quotas[label.kind] >= contourLabelQuota(label.kind)) return false;

      const cellX = Math.round(label.position[0] / 0.11);
      const cellY = Math.round(label.position[1] / 0.08);
      const cellKey = `${cellX}:${cellY}`;
      if (occupiedCells.has(cellKey)) return false;

      occupiedCells.add(cellKey);
      quotas[label.kind] += 1;
      return true;
    });
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
  const profile = sceneConfig(context.sceneProfile);
  const rawProbeFeatures = probeFeaturesForWaterLevel(data, slice, activeWaterLevel);
  const activeProbeFeatures = rawProbeFeatures.filter((feature) => Math.abs(feature.properties.elevation_m - activeWaterLevel) <= 2.5);
  const emergencePoints = emergencePointsForWaterLevel(rawProbeFeatures, terrain, activeWaterLevel, profile);
  const contourLabels = contourLabelsForWaterLevel(rawProbeFeatures, terrain, activeWaterLevel, profile);
  const terrainFootprints = context.showTerrainFootprints ? terrainFootprintsForSlice(slice, activeWaterLevel, profile) : [];
  const features = [
    ...slice.coastline.features,
    ...activeProbeFeatures,
    ...(context.showPaleoUncertainty ? slice.uncertainty.features : []),
  ].map((feature) => elevatedFeature(feature, terrain, undefined, profile));
  const shorelineGlowFeatures = activeProbeFeatures.map((feature) => elevatedFeature(feature, terrain, 3.2, profile));
  const depthContourFeatures = rawProbeFeatures.map((feature) => elevatedFeature(feature, terrain, undefined, profile));

  const terrainLayers = terrainStackForSlice(slice).map((terrain, index) =>
    new TerrainLayer({
      id: `paleo-terrain-${terrain.sourceId}`,
      elevationData: terrain.elevationData,
      texture: textureForTerrain(terrain, context.terrainTextureMode),
      bounds: terrain.bounds,
      elevationDecoder: elevationDecoderForTerrain(terrain, profile),
      meshMaxError: meshMaxErrorForTerrain(terrain, index, context.terrainDetail),
      wireframe: false,
      material: {
        ambient: profile.terrainAmbient,
        diffuse: profile.terrainDiffuse,
        shininess: profile.terrainShininess,
        specularColor: [60, 70, 78],
      },
      _subLayerProps: {
        mesh: {
          extensions: [terrainRevealExtension],
          terrainRevealBandMeters: isBroadTerrain(terrain) ? 28 : 44,
          terrainRevealEnabled: true,
          terrainRevealReliefStrength: (isBroadTerrain(terrain) ? 0.7 : 1) * profile.terrainReliefStrength,
          terrainRevealStrength: (isBroadTerrain(terrain) ? 0.24 : 0.42) * profile.revealStrengthScale,
          terrainRevealSubmergedStrength: (isBroadTerrain(terrain) ? 0.14 : 0.26) * profile.submergedStrengthScale,
          terrainRevealWaterLevelZ: terrainZ(terrain, activeWaterLevel, profile),
        },
      },
    }),
  );

  const waterLayer = new PolygonLayer<WaterPlaneFeature>({
    id: "paleo-water",
    data: waterPlaneForSlice(waterSlice, profile),
    pickable: false,
    filled: true,
    stroked: true,
    getPolygon: (item) => item.polygon,
    getFillColor: [24, 112, 166, profile.waterAlpha],
    getLineColor: [188, 248, 255, profile.waterLineAlpha],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
  });

  const terrainFootprintFillLayer = new PolygonLayer<TerrainFootprint>({
    id: "paleo-terrain-footprints-fill",
    data: terrainFootprints,
    pickable: true,
    filled: true,
    stroked: true,
    getPolygon: (item) => item.polygon,
    getFillColor: (item) => terrainFootprintColor(item.category, 18),
    getLineColor: (item) => terrainFootprintColor(item.category, 220),
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    parameters: {
      depthCompare: "always",
      depthWriteEnabled: false,
    },
  });

  const terrainFootprintLabelLayer = new TextLayer<TerrainFootprint>({
    id: "paleo-terrain-footprints-labels",
    data: terrainFootprints,
    pickable: false,
    getPosition: (item) => item.position,
    getText: shortTerrainLabel,
    getSize: (item) => item.category === "usgsOffshore" ? 12 : 11,
    getColor: (item) => terrainFootprintColor(item.category, 245),
    getAngle: 0,
    getTextAnchor: "middle",
    getAlignmentBaseline: "center",
    sizeUnits: "pixels",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontWeight: 700,
    outlineWidth: 2,
    outlineColor: [2, 8, 23, 230],
    parameters: {
      depthCompare: "always",
      depthWriteEnabled: false,
    },
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
    getLineColor: (feature) => depthContourColor(feature, activeWaterLevel, profile),
    getLineWidth: (feature) => depthContourWidth(feature, activeWaterLevel, profile),
  });

  const contourLabelLayer = new TextLayer<ContourLabel>({
    id: "paleo-contour-labels",
    data: contourLabels,
    pickable: false,
    getPosition: (item) => item.position,
    getText: (item) => item.text,
    getSize: contourLabelSize,
    getColor: (item) => contourLabelColor(item, profile),
    getTextAnchor: "middle",
    getAlignmentBaseline: "center",
    sizeUnits: "pixels",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontWeight: 800,
    outlineWidth: 2,
    outlineColor: [2, 8, 23, 235],
    background: true,
    getBackgroundColor: (item) => item.kind === "waterline" ? [2, 8, 23, 168] : [2, 8, 23, 120],
    backgroundPadding: [2, 1],
    parameters: {
      depthCompare: "always",
      depthWriteEnabled: false,
    },
  });

  const shorelineGlowOuterLayer = new GeoJsonLayer<PaleoCoastlineProperties>({
    id: "paleo-waterline-glow-outer",
    data: {
      type: "FeatureCollection",
      features: shorelineGlowFeatures,
    } as never,
    pickable: false,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1,
    getLineColor: (feature) => shorelineGlowColor(feature, activeWaterLevel, "outer", profile),
    getLineWidth: (feature) => shorelineGlowWidth(feature, activeWaterLevel, "outer", profile),
  });

  const shorelineGlowInnerLayer = new GeoJsonLayer<PaleoCoastlineProperties>({
    id: "paleo-waterline-glow-inner",
    data: {
      type: "FeatureCollection",
      features: shorelineGlowFeatures,
    } as never,
    pickable: false,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1,
    getLineColor: (feature) => shorelineGlowColor(feature, activeWaterLevel, "inner", profile),
    getLineWidth: (feature) => shorelineGlowWidth(feature, activeWaterLevel, "inner", profile),
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
    getRadius: (item) => (180 + (15 - item.offsetMeters) * 14) * profile.emergenceRadiusScale,
    getFillColor: (item) => {
      const alpha = scaleAlpha(135 + (15 - item.offsetMeters) * 7, profile.emergenceAlphaScale);
      return [255, 232, 92, alpha];
    },
    getLineColor: [255, 255, 255, scaleAlpha(190, profile.emergenceAlphaScale)],
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
    getLineColor: (feature) => getLineColor(feature, activeWaterLevel, profile),
    getLineWidth: (feature) => getLineWidth(feature, activeWaterLevel, profile),
    autoHighlight: true,
    highlightColor: [255, 255, 255, 180],
  });

  return [
    ...terrainLayers,
    waterLayer,
    terrainFootprintFillLayer,
    terrainFootprintLabelLayer,
    depthContourLayer,
    contourLabelLayer,
    shorelineGlowOuterLayer,
    shorelineGlowInnerLayer,
    coastlineLayer,
    emergenceLayer,
  ];
}

export function getPaleoTooltip(object: unknown) {
  if (!object || typeof object !== "object") return null;

  if ("sourceLabel" in object && "heightRangeMeters" in object) {
    const terrain = object as TerrainFootprint;
    return {
      text: `${terrain.sourceLabel}\n${terrain.heightRangeMeters[0]} to ${terrain.heightRangeMeters[1]} m\n${terrain.note}`,
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

  if (!("properties" in object)) return null;

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
