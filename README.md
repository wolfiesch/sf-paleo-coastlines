# SF Paleo Coastlines

Standalone 3D paleo-coastline simulator for the San Francisco Bay, Golden Gate, offshore shelf, and Farallon Islands.

It uses a broad NOAA seafloor model for the full Bay-to-Farallones view, plus sharper USGS 2 m bathymetry insets where public high-resolution source tiles are available.

This project was split out from `cityscope-sf` because it is a separate research tool. CityScope should stay focused on civic map layers such as police calls, 311 reports, permits, heritage parcels, and live feeds.

## Run

The browser-ready map data is about 3.4 GB and is stored in this repository
with Git LFS. In plain English: reviewers should not need to download source
data again from NOAA or USGS, but their Git client does need Git LFS support so
the checked-out data files are real images/JSON instead of tiny pointer files.

```sh
git lfs install
pnpm install
git lfs pull
pnpm dev
```

### Running without the local data tree

`git lfs pull` is a multi-gigabyte download. To skip it, point the app at a
bucket or CDN that mirrors the `data/paleo-coastlines/...` layout:

```sh
cp .env.example .env.local
# set VITE_DATA_BASE_URL in .env.local
pnpm install
pnpm dev
```

`VITE_DATA_BASE_URL` is prepended to every `/data/...` request (manifest,
slices, waterline probes, terrain tiles, provenance overlays). Leaving it unset
keeps the original behaviour of serving from `public/data`.

A cross-origin bucket must send `Access-Control-Allow-Origin`. Add
`Timing-Allow-Origin` too if you want transfer sizes visible in browser
performance timings.

Setting the variable also makes `vite build` skip the `public/` copy entirely,
because that directory holds nothing but the generated data tree. That is how
CI and a static deploy are expected to build: a few hundred kilobytes of app
bundle, with the data served from object storage.

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
