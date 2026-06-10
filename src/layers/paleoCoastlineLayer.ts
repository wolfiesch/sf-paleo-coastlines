import { GeoJsonLayer, PolygonLayer, ScatterplotLayer, TextLayer } from "deck.gl";
import { TerrainLayer } from "@deck.gl/geo-layers";
import type {
  BaySourceFootprintCollection,
  BaySourceFootprintFeature,
  BaySourceFootprintProperties,
  PaleoCoastlineFeature,
  PaleoCoastlineProperties,
  PaleoRenderContext,
  PaleoRiverCollection,
  PaleoRiverFeature,
  PaleoRiverProperties,
  PaleoTerrainConfig,
  PaleoTimeSlice,
  SceneProfile,
  SourceSeamAudit,
  SourceSeamLocalHeight,
  SourceSeamVerticalOverlap,
  SourceQualityGapCollection,
  SourceQualityGapFeature,
  SourceQualityGapProperties,
  TerrainDetailLevel,
  TerrainQualityTier,
  TerrainTextureMode,
} from "../types";
import { terrainRevealExtension } from "./terrainRevealExtension";
import { PALEO_PLACE_LABELS, type PaleoPlaceLabel } from "../lib/paleoPlaceLabels";
import { SmoothTerrainMeshLayer } from "./smoothTerrainMeshLayer";

interface PickedPaleoFeature {
  properties: PaleoCoastlineProperties;
}

interface PickedBaySourceFeature {
  properties: BaySourceFootprintProperties;
}

interface PickedSourceQualityGapFeature {
  properties: SourceQualityGapProperties;
}

interface SourceSeamRenderTarget {
  position: [number, number, number];
  categories: string[];
  edgePixelCount: number;
  edgePixelsInCluster: number;
  importance: number;
  localHeight?: SourceSeamLocalHeight;
  priorityScore: number;
  recommendedView: string;
  verticalOverlap: SourceSeamVerticalOverlap;
  transitionIndex: number;
  targetIndex: number;
}

interface EmergencePoint {
  position: [number, number, number];
  offsetMeters: number;
}

