# Paleo Coastline Layer

This layer estimates old Bay Area coastlines by tracing elevation lines across a land-plus-seafloor height model.

```text
terrain height map
        +
past sea level estimate
        =
estimated coastline
```

## Current Data

The checked-in browser data now uses three public elevation sources:

| Source | Why it is used |
|---|---|
| USGS DS684 DEM 4, 2 m San Francisco Bar tile | Better local detail around Ocean Beach, the Golden Gate, Marin Headlands, and the San Francisco Bar. This drives the present, 5k, and 10k slices where it has enough depth coverage. |
| USGS/CSMP DS 781 Offshore of San Francisco, 2 m bathymetry | Sharper ocean-floor detail west of San Francisco and the Golden Gate. This is the new high-resolution nearshore seafloor inset. |
| NOAA CRM Vol. 7, 3 arc-second grid | Broader Bay/offshore coverage toward the Farallones. This drives the wide 3D terrain surface and the 20k lowstand because the USGS tile does not reach far enough offshore or deep enough for a full -120 m contour. |
| NOAA ETOPO 2022, 15 arc-second grid | Fallback broad source kept in the raw data references. CRM is now preferred for the app because it is about 5x finer for this region. |

Generated app files:

- `public/data/paleo-coastlines/paleo_coastlines.json`
- `public/data/paleo-coastlines/paleo_coastline_metadata.json`

Local source/work files:

- `data/paleo-coastlines/raw/etopo_2022_sf_bay_coast_15s.nc`
- `data/paleo-coastlines/raw/noaa-crm/crm_vol7_sf_farallones_3as.tif`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-sf/Bathymetry_OffshoreSanFrancisco.zip`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-sf/Bathymetry_OffshoreSanFrancisco.tif`
- `data/paleo-coastlines/raw/usgs-ds684/DEM_4_GeoTIFF.zip`
- `data/paleo-coastlines/raw/usgs-ds684/DEM_4_GeoTIFF/DEM_4_GeoTIFF.tif`
- `data/paleo-coastlines/work/noaa_crm_vol7_contours_raw.geojson`
- `data/paleo-coastlines/work/noaa_crm_vol7_contours_browser.geojson`
- `data/paleo-coastlines/work/usgs_csmp_offshore_sf_contours_raw.geojson`
- `data/paleo-coastlines/work/usgs_csmp_offshore_sf_contours_wgs84.geojson`
- `data/paleo-coastlines/work/usgs_ds684_dem4_contours_raw.geojson`
- `data/paleo-coastlines/work/usgs_ds684_dem4_contours_wgs84.geojson`
- `data/paleo-coastlines/work/noaa_crm_vol7_sf_farallones_terrain_wgs84.tif`
- `data/paleo-coastlines/work/usgs_csmp_offshore_sf_terrain_wgs84.tif`
- `data/paleo-coastlines/work/usgs_ds684_dem4_terrain_wgs84.tif`

## Regenerate

```sh
pnpm paleo-coastlines:generate
```

The script downloads missing source files, runs `gdal_contour`, simplifies the broad NOAA contour lines for browser use, reprojects the USGS output to WGS84, converts NOAA's 0-360 longitude values into normal west-longitude values, filters tiny contour fragments, and writes browser-ready GeoJSON plus browser-ready terrain PNGs.

The important idea is:

```text
use high-resolution USGS/CSMP or DS684 tiles where they cover the contour
otherwise use the broad NOAA offshore grid
        |
        v
one browser GeoJSON file with source labels per line
```

## 3D Terrain View

The Paleo Coastline layer renders a stack of 3D terrain surfaces:

```text
NOAA CRM broad surface
        covers Bay + offshore shelf + Farallon Islands
        |
        v
USGS/CSMP nearshore seafloor inset
        sharper ocean floor west of San Francisco and the Golden Gate
        |
        v
USGS DS684 local inset
        sharper Golden Gate / Ocean Beach / San Francisco Bar detail
        |
        v
transparent water plane
        moves with the year buttons or waterline slider
        |
        v
nearest 5 m probe contour
        bright line showing the closest terrain/water intersection
```

Generated terrain files:

