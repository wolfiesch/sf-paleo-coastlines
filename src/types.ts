export type PaleoTimeSliceId = "present" | "5k_years_ago" | "10k_years_ago" | "20k_years_ago";

export interface PaleoTerrainConfig {
  sourceId: string;
  sourceLabel: string;
  elevationData: string;
  texture: string;
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

export interface PaleoRenderContext {
  paleoTimeSliceId: PaleoTimeSliceId;
  showPaleoUncertainty: boolean;
  paleoWaterLevelMeters: number | null;
}
