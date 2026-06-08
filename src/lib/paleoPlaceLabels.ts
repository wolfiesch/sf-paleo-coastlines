/**
 * Curated paleo-geography labels. Positions are approximate. `elevationM` is a
 * rough bed elevation used to drape the label onto the terrain. `minYearsBP` /
 * `maxYearsBP` set the time window in which a label is relevant (e.g. the
 * exposed shelf only makes sense at low sea level / old dates).
 */
export interface PaleoPlaceLabel {
  text: string;
  longitude: number;
  latitude: number;
  elevationM: number;
  minYearsBP: number;
  maxYearsBP: number;
}

export const PALEO_PLACE_LABELS: PaleoPlaceLabel[] = [
  { text: "Paleo Golden Gate", longitude: -122.55, latitude: 37.81, elevationM: -60, minYearsBP: 6000, maxYearsBP: 20000 },
  { text: "Sacramento–San Joaquin valley", longitude: -122.30, latitude: 38.02, elevationM: -30, minYearsBP: 7000, maxYearsBP: 20000 },
  { text: "Farallon Plain (dry land)", longitude: -123.00, latitude: 37.70, elevationM: -90, minYearsBP: 11000, maxYearsBP: 20000 },
  { text: "Exposed outer shelf", longitude: -123.30, latitude: 37.62, elevationM: -110, minYearsBP: 14000, maxYearsBP: 20000 },
  { text: "Colma Gap", longitude: -122.46, latitude: 37.69, elevationM: -20, minYearsBP: 4000, maxYearsBP: 20000 },
  { text: "Modern Bay shoreline", longitude: -122.30, latitude: 37.80, elevationM: 0, minYearsBP: 0, maxYearsBP: 6000 },
];
