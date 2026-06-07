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

The checked-in browser data now uses two broad elevation sources plus several sharper NOAA and USGS patches:

For the source-by-source quality audit, resolution notes, datum cautions, and next data chases, see `docs/survey-inventory.md`. The browser-readable JSON version is `public/data/paleo-coastlines/survey_inventory.json`. For the high-detail Bay DEM acquisition path, see `docs/usgs-sf-bay-1m-dem.md` and `public/data/paleo-coastlines/usgs_sf_bay_1m_dem_manifest.json`. For the Bay DEM source-survey polygons, see `docs/usgs-sf-bay-source-footprints.md`.

| Source | Why it is used |
|---|---|
| NOAA CRM Vol. 7, 3 arc-second grid | Broad Bay/offshore coverage toward the Farallones. This keeps the full map continuous when detailed survey patches have gaps. |
| NOAA CUDEM 1/9 arc-second topobathymetry | Sharper broad Bay/coast inset built from California topobathymetry tiles. It improves the wide-area terrain texture where tiles exist, but does not fully replace CRM farther offshore. |
| NOAA/NOS H12109, H12110, and H12111 BAG surveys, 1 m and 2 m grids | Very high-resolution Golden Gate approach survey patches. These add sharper local bathymetry from NOAA's hydrographic survey archive, extending the detailed BAG mosaic south and north from the first H12109 patch. They use MLLW rather than the NAVD88-style references used by many other local sources. |
| NOAA/NOS H11965, H13334, W00477, and W00614 variable-resolution BAG surveys | High-resolution Farallon and Greater Farallones survey patches. These are small files with large visual payoff: they add surveyed offshore ridges, banks, island-adjacent bathymetry, and sanctuary-priority patches farther west of the Golden Gate. |
| USGS/CSMP DS 781, 2 m coastal bathymetry blocks | Sharper nearshore ocean-floor detail from Tomales Point and Point Reyes down through Bolinas, San Francisco, Pacifica, Half Moon Bay, and San Gregorio. These blocks improve the coastal shelf, but they do not cover the full offshore region. |
| USGS/CSMP DS 781 acoustic backscatter and seafloor-character blocks | Sonar intensity and interpreted bottom-type textures for the same coastal bathymetry blocks. This makes rocky bottom, sediment patterns, and smoother versus more rugose bottom easier to see on top of the 3D surface. These are visual/context textures, not elevation. |
| USGS OFR 2014-1234 Farallon Escarpment / Rittenburg Bank bathymetry, backscatter, and seafloor character | Sharper offshore multibeam patches west of San Francisco, including a 10 m Farallon Escarpment grid and a 2 m Rittenburg Bank grid. Backscatter adds measured acoustic texture, and seafloor-character maps add interpreted bottom classes for those offshore patches. |
| USGS DS684 DEM 4, 2 m San Francisco Bar tile | Better local detail around Ocean Beach, the Golden Gate, Marin Headlands, and the San Francisco Bar. This drives the present, 5k, and 10k slices where it has enough depth coverage. |
| NOAA ETOPO 2022, 15 arc-second grid | Fallback broad source kept in the raw data references. CRM is now preferred for the app because it is about 5x finer for this region. |

Generated app files:

- `public/data/paleo-coastlines/paleo_manifest.json`
- `public/data/paleo-coastlines/usgs_sf_bay_source_footprints.geojson`
- `public/data/paleo-coastlines/usgs_sf_bay_source_footprints_manifest.json`
- `public/data/paleo-coastlines/slices/*.json`
- `public/data/paleo-coastlines/waterline-probe/*.json`
- `public/data/paleo-coastlines/waterline_probe.json`
- `public/data/paleo-coastlines/paleo_coastlines.json`
- `public/data/paleo-coastlines/paleo_coastline_metadata.json`

Local source/work files:

- `data/paleo-coastlines/raw/etopo_2022_sf_bay_coast_15s.nc`
- `data/paleo-coastlines/raw/noaa-crm/crm_vol7_sf_farallones_3as.tif`
- `data/paleo-coastlines/raw/noaa-cudem/cudem_sf_bay_farallones_1_9as_subset.tif`
- `data/paleo-coastlines/raw/noaa-nos-h12109/H12109_MB_*_MLLW_*.bag`
- `data/paleo-coastlines/raw/noaa-nos-h12110/H12110_MB_*_MLLW_*.bag`
- `data/paleo-coastlines/raw/noaa-nos-h12111/H12111_MB_*_MLLW_*.bag`
- `data/paleo-coastlines/raw/noaa-nos-h11965/H11965_MB_VR_MLLW_1of1.bag`
- `data/paleo-coastlines/raw/noaa-nos-h13334/H13334_MB_VR_MLLW_1of1.bag`
- `data/paleo-coastlines/raw/noaa-nos-w00477/W00477_MB_VR_MLLW_*.bag`
- `data/paleo-coastlines/raw/noaa-nos-w00614/W00614_MB_VR_MLLW_1of1.bag`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/Bathymetry_*.zip`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/Bathymetry_*.tif`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/Backscatter*.zip`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/*Backscatter*.tif`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/SeafloorCharacter_*.zip`
- `data/paleo-coastlines/raw/usgs-csmp-offshore-*/SeafloorCharacter_*.tif`
- `data/paleo-coastlines/raw/usgs-farallon-escarpment/USGS_escarpment_bathy_10m.asc`
- `data/paleo-coastlines/raw/usgs-farallon-escarpment/fe3classnad83.tif`
- `data/paleo-coastlines/raw/usgs-rittenburg-bank/usgs_rittenburgbank_bathy_2m.asc`
- `data/paleo-coastlines/raw/usgs-rittenburg-bank/rb3classnad83.tif`
- `data/paleo-coastlines/raw/usgs-ds684/DEM_4_GeoTIFF.zip`
- `data/paleo-coastlines/raw/usgs-ds684/DEM_4_GeoTIFF/DEM_4_GeoTIFF.tif`
- `data/paleo-coastlines/work/noaa_crm_vol7_contours_raw.geojson`
- `data/paleo-coastlines/work/noaa_crm_vol7_contours_browser.geojson`
- `data/paleo-coastlines/work/noaa_cudem_1_9as_contours_raw.geojson`
- `data/paleo-coastlines/work/noaa_cudem_1_9as_contours_browser.geojson`
- `data/paleo-coastlines/work/noaa_nos_h12109_*_bag_contours_raw.geojson`
- `data/paleo-coastlines/work/noaa_nos_h12109_*_bag_contours_wgs84.geojson`
- `data/paleo-coastlines/work/*_contours_raw.geojson`
- `data/paleo-coastlines/work/*_contours_wgs84.geojson`
- `data/paleo-coastlines/work/usgs_ds684_dem4_contours_raw.geojson`
- `data/paleo-coastlines/work/usgs_ds684_dem4_contours_wgs84.geojson`
- `data/paleo-coastlines/work/noaa_crm_vol7_sf_farallones_terrain_wgs84.tif`
- `data/paleo-coastlines/work/noaa_cudem_1_9as_terrain_wgs84.tif`
- `data/paleo-coastlines/work/noaa_nos_h12109_*_bag_terrain_wgs84.tif`
- `data/paleo-coastlines/work/*_terrain_wgs84.tif`
- `data/paleo-coastlines/work/usgs_ds684_dem4_terrain_wgs84.tif`

## Regenerate

```sh
pnpm paleo-coastlines:generate
```

To rebuild the lightweight source-quality audit without regenerating terrain:

```sh
pnpm paleo-coastlines:inventory
```

To rebuild the USGS 1 m Bay DEM source-survey overlay:

```bash
pnpm paleo-coastlines:bay-source-footprints
```

This layer is a data-quality overlay, not a new terrain surface. In plain English: it shows which source surveys fed the USGS 1 m Bay DEM, including survey year, source agency, sensor type, resolution, datum, and whether interpolation was needed.

The script downloads missing source files, runs `gdal_contour`, simplifies the broad NOAA contour lines for browser use, reprojects the USGS output to WGS84, converts NOAA's 0-360 longitude values into normal west-longitude values, filters tiny contour fragments, and writes browser-ready GeoJSON plus browser-ready terrain PNGs.

The browser GeoJSON is written as compact JSON with coordinates rounded to 6 decimal places. That keeps sub-meter coordinate precision for this area while cutting a lot of unnecessary browser download size.

The app now starts from `paleo_manifest.json`, then loads only the selected time slice from `slices/*.json`, plus the nearest current waterline probe from `waterline-probe/*.json`. The older all-in-one `paleo_coastlines.json` and full `waterline_probe.json` are still generated as compatibility artifacts.

The important idea is:

```text
always keep the broad NOAA contour for continuity
overlay high-resolution USGS contours where survey patches exist
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
NOAA CUDEM 1/9 arc-second inset
        sharper broad Bay/coast topobathymetry where tiles exist
        |
        v
NOAA/NOS H12109/H12110/H12111 BAG patches
        1 m and 2 m Golden Gate approach hydrographic survey detail
        |
        v
NOAA/NOS Farallon-region BAG patches
        variable-resolution H11965, H13334, W00477, and W00614 offshore survey detail
        |
        v
USGS/CSMP coastal seafloor patches
        sharper nearshore ocean floor from Bolinas to Half Moon Bay
        |
        v
USGS Farallon Escarpment / Rittenburg Bank patches
        sharper surveyed ocean floor farther offshore
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
        plus nearby depth contours for shape-reading
        plus a glow around the active wet/dry edge
```

Generated terrain files follow this naming pattern:

- `public/data/paleo-coastlines/terrain/*_elevation.png`
- `public/data/paleo-coastlines/terrain/*_color.png`
- `public/data/paleo-coastlines/terrain/*_relief.png`
- `public/data/paleo-coastlines/terrain/*_composite.png`
- `public/data/paleo-coastlines/terrain/*_sonar.png`
- `public/data/paleo-coastlines/terrain/*_hybrid.png`
- `public/data/paleo-coastlines/terrain/*_character.png`

The current high-resolution CSMP terrain stems are `csmp_offshore_tomales_point`, `csmp_offshore_point_reyes`, `csmp_offshore_bolinas`, `csmp_offshore_sf`, `csmp_offshore_pacifica`, `csmp_offshore_half_moon_bay`, and `csmp_offshore_san_gregorio`.
- `public/data/paleo-coastlines/terrain/dem4_relief.png`
- `public/data/paleo-coastlines/terrain/dem4_composite.png`

The `*_elevation.png` files encode height in RGB, not grayscale. In plain English: each pixel gets three color channels to store the height number, which preserves much finer vertical detail than a single 0-255 grayscale value.

The `*_relief.png` files blend the depth color ramp with DEM-derived light and shadow. They make ridges, banks, channels, and small seafloor texture easier to see. The original `*_color.png` files remain available through the surface-style control.

The `*_composite.png` files power the `Survey` surface style. They combine depth color, shaded relief, local slope, roughness, and a simple ridge-or-hollow signal calculated from neighboring height pixels. In plain English: this is still the same terrain height data, but the texture makes small banks, channels, scarps, rocky patches, and newly exposed ridges easier to read at a glance.

The composite texture bake now reads the DEM at two scales: very nearby pixels for fine bumps and a wider neighborhood for broader banks, ridges, and channels. In plain English: the app is not inventing more depth measurements, but it is doing a better job of showing the shape that already exists in the data.

The `*_sonar.png` files are generated from USGS/CSMP acoustic backscatter where that data exists. In plain English: backscatter is how strongly the seafloor reflected the survey sound signal. Hard rock, sand, mud, and rough bottom can show up differently, so this gives the surface a much more detailed "ocean survey" look. It does not change the 3D height shape; the height still comes from the bathymetry DEM. The app keeps `Sonar` as a separate surface style and falls back to shaded relief for terrain sources without backscatter.

The `*_hybrid.png` files are the default `Hybrid` surface style for USGS/CSMP blocks with acoustic backscatter. They bake sonar intensity on top of the Survey texture. In plain English: where sonar exists, Hybrid shows both measured seafloor reflectivity and DEM-derived shape detail; where sonar does not exist, the app falls back to Survey so the map remains continuous.

The `*_character.png` files power the `Bottom` surface style for CSMP coastal blocks plus the Farallon Escarpment and Rittenburg Bank OFR 2014-1234 patches. They use interpreted USGS seafloor-character classes: `1` means smoother sediment, `2` means mixed sediment and rock, and `3` means more rugose rock or boulder-like bottom. In plain English: this is a mapped bottom-type layer draped over the 3D terrain. It does not change the actual height mesh.

The vertical scale is exaggerated 4x so the shelf, ridges, and small protruding islands are easier to see. The waterline slider moves the transparent water plane independently of the selected scientific time slice, so you can scrub sea level and watch terrain start to emerge.

The terrain mesh control changes deck.gl's `meshMaxError` setting. In plain English: lower values keep more small bumps and ridges from the elevation image, while higher values trade some detail for speed. The default `Survey` setting now uses very tight mesh error values for the NOAA Area A 1 m Bay mosaic, the USGS SF Bay 1 m DEM inset, the NOAA BAG patches, and the USGS/CSMP/Farallon multibeam patches. This is intentionally heavier because the current sprint prioritizes detail over speed.

The generated browser terrain images are intentionally larger than the first MVP while staying inside common WebGL texture limits. The best-available fused surface is exported at 8192 pixels wide, the NOAA Area A 1 m mosaic at 5120 pixels wide, the individual NOAA Area A source-survey tiles at 3072 pixels wide, and the USGS SF Bay 1 m DEM insets at 4096 pixels wide when present. In plain English: we are preserving more of the raw DEM detail before the browser turns it into a 3D surface, but keeping each single image small enough for the browser to draw reliably.

The scene control changes only how the terrain is drawn. `Study` is calmer for reading labels and sources, `Relief` increases height, light, and shadow, and `Emerge` makes the active waterline and newly exposed terrain more obvious. In plain English: this is like changing the lighting and vertical emphasis on a physical model. It does not change the sea-level estimate or the source elevation data.

The slider also draws the nearest 5 m contour as a bright waterline and nearby 5 m contours as thinner depth lines. These lines are not dated coastline reconstructions. They are visual helpers for the question: "if the water were at this height, which terrain edge would meet the water, and what nearby seafloor shape surrounds it?" The probe interval is deliberately 5 m for the first pass so the browser payload stays manageable.

The terrain surface also uses a shader-based reveal tint near the active waterline. In plain English: terrain just above the current scrubbed water level gets a warm exposed-land tint, terrain just below the level gets a cool submerged tint, and the source terrain texture stays underneath. The active waterline also gets a soft glow so the exact wet/dry edge remains readable over busy survey textures. These are visual reading aids, not added erosion, sediment, vegetation, or hydrodynamic models.

High-resolution survey insets now fade slightly at their outer bounds. In plain English: this softens the visible edge where a detailed NOAA or USGS survey patch meets the broader background DEM. It does not invent new seafloor data outside the survey footprint; it only makes the transition easier to read.

## Time Slices

| Slice | Sea level used | Purpose |
|---|---:|---|
| Present | 0 m | Modern comparison line |
| 5k years ago | -3 m | Late Holocene, close to modern shoreline |
| 10k years ago | -56 m | Early Holocene, Bay basin still mostly valley |
| 20k years ago | -120 m | Last-glacial lowstand, coastline far west |

The uncertainty toggle shows extra contour lines around each estimate. These bands only show uncertainty in sea-level height. They do not model erosion, sediment, marsh growth, tectonic motion, or river-channel changes.

## Data Limits

- USGS/CSMP DS 781 is high resolution, but the blocks are mostly nearshore and state-water focused. The app now uses a longer chain of those blocks, but they still do not form one seamless full-ocean DEM.
- NOAA/NOS Farallon-region BAG surveys improve island-adjacent and sanctuary-priority offshore bathymetry, but they are still survey patches. In plain English: the Farallones view is becoming much more interesting, but we should still expect visible data-footprint edges where detailed surveys start and stop.
- NOAA OCM Area B/C Bay survey metadata exists and would likely help north/south Bay detail, but the official InPort records currently expose no public downloadable distribution. In plain English: it is a real lead, but not an actionable app input until we find a working NOAA/NCEI download path.
- USGS OFR 2014-1234 improves the Farallon Escarpment and Rittenburg Bank areas with bathymetry, backscatter, and seafloor character, but it is still patch coverage, not full Farallones-region coverage.
- USGS DS684 DEM 4 is high resolution, but it is only one tile. It improves the Golden Gate and nearby coast; it is not full Bay-plus-Farallones coverage.
- NOAA/NOS BAG surveys add very detailed Golden Gate and Farallon-region bathymetry, but they use MLLW. In plain English: they are excellent shape data, but we should not overclaim exact sea-level alignment until we do a proper local datum conversion.
- NOAA CUDEM is much sharper than CRM where California 1/9 arc-second tiles exist, but the clipped source still has tile limits and should be treated as a broad inset, not a complete far-offshore survey.
- NOAA CRM is much coarser than the USGS tile, but it covers the offshore shelf and Farallones at about 3 arc-second resolution.
- NOAA ETOPO is coarser still, but remains a fallback global relief source if CRM access changes.
- The script now keeps the broad NOAA contour for continuity and adds high-resolution USGS contour pieces where available. This avoids losing the full shoreline just because a detailed patch is incomplete.
- The vertical datums differ: NOAA/NOS BAG surveys use MLLW; NOAA CUDEM, USGS/CSMP DS 781, USGS OFR 2014-1234, and USGS DS684 are NAVD88-style sources; NOAA CRM and ETOPO use broader sea-level/EGM-style references. This first pass treats the sea-level values as approximate relative heights, not as a full local tidal-datum correction.

## Higher-Resolution Next Step

The best next science upgrade is to keep expanding the NOAA NOS BAG mosaic into more Bay, Golden Gate, Gulf of the Farallones, and priority offshore survey areas. In plain English: the app now has a multi-survey BAG corridor around the Golden Gate; the next leap is a wider BAG survey mosaic plus local vertical datum correction.

## Rendering Backend

The layer renders through deck.gl. The app keeps WebGL2 as the default renderer because MapLibre interleaving and many deck.gl geospatial paths are still most reliable there. WebGPU should be tested as a separate dependency change by adding the luma.gl WebGPU adapter and enabling deck.gl `deviceProps` only after confirming the target layers render correctly in the browsers we care about.

Primary references:

- NOAA ETOPO 2022: https://www.ncei.noaa.gov/products/etopo-global-relief-model
- NOAA Coastal Relief Model: https://www.ncei.noaa.gov/products/coastal-relief-model
- NOAA CUDEM 1/9 arc-second topobathymetry bulk tiles: https://coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/
- NOAA NOS hydrographic survey products: https://www.ncei.noaa.gov/products/nos-hydrographic-survey
- NOAA NOS H12109 hydrographic survey report and BAG downloads: https://www.ngdc.noaa.gov/nos/H12001-H14000/H12109.html
- NOAA NOS H12110 hydrographic survey report and BAG downloads: https://www.ngdc.noaa.gov/nos/H12001-H14000/H12110.html
- NOAA NOS H12111 hydrographic survey report and BAG downloads: https://www.ngdc.noaa.gov/nos/H12001-H14000/H12111.html
- NOAA NOS H11965 hydrographic survey report and BAG download: https://www.ngdc.noaa.gov/nos/H10001-H12000/H11965.html
- NOAA NOS H13334 hydrographic survey report and BAG download: https://www.ngdc.noaa.gov/nos/H12001-H14000/H13334.html
- NOAA NOS W00477 hydrographic survey report and BAG downloads: https://www.ngdc.noaa.gov/nos/W00001-W02000/W00477.html
- NOAA NOS W00614 hydrographic survey report and BAG download: https://www.ngdc.noaa.gov/nos/W00001-W02000/W00614.html
- USGS DS 781 California State Waters data catalog: https://pubs.usgs.gov/ds/781/
- USGS Data Series 781 Offshore Tomales Point catalog: https://pubs.usgs.gov/ds/781/OffshoreTomalesPoint/data_catalog_OffshoreTomalesPoint.html
- USGS Data Series 781 Offshore Point Reyes catalog: https://pubs.usgs.gov/ds/781/OffshorePointReyes/data_catalog_OffshorePointReyes.html
- USGS Data Series 781 Offshore of Bolinas catalog: https://pubs.usgs.gov/ds/781/OffshoreBolinas/data_catalog_OffshoreBolinas.html
- USGS Data Series 781 Offshore of San Francisco catalog: https://pubs.usgs.gov/ds/781/OffshoreSanFrancisco/data_catalog_OffshoreSanFrancisco.html
- USGS Data Series 781 Offshore of Pacifica catalog: https://pubs.usgs.gov/ds/781/OffshorePacifica/data_catalog_OffshorePacifica.html
- USGS Data Series 781 Offshore of Half Moon Bay catalog: https://pubs.usgs.gov/ds/781/OffshoreHalfMoonBay/data_catalog_OffshoreHalfMoonBay.html
- USGS Data Series 781 Offshore of San Gregorio catalog: https://pubs.usgs.gov/ds/781/OffshoreSanGregorio/data_catalog_OffshoreSanGregorio.html
- USGS OFR 2014-1234 Farallon Escarpment and Rittenburg Bank: https://pubs.usgs.gov/of/2014/1234/datacatalog.html
- USGS Data Series 684 DEM GeoTIFF files: https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/
- USGS CoNED SF Bay: https://www.usgs.gov/special-topics/coastal-national-elevation-database-applications-project/science/topobathymetric-0
- USGS SF Bay bathymetry DEM: https://www.usgs.gov/data/high-resolution-1-m-digital-elevation-model-dem-san-francisco-bay-california-created-using
- USGS Atwater/Hedel/Helley sea-level report: https://pubs.usgs.gov/of/1976/0389/report.pdf
- NPS Presidio shoreline reference: https://www.nps.gov/prsf/learn/nature/sea-level-rise-since-the-last-glaciation.htm
