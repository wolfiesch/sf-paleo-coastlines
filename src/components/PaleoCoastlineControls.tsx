import { Database, Gauge, Layers3, MapPinned, Pause, Play, RotateCcw, Waves } from "lucide-react";
import type { MapViewState } from "deck.gl";
import type { PaleoTimeSlice, PaleoTimeSliceId, SceneProfile, TerrainDetailLevel, TerrainTextureMode } from "../types";

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
  waterLevelMeters: number | null;
  isPlaying: boolean;
  terrainDetail: TerrainDetailLevel;
  terrainTextureMode: TerrainTextureMode;
  sceneProfile: SceneProfile;
  viewPresets: ViewPreset[];
  onSliceChange: (id: PaleoTimeSliceId) => void;
  onToggleUncertainty: () => void;
  onToggleTerrainFootprints: () => void;
  onToggleBaySourceFootprints: () => void;
  onWaterLevelChange: (level: number) => void;
  onTogglePlayback: () => void;
  onResetWaterLevel: () => void;
  onTerrainDetailChange: (level: TerrainDetailLevel) => void;
  onTerrainTextureModeChange: (mode: TerrainTextureMode) => void;
  onSceneProfileChange: (profile: SceneProfile) => void;
  onViewPreset: (viewState: MapViewState) => void;
}

const TERRAIN_DETAIL_OPTIONS: { id: TerrainDetailLevel; label: string; title: string }[] = [
  { id: "fast", label: "Fast", title: "Lower mesh density" },
  { id: "detailed", label: "Detailed", title: "Balanced mesh density" },
  { id: "survey", label: "Survey", title: "Highest mesh density" },
];

const TERRAIN_TEXTURE_OPTIONS: { id: TerrainTextureMode; label: string; title: string }[] = [
  { id: "bottom", label: "Bottom", title: "Interpreted seafloor type where USGS character maps exist" },
  { id: "hybrid", label: "Hybrid", title: "Survey texture plus acoustic backscatter where sonar exists" },
  { id: "survey", label: "Survey", title: "Slope, roughness, ridge, and hollow detail blended with depth color" },
  { id: "relief", label: "Relief", title: "Depth color plus DEM-derived light and shadow" },
  { id: "sonar", label: "Sonar", title: "Acoustic backscatter where available, relief elsewhere" },
  { id: "color", label: "Color", title: "Depth color without baked terrain shading" },
];

const SCENE_PROFILE_OPTIONS: { id: SceneProfile; label: string; title: string }[] = [
  { id: "study", label: "Study", title: "Lower contrast view for reading source layers and labels" },
  { id: "relief", label: "Relief", title: "Stronger height, light, and shadow for terrain shape" },
  { id: "emergence", label: "Emerge", title: "Clearer waterline and newly exposed terrain" },
];