interface TerrainFootprint {
  sourceId: string;
  sourceLabel: string;
  note: string;
  category: "noaaBag" | "noaaMultibeam" | "noaaOcm" | "usgsConed" | "usgsCsmp" | "usgsOffshore" | "usgsLandLidar" | "usgsGoldenGate" | "other";
  qualityTier: TerrainQualityTier;
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

interface TerrainTileConfig {
  elevationData: string;
  textures: {
    shadedRelief: string;
    depthColor?: string;
    surveyComposite?: string;
  };
  minZoom: number;
  maxZoom: number;
  tileSize: number;
  extent: [number, number, number, number];
}

const DEPTH_CONTOUR_BAND_METERS = 30;
const Z_BANDS = {
  probeContour: 18,
  coastline: 22,
  riverChannel: 24,
  shorelineGlow: 26,
  emergencePoint: 34,
  contourLabel: 52,
  sourceQualityGap: 58,
  sourceFootprint: 62,
  sourceSeam: 76,
  sourceLabel: 84,
} as const;

const ANNOTATION_PARAMETERS = {
  depthCompare: "always",
  depthWriteEnabled: false,
} as const;

// Display-space meters added above the waterline Z so near-flat shelf terrain
// sitting at exactly the waterline does not z-fight the water surface plane.
const WATER_SURFACE_Z_NUDGE_METERS = 1.5;
// The plane extends past the terrain edges so the surrounding flat-ocean
// backdrop carries the same water tone instead of ending at a hard seam.
const WATER_SURFACE_PAD_DEGREES = 1.5;

export const TERRAIN_TILESETS: Record<string, Omit<TerrainTileConfig, "extent">> = {
  best_available_gate_shelf_fusion: {
    elevationData: "/data/paleo-coastlines/terrain-tiles/best_available_gate_shelf_fusion/elevation/{z}/{x}/{y}.png",
    textures: {
      shadedRelief: "/data/paleo-coastlines/terrain-tiles/best_available_gate_shelf_fusion/relief/{z}/{x}/{y}.png",
      depthColor: "/data/paleo-coastlines/terrain-tiles/best_available_gate_shelf_fusion/color/{z}/{x}/{y}.png",
      surveyComposite: "/data/paleo-coastlines/terrain-tiles/best_available_gate_shelf_fusion/composite/{z}/{x}/{y}.png",
    },
    minZoom: 12,
    maxZoom: 15,
    tileSize: 256,
  },
  usgs_2023_sf_lidar_dem: {
    elevationData: "/data/paleo-coastlines/terrain-tiles/usgs_2023_sf_lidar_dem/elevation/{z}/{x}/{y}.png",
    textures: {
      shadedRelief: "/data/paleo-coastlines/terrain-tiles/usgs_2023_sf_lidar_dem/relief/{z}/{x}/{y}.png",
      depthColor: "/data/paleo-coastlines/terrain-tiles/usgs_2023_sf_lidar_dem/color/{z}/{x}/{y}.png",
      surveyComposite: "/data/paleo-coastlines/terrain-tiles/usgs_2023_sf_lidar_dem/composite/{z}/{x}/{y}.png",
    },
    minZoom: 12,
    maxZoom: 16,
    tileSize: 256,
  },
  usgs_coned_sf_2m_gate_shelf: {
    elevationData: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_gate_shelf/elevation/{z}/{x}/{y}.png",
    textures: {
      shadedRelief: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_gate_shelf/relief/{z}/{x}/{y}.png",
      depthColor: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_gate_shelf/color/{z}/{x}/{y}.png",
      surveyComposite: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_gate_shelf/composite/{z}/{x}/{y}.png",
    },
    minZoom: 12,
    maxZoom: 15,
    tileSize: 256,
  },
  usgs_coned_sf_2m_farallon_shelf: {
    elevationData: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_farallon_shelf/elevation/{z}/{x}/{y}.png",
    textures: {
      shadedRelief: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_farallon_shelf/relief/{z}/{x}/{y}.png",
      depthColor: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_farallon_shelf/color/{z}/{x}/{y}.png",
      surveyComposite: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_farallon_shelf/composite/{z}/{x}/{y}.png",
    },
    minZoom: 12,
    maxZoom: 15,
    tileSize: 256,
  },
  usgs_coned_sf_2m_south_bay_edge: {
    elevationData: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_south_bay_edge/elevation/{z}/{x}/{y}.png",
    textures: {
      shadedRelief: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_south_bay_edge/relief/{z}/{x}/{y}.png",
      depthColor: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_south_bay_edge/color/{z}/{x}/{y}.png",
      surveyComposite: "/data/paleo-coastlines/terrain-tiles/usgs_coned_sf_2m_south_bay_edge/composite/{z}/{x}/{y}.png",
    },
    minZoom: 12,
    maxZoom: 14,
    tileSize: 256,
  },
};

interface SceneProfileConfig {
  verticalScale: number;
  waterDepthFogStrength: number;
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
    waterDepthFogStrength: 0.09,
    terrainAmbient: 0.5,
    terrainDiffuse: 0.55,
    terrainShininess: 12,
    terrainReliefStrength: 0.14,
    revealStrengthScale: 0.84,
    submergedStrengthScale: 0.88,
    contourAlphaScale: 0.78,
    contourWidthScale: 0.9,
    emergenceAlphaScale: 0.7,
    emergenceRadiusScale: 0.82,
  },
  relief: {
    verticalScale: 1.42,
    waterDepthFogStrength: 0.2,
    terrainAmbient: 0.28,
    terrainDiffuse: 0.96,
    terrainShininess: 32,
    terrainReliefStrength: 0.52,
    revealStrengthScale: 1.12,
    submergedStrengthScale: 1.05,
    contourAlphaScale: 1.14,
    contourWidthScale: 1.14,
    emergenceAlphaScale: 0.92,
    emergenceRadiusScale: 0.95,
  },
  emergence: {
    verticalScale: 1.3,
    waterDepthFogStrength: 0.18,
    terrainAmbient: 0.31,
    terrainDiffuse: 0.9,
    terrainShininess: 30,
    terrainReliefStrength: 0.42,
    revealStrengthScale: 1.68,
    submergedStrengthScale: 1.46,
    contourAlphaScale: 1.36,
    contourWidthScale: 1.34,
    emergenceAlphaScale: 1.42,
    emergenceRadiusScale: 1.32,
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
  // No white "waterline" branch here: the active shoreline is a single contour
  // drawn by the glow + coastline layers. Every contour this layer draws is
  // context, so it always reads as a quiet exposed/submerged depth ring.
  if (offsetMeters > 0) return [255, 224, 98, scaleAlpha(22 + fade * 38, profile.contourAlphaScale)];
  return [48, 205, 255, scaleAlpha(18 + fade * 34, profile.contourAlphaScale)];
}

function depthContourWidth(feature: PickedPaleoFeature, profile: SceneProfileConfig): number {
  return (Math.abs(feature.properties.elevation_m % 10) < 0.1 ? 1.0 : 0.55) * profile.contourWidthScale;
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
  if (kind === "waterline") return 4;
  if (kind === "exposed") return 5;
  return 4;
}

function shorelineGlowColor(feature: PickedPaleoFeature, activeWaterLevel: number, strength: "outer" | "inner", profile: SceneProfileConfig): [number, number, number, number] {
  const offsetMeters = feature.properties.elevation_m - activeWaterLevel;
  const distance = Math.abs(offsetMeters);
  const fade = Math.max(0, 1 - distance / 5.5);
  const baseAlpha = strength === "outer" ? 42 : 170;
  const alpha = scaleAlpha(baseAlpha * fade, profile.contourAlphaScale);
  if (offsetMeters > 0) return [255, 230, 118, alpha];
  return strength === "outer" ? [88, 228, 255, alpha] : [232, 255, 255, alpha];
}

function shorelineGlowWidth(feature: PickedPaleoFeature, activeWaterLevel: number, strength: "outer" | "inner", profile: SceneProfileConfig): number {
  const distance = Math.abs(feature.properties.elevation_m - activeWaterLevel);
  const fade = Math.max(0, 1 - distance / 5.5);
  // Slim soft halo (outer) over a crisp core (inner). Kept narrow so the active
  // waterline reads as a clean glowing line rather than a thick painted band.
  return (strength === "outer" ? 4 + fade * 2.5 : 2.5 + fade * 1.5) * profile.contourWidthScale;
}

function selectedSlice(data: PaleoTimeSlice[], context: PaleoRenderContext): PaleoTimeSlice | null {
  return data.find((item) => item.id === context.paleoTimeSliceId)
    ?? data.find((item) => item.id === "20k_years_ago")
    ?? null;
}

function terrainStackForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig[] {
  const terrains = slice.terrains?.length ? slice.terrains : slice.terrain ? [slice.terrain] : [];
  return [...terrains].sort((a, b) => terrainRenderPriority(a) - terrainRenderPriority(b));
}

function primaryTerrainForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig | null {
  return terrainStackForSlice(slice)[0] ?? null;
}

function bestAvailableTerrainForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig | null {
  const terrains = terrainStackForSlice(slice);
  return terrains.find((terrain) => terrain.sourceId.includes("best_available"))
    ?? terrains.find((terrain) => terrain.sourceId.includes("fusion"))
    ?? terrains.find((terrain) => terrain.sourceId.includes("coned_sf_2m"))
    ?? terrains.find((terrain) => !isBroadTerrain(terrain))
    ?? terrains[0]
    ?? null;
}

function uniqueTerrains(terrains: (PaleoTerrainConfig | null | undefined)[]): PaleoTerrainConfig[] {
  const seen = new Set<string>();
  return terrains.filter((terrain): terrain is PaleoTerrainConfig => {
    if (!terrain || seen.has(terrain.sourceId)) return false;
    seen.add(terrain.sourceId);
    return true;
  });
}

function bestAvailableTerrainStackForSlice(slice: PaleoTimeSlice): PaleoTerrainConfig[] {
  const terrains = terrainStackForSlice(slice);
  const best = bestAvailableTerrainForSlice(slice);

  return uniqueTerrains([best ?? terrains[0]]);
}

function terrainStackForRender(slice: PaleoTimeSlice, context: PaleoRenderContext): PaleoTerrainConfig[] {
  const terrains = terrainStackForSlice(slice);

  if (context.terrainSourceMode === "stack") return terrains;

  if (context.terrainSourceMode === "single" && context.selectedTerrainSourceId) {
    const selected = terrains.find((terrain) => terrain.sourceId === context.selectedTerrainSourceId);
    if (selected) return [selected];
  }

  return bestAvailableTerrainStackForSlice(slice);
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

// The single contour elevation closest to the active sea level. The waterline is
// drawn as just this one contour - a continuous line, offshore islands included -
// instead of a +/-2.5 m band. A band made gently sloping shelves show several
// parallel "shorelines" when there is really only one: those extra lines were
// just neighbouring depth contours all being painted as the waterline.
function activeWaterlineLevel(
  features: PaleoCoastlineFeature[],
  activeWaterLevel: number,
): number | null {
  let nearest: number | null = null;
  let nearestDistance = Infinity;
  for (const feature of features) {
    if (feature.properties.line_role !== "waterline_probe") continue;
    const distance = Math.abs(feature.properties.elevation_m - activeWaterLevel);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearest = feature.properties.elevation_m;
    }
  }
  return nearest;
}

function terrainQualityTier(terrain: PaleoTerrainConfig): TerrainQualityTier {
  if (terrain.qualityTier) return terrain.qualityTier;
  if (terrain.sourceId.includes("crm") || terrain.sourceId.includes("cudem") || terrain.sourceId.includes("etopo")) return "broad";
  if (terrain.sourceId.includes("noaa_ocm_area_a_interferometric")) return "bay_mosaic";
  if (terrain.sourceId.includes("noaa_ocm_area_a") || terrain.sourceId.includes("noaa_nos") || terrain.sourceId.includes("sf_bay_1m")) return "source_survey";
  if (terrain.sourceId.includes("csmp") || terrain.sourceId.includes("ds684")) return "nearshore_detail";
  if (terrain.sourceId.includes("farallon") || terrain.sourceId.includes("rittenburg")) return "offshore_survey";
  return "reference";
}

function terrainRenderPriority(terrain: PaleoTerrainConfig): number {
  if (terrain.sourceId.includes("crm")) return 10;
  if (terrain.sourceId.includes("cudem")) return 20;
  if (typeof terrain.renderPriority === "number") return terrain.renderPriority;

  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 10;
  if (tier === "bay_mosaic") return 40;
  if (tier === "source_survey") return 70;
  if (tier === "nearshore_detail") return 85;
  if (tier === "offshore_survey") return 90;
  return 50;
}

function isBroadTerrain(terrain: PaleoTerrainConfig): boolean {
  return terrainQualityTier(terrain) === "broad";
}

function terrainVisualLiftMeters(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  const sourceJitter = stableSourceOffsetMeters(terrain.sourceId);
  if (terrain.sourceId.includes("crm")) return 0;
  if (terrain.sourceId.includes("cudem")) return 4;
  if (terrain.sourceId.includes("usgs_coned_sf_2m_gate_shelf")) return 11 + sourceJitter;
  if (terrain.sourceId.includes("usgs_coned_sf_2m_farallon_shelf")) return 11 + sourceJitter;
  if (terrain.sourceId.includes("usgs_coned_sf_2m_south_bay_edge")) return 11 + sourceJitter;
  if (tier === "bay_mosaic") return 8 + sourceJitter;
  if (tier === "source_survey") return sourceSurveyLiftMeters(terrain) + sourceJitter;
  if (tier === "nearshore_detail") return 20 + sourceJitter;
  if (tier === "offshore_survey") return 24 + sourceJitter;
  return 6 + sourceJitter;
}

function sourceSurveyLiftMeters(terrain: PaleoTerrainConfig): number {
  if (terrain.sourceId.includes("noaa_nos") && terrain.sourceId.includes("_2m")) return 12;
  if (terrain.sourceId.includes("noaa_nos") && terrain.sourceId.includes("_1m")) return 16;
  if (terrain.sourceId.includes("noaa_nos")) return 14;
  if (terrain.sourceId.includes("noaa_ocm_area_a")) return 18;
  return 14;
}

function stableSourceOffsetMeters(sourceId: string): number {
  let hash = 0;
  for (let index = 0; index < sourceId.length; index += 1) {
    hash = (hash * 31 + sourceId.charCodeAt(index)) % 997;
  }
  return (hash % 13) * 0.18;
}

function terrainDepthBiasParameters(terrain: PaleoTerrainConfig) {
  const tier = terrainQualityTier(terrain);
  const units = tier === "broad" ? 0 : tier === "bay_mosaic" ? -24 : tier === "source_survey" ? -48 : -64;
  return {
    depthWriteEnabled: true,
    polygonOffsetFill: true,
    polygonOffset: [0, units] as [number, number],
  };
}

function terrainLayerOpacity(terrain: PaleoTerrainConfig, context: PaleoRenderContext): number {
  if (context.terrainSourceMode !== "best") return 1;
  if (terrain.sourceId.includes("best_available") || terrain.sourceId.includes("fusion")) return 1;
  if (terrain.sourceId.includes("2023_sf_lidar")) return 1;
  return 1;
}

function terrainRevealBandMeters(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 36;
  if (tier === "bay_mosaic") return 52;
  if (tier === "source_survey") return 62;
  return 58;
}

function terrainRevealReliefScale(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 0.78;
  if (tier === "bay_mosaic") return 1.04;
  return 1.2;
}

function terrainRevealReliefStrengthForRender(
  terrain: PaleoTerrainConfig,
  context: PaleoRenderContext,
  profile: SceneProfileConfig,
): number {
  if (context.terrainTextureMode === "relief" || context.terrainTextureMode === "survey") {
    return terrainRevealReliefScale(terrain) * profile.terrainReliefStrength * 0.16;
  }
  return terrainRevealReliefScale(terrain) * profile.terrainReliefStrength;
}

function terrainRevealStrength(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 0.3;
  if (tier === "bay_mosaic") return 0.48;
  return 0.58;
}

function terrainSubmergedStrength(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 0.2;
  if (tier === "bay_mosaic") return 0.3;
  return 0.36;
}

function terrainDepthFogStrength(terrain: PaleoTerrainConfig): number {
  const tier = terrainQualityTier(terrain);
  if (tier === "broad") return 1.12;
  if (tier === "bay_mosaic") return 0.98;
  return 0.88;
}

function terrainMaterial(terrain: PaleoTerrainConfig, profile: SceneProfileConfig, textureMode: TerrainTextureMode) {
  const tier = terrainQualityTier(terrain);
  const detailBoost = tier === "broad" ? 0 : tier === "bay_mosaic" ? 0.08 : 0.14;
  const specularColor: [number, number, number] = tier === "broad" ? [60, 70, 78] : [78, 88, 96];

  if (textureMode === "relief") {
    // The relief texture is a baked grayscale hillshade, so it is lit flatly
    // (diffuse near zero). Ambient was 0.96, which pushed every light-gray
    // hillshade pixel to near-white - tolerable when only peaks were exposed,
    // but a blinding white sheet once a whole valley sits above the waterline.
    // A calmer ambient keeps the relief readable as soft pale terrain instead.
    return {
      ambient: 0.64,
      diffuse: 0.08,
      shininess: 1,
      specularColor: [8, 10, 12] as [number, number, number],
    };
  }

  if (textureMode === "survey") {
    // Survey composites already contain measured color/detail, but they are no
    // longer plain grayscale hillshade. A small amount of real mesh lighting
    // helps hills read as terrain without turning the map into harsh relief art.
    return {
      ambient: Math.max(0.38, 0.54 - detailBoost * 0.36),
      diffuse: tier === "broad" ? 0.2 : tier === "bay_mosaic" ? 0.24 : 0.28,
      shininess: 4,
      specularColor: [18, 22, 24] as [number, number, number],
    };
  }

  return {
    ambient: Math.max(0.22, profile.terrainAmbient - detailBoost * 0.7),
    diffuse: Math.min(1, profile.terrainDiffuse + detailBoost),
    shininess: profile.terrainShininess + (tier === "broad" ? 0 : tier === "bay_mosaic" ? 4 : 8),
    specularColor,
  };
}

function terrainFootprintCategory(terrain: PaleoTerrainConfig): TerrainFootprint["category"] {
  if (terrain.sourceId.includes("noaa_ocm_area_a")) return "noaaOcm";
  if (terrain.sourceId.includes("noaa_ncei")) return "noaaMultibeam";
  if (terrain.sourceId.includes("noaa_nos")) return "noaaBag";
  if (terrain.sourceId.includes("coned_sf_2m")) return "usgsConed";
  if (terrain.sourceId.includes("2023_sf_lidar")) return "usgsLandLidar";
  if (terrain.sourceId.includes("sf_bay_1m")) return "usgsGoldenGate";
  if (terrain.sourceId.includes("csmp")) return "usgsCsmp";
  if (terrain.sourceId.includes("farallon") || terrain.sourceId.includes("rittenburg")) return "usgsOffshore";
  if (terrain.sourceId.includes("ds684")) return "usgsGoldenGate";
  return "other";
}

function terrainFootprintColor(category: TerrainFootprint["category"], alpha: number): [number, number, number, number] {
  if (category === "noaaBag") return [70, 210, 255, alpha];
  if (category === "noaaMultibeam") return [99, 160, 255, alpha];
  if (category === "noaaOcm") return [70, 245, 190, alpha];
  if (category === "usgsConed") return [92, 180, 132, alpha];
  if (category === "usgsCsmp") return [255, 208, 92, alpha];
  if (category === "usgsOffshore") return [190, 124, 255, alpha];
  if (category === "usgsLandLidar") return [236, 241, 222, alpha];
  if (category === "usgsGoldenGate") return [110, 255, 170, alpha];
  return [235, 244, 255, alpha];
}

function shortTerrainLabel(terrain: TerrainFootprint): string {
  if (terrain.sourceId.includes("best_available_gate_shelf")) return "Best available";
  if (terrain.sourceId.includes("coned_sf_2m")) return "CoNED";
  if (terrain.sourceId.includes("2023_sf_lidar")) return "SF LiDAR";
  if (terrain.sourceId.includes("noaa_ocm_area_a_interferometric")) return "Area A mosaic";
  const ocmSurveyId = terrain.sourceId.match(/noaa_ocm_area_a_([a-z]{2}1b\d{2})_1m/);
  if (ocmSurveyId) return ocmSurveyId[1].toUpperCase();
  if (terrain.sourceId.includes("h12109")) return "H12109";
  if (terrain.sourceId.includes("h12110")) return "H12110";
  if (terrain.sourceId.includes("h12111")) return "H12111";
  if (terrain.sourceId.includes("h12112")) return "H12112";
  if (terrain.sourceId.includes("h12113")) return "H12113";
  if (terrain.sourceId.includes("h11965")) return "H11965";
  if (terrain.sourceId.includes("h13334")) return "H13334";
  if (terrain.sourceId.includes("w00477")) return "W00477";
  if (terrain.sourceId.includes("w00614")) return "W00614";
  if (terrain.sourceId.includes("ex0907")) return "EX0907";
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
  if (terrain.sourceId.includes("sf_bay_1m_north")) return "North Bay";
  if (terrain.sourceId.includes("sf_bay_1m_central")) return "Central Bay";
  if (terrain.sourceId.includes("sf_bay_1m_south")) return "South Bay";
  return terrain.sourceLabel.split(",")[0];
}

function terrainTierLabel(tier: TerrainQualityTier): string {
  if (tier === "broad") return "broad support surface";
  if (tier === "bay_mosaic") return "high-detail support mosaic";
  if (tier === "source_survey") return "source survey";
  if (tier === "nearshore_detail") return "nearshore detail patch";
  if (tier === "offshore_survey") return "offshore survey patch";
  return "reference surface";
}

function terrainFootprintsForSlice(
  slice: PaleoTimeSlice,
  activeWaterLevel: number,
  profile: SceneProfileConfig,
): TerrainFootprint[] {
  const terrain = primaryTerrainForSlice(slice);
  if (!terrain) return [];

  const zMeters = terrainZ(terrain, activeWaterLevel, profile, Z_BANDS.sourceFootprint);
  return terrainStackForSlice(slice)
    .filter((item) => !isBroadTerrain(item))
    .map((item) => {
      const [west, south, east, north] = item.bounds;
      return {
        sourceId: item.sourceId,
        sourceLabel: item.sourceLabel,
        note: item.note,
        category: terrainFootprintCategory(item),
        qualityTier: terrainQualityTier(item),
        bounds: item.bounds,
        heightRangeMeters: item.heightRangeMeters,
        polygon: [
          [west, south, zMeters],
          [east, south, zMeters],
          [east, north, zMeters],
          [west, north, zMeters],
          [west, south, zMeters],
        ],
        position: [(west + east) / 2, (south + north) / 2, terrainZ(terrain, activeWaterLevel, profile, Z_BANDS.sourceLabel)],
      };
    });
}

function baySourceFillColor(feature: PickedBaySourceFeature): [number, number, number, number] {
  const sensor = feature.properties.sensor_type.toLowerCase();
  const interpolation = feature.properties.interpolation.toLowerCase();
  const quality = feature.properties.quality_class.toLowerCase();

  if (quality.includes("direct") && quality.includes("1m")) return [92, 255, 178, 28];
  if (sensor.includes("multi")) return [75, 210, 255, 24];
  if (sensor.includes("interferometric")) return [190, 124, 255, interpolation === "yes" ? 20 : 26];
  if (sensor.includes("single")) return [255, 198, 92, 22];
  return [235, 244, 255, 18];
}

function baySourceLineColor(feature: PickedBaySourceFeature): [number, number, number, number] {
  const sensor = feature.properties.sensor_type.toLowerCase();
  const interpolation = feature.properties.interpolation.toLowerCase();
  const quality = feature.properties.quality_class.toLowerCase();

  if (quality.includes("direct") && quality.includes("1m")) return [118, 255, 190, 218];
  if (sensor.includes("multi")) return [88, 225, 255, 205];
  if (sensor.includes("interferometric")) return [205, 155, 255, interpolation === "yes" ? 175 : 210];
  if (sensor.includes("single")) return [255, 206, 110, 182];
  return [235, 244, 255, 160];
}

function baySourceLineWidth(feature: PickedBaySourceFeature): number {
  const quality = feature.properties.quality_class.toLowerCase();
  if (quality.includes("direct") && quality.includes("1m")) return 2.6;
  return 1.8;
}

function sourceQualityGapFillColor(feature: PickedSourceQualityGapFeature): [number, number, number, number] {
  const tier = feature.properties.tier;
  if (tier === "critical_gap") return [244, 63, 94, 46];
  if (tier === "support_gap") return [251, 146, 60, 40];
  if (tier === "coned_foundation") return [250, 204, 21, 24];
  if (tier === "mixed_foundation") return [163, 230, 53, 24];
  if (tier === "measured_detail") return [45, 212, 191, 28];
  return [103, 232, 249, 30];
}

function sourceQualityGapLineColor(feature: PickedSourceQualityGapFeature): [number, number, number, number] {
  const tier = feature.properties.tier;
  if (tier === "critical_gap") return [251, 113, 133, 170];
  if (tier === "support_gap") return [253, 186, 116, 150];
  if (tier === "coned_foundation") return [253, 224, 71, 96];
  if (tier === "mixed_foundation") return [190, 242, 100, 94];
  if (tier === "measured_detail") return [94, 234, 212, 108];
  return [125, 249, 255, 118];
}

function sourceQualityGapLineWidth(feature: PickedSourceQualityGapFeature): number {
  if (feature.properties.tier === "critical_gap") return 1.4;
  if (feature.properties.tier === "support_gap") return 1.2;
  return 0.75;
}

function sourceSeamTargetsForAudit(
  audit: SourceSeamAudit | null | undefined,
  terrain: PaleoTerrainConfig | null,
  activeWaterLevel: number,
  profile: SceneProfileConfig,
): SourceSeamRenderTarget[] {
  if (!audit) return EMPTY_SEAM_TARGET_ARRAY;

  const zMeters = terrain ? terrainZ(terrain, activeWaterLevel, profile, Z_BANDS.sourceSeam) : 0;
  return audit.topTransitions.flatMap((transition, transitionIndex) =>
    transition.targets.map((target, targetIndex) => ({
      position: [target.lon, target.lat, zMeters] as [number, number, number],
      categories: transition.categories,
      edgePixelCount: transition.edgePixelCount,
      edgePixelsInCluster: target.edgePixelsInCluster,
      importance: transition.importance,
      localHeight: target.localHeight,
      priorityScore: transition.priorityScore,
      recommendedView: transition.recommendedView,
      verticalOverlap: transition.verticalOverlap,
      transitionIndex,
      targetIndex,
    })),
  );
}

function sourceSeamTargetFillColor(target: SourceSeamRenderTarget): [number, number, number, number] {
  if (target.localHeight?.level === "severe") return [251, 113, 133, 232];
  if (target.localHeight?.level === "suspicious") return [251, 146, 60, 220];
  if (target.localHeight?.level === "calm") return [45, 212, 191, 208];
  if (target.localHeight?.level === "no_edges") return [125, 211, 252, 188];
  if (target.verticalOverlap.level === "offset_warning") return [251, 113, 133, 230];
  if (target.verticalOverlap.level === "mixed_warning") return [251, 146, 60, 218];
  if (target.verticalOverlap.level === "low") return [45, 212, 191, 206];
  if (target.verticalOverlap.level === "unknown") return [125, 211, 252, 190];
  if (target.priorityScore >= 5000) return [240, 171, 252, 224];
  if (target.priorityScore >= 1800) return [251, 146, 60, 210];
  return [125, 211, 252, 198];
}

function sourceSeamTargetLineColor(target: SourceSeamRenderTarget): [number, number, number, number] {
  if (target.localHeight?.level === "severe") return [255, 255, 255, 240];
  if (target.localHeight?.level === "suspicious") return [255, 237, 213, 226];
  if (target.localHeight?.level === "calm") return [204, 251, 241, 216];
  if (target.localHeight?.level === "no_edges") return [224, 242, 254, 204];
  if (target.verticalOverlap.level === "offset_warning") return [255, 255, 255, 238];
  if (target.verticalOverlap.level === "mixed_warning") return [255, 237, 213, 224];
  if (target.verticalOverlap.level === "low") return [204, 251, 241, 214];
  if (target.verticalOverlap.level === "unknown") return [224, 242, 254, 204];
  if (target.priorityScore >= 5000) return [255, 255, 255, 235];
  if (target.priorityScore >= 1800) return [255, 237, 213, 220];
  return [224, 242, 254, 205];
}

function sourceSeamTargetRadius(target: SourceSeamRenderTarget): number {
  return Math.max(4.5, Math.min(11, 4.5 + Math.sqrt(target.edgePixelsInCluster) / 10));
}

function meshMaxErrorForTerrain(
  terrain: PaleoTerrainConfig,
  detail: TerrainDetailLevel,
): number {
  const tier = terrainQualityTier(terrain);

  if (detail === "fast") {
    if (tier === "broad") return 6;
    if (tier === "bay_mosaic") return 2.2;
    return 1.4;
  }

  if (detail === "survey") {
    if (tier === "broad") return 0.55;
    if (tier === "bay_mosaic") return 0.18;
    if (tier === "offshore_survey") return 0.22;
    return 0.12;
  }

  if (detail === "ultra") {
    if (tier === "broad") return 0.09;
    if (tier === "bay_mosaic") return 0.025;
    if (tier === "offshore_survey") return 0.03;
    return 0.012;
  }

  if (tier === "broad") return 1.8;
  if (tier === "bay_mosaic") return 0.42;
  return 0.32;
}

function terrainTileConfigForRender(
  terrain: PaleoTerrainConfig,
  detail: TerrainDetailLevel,
): TerrainTileConfig | null {
  if (detail !== "ultra") return null;
  const tileset = TERRAIN_TILESETS[terrain.sourceId];
  if (!tileset) return null;
  return {
    ...tileset,
    extent: terrain.bounds,
  };
}

function textureForTerrain(terrain: PaleoTerrainConfig, mode: TerrainTextureMode, tileConfig?: TerrainTileConfig | null): string {
  const textures = tileConfig?.textures ?? terrain.textures;
  const fallback = tileConfig?.textures.shadedRelief ?? terrain.texture;
  if (mode === "color") return textures?.depthColor ?? fallback;
  if (mode === "bottom") return terrain.textures?.seafloorCharacter ?? terrain.textures?.surveySonarHybrid ?? textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? textures?.shadedRelief ?? fallback;
  if (mode === "hybrid") return terrain.textures?.surveySonarHybrid ?? textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? textures?.shadedRelief ?? fallback;
  if (mode === "sonar") return terrain.textures?.sonarBackscatter ?? textures?.shadedRelief ?? fallback;
  if (mode === "source") return terrain.textures?.sourceConfidence ?? textures?.surveyComposite ?? textures?.shadedRelief ?? fallback;
  if (mode === "survey") return textures?.surveyComposite ?? terrain.textures?.sonarBackscatter ?? textures?.shadedRelief ?? fallback;
  return textures?.shadedRelief ?? fallback;
}

function elevationDecoderForTerrain(
  terrain: PaleoTerrainConfig,
  profile: SceneProfileConfig,
  zLiftMeters = 0,
): PaleoTerrainConfig["elevationDecoder"] {
  return {
    rScaler: terrain.elevationDecoder.rScaler * profile.verticalScale,
    gScaler: terrain.elevationDecoder.gScaler * profile.verticalScale,
    bScaler: terrain.elevationDecoder.bScaler * profile.verticalScale,
    offset: (terrain.elevationDecoder.offset * profile.verticalScale) + zLiftMeters,
  };
}

function terrainZ(terrain: PaleoTerrainConfig, elevationMeters: number, profile: SceneProfileConfig, zOffsetMeters = 0): number {
  return (elevationMeters * terrain.verticalExaggeration * profile.verticalScale) + zOffsetMeters;
}

// One flat quad spanning every visible terrain footprint (plus padding) at the
// active waterline Z. Drawn after the terrain with depth testing on, the depth
// buffer alone clips it: exposed land wrote nearer depths, so the plane only
// survives where open water should be.
function waterSurfacePolygon(
  terrains: PaleoTerrainConfig[],
  zMeters: number,
): [number, number, number][] | null {
  if (!terrains.length) return null;
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const item of terrains) {
    west = Math.min(west, item.bounds[0]);
    south = Math.min(south, item.bounds[1]);
    east = Math.max(east, item.bounds[2]);
    north = Math.max(north, item.bounds[3]);
  }
  west -= WATER_SURFACE_PAD_DEGREES;
  south -= WATER_SURFACE_PAD_DEGREES;
  east += WATER_SURFACE_PAD_DEGREES;
  north += WATER_SURFACE_PAD_DEGREES;
  return [
    [west, south, zMeters],
    [east, south, zMeters],
    [east, north, zMeters],
    [west, north, zMeters],
  ];
}

