# AGENTS.md

This is the standalone SF paleo-coastline simulator.

Keep this project separate from `cityscope-sf`:

- Do not add police, 311, permits, fire, live feed, or civic dashboard layers here.
- Keep this app focused on 3D terrain, bathymetry, old coastlines, sea-level controls, and source notes.
- Put GIS source files under `data/paleo-coastlines`.
- Put browser-ready generated files under `public/data/paleo-coastlines`.
- Use `pnpm paleo-coastlines:generate` after changing the GIS pipeline.
- Use `pnpm paleo-coastlines:terrain-tiles` after changing only browser terrain tiles.
