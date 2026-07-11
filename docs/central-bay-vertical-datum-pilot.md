# Central Bay Vertical-Datum Pilot

This report tests whether Central Bay needs one blanket height correction. It does not modify production terrain.

## Overlap Results

| NOAA source block | Overlap pixels | Median difference | 10th–90th percentile | 95% absolute difference |
|---|---:|---:|---:|---:|
| noaa_ocm_area_a_ca1b08_1m | 292 | -0.429 m | -1.001 to -0.138 m | 1.233 m |
| noaa_ocm_area_a_ca1b09_1m | 1331 | -0.001 m | -0.06 to 0.015 m | 0.167 m |
| noaa_ocm_area_a_ca1b22_1m | 7520 | -0.001 m | -0.025 to 0.022 m | 0.065 m |
| noaa_ocm_area_a_ca1b24_1m | 15265 | -0.001 m | -0.017 to 0.014 m | 0.064 m |
| noaa_ocm_area_a_ca1b26_1m | 1838 | 0.001 m | -0.039 to 0.042 m | 0.078 m |
| noaa_ocm_area_a_na1b15_1m | 29432 | -0.0 m | -0.015 to 0.012 m | 0.042 m |

## NOAA VDatum Samples

These values are the modeled correction from zero meters NAVD88 to MLLW at each point.

| Longitude | Latitude | NAVD88 → MLLW | Stated uncertainty |
|---:|---:|---:|---:|
| -122.46 | 37.86 | -0.001 m | ±0.078 m |
| -122.42 | 37.84 | 0.015 m | ±0.078 m |
| -122.38 | 37.82 | 0.02 m | ±0.078 m |
| -122.34 | 37.8 | 0.036 m | ±0.078 m |
| -122.3 | 37.78 | 0.075 m | ±0.077 m |

## Decision

Do **not** apply a blanket Central Bay vertical offset. Most source blocks already align within centimeters. Investigate CA1B08 as a local survey-edge or surface-age difference before changing its heights.

The earlier roughly 33 m Central Bay warning is a comparison against broad CUDEM, not evidence that the modern Central Bay source stack is shifted by 33 m.
