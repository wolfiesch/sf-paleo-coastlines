import type { MapViewState } from "deck.gl";

export interface TourStep {
  id: string;
  yearsBP: number;
  caption: string;
  viewState: MapViewState;
  flyMs: number;   // camera + year transition duration
  holdMs: number;  // pause after arriving
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: "lowstand",
    yearsBP: 20000,
    caption: "20,000 years ago: sea level was ~120 m lower. The Bay was a dry valley and you could walk to the Farallon Islands.",
    viewState: { longitude: -123.13, latitude: 37.69, zoom: 8.75, pitch: 62, bearing: -34 },
    flyMs: 3000,
    holdMs: 4500,
  },
  {
    id: "river",
    yearsBP: 15000,
    caption: "The Sacramento–San Joaquin river drained west across the exposed shelf, carving the canyon that is now the Golden Gate.",
    viewState: { longitude: -122.61, latitude: 37.78, zoom: 10.05, pitch: 64, bearing: -39 },
    flyMs: 3500,
    holdMs: 4500,
  },
  {
    id: "flooding",
    yearsBP: 10000,
    caption: "10,000 years ago: rapid post-glacial rise pushed the ocean back through the Gate and began flooding the valley.",
    viewState: { longitude: -122.61, latitude: 37.80, zoom: 9.6, pitch: 60, bearing: -36 },
    flyMs: 3500,
    holdMs: 4500,
  },
  {
    id: "present",
    yearsBP: 0,
    caption: "Today: the drowned valley is San Francisco Bay. The old river canyon survives as the deep channel under the Golden Gate.",
    viewState: { longitude: -122.88, latitude: 37.78, zoom: 8.55, pitch: 58, bearing: -32 },
    flyMs: 4000,
    holdMs: 4000,
  },
];
