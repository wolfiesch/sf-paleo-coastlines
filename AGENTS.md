# AGENTS.md

This is the standalone SF paleo-coastline simulator.

Keep this project separate from `cityscope-sf`:

- Do not add police, 311, permits, fire, live feed, or civic dashboard layers here.
- Keep this app focused on 3D terrain, bathymetry, old coastlines, sea-level controls, and source notes.
- Put GIS source files under `data/paleo-coastlines`.
- Put browser-ready generated files under `public/data/paleo-coastlines`.
- Use `pnpm paleo-coastlines:generate` after changing the GIS pipeline.
- Use `pnpm paleo-coastlines:terrain-tiles` after changing only browser terrain tiles.
- The browser's ultra terrain uses `best_available_gate_shelf_fusion`; make sure its terrain tiles are regenerated after changing best-available terrain output.
- `python3 scripts/generate_paleo_coastlines.py --help` currently does not print help; it starts the generator. Do not use it as a harmless help probe.
- Do not trust a focused best-available terrain run unless the prepared WGS84 source stack is complete. A partial run can overwrite the browser terrain with a much weaker fallback layer.
- If `usgs_coned_sf_2m_south_bay_edge_terrain_wgs84.tif` fails with a TIFF read error, rebuild that focus asset from the raw CoNED source instead of working around the missing tile.
- EX1505's NOAA/NCEI metadata leaves the vertical datum unknown; its apparent CoNED overlap difference is a mixed-source seam, not a safe blanket offset. VDatum's local NAVD88-to-MLLW values are only about 2 cm there, and the paired H13334 check shows EX1505 is sea-level-like rather than ellipsoidal.
- Be careful when warping source rasters with a compound horizontal-plus-vertical CRS to plain EPSG:4326. GDAL can apply a vertical conversion and then drop the vertical label. For the NOAA CUDEM tiles, use `-s_srs EPSG:4326`; for the USGS 2023 San Francisco LiDAR tiles, use `-s_srs EPSG:7131`. These overrides preserve the source NAVD88 height numbers while changing only the horizontal coordinates.
- The raw-sonar VPS artifact paths in `docs/raw-sonar-vps-processing.md` are historical and may have been cleaned up; verify them before assuming candidate grids still exist. As of 2026-07-10 the VPS root disk was full. Local Docker can run `mbari/mbsystem:latest` through amd64 emulation on Apple Silicon, but the image consumes several gigabytes, so check local disk space and remove only the image/files created by the current run afterward.
- Hand-written source cross-check tables go stale silently when a prepared raster is rebuilt. Both B00012 raw-sonar promotions were justified by a CUDEM reading that the next commit's warp fix moved by about 35 m. After any change to the prepared WGS84 rasters or the fusion, run `pnpm paleo-coastlines:promotion-audit` and re-derive any promotion whose drift is non-zero. Do not add a new promotion rationale as hand-typed numbers.
- Run the best-available fusion on this machine only. Several inputs are gated on their raw downloads being present (`active_usgs_coned_sf_2m` checks `USGS_CONED_SF_2M_TIF`, and the 2023 LiDAR and Bay 1 m blocks gate the same way), not on their prepared WGS84 tif. Copying only the prepared work rasters to another host silently drops CoNED, the LiDAR, and the Bay DEM while still clearing `BEST_AVAILABLE_MIN_FUSION_INPUTS`, which produces a much weaker surface that looks like a successful run. `generate_best_available_terrain_asset` now refuses to drop a source that won pixels in the last recorded fusion; override deliberately with `PALEO_ALLOW_SOURCE_LOSS=1`.
- Changing a fusion priority does nothing until the terrain is rebaked. Commit `e648d085` demoted `usgs_coned_sf_2m_farallon_shelf` to rank 15 but committed a fused PNG built before that change, so the Farallon shelf kept the focus clip's rectangle for two weeks. After editing `best_available_fusion_ranked_records` or `terrain_source_kind`, rebuild the fusion and confirm the intended winner in `best_available_full_extent_source_quality.json`.
