# SF Paleo Coastlines

Standalone 3D paleo-coastline simulator for the San Francisco Bay, Golden Gate, offshore shelf, and Farallon Islands.

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
