# SF Paleo Coastlines

Standalone 3D paleo-coastline simulator for the San Francisco Bay, Golden Gate, offshore shelf, and Farallon Islands.

It uses a broad NOAA seafloor model for the full Bay-to-Farallones view, plus sharper USGS 2 m bathymetry insets where public high-resolution source tiles are available.

This project was split out from `cityscope-sf` because it is a separate research tool. CityScope should stay focused on civic map layers such as police calls, 311 reports, permits, heritage parcels, and live feeds.

## Run

```sh
pnpm install
pnpm dev
```

## Regenerate GIS Outputs

```sh
pnpm paleo-coastlines:generate
```

The generation script uses local GDAL tools and writes browser-ready terrain and coastline files into `public/data/paleo-coastlines`.

## Data Notes

See `docs/paleo-coastline.md` for the data sources, assumptions, and current limits.

See `docs/public-claim-audit.md` for defensible public wording about how this
project compares with similar Bay Area shoreline, bathymetry, and sea-level
mapping projects.

The paleo-drainage river layer is generated separately; see the "Paleo-Drainage Network" section in `docs/paleo-coastline.md`.

The app defaults to a years-before-present time mode driven by a relative sea-level curve, with a guided tour; see "Time-True Sea Level and Guided Tour" in `docs/paleo-coastline.md`.
