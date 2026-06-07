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

import numpy as np
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
CUDEM_DIR = RAW_DIR / "noaa-cudem"
CUDEM_TIF = CUDEM_DIR / "cudem_sf_bay_farallones_1_9as_subset.tif"
CUDEM_CONTOURS_RAW = WORK_DIR / "noaa_cudem_1_9as_contours_raw.geojson"
CUDEM_CONTOURS_BROWSER = WORK_DIR / "noaa_cudem_1_9as_contours_browser.geojson"
CUDEM_TERRAIN_WGS84 = WORK_DIR / "noaa_cudem_1_9as_terrain_wgs84.tif"
CUDEM_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "cudem_sf_bay_farallones_elevation.png"
CUDEM_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "cudem_sf_bay_farallones_color.png"
CUDEM_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "cudem_sf_bay_farallones_relief.png"
CUDEM_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "cudem_sf_bay_farallones_composite.png"
BEST_AVAILABLE_TERRAIN_VRT = WORK_DIR / "best_available_gate_shelf_terrain.vrt"
BEST_AVAILABLE_TERRAIN_WGS84 = WORK_DIR / "best_available_gate_shelf_terrain_wgs84.tif"
BEST_AVAILABLE_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_elevation.png"
BEST_AVAILABLE_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_color.png"
BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_relief.png"
BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_composite.png"
BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_source_quality.png"
NOS_BAG_DEFAULT_DIR = RAW_DIR / "noaa-nos-bag"
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
CUDEM_TERRAIN_SIZE = 4096
DS684_TERRAIN_SIZE = 768
DS684_TERRAIN_MIN_M = -130.0
DS684_TERRAIN_MAX_M = 400.0
ETOPO_TERRAIN_MIN_M = -2500.0
ETOPO_TERRAIN_MAX_M = 1000.0
CRM_TERRAIN_MIN_M = -2500.0
CRM_TERRAIN_MAX_M = 1000.0
CUDEM_TERRAIN_MIN_M = -2500.0
CUDEM_TERRAIN_MAX_M = 1200.0
BEST_AVAILABLE_TERRAIN_SIZE = 8192
BEST_AVAILABLE_SOURCE_TEXTURE_SIZE = 4096
BEST_AVAILABLE_TERRAIN_MIN_M = -1000.0
BEST_AVAILABLE_TERRAIN_MAX_M = 500.0
BEST_AVAILABLE_BOUNDS = {
    "west": -123.55,
    "south": 37.35,
    "east": -122.15,
    "north": 38.15,
}
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
CUDEM_BASE_URL = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/NCEI_ninth_Topobathy_2014_8483/CA"
CUDEM_TILE_NAMES = [
    "ncei19_n37x00_w121x75_2023v1.tif",
    "ncei19_n37x00_w122x00_2023v1.tif",
    "ncei19_n37x00_w122x25_2023v1.tif",
    "ncei19_n37x00_w122x50_2023v1.tif",
    "ncei19_n37x25_w121x75_2023v1.tif",
    "ncei19_n37x25_w122x00_2023v1.tif",
    "ncei19_n37x25_w122x25_2023v1.tif",
    "ncei19_n37x25_w122x50_2023v1.tif",
    "ncei19_n37x50_w122x00_2022v1.tif",
    "ncei19_n37x50_w122x25_2022v1.tif",
    "ncei19_n37x50_w122x50_2022v1.tif",
    "ncei19_n37x50_w122x75_2022v1.tif",
    "ncei19_n37x75_w122x00_2022v1.tif",
    "ncei19_n37x75_w122x25_2022v1.tif",
    "ncei19_n37x75_w122x50_2022v1.tif",
    "ncei19_n37x75_w122x75_2022v1.tif",
    "ncei19_n38x00_w122x00_2022v1.tif",
    "ncei19_n38x00_w122x25_2022v1.tif",
    "ncei19_n38x00_w122x50_2022v1.tif",
    "ncei19_n38x00_w122x75_2022v1.tif",
    "ncei19_n38x00_w123x00_2025v1.tif",
    "ncei19_n38x00_w123x25_2025v1.tif",
    "ncei19_n38x00_w123x50_2025v1.tif",
    "ncei19_n38x25_w122x00_2022v1.tif",
    "ncei19_n38x25_w122x25_2022v1.tif",
    "ncei19_n38x25_w122x50_2022v1.tif",
    "ncei19_n38x25_w122x75_2022v1.tif",
    "ncei19_n38x25_w123x00_2025v1.tif",
    "ncei19_n38x25_w123x25_2025v1.tif",
    "ncei19_n38x25_w123x50_2025v1.tif",
]
CUDEM_TILE_URLS = [f"{CUDEM_BASE_URL}/{name}" for name in CUDEM_TILE_NAMES]
CUDEM_GDAL_INPUTS = [f"/vsicurl/{url}" for url in CUDEM_TILE_URLS]