function elevatedBaySourceFeature(
  feature: BaySourceFootprintFeature,
  terrain: PaleoTerrainConfig | null,
  activeWaterLevel: number,
  profile: SceneProfileConfig,
): BaySourceFootprintFeature {
  const zMeters = terrain ? terrainZ(terrain, activeWaterLevel, profile, Z_BANDS.sourceFootprint) : 0;
  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: addZToCoordinates(feature.geometry.coordinates, zMeters),
    },
  };
}

// The ~5,280 source-quality gap cells are flat 2D grid quads. They render as a
// PolygonLayer (not GeoJsonLayer) so deck.gl skips GeoJSON feature-type
// separation, and the constant cell elevation is applied per-vertex inside the
// layer's getPolygon accessor (gated by updateTriggers) rather than by
// deep-cloning the whole FeatureCollection up front.
const EMPTY_GAP_ARRAY: SourceQualityGapFeature[] = [];
const EMPTY_SEAM_TARGET_ARRAY: SourceSeamRenderTarget[] = [];

// Once the overlay has been shown, keep its tessellated geometry resident and
// toggle layer `visible` instead of swapping `data` in and out. Re-toggles then
// cost nothing (deck.gl retains the GPU geometry); only the first reveal pays a
// tessellation. Load is not penalized - data stays empty until the first open.
let gapsEverShown = false;
let seamsEverShown = false;

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

  const zOffset = zOffsetOverride ?? (feature.properties.line_role === "waterline_probe" ? Z_BANDS.probeContour : Z_BANDS.coastline);
  const zMeters = terrainZ(terrain, feature.properties.elevation_m, profile, zOffset);
  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: addZToCoordinates(feature.geometry.coordinates, zMeters),
    },
  };
}

