import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { Map } from "react-map-gl/maplibre";
import type { MapViewState } from "deck.gl";
import { FlyToInterpolator } from "deck.gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { PaleoCoastlineControls } from "./components/PaleoCoastlineControls";
import { createPaleoCoastlineLayers, getPaleoTooltip } from "./layers/paleoCoastlineLayer";
import { DARK_MAP_STYLE } from "./lib/mapStyles";
import { MAX_YEARS_BP, seaLevelForYearsBP } from "./lib/seaLevelCurve";
import { TOUR_STEPS } from "./lib/tourScript";
import type {
  BaySourceFootprintCollection,
  PaleoManifest,
  PaleoFeatureCollection,
  PaleoRiverCollection,
  PaleoTimeSlice,
  PaleoTimeSliceId,
  PaleoTimeSliceManifestItem,
  PaleoWaterlineProbeIndex,
  SceneProfile,
  SeaLevelStats,
  SourceSeamAudit,
  SourceQualityGapCollection,
  SourceQualityGapSummary,
  TerrainDetailLevel,
  PaleoTerrainConfig,
  TerrainSourceMode,
  TerrainSurfaceSmoothing,
  TerrainTextureMode,
} from "./types";

const START_VIEW: MapViewState = {
  longitude: -122.88,
  latitude: 37.78,
  zoom: 8.55,
  pitch: 58,
  bearing: -32,
};

const VIEW_PRESETS = [
  {
    id: "gate",
    label: "Gate",
    viewState: {
      longitude: -122.61,
      latitude: 37.78,
      zoom: 10.05,
      pitch: 64,
      bearing: -39,
    },
  },
  {
    id: "farallones",
    label: "Farallones",
    viewState: {
      longitude: -123.13,
      latitude: 37.69,
      zoom: 8.75,
      pitch: 62,
      bearing: -34,
    },
  },
  {
    id: "shelf",
    label: "Shelf",
    viewState: {
      longitude: -123.38,
      latitude: 37.77,
      zoom: 8.35,
      pitch: 66,
      bearing: -43,
    },
  },
  {
    id: "northwest-gap",
    label: "NW Gap",
    viewState: {
      longitude: -123.35,
      latitude: 38.05,
      zoom: 8.65,
      pitch: 62,
      bearing: -34,
    },
  },
] satisfies { id: string; label: string; viewState: MapViewState }[];

const BAY_SOURCE_FOOTPRINTS_URL = "/data/paleo-coastlines/usgs_sf_bay_source_footprints.geojson";
const RIVERS_URL = "/data/paleo-coastlines/paleo_rivers.geojson";
const SEALEVEL_STATS_URL = "/data/paleo-coastlines/sealevel_stats.json";
const SOURCE_QUALITY_GAPS_URL = "/data/paleo-coastlines/source_quality_gaps.geojson";
const SOURCE_QUALITY_GAPS_SUMMARY_URL = "/data/paleo-coastlines/source_quality_gaps_summary.json";
const SOURCE_SEAM_AUDIT_URL = "/data/paleo-coastlines/source_seam_audit_targets.json";

const TIME_SLICE_IDS: PaleoTimeSliceId[] = ["present", "5k_years_ago", "10k_years_ago", "20k_years_ago"];
const TERRAIN_DETAIL_LEVELS: TerrainDetailLevel[] = ["fast", "detailed", "survey", "ultra"];
const TERRAIN_SURFACE_SMOOTHING_MODES: TerrainSurfaceSmoothing[] = ["smooth", "sharp"];
const TERRAIN_TEXTURE_MODES: TerrainTextureMode[] = ["bottom", "hybrid", "survey", "source", "sonar", "relief", "color"];
const TERRAIN_SOURCE_MODES: TerrainSourceMode[] = ["best", "single", "stack"];
const SCENE_PROFILES: SceneProfile[] = ["study", "relief", "emergence"];

interface UrlInitialState {
  captureMode: boolean;
  showUi: boolean;
  viewState: MapViewState;
  activeSliceId: PaleoTimeSliceId;
  showUncertainty: boolean;
  showTerrainFootprints: boolean;
  showBaySourceFootprints: boolean;
  showRivers: boolean;
  showPlaceLabels: boolean;
  showSourceQualityGaps: boolean;
  showSourceSeams: boolean;
  timeMode: boolean;
  yearsBeforePresent: number;
  waterLevelMeters: number | null;
  terrainDetail: TerrainDetailLevel;
  terrainSurfaceSmoothing: TerrainSurfaceSmoothing;
  terrainTextureMode: TerrainTextureMode;
  terrainSourceMode: TerrainSourceMode;
  selectedTerrainSourceId: string | null;
  sceneProfile: SceneProfile;
}