NOS_BAG_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": "noaa_nos_h12109_1m_bag",
        "sourceLabel": "NOAA NOS H12109, 1 m BAG Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12109 Bathymetric Attributed Grid, 1 m, MLLW, Gulf of the Farallones / Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12109.html",
        "role": "High-resolution NOAA BAG survey inset for the shallow part of the Golden Gate approach.",
        "folder": "noaa-nos-h12109",
        "fileName": "H12109_MB_1m_MLLW_1of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12109/BAG/H12109_MB_1m_MLLW_1of2.bag",
        "terrainStem": "noaa_nos_h12109_1m",
        "terrainSize": 1536,
        "terrainMinimum": -32.0,
        "terrainMaximum": -10.0,
        "contourMinimum": -30.0,
        "contourMaximum": -10.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12109 1 m BAG survey patch in MLLW, adding detailed shallow Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12109_2m_bag",
        "sourceLabel": "NOAA NOS H12109, 2 m BAG Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12109 Bathymetric Attributed Grid, 2 m, MLLW, Gulf of the Farallones / Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12109.html",
        "role": "High-resolution NOAA BAG survey inset for the deeper part of the Golden Gate approach.",
        "folder": "noaa-nos-h12109",
        "fileName": "H12109_MB_2m_MLLW_2of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12109/BAG/H12109_MB_2m_MLLW_2of2.bag",
        "terrainStem": "noaa_nos_h12109_2m",
        "terrainSize": 1536,
        "terrainMinimum": -60.0,
        "terrainMaximum": -15.0,
        "contourMinimum": -60.0,
        "contourMaximum": -15.0,
        "contourSimplify": 5,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12109 2 m BAG survey patch in MLLW, adding detailed deeper Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12110_1m_bag",
        "sourceLabel": "NOAA NOS H12110, 1 m BAG south Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12110 Bathymetric Attributed Grid, 1 m, MLLW, south Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12110.html",
        "role": "High-resolution NOAA BAG survey inset for the southern shallow part of the Golden Gate approach.",
        "folder": "noaa-nos-h12110",
        "fileName": "H12110_MB_1m_MLLW_1of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12110/BAG/H12110_MB_1m_MLLW_1of2.bag",
        "terrainStem": "noaa_nos_h12110_1m",
        "terrainSize": 1536,
        "terrainMinimum": -28.0,
        "terrainMaximum": -16.0,
        "contourMinimum": -25.0,
        "contourMaximum": -20.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12110 1 m BAG survey patch in MLLW, adding shallow southern Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12110_2m_bag",
        "sourceLabel": "NOAA NOS H12110, 2 m BAG south Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12110 Bathymetric Attributed Grid, 2 m, MLLW, south Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12110.html",
        "role": "High-resolution NOAA BAG survey inset for the deeper southern Golden Gate approach.",
        "folder": "noaa-nos-h12110",
        "fileName": "H12110_MB_2m_MLLW_2of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12110/BAG/H12110_MB_2m_MLLW_2of2.bag",
        "terrainStem": "noaa_nos_h12110_2m",
        "terrainSize": 1536,
        "terrainMinimum": -60.0,
        "terrainMaximum": -15.0,
        "contourMinimum": -50.0,
        "contourMaximum": -20.0,
        "contourSimplify": 5,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12110 2 m BAG survey patch in MLLW, adding detailed deeper southern Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12111_1m_bag",
        "sourceLabel": "NOAA NOS H12111, 1 m BAG north Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12111 Bathymetric Attributed Grid, 1 m, MLLW, north Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12111.html",
        "role": "High-resolution NOAA BAG survey inset for the shallow northern Golden Gate approach.",
        "folder": "noaa-nos-h12111",
        "fileName": "H12111_MB_1m_MLLW_1of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12111/BAG/H12111_MB_1m_MLLW_1of2.bag",
        "terrainStem": "noaa_nos_h12111_1m",
        "terrainSize": 1536,
        "terrainMinimum": -30.0,
        "terrainMaximum": 2.0,
        "contourMinimum": -20.0,
        "contourMaximum": 0.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12111 1 m BAG survey patch in MLLW, adding shallow northern Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12111_2m_bag",
        "sourceLabel": "NOAA NOS H12111, 2 m BAG north Golden Gate approach bathymetry",
        "sourceName": "NOAA/NOS H12111 Bathymetric Attributed Grid, 2 m, MLLW, north Golden Gate approach",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12111.html",
        "role": "High-resolution NOAA BAG survey inset for the deeper northern Golden Gate approach.",
        "folder": "noaa-nos-h12111",
        "fileName": "H12111_MB_2m_MLLW_2of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12111/BAG/H12111_MB_2m_MLLW_2of2.bag",
        "terrainStem": "noaa_nos_h12111_2m",
        "terrainSize": 1536,
        "terrainMinimum": -40.0,
        "terrainMaximum": -10.0,
        "contourMinimum": -30.0,
        "contourMaximum": -15.0,
        "contourSimplify": 5,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12111 2 m BAG survey patch in MLLW, adding detailed deeper northern Golden Gate approach bathymetry.",
    },
    {
        "sourceId": "noaa_nos_h12112_1m_bag",
        "sourceLabel": "NOAA NOS H12112, 1 m BAG outer Golden Gate bathymetry",
        "sourceName": "NOAA/NOS H12112 Bathymetric Attributed Grid, 1 m, MLLW, Gulf of the Farallones / vicinity of Golden Gate",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12112.html",
        "role": "High-resolution NOAA BAG survey inset for the outer Golden Gate and Gulf of the Farallones approach.",
        "folder": "noaa-nos-h12112",
        "fileName": "H12112_MB_1m_MLLW_1of3.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12112/BAG/H12112_MB_1m_MLLW_1of3.bag",
        "terrainStem": "noaa_nos_h12112_1m",
        "terrainSize": 1536,
        "terrainMinimum": -45.0,
        "terrainMaximum": 2.0,
        "contourMinimum": -40.0,
        "contourMaximum": 0.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12112 1 m BAG survey patch in MLLW, filling a high-detail outer Golden Gate / Gulf of the Farallones gap.",
    },
    {
        "sourceId": "noaa_nos_h12112_2m_bag",
        "sourceLabel": "NOAA NOS H12112, 2 m BAG outer Golden Gate bathymetry",
        "sourceName": "NOAA/NOS H12112 Bathymetric Attributed Grid, 2 m, MLLW, Gulf of the Farallones / vicinity of Golden Gate",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12112.html",
        "role": "High-resolution NOAA BAG survey inset for deeper outer Golden Gate approach terrain.",
        "folder": "noaa-nos-h12112",
        "fileName": "H12112_MB_2m_MLLW_2of3.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12112/BAG/H12112_MB_2m_MLLW_2of3.bag",
        "terrainStem": "noaa_nos_h12112_2m",
        "terrainSize": 1024,
        "terrainMinimum": -80.0,
        "terrainMaximum": -8.0,
        "contourMinimum": -75.0,
        "contourMaximum": -10.0,
        "contourSimplify": 5,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12112 2 m BAG survey patch in MLLW, adding deeper outer Golden Gate / Gulf of the Farallones bathymetry detail.",
    },
    {
        "sourceId": "noaa_nos_h12112_4m_bag",
        "sourceLabel": "NOAA NOS H12112, 4 m BAG outer Golden Gate bathymetry",
        "sourceName": "NOAA/NOS H12112 Bathymetric Attributed Grid, 4 m, MLLW, Gulf of the Farallones / vicinity of Golden Gate",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12112.html",
        "role": "High-resolution NOAA BAG survey inset for the deepest H12112 outer approach patch.",
        "folder": "noaa-nos-h12112",
        "fileName": "H12112_MB_4m_MLLW_3of3.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12112/BAG/H12112_MB_4m_MLLW_3of3.bag",
        "terrainStem": "noaa_nos_h12112_4m",
        "terrainSize": 768,
        "terrainMinimum": -150.0,
        "terrainMaximum": -25.0,
        "contourMinimum": -140.0,
        "contourMaximum": -30.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.0025,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12112 4 m BAG survey patch in MLLW, adding deeper Gulf of the Farallones bathymetry continuity.",
    },
    {
        "sourceId": "noaa_nos_h12113_1m_bag",
        "sourceLabel": "NOAA NOS H12113, 1 m BAG Lake Merced to Shelter Cove bathymetry",
        "sourceName": "NOAA/NOS H12113 Bathymetric Attributed Grid, 1 m, MLLW, Gulf of the Farallones / Lake Merced to Shelter Cove",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12113.html",
        "role": "High-resolution NOAA BAG survey inset south of the Golden Gate along the Gulf of the Farallones shelf.",
        "folder": "noaa-nos-h12113",
        "fileName": "H12113_MB_1m_MLLW_1of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12113/BAG/H12113_MB_1m_MLLW_1of2.bag",
        "terrainStem": "noaa_nos_h12113_1m",
        "terrainSize": 1536,
        "terrainMinimum": -55.0,
        "terrainMaximum": 2.0,
        "contourMinimum": -50.0,
        "contourMaximum": 0.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12113 1 m BAG survey patch in MLLW, adding high-detail shelf bathymetry south of the Golden Gate.",
    },
    {
        "sourceId": "noaa_nos_h12113_2m_bag",
        "sourceLabel": "NOAA NOS H12113, 2 m BAG Lake Merced to Shelter Cove bathymetry",
        "sourceName": "NOAA/NOS H12113 Bathymetric Attributed Grid, 2 m, MLLW, Gulf of the Farallones / Lake Merced to Shelter Cove",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H12113.html",
        "role": "High-resolution NOAA BAG survey inset for the deeper H12113 shelf patch south of the Golden Gate.",
        "folder": "noaa-nos-h12113",
        "fileName": "H12113_MB_2m_MLLW_2of2.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H12113/BAG/H12113_MB_2m_MLLW_2of2.bag",
        "terrainStem": "noaa_nos_h12113_2m",
        "terrainSize": 1024,
        "terrainMinimum": -120.0,
        "terrainMaximum": -8.0,
        "contourMinimum": -115.0,
        "contourMaximum": -10.0,
        "contourSimplify": 6,
        "minDegreesLength": 0.002,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H12113 2 m BAG survey patch in MLLW, improving deeper shelf continuity south of the Golden Gate.",
    },
    {
        "sourceId": "noaa_nos_h11965_vr_bag",
        "sourceLabel": "NOAA NOS H11965, VR BAG Farallon Islands bathymetry",
        "sourceName": "NOAA/NOS H11965 Variable Resolution Bathymetric Attributed Grid, MLLW, Farallon Islands",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H10001-H12000/H11965.html",
        "role": "High-resolution NOAA BAG survey inset around the Farallon Islands.",
        "folder": "noaa-nos-h11965",
        "fileName": "H11965_MB_VR_MLLW_1of1.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H10001-H12000/H11965/BAG/H11965_MB_VR_MLLW_1of1.bag",
        "terrainStem": "noaa_nos_h11965_vr",
        "terrainSize": 1024,
        "terrainMinimum": -140.0,
        "terrainMaximum": -30.0,
        "contourMinimum": -125.0,
        "contourMaximum": -35.0,
        "contourSimplify": 10,
        "minDegreesLength": 0.003,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H11965 VR BAG survey patch in MLLW, adding Farallon Islands bathymetry detail.",
    },
    {
        "sourceId": "noaa_nos_h13334_vr_bag",
        "sourceLabel": "NOAA NOS H13334, VR BAG southeast Farallon bathymetry",
        "sourceName": "NOAA/NOS H13334 Variable Resolution Bathymetric Attributed Grid, MLLW, southeast of Southeast Farallon Island",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H12001-H14000/H13334.html",
        "role": "High-resolution NOAA BAG survey inset southeast of the Farallon Islands.",
        "folder": "noaa-nos-h13334",
        "fileName": "H13334_MB_VR_MLLW_1of1.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H12001-H14000/H13334/BAG/H13334_MB_VR_MLLW_1of1.bag",
        "terrainStem": "noaa_nos_h13334_vr",
        "terrainSize": 1024,
        "terrainMinimum": -240.0,
        "terrainMaximum": -45.0,
        "contourMinimum": -220.0,
        "contourMaximum": -55.0,
        "contourSimplify": 12,
        "minDegreesLength": 0.003,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H13334 VR BAG survey patch in MLLW, adding detail southeast of Southeast Farallon Island.",
    },
    {
        "sourceId": "noaa_nos_w00477_vr_1_bag",
        "sourceLabel": "NOAA NOS W00477, VR BAG Greater Farallones bathymetry 1",
        "sourceName": "NOAA/NOS W00477 Variable Resolution Bathymetric Attributed Grid, MLLW, Greater Farallones 1 of 4",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00477.html",
        "role": "High-resolution NOAA BAG survey inset for a northern Greater Farallones priority area.",
        "folder": "noaa-nos-w00477",
        "fileName": "W00477_MB_VR_MLLW_1of4.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00477/BAG/W00477_MB_VR_MLLW_1of4.bag",
        "terrainStem": "noaa_nos_w00477_vr_1",
        "terrainSize": 1024,
        "terrainMinimum": -850.0,
        "terrainMaximum": -80.0,
        "contourMinimum": -750.0,
        "contourMaximum": -95.0,
        "contourSimplify": 18,
        "minDegreesLength": 0.004,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00477 VR BAG survey patch in MLLW, adding deep Greater Farallones bathymetry detail.",
    },
    {
        "sourceId": "noaa_nos_w00477_vr_2_bag",
        "sourceLabel": "NOAA NOS W00477, VR BAG Greater Farallones bathymetry 2",
        "sourceName": "NOAA/NOS W00477 Variable Resolution Bathymetric Attributed Grid, MLLW, Greater Farallones 2 of 4",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00477.html",
        "role": "High-resolution NOAA BAG survey inset for a shallow Greater Farallones priority area.",
        "folder": "noaa-nos-w00477",
        "fileName": "W00477_MB_VR_MLLW_2of4.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00477/BAG/W00477_MB_VR_MLLW_2of4.bag",
        "terrainStem": "noaa_nos_w00477_vr_2",
        "terrainSize": 1024,
        "terrainMinimum": -90.0,
        "terrainMaximum": -45.0,
        "contourMinimum": -85.0,
        "contourMaximum": -50.0,
        "contourSimplify": 10,
        "minDegreesLength": 0.003,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00477 VR BAG survey patch in MLLW, adding shallow Greater Farallones bathymetry detail.",
    },
    {
        "sourceId": "noaa_nos_w00477_vr_3_bag",
        "sourceLabel": "NOAA NOS W00477, VR BAG Greater Farallones bathymetry 3",
        "sourceName": "NOAA/NOS W00477 Variable Resolution Bathymetric Attributed Grid, MLLW, Greater Farallones 3 of 4",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00477.html",
        "role": "High-resolution NOAA BAG survey inset west of the Golden Gate and Farallon shelf.",
        "folder": "noaa-nos-w00477",
        "fileName": "W00477_MB_VR_MLLW_3of4.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00477/BAG/W00477_MB_VR_MLLW_3of4.bag",
        "terrainStem": "noaa_nos_w00477_vr_3",
        "terrainSize": 1024,
        "terrainMinimum": -180.0,
        "terrainMaximum": -20.0,
        "contourMinimum": -160.0,
        "contourMaximum": -25.0,
        "contourSimplify": 12,
        "minDegreesLength": 0.003,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00477 VR BAG survey patch in MLLW, adding west-of-Golden-Gate Greater Farallones detail.",
    },
    {
        "sourceId": "noaa_nos_w00477_vr_4_bag",
        "sourceLabel": "NOAA NOS W00477, VR BAG Greater Farallones bathymetry 4",
        "sourceName": "NOAA/NOS W00477 Variable Resolution Bathymetric Attributed Grid, MLLW, Greater Farallones 4 of 4",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00477.html",
        "role": "High-resolution NOAA BAG survey inset for a deep southern Greater Farallones priority area.",
        "folder": "noaa-nos-w00477",
        "fileName": "W00477_MB_VR_MLLW_4of4.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00477/BAG/W00477_MB_VR_MLLW_4of4.bag",
        "terrainStem": "noaa_nos_w00477_vr_4",
        "terrainSize": 768,
        "terrainMinimum": -850.0,
        "terrainMaximum": -90.0,
        "contourMinimum": -820.0,
        "contourMaximum": -110.0,
        "contourSimplify": 18,
        "minDegreesLength": 0.004,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00477 VR BAG survey patch in MLLW, adding deep southern Greater Farallones bathymetry detail.",
    },
    {
        "sourceId": "noaa_nos_w00614_vr_bag",
        "sourceLabel": "NOAA NOS W00614, VR BAG sanctuary bathymetry",
        "sourceName": "NOAA/NOS W00614 Variable Resolution Bathymetric Attributed Grid, MLLW, California sanctuary bathymetry",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00614.html",
        "role": "High-resolution NOAA BAG survey inset spanning CBNMS, GFNMS, and MBNMS priority areas.",
        "folder": "noaa-nos-w00614",
        "fileName": "W00614_MB_VR_MLLW_1of1.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00614/BAG/W00614_MB_VR_MLLW_1of1.bag",
        "terrainStem": "noaa_nos_w00614_vr",
        "terrainSize": 1536,
        "terrainMinimum": -560.0,
        "terrainMaximum": -45.0,
        "contourMinimum": -520.0,
        "contourMaximum": -55.0,
        "contourSimplify": 16,
        "minDegreesLength": 0.004,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00614 VR BAG survey patch in MLLW, adding broader sanctuary bathymetry detail across the Farallones-region shelf.",
    },
]

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
        "terrainSize": 4096,
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

