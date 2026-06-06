export type PaleoTimeSliceId = "present" | "5k_years_ago" | "10k_years_ago" | "20k_years_ago";
export type TerrainDetailLevel = "fast" | "detailed" | "survey";
export type TerrainTextureMode = "bottom" | "hybrid" | "survey" | "sonar" | "relief" | "color";
export type SceneProfile = "study" | "relief" | "emergence";

export interface PaleoTerrainConfig {
  sourceId: string;
  sourceLabel: string;
  elevationData: string;
  texture: string;
  textures?: {
    depthColor: string;
    shadedRelief: string;
    surveyComposite?: string;
    surveySonarHybrid?: string;
    sonarBackscatter?: string;
    seafloorCharacter?: string;
  };
  bounds: [number, number, number, number];
  heightRangeMeters: [number, number];
  verticalExaggeration: number;
  elevationDecoder: {
    rScaler: number;
    gScaler: number;
    bScaler: number;
    offset: number;
  };
  note: string;
}

export interface PaleoCoastlineProperties {
  slice_id: PaleoTimeSliceId | "waterline_probe";
  label: string;
  line_role: "estimate" | "lower_sea_level_bound" | "higher_sea_level_bound" | "waterline_probe";
  elevation_m: number;
  years_before_present: number;
  source_id: string;
  source_label: string;
}

export interface PaleoCoastlineFeature {
  type: "Feature";
  properties: PaleoCoastlineProperties;
  geometry: {
    type: string;
    coordinates: unknown;
  };
}

export interface PaleoFeatureCollection {
  type: "FeatureCollection";
  features: PaleoCoastlineFeature[];
}

export interface BaySourceFootprintProperties {
  source_section: string;
  section_id: string;
  agency: string;
  survey: string;
  year: number | null;
  resolution: string;
  datum: string;
  interpolation: string;
  sensor_type: string;
  source_location: string;
  area_sq_m: number | null;
  quality_class: string;
  sciencebase_item_id: string;
  sciencebase_item_url: string;
}

export interface BaySourceFootprintFeature {
  type: "Feature";
  id?: string;
  properties: BaySourceFootprintProperties;
  geometry: {
    type: string;
    coordinates: unknown;
  };
}

export interface BaySourceFootprintCollection {
  type: "FeatureCollection";
  name?: string;
  features: BaySourceFootprintFeature[];
}

export interface PaleoTimeSlice {
  id: PaleoTimeSliceId;
  label: string;
  yearsBeforePresent: number;
  seaLevelMeters: number;
  uncertaintyMeters: number;
  summary: string;
  sourceModel: string;
  datumNote: string;
  uncertaintyNote: string;
  terrain?: PaleoTerrainConfig;
  terrains?: PaleoTerrainConfig[];
  waterlineProbe?: {
    levelsMeters: number[];
    intervalMeters: number;
    description: string;
    contours: PaleoFeatureCollection;
  };
  coastline: PaleoFeatureCollection;
  uncertainty: PaleoFeatureCollection;
}

export interface PaleoTimeSliceManifestItem extends PaleoTimeSlice {
  sliceDataUrl: string;
}

export interface PaleoManifest {
  generatedAt: string;
  studyBounds: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  slices: PaleoTimeSliceManifestItem[];
  waterlineProbe: {
    levelsMeters: number[];
    intervalMeters: number;
    description: string;
    levelDataUrls: Record<string, string>;
  };
  waterlineProbeUrl: string;
  metadataUrl: string;
  legacyAllInOneUrl: string;
}

export type PaleoWaterlineProbe = NonNullable<PaleoTimeSlice["waterlineProbe"]>;
export type PaleoWaterlineProbeIndex = PaleoManifest["waterlineProbe"];

export interface PaleoRenderContext {
  paleoTimeSliceId: PaleoTimeSliceId;
  showPaleoUncertainty: boolean;
  showTerrainFootprints: boolean;
  showBaySourceFootprints: boolean;
  paleoWaterLevelMeters: number | null;
  terrainDetail: TerrainDetailLevel;
  terrainTextureMode: TerrainTextureMode;
  sceneProfile: SceneProfile;
}