const COVERAGE_LEGEND = [
  { label: "NOAA BAG", className: "bg-cyan-300" },
  { label: "USGS CSMP", className: "bg-amber-300" },
  { label: "USGS offshore", className: "bg-violet-300" },
  { label: "SF Bar", className: "bg-emerald-300" },
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

function terrainSummary(slice: PaleoTimeSlice): string | null {
  const terrains = slice.terrains?.length ? slice.terrains : slice.terrain ? [slice.terrain] : [];
  if (!terrains.length) return null;
  if (terrains.length === 1) return terrains[0].note;
  return `${terrains.length} terrain surfaces: NOAA CRM/CUDEM broad Bay-to-coast coverage, NOAA BAG Golden Gate and Farallon-region survey patches, USGS/CSMP 2 m coastal bathymetry blocks, Farallon Escarpment/Rittenburg Bank offshore multibeam patches, and DS684 Golden Gate detail.`;
}

export function PaleoCoastlineControls({
  slices,
  activeSliceId,
  showUncertainty,
  showTerrainFootprints,
  showBaySourceFootprints,
  waterLevelMeters,
  isPlaying,
  terrainDetail,
  terrainTextureMode,
  sceneProfile,
  viewPresets,
  onSliceChange,
  onToggleUncertainty,
  onToggleTerrainFootprints,
  onToggleBaySourceFootprints,
  onWaterLevelChange,
  onTogglePlayback,
  onResetWaterLevel,
  onTerrainDetailChange,
  onTerrainTextureModeChange,
  onSceneProfileChange,
  onViewPreset,
}: PaleoCoastlineControlsProps) {
  const options = slices.length ? slices : FALLBACK_SLICES;
  const activeSlice = options.find((slice) => slice.id === activeSliceId) ?? options[0];
  const activeWaterLevel = waterLevelMeters ?? activeSlice.seaLevelMeters;
  const probeLevel = Math.max(-120, Math.min(0, nearestProbeLevel(activeWaterLevel)));
  const terrainStackSummary = terrainSummary(activeSlice);
  const activeTerrainDetail = TERRAIN_DETAIL_OPTIONS.find((option) => option.id === terrainDetail);
  const activeTextureMode = TERRAIN_TEXTURE_OPTIONS.find((option) => option.id === terrainTextureMode);
  const activeSceneProfile = SCENE_PROFILE_OPTIONS.find((option) => option.id === sceneProfile);

  return (
    <section className="pointer-events-auto max-h-[calc(100vh-6rem)] w-full overflow-y-auto rounded-lg border border-cyan-400/20 bg-gray-950/92 p-3 shadow-2xl backdrop-blur-md">
      <div className="mb-3 flex items-start gap-2">
        <div className="mt-0.5 rounded-md border border-cyan-400/25 bg-cyan-400/10 p-1.5 text-cyan-200">
          <Waves size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold leading-5 text-white">SF Paleo Coastline</h2>
          <p className="text-xs leading-4 text-gray-400">{activeSlice.summary}</p>
        </div>
      </div>

      <div className="mb-3 grid grid-cols-4 gap-1 rounded-lg border border-gray-700/50 bg-gray-900/70 p-1">
        {options.map((slice) => {
          const active = slice.id === activeSlice.id;
          return (
            <button
              key={slice.id}
              type="button"
              onClick={() => onSliceChange(slice.id)}
              className={`min-h-9 rounded-md px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                active
                  ? "bg-cyan-300 text-gray-950"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              }`}
              aria-pressed={active}
            >
              {compactLabel(slice.label)}
            </button>
          );
        })}
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-gray-700/50 bg-gray-900/60 p-2">
          <div className="flex items-center gap-1.5 text-[11px] uppercase leading-4 text-gray-500">
            <Gauge size={12} />
            Slice sea level
          </div>
          <div className="pt-1 font-mono text-sm text-cyan-100">
            {activeSlice.seaLevelMeters} m
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleUncertainty}
          className={`rounded-lg border p-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
            showUncertainty
              ? "border-cyan-400/30 bg-cyan-400/10"
              : "border-gray-700/50 bg-gray-900/60 hover:bg-gray-800/70"
          }`}
          aria-pressed={showUncertainty}
        >
          <div className="text-[11px] uppercase leading-4 text-gray-500">Uncertainty</div>
          <div className="pt-1 font-mono text-sm text-cyan-100">
            {showUncertainty ? `+/- ${activeSlice.uncertaintyMeters} m` : "hidden"}
          </div>
        </button>
      </div>

      <div className="mb-3 rounded-lg border border-gray-700/50 bg-gray-900/60 p-2">
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="flex items-center gap-1.5 text-[11px] uppercase leading-4 text-gray-500">
            <MapPinned size={12} />
            View
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              onClick={onToggleTerrainFootprints}
              className={`flex min-h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                showTerrainFootprints
                  ? "border-cyan-300/40 bg-cyan-300 text-gray-950"
                  : "border-gray-700/70 bg-gray-950/60 text-gray-300 hover:bg-gray-800 hover:text-white"
              }`}
              aria-pressed={showTerrainFootprints}
              title="Show rendered high-detail terrain coverage"
            >
              <Layers3 size={13} />
              Coverage
            </button>
            <button
              type="button"
              onClick={onToggleBaySourceFootprints}
              className={`flex min-h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                showBaySourceFootprints
                  ? "border-emerald-300/40 bg-emerald-300 text-gray-950"
                  : "border-gray-700/70 bg-gray-950/60 text-gray-300 hover:bg-gray-800 hover:text-white"
              }`}
              aria-pressed={showBaySourceFootprints}
              title="Show source surveys used by the USGS 1 m Bay DEM"
            >
              <Database size={13} />
              Bay sources
            </button>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-1 rounded-md border border-gray-800/80 bg-gray-950/60 p-1">
          {viewPresets.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => onViewPreset(preset.viewState)}
              className="min-h-8 rounded px-2 text-xs font-semibold text-gray-300 transition-colors hover:bg-gray-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
              title={`${preset.label} view`}
            >
              {preset.label}
            </button>
          ))}
        </div>
        {showTerrainFootprints ? (
          <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 border-t border-gray-800/80 pt-2 text-[10px] uppercase leading-4 text-gray-500">
            {COVERAGE_LEGEND.map((item) => (
              <span key={item.label} className="flex items-center gap-1.5">
                <span className={`h-1.5 w-4 rounded-full ${item.className}`} />
                {item.label}
              </span>
            ))}
          </div>
        ) : null}
        {showBaySourceFootprints ? (
          <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-1 border-t border-gray-800/80 pt-2 text-[10px] uppercase leading-4 text-gray-500">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-emerald-300" />
              Direct 1 m
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-violet-300" />
              Interp.
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-amber-300" />
              Single beam
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-cyan-300" />
              Multibeam
            </span>
          </div>
        ) : null}
      </div>

      <label className="mb-3 block rounded-lg border border-gray-700/50 bg-gray-900/60 p-2">
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase leading-4 text-gray-500">Waterline</span>
          <span className="font-mono text-sm text-cyan-100">{activeWaterLevel} m</span>
        </div>
        <input
          type="range"
          min="-120"
          max="2"
          step="1"
          value={activeWaterLevel}
          onChange={(event) => onWaterLevelChange(Number(event.currentTarget.value))}
          className="w-full accent-cyan-300"
        />
        <div className="mt-2 grid grid-cols-[1fr_auto] items-center gap-2">
          <div className="min-w-0">
            <div className="truncate text-xs text-gray-300">{waterlineStage(activeWaterLevel)}</div>
            <div className="font-mono text-[11px] leading-4 text-gray-500">contour band {probeLevel - 30} to {probeLevel + 30} m</div>
          </div>
          <div className="flex shrink-0 gap-1">
            <button
              type="button"
              onClick={onTogglePlayback}
              className="grid h-8 w-8 place-items-center rounded-md border border-cyan-400/25 bg-cyan-400/10 text-cyan-100 transition-colors hover:bg-cyan-300 hover:text-gray-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
              aria-label={isPlaying ? "Pause waterline playback" : "Play waterline playback"}
              title={isPlaying ? "Pause" : "Play"}
            >
              {isPlaying ? <Pause size={15} /> : <Play size={15} />}
            </button>
            <button
              type="button"
              onClick={onResetWaterLevel}
              className="grid h-8 w-8 place-items-center rounded-md border border-gray-700/70 bg-gray-950/60 text-gray-300 transition-colors hover:bg-gray-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
              aria-label="Reset waterline to high water"
              title="Reset"
            >
              <RotateCcw size={14} />
            </button>
          </div>
        </div>
        <div className="mt-2 grid grid-cols-4 gap-1 border-t border-gray-800/80 pt-2 text-[10px] uppercase leading-4 text-gray-500">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-4 rounded-full bg-white" />
            Waterline
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-4 rounded-full bg-amber-300" />
            Exposed
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-4 rounded-full bg-cyan-300" />
            Submerged
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-4 rounded-full bg-sky-700" />
            Depth
          </span>
        </div>
      </label>

      <div className="mb-3 rounded-lg border border-gray-700/50 bg-gray-900/60 p-2">
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase leading-4 text-gray-500">Scene</span>
          <span className="font-mono text-[11px] leading-4 text-cyan-100">{activeSceneProfile?.label}</span>
        </div>
        <div className="mb-2 grid grid-cols-3 gap-1 rounded-md border border-gray-800/80 bg-gray-950/60 p-1">
          {SCENE_PROFILE_OPTIONS.map((option) => {
            const active = option.id === sceneProfile;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => onSceneProfileChange(option.id)}
                className={`min-h-8 rounded px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                  active
                    ? "bg-cyan-300 text-gray-950"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`}
                aria-pressed={active}
                title={option.title}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="text-[11px] uppercase leading-4 text-gray-500">Terrain mesh</span>
          <span className="font-mono text-[11px] leading-4 text-cyan-100">{activeTerrainDetail?.label}</span>
        </div>
        <div className="grid grid-cols-3 gap-1 rounded-md border border-gray-800/80 bg-gray-950/60 p-1">
          {TERRAIN_DETAIL_OPTIONS.map((option) => {
            const active = option.id === terrainDetail;
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => onTerrainDetailChange(option.id)}
                className={`min-h-8 rounded px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                  active
                    ? "bg-cyan-300 text-gray-950"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`}
                aria-pressed={active}
                title={option.title}
              >
                {option.label}
              </button>
            );
          })}
        </div>
        <div className="mt-2 border-t border-gray-800/80 pt-2">
          <span className="text-[11px] uppercase leading-4 text-gray-500">Surface style</span>
          <div className="mt-1 grid grid-cols-3 gap-1 rounded-md border border-gray-800/80 bg-gray-950/60 p-1">
            {TERRAIN_TEXTURE_OPTIONS.map((option) => {
              const active = option.id === terrainTextureMode;
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => onTerrainTextureModeChange(option.id)}
                  className={`min-h-7 rounded px-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                    active
                      ? "bg-cyan-300 text-gray-950"
                      : "text-gray-300 hover:bg-gray-800 hover:text-white"
                  }`}
                  aria-pressed={active}
                  title={option.title}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <span className="sr-only">{activeTextureMode?.label}</span>
        </div>
      </div>

      <div className="space-y-2 border-t border-gray-800/70 pt-3 text-xs leading-4 text-gray-400">
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