USGS_SF_BAY_1M_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": "usgs_sf_bay_1m_north_navd88",
        "sourceLabel": "USGS SF Bay 1 m DEM, north Bay NAVD88",
        "sourceName": "USGS high-resolution 1 m DEM of northern San Francisco Bay, NAVD88",
        "sourceUrl": "https://www.sciencebase.gov/catalog/item/5e1cb737e4b0ecf25c5f0bf6",
        "role": "High-resolution Bay-interior DEM for northern San Francisco Bay.",
        "folder": "usgs-sf-bay-1m-dem/navd88/north",
        "zipName": None,
        "datasetName": "NorthSFBay_DEM_Mosaic_NAVD88_1m.tif",
        "terrainStem": "usgs_sf_bay_1m_north_navd88",
        "terrainSize": 4096,
        "terrainMinimum": -45.0,
        "terrainMaximum": 8.0,
        "contourMinimum": -40.0,
        "contourMaximum": 5.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "note": "USGS 1 m NAVD88 DEM inset for northern San Francisco Bay. This is intended to sharpen Bay-floor relief and near-modern waterline behavior once the large source file is present locally.",
    },
    {
        "sourceId": "usgs_sf_bay_1m_central_navd88",
        "sourceLabel": "USGS SF Bay 1 m DEM, central Bay NAVD88",
        "sourceName": "USGS high-resolution 1 m DEM of central San Francisco Bay, NAVD88",
        "sourceUrl": "https://www.sciencebase.gov/catalog/item/607df15ad34e8564d67e3ae9",
        "role": "High-resolution Bay-interior DEM for central San Francisco Bay.",
        "folder": "usgs-sf-bay-1m-dem/navd88/central",
        "zipName": "CentralSFBay_DEM_Mosaic_NAVD88_1M.zip",
        "datasetName": "CentralSFBay_DEM_Mosaic_NAVD88_1M.tif",
        "terrainStem": "usgs_sf_bay_1m_central_navd88",
        "terrainSize": 4096,
        "terrainMinimum": -45.0,
        "terrainMaximum": 8.0,
        "contourMinimum": -40.0,
        "contourMaximum": 5.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "note": "USGS 1 m NAVD88 DEM inset for central San Francisco Bay. This is intended to sharpen Bay-floor relief and near-modern waterline behavior once the large source file is present locally.",
    },
    {
        "sourceId": "usgs_sf_bay_1m_south_navd88",
        "sourceLabel": "USGS SF Bay 1 m DEM, south Bay NAVD88",
        "sourceName": "USGS high-resolution 1 m DEM of south San Francisco Bay, NAVD88",
        "sourceUrl": "https://www.sciencebase.gov/catalog/item/607df17bd34e8564d67e3af0",
        "role": "High-resolution Bay-interior DEM for south San Francisco Bay.",
        "folder": "usgs-sf-bay-1m-dem/navd88/south",
        "zipName": "SouthSFBay_DEM_Mosaic_NAVD88_1m.zip",
        "datasetName": "SouthSFBay_DEM_Mosaic_NAVD88_1m.tif",
        "terrainStem": "usgs_sf_bay_1m_south_navd88",
        "terrainSize": 4096,
        "terrainMinimum": -35.0,
        "terrainMaximum": 8.0,
        "contourMinimum": -30.0,
        "contourMaximum": 5.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "note": "USGS 1 m NAVD88 DEM inset for south San Francisco Bay. This is intended to sharpen Bay-floor relief and near-modern waterline behavior once the large source file is present locally.",
    },
    {
        "sourceId": "usgs_sf_bay_1m_south_mllw",
        "sourceLabel": "USGS SF Bay 1 m DEM, south Bay MLLW",
        "sourceName": "USGS high-resolution 1 m DEM of south San Francisco Bay, MLLW",
        "sourceUrl": "https://www.sciencebase.gov/catalog/item/607df116d34e8564d67e3ae6",
        "role": "High-resolution Bay-interior DEM for south San Francisco Bay, used as a visual-detail fallback while the NAVD88 package is unavailable from ScienceBase.",
        "folder": "usgs-sf-bay-1m-dem/mllw/south",
        "zipName": "SouthSFBay_DEM_Mosaic_MLLW_1m.zip",
        "datasetName": "SouthSFBay_DEM_Mosaic_MLLW_1m.tif",
        "terrainStem": "usgs_sf_bay_1m_south_mllw",
        "terrainSize": 4096,
        "terrainMinimum": -35.0,
        "terrainMaximum": 8.0,
        "contourMinimum": -30.0,
        "contourMaximum": 5.0,
        "contourSimplify": 4,
        "minDegreesLength": 0.0015,
        "note": "USGS 1 m MLLW DEM inset for south San Francisco Bay. It sharpens visible Bay-floor relief, but it needs tidal-datum conversion before exact sea-level alignment with NAVD88 sources.",
    },
]

NOAA_OCM_AREA_A_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": f"noaa_ocm_area_a_{survey.lower()}_1m",
        "sourceLabel": f"NOAA OCM Area A {survey}, 1 m Central Bay source survey",
        "sourceName": f"NOAA Office for Coastal Management San Francisco Bay Area A 1 m bathymetry tile {survey}",
        "sourceUrl": "https://www.fisheries.noaa.gov/inport/item/47860",
        "role": "High-resolution 1 m NOAA OCM source-survey tile used in the central San Francisco Bay bathymetry compilation.",
        "folder": "noaa-ocm-sf-bay-area-a",
        "fileName": f"{survey}_1m.tif",
        "url": f"https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/SF_mbs_areaA_2014_8500/{survey}_1m.tif",
        "stacUrl": f"https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/SF_mbs_areaA_2014_8500/stac/{survey}_1m.json",
        "terrainStem": f"noaa_ocm_area_a_{survey.lower()}_1m",
        "terrainSize": 3072,
        "terrainMinimum": -70.0,
        "terrainMaximum": 5.0,
        "contourMinimum": -65.0,
        "contourMaximum": 2.0,
        "contourSimplify": 2,
        "minDegreesLength": 0.0008,
        "sourceNoData": 1_000_000.0,
        "note": f"NOAA OCM Area A 1 m source-survey tile {survey} in central San Francisco Bay. This is a real source grid from NOAA's public S3 archive, not the ScienceBase stitched USGS Bay DEM package.",
    }
    for survey in ("CA1B08", "CA1B09", "CA1B22", "CA1B24", "CA1B26", "NA1B15", "NA1B23")
]

NOAA_OCM_AREA_A_INTERFEROMETRIC_TILES: tuple[str, ...] = (
    "CA1B01",
    "CA1B02",
    "CA1B03",
    "CA1B04",
    "CA1B05",
    "CA1B06",
    "CA1B07",
    "CA1B10",
    "CA1B11",
    "CA1B12",
    "CA1B13",
    "CA1B14",
    "CA1B15",
    "CA1B16",
    "CA1B17",
    "CA1B18",
    "CA1B19",
    "CA1B20",
    "CA1B21",
    "CA1B23",
    "CA1B25",
    "CA1B27",
    "CA1B28",
    "CA1B29",
    "CA1B30",
    "CA1B31",
    "CA1B32",
    "CA1B33",
    "CA1B34",
    "CA2B01",
    "NA1B01",
    "NA1B02",
    "NA1B03",
    "NA1B04",
    "NA1B05",
    "NA1B06",
    "NA1B07-08-09",
    "NA1B10",
    "NA1B11",
    "NA1B12",
    "NA1B13",
    "NA1B14",
    "NA1B16",
    "NA1B17",
    "NA1B18",
    "NA1B19",
    "NA1B20",
    "NA1B21",
    "NA1B22",
    "NA1B24",
    "NA1B25",
    "NA1B26",
    "NA1B27",
    "NA2B01",
    "NA2B02",
    "NA2B03",
    "NA2B04",
    "NA2B05",
    "SA1B01",
    "SA1B02",
    "SA1B03",
    "SA1B04",
    "SA1B05",
    "SA1B06",
    "SA1B07",
    "SA1B08",
    "SA1B09",
    "SA1B10",
    "SA1B11",
    "SA1B12",
    "SA2B01",
    "SA2B02",
    "SA2B03",
)

NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC: dict[str, Any] = {
    "sourceId": "noaa_ocm_area_a_interferometric_1m_mosaic",
    "sourceLabel": "NOAA OCM Area A interferometric 1 m Bay-floor mosaic",
    "sourceName": "NOAA Office for Coastal Management San Francisco Bay Area A 1 m interferometric bathymetry",
    "sourceUrl": "https://www.fisheries.noaa.gov/inport/item/47862",
    "indexUrl": "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/SF_sss_areaA_2014_9715/index.html",
    "urlPrefix": "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/SF_sss_areaA_2014_9715",
    "role": "Broad 1 m interferometric source-survey mosaic for much of San Francisco Bay Area A.",
    "folder": "noaa-ocm-sf-bay-area-a-interferometric",
    "terrainStem": "noaa_ocm_area_a_interferometric_1m_mosaic",
    "terrainSize": 5120,
    "terrainMinimum": -70.0,
    "terrainMaximum": 5.0,
    "contourMinimum": -65.0,
    "contourMaximum": 2.0,
    "contourSimplify": 3,
    "minDegreesLength": 0.0012,
    "sourceNoData": 1_000_000.0,
    "note": "NOAA OCM Area A 1 m interferometric bathymetry mosaic for San Francisco Bay. This source covers many more shallow Bay blocks than the multibeam subset, but NOAA notes the interferometric data are less accurate than multibeam in deeper water.",
}

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
    {
        "name": "NOAA CUDEM 1/9 arc-second California topobathymetry",
        "url": "https://coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/",
        "role": "Sharper broad Bay/coast topobathymetry inset built from remote California COG tiles.",
    },
    *[
        {
            "name": block["sourceName"],
            "url": block["sourceUrl"],
            "role": block["role"],
        }
        for block in NOS_BAG_BLOCKS
    ],
    *[
        {
            "name": block["sourceName"],
            "url": block["sourceUrl"],
            "role": block["role"],
        }
        for block in BATHYMETRY_BLOCKS
    ],
    *[
        {
            "name": block["sourceName"],
            "url": block["sourceUrl"],
            "role": block["role"],
        }
        for block in USGS_SF_BAY_1M_BLOCKS
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


def prepare_noaa_cudem_subset() -> None:
    if CUDEM_TIF.exists():
        print(f"Using existing source file: {CUDEM_TIF}")
        return

    CUDEM_DIR.mkdir(parents=True, exist_ok=True)
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=DEFLATE",
        "-co",
        "TILED=YES",
        "-t_srs",
        "EPSG:4326",
        "-te",
        str(BBOX["west"]),
        str(BBOX["south"]),
        str(BBOX["east"]),
        str(BBOX["north"]),
        "-ts",
        str(CUDEM_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-srcnodata",
        "-9999",
        "-dstnodata",
        "-9999",
        *CUDEM_GDAL_INPUTS,
        str(CUDEM_TIF),
    ])


def download_usgs_ds684_dem4() -> None:
    if DS684_TIF.exists():
        print(f"Using existing source file: {DS684_TIF}")
        return
    download_url(DS684_DEM4_URL, DS684_ZIP)
    run(["unzip", "-o", str(DS684_ZIP), "-d", str(DS684_DIR)])


def bathymetry_block_dir(block: dict[str, Any]) -> Path:
    return RAW_DIR / str(block["folder"])


def nos_bag_block_dir(block: dict[str, Any]) -> Path:
    return RAW_DIR / str(block.get("folder", NOS_BAG_DEFAULT_DIR.name))


def nos_bag_dataset(block: dict[str, Any]) -> Path:
    return nos_bag_block_dir(block) / str(block["fileName"])


def noaa_ocm_area_a_block_dir(block: dict[str, Any]) -> Path:
    return RAW_DIR / str(block["folder"])


def noaa_ocm_area_a_dataset(block: dict[str, Any]) -> Path:
    return noaa_ocm_area_a_block_dir(block) / str(block["fileName"])


def noaa_ocm_area_a_contours_raw(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_raw.geojson"


def noaa_ocm_area_a_contours_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_wgs84.geojson"


def noaa_ocm_area_a_terrain_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_terrain_wgs84.tif"


def noaa_ocm_area_a_elevation_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_elevation.png"


def noaa_ocm_area_a_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_color.png"


def noaa_ocm_area_a_relief_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_relief.png"


def noaa_ocm_area_a_composite_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_composite.png"


def noaa_ocm_area_a_interferometric_dir() -> Path:
    return RAW_DIR / str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["folder"])


def noaa_ocm_area_a_interferometric_dataset(tile_id: str) -> Path:
    return noaa_ocm_area_a_interferometric_dir() / f"{tile_id}_1m.tif"


def noaa_ocm_area_a_interferometric_vrt() -> Path:
    return WORK_DIR / "noaa_ocm_area_a_interferometric_1m_mosaic.vrt"


def noaa_ocm_area_a_interferometric_contours_raw() -> Path:
    return WORK_DIR / "noaa_ocm_area_a_interferometric_1m_mosaic_contours_raw.geojson"


def noaa_ocm_area_a_interferometric_contours_wgs84() -> Path:
    return WORK_DIR / "noaa_ocm_area_a_interferometric_1m_mosaic_contours_wgs84.geojson"


def noaa_ocm_area_a_interferometric_contour_grid_wgs84() -> Path:
    return WORK_DIR / "noaa_ocm_area_a_interferometric_1m_mosaic_contour_grid_wgs84.tif"


def noaa_ocm_area_a_interferometric_terrain_wgs84() -> Path:
    return WORK_DIR / "noaa_ocm_area_a_interferometric_1m_mosaic_terrain_wgs84.tif"


def noaa_ocm_area_a_interferometric_elevation_png() -> Path:
    return TERRAIN_PUBLIC_DIR / f"{NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC['terrainStem']}_elevation.png"


def noaa_ocm_area_a_interferometric_texture_png() -> Path:
    return TERRAIN_PUBLIC_DIR / f"{NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC['terrainStem']}_color.png"


def noaa_ocm_area_a_interferometric_relief_texture_png() -> Path:
    return TERRAIN_PUBLIC_DIR / f"{NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC['terrainStem']}_relief.png"


def noaa_ocm_area_a_interferometric_composite_texture_png() -> Path:
    return TERRAIN_PUBLIC_DIR / f"{NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC['terrainStem']}_composite.png"


def nos_bag_contours_raw(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_raw.geojson"


def nos_bag_contours_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_wgs84.geojson"


def nos_bag_terrain_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_terrain_wgs84.tif"


def nos_bag_elevation_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_elevation.png"


def nos_bag_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_color.png"


def nos_bag_relief_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_relief.png"


def nos_bag_composite_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_composite.png"


def download_nos_bag_blocks() -> None:
    for block in NOS_BAG_BLOCKS:
        download_url(str(block["url"]), nos_bag_dataset(block))


def download_noaa_ocm_area_a_blocks() -> None:
    for block in NOAA_OCM_AREA_A_BLOCKS:
        download_url(str(block["url"]), noaa_ocm_area_a_dataset(block))


def download_noaa_ocm_area_a_interferometric_tiles() -> None:
    prefix = str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["urlPrefix"])
    for tile_id in NOAA_OCM_AREA_A_INTERFEROMETRIC_TILES:
        download_url(f"{prefix}/{tile_id}_1m.tif", noaa_ocm_area_a_interferometric_dataset(tile_id))


def build_noaa_ocm_area_a_interferometric_vrt() -> None:
    run([
        "gdalbuildvrt",
        "-q",
        "-overwrite",
        "-srcnodata",
        str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceNoData"]),
        "-vrtnodata",
        str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceNoData"]),
        str(noaa_ocm_area_a_interferometric_vrt()),
        *[str(noaa_ocm_area_a_interferometric_dataset(tile_id)) for tile_id in NOAA_OCM_AREA_A_INTERFEROMETRIC_TILES],
    ])


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
    if not bathymetry_block_dataset(block).exists():
        download_url(str(block["zipUrl"]), bathymetry_block_zip(block))
        run(["unzip", "-o", str(bathymetry_block_zip(block)), "-d", str(bathymetry_block_dir(block))])
    else:
        print(f"Using existing source file: {bathymetry_block_dataset(block)}")

    for zip_name in block.get("backscatterZipNames", []):
        if not bathymetry_block_backscatter_dataset(block, str(zip_name)).exists():
            download_url(bathymetry_block_backscatter_url(block, str(zip_name)), bathymetry_block_backscatter_zip(block, str(zip_name)))
            run(["unzip", "-o", str(bathymetry_block_backscatter_zip(block, str(zip_name))), "-d", str(bathymetry_block_dir(block))])
        else:
            print(f"Using existing source file: {bathymetry_block_backscatter_dataset(block, str(zip_name))}")

    if block.get("characterZipName"):
        if not bathymetry_block_character_dataset(block).exists():
            download_url(bathymetry_block_character_url(block), bathymetry_block_character_zip(block))
            run(["unzip", "-o", str(bathymetry_block_character_zip(block)), "-d", str(bathymetry_block_dir(block))])
        else:
            print(f"Using existing source file: {bathymetry_block_character_dataset(block)}")


def download_bathymetry_blocks() -> None:
    for block in BATHYMETRY_BLOCKS:
        download_bathymetry_block(block)


def usgs_sf_bay_1m_block_dir(block: dict[str, Any]) -> Path:
    return RAW_DIR / str(block["folder"])


def usgs_sf_bay_1m_zip(block: dict[str, Any]) -> Path | None:
    if not block.get("zipName"):
        return None
    return usgs_sf_bay_1m_block_dir(block) / str(block["zipName"])


def usgs_sf_bay_1m_dataset(block: dict[str, Any]) -> Path:
    return usgs_sf_bay_1m_block_dir(block) / str(block["datasetName"])


