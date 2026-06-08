import { ChevronLeft, ChevronRight, Clapperboard, Clock, Database, Layers3, MapPin, Mountain, Pause, Play, RotateCcw, TriangleAlert, Waves } from "lucide-react";
import type { MapViewState } from "deck.gl";
import type { PaleoTerrainConfig, PaleoTimeSlice, PaleoTimeSliceId, SceneProfile, SourceQualityGapSummary, TerrainDetailLevel, TerrainSourceMode, TerrainSurfaceSmoothing, TerrainTextureMode } from "../types";
import { MAX_YEARS_BP, MIN_YEARS_BP } from "../lib/seaLevelCurve";
import { Legend, Section, SegmentedControl, TogglePill, sectionTitleClass, valueClass, type LegendItem } from "./PaleoControlPrimitives";

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70";

interface ViewPreset {
  id: string;
  label: string;
  viewState: MapViewState;
}

interface PaleoCoastlineControlsProps {
  slices: PaleoTimeSlice[];
  activeSliceId: PaleoTimeSliceId;
  showUncertainty: boolean;
  showTerrainFootprints: boolean;
  showBaySourceFootprints: boolean;
  showSourceQualityGaps: boolean;
  sourceQualityGapSummary: SourceQualityGapSummary | null;
  showRivers: boolean;
  waterLevelMeters: number | null;
  isPlaying: boolean;
  timeMode: boolean;
  yearsBeforePresent: number;
  showPlaceLabels: boolean;
  exposedAreaKm2: number | null;
  terrainDetail: TerrainDetailLevel;
  terrainSurfaceSmoothing: TerrainSurfaceSmoothing;
  terrainTextureMode: TerrainTextureMode;
  terrainSourceMode: TerrainSourceMode;
  selectedTerrainSourceId: string | null;
  terrainSources: PaleoTerrainConfig[];
  sceneProfile: SceneProfile;
  viewPresets: ViewPreset[];
  onSliceChange: (id: PaleoTimeSliceId) => void;
  onToggleUncertainty: () => void;
  onToggleTerrainFootprints: () => void;
  onToggleBaySourceFootprints: () => void;
  onToggleSourceQualityGaps: () => void;
  onToggleRivers: () => void;
  onWaterLevelChange: (level: number) => void;
  onTogglePlayback: () => void;
  onResetWaterLevel: () => void;
  onYearsChange: (years: number) => void;
  onToggleTimeMode: () => void;
  isTouring: boolean;
  onToggleTour: () => void;
  onTogglePlaceLabels: () => void;
  onTerrainDetailChange: (level: TerrainDetailLevel) => void;
  onTerrainSurfaceSmoothingChange: (mode: TerrainSurfaceSmoothing) => void;
  onTerrainTextureModeChange: (mode: TerrainTextureMode) => void;
  onTerrainSourceModeChange: (mode: TerrainSourceMode) => void;
  onTerrainSourceChange: (sourceId: string) => void;
  onPreviousTerrainSource: () => void;
  onNextTerrainSource: () => void;
  onSceneProfileChange: (profile: SceneProfile) => void;
  onViewPreset: (viewState: MapViewState) => void;
}

const TERRAIN_DETAIL_OPTIONS: { id: TerrainDetailLevel; label: string; title: string }[] = [
  { id: "fast", label: "Fast", title: "Lower mesh density" },
  { id: "detailed", label: "Detailed", title: "Balanced mesh density" },
  { id: "survey", label: "Survey", title: "High mesh density for survey review" },
  { id: "ultra", label: "Ultra", title: "Close-up mesh density for smoother hills" },
];

const TERRAIN_SURFACE_SMOOTHING_OPTIONS: { id: TerrainSurfaceSmoothing; label: string; title: string }[] = [
  { id: "smooth", label: "Smooth", title: "Gently softens visual terrain heights for presentation close-ups" },
  { id: "sharp", label: "Sharp", title: "Keeps original mesh heights for stricter terrain inspection" },
];