function drapedRiverFeature(
  feature: PaleoRiverFeature,
  terrain: PaleoTerrainConfig | null,
  profile: SceneProfileConfig,
): PaleoRiverFeature {
  if (!terrain) return feature;
  const coordinates = feature.geometry.coordinates.map((vertex) => {
    const [lon, lat, elevationMeters = 0] = vertex;
    return [lon, lat, terrainZ(terrain, elevationMeters, profile, Z_BANDS.riverChannel)];
  });
  return { ...feature, geometry: { ...feature.geometry, coordinates } };
}

function riverColor(feature: { properties: PaleoRiverProperties }): [number, number, number, number] {
  // Brighter, more opaque for higher-order trunk channels.
  const order = feature.properties.order;
  const alpha = Math.min(235, 120 + order * 24);
  return [86, 188, 255, alpha];
}

function riverWidth(feature: { properties: PaleoRiverProperties }): number {
  return 0.8 + feature.properties.order * 0.9;
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
    const stride = Math.max(1, Math.ceil(positions.length / 40));
    const zMeters = terrainZ(terrain, feature.properties.elevation_m, profile, Z_BANDS.emergencePoint);

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
  waterlineLevel: number | null,
  profile: SceneProfileConfig,
): ContourLabel[] {
  if (!terrain) return [];

  const candidates: ContourLabel[] = [];

  for (const feature of features) {
    if (feature.properties.line_role !== "waterline_probe") continue;

    const elevationMeters = feature.properties.elevation_m;
    const offsetMeters = elevationMeters - activeWaterLevel;
    const distance = Math.abs(offsetMeters);
    // Only the single waterline contour is labelled "WL"; everything else is a
    // depth label, so the slope no longer shows a row of repeated "WL" tags.
    const isWaterline = waterlineLevel !== null && elevationMeters === waterlineLevel;
    const isNearestTenMeterStep = Math.abs(distance - 10) <= 2.5;
    if (!isWaterline && !isNearestTenMeterStep) continue;

    const positions = extractPositions(feature.geometry.coordinates);
    if (positions.length < 12) continue;

    const midpoint = positions[Math.floor(positions.length / 2)];
    if (typeof midpoint?.[0] !== "number" || typeof midpoint?.[1] !== "number") continue;

    const kind: ContourLabel["kind"] = isWaterline ? "waterline" : offsetMeters > 0 ? "exposed" : "submerged";
    candidates.push({
      position: [midpoint[0], midpoint[1], terrainZ(terrain, elevationMeters, profile, isWaterline ? Z_BANDS.contourLabel : Z_BANDS.contourLabel - 6)],
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

export function createPaleoCoastlineLayers(
  data: PaleoTimeSlice[],
  context: PaleoRenderContext,
  baySourceFootprints?: BaySourceFootprintCollection | null,
  paleoRivers?: PaleoRiverCollection | null,
  sourceQualityGaps?: SourceQualityGapCollection | null,
  sourceSeamAudit?: SourceSeamAudit | null,
) {
  const slice = selectedSlice(data, context);
  if (!slice) return [];

  const activeWaterLevel = context.paleoWaterLevelMeters ?? slice.seaLevelMeters;
  const visibleTerrainStack = terrainStackForRender(slice, context);
  const profile = sceneConfig(context.sceneProfile);
  const terrain = context.terrainSourceMode === "best"
    ? bestAvailableTerrainForSlice(slice) ?? visibleTerrainStack[0] ?? primaryTerrainForSlice(slice)
    : visibleTerrainStack[0] ?? primaryTerrainForSlice(slice);
  const rawProbeFeatures = probeFeaturesForWaterLevel(data, slice, activeWaterLevel);
  const waterlineLevel = activeWaterlineLevel(rawProbeFeatures, activeWaterLevel);
  const activeProbeFeatures = waterlineLevel === null
    ? []
    : rawProbeFeatures.filter(
        (feature) =>
          feature.properties.line_role === "waterline_probe" &&
          feature.properties.elevation_m === waterlineLevel,
      );
  const emergencePoints = emergencePointsForWaterLevel(rawProbeFeatures, terrain, activeWaterLevel, profile);
  const contourLabels = contourLabelsForWaterLevel(rawProbeFeatures, terrain, activeWaterLevel, waterlineLevel, profile);
  const terrainFootprints = context.showTerrainFootprints ? terrainFootprintsForSlice(slice, activeWaterLevel, profile) : [];
  const baySourceFeatures = context.showBaySourceFootprints && baySourceFootprints
    ? baySourceFootprints.features.map((feature) => elevatedBaySourceFeature(feature, terrain, activeWaterLevel, profile))
    : [];
  const riverFeatures = context.showRivers && paleoRivers
    ? paleoRivers.features.map((feature) => drapedRiverFeature(feature, terrain, profile))
    : [];
  if (context.showSourceQualityGaps) gapsEverShown = true;
  if (context.showSourceSeams) seamsEverShown = true;
  const gapData = gapsEverShown && sourceQualityGaps ? sourceQualityGaps.features : EMPTY_GAP_ARRAY;
  const gapZMeters = terrain ? terrainZ(terrain, activeWaterLevel, profile, Z_BANDS.sourceQualityGap) : 0;
  const gapZSignature = `${terrain?.sourceId ?? ""}|${activeWaterLevel}|${context.sceneProfile}`;
  const seamTargets = seamsEverShown
    ? sourceSeamTargetsForAudit(sourceSeamAudit, terrain, activeWaterLevel, profile)
    : EMPTY_SEAM_TARGET_ARRAY;
  const features = [
    ...slice.coastline.features,
    ...activeProbeFeatures,
    ...(context.showPaleoUncertainty ? slice.uncertainty.features : []),
  ].map((feature) => elevatedFeature(feature, terrain, undefined, profile));
  // The glow must sit at the EXACT same Z as the probe line in `features`
  // (Z_BANDS.probeContour) so it reads as a halo concentric with that one line.
  // Annotations render with depthCompare "always", so a differing Z would not
  // occlude anything but WOULD shift the perspective projection - which is what
  // made the glow drift off into a second parallel whitish line in tilted views.
  const shorelineGlowFeatures = activeProbeFeatures.map((feature) => elevatedFeature(feature, terrain, undefined, profile));
  // Near the active shoreline keep every contour; further out keep only the 10 m
  // majors so distant rings thin out instead of stacking into a dense band. The
  // waterline level itself is excluded - it is the glowing shoreline, not a ring.
  const depthContourFeatures = rawProbeFeatures
    .filter((feature) => {
      if (waterlineLevel !== null && feature.properties.elevation_m === waterlineLevel) return false;
      const offset = Math.abs(feature.properties.elevation_m - activeWaterLevel);
      return offset <= 8 || Math.abs(feature.properties.elevation_m % 10) < 0.1;
    })
    .map((feature) => elevatedFeature(feature, terrain, undefined, profile));

  const terrainLayers = visibleTerrainStack.map((terrain) => {
    const zLiftMeters = terrainVisualLiftMeters(terrain);
    const tileConfig = terrainTileConfigForRender(terrain, context.terrainDetail);
    return new TerrainLayer({
      id: `paleo-terrain-${terrain.sourceId}`,
      elevationData: tileConfig?.elevationData ?? terrain.elevationData,
      texture: textureForTerrain(terrain, context.terrainTextureMode, tileConfig),
      ...(tileConfig
        ? {
            extent: tileConfig.extent,
            maxZoom: tileConfig.maxZoom,
            minZoom: tileConfig.minZoom,
            maxCacheSize: 72,
            maxRequests: 12,
            tileSize: tileConfig.tileSize,
          }
        : {
            bounds: terrain.bounds,
          }),
      elevationDecoder: elevationDecoderForTerrain(terrain, profile, zLiftMeters),
      meshMaxError: meshMaxErrorForTerrain(terrain, context.terrainDetail),
      opacity: terrainLayerOpacity(terrain, context),
      wireframe: false,
      material: terrainMaterial(terrain, profile, context.terrainTextureMode),
      parameters: terrainDepthBiasParameters(terrain),
      _subLayerProps: {
        mesh: {
          type: SmoothTerrainMeshLayer,
          extensions: [terrainRevealExtension],
          flatShading: false,
          terrainSmoothHeights: context.terrainSurfaceSmoothing === "smooth",
          terrainRevealBandMeters: terrainRevealBandMeters(terrain),
          terrainRevealDepthFogStrength: terrainDepthFogStrength(terrain) * profile.waterDepthFogStrength,
          terrainRevealEnabled: true,
          terrainRevealReliefStrength: terrainRevealReliefStrengthForRender(terrain, context, profile),
          terrainRevealStrength: terrainRevealStrength(terrain) * profile.revealStrengthScale,
          terrainRevealSubmergedStrength: terrainSubmergedStrength(terrain) * profile.submergedStrengthScale,
          terrainRevealWaterLevelZ: terrainZ(terrain, activeWaterLevel, profile, zLiftMeters),
        },
      },
    });
  });

  // The plane sits at the same display Z the reveal shader uses as its
  // waterline (elevation x exaggeration x scene scale + the terrain's visual
  // lift), so the translucent surface and the shader's exposed/submerged
  // transition agree on where the water is.
  const waterSurfaceZ = terrain
    ? terrainZ(terrain, activeWaterLevel, profile, terrainVisualLiftMeters(terrain) + WATER_SURFACE_Z_NUDGE_METERS)
    : 0;
  const waterSurfaceData = context.showWaterSurface
    ? [waterSurfacePolygon(visibleTerrainStack, waterSurfaceZ)].filter(
        (polygon): polygon is [number, number, number][] => polygon !== null,
      )
    : [];

  const waterSurfaceLayer = new PolygonLayer<[number, number, number][]>({
    id: "paleo-water-surface",
    data: waterSurfaceData,
    visible: context.showWaterSurface,
    pickable: false,
    filled: true,
    stroked: false,
    getPolygon: (polygon) => polygon,
    getFillColor: [24, 116, 168, scaleAlpha(52, profile.submergedStrengthScale)],
    // Depth test on (clipped by exposed land), depth write off (never occludes
    // the annotation layers drawn after it).
    parameters: { depthWriteEnabled: false },
  });

  const terrainFootprintFillLayer = new PolygonLayer<TerrainFootprint>({
    id: "paleo-terrain-footprints-fill",
    data: terrainFootprints,
    pickable: true,
    filled: true,
    stroked: true,
    getPolygon: (item) => item.polygon,
    getFillColor: (item) => terrainFootprintColor(item.category, 10),
    getLineColor: (item) => terrainFootprintColor(item.category, 220),
    getLineWidth: 3,
    lineWidthUnits: "pixels",
    parameters: ANNOTATION_PARAMETERS,
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
    parameters: ANNOTATION_PARAMETERS,
  });

  const baySourceFootprintLayer = new GeoJsonLayer<BaySourceFootprintProperties>({
    id: "paleo-bay-source-footprints",
    data: {
      type: "FeatureCollection",
      features: baySourceFeatures,
    } as never,
    pickable: true,
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1.6,
    getFillColor: baySourceFillColor,
    getLineColor: baySourceLineColor,
    getLineWidth: baySourceLineWidth,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 92],
    parameters: ANNOTATION_PARAMETERS,
  });

  const sourceQualityGapLayer = new PolygonLayer<SourceQualityGapFeature>({
    id: "paleo-source-quality-gaps",
    data: gapData,
    visible: context.showSourceQualityGaps,
    pickable: true,
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 0.6,
    getPolygon: (feature) =>
      (feature.geometry.coordinates as number[][][]).map((ring) =>
        ring.map((position) => [position[0], position[1], gapZMeters] as [number, number, number])),
    getFillColor: sourceQualityGapFillColor,
    getLineColor: sourceQualityGapLineColor,
    getLineWidth: sourceQualityGapLineWidth,
    updateTriggers: { getPolygon: gapZSignature },
    autoHighlight: true,
    highlightColor: [255, 255, 255, 86],
    parameters: ANNOTATION_PARAMETERS,
  });

  const sourceSeamTargetLayer = new ScatterplotLayer<SourceSeamRenderTarget>({
    id: "paleo-source-seam-targets",
    data: seamTargets,
    visible: context.showSourceSeams,
    pickable: true,
    stroked: true,
    filled: true,
    radiusUnits: "pixels",
    getPosition: (item) => item.position,
    getRadius: sourceSeamTargetRadius,
    getFillColor: sourceSeamTargetFillColor,
    getLineColor: sourceSeamTargetLineColor,
    getLineWidth: 1.25,
    lineWidthUnits: "pixels",
    autoHighlight: true,
    highlightColor: [255, 255, 255, 112],
    parameters: ANNOTATION_PARAMETERS,
  });

  const depthContourLayer = new GeoJsonLayer<PaleoCoastlineProperties>({
    id: "paleo-depth-contours",
    data: {
      type: "FeatureCollection",
      features: depthContourFeatures,
    } as never,
    pickable: true,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 0.5,
    getLineColor: (feature) => depthContourColor(feature, activeWaterLevel, profile),
    getLineWidth: (feature) => depthContourWidth(feature, profile),
    autoHighlight: true,
    highlightColor: [255, 255, 255, 120],
    parameters: ANNOTATION_PARAMETERS,
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
    parameters: ANNOTATION_PARAMETERS,
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
    parameters: ANNOTATION_PARAMETERS,
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
    parameters: ANNOTATION_PARAMETERS,
  });

  const emergenceLayer = new ScatterplotLayer<EmergencePoint>({
    id: "paleo-emergence-glints",
    data: emergencePoints,
    pickable: false,
    stroked: true,
    filled: true,
    radiusUnits: "meters",
    radiusMinPixels: 1.4,
    radiusMaxPixels: 3.5,
    getPosition: (item) => item.position,
    getRadius: (item) => (90 + (15 - item.offsetMeters) * 7) * profile.emergenceRadiusScale,
    getFillColor: (item) => {
      const alpha = scaleAlpha(90 + (15 - item.offsetMeters) * 5, profile.emergenceAlphaScale);
      return [255, 232, 92, alpha];
    },
    getLineColor: [255, 255, 255, scaleAlpha(120, profile.emergenceAlphaScale)],
    getLineWidth: 0.6,
    lineWidthUnits: "pixels",
    parameters: ANNOTATION_PARAMETERS,
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
    parameters: ANNOTATION_PARAMETERS,
  });

  const riverLayer = new GeoJsonLayer<PaleoRiverProperties>({
    id: "paleo-rivers",
    data: {
      type: "FeatureCollection",
      features: riverFeatures,
    } as never,
    pickable: true,
    stroked: true,
    filled: false,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 0.8,
    getLineColor: riverColor,
    getLineWidth: riverWidth,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 160],
    parameters: ANNOTATION_PARAMETERS,
  });

  const placeLabels = context.showPlaceLabels
    ? PALEO_PLACE_LABELS.filter(
        (label) => context.currentYearsBP >= label.minYearsBP && context.currentYearsBP <= label.maxYearsBP,
      )
    : [];

  const placeLabelLayer = new TextLayer<PaleoPlaceLabel>({
    id: "paleo-place-labels",
    data: placeLabels,
    pickable: false,
    getPosition: (label) => {
      const z = terrain ? terrainZ(terrain, label.elevationM, profile, Z_BANDS.sourceLabel) : 0;
      return [label.longitude, label.latitude, z];
    },
    getText: (label) => label.text,
    getSize: 13,
    getColor: [255, 236, 178, 240],
    getTextAnchor: "middle",
    getAlignmentBaseline: "center",
    getAngle: 0,
    sizeUnits: "pixels",
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    fontWeight: 700,
    outlineWidth: 2,
    outlineColor: [2, 8, 23, 235],
    background: true,
    getBackgroundColor: [2, 8, 23, 150],
    backgroundPadding: [4, 2],
    parameters: ANNOTATION_PARAMETERS,
  });

  return [
    ...terrainLayers,
    waterSurfaceLayer,
    riverLayer,
    terrainFootprintFillLayer,
    terrainFootprintLabelLayer,
    baySourceFootprintLayer,
    sourceQualityGapLayer,
    sourceSeamTargetLayer,
    depthContourLayer,
    contourLabelLayer,
    shorelineGlowOuterLayer,
    shorelineGlowInnerLayer,
    coastlineLayer,
    emergenceLayer,
    placeLabelLayer,
  ];
}

export function getPaleoTooltip(object: unknown) {
  if (!object || typeof object !== "object") return null;

  if ("sourceLabel" in object && "heightRangeMeters" in object) {
    const terrain = object as TerrainFootprint;
    return {
      text: `${terrain.sourceLabel}\n${terrainTierLabel(terrain.qualityTier)}\n${terrain.heightRangeMeters[0]} to ${terrain.heightRangeMeters[1]} m\n${terrain.note}`,
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

  if ("categories" in object && "recommendedView" in object && "priorityScore" in object) {
    const target = object as SourceSeamRenderTarget;
    const pair = target.verticalOverlap.strongestPair;
    const localLine = target.localHeight?.medianAbsStepMeters != null && target.localHeight.p95AbsStepMeters != null
      ? `${target.localHeight.label}: median ${target.localHeight.medianAbsStepMeters} m, 95% ${target.localHeight.p95AbsStepMeters} m`
      : target.localHeight?.label ?? "Local height step not measured";
    const verticalLine = pair
      ? `${target.verticalOverlap.label}: median ${pair.medianMeters} m, 95% abs ${pair.p95AbsMeters} m`
      : target.verticalOverlap.label;
    return {
      text: `Source seam target\n${target.categories.join(" / ")}\n${localLine}\nOverlap audit: ${verticalLine}\nScore ${Math.round(target.priorityScore).toLocaleString()}, cluster ${target.edgePixelsInCluster.toLocaleString()} edge pixels\nRecommended view: ${target.recommendedView}`,
      style: {
        backgroundColor: "rgba(4, 20, 28, 0.94)",
        color: "#fce7f3",
        fontSize: "13px",
        padding: "8px 10px",
        borderRadius: "6px",
        border: "1px solid rgba(240, 171, 252, 0.45)",
      },
    };
  }

  const maybeRiver = object as Partial<{ properties: PaleoRiverProperties }>;
  if (maybeRiver.properties && "flow" in maybeRiver.properties && "order" in maybeRiver.properties) {
    const props = maybeRiver.properties;
    return {
      text: `Paleo-drainage channel\norder ${props.order} of 5\nbed ${props.min_elevation_m} to ${props.max_elevation_m} m`,
      style: {
        backgroundColor: "rgba(4, 20, 28, 0.92)",
        color: "#bfe8ff",
        fontSize: "13px",
        padding: "8px 10px",
        borderRadius: "6px",
        border: "1px solid rgba(103, 232, 249, 0.35)",
      },
    };
  }

  if (!("properties" in object)) return null;

  const maybeSourceQualityGap = object as Partial<PickedSourceQualityGapFeature>;
  if (maybeSourceQualityGap.properties?.cellId && "gapPriorityScore" in maybeSourceQualityGap.properties) {
    const props = maybeSourceQualityGap.properties;
    return {
      text: `${props.tierLabel}\n${props.dominantCategory} dominates ${props.dominantPercent}%\nBroad ${props.broadFallbackPercent}% / CoNED ${props.conedFoundationPercent}% / detail ${props.measuredDetailPercent}%\nGap score ${props.gapPriorityScore}: ${props.nextAction}`,
      style: {
        backgroundColor: "rgba(4, 20, 28, 0.94)",
        color: "#fff7ed",
        fontSize: "13px",
        padding: "8px 10px",
        borderRadius: "6px",
        border: "1px solid rgba(251, 191, 36, 0.42)",
      },
    };
  }

  const maybeBaySource = object as Partial<PickedBaySourceFeature>;
  if (maybeBaySource.properties?.survey && "sensor_type" in maybeBaySource.properties) {
    const props = maybeBaySource.properties;
    const year = props.year == null ? "unknown year" : String(props.year);
    const interpolation = props.interpolation.toLowerCase() === "yes" ? "interpolated" : "direct";
    return {
      text: `${props.source_section}: ${props.survey}\n${props.agency}, ${year}\n${props.sensor_type}, ${props.resolution}, ${props.datum}\n${interpolation} source area`,
      style: {
        backgroundColor: "rgba(4, 20, 28, 0.94)",
        color: "#d8fff4",
        fontSize: "13px",
        padding: "8px 10px",
        borderRadius: "6px",
        border: "1px solid rgba(110, 255, 190, 0.35)",
      },
    };
  }

  const feature = object as PickedPaleoFeature;
  const props = feature.properties;
  if (props.line_role === "waterline_probe") {
    // Plain-English explanation for the depth rings and waterline trace, so a
    // hover tells you what the contour means without needing an on-screen legend.
    return {
      text: `Paleo shoreline contour\nLand sits at ${props.elevation_m} m elevation here\nWhere the coast would be at this sea level`,
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
  return {
    text: `${props.label}\n${lineRoleLabel(props.line_role)}\nSea level ${props.elevation_m} m\n${props.source_label}`,
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