def usgs_sf_bay_1m_contours_raw(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_raw.geojson"


def usgs_sf_bay_1m_contours_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_contours_wgs84.geojson"


def usgs_sf_bay_1m_terrain_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_terrain_wgs84.tif"


def usgs_sf_bay_1m_elevation_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_elevation.png"


def usgs_sf_bay_1m_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_color.png"


def usgs_sf_bay_1m_relief_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_relief.png"


def usgs_sf_bay_1m_composite_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_composite.png"


def prepare_usgs_sf_bay_1m_blocks() -> None:
    for block in USGS_SF_BAY_1M_BLOCKS:
        dataset = usgs_sf_bay_1m_dataset(block)
        if dataset.exists():
            continue
        zip_path = usgs_sf_bay_1m_zip(block)
        if zip_path is not None and zip_path.exists():
            run(["unzip", "-o", str(zip_path), "-d", str(usgs_sf_bay_1m_block_dir(block))])


def active_usgs_sf_bay_1m_blocks() -> list[dict[str, Any]]:
    return [
        block
        for block in USGS_SF_BAY_1M_BLOCKS
        if usgs_sf_bay_1m_dataset(block).exists()
    ]


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
    run([
        "gdal_contour",
        "-q",
        "-a",
        "elevation_m",
        "-fl",
        *levels,
        str(CUDEM_TIF),
        str(CUDEM_CONTOURS_RAW),
    ])
    run([
        "ogr2ogr",
        "-f",
        "GeoJSON",
        "-simplify",
        "0.0008",
        str(CUDEM_CONTOURS_BROWSER),
        str(CUDEM_CONTOURS_RAW),
    ])

    for block in NOS_BAG_BLOCKS:
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
            "-b",
            "1",
            "-a",
            "elevation_m",
            "-snodata",
            str(block["sourceNoData"]),
            "-fl",
            *block_levels,
            str(nos_bag_dataset(block)),
            str(nos_bag_contours_raw(block)),
        ])
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-simplify",
            str(block["contourSimplify"]),
            str(nos_bag_contours_wgs84(block)),
            str(nos_bag_contours_raw(block)),
        ])

    for block in NOAA_OCM_AREA_A_BLOCKS:
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
            "-snodata",
            str(block["sourceNoData"]),
            "-fl",
            *block_levels,
            str(noaa_ocm_area_a_dataset(block)),
            str(noaa_ocm_area_a_contours_raw(block)),
        ])
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-simplify",
            str(block["contourSimplify"]),
            str(noaa_ocm_area_a_contours_wgs84(block)),
            str(noaa_ocm_area_a_contours_raw(block)),
        ])

    block = NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC
    block_levels = [
        str(level)
        for level in contour_levels()
        if float(block["contourMinimum"]) <= level <= float(block["contourMaximum"])
    ]
    if block_levels:
        build_noaa_ocm_area_a_interferometric_vrt()
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
            "-ot",
            "Float32",
            "-srcnodata",
            str(block["sourceNoData"]),
            "-dstnodata",
            "-9999",
            str(noaa_ocm_area_a_interferometric_vrt()),
            str(noaa_ocm_area_a_interferometric_contour_grid_wgs84()),
        ])
        run([
            "gdal_contour",
            "-q",
            "-a",
            "elevation_m",
            "-snodata",
            "-9999",
            "-fl",
            *block_levels,
            str(noaa_ocm_area_a_interferometric_contour_grid_wgs84()),
            str(noaa_ocm_area_a_interferometric_contours_raw()),
        ])
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-simplify",
            str(block["contourSimplify"]),
            str(noaa_ocm_area_a_interferometric_contours_wgs84()),
            str(noaa_ocm_area_a_interferometric_contours_raw()),
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

    for block in active_usgs_sf_bay_1m_blocks():
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
            str(usgs_sf_bay_1m_dataset(block)),
            str(usgs_sf_bay_1m_contours_raw(block)),
        ])
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            "-t_srs",
            "EPSG:4326",
            "-simplify",
            str(block["contourSimplify"]),
            str(usgs_sf_bay_1m_contours_wgs84(block)),
            str(usgs_sf_bay_1m_contours_raw(block)),
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
    return math.isfinite(value) and -9000 < value < 1_000_000


def clamp_byte(value: float) -> int:
    return max(0, min(255, round(value)))


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
    edge_fade_pixels: int = 0,
    low_detail_alpha_floor: int = 255,
) -> None:
    source = Image.open(source_path)
    heights = np.asarray(source, dtype=np.float32)
    if heights.ndim > 2:
        heights = heights[:, :, 0]

    image_height, width = heights.shape
    valid = np.isfinite(heights) & (heights > -9000) & (heights < 1_000_000)
    safe_heights = np.where(valid, heights, 0.0).astype(np.float32)

    normalized = np.clip((safe_heights - minimum) / (maximum - minimum), 0.0, 1.0)
    encoded = np.rint(normalized * 16_777_215).astype(np.uint32)
    elevation_pixels = np.zeros((image_height, width, 3), dtype=np.uint8)
    elevation_pixels[:, :, 0] = ((encoded >> 16) & 255).astype(np.uint8)
    elevation_pixels[:, :, 1] = ((encoded >> 8) & 255).astype(np.uint8)
    elevation_pixels[:, :, 2] = (encoded & 255).astype(np.uint8)
    elevation_pixels[~valid] = 0

    stop_heights = np.array([stop[0] for stop in TERRAIN_COLOR_STOPS], dtype=np.float32)
    stop_colors = np.array([stop[1] for stop in TERRAIN_COLOR_STOPS], dtype=np.float32)
    base = np.stack(
        [np.interp(safe_heights, stop_heights, stop_colors[:, channel]) for channel in range(3)],
        axis=-1,
    ).astype(np.float32)
    base[~valid] = 0

    if edge_fade_pixels > 0:
        x_edges = np.minimum(np.arange(width), np.arange(width)[::-1])
        y_edges = np.minimum(np.arange(image_height), np.arange(image_height)[::-1])
        edge_distance = np.minimum(y_edges[:, None], x_edges[None, :])
        alpha = np.rint(np.clip(edge_distance / edge_fade_pixels, 0.0, 1.0) * 255).astype(np.uint8)
    else:
        alpha = np.full((image_height, width), 255, dtype=np.uint8)
    alpha = np.where(valid, alpha, 0).astype(np.uint8)

    pad_radius = 3
    padded_heights = np.pad(safe_heights, pad_radius, mode="edge")
    padded_valid = np.pad(valid, pad_radius, mode="edge")

    def sample(dx: int, dy: int) -> np.ndarray:
        y0 = pad_radius + dy
        x0 = pad_radius + dx
        sampled_heights = padded_heights[y0:y0 + image_height, x0:x0 + width]
        sampled_valid = padded_valid[y0:y0 + image_height, x0:x0 + width]
        return np.where(sampled_valid, sampled_heights, safe_heights)

    west = sample(-1, 0)
    east = sample(1, 0)
    north = sample(0, -1)
    south = sample(0, 1)
    dz_dx = east - west
    dz_dy = south - north
    slope = np.hypot(dz_dx, dz_dy)

    normal_x = -dz_dx
    normal_y = -dz_dy
    normal_z = 42.0
    normal_length = np.sqrt((normal_x * normal_x) + (normal_y * normal_y) + (normal_z * normal_z))
    shade = ((normal_x * -0.48) + (normal_y * -0.58) + (normal_z * 0.66)) / normal_length
    shade = np.clip((shade * 0.5) + 0.5, 0.0, 1.0)

    local_min = safe_heights.copy()
    local_max = safe_heights.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            neighbor = sample(dx, dy)
            local_min = np.minimum(local_min, neighbor)
            local_max = np.maximum(local_max, neighbor)
    roughness = local_max - local_min
    curvature = safe_heights - ((west + east + north + south) / 4.0)

    broad_neighbors = [
        sample(-3, -3),
        sample(0, -3),
        sample(3, -3),
        sample(-3, 0),
        sample(3, 0),
        sample(-3, 3),
        sample(0, 3),
        sample(3, 3),
    ]
    broad_min = broad_neighbors[0].copy()
    broad_max = broad_neighbors[0].copy()
    for neighbor in broad_neighbors[1:]:
        broad_min = np.minimum(broad_min, neighbor)
        broad_max = np.maximum(broad_max, neighbor)
    broad_roughness = broad_max - broad_min
    broad_curvature = safe_heights - ((sample(-3, 0) + sample(3, 0) + sample(0, -3) + sample(0, 3)) / 4.0)

    underwater = safe_heights < 0
    depth_boost = np.clip(np.abs(safe_heights) / 140.0, 0.0, 1.0)
    relief_contrast = np.where(underwater, 0.78 + depth_boost * 0.32, 0.9)
    relief_brightness = np.where(
        underwater,
        0.34 + shade * 0.92 + np.minimum(0.28, slope * 0.018),
        0.42 + shade * 0.82 + np.minimum(0.22, slope * 0.012),
    )
    relief = ((base - 128.0) * relief_contrast[:, :, None] + 128.0) * relief_brightness[:, :, None]

    slope_signal = np.clip(slope / np.where(underwater, 34.0, 92.0), 0.0, 1.0)
    rough_signal = np.clip(roughness / np.where(underwater, 65.0, 140.0), 0.0, 1.0)
    ridge_signal = np.clip(curvature / np.where(underwater, 22.0, 48.0), 0.0, 1.0)
    hollow_signal = np.clip(-curvature / np.where(underwater, 22.0, 48.0), 0.0, 1.0)
    broad_rough_signal = np.clip(broad_roughness / np.where(underwater, 95.0, 220.0), 0.0, 1.0)
    broad_ridge_signal = np.clip(broad_curvature / np.where(underwater, 34.0, 72.0), 0.0, 1.0)
    broad_hollow_signal = np.clip(-broad_curvature / np.where(underwater, 34.0, 72.0), 0.0, 1.0)

    def mix(image: np.ndarray, color: tuple[int, int, int], amount: np.ndarray) -> np.ndarray:
        color_array = np.array(color, dtype=np.float32)
        return image + (color_array - image) * np.clip(amount, 0.0, 1.0)[:, :, None]

    fine_detail_signal = np.maximum.reduce([slope_signal * 0.86, rough_signal * 0.78, ridge_signal * 0.96])
    broad_form_signal = np.maximum.reduce([broad_rough_signal * 0.62, broad_ridge_signal * 0.78, broad_hollow_signal * 0.72])
    if low_detail_alpha_floor < 255:
        detail_alpha = np.clip(np.maximum(fine_detail_signal, broad_form_signal) / 0.45, 0.0, 1.0)
        floor = max(0.0, min(1.0, low_detail_alpha_floor / 255.0))
        alpha = np.rint(alpha.astype(np.float32) * (floor + ((1.0 - floor) * detail_alpha))).astype(np.uint8)

    composite_water = relief.copy()
    composite_water = mix(composite_water, (56, 183, 198), 0.08 + slope_signal * 0.15 + broad_rough_signal * 0.07)
    composite_water = mix(composite_water, (10, 28, 62), hollow_signal * 0.22 + broad_hollow_signal * 0.24)
    composite_water = mix(composite_water, (30, 17, 72), broad_hollow_signal * 0.16)
    composite_water = mix(composite_water, (247, 215, 126), ridge_signal * 0.34 + broad_ridge_signal * 0.28 + rough_signal * 0.10)
    composite_water = mix(composite_water, (238, 246, 226), fine_detail_signal * 0.14 + broad_form_signal * 0.10)
    water_contrast = 1.04 + fine_detail_signal * 0.30 + broad_form_signal * 0.18
    water_brightness = 0.92 + (shade - 0.5) * 0.22 - hollow_signal * 0.10 - broad_hollow_signal * 0.10
    composite_water = ((composite_water - 128.0) * water_contrast[:, :, None] + 128.0) * water_brightness[:, :, None]

    land_detail = np.minimum(0.34, slope_signal * 0.18 + rough_signal * 0.10 + broad_rough_signal * 0.08)
    composite_land = relief + (base - relief) * 0.18
    composite_land = mix(composite_land, (248, 248, 240), land_detail)
    composite_land = composite_land * (0.96 + shade * 0.12)[:, :, None]
    composite = np.where(underwater[:, :, None], composite_water, composite_land)

    texture_pixels = np.dstack((np.clip(np.rint(base), 0, 255).astype(np.uint8), alpha))
    relief_pixels = np.dstack((np.clip(np.rint(relief), 0, 255).astype(np.uint8), alpha))
    composite_pixels = np.dstack((np.clip(np.rint(composite), 0, 255).astype(np.uint8), alpha))
    texture_pixels[~valid] = 0
    relief_pixels[~valid] = 0
    composite_pixels[~valid] = 0

    Image.fromarray(elevation_pixels, "RGB").save(elevation_path)
    Image.fromarray(texture_pixels, "RGBA").save(texture_path)
    Image.fromarray(relief_pixels, "RGBA").save(relief_texture_path)
    Image.fromarray(composite_pixels, "RGBA").save(composite_texture_path)


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
    source_confidence_texture_png: Path | None = None,
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
    if source_confidence_texture_png is not None and source_confidence_texture_png.exists():
        textures["sourceConfidence"] = public_url(source_confidence_texture_png)

    source_kind = terrain_source_kind(source_id)

    return {
        "sourceId": source_id,
        "sourceLabel": source_label_value,
        "elevationData": public_url(elevation_png),
        "texture": public_url(texture_png),
        "textures": textures,
        "bounds": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
        "heightRangeMeters": [minimum, maximum],
        "qualityTier": source_kind["qualityTier"],
        "renderPriority": source_kind["renderPriority"],
        "resolutionMeters": source_kind["resolutionMeters"],
        "verticalExaggeration": TERRAIN_VERTICAL_EXAGGERATION,
        "elevationDecoder": {
            "rScaler": ((maximum - minimum) / 16_777_215.0) * 65_536 * TERRAIN_VERTICAL_EXAGGERATION,
            "gScaler": ((maximum - minimum) / 16_777_215.0) * 256 * TERRAIN_VERTICAL_EXAGGERATION,
            "bScaler": ((maximum - minimum) / 16_777_215.0) * TERRAIN_VERTICAL_EXAGGERATION,
            "offset": minimum * TERRAIN_VERTICAL_EXAGGERATION,
        },
        "note": note,
    }