const TERRAIN_TEXTURE_OPTIONS: { id: TerrainTextureMode; label: string; title: string }[] = [
  { id: "bottom", label: "Bottom", title: "Interpreted seafloor type where USGS character maps exist" },
  { id: "hybrid", label: "Hybrid", title: "Survey texture plus acoustic backscatter where sonar exists" },
  { id: "survey", label: "Survey", title: "Slope, roughness, ridge, and hollow detail blended with depth color" },
  { id: "source", label: "Source", title: "Source quality classes for the fused best-available terrain" },
  { id: "relief", label: "Relief", title: "Depth color plus DEM-derived light and shadow" },
  { id: "sonar", label: "Sonar", title: "Acoustic backscatter where available, relief elsewhere" },
  { id: "color", label: "Color", title: "Depth color without baked terrain shading" },
];

const SCENE_PROFILE_OPTIONS: { id: SceneProfile; label: string; title: string }[] = [
  { id: "study", label: "Study", title: "Lower contrast view for reading source layers and labels" },
  { id: "relief", label: "Relief", title: "Stronger height, light, and shadow for terrain shape" },
  { id: "emergence", label: "Emerge", title: "Clearer waterline and newly exposed terrain" },
];

const TERRAIN_SOURCE_MODE_OPTIONS: { id: TerrainSourceMode; label: string; title: string }[] = [
  { id: "best", label: "Best", title: "Render the clean fused best-available terrain surface" },
  { id: "single", label: "Source", title: "Render one selected source at a time" },
  { id: "stack", label: "Stack", title: "Render all terrain surfaces for debugging and comparison" },
];

// Hover titles double as the in-place explanation of what each color means, so
// the map can stay uncluttered without a permanent on-screen legend.
const WATERLINE_LEGEND: LegendItem[] = [
  { label: "Waterline", swatch: "bg-white", title: "The shoreline at the selected sea level" },
  { label: "Exposed", swatch: "bg-amber-300", title: "Land sitting above the current sea level" },
  { label: "Submerged", swatch: "bg-cyan-300", title: "Seafloor just below the current sea level" },
  { label: "Depth", swatch: "bg-sky-700", title: "Deeper water, shaded darker with depth" },
];

const COVERAGE_LEGEND: LegendItem[] = [
  { label: "NOAA BAG", swatch: "bg-cyan-300", title: "NOAA hydrographic survey patches (1-2 m)" },
  { label: "NOAA multibeam", swatch: "bg-blue-300", title: "NOAA/NCEI gridded multibeam survey patches" },
  { label: "NOAA OCM 1 m", swatch: "bg-teal-300", title: "NOAA 1 m Bay-floor mosaic" },
  { label: "USGS CoNED", swatch: "bg-emerald-400", title: "USGS 2 m land + seafloor topobathymetry" },
  { label: "USGS CSMP", swatch: "bg-amber-300", title: "USGS 2 m coastal seafloor mapping" },
  { label: "USGS offshore", swatch: "bg-violet-300", title: "Farallon escarpment / Rittenburg Bank multibeam" },
  { label: "USGS LiDAR", swatch: "bg-stone-100", title: "2023 USGS land LiDAR (high-res modern terrain)" },
  { label: "SF Bar", swatch: "bg-emerald-300", title: "Golden Gate / SF Bar detail tile" },
];

const BAY_SOURCE_LEGEND: LegendItem[] = [
  { label: "Direct 1 m", swatch: "bg-emerald-300", title: "Directly measured 1 m survey (highest quality)" },
  { label: "Interp.", swatch: "bg-violet-300", title: "Interpolated coverage where surveys had gaps" },
  { label: "Single beam", swatch: "bg-amber-300", title: "Single-beam sonar (sparser, often older)" },
  { label: "Multibeam", swatch: "bg-cyan-300", title: "Multibeam sonar (dense modern survey)" },
];

const GAP_LEGEND: LegendItem[] = [
  { label: "Broad gap", swatch: "bg-rose-400", title: "Relies on broad fallback data; needs new survey" },
  { label: "CoNED base", swatch: "bg-amber-300", title: "Backed by 2 m CoNED; solid but not survey-rich" },
  { label: "Survey detail", swatch: "bg-cyan-300", title: "Backed by measured local survey data" },
  { label: "Strong area", swatch: "bg-emerald-300", title: "Top-tier measured detail (quality benchmark)" },
];

