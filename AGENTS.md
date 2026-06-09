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