def terrain_source_kind(source_id: str) -> dict[str, Any]:
    if source_id.startswith("noaa_crm") or source_id.startswith("etopo"):
        return {"qualityTier": "broad", "renderPriority": 10, "resolutionMeters": None}
    if source_id.startswith("noaa_cudem"):
        return {"qualityTier": "broad", "renderPriority": 20, "resolutionMeters": None}
    if source_id.startswith("best_available"):
        return {"qualityTier": "bay_mosaic", "renderPriority": 35, "resolutionMeters": 20}
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        return {"qualityTier": "bay_mosaic", "renderPriority": 40, "resolutionMeters": 1}
    if source_id.startswith("usgs_sf_bay_1m") or source_id.startswith("noaa_ocm_area_a"):
        return {"qualityTier": "source_survey", "renderPriority": 70, "resolutionMeters": 1}
    if source_id.startswith("noaa_nos"):
        resolution = 1 if "_1m" in source_id else 2 if "_2m" in source_id else None
        return {"qualityTier": "source_survey", "renderPriority": 80, "resolutionMeters": resolution}
    if source_id.startswith("usgs_csmp") or source_id.startswith("usgs_ds684"):
        return {"qualityTier": "nearshore_detail", "renderPriority": 85, "resolutionMeters": 2}
    if "farallon" in source_id or "rittenburg" in source_id:
        resolution = 2 if "rittenburg" in source_id else 10 if "farallon_escarpment" in source_id else None
        return {"qualityTier": "offshore_survey", "renderPriority": 90, "resolutionMeters": resolution}
    return {"qualityTier": "reference", "renderPriority": 50, "resolutionMeters": None}


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
        18,
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
        24,
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


def generate_usgs_sf_bay_1m_terrain_asset(block: dict[str, Any]) -> dict[str, Any]:
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
        "-ot",
        "Float32",
        "-dstnodata",
        "-9999",
        str(usgs_sf_bay_1m_dataset(block)),
        str(usgs_sf_bay_1m_terrain_wgs84(block)),
    ])
    write_terrain_pngs_from_wgs84(
        usgs_sf_bay_1m_terrain_wgs84(block),
        usgs_sf_bay_1m_elevation_png(block),
        usgs_sf_bay_1m_texture_png(block),
        usgs_sf_bay_1m_relief_texture_png(block),
        usgs_sf_bay_1m_composite_texture_png(block),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        24,
    )
    return terrain_metadata(
        str(block["sourceId"]),
        source_label(str(block["sourceId"])),
        usgs_sf_bay_1m_terrain_wgs84(block),
        usgs_sf_bay_1m_elevation_png(block),
        usgs_sf_bay_1m_texture_png(block),
        usgs_sf_bay_1m_relief_texture_png(block),
        usgs_sf_bay_1m_composite_texture_png(block),
        None,
        None,
        None,
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        str(block["note"]),
    )


def generate_noaa_ocm_area_a_terrain_asset(block: dict[str, Any]) -> dict[str, Any]:
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
        "-ot",
        "Float32",
        "-srcnodata",
        str(block["sourceNoData"]),
        "-dstnodata",
        "-9999",
        str(noaa_ocm_area_a_dataset(block)),
        str(noaa_ocm_area_a_terrain_wgs84(block)),
    ])
    write_terrain_pngs_from_wgs84(
        noaa_ocm_area_a_terrain_wgs84(block),
        noaa_ocm_area_a_elevation_png(block),
        noaa_ocm_area_a_texture_png(block),
        noaa_ocm_area_a_relief_texture_png(block),
        noaa_ocm_area_a_composite_texture_png(block),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        24,
    )
    return terrain_metadata(
        str(block["sourceId"]),
        source_label(str(block["sourceId"])),
        noaa_ocm_area_a_terrain_wgs84(block),
        noaa_ocm_area_a_elevation_png(block),
        noaa_ocm_area_a_texture_png(block),
        noaa_ocm_area_a_relief_texture_png(block),
        noaa_ocm_area_a_composite_texture_png(block),
        None,
        None,
        None,
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        str(block["note"]),
    )


def generate_noaa_ocm_area_a_interferometric_terrain_asset() -> dict[str, Any]:
    block = NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC
    build_noaa_ocm_area_a_interferometric_vrt()
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
        "-ot",
        "Float32",
        "-srcnodata",
        str(block["sourceNoData"]),
        "-dstnodata",
        "-9999",
        str(noaa_ocm_area_a_interferometric_vrt()),
        str(noaa_ocm_area_a_interferometric_terrain_wgs84()),
    ])
    write_terrain_pngs_from_wgs84(
        noaa_ocm_area_a_interferometric_terrain_wgs84(),
        noaa_ocm_area_a_interferometric_elevation_png(),
        noaa_ocm_area_a_interferometric_texture_png(),
        noaa_ocm_area_a_interferometric_relief_texture_png(),
        noaa_ocm_area_a_interferometric_composite_texture_png(),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        22,
    )
    return terrain_metadata(
        str(block["sourceId"]),
        source_label(str(block["sourceId"])),
        noaa_ocm_area_a_interferometric_terrain_wgs84(),
        noaa_ocm_area_a_interferometric_elevation_png(),
        noaa_ocm_area_a_interferometric_texture_png(),
        noaa_ocm_area_a_interferometric_relief_texture_png(),
        noaa_ocm_area_a_interferometric_composite_texture_png(),
        None,
        None,
        None,
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        str(block["note"]),
    )