const FALLBACK_SLICES: PaleoTimeSlice[] = [
  {
    id: "present",
    label: "Present",
    yearsBeforePresent: 0,
    seaLevelMeters: 0,
    uncertaintyMeters: 1,
    summary: "Modern shoreline contour around present mean sea level.",
    sourceModel: "NOAA CRM / USGS topobathymetry",
    datumNote: "Approximate relative sea-level contour.",
    uncertaintyNote: "Uncertainty bands show sea-level range only.",
    coastline: { type: "FeatureCollection", features: [] },
    uncertainty: { type: "FeatureCollection", features: [] },
  },
];

function compactLabel(label: string): string {
  return label.replace(" years ago", "");
}

function nearestProbeLevel(level: number): number {
  return Math.round(level / 5) * 5;
}

function waterlineStage(level: number): string {
  if (level >= -5) return "Near modern shoreline";
  if (level >= -35) return "Bay margins exposed";
  if (level >= -75) return "Valley and shelf emerging";
  if (level >= -105) return "Outer shelf emerging";
  return "Glacial lowstand range";
}

function yearLabel(yearsBP: number): string {
  if (yearsBP <= 0) return "Present day";
  if (yearsBP < 1000) return `${Math.round(yearsBP)} yr ago`;
  return `${(yearsBP / 1000).toFixed(1)}k yr ago`;
}

function terrainSummary(slice: PaleoTimeSlice): string | null {
  const terrains = slice.terrains?.length ? slice.terrains : slice.terrain ? [slice.terrain] : [];
  if (!terrains.length) return null;
  if (terrains.length === 1) return terrains[0].note;
  return `${terrains.length} terrain surfaces, drawn from broad support grids up to sharper local survey patches: NOAA CRM/CUDEM Bay-to-coast coverage, USGS CoNED San Francisco 2 m land-plus-seafloor topobathymetry, smaller high-density CoNED focus clips for the Gate, Farallon shelf, and south Bay edge, a derived best-available Golden Gate-to-Farallones fusion surface, NOAA OCM 1 m Area A Bay-floor mosaic, Central Bay source-survey tiles, NOAA BAG Golden Gate/Gulf of the Farallones/Farallon-region survey patches, NOAA/NCEI EX0907 offshore multibeam, USGS/CSMP 2 m coastal bathymetry blocks, Farallon Escarpment/Rittenburg Bank offshore multibeam patches, 2023 USGS San Francisco land LiDAR where local tiles are present, and DS684 Golden Gate detail.`;
}

function terrainSourceGroup(source: PaleoTerrainConfig): string {
  const id = source.sourceId;
  if (id.includes("best_available")) return "Best available";
  if (id.includes("crm") || id.includes("cudem")) return "Broad grids";
  if (id.includes("coned")) return "USGS CoNED";
  if (id.includes("noaa_ocm")) return "NOAA OCM";
  if (id.includes("noaa_nos")) return "NOAA BAG";
  if (id.includes("noaa_ncei")) return "NOAA multibeam";
  if (id.includes("csmp") || id.includes("ds684")) return "USGS/CSMP";
  if (id.includes("lidar")) return "LiDAR";
  if (id.includes("farallon") || id.includes("rittenburg")) return "Offshore surveys";
  return "Other";
}

function terrainSourceShortLabel(source: PaleoTerrainConfig): string {
  return source.sourceLabel
    .replace("NOAA NOS ", "")
    .replace("NOAA OCM ", "")
    .replace("USGS ", "")
    .replace("San Francisco", "SF")
    .replace("bathymetry", "bathy")
    .replace("topobathymetry", "topobathy");
}

function terrainSourceMeta(source: PaleoTerrainConfig): string {
  const resolution = source.resolutionMeters ? `${source.resolutionMeters} m` : "variable";
  const [low, high] = source.heightRangeMeters;
  return `${resolution}, ${low} to ${high} m`;
}

function percentLabel(value: number): string {
  return `${Math.round(value)}%`;
}

function compactSourceCategory(category: string): string {
  return category
    .replace(" fallback", "")
    .replace(" support", "")
    .replace(" survey", "")
    .replace("USGS ", "")
    .replace("NOAA ", "");
}