function queryBoolean(params: URLSearchParams, name: string, fallback: boolean): boolean {
  const value = params.get(name);
  if (value == null) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function queryNumber(params: URLSearchParams, name: string): number | null {
  const value = params.get(name);
  if (value == null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function queryEnum<T extends string>(params: URLSearchParams, name: string, allowed: readonly T[], fallback: T): T {
  const value = params.get(name);
  return allowed.includes(value as T) ? value as T : fallback;
}

function initialViewStateFromParams(params: URLSearchParams): MapViewState {
  const preset = VIEW_PRESETS.find((item) => item.id === params.get("view"));
  const base = preset?.viewState ?? START_VIEW;
  return {
    ...base,
    longitude: queryNumber(params, "longitude") ?? queryNumber(params, "lon") ?? base.longitude,
    latitude: queryNumber(params, "latitude") ?? queryNumber(params, "lat") ?? base.latitude,
    zoom: queryNumber(params, "zoom") ?? base.zoom,
    pitch: queryNumber(params, "pitch") ?? base.pitch,
    bearing: queryNumber(params, "bearing") ?? base.bearing,
  };
}

function readUrlInitialState(): UrlInitialState {
  const params = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
  const yearsBeforePresent = queryNumber(params, "years") ?? MAX_YEARS_BP;
  const waterLevelMeters = queryNumber(params, "water") ?? queryNumber(params, "waterLevel");

  return {
    captureMode: queryBoolean(params, "capture", false),
    showUi: queryBoolean(params, "ui", true) && !queryBoolean(params, "hideUi", false),
    viewState: initialViewStateFromParams(params),
    activeSliceId: queryEnum(params, "slice", TIME_SLICE_IDS, "20k_years_ago"),
    showUncertainty: queryBoolean(params, "uncertainty", true),
    showTerrainFootprints: queryBoolean(params, "coverage", false),
    showBaySourceFootprints: queryBoolean(params, "baySources", false),
    showRivers: queryBoolean(params, "rivers", true),
    showPlaceLabels: queryBoolean(params, "labels", true),
    showSourceQualityGaps: queryBoolean(params, "gaps", false),
    showSourceSeams: queryBoolean(params, "seams", false),
    timeMode: waterLevelMeters == null,
    yearsBeforePresent,
    waterLevelMeters: waterLevelMeters ?? Math.round(seaLevelForYearsBP(yearsBeforePresent)),
    terrainDetail: queryEnum(params, "detail", TERRAIN_DETAIL_LEVELS, "ultra"),
    terrainSurfaceSmoothing: queryEnum(params, "smoothing", TERRAIN_SURFACE_SMOOTHING_MODES, "smooth"),
    terrainTextureMode: queryEnum(params, "texture", TERRAIN_TEXTURE_MODES, "survey"),
    terrainSourceMode: queryEnum(params, "sourceMode", TERRAIN_SOURCE_MODES, "best"),
    selectedTerrainSourceId: params.get("sourceId"),
    sceneProfile: queryEnum(params, "scene", SCENE_PROFILES, "emergence"),
  };
}

function exposedAreaForMeters(stats: SeaLevelStats | null, meters: number): number | null {
  if (!stats || !stats.levels.length) return null;
  const sorted = [...stats.levels].sort((a, b) => a.meters - b.meters);
  if (meters <= sorted[0].meters) return sorted[0].exposed_vs_present_km2;
  if (meters >= sorted[sorted.length - 1].meters) return sorted[sorted.length - 1].exposed_vs_present_km2;
  for (let i = 1; i < sorted.length; i += 1) {
    if (meters <= sorted[i].meters) {
      const a = sorted[i - 1];
      const b = sorted[i];
      const t = (meters - a.meters) / (b.meters - a.meters);
      return a.exposed_vs_present_km2 + t * (b.exposed_vs_present_km2 - a.exposed_vs_present_km2);
    }
  }
  return sorted[sorted.length - 1].exposed_vs_present_km2;
}

function nearestProbeLevel(level: number, levels: number[]): number | null {
  if (!levels.length) return null;

  return levels.reduce((nearest, candidate) => (
    Math.abs(candidate - level) < Math.abs(nearest - level) ? candidate : nearest
  ), levels[0]);
}

function probeLevelKey(level: number): string {
  return (Math.round(level * 10) / 10).toFixed(1);
}

function nearbyProbeLevels(activeLevel: number | null, levels: number[]): number[] {
  if (activeLevel == null || !levels.length) return [];
  const nearest = nearestProbeLevel(activeLevel, levels);
  if (nearest == null) return [];

  return levels.filter((level) => Math.abs(level - nearest) <= 30);
}

function terrainSourcesForSlice(slice: PaleoTimeSlice | null): PaleoTerrainConfig[] {
  if (!slice) return [];
  return slice.terrains?.length ? slice.terrains : slice.terrain ? [slice.terrain] : [];
}

function defaultTerrainSourceId(sources: PaleoTerrainConfig[]): string | null {
  return sources.find((source) => source.sourceId.includes("best_available"))?.sourceId
    ?? sources.find((source) => source.qualityTier === "bay_mosaic")?.sourceId
    ?? sources[0]?.sourceId
    ?? null;
}

function App() {
  const initialState = useMemo(() => readUrlInitialState(), []);
  const [viewState, setViewState] = useState<MapViewState>(initialState.viewState);
  const [sliceCatalog, setSliceCatalog] = useState<PaleoTimeSliceManifestItem[]>([]);
  const [loadedSlices, setLoadedSlices] = useState<Partial<Record<PaleoTimeSliceId, PaleoTimeSlice>>>({});
  const [waterlineProbeIndex, setWaterlineProbeIndex] = useState<PaleoWaterlineProbeIndex | null>(null);
  const [loadedProbeLevels, setLoadedProbeLevels] = useState<Record<string, PaleoFeatureCollection>>({});
  const [loading, setLoading] = useState(true);
  const [loadingSliceId, setLoadingSliceId] = useState<PaleoTimeSliceId | null>(null);
  const [loadingProbeLevel, setLoadingProbeLevel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeSliceId, setActiveSliceId] = useState<PaleoTimeSliceId>(initialState.activeSliceId);
  const [showUncertainty, setShowUncertainty] = useState(initialState.showUncertainty);
  const [waterLevelMeters, setWaterLevelMeters] = useState<number | null>(initialState.waterLevelMeters);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showTerrainFootprints, setShowTerrainFootprints] = useState(initialState.showTerrainFootprints);
  const [showBaySourceFootprints, setShowBaySourceFootprints] = useState(initialState.showBaySourceFootprints);
  const [baySourceFootprints, setBaySourceFootprints] = useState<BaySourceFootprintCollection | null>(null);
  const [loadingBaySourceFootprints, setLoadingBaySourceFootprints] = useState(false);
  const [showRivers, setShowRivers] = useState(initialState.showRivers);
  const [paleoRivers, setPaleoRivers] = useState<PaleoRiverCollection | null>(null);
  const [loadingRivers, setLoadingRivers] = useState(false);
  const [timeMode, setTimeMode] = useState(initialState.timeMode);
  const [yearsBeforePresent, setYearsBeforePresent] = useState(initialState.yearsBeforePresent);
  const [showPlaceLabels, setShowPlaceLabels] = useState(initialState.showPlaceLabels);
  const [seaLevelStats, setSeaLevelStats] = useState<SeaLevelStats | null>(null);
  const [showSourceQualityGaps, setShowSourceQualityGaps] = useState(initialState.showSourceQualityGaps);
  const [sourceQualityGaps, setSourceQualityGaps] = useState<SourceQualityGapCollection | null>(null);
  const [sourceQualityGapSummary, setSourceQualityGapSummary] = useState<SourceQualityGapSummary | null>(null);
  const [loadingSourceQualityGaps, setLoadingSourceQualityGaps] = useState(false);
  const [showSourceSeams, setShowSourceSeams] = useState(initialState.showSourceSeams);
  const [sourceSeamAudit, setSourceSeamAudit] = useState<SourceSeamAudit | null>(null);
  const [loadingSourceSeams, setLoadingSourceSeams] = useState(false);
  const [terrainDetail, setTerrainDetail] = useState<TerrainDetailLevel>(initialState.terrainDetail);
  const [terrainSurfaceSmoothing, setTerrainSurfaceSmoothing] = useState<TerrainSurfaceSmoothing>(initialState.terrainSurfaceSmoothing);
  const [terrainTextureMode, setTerrainTextureMode] = useState<TerrainTextureMode>(initialState.terrainTextureMode);
  const [terrainSourceMode, setTerrainSourceMode] = useState<TerrainSourceMode>(initialState.terrainSourceMode);
  const [selectedTerrainSourceId, setSelectedTerrainSourceId] = useState<string | null>(initialState.selectedTerrainSourceId);
  const [sceneProfile, setSceneProfile] = useState<SceneProfile>(initialState.sceneProfile);
  const [isTouring, setIsTouring] = useState(false);
  const [tourCaption, setTourCaption] = useState<string | null>(null);
  // Monotonic generation token. Each runTour() claims a new id; a stop, a new
  // run, or unmount bumps it so any in-flight loop fails closed on its next check.
  const tourRunId = useRef(0);

  // Invalidate any in-flight tour loop if the component unmounts mid-tour.
  useEffect(() => () => {
    tourRunId.current += 1;
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadPaleoManifest() {
      try {
        const response = await fetch("/data/paleo-coastlines/paleo_manifest.json");
        if (!response.ok) {
          throw new Error(`Failed to load paleo manifest: ${response.status}`);
        }
        const payload = await response.json() as PaleoManifest;
        if (!cancelled) {
          setSliceCatalog(payload.slices);
          setWaterlineProbeIndex(payload.waterlineProbe);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load paleo data.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadPaleoManifest();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadStats() {
      try {
        const response = await fetch(SEALEVEL_STATS_URL);
        if (!response.ok) return;
        const payload = await response.json() as SeaLevelStats;
        if (!cancelled) setSeaLevelStats(payload);
      } catch {
        // Stats are a non-critical enhancement; ignore load failures.
      }
    }
    void loadStats();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const slice = sliceCatalog.find((item) => item.id === activeSliceId);
    if (!slice) return;
    if (loadedSlices[activeSliceId]) return;

    const sliceToLoad = slice;

    let cancelled = false;

    async function loadActiveSlice() {
      setLoadingSliceId(activeSliceId);
      try {
        const response = await fetch(sliceToLoad.sliceDataUrl);
        if (!response.ok) {
          throw new Error(`Failed to load ${sliceToLoad.label}: ${response.status}`);
        }
        const payload = await response.json() as PaleoTimeSlice;
        if (!cancelled) {
          setLoadedSlices((current) => ({ ...current, [activeSliceId]: payload }));
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : `Failed to load ${sliceToLoad.label}.`);
        }
      } finally {
        if (!cancelled) {
          setLoadingSliceId(null);
        }
      }
    }

    void loadActiveSlice();

    return () => {
      cancelled = true;
    };
  }, [activeSliceId, loadedSlices, sliceCatalog]);

  useEffect(() => {
    if (!isPlaying) return;

    if (timeMode) {
      const timer = window.setInterval(() => {
        setYearsBeforePresent((current) => {
          const next = current <= 0 ? MAX_YEARS_BP : current - 200;
          setWaterLevelMeters(Math.round(seaLevelForYearsBP(next)));
          return next;
        });
      }, 120);
      return () => window.clearInterval(timer);
    }

    const timer = window.setInterval(() => {
      setWaterLevelMeters((current) => {
        const level = current ?? 2;
        return level <= -120 ? 2 : level - 1;
      });
    }, 220);
    return () => window.clearInterval(timer);
  }, [isPlaying, timeMode]);

  const activeProbeLevel = useMemo(() => nearestProbeLevel(
    waterLevelMeters ?? loadedSlices[activeSliceId]?.seaLevelMeters ?? sliceCatalog.find((item) => item.id === activeSliceId)?.seaLevelMeters ?? -120,
    waterlineProbeIndex?.levelsMeters ?? [],
  ), [activeSliceId, loadedSlices, sliceCatalog, waterLevelMeters, waterlineProbeIndex]);

  const activeProbeLevels = useMemo(() => nearbyProbeLevels(
    activeProbeLevel,
    waterlineProbeIndex?.levelsMeters ?? [],
  ), [activeProbeLevel, waterlineProbeIndex]);

  useEffect(() => {
    if (!waterlineProbeIndex || !activeProbeLevels.length) return;
    const probeIndex = waterlineProbeIndex;
    const missingLevels = activeProbeLevels.filter((level) => {
      const levelKey = probeLevelKey(level);
      return probeIndex.levelDataUrls[levelKey] && !loadedProbeLevels[levelKey];
    });
    if (!missingLevels.length) return;

    let cancelled = false;

    async function loadProbeLevels() {
      const activeKey = activeProbeLevel == null ? probeLevelKey(missingLevels[0]) : probeLevelKey(activeProbeLevel);
      setLoadingProbeLevel(activeKey);
      try {
        const entries = await Promise.all(missingLevels.map(async (level) => {
          const levelKey = probeLevelKey(level);
          const response = await fetch(probeIndex.levelDataUrls[levelKey]);
          if (!response.ok) {
            throw new Error(`Failed to load waterline probe ${levelKey} m: ${response.status}`);
          }
          const payload = await response.json() as PaleoFeatureCollection;
          return [levelKey, payload] as const;
        }));
        if (!cancelled) {
          setLoadedProbeLevels((current) => ({
            ...current,
            ...Object.fromEntries(entries),
          }));
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load nearby waterline probes.");
        }
      } finally {
        if (!cancelled) {
          setLoadingProbeLevel(null);
        }
      }
    }

    void loadProbeLevels();

    return () => {
      cancelled = true;
    };
  }, [activeProbeLevel, activeProbeLevels, loadedProbeLevels, waterlineProbeIndex]);

  useEffect(() => {
    if (!showBaySourceFootprints || baySourceFootprints) return;

    let cancelled = false;

    async function loadBaySourceFootprints() {
      setLoadingBaySourceFootprints(true);
      try {
        const response = await fetch(BAY_SOURCE_FOOTPRINTS_URL);
        if (!response.ok) {
          throw new Error(`Failed to load Bay source footprints: ${response.status}`);
        }
        const payload = await response.json() as BaySourceFootprintCollection;
        if (!cancelled) {
          setBaySourceFootprints(payload);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load Bay source footprints.");
        }
      } finally {
        if (!cancelled) {
          setLoadingBaySourceFootprints(false);
        }
      }
    }

    void loadBaySourceFootprints();

    return () => {
      cancelled = true;
    };
  }, [baySourceFootprints, showBaySourceFootprints]);

  useEffect(() => {
    if (!showRivers || paleoRivers) return;

    let cancelled = false;

    async function loadRivers() {
      setLoadingRivers(true);
      try {
        const response = await fetch(RIVERS_URL);
        if (!response.ok) {
          throw new Error(`Failed to load paleo rivers: ${response.status}`);
        }
        const payload = await response.json() as PaleoRiverCollection;
        if (!cancelled) {
          setPaleoRivers(payload);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load paleo rivers.");
        }
      } finally {
        if (!cancelled) {
          setLoadingRivers(false);
        }
      }
    }

    void loadRivers();

    return () => {
      cancelled = true;
    };
  }, [paleoRivers, showRivers]);

  useEffect(() => {
    if (!showSourceQualityGaps || (sourceQualityGaps && sourceQualityGapSummary)) return;

    let cancelled = false;

    async function loadSourceQualityGaps() {
      setLoadingSourceQualityGaps(true);
      try {
        const [gapsResponse, summaryResponse] = await Promise.all([
          sourceQualityGaps ? Promise.resolve(null) : fetch(SOURCE_QUALITY_GAPS_URL),
          sourceQualityGapSummary ? Promise.resolve(null) : fetch(SOURCE_QUALITY_GAPS_SUMMARY_URL),
        ]);
        if (gapsResponse && !gapsResponse.ok) {
          throw new Error(`Failed to load source quality gaps: ${gapsResponse.status}`);
        }
        if (summaryResponse && !summaryResponse.ok) {
          throw new Error(`Failed to load source quality summary: ${summaryResponse.status}`);
        }
        const payload = gapsResponse ? await gapsResponse.json() as SourceQualityGapCollection : null;
        const summary = summaryResponse ? await summaryResponse.json() as SourceQualityGapSummary : null;
        if (!cancelled) {
          if (payload) setSourceQualityGaps(payload);
          if (summary) setSourceQualityGapSummary(summary);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load source quality gaps.");
        }
      } finally {
        if (!cancelled) {
          setLoadingSourceQualityGaps(false);
        }
      }
    }

    void loadSourceQualityGaps();

    return () => {
      cancelled = true;
    };
  }, [showSourceQualityGaps, sourceQualityGaps, sourceQualityGapSummary]);

  useEffect(() => {
    if (!showSourceSeams || sourceSeamAudit) return;

    let cancelled = false;

    async function loadSourceSeams() {
      setLoadingSourceSeams(true);
      try {
        const response = await fetch(SOURCE_SEAM_AUDIT_URL);
        if (!response.ok) {
          throw new Error(`Failed to load source seam audit: ${response.status}`);
        }
        const payload = await response.json() as SourceSeamAudit;
        if (!cancelled) {
          setSourceSeamAudit(payload);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load source seam audit.");
        }
      } finally {
        if (!cancelled) {
          setLoadingSourceSeams(false);
        }
      }
    }

    void loadSourceSeams();

    return () => {
      cancelled = true;
    };
  }, [showSourceSeams, sourceSeamAudit]);

  const activeSlice = useMemo(
    () => {
      const slice = loadedSlices[activeSliceId]
        ?? sliceCatalog.find((item) => item.id === activeSliceId)
        ?? sliceCatalog[0]
        ?? null;
      if (!slice || !waterlineProbeIndex) return slice;
      const levelKey = activeProbeLevel == null ? "" : probeLevelKey(activeProbeLevel);
      const probeFeatures = activeProbeLevels.flatMap((level) => {
        const loadedLevel = loadedProbeLevels[probeLevelKey(level)];
        return loadedLevel?.features ?? [];
      });
      return {
        ...slice,
        waterlineProbe: {
          levelsMeters: waterlineProbeIndex.levelsMeters,
          intervalMeters: waterlineProbeIndex.intervalMeters,
          description: waterlineProbeIndex.description,
          contours: {
            type: "FeatureCollection",
            features: probeFeatures.length ? probeFeatures : loadedProbeLevels[levelKey]?.features ?? [],
          } satisfies PaleoFeatureCollection,
        },
      };
    },
    [activeProbeLevel, activeProbeLevels, activeSliceId, loadedProbeLevels, loadedSlices, sliceCatalog, waterlineProbeIndex],
  );

  const renderSlices = useMemo(() => (activeSlice ? [activeSlice] : []), [activeSlice]);
  const terrainSources = useMemo(() => terrainSourcesForSlice(activeSlice), [activeSlice]);
  const isLoadingData = loading || loadingSliceId === activeSliceId;
  const probeLoading = loadingProbeLevel === (activeProbeLevel == null ? null : probeLevelKey(activeProbeLevel));
  const captureReady = Boolean(
    activeSlice
    && !error
    && !isLoadingData
    && !probeLoading
    && (!showRivers || paleoRivers)
    && (!showBaySourceFootprints || baySourceFootprints)
    && (!showSourceQualityGaps || (sourceQualityGaps && sourceQualityGapSummary))
    && (!showSourceSeams || sourceSeamAudit),
  );

  const effectiveTerrainSourceId = useMemo(() => (
    terrainSources.some((source) => source.sourceId === selectedTerrainSourceId)
      ? selectedTerrainSourceId
      : defaultTerrainSourceId(terrainSources)
  ), [selectedTerrainSourceId, terrainSources]);

  const layers = useMemo(() => createPaleoCoastlineLayers(renderSlices, {
    paleoTimeSliceId: activeSliceId,
    showPaleoUncertainty: showUncertainty,
    showTerrainFootprints,
    showBaySourceFootprints,
    showRivers,
    showSourceQualityGaps,
    showSourceSeams,
    paleoWaterLevelMeters: waterLevelMeters,
    terrainDetail,
    terrainSurfaceSmoothing,
    terrainTextureMode,
    terrainSourceMode,
    selectedTerrainSourceId: effectiveTerrainSourceId,
    sceneProfile,
    showPlaceLabels,
    currentYearsBP: yearsBeforePresent,
  }, baySourceFootprints, paleoRivers, sourceQualityGaps, sourceSeamAudit), [activeSliceId, baySourceFootprints, effectiveTerrainSourceId, paleoRivers, renderSlices, sceneProfile, showBaySourceFootprints, showPlaceLabels, showRivers, showSourceQualityGaps, showSourceSeams, showTerrainFootprints, showUncertainty, sourceQualityGaps, sourceSeamAudit, terrainDetail, terrainSourceMode, terrainSurfaceSmoothing, terrainTextureMode, waterLevelMeters, yearsBeforePresent]);

  const handleSliceChange = useCallback((id: PaleoTimeSliceId) => {
    setIsPlaying(false);
    setActiveSliceId(id);
    const nextSlice = sliceCatalog.find((slice) => slice.id === id);
    if (nextSlice) {
      setWaterLevelMeters(nextSlice.seaLevelMeters);
    }
  }, [sliceCatalog]);

  const handleYearsChange = useCallback((years: number) => {
    setIsPlaying(false);
    setYearsBeforePresent(years);
    setWaterLevelMeters(Math.round(seaLevelForYearsBP(years)));
  }, []);

  const handleTerrainSourceModeChange = useCallback((mode: TerrainSourceMode) => {
    setTerrainSourceMode(mode);
    if (mode === "single" && !selectedTerrainSourceId) {
      setSelectedTerrainSourceId(defaultTerrainSourceId(terrainSources));
    }
  }, [selectedTerrainSourceId, terrainSources]);

  const handleTerrainSourceChange = useCallback((sourceId: string) => {
    setSelectedTerrainSourceId(sourceId);
    setTerrainSourceMode("single");
  }, []);

  const cycleTerrainSource = useCallback((direction: -1 | 1) => {
    if (!terrainSources.length) return;
    const currentId = effectiveTerrainSourceId ?? defaultTerrainSourceId(terrainSources);
    const currentIndex = Math.max(0, terrainSources.findIndex((source) => source.sourceId === currentId));
    const nextIndex = (currentIndex + direction + terrainSources.length) % terrainSources.length;
    setSelectedTerrainSourceId(terrainSources[nextIndex].sourceId);
    setTerrainSourceMode("single");
  }, [effectiveTerrainSourceId, terrainSources]);

  const handleToggleTimeMode = useCallback(() => {
    setTimeMode((mode) => {
      const next = !mode;
      if (next) setWaterLevelMeters(Math.round(seaLevelForYearsBP(yearsBeforePresent)));
      return next;
    });
  }, [yearsBeforePresent]);

  const stopTour = useCallback(() => {
    tourRunId.current += 1; // invalidate any in-flight tour loop
    setIsTouring(false);
    setTourCaption(null);
  }, []);

  const runTour = useCallback(async () => {
    const myRun = (tourRunId.current += 1); // claim a generation; supersedes any prior loop
    setIsPlaying(false);
    setTimeMode(true);
    setIsTouring(true);

    const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

    for (const step of TOUR_STEPS) {
      if (tourRunId.current !== myRun) return; // a stop, a newer run, or unmount superseded us
      setTourCaption(step.caption);
      setYearsBeforePresent(step.yearsBP);
      setWaterLevelMeters(Math.round(seaLevelForYearsBP(step.yearsBP)));
      setViewState({
        ...step.viewState,
        transitionDuration: step.flyMs,
        transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }),
      } as MapViewState);
      await sleep(step.flyMs + step.holdMs);
    }

    if (tourRunId.current !== myRun) return; // superseded during the final hold
    // Clear transition props so subsequent user drags are not re-animated.
    setViewState((current) => ({ ...current, transitionDuration: 0, transitionInterpolator: undefined } as MapViewState));
    setIsTouring(false);
    setTourCaption(null);
  }, []);

  const handleToggleTour = useCallback(() => {
    if (isTouring) {
      stopTour();
    } else {
      void runTour();
    }
  }, [isTouring, runTour, stopTour]);

  return (
    <main
      className="relative h-screen w-screen overflow-hidden bg-gray-950 text-white"
      data-capture-mode={initialState.captureMode ? "true" : "false"}
      data-capture-ui={initialState.showUi ? "true" : "false"}
      data-capture-ready={captureReady ? "true" : "false"}
      data-capture-view={`${viewState.longitude},${viewState.latitude},${viewState.zoom},${viewState.pitch},${viewState.bearing}`}
    >
      <DeckGL
        layers={layers}
        viewState={viewState}
        controller={!initialState.captureMode}
        onViewStateChange={({ viewState: nextViewState, interactionState }) => {
          if (interactionState?.isDragging && isTouring) {
            tourRunId.current += 1; // cancel the in-flight tour loop
            setIsTouring(false);
            setTourCaption(null);
          }
          setViewState(nextViewState as MapViewState);
        }}
        getTooltip={({ object }) => getPaleoTooltip(object)}
      >
        <Map mapStyle={DARK_MAP_STYLE} reuseMaps />
      </DeckGL>

      {initialState.showUi ? (
        <>
          <header className="pointer-events-none absolute inset-x-0 top-0 z-20 border-b border-white/10 bg-gray-950/88 px-4 py-3 backdrop-blur-md">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-base font-semibold tracking-tight text-white">SF Paleo Coastlines</h1>
                <p className="text-xs text-gray-400">3D topobathymetry, old shorelines, and sea-level scrubbing</p>
              </div>
              <div className="rounded-md border border-cyan-400/20 bg-cyan-400/10 px-3 py-1.5 text-xs font-semibold text-cyan-100">
                Standalone research view
              </div>
            </div>
          </header>

          <div className="pointer-events-none absolute left-4 top-20 z-30 w-[22rem] max-w-[calc(100vw-2rem)]">
            <PaleoCoastlineControls
              slices={sliceCatalog}
              activeSliceId={activeSliceId}
              showUncertainty={showUncertainty}
              waterLevelMeters={waterLevelMeters}
              isPlaying={isPlaying}
              terrainDetail={terrainDetail}
              terrainSurfaceSmoothing={terrainSurfaceSmoothing}
              terrainTextureMode={terrainTextureMode}
              terrainSourceMode={terrainSourceMode}
              selectedTerrainSourceId={effectiveTerrainSourceId}
              terrainSources={terrainSources}
              sceneProfile={sceneProfile}
              showTerrainFootprints={showTerrainFootprints}
              showBaySourceFootprints={showBaySourceFootprints}
              showSourceQualityGaps={showSourceQualityGaps}
              showSourceSeams={showSourceSeams}
              sourceQualityGapSummary={sourceQualityGapSummary}
              viewPresets={VIEW_PRESETS}
              onSliceChange={handleSliceChange}
              onToggleUncertainty={() => setShowUncertainty((shown) => !shown)}
              onToggleTerrainFootprints={() => setShowTerrainFootprints((shown) => !shown)}
              onToggleBaySourceFootprints={() => setShowBaySourceFootprints((shown) => !shown)}
              onToggleSourceQualityGaps={() => setShowSourceQualityGaps((shown) => !shown)}
              onToggleSourceSeams={() => setShowSourceSeams((shown) => !shown)}
              showRivers={showRivers}
              onToggleRivers={() => setShowRivers((shown) => !shown)}
              timeMode={timeMode}
              yearsBeforePresent={yearsBeforePresent}
              showPlaceLabels={showPlaceLabels}
              exposedAreaKm2={exposedAreaForMeters(seaLevelStats, waterLevelMeters ?? -120)}
              onYearsChange={handleYearsChange}
              onToggleTimeMode={handleToggleTimeMode}
              isTouring={isTouring}
              onToggleTour={handleToggleTour}
              onTogglePlaceLabels={() => setShowPlaceLabels((shown) => !shown)}
              onWaterLevelChange={(level) => {
                setIsPlaying(false);
                setWaterLevelMeters(level);
              }}
              onTogglePlayback={() => setIsPlaying((playing) => !playing)}
              onResetWaterLevel={() => {
                setIsPlaying(false);
                if (timeMode) {
                  // In time mode, reset to the default lowstand year and derive its
                  // sea level so the year readout and the meters stay consistent.
                  setYearsBeforePresent(MAX_YEARS_BP);
                  setWaterLevelMeters(Math.round(seaLevelForYearsBP(MAX_YEARS_BP)));
                } else {
                  setWaterLevelMeters(2);
                }
              }}
              onTerrainDetailChange={setTerrainDetail}
              onTerrainSurfaceSmoothingChange={setTerrainSurfaceSmoothing}
              onTerrainTextureModeChange={setTerrainTextureMode}
              onTerrainSourceModeChange={handleTerrainSourceModeChange}
              onTerrainSourceChange={handleTerrainSourceChange}
              onPreviousTerrainSource={() => cycleTerrainSource(-1)}
              onNextTerrainSource={() => cycleTerrainSource(1)}
              onSceneProfileChange={setSceneProfile}
              onViewPreset={(nextViewState) => setViewState(nextViewState)}
            />
          </div>

          <aside className="pointer-events-none absolute bottom-4 right-4 z-20 w-[20rem] max-w-[calc(100vw-2rem)] rounded-lg border border-white/10 bg-gray-950/88 p-3 text-xs leading-4 text-gray-400 shadow-2xl backdrop-blur-md">
            {isLoadingData ? <p>Loading terrain and coastline data...</p> : null}
            {!isLoadingData && probeLoading ? <p>Loading waterline probe...</p> : null}
            {!isLoadingData && loadingBaySourceFootprints ? <p>Loading Bay source footprints...</p> : null}
            {!isLoadingData && loadingRivers ? <p>Loading paleo rivers...</p> : null}
            {!isLoadingData && loadingSourceQualityGaps ? <p>Loading source quality gaps...</p> : null}
            {!isLoadingData && loadingSourceSeams ? <p>Loading source seam audit...</p> : null}
            {error ? <p className="text-red-200">{error}</p> : null}
            {!isLoadingData && !error && activeSlice ? (
              <div className="space-y-2">
                <div className="font-mono text-[11px] uppercase tracking-wide text-cyan-200">
                  {activeSlice.label} / {waterLevelMeters ?? activeSlice.seaLevelMeters} m waterline
                </div>
                <p>This standalone app contains only the paleo coastline simulator. Civic layers such as police, 311, permits, and live feeds stay in CityScope.</p>
              </div>
            ) : null}
          </aside>
          {tourCaption ? (
            <div className="pointer-events-none absolute inset-x-0 bottom-24 z-30 flex justify-center px-4">
              <div className="max-w-2xl rounded-lg border border-cyan-400/25 bg-gray-950/85 px-5 py-3 text-center text-sm leading-5 text-cyan-50 shadow-2xl backdrop-blur-md">
                {tourCaption}
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </main>
  );
}

export default App;
