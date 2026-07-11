# EX1505 Vertical-Reference Audit

This is a targeted check of the remaining apparent height difference between the NOAA/NCEI EX1505 75 m multibeam grid and the USGS CoNED 2 m Farallon-shelf clip.

## Decision

Do not apply the apparent `+7.3 m` EX1505 correction. The difference is not a verified source-wide offset. The evidence points to a mixed-source seam, with EX1505's vertical reference still unresolved:

- EX1505's official NCEI ISO metadata identifies the horizontal system as WGS 84 and labels the vertical datum **unknown**. Its vertical extent uses the generic EPSG:5715 “MSL depth” label, which is not a location-specific tide or geoid model.
- The preparation path only assigns the horizontal CRS (`gdal_translate -a_srs EPSG:4326`) and then resamples horizontally to EPSG:4326. There is no hidden vertical conversion in the EX1505 path.
- In a targeted common grid around the southern Golden Gate/Farallon overlap, EX1505 is about 5.4 m higher than CoNED at the median of 2,091 overlapping pixels. This is smaller than the 7.3 m flag from the broad 1,024-pixel audit and varies along the overlap.
- A three-way check against NOAA/NOS H13334 gives a more useful decomposition over 1,009 shared pixels: EX1505 minus H13334 has a median of **+1.19 m**; H13334 minus CoNED has a median of **+3.37 m**; EX1505 minus CoNED has a median of **+4.56 m**. H13334 is explicitly MLLW in NOAA's survey record, while CoNED is NAVD88 in USGS product documentation.
- NOAA VDatum samples at four points in this overlap return NAVD88 → MLLW corrections of only **+0.015 to +0.018 m**, with stated uncertainty around **0.084 m**. That is far too small to explain the 3–5 m three-way differences. The remaining gap is therefore a local source-surface difference (plus EX1505's unresolved vertical reference), not a justified MLLW-to-NAVD88 shift.

In plain English: the CoNED seam is not evidence that EX1505 was warped incorrectly. It is a mixed-source seam involving an unknown EX1505 vertical reference and a local CoNED surface that does not match the independent H13334 surface. The independent survey and VDatum checks do not support adding 7.3 m to EX1505.

## What was checked

| Check | Result |
|---|---|
| Raw EX1505 grid | 10,788 × 3,615 Float32 grid; EPSG:4326 horizontal CRS; `-32768` nodata; values are negative seafloor elevations. |
| EX1505 preparation | XYZ → GeoTIFF with horizontal `EPSG:4326`, then horizontal WGS84 warp/resample; no vertical transform. |
| Broad overlap audit | EX1505 median about +7.3 m vs CoNED, but with a wide mixed spread. |
| Targeted overlap | EX1505 median about +5.4 m vs CoNED in the actual valid track overlap. |
| Independent H13334 tie | EX1505 is about +1.2 m vs the nearby MLLW H13334 survey; CoNED is about 3.4 m lower than H13334 in the same three-way overlap. |
| VDatum tie | NAVD88 → MLLW is only about +0.02 m at four overlap points, so the multi-meter difference is not explained by that tidal-datum conversion. |

## Current handling

EX1505 remains useful as measured offshore shape where it fills broad CRM gaps. Its overlap with CoNED is now treated as a warning seam, not a correction target. The project should not claim exact paleo waterline elevations from this patch until a location-specific vertical tie is available.

The next safe improvement is a local source-surface check using the paired H13334 MLLW and ellipsoid products plus VDatum/tidal metadata. If that bridge cannot identify EX1505's original reference, preserve the current terrain shape and avoid inventing a constant offset.

## Source records

- [NOAA/NCEI EX1505 multibeam report](https://www.ngdc.noaa.gov/ships/okeanos_explorer/EX1505_mb.html)
- [NOAA/NOS H13334 survey record](https://www.ngdc.noaa.gov/nos/H12001-H14000/H13334.html)
- [USGS CoNED topobathymetric model description](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-coastal-national-elevation-database-coned)
- [EPSG:5715 generic MSL-depth definition](https://epsg.io/5715)
- [NOAA VDatum API documentation](https://vdatum.noaa.gov/docs/services.html)