export function PaleoCoastlineControls({
  slices,
  activeSliceId,
  showUncertainty,
  showTerrainFootprints,
  showBaySourceFootprints,
  showSourceQualityGaps,
  sourceQualityGapSummary,
  showRivers,
  waterLevelMeters,
  isPlaying,
  timeMode,
  yearsBeforePresent,
  showPlaceLabels,
  exposedAreaKm2,
  terrainDetail,
  terrainSurfaceSmoothing,
  terrainTextureMode,
  terrainSourceMode,
  selectedTerrainSourceId,
  terrainSources,
  sceneProfile,
  viewPresets,
  onSliceChange,
  onToggleUncertainty,
  onToggleTerrainFootprints,
  onToggleBaySourceFootprints,
  onToggleSourceQualityGaps,
  onToggleRivers,
  onWaterLevelChange,
  onTogglePlayback,
  onResetWaterLevel,
  onYearsChange,
  onToggleTimeMode,
  isTouring,
  onToggleTour,
  onTogglePlaceLabels,
  onTerrainDetailChange,
  onTerrainSurfaceSmoothingChange,
  onTerrainTextureModeChange,
  onTerrainSourceModeChange,
  onTerrainSourceChange,
  onPreviousTerrainSource,
  onNextTerrainSource,
  onSceneProfileChange,
  onViewPreset,
}: PaleoCoastlineControlsProps) {
  const options = slices.length ? slices : FALLBACK_SLICES;
  const activeSlice = options.find((slice) => slice.id === activeSliceId) ?? options[0];
  const activeWaterLevel = waterLevelMeters ?? activeSlice.seaLevelMeters;
  const probeLevel = Math.max(-120, Math.min(0, nearestProbeLevel(activeWaterLevel)));
  const terrainStackSummary = terrainSummary(activeSlice);
  const activeSceneProfile = SCENE_PROFILE_OPTIONS.find((option) => option.id === sceneProfile);
  const activeTerrainSource = terrainSources.find((source) => source.sourceId === selectedTerrainSourceId)
    ?? terrainSources.find((source) => source.sourceId.includes("best_available"))
    ?? terrainSources[0]
    ?? null;
  const terrainSourceGroups = terrainSources.reduce<Record<string, PaleoTerrainConfig[]>>((groups, source) => {
    const group = terrainSourceGroup(source);
    groups[group] = [...(groups[group] ?? []), source];
    return groups;
  }, {});
  const terrainSourceGroupNames = Object.keys(terrainSourceGroups).sort((a, b) => {
    const order = ["Best available", "Broad grids", "USGS CoNED", "NOAA OCM", "NOAA BAG", "NOAA multibeam", "USGS/CSMP", "LiDAR", "Offshore surveys", "Other"];
    return order.indexOf(a) - order.indexOf(b);
  });

  const terrainSourceTrailing = terrainSourceMode === "best"
    ? "Best available"
    : terrainSourceMode === "stack"
      ? "All stacked"
      : activeTerrainSource ? terrainSourceShortLabel(activeTerrainSource) : "None";

  return (
    <section className="pointer-events-auto max-h-[calc(100vh-6rem)] w-full overflow-y-auto rounded-xl border border-cyan-400/15 bg-gray-950/92 p-4 shadow-2xl backdrop-blur-md">
      <div className="mb-4 flex items-start gap-2.5">
        <div className="mt-0.5 rounded-lg border border-cyan-400/25 bg-cyan-400/10 p-2 text-cyan-200">
          <Waves size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold leading-5 text-white">SF Paleo Coastline</h2>
          <p className="mt-0.5 text-xs leading-4 text-gray-400">{activeSlice.summary}</p>
        </div>
      </div>

      <button
        type="button"
        onClick={onToggleTour}
        className={`mb-1 flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-semibold transition-colors ${FOCUS_RING} ${
          isTouring
            ? "border-rose-300/40 bg-rose-300 text-gray-950"
            : "border-cyan-400/30 bg-cyan-400/10 text-cyan-100 hover:bg-cyan-300 hover:text-gray-950"
        }`}
        aria-pressed={isTouring}
      >
        <Clapperboard size={15} />
        {isTouring ? "Stop tour" : "Play guided tour"}
      </button>

      {/* Time / sea level - the primary interaction, given the most visual weight. */}
      <Section
        title={timeMode ? "Time" : "Depth"}
        icon={<Clock size={12} />}
        trailing={
          <button
            type="button"
            onClick={onToggleTimeMode}
            className={`rounded-md border border-cyan-400/25 bg-cyan-400/10 px-2 py-0.5 text-[11px] font-semibold text-cyan-100 transition-colors hover:bg-cyan-300 hover:text-gray-950 ${FOCUS_RING}`}
            aria-pressed={timeMode}
            title="Switch between years-before-present and raw water depth"
          >
            {timeMode ? "Years" : "Meters"}
          </button>
        }
      >
        <SegmentedControl
          options={options.map((slice) => ({
            id: slice.id,
            label: compactLabel(slice.label),
            title: `${slice.label} - ${slice.seaLevelMeters} m sea level`,
          }))}
          value={activeSlice.id}
          onChange={onSliceChange}
          columns={options.length}
          ariaLabel="Time period"
        />

        {timeMode ? (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-mono text-lg font-semibold leading-none text-white">{yearLabel(yearsBeforePresent)}</span>
              <span className={valueClass}>
                <span className="sr-only">Derived sea level </span>
                {activeWaterLevel} m
              </span>
            </div>
            <input
              type="range"
              min={MIN_YEARS_BP}
              max={MAX_YEARS_BP}
              step={100}
              value={yearsBeforePresent}
              onChange={(event) => onYearsChange(Number(event.currentTarget.value))}
              disabled={isTouring}
              className="w-full accent-cyan-300 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Years before present"
            />
            {exposedAreaKm2 != null && exposedAreaKm2 > 0 ? (
              <div className="text-xs text-gray-400">
                ~{Math.round(exposedAreaKm2).toLocaleString()} km² more land than today
              </div>
            ) : null}
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between gap-3">
              <span className={sectionTitleClass}>Waterline</span>
              <span className="font-mono text-lg font-semibold leading-none text-white">{activeWaterLevel} m</span>
            </div>
            <input
              type="range"
              min="-120"
              max="2"
              step="1"
              value={activeWaterLevel}
              onChange={(event) => onWaterLevelChange(Number(event.currentTarget.value))}
              className="w-full accent-cyan-300"
              aria-label="Water level in meters"
            />
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate text-xs text-gray-300">{waterlineStage(activeWaterLevel)}</div>
            <div className="font-mono text-[11px] leading-4 text-gray-500">contour band {probeLevel - 30} to {probeLevel + 30} m</div>
          </div>
          <div className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={onTogglePlayback}
              disabled={isTouring}
              className={`grid h-8 w-8 place-items-center rounded-md border border-cyan-300/30 bg-cyan-300/10 text-cyan-100 transition-colors hover:bg-cyan-300 hover:text-gray-950 ${FOCUS_RING} disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-cyan-300/10 disabled:hover:text-cyan-100`}
              aria-label={isPlaying ? "Pause waterline playback" : "Play waterline playback"}
              title={isPlaying ? "Pause" : "Play"}
            >
              {isPlaying ? <Pause size={15} /> : <Play size={15} />}
            </button>
            <button
              type="button"
              onClick={onResetWaterLevel}
              disabled={isTouring}
              className={`grid h-8 w-8 place-items-center rounded-md border border-white/10 bg-white/[0.04] text-gray-300 transition-colors hover:bg-white/[0.08] hover:text-white ${FOCUS_RING} disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-white/[0.04] disabled:hover:text-gray-300`}
              aria-label="Reset waterline to high water"
              title="Reset"
            >
              <RotateCcw size={14} />
            </button>
          </div>
        </div>

        <Legend items={WATERLINE_LEGEND} columns={2} />
      </Section>

      {/* Layers - the toggles a typical viewer reaches for, plus camera presets. */}
      <Section title="Layers" icon={<Layers3 size={12} />}>
        <div className="flex flex-wrap gap-1.5">
          <TogglePill
            active={showRivers}
            onClick={onToggleRivers}
            icon={<Waves size={13} />}
            label="Rivers"
            accent="sky"
            title="Show the last-glacial-lowstand paleo-drainage network"
          />
          <TogglePill
            active={showPlaceLabels}
            onClick={onTogglePlaceLabels}
            icon={<MapPin size={13} />}
            label="Labels"
            accent="amber"
            title="Show paleo-geography place labels"
          />
          <TogglePill
            active={showUncertainty}
            onClick={onToggleUncertainty}
            label="Uncertainty"
            title={`Show the +/- ${activeSlice.uncertaintyMeters} m sea-level uncertainty bands`}
          />
          <TogglePill
            active={showTerrainFootprints}
            onClick={onToggleTerrainFootprints}
            icon={<Layers3 size={13} />}
            label="Coverage"
            title="Show rendered high-detail terrain coverage"
          />
          <TogglePill
            active={showBaySourceFootprints}
            onClick={onToggleBaySourceFootprints}
            icon={<Database size={13} />}
            label="Bay sources"
            accent="emerald"
            title="Show source surveys used by the USGS 1 m Bay DEM"
          />
          <TogglePill
            active={showSourceQualityGaps}
            onClick={onToggleSourceQualityGaps}
            icon={<TriangleAlert size={13} />}
            label="Gaps"
            accent="amber"
            title="Show source-quality gap cells derived from the fused terrain provenance"
          />
        </div>

        {showTerrainFootprints ? <Legend items={COVERAGE_LEGEND} /> : null}
        {showBaySourceFootprints ? <Legend items={BAY_SOURCE_LEGEND} /> : null}
        {showSourceQualityGaps ? (
          <div className="space-y-2">
            <Legend items={GAP_LEGEND} />
            {sourceQualityGapSummary ? (
              <div className="rounded-lg border border-amber-300/15 bg-amber-300/[0.06] p-2.5">
                <div className="mb-2 grid grid-cols-3 gap-1 text-center">
                  <div>
                    <div className="font-mono text-[13px] font-semibold text-rose-200">{percentLabel(sourceQualityGapSummary.sourceFamilyPercents.broadFallbackOrSupport)}</div>
                    <div className="text-[10px] leading-3 text-gray-500">broad support</div>
                  </div>
                  <div>
                    <div className="font-mono text-[13px] font-semibold text-amber-200">{percentLabel(sourceQualityGapSummary.sourceFamilyPercents.conedFoundation)}</div>
                    <div className="text-[10px] leading-3 text-gray-500">2 m base</div>
                  </div>
                  <div>
                    <div className="font-mono text-[13px] font-semibold text-cyan-200">{percentLabel(sourceQualityGapSummary.sourceFamilyPercents.measuredDetail)}</div>
                    <div className="text-[10px] leading-3 text-gray-500">measured detail</div>
                  </div>
                </div>
                {sourceQualityGapSummary.priorityZones[0] ? (
                  <div className="border-t border-white/[0.07] pt-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-semibold text-gray-200">{sourceQualityGapSummary.priorityZones[0].label}</span>
                      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.08em] text-amber-200">{sourceQualityGapSummary.priorityZones[0].tierLabel}</span>
                    </div>
                    {sourceQualityGapSummary.priorityZones[0].topCategories?.length ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {sourceQualityGapSummary.priorityZones[0].topCategories.slice(0, 2).map((category) => (
                          <span key={category.category} className="rounded border border-white/[0.08] bg-white/[0.04] px-1.5 py-0.5 text-[10px] leading-3 text-gray-300">
                            {compactSourceCategory(category.category)} {percentLabel(category.percent)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-1 text-[11px] leading-4 text-gray-400">{sourceQualityGapSummary.priorityZones[0].nextAction}</p>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        <div>
          <span className={`mb-1.5 block ${sectionTitleClass}`}>Fly to</span>
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-white/[0.04] p-1 sm:grid-cols-4">
            {viewPresets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => onViewPreset(preset.viewState)}
                className={`min-h-8 rounded-md px-2 text-xs font-semibold text-gray-300 transition-colors hover:bg-white/[0.06] hover:text-white ${FOCUS_RING}`}
                title={`${preset.label} view`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </Section>

      {/* Display - aesthetic / rendering controls, collapsed by default. */}
      <Section
        title="Display"
        icon={<Mountain size={12} />}
        collapsible
        defaultOpen={false}
        trailing={<span className={valueClass}>{activeSceneProfile?.label}</span>}
      >
        <div className="space-y-1.5">
          <span className={`block ${sectionTitleClass}`}>Scene</span>
          <SegmentedControl options={SCENE_PROFILE_OPTIONS} value={sceneProfile} onChange={onSceneProfileChange} ariaLabel="Scene profile" />
        </div>
        <div className="space-y-1.5">
          <span className={`block ${sectionTitleClass}`}>Mesh detail</span>
          <SegmentedControl options={TERRAIN_DETAIL_OPTIONS} value={terrainDetail} onChange={onTerrainDetailChange} ariaLabel="Terrain mesh detail" />
        </div>
        <div className="space-y-1.5">
          <span className={`block ${sectionTitleClass}`}>Mesh finish</span>
          <SegmentedControl options={TERRAIN_SURFACE_SMOOTHING_OPTIONS} value={terrainSurfaceSmoothing} onChange={onTerrainSurfaceSmoothingChange} ariaLabel="Terrain mesh finish" />
        </div>
        <div className="space-y-1.5">
          <span className={`block ${sectionTitleClass}`}>Surface style</span>
          <SegmentedControl options={TERRAIN_TEXTURE_OPTIONS} value={terrainTextureMode} onChange={onTerrainTextureModeChange} columns={4} ariaLabel="Surface style" />
        </div>
      </Section>

      {/* Terrain source - power-user / provenance controls, collapsed by default. */}
      <Section
        title="Terrain source"
        icon={<Database size={12} />}
        collapsible
        defaultOpen={false}
        trailing={<span className={`max-w-[8rem] truncate ${valueClass}`}>{terrainSourceTrailing}</span>}
      >
        <SegmentedControl options={TERRAIN_SOURCE_MODE_OPTIONS} value={terrainSourceMode} onChange={onTerrainSourceModeChange} ariaLabel="Terrain source mode" />
        <div className="grid grid-cols-[2rem_1fr_2rem] gap-1">
          <button
            type="button"
            onClick={onPreviousTerrainSource}
            disabled={!terrainSources.length}
            className={`grid h-8 place-items-center rounded-md border border-white/10 bg-white/[0.04] text-gray-300 transition-colors hover:bg-white/[0.08] hover:text-white ${FOCUS_RING} disabled:cursor-not-allowed disabled:opacity-40`}
            aria-label="Previous terrain source"
            title="Previous source"
          >
            <ChevronLeft size={15} />
          </button>
          <select
            value={activeTerrainSource?.sourceId ?? ""}
            onChange={(event) => onTerrainSourceChange(event.currentTarget.value)}
            disabled={!terrainSources.length}
            className="h-8 min-w-0 rounded-md border border-white/10 bg-gray-900/80 px-2 text-xs font-semibold text-gray-100 outline-none transition-colors focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/30 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Terrain source"
            title={activeTerrainSource ? `${activeTerrainSource.sourceLabel} (${terrainSourceMeta(activeTerrainSource)})` : "Terrain source"}
          >
            {terrainSourceGroupNames.map((group) => (
              <optgroup key={group} label={group}>
                {terrainSourceGroups[group].map((source) => (
                  <option key={source.sourceId} value={source.sourceId}>
                    {terrainSourceShortLabel(source)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <button
            type="button"
            onClick={onNextTerrainSource}
            disabled={!terrainSources.length}
            className={`grid h-8 place-items-center rounded-md border border-white/10 bg-white/[0.04] text-gray-300 transition-colors hover:bg-white/[0.08] hover:text-white ${FOCUS_RING} disabled:cursor-not-allowed disabled:opacity-40`}
            aria-label="Next terrain source"
            title="Next source"
          >
            <ChevronRight size={15} />
          </button>
        </div>
        {activeTerrainSource ? (
          <div className="truncate font-mono text-[10px] leading-4 text-gray-500" title={activeTerrainSource.sourceLabel}>
            {terrainSourceMeta(activeTerrainSource)}
          </div>
        ) : null}
      </Section>

      <div className="mt-4 space-y-2 border-t border-white/[0.06] pt-4 text-xs leading-4 text-gray-400">
        <div className="flex gap-2">
          <Database size={13} className="mt-0.5 shrink-0 text-cyan-300" />
          <span>{activeSlice.sourceModel}</span>
        </div>
        {terrainStackSummary ? <p>{terrainStackSummary}</p> : null}
        <p>{activeSlice.datumNote}</p>
        {showUncertainty ? <p>{activeSlice.uncertaintyNote}</p> : null}
      </div>
    </section>
  );
}