def generate_nos_bag_terrain_asset(block: dict[str, Any]) -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-b",
        "1",
        "-t_srs",
        "EPSG:4326",
        "-ts",
        str(block["terrainSize"]),
        "0",
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-srcnodata",
        str(block["sourceNoData"]),
        "-dstnodata",
        "-9999",
        str(nos_bag_dataset(block)),
        str(nos_bag_terrain_wgs84(block)),
    ])
    write_terrain_pngs_from_wgs84(
        nos_bag_terrain_wgs84(block),
        nos_bag_elevation_png(block),
        nos_bag_texture_png(block),
        nos_bag_relief_texture_png(block),
        nos_bag_composite_texture_png(block),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        24,
        72,
    )
    return terrain_metadata(
        str(block["sourceId"]),
        source_label(str(block["sourceId"])),
        nos_bag_terrain_wgs84(block),
        nos_bag_elevation_png(block),
        nos_bag_texture_png(block),
        nos_bag_relief_texture_png(block),
        nos_bag_composite_texture_png(block),
        None,
        None,
        None,
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
        "-t_srs",
        "EPSG:4326",
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


def generate_cudem_terrain_asset() -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-ts",
        str(CUDEM_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-dstnodata",
        "-9999",
        str(CUDEM_TIF),
        str(CUDEM_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        CUDEM_TERRAIN_WGS84,
        CUDEM_TERRAIN_ELEVATION_PNG,
        CUDEM_TERRAIN_TEXTURE_PNG,
        CUDEM_TERRAIN_RELIEF_TEXTURE_PNG,
        CUDEM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        CUDEM_TERRAIN_MIN_M,
        CUDEM_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "noaa_cudem_1_9as",
        source_label("noaa_cudem_1_9as"),
        CUDEM_TERRAIN_WGS84,
        CUDEM_TERRAIN_ELEVATION_PNG,
        CUDEM_TERRAIN_TEXTURE_PNG,
        CUDEM_TERRAIN_RELIEF_TEXTURE_PNG,
        CUDEM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        CUDEM_TERRAIN_MIN_M,
        CUDEM_TERRAIN_MAX_M,
        "NOAA CUDEM 1/9 arc-second topobathymetry clipped from remote California COG tiles. It is a sharper broad Bay/coast inset than CRM, but it does not replace CRM for complete offshore continuity toward the Farallones.",
    )


def fusion_resolution_rank(source_id: str) -> int:
    if "_1m" in source_id:
        return 30
    if "_2m" in source_id:
        return 20
    if "_4m" in source_id:
        return 12
    if "vr" in source_id:
        return 10
    if "_10m" in source_id or "farallon_escarpment" in source_id:
        return 8
    return 0


def best_available_fusion_input_records() -> list[tuple[str, Path]]:
    ordered_sources: list[tuple[int, int, str, Path]] = [
        (10, 0, "noaa_crm_vol7_3as", CRM_TERRAIN_WGS84),
        (20, 0, "noaa_cudem_1_9as", CUDEM_TERRAIN_WGS84),
        (
            40,
            0,
            str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceId"]),
            noaa_ocm_area_a_interferometric_terrain_wgs84(),
        ),
        *[
            (
                70,
                fusion_resolution_rank(str(block["sourceId"])),
                str(block["sourceId"]),
                usgs_sf_bay_1m_terrain_wgs84(block),
            )
            for block in active_usgs_sf_bay_1m_blocks()
        ],
        *[
            (
                70,
                fusion_resolution_rank(str(block["sourceId"])),
                str(block["sourceId"]),
                noaa_ocm_area_a_terrain_wgs84(block),
            )
            for block in NOAA_OCM_AREA_A_BLOCKS
        ],
        *[
            (
                80,
                fusion_resolution_rank(str(block["sourceId"])),
                str(block["sourceId"]),
                nos_bag_terrain_wgs84(block),
            )
            for block in NOS_BAG_BLOCKS
        ],
        *[
            (
                85 if not ("farallon" in str(block["sourceId"]) or "rittenburg" in str(block["sourceId"])) else 90,
                fusion_resolution_rank(str(block["sourceId"])),
                str(block["sourceId"]),
                bathymetry_block_terrain_wgs84(block),
            )
            for block in BATHYMETRY_BLOCKS
        ],
        (95, 20, "usgs_ds684_dem4", DS684_TERRAIN_WGS84),
    ]
    ordered_sources.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(source_id, path) for _, _, source_id, path in ordered_sources if path.exists()]


def best_available_fusion_inputs() -> list[Path]:
    return [path for _, path in best_available_fusion_input_records()]


def source_quality_category(source_id: str) -> str:
    if source_id.startswith("noaa_crm"):
        return "CRM fallback"
    if source_id.startswith("noaa_cudem"):
        return "CUDEM support"
    if source_id.startswith("noaa_ocm_area_a"):
        return "NOAA OCM survey"
    if source_id.startswith("noaa_nos"):
        return "NOAA BAG survey"
    if source_id.startswith("usgs_csmp") or source_id.startswith("usgs_ds684"):
        return "USGS nearshore"
    if "farallon" in source_id or "rittenburg" in source_id:
        return "USGS offshore"
    if source_id.startswith("usgs_sf_bay_1m"):
        return "USGS Bay DEM"
    return "other"


def source_quality_color(category: str) -> tuple[int, int, int]:
    colors = {
        "CRM fallback": (35, 48, 76),
        "CUDEM support": (43, 104, 142),
        "NOAA OCM survey": (42, 202, 170),
        "NOAA BAG survey": (74, 218, 255),
        "USGS nearshore": (248, 207, 82),
        "USGS offshore": (188, 126, 255),
        "USGS Bay DEM": (105, 245, 163),
        "other": (220, 230, 240),
    }
    return colors.get(category, colors["other"])


def write_best_available_source_quality_texture(records: list[tuple[str, Path]]) -> dict[str, Any]:
    if not records:
        return {}

    categories = [
        "CRM fallback",
        "CUDEM support",
        "NOAA OCM survey",
        "NOAA BAG survey",
        "USGS nearshore",
        "USGS offshore",
        "USGS Bay DEM",
        "other",
    ]
    category_codes = {category: index + 1 for index, category in enumerate(categories)}
    code_to_category = {code: category for category, code in category_codes.items()}

    width = 0
    height = 0
    provenance: np.ndarray | None = None
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for source_id, path in records:
            sample_path = temp_root / f"{source_id}.tif"
            run([
                "gdalwarp",
                "-q",
                "-overwrite",
                "-t_srs",
                "EPSG:4326",
                "-te",
                str(BEST_AVAILABLE_BOUNDS["west"]),
                str(BEST_AVAILABLE_BOUNDS["south"]),
                str(BEST_AVAILABLE_BOUNDS["east"]),
                str(BEST_AVAILABLE_BOUNDS["north"]),
                "-ts",
                str(BEST_AVAILABLE_SOURCE_TEXTURE_SIZE),
                "0",
                "-r",
                "near",
                "-ot",
                "Float32",
                "-srcnodata",
                "-9999",
                "-dstnodata",
                "-9999",
                str(path),
                str(sample_path),
            ])
            sample = Image.open(sample_path)
            values = np.asarray(sample, dtype=np.float32)
            if values.ndim > 2:
                values = values[:, :, 0]

            if provenance is None:
                height, width = values.shape
                provenance = np.zeros((height, width), dtype=np.uint8)

            valid = np.isfinite(values) & (values > -9000) & (values < 1_000_000)
            category = source_quality_category(source_id)
            provenance[valid] = category_codes[category]

    if provenance is None:
        return {}

    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    summary: dict[str, int] = {}
    for code, category in code_to_category.items():
        mask = provenance == code
        count = int(mask.sum())
        if count == 0:
            continue
        color = source_quality_color(category)
        pixels[mask, 0] = color[0]
        pixels[mask, 1] = color[1]
        pixels[mask, 2] = color[2]
        pixels[mask, 3] = 238
        summary[category] = count

    Image.fromarray(pixels, "RGBA").save(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG)
    total = sum(summary.values())
    return {
        "texture": "/" + str(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG.relative_to(ROOT / "public")),
        "pixelSize": [width, height],
        "pixelCounts": summary,
        "pixelPercents": {
            category: round((count / total) * 100, 2)
            for category, count in summary.items()
            if total
        },
        "note": "Lower-resolution source-quality texture for the fused terrain. It shows which input class won each sampled pixel after broad-to-detailed stacking.",
    }


def generate_best_available_terrain_asset() -> dict[str, Any]:
    records = best_available_fusion_input_records()
    inputs = [path for _, path in records]
    if len(inputs) < 2:
        raise SystemExit("Best-available terrain fusion needs at least two prepared WGS84 terrain sources.")

    run([
        "gdalbuildvrt",
        "-q",
        "-overwrite",
        "-allow_projection_difference",
        "-srcnodata",
        "-9999",
        "-vrtnodata",
        "-9999",
        str(BEST_AVAILABLE_TERRAIN_VRT),
        *[str(path) for path in inputs],
    ])
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-te",
        str(BEST_AVAILABLE_BOUNDS["west"]),
        str(BEST_AVAILABLE_BOUNDS["south"]),
        str(BEST_AVAILABLE_BOUNDS["east"]),
        str(BEST_AVAILABLE_BOUNDS["north"]),
        "-ts",
        str(BEST_AVAILABLE_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-srcnodata",
        "-9999",
        "-dstnodata",
        "-9999",
        str(BEST_AVAILABLE_TERRAIN_VRT),
        str(BEST_AVAILABLE_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        BEST_AVAILABLE_TERRAIN_WGS84,
        BEST_AVAILABLE_TERRAIN_ELEVATION_PNG,
        BEST_AVAILABLE_TERRAIN_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_MIN_M,
        BEST_AVAILABLE_TERRAIN_MAX_M,
    )
    source_confidence_summary = write_best_available_source_quality_texture(records)
    metadata = terrain_metadata(
        "best_available_gate_shelf_fusion",
        source_label("best_available_gate_shelf_fusion"),
        BEST_AVAILABLE_TERRAIN_WGS84,
        BEST_AVAILABLE_TERRAIN_ELEVATION_PNG,
        BEST_AVAILABLE_TERRAIN_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        BEST_AVAILABLE_TERRAIN_MIN_M,
        BEST_AVAILABLE_TERRAIN_MAX_M,
        "Derived best-available terrain fusion for the Golden Gate, San Francisco Bar, nearshore shelf, and Farallones approach. It stacks CRM/CUDEM continuity first, then available NOAA OCM, NOAA BAG, USGS/CSMP, Farallon/Rittenburg, and DS684 survey surfaces where they exist. This is a visual continuity layer, not a new measured survey.",
        BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG,
    )
    if source_confidence_summary:
        metadata["sourceConfidence"] = source_confidence_summary
    return metadata


def generate_terrain_assets() -> list[dict[str, Any]]:
    TERRAIN_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    for target in (
        DS684_TERRAIN_WGS84,
        CRM_TERRAIN_WGS84,
        CUDEM_TERRAIN_WGS84,
        ETOPO_TERRAIN_WGS84,
        BEST_AVAILABLE_TERRAIN_VRT,
        BEST_AVAILABLE_TERRAIN_WGS84,
        noaa_ocm_area_a_interferometric_contour_grid_wgs84(),
        noaa_ocm_area_a_interferometric_terrain_wgs84(),
    ):
        target.unlink(missing_ok=True)
    for block in NOS_BAG_BLOCKS:
        nos_bag_terrain_wgs84(block).unlink(missing_ok=True)
    for block in NOAA_OCM_AREA_A_BLOCKS:
        noaa_ocm_area_a_terrain_wgs84(block).unlink(missing_ok=True)
    for block in BATHYMETRY_BLOCKS:
        bathymetry_block_terrain_wgs84(block).unlink(missing_ok=True)
        bathymetry_block_backscatter_wgs84(block).unlink(missing_ok=True)
        if block.get("characterZipName"):
            bathymetry_block_character_wgs84(block).unlink(missing_ok=True)
    for block in active_usgs_sf_bay_1m_blocks():
        usgs_sf_bay_1m_terrain_wgs84(block).unlink(missing_ok=True)

    terrain = [
        generate_crm_terrain_asset(),
        generate_cudem_terrain_asset(),
        generate_noaa_ocm_area_a_interferometric_terrain_asset(),
        *[generate_usgs_sf_bay_1m_terrain_asset(block) for block in active_usgs_sf_bay_1m_blocks()],
        *[generate_noaa_ocm_area_a_terrain_asset(block) for block in NOAA_OCM_AREA_A_BLOCKS],
        *[generate_nos_bag_terrain_asset(block) for block in NOS_BAG_BLOCKS],
        *[generate_bathymetry_block_terrain_asset(block) for block in BATHYMETRY_BLOCKS],
        generate_usgs_terrain_asset(),
    ]
    terrain.append(generate_best_available_terrain_asset())
    return terrain


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
    cudem_by_level: dict[float, list[dict[str, Any]]],
    nos_bag_by_level: dict[float, list[dict[str, Any]]],
    bathymetry_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
    preferred_source_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    level_key = rounded_level(level)
    if preferred_source_id == "usgs_ds684_dem4" and usgs_by_level.get(level_key):
        return "usgs_ds684_dem4", usgs_by_level[level_key]
    if preferred_source_id in NOS_BAG_SOURCE_IDS:
        preferred_features = features_for_source(nos_bag_by_level, level_key, preferred_source_id)
        if preferred_features:
            return preferred_source_id, preferred_features
    if preferred_source_id in BATHYMETRY_SOURCE_IDS:
        preferred_features = features_for_source(bathymetry_by_level, level_key, preferred_source_id)
        if preferred_features:
            return preferred_source_id, preferred_features
    if preferred_source_id == "noaa_cudem_1_9as" and cudem_by_level.get(level_key):
        return "noaa_cudem_1_9as", [
            *crm_by_level.get(level_key, []),
            *cudem_by_level[level_key],
        ]
    if preferred_source_id == "noaa_crm_vol7_3as" and crm_by_level.get(level_key):
        return "noaa_crm_vol7_3as", crm_by_level[level_key]
    if preferred_source_id == "composite_high_resolution_local" and (
        cudem_by_level.get(level_key) or nos_bag_by_level.get(level_key) or usgs_by_level.get(level_key) or bathymetry_by_level.get(level_key)
    ):
        return "composite_high_resolution_local", [
            *crm_by_level.get(level_key, []),
            *cudem_by_level.get(level_key, []),
            *nos_bag_by_level.get(level_key, []),
            *bathymetry_by_level.get(level_key, []),
            *usgs_by_level.get(level_key, []),
        ]

    local_features = [
        *cudem_by_level.get(level_key, []),
        *nos_bag_by_level.get(level_key, []),
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
    cudem_by_level: dict[float, list[dict[str, Any]]],
    nos_bag_by_level: dict[float, list[dict[str, Any]]],
    bathymetry_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    level_key = rounded_level(level)
    features: list[dict[str, Any]] = []
    features.extend(crm_by_level.get(level_key, []))
    features.extend(cudem_by_level.get(level_key, []))
    features.extend(nos_bag_by_level.get(level_key, []))
    features.extend(bathymetry_by_level.get(level_key, []))
    features.extend(usgs_by_level.get(level_key, []))
    return features


BATHYMETRY_SOURCE_IDS = {
    str(block["sourceId"])
    for block in [*BATHYMETRY_BLOCKS, *USGS_SF_BAY_1M_BLOCKS, *NOAA_OCM_AREA_A_BLOCKS, NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC]
}
NOS_BAG_SOURCE_IDS = {str(block["sourceId"]) for block in NOS_BAG_BLOCKS}
SOURCE_LABELS = {
    **{str(block["sourceId"]): str(block["sourceLabel"]) for block in NOS_BAG_BLOCKS},
    **{str(block["sourceId"]): str(block["sourceLabel"]) for block in NOAA_OCM_AREA_A_BLOCKS},
    str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceId"]): str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceLabel"]),
    **{str(block["sourceId"]): str(block["sourceLabel"]) for block in BATHYMETRY_BLOCKS},
    **{str(block["sourceId"]): str(block["sourceLabel"]) for block in USGS_SF_BAY_1M_BLOCKS},
}


def source_label(source_id: str) -> str:
    if source_id == "usgs_ds684_dem4":
        return "USGS DS684 DEM 4, 2 m San Francisco Bar / Ocean Beach tile"
    if source_id in SOURCE_LABELS:
        return SOURCE_LABELS[source_id]
    if source_id == "best_available_gate_shelf_fusion":
        return "Best-available fused Golden Gate-to-Farallones terrain"
    if source_id == "composite_high_resolution_local":
        return "Composite high-resolution CUDEM, NOAA BAG, local bathymetry, and topobathymetry"
    if source_id == "noaa_cudem_1_9as":
        return "NOAA CUDEM 1/9 arc-second Bay/coast topobathymetry"
    if source_id == "noaa_crm_vol7_3as":
        return "NOAA CRM Vol. 7, 3 arc-second Bay-to-Farallones grid"
    return "NOAA ETOPO 2022 15 arc-second broad Bay/offshore grid"


def build_browser_payload() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bay_dem_blocks = active_usgs_sf_bay_1m_blocks()
    crm_by_level = build_level_index(CRM_CONTOURS_BROWSER, "noaa_crm_vol7_3as", 0.004, False)
    cudem_by_level = build_level_index(CUDEM_CONTOURS_BROWSER, "noaa_cudem_1_9as", 0.004, False)
    nos_bag_by_level = merge_level_indexes([
        build_level_index(
            nos_bag_contours_wgs84(block),
            str(block["sourceId"]),
            float(block["minDegreesLength"]),
            False,
        )
        for block in NOS_BAG_BLOCKS
    ])
    bathymetry_by_level = merge_level_indexes([
        build_level_index(
            noaa_ocm_area_a_interferometric_contours_wgs84(),
            str(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceId"]),
            float(NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["minDegreesLength"]),
            False,
        ),
        *[
            build_level_index(
                noaa_ocm_area_a_contours_wgs84(block),
                str(block["sourceId"]),
                float(block["minDegreesLength"]),
                False,
            )
            for block in NOAA_OCM_AREA_A_BLOCKS
        ],
        *[
            build_level_index(
                bathymetry_block_contours_wgs84(block),
                str(block["sourceId"]),
                float(block["minDegreesLength"]),
                False,
            )
            for block in BATHYMETRY_BLOCKS
        ],
        *[
            build_level_index(
                usgs_sf_bay_1m_contours_wgs84(block),
                str(block["sourceId"]),
                float(block["minDegreesLength"]),
                False,
            )
            for block in bay_dem_blocks
        ],
    ])
    usgs_by_level = build_level_index(DS684_CONTOURS_WGS84, "usgs_ds684_dem4", 0.003, False)
    terrain = generate_terrain_assets()

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload: list[dict[str, Any]] = []
    waterline_probe_features: list[dict[str, Any]] = []

    for level in WATERLINE_PROBE_LEVELS:
        for feature in probe_features_for_level(level, crm_by_level, cudem_by_level, nos_bag_by_level, bathymetry_by_level, usgs_by_level):
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

        estimate_source_id, estimate_source_features = features_for_level(center, crm_by_level, cudem_by_level, nos_bag_by_level, bathymetry_by_level, usgs_by_level)
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
                cudem_by_level,
                nos_bag_by_level,
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
            "datumNote": "NOAA BAG and NOAA OCM source-survey tiles use survey-specific vertical references; NOAA CUDEM, USGS CSMP, Farallon, Rittenburg Bank, and DS684 sources use NAVD88-style vertical references; NOAA CRM and ETOPO use broader sea-level/EGM-style vertical references. Sea-level offsets are approximate relative values, not a full local tidal-datum correction.",
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
        "method": "Downloaded a NOAA CRM Vol. 7 SF/Farallones subset, clipped NOAA CUDEM 1/9 arc-second California topobathymetry tiles, added a NOAA OCM Area A 1 m interferometric Bay-floor mosaic, added NOAA OCM Area A 1 m Central Bay multibeam source-survey GeoTIFFs, NOAA/NOS H12109, H12110, H12111, H12112, and H12113 Golden Gate/Gulf of the Farallones BAG survey patches plus NOAA/NOS H11965, H13334, W00477, and W00614 Farallon-region BAG survey patches, multiple USGS/CSMP nearshore 2 m bathymetry blocks, USGS Farallon Escarpment/Rittenburg Bank offshore multibeam bathymetry, and the USGS DS684 San Francisco Bar 2 m DEM tile, generated fixed elevation contours with GDAL, exported broad plus local browser terrain images, and built a derived best-available Golden Gate-to-Farallones fusion surface from the prepared WGS84 terrain sources. NOAA ETOPO 2022 remains documented as a fallback broad source.",
        "rawDatasets": [
            str(CRM_TIF.relative_to(ROOT)),
            str(CUDEM_TIF.relative_to(ROOT)),
            *CUDEM_TILE_URLS,
            *[str(nos_bag_dataset(block).relative_to(ROOT)) for block in NOS_BAG_BLOCKS],
            *[
                str(noaa_ocm_area_a_interferometric_dataset(tile_id).relative_to(ROOT))
                for tile_id in NOAA_OCM_AREA_A_INTERFEROMETRIC_TILES
            ],
            *[str(noaa_ocm_area_a_dataset(block).relative_to(ROOT)) for block in NOAA_OCM_AREA_A_BLOCKS],
            str(RAW_NETCDF.relative_to(ROOT)),
            *[
                str(bathymetry_block_dataset(block).relative_to(ROOT))
                for block in BATHYMETRY_BLOCKS
            ],
            *[
                str(usgs_sf_bay_1m_dataset(block).relative_to(ROOT))
                for block in bay_dem_blocks
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
            str(CUDEM_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(CUDEM_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
            str(CUDEM_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
            str(CUDEM_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
            str(BEST_AVAILABLE_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(BEST_AVAILABLE_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
            str(BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
            str(BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
            str(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG.relative_to(ROOT)),
            str(noaa_ocm_area_a_interferometric_elevation_png().relative_to(ROOT)),
            str(noaa_ocm_area_a_interferometric_texture_png().relative_to(ROOT)),
            str(noaa_ocm_area_a_interferometric_relief_texture_png().relative_to(ROOT)),
            str(noaa_ocm_area_a_interferometric_composite_texture_png().relative_to(ROOT)),
            *[
                str(path.relative_to(ROOT))
                for block in NOS_BAG_BLOCKS
                for path in (
                    nos_bag_elevation_png(block),
                    nos_bag_texture_png(block),
                    nos_bag_relief_texture_png(block),
                    nos_bag_composite_texture_png(block),
                )
                if path.exists()
            ],
            *[
                str(path.relative_to(ROOT))
                for block in NOAA_OCM_AREA_A_BLOCKS
                for path in (
                    noaa_ocm_area_a_elevation_png(block),
                    noaa_ocm_area_a_texture_png(block),
                    noaa_ocm_area_a_relief_texture_png(block),
                    noaa_ocm_area_a_composite_texture_png(block),
                )
                if path.exists()
            ],
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
            *[
                str(path.relative_to(ROOT))
                for block in bay_dem_blocks
                for path in (
                    usgs_sf_bay_1m_elevation_png(block),
                    usgs_sf_bay_1m_texture_png(block),
                    usgs_sf_bay_1m_relief_texture_png(block),
                    usgs_sf_bay_1m_composite_texture_png(block),
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
    require_tool("gdalbuildvrt")
    require_tool("gdalinfo")
    require_tool("gdal_translate")
    require_tool("gdalwarp")
    require_tool("ogr2ogr")
    require_tool("unzip")
    download_raw_netcdf()
    download_noaa_crm_vol7_subset()
    prepare_noaa_cudem_subset()
    download_noaa_ocm_area_a_interferometric_tiles()
    download_noaa_ocm_area_a_blocks()
    download_nos_bag_blocks()
    download_bathymetry_blocks()
    prepare_usgs_sf_bay_1m_blocks()
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
