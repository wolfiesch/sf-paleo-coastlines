#!/usr/bin/env python3
"""Generate first-pass paleo-coastline contours from public elevation grids.

The browser layer uses NOAA CRM Vol. 7 for broad SF/Farallones coverage and
high-resolution USGS/CSMP bathymetry where local tiles cover the requested
sea-level contour.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "paleo-coastlines" / "raw"
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work"
PUBLIC_DIR = ROOT / "public" / "data" / "paleo-coastlines"
TERRAIN_PUBLIC_DIR = PUBLIC_DIR / "terrain"
SLICES_PUBLIC_DIR = PUBLIC_DIR / "slices"
WATERLINE_PROBE_PUBLIC_DIR = PUBLIC_DIR / "waterline-probe"

RAW_NETCDF = RAW_DIR / "etopo_2022_sf_bay_coast_15s.nc"
CONTOURS_RAW = WORK_DIR / "etopo_2022_contours_raw.geojson"
CRM_DIR = RAW_DIR / "noaa-crm"
CRM_TIF = CRM_DIR / "crm_vol7_sf_farallones_3as.tif"
CRM_CONTOURS_RAW = WORK_DIR / "noaa_crm_vol7_contours_raw.geojson"
CRM_CONTOURS_BROWSER = WORK_DIR / "noaa_crm_vol7_contours_browser.geojson"
CRM_TERRAIN_WGS84 = WORK_DIR / "noaa_crm_vol7_sf_farallones_terrain_wgs84.tif"
CRM_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_elevation.png"
CRM_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_color.png"
CRM_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_relief.png"
CRM_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_composite.png"
DS684_DIR = RAW_DIR / "usgs-ds684"
DS684_ZIP = DS684_DIR / "DEM_4_GeoTIFF.zip"
DS684_TIF = DS684_DIR / "DEM_4_GeoTIFF" / "DEM_4_GeoTIFF.tif"
DS684_CONTOURS_RAW = WORK_DIR / "usgs_ds684_dem4_contours_raw.geojson"
DS684_CONTOURS_WGS84 = WORK_DIR / "usgs_ds684_dem4_contours_wgs84.geojson"
DS684_TERRAIN_WGS84 = WORK_DIR / "usgs_ds684_dem4_terrain_wgs84.tif"
DS684_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "dem4_elevation.png"
DS684_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "dem4_color.png"
DS684_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "dem4_relief.png"
DS684_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "dem4_composite.png"
ETOPO_TERRAIN_WGS84 = WORK_DIR / "etopo_2022_bay_farallones_terrain_wgs84.tif"
ETOPO_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_elevation.png"
ETOPO_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_color.png"
ETOPO_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_relief.png"
ETOPO_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_composite.png"
CRM_TERRAIN_SIZE = 1536
DS684_TERRAIN_SIZE = 768
DS684_TERRAIN_MIN_M = -130.0
DS684_TERRAIN_MAX_M = 400.0
ETOPO_TERRAIN_MIN_M = -150.0
ETOPO_TERRAIN_MAX_M = 1000.0
CRM_TERRAIN_MIN_M = -150.0
CRM_TERRAIN_MAX_M = 1000.0
TERRAIN_VERTICAL_EXAGGERATION = 4.0
TERRAIN_COLOR_STOPS = [
    (-1000.0, (18, 8, 48)),
    (-700.0, (29, 21, 92)),
    (-400.0, (42, 39, 126)),
    (-130.0, (52, 20, 101)),
    (-100.0, (33, 70, 170)),
    (-70.0, (20, 136, 206)),
    (-45.0, (24, 186, 171)),
    (-20.0, (120, 209, 82)),
    (-8.0, (220, 210, 55)),
    (0.0, (224, 91, 34)),
    (4.0, (176, 176, 176)),
    (80.0, (214, 214, 214)),
    (250.0, (244, 244, 244)),
    (400.0, (255, 255, 255)),
]

# Bay + coast + offshore shelf toward the Farallones.
BBOX = {
    "west": -124.0,
    "south": 37.0,
    "east": -121.5,
    "north": 38.5,
}

ERDDAP_URL = (
    "https://oceanwatch.pifsc.noaa.gov/erddap/griddap/"
    "ETOPO_2022_v1_15s.nc?z%5B(37.0):(38.5)%5D%5B(236.0):(238.5)%5D"
)

CRM_VOL7_REMOTE = 'NETCDF:"https://www.ngdc.noaa.gov/thredds/dodsC/crm/crm_vol7.nc":z'
CSMP_OFFSHORE_SF_URL = "https://pubs.usgs.gov/ds/781/OffshoreSanFrancisco/data/Bathymetry_OffshoreSanFrancisco.zip"
DS684_DEM4_URL = "https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/DEM_4_GeoTIFF.zip"

BATHYMETRY_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": "usgs_csmp_offshore_tomales_point_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore Tomales Point bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore Tomales Point 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshoreTomalesPoint/data_catalog_OffshoreTomalesPoint.html",
        "role": "High-resolution nearshore bathymetry north of Point Reyes.",
        "folder": "usgs-csmp-offshore-tomales-point",
        "zipName": "Bathymetry_OffshoreTomalesPoint.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshoreTomalesPoint/data/Bathymetry_OffshoreTomalesPoint.zip",
        "datasetName": "Bathymetry_OffshoreTomalesPoint.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_OffshoreTomalesPoint.zip",
            "BackscatterB_7125_OffshoreTomalesPoint.zip",
            "BackscatterC_Swath_OffshoreTomalesPoint.zip",
            "BackscatterD_USGS_OffshoreTomalesPoint.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshoreTomalesPoint.zip",
        "characterDatasetName": "SeafloorCharacter_OffshoreTomalesPoint.tif",
        "terrainStem": "csmp_offshore_tomales_point",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS bathymetry, backscatter, and seafloor-character inset north of Point Reyes around Tomales Point.",
    },
    {
        "sourceId": "usgs_csmp_offshore_point_reyes_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore Point Reyes bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore Point Reyes and Vicinity 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshorePointReyes/data_catalog_OffshorePointReyes.html",
        "role": "High-resolution nearshore bathymetry around Point Reyes and Drakes Bay.",
        "folder": "usgs-csmp-offshore-point-reyes",
        "zipName": "Bathymetry_OffshorePointReyes.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshorePointReyes/data/Bathymetry_OffshorePointReyes.zip",
        "datasetName": "Bathymetry_OffshorePointReyes.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_OffshorePointReyes.zip",
            "BackscatterB_Swath_OffshorePointReyes.zip",
            "BackscatterC_7125_OffshorePointReyes.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshorePointReyes.zip",
        "characterDatasetName": "SeafloorCharacter_OffshorePointReyes.tif",
        "terrainStem": "csmp_offshore_point_reyes",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS bathymetry, backscatter, and seafloor-character inset around Point Reyes and Drakes Bay.",
    },
    {
        "sourceId": "usgs_csmp_offshore_bolinas_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore of Bolinas bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore of Bolinas 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshoreBolinas/data_catalog_OffshoreBolinas.html",
        "role": "High-resolution nearshore bathymetry north of the Golden Gate.",
        "folder": "usgs-csmp-offshore-bolinas",
        "zipName": "Bathymetry_OffshoreBolinas.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshoreBolinas/data/Bathymetry_OffshoreBolinas.zip",
        "datasetName": "Bathymetry_OffshoreBolinas.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_2004_OffshoreBolinas.zip",
            "BackscatterB_8101_2007_OffshoreBolinas.zip",
            "BackscatterC_7125_OffshoreBolinas.zip",
            "BackscatterD_Snippets_OffshoreBolinas.zip",
            "BackscatterE_Swath_OffshoreBolinas.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshoreBolinas.zip",
        "characterDatasetName": "SeafloorCharacter_OffshoreBolinas.tif",
        "terrainStem": "csmp_offshore_bolinas",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS nearshore bathymetry north of the Golden Gate around Bolinas and Stinson Beach.",
    },
    {
        "sourceId": "usgs_csmp_offshore_sf_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore of San Francisco bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore of San Francisco 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshoreSanFrancisco/data_catalog_OffshoreSanFrancisco.html",
        "role": "High-resolution nearshore bathymetry for the ocean floor west of San Francisco and the Golden Gate.",
        "folder": "usgs-csmp-offshore-sf",
        "zipName": "Bathymetry_OffshoreSanFrancisco.zip",
        "zipUrl": CSMP_OFFSHORE_SF_URL,
        "datasetName": "Bathymetry_OffshoreSanFrancisco.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_2004_OffshoreSanFrancisco.zip",
            "BackscatterB_8101_2007_OffshoreSanFrancisco.zip",
            "BackscatterC_8101_2008_OffshoreSanFrancisco.zip",
            "BackscatterD_7125_2006_OffshoreSanFrancisco.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshoreSanFrancisco.zip",
        "characterDatasetName": "SeafloorCharacter_OffshoreSanFrancisco.tif",
        "terrainStem": "csmp_offshore_sf",
        "terrainSize": 2048,
        "terrainMinimum": -120.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS nearshore bathymetry inset for the ocean floor west of San Francisco and the Golden Gate.",
    },
    {
        "sourceId": "usgs_csmp_offshore_pacifica_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore of Pacifica bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore of Pacifica 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshorePacifica/data_catalog_OffshorePacifica.html",
        "role": "High-resolution nearshore bathymetry south of San Francisco.",
        "folder": "usgs-csmp-offshore-pacifica",
        "zipName": "Bathymetry_OffshorePacifica.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshorePacifica/data/Bathymetry_OffshorePacifica.zip",
        "datasetName": "Bathymetry_OffshorePacifica.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_OffshorePacifica.zip",
            "BackscatterB_7125_OffshorePacifica.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshorePacifica.zip",
        "characterDatasetName": "SeafloorCharacter_OffshorePacifica.tif",
        "terrainStem": "csmp_offshore_pacifica",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS nearshore bathymetry south of San Francisco around Pacifica.",
    },
    {
        "sourceId": "usgs_csmp_offshore_half_moon_bay_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore of Half Moon Bay bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore of Half Moon Bay 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshoreHalfMoonBay/data_catalog_OffshoreHalfMoonBay.html",
        "role": "High-resolution nearshore bathymetry south of Pacifica.",
        "folder": "usgs-csmp-offshore-half-moon-bay",
        "zipName": "Bathymetry_OffshoreHalfMoonBay.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshoreHalfMoonBay/data/Bathymetry_OffshoreHalfMoonBay.zip",
        "datasetName": "Bathymetry_OffshoreHalfMoonBay.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_OffshoreHalfMoonBay.zip",
            "BackscatterB_7125_OffshoreHalfMoonBay.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshoreHalfMoonBay.zip",
        "characterDatasetName": "SeafloorCharacter_OffshoreHalfMoonBay.tif",
        "terrainStem": "csmp_offshore_half_moon_bay",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS nearshore bathymetry farther south around Half Moon Bay.",
    },
    {
        "sourceId": "usgs_csmp_offshore_san_gregorio_2m",
        "sourceLabel": "USGS/CSMP DS 781, 2 m Offshore of San Gregorio bathymetry",
        "sourceName": "USGS Data Series 781 / California Seafloor Mapping Program, Offshore of San Gregorio 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/ds/781/OffshoreSanGregorio/data_catalog_OffshoreSanGregorio.html",
        "role": "High-resolution nearshore bathymetry south of Half Moon Bay.",
        "folder": "usgs-csmp-offshore-san-gregorio",
        "zipName": "Bathymetry_OffshoreSanGregorio.zip",
        "zipUrl": "https://pubs.usgs.gov/ds/781/OffshoreSanGregorio/data/Bathymetry_OffshoreSanGregorio.zip",
        "datasetName": "Bathymetry_OffshoreSanGregorio.tif",
        "backscatterZipNames": [
            "BackscatterA_8101_OffshoreSanGregorio.zip",
            "BackscatterB_7125_OffshoreSanGregorio.zip",
        ],
        "characterZipName": "SeafloorCharacter_OffshoreSanGregorio.zip",
        "characterDatasetName": "SeafloorCharacter_OffshoreSanGregorio.tif",
        "terrainStem": "csmp_offshore_san_gregorio",
        "terrainSize": 1536,
        "terrainMinimum": -130.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -115.0,
        "contourMaximum": 1.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.003,
        "note": "High-resolution 2 m CSMP/USGS bathymetry, backscatter, and seafloor-character inset south of Half Moon Bay around San Gregorio.",
    },
    {
        "sourceId": "usgs_farallon_escarpment_10m",
        "sourceLabel": "USGS OFR 2014-1234, 10 m Upper Farallon Escarpment bathymetry",
        "sourceName": "USGS OFR 2014-1234, Upper Farallon Escarpment 10 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/of/2014/1234/datacatalog.html",
        "role": "Higher-resolution offshore bathymetry for the outer shelf and upper Farallon Escarpment.",
        "folder": "usgs-farallon-escarpment",
        "zipName": "USGS_escarpment_bathy_10m.zip",
        "zipUrl": "https://pubs.usgs.gov/of/2014/1234/data/USGS_escarpment_bathy_10m.zip",
        "datasetName": "USGS_escarpment_bathy_10m.asc",
        "backscatterZipNames": [
            "USGS_escarpment_back_10m.zip",
        ],
        "backscatterSourceSrs": "EPSG:26910",
        "characterZipName": "fe3classnad83.zip",
        "characterDatasetName": "fe3classnad83.tif",
        "characterSourceSrs": "EPSG:26910",
        "terrainStem": "usgs_farallon_escarpment",
        "terrainSize": 1024,
        "terrainMinimum": -950.0,
        "terrainMaximum": -80.0,
        "contourMinimum": -950.0,
        "contourMaximum": -80.0,
        "contourSimplify": 20,
        "minDegreesLength": 0.004,
        "note": "USGS 10 m multibeam bathymetry patch for the outer shelf and upper Farallon Escarpment.",
    },
    {
        "sourceId": "usgs_rittenburg_bank_2m",
        "sourceLabel": "USGS OFR 2014-1234, 2 m Rittenburg Bank bathymetry",
        "sourceName": "USGS OFR 2014-1234, Rittenburg Bank 2 m bathymetry",
        "sourceUrl": "https://pubs.usgs.gov/of/2014/1234/datacatalog.html",
        "role": "Higher-resolution offshore bathymetry for Rittenburg Bank near the Farallon region.",
        "folder": "usgs-rittenburg-bank",
        "zipName": "USGS_rittenburgbank_bathy_2m.zip",
        "zipUrl": "https://pubs.usgs.gov/of/2014/1234/data/USGS_rittenburgbank_bathy_2m.zip",
        "datasetName": "usgs_rittenburgbank_bathy_2m.asc",
        "backscatterZipNames": [
            "USGS_rittenburg_back_2m.zip",
        ],
        "backscatterDatasetNames": {
            "USGS_rittenburg_back_2m.zip": "USGS_rittenburg_back.tif",
        },
        "backscatterSourceSrs": "EPSG:26910",
        "characterZipName": "rb3classnad83.zip",
        "characterDatasetName": "rb3classnad83.tif",
        "characterSourceSrs": "EPSG:26910",
        "terrainStem": "usgs_rittenburg_bank",
        "terrainSize": 1024,
        "terrainMinimum": -130.0,
        "terrainMaximum": -40.0,
        "contourMinimum": -130.0,
        "contourMaximum": -40.0,
        "contourSimplify": 12,
        "minDegreesLength": 0.003,
        "note": "USGS 2 m multibeam bathymetry patch for Rittenburg Bank near the Farallon region.",
    },
]

TIME_SLICES = [
    {
        "id": "present",
        "label": "Present",
        "yearsBeforePresent": 0,
        "seaLevelMeters": 0.0,
        "uncertaintyMeters": 1.0,
        "summary": "Modern comparison contour from the best available local topobathymetry.",
    },
    {
        "id": "5k_years_ago",
        "label": "5k years ago",
        "yearsBeforePresent": 5000,
        "seaLevelMeters": -3.0,
        "uncertaintyMeters": 3.0,
        "summary": "Late Holocene estimate near modern sea level; local marsh, sediment, and datum effects matter.",
    },
    {
        "id": "10k_years_ago",
        "label": "10k years ago",
        "yearsBeforePresent": 10000,
        "seaLevelMeters": -56.0,
        "uncertaintyMeters": 8.0,
        "summary": "Early Holocene estimate from SF Bay sea-level literature; the Bay basin was still largely a valley.",
    },
    {
        "id": "20k_years_ago",
        "label": "20k years ago",
        "yearsBeforePresent": 20000,
        "seaLevelMeters": -120.0,
        "uncertaintyMeters": 15.0,
        "summary": "Approximate last-glacial lowstand; the open-ocean coast was far west of today's SF shoreline.",
    },
]

# Extra contours used by the browser waterline scrubber. These are not dated
# reconstructions; they are a visual probe for "what terrain is above water
# if the sea surface is here?"
WATERLINE_PROBE_LEVELS = [float(level) for level in range(-120, 5, 5)]

SOURCES = [
    {
        "name": "NOAA ETOPO 2022 15 arc-second Global Relief Model",
        "url": "https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        "role": "Fallback broad land and seafloor elevation source.",
    },
    {
        "name": "NOAA NCEI Coastal Relief Model Vol. 7, 3 arc-second",
        "url": "https://www.ngdc.noaa.gov/thredds/catalog/crm/catalog.html",
        "role": "Broad SF-to-Farallones elevation source for offshore shelf terrain and contours.",
    },
    *[
        {
            "name": block["sourceName"],
            "url": block["sourceUrl"],
            "role": block["role"],
        }
        for block in BATHYMETRY_BLOCKS
    ],
    {
        "name": "USGS Data Series 684 DEM 4, San Francisco Bar 2 m GeoTIFF",
        "url": "https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/",
        "role": "Higher-resolution topobathymetric surface for Ocean Beach, Golden Gate, Marin Headlands, and the San Francisco Bar.",
    },
    {
        "name": "USGS CoNED San Francisco Bay 2 m topobathymetric DEM",
        "url": "https://www.usgs.gov/special-topics/coastal-national-elevation-database-applications-project/science/topobathymetric-0",
        "role": "Recommended higher-resolution replacement DEM for later local refinement.",
    },
    {
        "name": "USGS Atwater, Hedel, and Helley sea-level reconstruction",
        "url": "https://pubs.usgs.gov/of/1976/0389/report.pdf",
        "role": "Local sea-level history reference for early Holocene SF Bay estimates.",
    },
    {
        "name": "NPS Presidio sea-level-rise since last glaciation map",
        "url": "https://www.nps.gov/prsf/learn/nature/sea-level-rise-since-the-last-glaciation.htm",
        "role": "Visual reference for Golden Gate shorelines since the last glaciation.",
    },
]


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Missing required tool: {name}")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def download_url(url: str, target: Path) -> None:
    if target.exists():
        print(f"Using existing source file: {target}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=target.suffix) as tmp:
        tmp_path = Path(tmp.name)

    print(f"Downloading {url} to {target}")
    try:
        urllib.request.urlretrieve(url, tmp_path)
        tmp_path.replace(target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def download_raw_netcdf() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download_url(ERDDAP_URL, RAW_NETCDF)


def download_noaa_crm_vol7_subset() -> None:
    if CRM_TIF.exists():
        print(f"Using existing source file: {CRM_TIF}")
        return

    CRM_DIR.mkdir(parents=True, exist_ok=True)
    run([
        "gdal_translate",
        "-q",
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=DEFLATE",
        "-projwin",
        str(BBOX["west"]),
        str(BBOX["north"]),
        str(BBOX["east"]),
        str(BBOX["south"]),
        CRM_VOL7_REMOTE,
        str(CRM_TIF),
    ])


def download_usgs_ds684_dem4() -> None:
    download_url(DS684_DEM4_URL, DS684_ZIP)
    if DS684_TIF.exists():
        return
    run(["unzip", "-o", str(DS684_ZIP), "-d", str(DS684_DIR)])


def bathymetry_block_dir(block: dict[str, Any]) -> Path:
    return RAW_DIR / str(block["folder"])


def bathymetry_block_zip(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["zipName"])


def bathymetry_block_dataset(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["datasetName"])


def bathymetry_block_contours_raw(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_raw.geojson"


def bathymetry_block_contours_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_wgs84.geojson"


def bathymetry_block_terrain_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_terrain_wgs84.tif"


def bathymetry_block_elevation_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_elevation.png"


def bathymetry_block_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_color.png"


def bathymetry_block_relief_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_relief.png"


def bathymetry_block_composite_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_composite.png"


def bathymetry_block_sonar_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_sonar.png"


def bathymetry_block_hybrid_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_hybrid.png"


def bathymetry_block_character_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_character.png"


def bathymetry_block_backscatter_zip(block: dict[str, Any], zip_name: str) -> Path:
    return bathymetry_block_dir(block) / zip_name


def bathymetry_block_backscatter_dataset(block: dict[str, Any], zip_name: str) -> Path:
    dataset_name = block.get("backscatterDatasetNames", {}).get(zip_name, zip_name.replace(".zip", ".tif"))
    return bathymetry_block_dir(block) / str(dataset_name)


def bathymetry_block_backscatter_url(block: dict[str, Any], zip_name: str) -> str:
    return f"{str(block['sourceUrl']).rsplit('/', 1)[0]}/data/{zip_name}"


def bathymetry_block_backscatter_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_backscatter_wgs84.tif"


def bathymetry_block_character_zip(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["characterZipName"])


def bathymetry_block_character_dataset(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["characterDatasetName"])


def bathymetry_block_character_url(block: dict[str, Any]) -> str:
    return f"{str(block['sourceUrl']).rsplit('/', 1)[0]}/data/{block['characterZipName']}"


def bathymetry_block_character_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_character_wgs84.tif"


def download_bathymetry_block(block: dict[str, Any]) -> None:
    download_url(str(block["zipUrl"]), bathymetry_block_zip(block))
    if not bathymetry_block_dataset(block).exists():
        run(["unzip", "-o", str(bathymetry_block_zip(block)), "-d", str(bathymetry_block_dir(block))])

    for zip_name in block.get("backscatterZipNames", []):
        download_url(bathymetry_block_backscatter_url(block, str(zip_name)), bathymetry_block_backscatter_zip(block, str(zip_name)))
        if not bathymetry_block_backscatter_dataset(block, str(zip_name)).exists():
            run(["unzip", "-o", str(bathymetry_block_backscatter_zip(block, str(zip_name))), "-d", str(bathymetry_block_dir(block))])

    if block.get("characterZipName"):
        download_url(bathymetry_block_character_url(block), bathymetry_block_character_zip(block))
        if not bathymetry_block_character_dataset(block).exists():
            run(["unzip", "-o", str(bathymetry_block_character_zip(block)), "-d", str(bathymetry_block_dir(block))])


def download_bathymetry_blocks() -> None:
    for block in BATHYMETRY_BLOCKS:
        download_bathymetry_block(block)


def contour_levels() -> list[float]:
    levels: set[float] = set()
    for item in TIME_SLICES:
        center = float(item["seaLevelMeters"])
        spread = float(item["uncertaintyMeters"])
        levels.add(center)
        levels.add(center - spread)
        levels.add(center + spread)
    levels.update(WATERLINE_PROBE_LEVELS)
    return sorted(levels)


def generate_contours() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    levels = [str(level) for level in contour_levels()]
    run([
        "gdal_contour",
        "-q",
        "-a",
        "elevation_m",
        "-fl",
        *levels,
        str(CRM_TIF),
        str(CRM_CONTOURS_RAW),
    ])
    run([
        "ogr2ogr",
        "-f",
        "GeoJSON",
        "-simplify",
        "0.0008",
        str(CRM_CONTOURS_BROWSER),
        str(CRM_CONTOURS_RAW),
    ])

    # These bathymetry blocks are sharper than the broad CRM grid, but each
    # covers only a patch. Generate all matching contours and merge them later.
    for block in BATHYMETRY_BLOCKS:
        block_levels = [
            str(level)
            for level in contour_levels()
            if float(block["contourMinimum"]) <= level <= float(block["contourMaximum"])
        ]
        if not block_levels:
            continue
        run([
            "gdal_contour",
            "-q",
            "-a",
            "elevation_m",
            "-fl",
            *block_levels,
            str(bathymetry_block_dataset(block)),
            str(bathymetry_block_contours_raw(block)),
        ])
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-simplify",
            str(block["contourSimplify"]),
            str(bathymetry_block_contours_wgs84(block)),
            str(bathymetry_block_contours_raw(block)),
        ])

    # DEM 4 is the high-resolution Golden Gate / Ocean Beach / San Francisco Bar tile.
    # It is in meters, NAVD88, NAD83 / UTM zone 10N. Simplify before browser export
    # so 2 m source data does not produce a huge client payload.
    usgs_levels = [str(level) for level in contour_levels() if -115.0 <= level <= 2.0]
    run([
        "gdal_contour",
        "-q",
        "-a",
        "elevation_m",
        "-fl",
        *usgs_levels,
        str(DS684_TIF),
        str(DS684_CONTOURS_RAW),
    ])
    run([
        "ogr2ogr",
        "-f",
        "GeoJSON",
        "-t_srs",
        "EPSG:4326",
        "-simplify",
        "12",
        str(DS684_CONTOURS_WGS84),
        str(DS684_CONTOURS_RAW),
    ])


def is_valid_height(value: float) -> bool:
    return math.isfinite(value) and -1000 < value < 1_000_000


def clamp_byte(value: float) -> int:
    return max(0, min(255, round(value)))


def encode_height_rgb(height: float, minimum: float, maximum: float) -> tuple[int, int, int]:
    normalized = max(0.0, min(1.0, (height - minimum) / (maximum - minimum)))
    encoded = round(normalized * 16_777_215)
    return (
        (encoded >> 16) & 255,
        (encoded >> 8) & 255,
        encoded & 255,
    )


def terrain_color(height: float) -> tuple[int, int, int]:
    if height <= TERRAIN_COLOR_STOPS[0][0]:
        return TERRAIN_COLOR_STOPS[0][1]

    for index in range(1, len(TERRAIN_COLOR_STOPS)):
        low_height, low_color = TERRAIN_COLOR_STOPS[index - 1]
        high_height, high_color = TERRAIN_COLOR_STOPS[index]
        if height <= high_height:
            amount = (height - low_height) / (high_height - low_height)
            return tuple(
                clamp_byte(low_color[channel] + ((high_color[channel] - low_color[channel]) * amount))
                for channel in range(3)
            )

    return TERRAIN_COLOR_STOPS[-1][1]


def shaded_relief_color(base: tuple[int, int, int], shade: float, slope: float, height: float) -> tuple[int, int, int]:
    if height < 0:
        depth_boost = max(0.0, min(1.0, abs(height) / 140.0))
        contrast = 0.78 + depth_boost * 0.32
        brightness = 0.34 + shade * 0.92 + min(0.28, slope * 0.018)
    else:
        contrast = 0.9
        brightness = 0.42 + shade * 0.82 + min(0.22, slope * 0.012)

    return tuple(clamp_byte(((channel - 128) * contrast + 128) * brightness) for channel in base)


def mix_color(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(clamp_byte(a[channel] + (b[channel] - a[channel]) * amount) for channel in range(3))


def survey_composite_color(
    base: tuple[int, int, int],
    relief: tuple[int, int, int],
    shade: float,
    slope: float,
    roughness: float,
    curvature: float,
    height: float,
) -> tuple[int, int, int]:
    slope_signal = max(0.0, min(1.0, slope / (34.0 if height < 0 else 92.0)))
    rough_signal = max(0.0, min(1.0, roughness / (65.0 if height < 0 else 140.0)))
    ridge_signal = max(0.0, min(1.0, curvature / (22.0 if height < 0 else 48.0)))
    hollow_signal = max(0.0, min(1.0, -curvature / (22.0 if height < 0 else 48.0)))

    if height < 0:
        shelf_cyan = (56, 183, 198)
        deep_blue = (10, 28, 62)
        ridge_gold = (247, 215, 126)
        pale_scarp = (238, 246, 226)

        detail_signal = max(slope_signal * 0.8, rough_signal * 0.72, ridge_signal * 0.9)
        color = mix_color(relief, shelf_cyan, 0.08 + slope_signal * 0.16)
        color = mix_color(color, deep_blue, hollow_signal * 0.28)
        color = mix_color(color, ridge_gold, ridge_signal * 0.38 + rough_signal * 0.12)
        color = mix_color(color, pale_scarp, detail_signal * 0.18)

        contrast = 1.04 + detail_signal * 0.34
        brightness = 0.92 + (shade - 0.5) * 0.22 - hollow_signal * 0.12
        return tuple(clamp_byte(((channel - 128) * contrast + 128) * brightness) for channel in color)

    land_detail = min(0.28, slope_signal * 0.18 + rough_signal * 0.1)
    color = mix_color(relief, base, 0.18)
    color = mix_color(color, (248, 248, 240), land_detail)
    return tuple(clamp_byte(channel * (0.96 + shade * 0.12)) for channel in color)


def relief_shade(
    heights: list[float | None],
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[float, float]:
    def sample(sample_x: int, sample_y: int) -> float:
        clamped_x = max(0, min(width - 1, sample_x))
        clamped_y = max(0, min(height - 1, sample_y))
        value = heights[clamped_y * width + clamped_x]
        center = heights[y * width + x]
        if value is None and center is not None:
            return center
        return value if value is not None else 0.0

    west = sample(x - 1, y)
    east = sample(x + 1, y)
    north = sample(x, y - 1)
    south = sample(x, y + 1)
    dz_dx = east - west
    dz_dy = south - north
    slope = math.hypot(dz_dx, dz_dy)

    # A simple northwest light. This is visual shading, not a measured sun model.
    normal_x = -dz_dx
    normal_y = -dz_dy
    normal_z = 42.0
    normal_length = math.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    light_x, light_y, light_z = -0.48, -0.58, 0.66
    shade = (normal_x * light_x + normal_y * light_y + normal_z * light_z) / normal_length
    return max(0.0, min(1.0, shade * 0.5 + 0.5)), slope


def terrain_surface_metrics(
    heights: list[float | None],
    width: int,
    height: int,
    x: int,
    y: int,
) -> tuple[float, float]:
    center = heights[y * width + x]
    if center is None:
        return 0.0, 0.0

    def sample(sample_x: int, sample_y: int) -> float:
        clamped_x = max(0, min(width - 1, sample_x))
        clamped_y = max(0, min(height - 1, sample_y))
        value = heights[clamped_y * width + clamped_x]
        return value if value is not None else center

    neighbors = [
        sample(sample_x, sample_y)
        for sample_y in range(y - 1, y + 2)
        for sample_x in range(x - 1, x + 2)
    ]
    roughness = max(neighbors) - min(neighbors)
    cardinal_average = (
        sample(x - 1, y)
        + sample(x + 1, y)
        + sample(x, y - 1)
        + sample(x, y + 1)
    ) / 4.0
    curvature = center - cardinal_average
    return roughness, curvature


def raw_pixel_value(raw: Any) -> float:
    if isinstance(raw, tuple):
        values = [float(value) for value in raw[:3] if isinstance(value, (int, float)) and math.isfinite(float(value))]
        return sum(values) / len(values) if values else float("nan")
    return float(raw)


def percentile(sorted_values: list[float], amount: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * amount)))
    return sorted_values[index]


def sonar_color(intensity: float) -> tuple[int, int, int]:
    intensity = max(0.0, min(1.0, intensity))
    if intensity < 0.55:
        amount = intensity / 0.55
        low = (12, 27, 44)
        mid = (38, 112, 126)
        return tuple(clamp_byte(low[channel] + (mid[channel] - low[channel]) * amount) for channel in range(3))

    amount = (intensity - 0.55) / 0.45
    mid = (38, 112, 126)
    high = (236, 214, 158)
    return tuple(clamp_byte(mid[channel] + (high[channel] - mid[channel]) * amount) for channel in range(3))


def write_sonar_texture_png(backscatter_path: Path, relief_texture_path: Path, output_path: Path) -> None:
    backscatter = Image.open(backscatter_path)
    relief = Image.open(relief_texture_path).convert("RGBA")
    if backscatter.size != relief.size:
        backscatter = backscatter.resize(relief.size, Image.Resampling.BILINEAR)

    raw_values = [raw_pixel_value(raw) for raw in backscatter.getdata()]
    valid_values = sorted(value for value in raw_values if math.isfinite(value) and 0 < value < 255)
    low = percentile(valid_values, 0.02)
    high = percentile(valid_values, 0.98)
    if high <= low:
        high = low + 1.0

    output_pixels: list[tuple[int, int, int, int]] = []
    relief_pixels = list(relief.getdata())
    for raw_value, relief_pixel in zip(raw_values, relief_pixels):
        relief_r, relief_g, relief_b, relief_a = relief_pixel
        if not math.isfinite(raw_value) or raw_value <= 0 or raw_value >= 255:
            output_pixels.append((relief_r, relief_g, relief_b, relief_a))
            continue

        normalized = max(0.0, min(1.0, (raw_value - low) / (high - low)))
        normalized = math.pow(normalized, 0.82)
        sonar_r, sonar_g, sonar_b = sonar_color(normalized)
        relief_luma = (0.2126 * relief_r + 0.7152 * relief_g + 0.0722 * relief_b) / 255.0
        shade = 0.72 + relief_luma * 0.46
        output_pixels.append((
            clamp_byte((sonar_r * shade * 0.72) + (relief_r * 0.28)),
            clamp_byte((sonar_g * shade * 0.72) + (relief_g * 0.28)),
            clamp_byte((sonar_b * shade * 0.72) + (relief_b * 0.28)),
            relief_a,
        ))

    output = Image.new("RGBA", relief.size)
    output.putdata(output_pixels)
    output.save(output_path)


def character_color(character_class: int) -> tuple[int, int, int] | None:
    colors = {
        1: (226, 193, 118),  # smooth sediment
        2: (53, 174, 163),   # mixed sediment and rock
        3: (238, 104, 93),   # rugose rock or boulder-like bottom
    }
    return colors.get(character_class)


def write_character_texture_png(character_path: Path, base_texture_path: Path, output_path: Path) -> None:
    character = Image.open(character_path)
    base = Image.open(base_texture_path).convert("RGBA")
    if character.size != base.size:
        character = character.resize(base.size, Image.Resampling.NEAREST)

    output_pixels: list[tuple[int, int, int, int]] = []
    for raw, base_pixel in zip(character.getdata(), base.getdata()):
        base_r, base_g, base_b, base_a = base_pixel
        raw_value = raw_pixel_value(raw)
        if not math.isfinite(raw_value):
            output_pixels.append(base_pixel)
            continue

        class_color = character_color(round(raw_value))
        if class_color is None:
            output_pixels.append(base_pixel)
            continue

        class_r, class_g, class_b = class_color
        base_luma = (0.2126 * base_r + 0.7152 * base_g + 0.0722 * base_b) / 255.0
        shade = 0.76 + base_luma * 0.42
        output_pixels.append((
            clamp_byte(((class_r * 0.7) + (base_r * 0.3)) * shade),
            clamp_byte(((class_g * 0.7) + (base_g * 0.3)) * shade),
            clamp_byte(((class_b * 0.7) + (base_b * 0.3)) * shade),
            base_a,
        ))

    output = Image.new("RGBA", base.size)
    output.putdata(output_pixels)
    output.save(output_path)


def write_terrain_pngs_from_wgs84(
    source_path: Path,
    elevation_path: Path,
    texture_path: Path,
    relief_texture_path: Path,
    composite_texture_path: Path,
    minimum: float,
    maximum: float,
) -> None:
    source = Image.open(source_path)
    elevation = Image.new("RGB", source.size)
    texture = Image.new("RGBA", source.size)
    relief_texture = Image.new("RGBA", source.size)
    composite_texture = Image.new("RGBA", source.size)
    width, image_height = source.size

    elevation_pixels = []
    texture_pixels: list[tuple[int, int, int, int]] = []
    relief_pixels: list[tuple[int, int, int, int]] = []
    composite_pixels: list[tuple[int, int, int, int]] = []
    heights: list[float | None] = []
    base_colors: list[tuple[int, int, int] | None] = []

    for raw in source.getdata():
        elevation_m = float(raw)
        if not is_valid_height(elevation_m):
            elevation_pixels.append((0, 0, 0))
            texture_pixels.append((0, 0, 0, 0))
            heights.append(None)
            base_colors.append(None)
            continue

        base_color = terrain_color(elevation_m)
        elevation_pixels.append(encode_height_rgb(elevation_m, minimum, maximum))
        texture_pixels.append((*base_color, 255))
        heights.append(elevation_m)
        base_colors.append(base_color)

    for index, base_color in enumerate(base_colors):
        height_value = heights[index]
        if base_color is None or height_value is None:
            relief_pixels.append((0, 0, 0, 0))
            composite_pixels.append((0, 0, 0, 0))
            continue
        x = index % width
        y = index // width
        shade, slope = relief_shade(heights, width, image_height, x, y)
        roughness, curvature = terrain_surface_metrics(heights, width, image_height, x, y)
        relief_color = shaded_relief_color(base_color, shade, slope, height_value)
        relief_pixels.append((*relief_color, 255))
        composite_pixels.append((
            *survey_composite_color(base_color, relief_color, shade, slope, roughness, curvature, height_value),
            255,
        ))

    elevation.putdata(elevation_pixels)
    texture.putdata(texture_pixels)
    relief_texture.putdata(relief_pixels)
    composite_texture.putdata(composite_pixels)
    elevation.save(elevation_path)
    texture.save(texture_path)
    relief_texture.save(relief_texture_path)
    composite_texture.save(composite_texture_path)


def terrain_metadata(
    source_id: str,
    source_label_value: str,
    wgs84_tif: Path,
    elevation_png: Path,
    texture_png: Path,
    relief_texture_png: Path,
    composite_texture_png: Path,
    sonar_texture_png: Path | None,
    hybrid_texture_png: Path | None,
    character_texture_png: Path | None,
    minimum: float,
    maximum: float,
    note: str,
) -> dict[str, Any]:
    info = json.loads(subprocess.check_output(["gdalinfo", "-json", str(wgs84_tif)]))
    transform = info["geoTransform"]
    width = info["size"][0]
    height = info["size"][1]
    west = transform[0]
    north = transform[3]
    east = west + transform[1] * width
    south = north + transform[5] * height

    def public_url(path: Path) -> str:
        return "/" + str(path.relative_to(ROOT / "public"))

    textures = {
        "depthColor": public_url(texture_png),
        "shadedRelief": public_url(relief_texture_png),
        "surveyComposite": public_url(composite_texture_png),
    }
    if sonar_texture_png is not None and sonar_texture_png.exists():
        textures["sonarBackscatter"] = public_url(sonar_texture_png)
    if hybrid_texture_png is not None and hybrid_texture_png.exists():
        textures["surveySonarHybrid"] = public_url(hybrid_texture_png)
    if character_texture_png is not None and character_texture_png.exists():
        textures["seafloorCharacter"] = public_url(character_texture_png)

    return {
        "sourceId": source_id,
        "sourceLabel": source_label_value,
        "elevationData": public_url(elevation_png),
        "texture": public_url(texture_png),
        "textures": textures,
        "bounds": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
        "heightRangeMeters": [minimum, maximum],
        "verticalExaggeration": TERRAIN_VERTICAL_EXAGGERATION,
        "elevationDecoder": {
            "rScaler": ((maximum - minimum) / 16_777_215.0) * 65_536 * TERRAIN_VERTICAL_EXAGGERATION,
            "gScaler": ((maximum - minimum) / 16_777_215.0) * 256 * TERRAIN_VERTICAL_EXAGGERATION,
            "bScaler": ((maximum - minimum) / 16_777_215.0) * TERRAIN_VERTICAL_EXAGGERATION,
            "offset": minimum * TERRAIN_VERTICAL_EXAGGERATION,
        },
        "note": note,
    }


def generate_usgs_terrain_asset() -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-ts",
        str(DS684_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-dstnodata",
        "-9999",
        str(DS684_TIF),
        str(DS684_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        DS684_TERRAIN_WGS84,
        DS684_TERRAIN_ELEVATION_PNG,
        DS684_TERRAIN_TEXTURE_PNG,
        DS684_TERRAIN_RELIEF_TEXTURE_PNG,
        DS684_TERRAIN_COMPOSITE_TEXTURE_PNG,
        DS684_TERRAIN_MIN_M,
        DS684_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "usgs_ds684_dem4",
        source_label("usgs_ds684_dem4"),
        DS684_TERRAIN_WGS84,
        DS684_TERRAIN_ELEVATION_PNG,
        DS684_TERRAIN_TEXTURE_PNG,
        DS684_TERRAIN_RELIEF_TEXTURE_PNG,
        DS684_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        DS684_TERRAIN_MIN_M,
        DS684_TERRAIN_MAX_M,
        "Higher-resolution 2 m terrain inset for the Golden Gate, Ocean Beach, Marin Headlands, and San Francisco Bar.",
    )


def generate_bathymetry_block_sonar_texture(block: dict[str, Any]) -> tuple[Path | None, Path | None]:
    zip_names = [str(zip_name) for zip_name in block.get("backscatterZipNames", [])]
    if not zip_names:
        return None, None

    datasets = [
        bathymetry_block_backscatter_dataset(block, zip_name)
        for zip_name in zip_names
        if bathymetry_block_backscatter_dataset(block, zip_name).exists()
    ]
    if not datasets:
        return None, None

    terrain_info = json.loads(subprocess.check_output(["gdalinfo", "-json", str(bathymetry_block_terrain_wgs84(block))]))
    transform = terrain_info["geoTransform"]
    width = terrain_info["size"][0]
    height = terrain_info["size"][1]
    west = transform[0]
    north = transform[3]
    east = west + transform[1] * width
    south = north + transform[5] * height

    source_srs_args = ["-s_srs", str(block["backscatterSourceSrs"])] if block.get("backscatterSourceSrs") else []
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        *source_srs_args,
        "-t_srs",
        "EPSG:4326",
        "-te",
        str(west),
        str(south),
        str(east),
        str(north),
        "-ts",
        str(width),
        str(height),
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-dstnodata",
        "-9999",
        *[str(dataset) for dataset in datasets],
        str(bathymetry_block_backscatter_wgs84(block)),
    ])
    write_sonar_texture_png(
        bathymetry_block_backscatter_wgs84(block),
        bathymetry_block_relief_texture_png(block),
        bathymetry_block_sonar_texture_png(block),
    )
    write_sonar_texture_png(
        bathymetry_block_backscatter_wgs84(block),
        bathymetry_block_composite_texture_png(block),
        bathymetry_block_hybrid_texture_png(block),
    )
    return bathymetry_block_sonar_texture_png(block), bathymetry_block_hybrid_texture_png(block)


def generate_bathymetry_block_character_texture(block: dict[str, Any], base_texture_path: Path) -> Path | None:
    if not block.get("characterZipName"):
        return None
    if not bathymetry_block_character_dataset(block).exists():
        return None

    terrain_info = json.loads(subprocess.check_output(["gdalinfo", "-json", str(bathymetry_block_terrain_wgs84(block))]))
    transform = terrain_info["geoTransform"]
    width = terrain_info["size"][0]
    height = terrain_info["size"][1]
    west = transform[0]
    north = transform[3]
    east = west + transform[1] * width
    south = north + transform[5] * height

    source_srs_args = ["-s_srs", str(block["characterSourceSrs"])] if block.get("characterSourceSrs") else []
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        *source_srs_args,
        "-t_srs",
        "EPSG:4326",
        "-te",
        str(west),
        str(south),
        str(east),
        str(north),
        "-ts",
        str(width),
        str(height),
        "-r",
        "near",
        "-ot",
        "Byte",
        "-dstnodata",
        "255",
        str(bathymetry_block_character_dataset(block)),
        str(bathymetry_block_character_wgs84(block)),
    ])
    write_character_texture_png(
        bathymetry_block_character_wgs84(block),
        base_texture_path,
        bathymetry_block_character_texture_png(block),
    )
    return bathymetry_block_character_texture_png(block)


def generate_bathymetry_block_terrain_asset(block: dict[str, Any]) -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-ts",
        str(block["terrainSize"]),
        "0",
        "-r",
        "bilinear",
        "-dstnodata",
        "-9999",
        str(bathymetry_block_dataset(block)),
        str(bathymetry_block_terrain_wgs84(block)),
    ])
    write_terrain_pngs_from_wgs84(
        bathymetry_block_terrain_wgs84(block),
        bathymetry_block_elevation_png(block),
        bathymetry_block_texture_png(block),
        bathymetry_block_relief_texture_png(block),
        bathymetry_block_composite_texture_png(block),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
    )
    sonar_texture, hybrid_texture = generate_bathymetry_block_sonar_texture(block)
    character_base = hybrid_texture if hybrid_texture is not None and hybrid_texture.exists() else bathymetry_block_composite_texture_png(block)
    character_texture = generate_bathymetry_block_character_texture(block, character_base)
    return terrain_metadata(
        str(block["sourceId"]),
        source_label(str(block["sourceId"])),
        bathymetry_block_terrain_wgs84(block),
        bathymetry_block_elevation_png(block),
        bathymetry_block_texture_png(block),
        bathymetry_block_relief_texture_png(block),
        bathymetry_block_composite_texture_png(block),
        sonar_texture,
        hybrid_texture,
        character_texture,
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        str(block["note"]),
    )


def generate_etopo_terrain_asset() -> dict[str, Any]:
    west = 236.0020833333333 - 360.0
    east = 238.5020833333333 - 360.0
    north = 38.50208333333333
    south = 37.00208333333333
    run([
        "gdal_translate",
        "-q",
        "-of",
        "GTiff",
        "-a_srs",
        "EPSG:4326",
        "-a_ullr",
        str(west),
        str(north),
        str(east),
        str(south),
        f"NETCDF:{RAW_NETCDF}:z",
        str(ETOPO_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        ETOPO_TERRAIN_WGS84,
        ETOPO_TERRAIN_ELEVATION_PNG,
        ETOPO_TERRAIN_TEXTURE_PNG,
        ETOPO_TERRAIN_RELIEF_TEXTURE_PNG,
        ETOPO_TERRAIN_COMPOSITE_TEXTURE_PNG,
        ETOPO_TERRAIN_MIN_M,
        ETOPO_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "noaa_etopo_2022",
        source_label("noaa_etopo_2022"),
        ETOPO_TERRAIN_WGS84,
        ETOPO_TERRAIN_ELEVATION_PNG,
        ETOPO_TERRAIN_TEXTURE_PNG,
        ETOPO_TERRAIN_RELIEF_TEXTURE_PNG,
        ETOPO_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        ETOPO_TERRAIN_MIN_M,
        ETOPO_TERRAIN_MAX_M,
        "Broad Bay-to-Farallones terrain surface. It is coarser than the USGS tile, but it reaches the offshore shelf and Farallon Islands.",
    )


def generate_crm_terrain_asset() -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-ts",
        str(CRM_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        str(CRM_TIF),
        str(CRM_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        CRM_TERRAIN_WGS84,
        CRM_TERRAIN_ELEVATION_PNG,
        CRM_TERRAIN_TEXTURE_PNG,
        CRM_TERRAIN_RELIEF_TEXTURE_PNG,
        CRM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        CRM_TERRAIN_MIN_M,
        CRM_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "noaa_crm_vol7_3as",
        source_label("noaa_crm_vol7_3as"),
        CRM_TERRAIN_WGS84,
        CRM_TERRAIN_ELEVATION_PNG,
        CRM_TERRAIN_TEXTURE_PNG,
        CRM_TERRAIN_RELIEF_TEXTURE_PNG,
        CRM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        CRM_TERRAIN_MIN_M,
        CRM_TERRAIN_MAX_M,
        "NOAA CRM Vol. 7 broad Bay-to-Farallones terrain surface at 3 arc-second resolution. It is coarser than the USGS tile, but about 5x finer than ETOPO 2022 for this view.",
    )


def generate_terrain_assets() -> list[dict[str, Any]]:
    TERRAIN_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for target in (
        DS684_TERRAIN_WGS84,
        DS684_TERRAIN_ELEVATION_PNG,
        DS684_TERRAIN_TEXTURE_PNG,
        DS684_TERRAIN_RELIEF_TEXTURE_PNG,
        DS684_TERRAIN_COMPOSITE_TEXTURE_PNG,
        CRM_TERRAIN_WGS84,
        CRM_TERRAIN_ELEVATION_PNG,
        CRM_TERRAIN_TEXTURE_PNG,
        CRM_TERRAIN_RELIEF_TEXTURE_PNG,
        CRM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        ETOPO_TERRAIN_WGS84,
        ETOPO_TERRAIN_ELEVATION_PNG,
        ETOPO_TERRAIN_TEXTURE_PNG,
        ETOPO_TERRAIN_RELIEF_TEXTURE_PNG,
        ETOPO_TERRAIN_COMPOSITE_TEXTURE_PNG,
    ):
        target.unlink(missing_ok=True)
    for block in BATHYMETRY_BLOCKS:
        bathymetry_block_terrain_wgs84(block).unlink(missing_ok=True)
        bathymetry_block_elevation_png(block).unlink(missing_ok=True)
        bathymetry_block_texture_png(block).unlink(missing_ok=True)
        bathymetry_block_relief_texture_png(block).unlink(missing_ok=True)
        bathymetry_block_composite_texture_png(block).unlink(missing_ok=True)
        bathymetry_block_backscatter_wgs84(block).unlink(missing_ok=True)
        bathymetry_block_sonar_texture_png(block).unlink(missing_ok=True)
        bathymetry_block_hybrid_texture_png(block).unlink(missing_ok=True)
        if block.get("characterZipName"):
            bathymetry_block_character_wgs84(block).unlink(missing_ok=True)
            bathymetry_block_character_texture_png(block).unlink(missing_ok=True)

    return [
        generate_crm_terrain_asset(),
        *[generate_bathymetry_block_terrain_asset(block) for block in BATHYMETRY_BLOCKS],
        generate_usgs_terrain_asset(),
    ]


def normalize_lon(value: float) -> float:
    return value - 360 if value > 180 else value


def transform_coordinates(coords: Any, normalize_360_lon: bool) -> Any:
    if (
        isinstance(coords, list)
        and len(coords) >= 2
        and isinstance(coords[0], (int, float))
        and isinstance(coords[1], (int, float))
    ):
        lon = normalize_lon(float(coords[0])) if normalize_360_lon else float(coords[0])
        return [round(lon, 6), round(float(coords[1]), 6)]
    if isinstance(coords, list):
        return [transform_coordinates(item, normalize_360_lon) for item in coords]
    return coords


def coordinate_pairs(coords: Any) -> list[list[float]]:
    if (
        isinstance(coords, list)
        and len(coords) >= 2
        and isinstance(coords[0], (int, float))
        and isinstance(coords[1], (int, float))
    ):
        return [[float(coords[0]), float(coords[1])]]
    if isinstance(coords, list):
        pairs: list[list[float]] = []
        for item in coords:
            pairs.extend(coordinate_pairs(item))
        return pairs
    return []


def approximate_degrees_length(coords: Any) -> float:
    pairs = coordinate_pairs(coords)
    return sum(
        ((pairs[index][0] - pairs[index - 1][0]) ** 2 + (pairs[index][1] - pairs[index - 1][1]) ** 2) ** 0.5
        for index in range(1, len(pairs))
    )


def rounded_level(value: Any) -> float:
    return round(float(value), 3)


def clone_feature(feature: dict[str, Any], properties: dict[str, Any], normalize_360_lon: bool) -> dict[str, Any]:
    geometry = feature["geometry"]
    coordinates = geometry["coordinates"]
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry["type"],
            "coordinates": transform_coordinates(coordinates, normalize_360_lon),
        },
    }


def build_level_index(path: Path, source_id: str, min_degrees_length: float, normalize_360_lon: bool) -> dict[float, list[dict[str, Any]]]:
    source = json.loads(path.read_text())
    by_level: dict[float, list[dict[str, Any]]] = {}

    for feature in source.get("features", []):
        if approximate_degrees_length(feature["geometry"]["coordinates"]) < min_degrees_length:
            continue
        level = rounded_level(feature["properties"]["elevation_m"])
        feature["properties"]["source_id"] = source_id
        feature["properties"]["normalize_360_lon"] = normalize_360_lon
        by_level.setdefault(level, []).append(feature)

    return by_level


def merge_level_indexes(indexes: list[dict[float, list[dict[str, Any]]]]) -> dict[float, list[dict[str, Any]]]:
    merged: dict[float, list[dict[str, Any]]] = {}
    for index in indexes:
        for level, features in index.items():
            merged.setdefault(level, []).extend(features)
    return merged


def features_for_source(index: dict[float, list[dict[str, Any]]], level: float, source_id: str) -> list[dict[str, Any]]:
    return [
        feature
        for feature in index.get(rounded_level(level), [])
        if feature["properties"].get("source_id") == source_id
    ]


def features_for_level(
    level: float,
    crm_by_level: dict[float, list[dict[str, Any]]],
    bathymetry_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
    preferred_source_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    level_key = rounded_level(level)
    if preferred_source_id == "usgs_ds684_dem4" and usgs_by_level.get(level_key):
        return "usgs_ds684_dem4", usgs_by_level[level_key]
    if preferred_source_id in BATHYMETRY_SOURCE_IDS:
        preferred_features = features_for_source(bathymetry_by_level, level_key, preferred_source_id)
        if preferred_features:
            return preferred_source_id, preferred_features
    if preferred_source_id == "noaa_crm_vol7_3as" and crm_by_level.get(level_key):
        return "noaa_crm_vol7_3as", crm_by_level[level_key]
    if preferred_source_id == "composite_high_resolution_local" and (
        usgs_by_level.get(level_key) or bathymetry_by_level.get(level_key)
    ):
        return "composite_high_resolution_local", [
            *crm_by_level.get(level_key, []),
            *bathymetry_by_level.get(level_key, []),
            *usgs_by_level.get(level_key, []),
        ]

    local_features = [
        *bathymetry_by_level.get(level_key, []),
        *usgs_by_level.get(level_key, []),
    ]
    if local_features:
        return "composite_high_resolution_local", [
            *crm_by_level.get(level_key, []),
            *local_features,
        ]
    return "noaa_crm_vol7_3as", crm_by_level.get(level_key, [])


def probe_features_for_level(
    level: float,
    crm_by_level: dict[float, list[dict[str, Any]]],
    bathymetry_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    level_key = rounded_level(level)
    features: list[dict[str, Any]] = []
    features.extend(crm_by_level.get(level_key, []))
    features.extend(bathymetry_by_level.get(level_key, []))
    features.extend(usgs_by_level.get(level_key, []))
    return features


BATHYMETRY_SOURCE_IDS = {str(block["sourceId"]) for block in BATHYMETRY_BLOCKS}
SOURCE_LABELS = {str(block["sourceId"]): str(block["sourceLabel"]) for block in BATHYMETRY_BLOCKS}


def source_label(source_id: str) -> str:
    if source_id == "usgs_ds684_dem4":
        return "USGS DS684 DEM 4, 2 m San Francisco Bar / Ocean Beach tile"
    if source_id in SOURCE_LABELS:
        return SOURCE_LABELS[source_id]
    if source_id == "composite_high_resolution_local":
        return "Composite high-resolution local bathymetry plus topobathymetry"
    if source_id == "noaa_crm_vol7_3as":
        return "NOAA CRM Vol. 7, 3 arc-second Bay-to-Farallones grid"
    return "NOAA ETOPO 2022 15 arc-second broad Bay/offshore grid"


def build_browser_payload() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    crm_by_level = build_level_index(CRM_CONTOURS_BROWSER, "noaa_crm_vol7_3as", 0.004, False)
    bathymetry_by_level = merge_level_indexes([
        build_level_index(
            bathymetry_block_contours_wgs84(block),
            str(block["sourceId"]),
            float(block["minDegreesLength"]),
            False,
        )
        for block in BATHYMETRY_BLOCKS
    ])
    usgs_by_level = build_level_index(DS684_CONTOURS_WGS84, "usgs_ds684_dem4", 0.003, False)
    terrain = generate_terrain_assets()

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload: list[dict[str, Any]] = []
    waterline_probe_features: list[dict[str, Any]] = []

    for level in WATERLINE_PROBE_LEVELS:
        for feature in probe_features_for_level(level, crm_by_level, bathymetry_by_level, usgs_by_level):
            source_id = feature["properties"]["source_id"]
            waterline_probe_features.append(
                clone_feature(
                    feature,
                    {
                        "slice_id": "waterline_probe",
                        "label": "Waterline probe",
                        "line_role": "waterline_probe",
                        "elevation_m": rounded_level(level),
                        "years_before_present": 0,
                        "source_id": source_id,
                        "source_label": source_label(source_id),
                    },
                    bool(feature["properties"].get("normalize_360_lon")),
                )
            )

    waterline_probe = {
        "levelsMeters": WATERLINE_PROBE_LEVELS,
        "intervalMeters": 5,
        "description": "Five-meter DEM contour set used only for interactive waterline scrubbing. It is not a dated sea-level reconstruction.",
        "contours": {"type": "FeatureCollection", "features": waterline_probe_features},
    }

    for index, item in enumerate(TIME_SLICES):
        center = rounded_level(item["seaLevelMeters"])
        spread = rounded_level(item["uncertaintyMeters"])
        low = rounded_level(center - spread)
        high = rounded_level(center + spread)

        estimate_source_id, estimate_source_features = features_for_level(center, crm_by_level, bathymetry_by_level, usgs_by_level)
        coastline_features = [
            clone_feature(
                feature,
                {
                    "slice_id": item["id"],
                    "label": item["label"],
                    "line_role": "estimate",
                    "elevation_m": center,
                    "years_before_present": item["yearsBeforePresent"],
                    "source_id": feature["properties"]["source_id"],
                    "source_label": source_label(feature["properties"]["source_id"]),
                },
                bool(feature["properties"].get("normalize_360_lon")),
            )
            for feature in estimate_source_features
        ]
        uncertainty_features = []
        for role, level in (("lower_sea_level_bound", low), ("higher_sea_level_bound", high)):
            uncertainty_source_id, uncertainty_source_features = features_for_level(
                level,
                crm_by_level,
                bathymetry_by_level,
                usgs_by_level,
                estimate_source_id,
            )
            uncertainty_features.extend(
                clone_feature(
                    feature,
                    {
                        "slice_id": item["id"],
                        "label": item["label"],
                        "line_role": role,
                        "elevation_m": level,
                        "years_before_present": item["yearsBeforePresent"],
                        "source_id": feature["properties"]["source_id"],
                        "source_label": source_label(feature["properties"]["source_id"]),
                    },
                    bool(feature["properties"].get("normalize_360_lon")),
                )
                for feature in uncertainty_source_features
            )

        payload.append({
            **item,
            "generatedAt": generated_at,
            "sourceModel": source_label(estimate_source_id),
            "datumNote": "USGS CSMP, Farallon, Rittenburg Bank, and DS684 sources use NAVD88-style vertical references; NOAA CRM and ETOPO use broader sea-level/EGM-style vertical references. Sea-level offsets are approximate relative values, not a full local tidal-datum correction.",
            "uncertaintyNote": "Lines show only sea-level uncertainty. They do not model erosion, sediment, marsh growth, tectonic motion, or river-channel migration.",
            "terrain": terrain[0],
            "terrains": terrain,
            "coastline": {"type": "FeatureCollection", "features": coastline_features},
            "uncertainty": {"type": "FeatureCollection", "features": uncertainty_features},
            **({"waterlineProbe": waterline_probe} if index == 0 else {}),
        })

    metadata = {
        "generatedAt": generated_at,
        "studyBounds": BBOX,
        "method": "Downloaded a NOAA CRM Vol. 7 SF/Farallones subset, multiple USGS/CSMP nearshore 2 m bathymetry blocks, USGS Farallon Escarpment/Rittenburg Bank offshore multibeam bathymetry, and the USGS DS684 San Francisco Bar 2 m DEM tile, generated fixed elevation contours with GDAL, and exported broad plus local browser terrain images. NOAA ETOPO 2022 remains documented as a fallback broad source.",
        "rawDatasets": [
            str(CRM_TIF.relative_to(ROOT)),
            str(RAW_NETCDF.relative_to(ROOT)),
            *[
                str(bathymetry_block_dataset(block).relative_to(ROOT))
                for block in BATHYMETRY_BLOCKS
            ],
            *[
                str(bathymetry_block_backscatter_dataset(block, str(zip_name)).relative_to(ROOT))
                for block in BATHYMETRY_BLOCKS
                for zip_name in block.get("backscatterZipNames", [])
                if bathymetry_block_backscatter_dataset(block, str(zip_name)).exists()
            ],
            *[
                str(bathymetry_block_character_dataset(block).relative_to(ROOT))
                for block in BATHYMETRY_BLOCKS
                if block.get("characterZipName") and bathymetry_block_character_dataset(block).exists()
            ],
            str(DS684_TIF.relative_to(ROOT)),
        ],
        "browserDataset": "public/data/paleo-coastlines/paleo_coastlines.json",
        "terrainAssets": [
            str(CRM_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(CRM_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
            str(CRM_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
            str(CRM_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
            *[
                str(path.relative_to(ROOT))
                for block in BATHYMETRY_BLOCKS
                for path in (
                    bathymetry_block_elevation_png(block),
                    bathymetry_block_texture_png(block),
                    bathymetry_block_relief_texture_png(block),
                    bathymetry_block_composite_texture_png(block),
                    bathymetry_block_sonar_texture_png(block),
                    bathymetry_block_hybrid_texture_png(block),
                    bathymetry_block_character_texture_png(block),
                )
                if path.exists()
            ],
            str(DS684_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(DS684_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
            str(DS684_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
            str(DS684_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
        ],
        "sources": SOURCES,
        "timeSlices": [
            {
                "id": item["id"],
                "label": item["label"],
                "seaLevelMeters": item["seaLevelMeters"],
                "uncertaintyMeters": item["uncertaintyMeters"],
            }
            for item in TIME_SLICES
        ],
        "waterlineProbe": {
            "levelsMeters": WATERLINE_PROBE_LEVELS,
            "intervalMeters": 5,
            "description": waterline_probe["description"],
        },
    }
    return payload, metadata


def write_outputs(payload: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    SLICES_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    if WATERLINE_PROBE_PUBLIC_DIR.exists():
        shutil.rmtree(WATERLINE_PROBE_PUBLIC_DIR)
    WATERLINE_PROBE_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    def public_url(path: Path) -> str:
        return "/" + str(path.relative_to(ROOT / "public"))

    def write_compact_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, separators=(",", ":")) + "\n")

    (PUBLIC_DIR / "paleo_coastlines.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    (PUBLIC_DIR / "paleo_coastline_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    manifest_slices = []
    waterline_probe = None
    for item in payload:
        slice_payload = {key: value for key, value in item.items() if key != "waterlineProbe"}
        slice_path = SLICES_PUBLIC_DIR / f"{item['id']}.json"
        write_compact_json(slice_path, slice_payload)

        if item.get("waterlineProbe"):
            waterline_probe = item["waterlineProbe"]

        manifest_item = {
            key: value
            for key, value in item.items()
            if key not in {"coastline", "uncertainty", "waterlineProbe"}
        }
        manifest_item["coastline"] = {"type": "FeatureCollection", "features": []}
        manifest_item["uncertainty"] = {"type": "FeatureCollection", "features": []}
        manifest_item["sliceDataUrl"] = public_url(slice_path)
        manifest_slices.append(manifest_item)

    if waterline_probe is None:
        raise SystemExit("No waterline probe was generated.")

    waterline_probe_path = PUBLIC_DIR / "waterline_probe.json"
    write_compact_json(waterline_probe_path, waterline_probe)

    level_data_urls = {}
    probe_features = waterline_probe["contours"]["features"]
    for level in waterline_probe["levelsMeters"]:
        level_key = str(rounded_level(level))
        slug = level_key.replace("-", "minus_").replace(".", "_")
        level_path = WATERLINE_PROBE_PUBLIC_DIR / f"{slug}.json"
        level_collection = {
            "type": "FeatureCollection",
            "features": [
                feature
                for feature in probe_features
                if rounded_level(feature["properties"]["elevation_m"]) == rounded_level(level)
            ],
        }
        write_compact_json(level_path, level_collection)
        level_data_urls[level_key] = public_url(level_path)

    manifest = {
        "generatedAt": metadata["generatedAt"],
        "studyBounds": metadata["studyBounds"],
        "slices": manifest_slices,
        "waterlineProbe": {
            "levelsMeters": waterline_probe["levelsMeters"],
            "intervalMeters": waterline_probe["intervalMeters"],
            "description": waterline_probe["description"],
            "levelDataUrls": level_data_urls,
        },
        "waterlineProbeUrl": public_url(waterline_probe_path),
        "metadataUrl": public_url(PUBLIC_DIR / "paleo_coastline_metadata.json"),
        "legacyAllInOneUrl": public_url(PUBLIC_DIR / "paleo_coastlines.json"),
    }
    write_compact_json(PUBLIC_DIR / "paleo_manifest.json", manifest)

    print(f"Wrote {PUBLIC_DIR / 'paleo_coastlines.json'}")
    print(f"Wrote {PUBLIC_DIR / 'paleo_manifest.json'}")
    print(f"Wrote {waterline_probe_path}")
    print(f"Wrote {PUBLIC_DIR / 'paleo_coastline_metadata.json'}")


def main() -> int:
    require_tool("gdal_contour")
    require_tool("gdalinfo")
    require_tool("gdal_translate")
    require_tool("gdalwarp")
    require_tool("ogr2ogr")
    require_tool("unzip")
    download_raw_netcdf()
    download_noaa_crm_vol7_subset()
    download_bathymetry_blocks()
    download_usgs_ds684_dem4()
    generate_contours()
    payload, metadata = build_browser_payload()
    write_outputs(payload, metadata)

    for item in payload:
        print(
            f"{item['id']}: "
            f"{len(item['coastline']['features'])} estimate features, "
            f"{len(item['uncertainty']['features'])} uncertainty features"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
