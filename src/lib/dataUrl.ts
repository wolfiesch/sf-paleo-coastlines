/**
 * Resolves browser data paths against an optional external origin.
 *
 * The generated map data (terrain tiles, slices, waterline probes, provenance
 * GeoJSON) is several gigabytes. Keeping it inside `public/` works for local
 * development but makes the repository unclonable and rules out most static
 * hosts. Setting `VITE_DATA_BASE_URL` at build time points every data fetch at
 * an object store or CDN instead, without touching the manifest, the generator,
 * or any call site.
 *
 * Unset (the default) keeps the original root-relative behaviour, so a plain
 * `pnpm dev` against a local `public/data` tree is unchanged.
 *
 * Paths outside `/data/` and already-absolute URLs pass through untouched, so
 * basemap styles and third-party tile templates are safe to route through this
 * helper indiscriminately.
 */
const DATA_BASE = ((import.meta.env.VITE_DATA_BASE_URL as string | undefined) ?? "").replace(/\/+$/, "");

export function dataUrl(path: string): string {
  if (!DATA_BASE || !path.startsWith("/data/")) return path;
  return DATA_BASE + path;
}
