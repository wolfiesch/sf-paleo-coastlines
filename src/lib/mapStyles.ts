import type { StyleSpecification } from "maplibre-gl";

// Modern street reference (Carto dark matter), kept behind the "Modern" layer
// toggle so viewers can compare paleo shorelines against today's geography.
export const MODERN_REFERENCE_MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// Default backdrop: a single deep-ocean tone with no roads, parcels, or modern
// labels. The paleo terrain covers the study extent, so this only shows at the
// edges, where flat abyssal water is the honest reading.
export const PALEO_MAP_STYLE: StyleSpecification = {
  version: 8,
  name: "paleo-deep-ocean",
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#04111e" },
    },
  ],
};