- `public/data/paleo-coastlines/terrain/crm_vol7_sf_farallones_elevation.png`
- `public/data/paleo-coastlines/terrain/crm_vol7_sf_farallones_color.png`
- `public/data/paleo-coastlines/terrain/csmp_offshore_sf_elevation.png`
- `public/data/paleo-coastlines/terrain/csmp_offshore_sf_color.png`
- `public/data/paleo-coastlines/terrain/dem4_elevation.png`
- `public/data/paleo-coastlines/terrain/dem4_color.png`

The vertical scale is exaggerated 4x so the shelf, ridges, and small protruding islands are easier to see. The waterline slider moves the transparent water plane independently of the selected scientific time slice, so you can scrub sea level and watch terrain start to emerge.

The slider also draws the nearest 5 m contour as a bright probe line. This probe is not a dated coastline reconstruction. It is a visual helper for the question: "if the water were at this height, which terrain edge would meet the water?" The probe interval is deliberately 5 m for the first pass so the single browser JSON stays manageable.

## Time Slices

| Slice | Sea level used | Purpose |
|---|---:|---|
| Present | 0 m | Modern comparison line |
| 5k years ago | -3 m | Late Holocene, close to modern shoreline |
| 10k years ago | -56 m | Early Holocene, Bay basin still mostly valley |
| 20k years ago | -120 m | Last-glacial lowstand, coastline far west |

The uncertainty toggle shows extra contour lines around each estimate. These bands only show uncertainty in sea-level height. They do not model erosion, sediment, marsh growth, tectonic motion, or river-channel changes.

## Data Limits

- USGS/CSMP DS 781 is high resolution, but it only covers the nearshore ocean floor west of San Francisco and the Golden Gate. It does not reach all the way to the Farallon Islands.
- USGS DS684 DEM 4 is high resolution, but it is only one tile. It improves the Golden Gate and nearby coast; it is not full Bay-plus-Farallones coverage.
- NOAA CRM is much coarser than the USGS tile, but it covers the offshore shelf and Farallones at about 3 arc-second resolution.
- NOAA ETOPO is coarser still, but remains a fallback global relief source if CRM access changes.
- The script keeps each time slice's uncertainty band on the same elevation source as its main estimate when possible. That avoids mixing a broad offshore estimate with a short local-only uncertainty line.
- The vertical datums differ: USGS/CSMP DS 781 and USGS DS684 are NAVD88; NOAA CRM and ETOPO use broader sea-level/EGM-style references. This first pass treats the sea-level values as approximate relative heights, not as a full local tidal-datum correction.

## Higher-Resolution Next Step

The best next science upgrade is to add more USGS California Seafloor Mapping Program blocks, more USGS DS684 tiles, or the USGS CoNED SF Bay topobathymetric DEM, then mosaic and clip them into one local Bay-plus-offshore elevation model. The rendering layer should not need to change if the generated JSON keeps the same shape.

## Rendering Backend

The layer renders through deck.gl. The app keeps WebGL2 as the default renderer because MapLibre interleaving and many deck.gl geospatial paths are still most reliable there. WebGPU should be tested as a separate dependency change by adding the luma.gl WebGPU adapter and enabling deck.gl `deviceProps` only after confirming the target layers render correctly in the browsers we care about.

Primary references:

- NOAA ETOPO 2022: https://www.ncei.noaa.gov/products/etopo-global-relief-model
- NOAA Coastal Relief Model: https://www.ncei.noaa.gov/products/coastal-relief-model
- USGS Data Series 781 Offshore of San Francisco catalog: https://pubs.usgs.gov/ds/781/OffshoreSanFrancisco/data_catalog_OffshoreSanFrancisco.html
- USGS Data Series 684 DEM GeoTIFF files: https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/
- USGS CoNED SF Bay: https://www.usgs.gov/special-topics/coastal-national-elevation-database-applications-project/science/topobathymetric-0
- USGS SF Bay bathymetry DEM: https://www.usgs.gov/data/high-resolution-1-m-digital-elevation-model-dem-san-francisco-bay-california-created-using
- USGS Atwater/Hedel/Helley sea-level report: https://pubs.usgs.gov/of/1976/0389/report.pdf
- NPS Presidio shoreline reference: https://www.nps.gov/prsf/learn/nature/sea-level-rise-since-the-last-glaciation.htm
