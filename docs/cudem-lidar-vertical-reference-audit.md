# CUDEM and USGS LiDAR vertical-reference audit

This documents a systemic height error found while comparing the broad terrain sources. It is separate from the remaining survey-specific MLLW work.

## What was wrong

Both source families carry a horizontal CRS and a NAVD88 vertical CRS:

- NOAA CUDEM tiles advertise `NAD83 + NAVD88 height`.
- The 2023 USGS San Francisco LiDAR tiles advertise `NAD83(2011) / San Francisco CS13 + NAVD88 height - Geoid18 (m)`.

The old preparation command asked GDAL to warp those compound sources directly to plain `EPSG:4326`. That made GDAL convert the height values toward ellipsoidal height and then discard the vertical label. The result was a repeatable local error of about 33–34 m.

NOAA's dataset metadata describes the CUDEM tiles as vertically referenced to NAVD88: [NCEI CUDEM human-readable metadata](https://coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/ncei_nintharcsec_dem_m8483_met_forHumans.html).

## Reproduction

The same source location was sampled before and after the fix:

| Source and point | Old direct warp | Horizontal-only warp | Interpretation |
|---|---:|---:|---|
| CUDEM, `(-122.90, 37.90)` | `-92.19 m` | `-58.36 m` | The live CUDEM source and corrected output agree; the old output was about 33.8 m too low. |
| USGS LiDAR, `(-122.3825, 37.7475)` | `-34.05 m` | `-1.07 m` | The raw LiDAR tile and corrected output agree; the old output was about 33.0 m too low. |

The production fix is deliberately small:

- CUDEM preparation uses `gdalwarp -s_srs EPSG:4326 -t_srs EPSG:4326`.
- USGS LiDAR preparation uses `gdalwarp -s_srs EPSG:7131 -t_srs EPSG:4326`.

The source override tells GDAL to treat the input CRS as horizontal for this export. It changes the map coordinates without performing a vertical conversion.

## Post-fix evidence

After rebuilding the prepared rasters, fused terrain, and browser tiles, the vertical-overlap audit reports:

- CUDEM versus CRM: median difference `+0.17 m` over about `20,167 sq km`; no longer a 33 m offset.
- USGS LiDAR versus CRM: median difference `+0.804 m` over about `175 sq km`; no longer a 33 m offset.
- The local seam audit fell to `1` severe target and `16` suspicious targets, from `24` suspicious targets before this datum pass.

The audit still shows real smaller differences. In particular, the broad overlap audit flags NOAA/NCEI EX1505 as roughly 7 m above CoNED, but a targeted three-way check against the nearby NOAA/NOS H13334 MLLW survey shows that this is a mixed-reference seam rather than a safe blanket correction. See `docs/ex1505-vertical-reference-audit.md`. NOAA BAG/OCM layers still have survey-specific tidal references as well.

## Rebuild path

```bash
pnpm paleo-coastlines:generate
python3 scripts/regenerate_best_available_fusion.py
python3 scripts/generate_terrain_tiles.py --source-id best_available_gate_shelf_fusion --clean --workers 8
python3 scripts/audit_vertical_overlaps.py
python3 scripts/audit_local_seam_heights.py
```
