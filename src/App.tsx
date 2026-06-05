import { useCallback, useEffect, useMemo, useState } from "react";
import { DeckGL } from "@deck.gl/react";
import { Map } from "react-map-gl/maplibre";
import type { MapViewState } from "deck.gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { PaleoCoastlineControls } from "./components/PaleoCoastlineControls";
import { createPaleoCoastlineLayers, getPaleoTooltip } from "./layers/paleoCoastlineLayer";
import { DARK_MAP_STYLE } from "./lib/mapStyles";
import type { PaleoTimeSlice, PaleoTimeSliceId } from "./types";

const START_VIEW: MapViewState = {
  longitude: -122.88,
  latitude: 37.78,
  zoom: 8.55,
  pitch: 58,
  bearing: -32,
};

function App() {
  const [viewState, setViewState] = useState<MapViewState>(START_VIEW);
  const [slices, setSlices] = useState<PaleoTimeSlice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSliceId, setActiveSliceId] = useState<PaleoTimeSliceId>("20k_years_ago");
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [waterLevelMeters, setWaterLevelMeters] = useState<number | null>(-120);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadPaleoData() {
      try {
        const response = await fetch("/data/paleo-coastlines/paleo_coastlines.json");
        if (!response.ok) {
          throw new Error(`Failed to load paleo data: ${response.status}`);
        }
        const payload = await response.json() as PaleoTimeSlice[];
        if (!cancelled) {
          setSlices(payload);
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

    void loadPaleoData();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isPlaying) return;

    const timer = window.setInterval(() => {
      setWaterLevelMeters((current) => {
        const level = current ?? 2;
        return level <= -120 ? 2 : level - 1;
      });
    }, 220);

    return () => window.clearInterval(timer);
  }, [isPlaying]);

  const activeSlice = useMemo(
    () => slices.find((slice) => slice.id === activeSliceId) ?? slices[0] ?? null,
    [activeSliceId, slices],
  );

  const layers = useMemo(() => createPaleoCoastlineLayers(slices, {
    paleoTimeSliceId: activeSliceId,
    showPaleoUncertainty: showUncertainty,
    paleoWaterLevelMeters: waterLevelMeters,
  }), [activeSliceId, showUncertainty, slices, waterLevelMeters]);

  const handleSliceChange = useCallback((id: PaleoTimeSliceId) => {
    setIsPlaying(false);
    setActiveSliceId(id);
    const nextSlice = slices.find((slice) => slice.id === id);
    if (nextSlice) {
      setWaterLevelMeters(nextSlice.seaLevelMeters);
    }
  }, [slices]);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-gray-950 text-white">
      <DeckGL
        layers={layers}
        viewState={viewState}
        controller
        onViewStateChange={({ viewState: nextViewState }) => setViewState(nextViewState as MapViewState)}
        getTooltip={({ object }) => getPaleoTooltip(object)}
      >
        <Map mapStyle={DARK_MAP_STYLE} reuseMaps />
      </DeckGL>

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
          slices={slices}
          activeSliceId={activeSliceId}
          showUncertainty={showUncertainty}
          waterLevelMeters={waterLevelMeters}
          isPlaying={isPlaying}
          onSliceChange={handleSliceChange}
          onToggleUncertainty={() => setShowUncertainty((shown) => !shown)}
          onWaterLevelChange={(level) => {
            setIsPlaying(false);
            setWaterLevelMeters(level);
          }}
          onTogglePlayback={() => setIsPlaying((playing) => !playing)}
          onResetWaterLevel={() => {
            setIsPlaying(false);
            setWaterLevelMeters(2);
          }}
        />
      </div>

      <aside className="pointer-events-none absolute bottom-4 right-4 z-20 w-[20rem] max-w-[calc(100vw-2rem)] rounded-lg border border-white/10 bg-gray-950/88 p-3 text-xs leading-4 text-gray-400 shadow-2xl backdrop-blur-md">
        {loading ? <p>Loading terrain and coastline data...</p> : null}
        {error ? <p className="text-red-200">{error}</p> : null}
        {!loading && !error && activeSlice ? (
          <div className="space-y-2">
            <div className="font-mono text-[11px] uppercase tracking-wide text-cyan-200">
              {activeSlice.label} / {waterLevelMeters ?? activeSlice.seaLevelMeters} m waterline
            </div>
            <p>This standalone app contains only the paleo coastline simulator. Civic layers such as police, 311, permits, and live feeds stay in CityScope.</p>
          </div>
        ) : null}
      </aside>
    </main>
  );
}

export default App;
