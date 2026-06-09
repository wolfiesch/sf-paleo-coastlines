#!/usr/bin/env python3
"""Generate first-pass paleo-coastline contours from public elevation grids.

The browser layer uses NOAA CRM Vol. 7 for broad SF/Farallones coverage and
high-resolution USGS/CSMP bathymetry where local tiles cover the requested
sea-level contour.
"""

from __future__ import annotations

import gzip
import json
import math
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter


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
USGS_CONED_SF_2M_DIR = RAW_DIR / "usgs-coned-sf-2m"
USGS_CONED_SF_2M_TIF = USGS_CONED_SF_2M_DIR / "coned_sf_2m_best_available_8192.tif"
USGS_CONED_SF_2M_TERRAIN_WGS84 = WORK_DIR / "usgs_coned_sf_2m_terrain_wgs84.tif"
USGS_CONED_SF_2M_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "usgs_coned_sf_2m_elevation.png"
USGS_CONED_SF_2M_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_coned_sf_2m_color.png"
USGS_CONED_SF_2M_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_coned_sf_2m_relief.png"
USGS_CONED_SF_2M_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_coned_sf_2m_composite.png"
BEST_AVAILABLE_TERRAIN_VRT = WORK_DIR / "best_available_gate_shelf_terrain.vrt"
BEST_AVAILABLE_TERRAIN_WGS84 = WORK_DIR / "best_available_gate_shelf_terrain_wgs84.tif"
BEST_AVAILABLE_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_elevation.png"
BEST_AVAILABLE_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_color.png"
BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_relief.png"
BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_composite.png"
BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_source_quality.png"
BEST_AVAILABLE_TERRAIN_SOURCE_PROVENANCE_JSON = TERRAIN_PUBLIC_DIR / "best_available_gate_shelf_source_quality.json"
BEST_AVAILABLE_MIN_FUSION_INPUTS = 40
BEST_AVAILABLE_SEAM_BLEND_EDGE_WINDOW_SOURCE_PIXELS = 54
BEST_AVAILABLE_SEAM_BLEND_RADIUS_SOURCE_PIXELS = 20.0
BEST_AVAILABLE_SEAM_BLEND_SMOOTH_SIGMA_ELEVATION_PIXELS = 11.0
BEST_AVAILABLE_SEAM_BLEND_TARGETS = [
    {
        "categories": ["CUDEM support", "USGS offshore"],
        "lon": -123.303675,
        "lat": 37.782137,
        "reason": "Unblended local seam audit measured a 46.8 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS offshore"],
        "lon": -123.389145,
        "lat": 37.822821,
        "reason": "Unblended local seam audit measured a 39.915 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS offshore"],
        "lon": -123.352735,
        "lat": 37.802308,
        "reason": "Unblended local seam audit measured a 38.508 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS offshore"],
        "lon": -123.207436,
        "lat": 37.73906,
        "reason": "Unblended local seam audit measured a 27.356 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "NOAA BAG survey"],
        "lon": -123.396838,
        "lat": 37.895983,
        "reason": "Unblended local seam audit measured a 24.872 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS CoNED broad"],
        "lon": -123.296325,
        "lat": 37.994615,
        "reason": "Unblended local seam audit measured a 24.665 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "NOAA BAG survey"],
        "lon": -123.356496,
        "lat": 37.865897,
        "reason": "Unblended local seam audit measured a 24.585 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "NOAA multibeam"],
        "lon": -123.438547,
        "lat": 38.117179,
        "reason": "Unblended local seam audit measured a 23.904 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS CoNED focus"],
        "lon": -123.296325,
        "lat": 37.945897,
        "reason": "Unblended local seam audit measured a 23.731 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS offshore"],
        "lon": -123.390684,
        "lat": 37.868632,
        "reason": "Unblended local seam audit measured a 23.498 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "NOAA BAG survey"],
        "lon": -123.390855,
        "lat": 38.090171,
        "reason": "Unblended local seam audit measured a 23.459 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "NOAA BAG survey"],
        "lon": -123.346923,
        "lat": 38.087094,
        "reason": "Unblended local seam audit measured a 22.544 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS CoNED focus"],
        "lon": -123.295983,
        "lat": 37.917692,
        "reason": "Unblended local seam audit measured a 21.581 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS CoNED focus"],
        "lon": -123.295983,
        "lat": 37.859402,
        "reason": "Unblended local seam audit measured a 21.297 m 95% height step.",
    },
    {
        "categories": ["CRM fallback", "CUDEM support"],
        "lon": -123.500427,
        "lat": 38.081111,
        "reason": "Unblended local seam audit measured a 16.834 m 95% height step.",
    },
    {
        "categories": ["CUDEM support", "USGS CoNED focus"],
        "lon": -123.295641,
        "lat": 37.769658,
        "reason": "Unblended local seam audit measured a 16.712 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS land LiDAR"],
        "lon": -122.461624,
        "lat": 37.704872,
        "reason": "Post-blend local seam audit still measured a 25.703 m 95% height step.",
    },
    {
        "categories": ["USGS land LiDAR", "USGS nearshore"],
        "lon": -122.475128,
        "lat": 37.808462,
        "reason": "Post-blend local seam audit still measured a 25.24 m 95% height step.",
    },
    {
        "categories": ["USGS land LiDAR", "USGS nearshore"],
        "lon": -122.467265,
        "lat": 37.721111,
        "reason": "Post-blend local seam audit still measured a 23.752 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS land LiDAR"],
        "lon": -122.414615,
        "lat": 37.704872,
        "reason": "Post-blend local seam audit still measured a 23.197 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS land LiDAR"],
        "lon": -122.392051,
        "lat": 37.699744,
        "reason": "Post-blend local seam audit still measured a 23.162 m 95% height step.",
    },
    {
        "categories": ["USGS land LiDAR", "USGS nearshore"],
        "lon": -122.472051,
        "lat": 37.772222,
        "reason": "Post-blend local seam audit still measured a 23.06 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM", "USGS land LiDAR"],
        "lon": -122.370513,
        "lat": 37.72094,
        "reason": "Post-blend local seam audit still measured a 22.727 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS land LiDAR"],
        "lon": -122.378034,
        "lat": 37.716496,
        "reason": "Post-blend local seam audit still measured a 22.396 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM", "USGS land LiDAR"],
        "lon": -122.340427,
        "lat": 37.820427,
        "reason": "Post-blend local seam audit still measured a 21.296 m 95% height step.",
    },
    {
        "categories": ["NOAA OCM survey", "USGS land LiDAR"],
        "lon": -122.474786,
        "lat": 37.810342,
        "reason": "Post-blend local seam audit still measured an 18.015 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS offshore"],
        "lon": -123.157521,
        "lat": 37.69188,
        "reason": "Post-blend local seam audit still measured a 30.827 m 95% height step.",
    },
    {
        "categories": ["NOAA multibeam", "USGS offshore"],
        "lon": -123.423162,
        "lat": 37.847778,
        "reason": "Post-blend local seam audit still measured a 26.813 m 95% height step.",
    },
    {
        "categories": ["NOAA BAG survey", "NOAA multibeam"],
        "lon": -123.521624,
        "lat": 38.03735,
        "reason": "Post-blend local seam audit still measured a 23.784 m 95% height step.",
    },
    {
        "categories": ["NOAA multibeam", "USGS offshore"],
        "lon": -123.26453,
        "lat": 37.755128,
        "reason": "Post-blend local seam audit still measured a 21.38 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM", "USGS land LiDAR"],
        "lon": -122.371197,
        "lat": 37.814957,
        "reason": "Post-blend local seam audit still measured a 20.167 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS offshore"],
        "lon": -123.119231,
        "lat": 37.655641,
        "reason": "Post-blend local seam audit still measured a 19.721 m 95% height step.",
    },
    {
        "categories": ["NOAA multibeam", "USGS offshore"],
        "lon": -123.409829,
        "lat": 37.833761,
        "reason": "Post-blend local seam audit still measured a 19.303 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS offshore"],
        "lon": -123.178718,
        "lat": 37.713077,
        "reason": "Post-blend local seam audit still measured a 19.059 m 95% height step.",
    },
    {
        "categories": ["CRM fallback", "NOAA BAG survey"],
        "lon": -123.503162,
        "lat": 38.097009,
        "reason": "Post-blend local seam audit still measured an 18.156 m 95% height step.",
    },
    {
        "categories": ["CRM fallback", "NOAA BAG survey"],
        "lon": -123.506923,
        "lat": 38.094957,
        "reason": "Post-blend local seam audit still measured a 16.558 m 95% height step.",
    },
    {
        "categories": ["USGS land LiDAR", "USGS nearshore"],
        "lon": -122.423846,
        "lat": 37.81188,
        "reason": "Post-blend local seam audit still measured a 15.749 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM overview", "USGS CoNED broad"],
        "lon": -122.188462,
        "lat": 38.053248,
        "reason": "Current local seam audit measured a 14.564 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM", "USGS land LiDAR"],
        "lon": -122.380085,
        "lat": 37.774274,
        "reason": "Current local seam audit measured a 14.534 m 95% height step.",
    },
    {
        "categories": ["NOAA BAG survey", "NOAA multibeam"],
        "lon": -123.521282,
        "lat": 38.00265,
        "reason": "Current local seam audit measured a 13.001 m 95% height step.",
    },
    {
        "categories": ["NOAA BAG survey", "NOAA multibeam"],
        "lon": -123.524701,
        "lat": 38.080598,
        "reason": "Current local seam audit measured a 12.032 m 95% height step.",
    },
    {
        "categories": ["USGS Bay DEM", "USGS CoNED focus"],
        "lon": -122.326752,
        "lat": 37.810171,
        "reason": "Current local seam audit measured an 11.883 m 95% height step.",
    },
    {
        "categories": ["USGS CoNED focus", "USGS land LiDAR"],
        "lon": -122.478205,
        "lat": 37.829487,
        "reason": "Current local seam audit measured a 9.495 m 95% height step.",
    },
]
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
USGS_2023_SF_LIDAR_DEM_DIR = RAW_DIR / "usgs-2023-sf-lidar-dem"
USGS_2023_SF_LIDAR_DEM_VRT = WORK_DIR / "usgs_2023_sf_lidar_dem.vrt"
USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84 = WORK_DIR / "usgs_2023_sf_lidar_dem_terrain_wgs84.tif"
USGS_2023_SF_LIDAR_DEM_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "usgs_2023_sf_lidar_dem_elevation.png"
USGS_2023_SF_LIDAR_DEM_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_2023_sf_lidar_dem_color.png"
USGS_2023_SF_LIDAR_DEM_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_2023_sf_lidar_dem_relief.png"
USGS_2023_SF_LIDAR_DEM_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "usgs_2023_sf_lidar_dem_composite.png"
ETOPO_TERRAIN_WGS84 = WORK_DIR / "etopo_2022_bay_farallones_terrain_wgs84.tif"
ETOPO_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_elevation.png"
ETOPO_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_color.png"
ETOPO_TERRAIN_RELIEF_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_relief.png"
ETOPO_TERRAIN_COMPOSITE_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_composite.png"
CRM_TERRAIN_SIZE = 1536
CUDEM_TERRAIN_SIZE = 4096
DS684_TERRAIN_SIZE = 768
USGS_2023_SF_LIDAR_DEM_TERRAIN_SIZE = 5120
DS684_TERRAIN_MIN_M = -130.0
DS684_TERRAIN_MAX_M = 400.0
USGS_2023_SF_LIDAR_DEM_TERRAIN_MIN_M = -15.0
USGS_2023_SF_LIDAR_DEM_TERRAIN_MAX_M = 500.0
USGS_2023_SF_LIDAR_DEM_NODATA_M = -9999.0
USGS_2023_SF_LIDAR_DEM_VALID_MIN_M = -100.0
ETOPO_TERRAIN_MIN_M = -2500.0
ETOPO_TERRAIN_MAX_M = 1000.0
CRM_TERRAIN_MIN_M = -2500.0
CRM_TERRAIN_MAX_M = 1000.0
CUDEM_TERRAIN_MIN_M = -2500.0
CUDEM_TERRAIN_MAX_M = 1200.0
USGS_CONED_SF_2M_TERRAIN_SIZE = 8192
USGS_CONED_SF_2M_TERRAIN_MIN_M = -1000.0
USGS_CONED_SF_2M_TERRAIN_MAX_M = 500.0
USGS_CONED_SF_2M_NODATA_M = -3.4028235e38
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


def build_nautilus_nos_bag_blocks() -> list[dict[str, Any]]:
    """NOAA Nautilus transect surveys that sharpen the northwest shelf gap."""

    survey_specs = [
        {
            "survey": "W00442",
            "label": "north coast",
            "source_name": "San Francisco Bay to Strait of Juan de Fuca",
            "resolutions": [
                {"meters": 8, "part": 1, "total": 5, "minimum": -85.0, "maximum": -35.0},
                {"meters": 16, "part": 2, "total": 5, "minimum": -170.0, "maximum": -65.0},
                {"meters": 32, "part": 3, "total": 5, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 4, "total": 5, "minimum": -1050.0, "maximum": -275.0},
            ],
        },
        {
            "survey": "W00431",
            "label": "California/Oregon coast",
            "source_name": "Channel Islands to Cape Blanco",
            "resolutions": [
                {"meters": 8, "part": 1, "total": 5, "minimum": -85.0, "maximum": -35.0},
                {"meters": 16, "part": 2, "total": 5, "minimum": -170.0, "maximum": -65.0},
                {"meters": 32, "part": 3, "total": 5, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 4, "total": 5, "minimum": -1050.0, "maximum": -275.0},
            ],
        },
        {
            "survey": "W00433",
            "label": "northwest shelf",
            "source_name": "Greater Farallones northwest shelf",
            "resolutions": [
                {"meters": 8, "part": 1, "total": 5, "minimum": -85.0, "maximum": -35.0},
                {"meters": 16, "part": 2, "total": 5, "minimum": -170.0, "maximum": -65.0},
                {"meters": 32, "part": 3, "total": 5, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 4, "total": 5, "minimum": -1050.0, "maximum": -275.0},
            ],
        },
        {
            "survey": "W00443",
            "label": "northwest shelf",
            "source_name": "Greater Farallones northwest shelf",
            "resolutions": [
                {"meters": 16, "part": 1, "total": 4, "minimum": -170.0, "maximum": -65.0},
                {"meters": 32, "part": 2, "total": 4, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 3, "total": 4, "minimum": -1050.0, "maximum": -275.0},
            ],
        },
        {
            "survey": "W00444",
            "label": "northwest shelf",
            "source_name": "Greater Farallones northwest shelf",
            "resolutions": [
                {"meters": 8, "part": 1, "total": 5, "minimum": -85.0, "maximum": -35.0},
                {"meters": 16, "part": 2, "total": 5, "minimum": -170.0, "maximum": -65.0},
                {"meters": 32, "part": 3, "total": 5, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 4, "total": 5, "minimum": -1050.0, "maximum": -275.0},
            ],
        },
        {
            "survey": "W00447",
            "label": "southern outer shelf",
            "source_name": "Greater Farallones southern outer shelf and slope",
            "resolutions": [
                {"meters": 16, "part": 1, "total": 4, "minimum": -170.0, "maximum": -80.0},
                {"meters": 32, "part": 2, "total": 4, "minimum": -330.0, "maximum": -135.0},
                {"meters": 64, "part": 3, "total": 4, "minimum": -1050.0, "maximum": -275.0},
                {"meters": 128, "part": 4, "total": 4, "minimum": -4200.0, "maximum": -900.0},
            ],
        },
    ]
    blocks: list[dict[str, Any]] = []
    for survey_spec in survey_specs:
        survey = survey_spec["survey"]
        source_url = f"https://www.ngdc.noaa.gov/nos/W00001-W02000/{survey}.html"
        for resolution in survey_spec["resolutions"]:
            meters = resolution["meters"]
            terrain_size = 2048 if meters <= 32 else 1536
            blocks.append({
                "sourceId": f"noaa_nos_{survey.lower()}_{meters}m_bag",
                "sourceLabel": f"NOAA NOS {survey}, {meters} m BAG {survey_spec['label']} bathymetry",
                "sourceName": f"NOAA/NOS {survey} Bathymetric Attributed Grid, {meters} m, MLLW, {survey_spec['source_name']}",
                "sourceUrl": source_url,
                "role": f"Measured E/V Nautilus multibeam BAG transect used to sharpen the {survey_spec['label']} gap.",
                "folder": f"noaa-nos-{survey.lower()}",
                "fileName": f"{survey}_MB_{meters}m_MLLW_{resolution['part']}of{resolution['total']}.bag",
                "url": f"https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/{survey}/BAG/{survey}_MB_{meters}m_MLLW_{resolution['part']}of{resolution['total']}.bag",
                "terrainStem": f"noaa_nos_{survey.lower()}_{meters}m",
                "terrainSize": terrain_size,
                "terrainMinimum": resolution["minimum"],
                "terrainMaximum": resolution["maximum"],
                "contourMinimum": resolution["minimum"],
                "contourMaximum": resolution["maximum"],
                "contourSimplify": 18,
                "minDegreesLength": 0.004,
                "clipBounds": BEST_AVAILABLE_BOUNDS,
                "skipContours": True,
                "sourceNoData": 1_000_000.0,
                "note": f"NOAA NOS {survey} {meters} m BAG survey patch in MLLW, clipped to the current Bay-to-Farallones study box to add measured E/V Nautilus seafloor texture in the {survey_spec['label']} gap.",
            })
    return blocks


def build_point_reyes_nos_bag_blocks() -> list[dict[str, Any]]:
    """NOAA Point Reyes / Drakes Bay BAG depth bands for the northern approach."""

    survey = "H11738"
    source_url = f"https://www.ngdc.noaa.gov/nos/H10001-H12000/{survey}.html"
    resolution_specs = [
        {
            "resolutionLabel": "1 m",
            "sourceIdResolution": "1m",
            "fileResolution": "1m",
            "part": 2,
            "terrainSize": 1536,
            "minimum": -21.0,
            "maximum": -8.0,
            "contourMinimum": -21.0,
            "contourMaximum": -9.0,
        },
        {
            "resolutionLabel": "1.5 m",
            "sourceIdResolution": "1p5m",
            "fileResolution": "150cm",
            "part": 1,
            "terrainSize": 1536,
            "minimum": -35.0,
            "maximum": -18.0,
            "contourMinimum": -35.0,
            "contourMaximum": -18.0,
        },
        {
            "resolutionLabel": "2 m",
            "sourceIdResolution": "2m",
            "fileResolution": "2m",
            "part": 3,
            "terrainSize": 1536,
            "minimum": -50.0,
            "maximum": -31.0,
            "contourMinimum": -50.0,
            "contourMaximum": -31.0,
        },
        {
            "resolutionLabel": "4 m",
            "sourceIdResolution": "4m",
            "fileResolution": "4m",
            "part": 4,
            "terrainSize": 1024,
            "minimum": -74.0,
            "maximum": -45.0,
            "contourMinimum": -74.0,
            "contourMaximum": -45.0,
        },
    ]
    blocks: list[dict[str, Any]] = []
    for resolution in resolution_specs:
        source_id_resolution = resolution["sourceIdResolution"]
        file_resolution = resolution["fileResolution"]
        label = resolution["resolutionLabel"]
        blocks.append({
            "sourceId": f"noaa_nos_h11738_{source_id_resolution}_bag",
            "sourceLabel": f"NOAA NOS H11738, {label} BAG Point Reyes / Drakes Bay bathymetry",
            "sourceName": f"NOAA/NOS H11738 Bathymetric Attributed Grid, {label}, MLLW, Point Reyes Light to Drakes Bay",
            "sourceUrl": source_url,
            "role": "High-resolution NOAA BAG survey depth band for the Point Reyes / Drakes Bay northern Golden Gate approach.",
            "folder": "noaa-nos-h11738",
            "fileName": f"H11738_MB_{file_resolution}_MLLW_{resolution['part']}of4.bag",
            "url": f"https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H10001-H12000/H11738/BAG/H11738_MB_{file_resolution}_MLLW_{resolution['part']}of4.bag",
            "terrainStem": f"noaa_nos_h11738_{source_id_resolution}",
            "terrainSize": resolution["terrainSize"],
            "terrainMinimum": resolution["minimum"],
            "terrainMaximum": resolution["maximum"],
            "contourMinimum": resolution["contourMinimum"],
            "contourMaximum": resolution["contourMaximum"],
            "contourSimplify": 8,
            "minDegreesLength": 0.002,
            "clipBounds": BEST_AVAILABLE_BOUNDS,
            "skipContours": True,
            "sourceNoData": 1_000_000.0,
            "note": f"NOAA NOS H11738 {label} BAG survey patch in MLLW, clipped to the current Bay-to-Farallones study box to add measured Point Reyes / Drakes Bay seafloor texture north of the Golden Gate.",
        })

    blocks.append({
        "sourceId": "noaa_nos_h11739_vr_bag",
        "sourceLabel": "NOAA NOS H11739, VR BAG Drakes Bay to Bolinas bathymetry",
        "sourceName": "NOAA/NOS H11739 Variable Resolution Bathymetric Attributed Grid, MLLW, Drakes Bay to Bolinas Bay",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/H10001-H12000/H11739.html",
        "role": "Measured NOAA BAG survey support for Drakes Bay to Bolinas Bay north of the Golden Gate.",
        "folder": "noaa-nos-h11739",
        "fileName": "H11739_MB_VR_MLLW_1of1.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/H10001-H12000/H11739/BAG/H11739_MB_VR_MLLW_1of1.bag",
        "terrainStem": "noaa_nos_h11739_vr",
        "terrainSize": 1024,
        "terrainMinimum": -46.0,
        "terrainMaximum": -13.0,
        "contourMinimum": -45.0,
        "contourMaximum": -14.0,
        "contourSimplify": 8,
        "minDegreesLength": 0.002,
        "clipBounds": BEST_AVAILABLE_BOUNDS,
        "skipContours": True,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS H11739 VR BAG survey patch in MLLW, clipped to the current Bay-to-Farallones study box to add measured Drakes Bay to Bolinas Bay seafloor support north of the Golden Gate.",
    })
    return blocks


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
    {
        "sourceId": "noaa_nos_w00478_vr_bag",
        "sourceLabel": "NOAA NOS W00478, VR BAG northwest shelf bathymetry",
        "sourceName": "NOAA/NOS W00478 Variable Resolution Bathymetric Attributed Grid, MLLW, northwest Greater Farallones shelf",
        "sourceUrl": "https://www.ngdc.noaa.gov/nos/W00001-W02000/W00478.html",
        "role": "High-resolution NOAA BAG survey inset spanning much of the northwest outer-shelf gap.",
        "folder": "noaa-nos-w00478",
        "fileName": "W00478_MB_VR_MLLW.bag",
        "url": "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000/W00478/BAG/W00478_MB_VR_MLLW.bag",
        "terrainStem": "noaa_nos_w00478_vr",
        "terrainSize": 2048,
        "terrainMinimum": -620.0,
        "terrainMaximum": -65.0,
        "contourMinimum": -580.0,
        "contourMaximum": -80.0,
        "contourSimplify": 16,
        "minDegreesLength": 0.004,
        "sourceNoData": 1_000_000.0,
        "note": "NOAA NOS W00478 VR BAG survey patch in MLLW, replacing part of the northwest outer-shelf broad-support gap with measured bathymetry.",
    },
    *build_point_reyes_nos_bag_blocks(),
    *build_nautilus_nos_bag_blocks(),
]

BATHYMETRY_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": "noaa_ncei_ex0907_sanctuary_50m_multibeam",
        "sourceLabel": "NOAA/NCEI EX0907, 50 m Sanctuary multibeam bathymetry",
        "sourceName": "NOAA Ship Okeanos Explorer EX0907 50 m Sanctuary gridded multibeam bathymetry",
        "sourceUrl": "https://www.ngdc.noaa.gov/ships/okeanos_explorer/EX0907_mb.html",
        "role": "Measured offshore multibeam grid for the northwest Greater Farallones shelf and deeper sanctuary corridor.",
        "folder": "noaa-ex0907-products",
        "xyzGzipName": "Geog_LatLong_50m_Sanctuary_EX0907.xyz.gz",
        "xyzName": "Geog_LatLong_50m_Sanctuary_EX0907.xyz",
        "xyzUrl": "https://data.ngdc.noaa.gov/platforms/ocean/ships/okeanos_explorer/EX0907/multibeam/data/version2/products/Geog_LatLong_50m_Sanctuary_EX0907.xyz.gz",
        "datasetName": "Geog_LatLong_50m_Sanctuary_EX0907_bathy.tif",
        "terrainStem": "noaa_ncei_ex0907_sanctuary_50m",
        "terrainSize": 1536,
        "terrainMinimum": -3700.0,
        "terrainMaximum": -100.0,
        "contourMinimum": -3600.0,
        "contourMaximum": -120.0,
        "contourSimplify": 20,
        "minDegreesLength": 0.004,
        "note": "NOAA/NCEI EX0907 50 m gridded multibeam bathymetry, adding measured deeper-water shape across the northwest outer-shelf support gap.",
    },
    {
        "sourceId": "noaa_ncei_ex1505_05_75m_multibeam",
        "sourceLabel": "NOAA/NCEI EX1505, 75 m southern offshore multibeam bathymetry",
        "sourceName": "NOAA Ship Okeanos Explorer EX1505 75 m gridded multibeam bathymetry, segment 05",
        "sourceUrl": "https://www.ngdc.noaa.gov/ships/okeanos_explorer/EX1505_mb.html",
        "role": "Measured offshore multibeam grid for the southern Greater Farallones shelf and slope where the current best-available surface still has CRM fallback.",
        "folder": "noaa-ex1505-products",
        "xyzGzipName": "EX1505_MB_FNL_05_75m_WGS84.xyz.gz",
        "xyzName": "EX1505_MB_FNL_05_75m_WGS84.xyz",
        "xyzUrl": "https://data.ngdc.noaa.gov/platforms/ocean/ships/okeanos_explorer/EX1505/multibeam/data/version1/products/EX1505_MB_FNL_05_75m_WGS84.xyz.gz",
        "datasetName": "EX1505_MB_FNL_05_75m_WGS84_bathy.tif",
        "terrainStem": "noaa_ncei_ex1505_05_75m",
        "terrainSize": 1536,
        "terrainMinimum": -3200.0,
        "terrainMaximum": -45.0,
        "contourMinimum": -3100.0,
        "contourMaximum": -50.0,
        "contourSimplify": 20,
        "minDegreesLength": 0.004,
        "note": "NOAA/NCEI EX1505 75 m gridded multibeam bathymetry, replacing part of the southern outer-shelf CRM fallback with measured Okeanos Explorer seafloor shape.",
    },
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
        "sourceId": "usgs_sf_bay_1m_north_navd88_overview",
        "sourceLabel": "USGS SF Bay DEM, north Bay NAVD88 overview fallback",
        "sourceName": "USGS high-resolution DEM of northern San Francisco Bay, NAVD88 overview fallback",
        "sourceUrl": "https://www.sciencebase.gov/catalog/item/5e1cb737e4b0ecf25c5f0bf6",
        "role": "Lower-detail official overview fallback for northern San Francisco Bay while the full North Bay TIFF endpoint is unavailable.",
        "folder": "usgs-sf-bay-1m-dem/navd88/north",
        "zipName": None,
        "datasetName": "NorthSFBay_DEM_Mosaic_NAVD88_1m.tif.ovr",
        "terrainStem": "usgs_sf_bay_1m_north_navd88_overview",
        "terrainSize": 4096,
        "terrainMinimum": -45.0,
        "terrainMaximum": 8.0,
        "contourMinimum": -40.0,
        "contourMaximum": 5.0,
        "contourSimplify": 5,
        "minDegreesLength": 0.0015,
        "overviewFallbackFor": "usgs_sf_bay_1m_north_navd88",
        "overviewSrs": "EPSG:6339",
        "overviewUpperLeftX": 544367.5,
        "overviewUpperLeftY": 4221080.5,
        "overviewLowerRightX": 599611.5,
        "overviewLowerRightY": 4201322.5,
        "note": "USGS North Bay NAVD88 overview fallback built from the official ScienceBase .ovr and .tfw sidecar files. It is a 2 m overview of the missing 1 m BigTIFF, so it improves northern Bay detail without claiming full 1 m coverage.",
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

USGS_CONED_SF_2M_FOCUS_BLOCKS: list[dict[str, Any]] = [
    {
        "sourceId": "usgs_coned_sf_2m_gate_shelf",
        "sourceLabel": "USGS CoNED 2 m focus clip, Golden Gate and SF Bar",
        "sourceName": "USGS CoNED San Francisco 2 m topobathymetry, Golden Gate focus clip",
        "sourceUrl": "https://topotools.cr.usgs.gov/topobathy_viewer/",
        "role": "Higher-pixel-density CoNED WCS clip around the Golden Gate, San Francisco Bar, Ocean Beach, and inner shelf.",
        "fileName": "coned_sf_2m_gate_shelf_8192.tif",
        "terrainStem": "usgs_coned_sf_2m_gate_shelf",
        "terrainSize": 8192,
        "terrainMinimum": -500.0,
        "terrainMaximum": 500.0,
        "note": "USGS CoNED 2 m focus clip for the Golden Gate, San Francisco Bar, Ocean Beach, and inner shelf. It preserves more CoNED pixels per mile than the broad all-region clip, while true survey patches still draw above it.",
    },
    {
        "sourceId": "usgs_coned_sf_2m_farallon_shelf",
        "sourceLabel": "USGS CoNED 2 m focus clip, Farallon shelf",
        "sourceName": "USGS CoNED San Francisco 2 m topobathymetry, Farallon shelf focus clip",
        "sourceUrl": "https://topotools.cr.usgs.gov/topobathy_viewer/",
        "role": "Higher-pixel-density CoNED WCS clip across the Farallon Islands approach and outer shelf.",
        "fileName": "coned_sf_2m_farallon_shelf_8192.tif",
        "terrainStem": "usgs_coned_sf_2m_farallon_shelf",
        "terrainSize": 8192,
        "terrainMinimum": -2200.0,
        "terrainMaximum": 500.0,
        "note": "USGS CoNED 2 m focus clip for the Farallon Islands approach and outer shelf. It improves the broad CoNED base where the user is looking far west of today's coast.",
    },
    {
        "sourceId": "usgs_coned_sf_2m_south_bay_edge",
        "sourceLabel": "USGS CoNED 2 m focus clip, south Bay edge",
        "sourceName": "USGS CoNED San Francisco 2 m topobathymetry, south Bay edge focus clip",
        "sourceUrl": "https://topotools.cr.usgs.gov/topobathy_viewer/",
        "role": "Higher-pixel-density CoNED WCS clip for the south and lower-central Bay edge inside the public CoNED layer bounds.",
        "fileName": "coned_sf_2m_south_bay_edge_8192.tif",
        "terrainStem": "usgs_coned_sf_2m_south_bay_edge",
        "terrainSize": 8192,
        "terrainMinimum": -120.0,
        "terrainMaximum": 500.0,
        "note": "USGS CoNED 2 m focus clip for the south and lower-central Bay edge. It helps offset the currently blocked USGS south Bay 1 m NAVD88 ScienceBase download.",
    },
]

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
    {
        "name": "USGS CoNED San Francisco Bay 2 m topobathymetric DEM",
        "url": "https://topotools.cr.usgs.gov/topobathy_viewer/",
        "role": "Unified San Francisco land-plus-seafloor topobathymetry surface clipped from the official USGS CoNED WCS layer.",
    },
    *[
        {
            "name": block["sourceName"],
            "url": block["sourceUrl"],
            "role": block["role"],
        }
        for block in USGS_CONED_SF_2M_FOCUS_BLOCKS
    ],
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


def usgs_2023_sf_lidar_dem_tiles() -> list[Path]:
    return sorted(USGS_2023_SF_LIDAR_DEM_DIR.glob("USGS_OPR_CA_SanFrancisco_B23_*.tif"))


def active_usgs_2023_sf_lidar_dem() -> bool:
    return bool(usgs_2023_sf_lidar_dem_tiles())


def active_usgs_coned_sf_2m() -> bool:
    return USGS_CONED_SF_2M_TIF.exists()


def usgs_coned_sf_2m_focus_dataset(block: dict[str, Any]) -> Path:
    return USGS_CONED_SF_2M_DIR / str(block["fileName"])


def usgs_coned_sf_2m_focus_terrain_wgs84(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_terrain_wgs84.tif"


def usgs_coned_sf_2m_focus_elevation_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_elevation.png"


def usgs_coned_sf_2m_focus_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_color.png"


def usgs_coned_sf_2m_focus_relief_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_relief.png"


def usgs_coned_sf_2m_focus_composite_texture_png(block: dict[str, Any]) -> Path:
    return TERRAIN_PUBLIC_DIR / f"{block['terrainStem']}_composite.png"


def active_usgs_coned_sf_2m_focus_blocks() -> list[dict[str, Any]]:
    return [
        block
        for block in USGS_CONED_SF_2M_FOCUS_BLOCKS
        if usgs_coned_sf_2m_focus_dataset(block).exists()
    ]


def build_usgs_2023_sf_lidar_dem_vrt() -> None:
    tiles = usgs_2023_sf_lidar_dem_tiles()
    if not tiles:
        raise SystemExit(
            "USGS 2023 SF LiDAR DEM tiles are missing. "
            "Run `pnpm paleo-coastlines:usgs-2023-sf-dem --download` first."
        )
    run([
        "gdalbuildvrt",
        "-q",
        "-overwrite",
        "-srcnodata",
        "-999999",
        "-vrtnodata",
        "-9999",
        str(USGS_2023_SF_LIDAR_DEM_VRT),
        *[str(tile) for tile in tiles],
    ])


def clean_usgs_2023_sf_lidar_dem_nodata() -> None:
    temp_output = USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84.with_name(
        f"{USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84.stem}_cleaned.tif"
    )
    for sidecar in (
        USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84.with_suffix(f"{USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84.suffix}.aux.xml"),
        temp_output.with_suffix(f"{temp_output.suffix}.aux.xml"),
    ):
        sidecar.unlink(missing_ok=True)
    run([
        "gdal_calc.py",
        "--quiet",
        "-A",
        str(USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84),
        "--outfile",
        str(temp_output),
        "--calc",
        f"where(A<{USGS_2023_SF_LIDAR_DEM_VALID_MIN_M},{USGS_2023_SF_LIDAR_DEM_NODATA_M},A)",
        "--NoDataValue",
        str(USGS_2023_SF_LIDAR_DEM_NODATA_M),
        "--type",
        "Float32",
        "--format",
        "GTiff",
        "--overwrite",
    ])
    temp_output.replace(USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84)
    temp_output.with_suffix(f"{temp_output.suffix}.aux.xml").unlink(missing_ok=True)


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


def bathymetry_block_xyz_gzip(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["xyzGzipName"])


def bathymetry_block_xyz(block: dict[str, Any]) -> Path:
    return bathymetry_block_dir(block) / str(block["xyzName"])


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
    if block.get("xyzUrl"):
        if not bathymetry_block_dataset(block).exists():
            download_url(str(block["xyzUrl"]), bathymetry_block_xyz_gzip(block))
            print(f"Unpacking {bathymetry_block_xyz_gzip(block)} to {bathymetry_block_xyz(block)}")
            with gzip.open(bathymetry_block_xyz_gzip(block), "rb") as source, bathymetry_block_xyz(block).open("wb") as target:
                shutil.copyfileobj(source, target)
            run([
                "gdal_translate",
                "-q",
                "-of",
                "GTiff",
                "-a_srs",
                "EPSG:4326",
                str(bathymetry_block_xyz(block)),
                str(bathymetry_block_dataset(block)),
            ])
        else:
            print(f"Using existing source file: {bathymetry_block_dataset(block)}")
        return

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


def usgs_sf_bay_1m_dataset_candidates(block: dict[str, Any]) -> list[Path]:
    block_dir = usgs_sf_bay_1m_block_dir(block)
    dataset_name = str(block["datasetName"])
    candidates = [block_dir / dataset_name]
    if dataset_name.endswith(".tif"):
        candidates.append(block_dir / f"{dataset_name.removesuffix('.tif')}..tif")
    return candidates


def usgs_sf_bay_1m_raw_dataset(block: dict[str, Any]) -> Path:
    for candidate in usgs_sf_bay_1m_dataset_candidates(block):
        if candidate.exists():
            return candidate
    return usgs_sf_bay_1m_dataset_candidates(block)[0]


def usgs_sf_bay_1m_georeferenced_overview(block: dict[str, Any]) -> Path:
    return WORK_DIR / f"{block['sourceId']}_source_georef.tif"


def usgs_sf_bay_1m_dataset(block: dict[str, Any]) -> Path:
    if block.get("overviewFallbackFor"):
        return usgs_sf_bay_1m_georeferenced_overview(block)
    return usgs_sf_bay_1m_raw_dataset(block)


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
        if block.get("overviewFallbackFor"):
            source_id = str(block["overviewFallbackFor"])
            full_block = next((candidate for candidate in USGS_SF_BAY_1M_BLOCKS if candidate["sourceId"] == source_id), None)
            if full_block is not None and usgs_sf_bay_1m_raw_dataset(full_block).exists():
                continue
            raw_overview = usgs_sf_bay_1m_raw_dataset(block)
            georeferenced_overview = usgs_sf_bay_1m_georeferenced_overview(block)
            if raw_overview.exists() and not georeferenced_overview.exists():
                run([
                    "gdal_translate",
                    "-q",
                    "-of",
                    "GTiff",
                    "-co",
                    "TILED=YES",
                    "-co",
                    "COMPRESS=DEFLATE",
                    "-a_srs",
                    str(block["overviewSrs"]),
                    "-a_ullr",
                    str(block["overviewUpperLeftX"]),
                    str(block["overviewUpperLeftY"]),
                    str(block["overviewLowerRightX"]),
                    str(block["overviewLowerRightY"]),
                    str(raw_overview),
                    str(georeferenced_overview),
                ])
            continue
        dataset = usgs_sf_bay_1m_dataset(block)
        if dataset.exists():
            continue
        zip_path = usgs_sf_bay_1m_zip(block)
        if zip_path is not None and zip_path.exists():
            run(["unzip", "-o", str(zip_path), "-d", str(usgs_sf_bay_1m_block_dir(block))])


def active_usgs_sf_bay_1m_blocks() -> list[dict[str, Any]]:
    active_blocks: list[dict[str, Any]] = []
    active_source_ids: set[str] = set()
    for block in USGS_SF_BAY_1M_BLOCKS:
        if block.get("overviewFallbackFor") and str(block["overviewFallbackFor"]) in active_source_ids:
            continue
        if usgs_sf_bay_1m_dataset(block).exists():
            active_blocks.append(block)
            active_source_ids.add(str(block["sourceId"]))
    return active_blocks


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
        if block.get("skipContours"):
            continue
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
    height_filter: Callable[[np.ndarray, np.ndarray], np.ndarray] | None = None,
) -> None:
    source = Image.open(source_path)
    heights = np.asarray(source, dtype=np.float32)
    if heights.ndim > 2:
        heights = heights[:, :, 0]

    image_height, width = heights.shape
    valid = np.isfinite(heights) & (heights > -9000) & (heights < 1_000_000)
    if height_filter is not None:
        heights = height_filter(heights, valid).astype(np.float32)
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
    if source_id == "usgs_coned_sf_2m":
        return {"qualityTier": "bay_mosaic", "renderPriority": 30, "resolutionMeters": 2}
    if source_id.startswith("usgs_coned_sf_2m_"):
        return {"qualityTier": "bay_mosaic", "renderPriority": 32, "resolutionMeters": 2}
    if source_id.startswith("best_available"):
        return {"qualityTier": "bay_mosaic", "renderPriority": 35, "resolutionMeters": 20}
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        return {"qualityTier": "bay_mosaic", "renderPriority": 40, "resolutionMeters": 1}
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return {"qualityTier": "source_survey", "renderPriority": 68, "resolutionMeters": 2}
    if source_id.startswith("usgs_sf_bay_1m") or source_id.startswith("noaa_ocm_area_a"):
        return {"qualityTier": "source_survey", "renderPriority": 70, "resolutionMeters": 1}
    if source_id.startswith("noaa_nos"):
        if "_1p5m" in source_id:
            return {"qualityTier": "source_survey", "renderPriority": 80, "resolutionMeters": 1.5}
        resolution = next(
            (
                meters
                for meters in (1, 2, 4, 8, 10, 16, 32, 64, 128)
                if f"_{meters}m" in source_id
            ),
            None,
        )
        return {"qualityTier": "source_survey", "renderPriority": 80, "resolutionMeters": resolution}
    if source_id.startswith("usgs_2023_sf_lidar"):
        return {"qualityTier": "nearshore_detail", "renderPriority": 82, "resolutionMeters": 1}
    if source_id.startswith("usgs_csmp") or source_id.startswith("usgs_ds684"):
        return {"qualityTier": "nearshore_detail", "renderPriority": 85, "resolutionMeters": 2}
    if source_id.startswith("noaa_ncei"):
        return {"qualityTier": "offshore_survey", "renderPriority": 75, "resolutionMeters": 50}
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


def generate_usgs_coned_sf_2m_terrain_asset() -> dict[str, Any]:
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-ts",
        str(USGS_CONED_SF_2M_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-srcnodata",
        str(USGS_CONED_SF_2M_NODATA_M),
        "-dstnodata",
        "-9999",
        str(USGS_CONED_SF_2M_TIF),
        str(USGS_CONED_SF_2M_TERRAIN_WGS84),
    ])
    write_terrain_pngs_from_wgs84(
        USGS_CONED_SF_2M_TERRAIN_WGS84,
        USGS_CONED_SF_2M_TERRAIN_ELEVATION_PNG,
        USGS_CONED_SF_2M_TERRAIN_TEXTURE_PNG,
        USGS_CONED_SF_2M_TERRAIN_RELIEF_TEXTURE_PNG,
        USGS_CONED_SF_2M_TERRAIN_COMPOSITE_TEXTURE_PNG,
        USGS_CONED_SF_2M_TERRAIN_MIN_M,
        USGS_CONED_SF_2M_TERRAIN_MAX_M,
        18,
    )
    return terrain_metadata(
        "usgs_coned_sf_2m",
        source_label("usgs_coned_sf_2m"),
        USGS_CONED_SF_2M_TERRAIN_WGS84,
        USGS_CONED_SF_2M_TERRAIN_ELEVATION_PNG,
        USGS_CONED_SF_2M_TERRAIN_TEXTURE_PNG,
        USGS_CONED_SF_2M_TERRAIN_RELIEF_TEXTURE_PNG,
        USGS_CONED_SF_2M_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        USGS_CONED_SF_2M_TERRAIN_MIN_M,
        USGS_CONED_SF_2M_TERRAIN_MAX_M,
        "USGS CoNED San Francisco 2 m topobathymetry clipped from the official WCS layer. It gives the app a unified local land-plus-seafloor continuity surface underneath sharper survey patches.",
    )


def generate_usgs_coned_sf_2m_focus_terrain_asset(block: dict[str, Any]) -> dict[str, Any]:
    terrain_wgs84 = usgs_coned_sf_2m_focus_terrain_wgs84(block)
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
        str(USGS_CONED_SF_2M_NODATA_M),
        "-dstnodata",
        "-9999",
        str(usgs_coned_sf_2m_focus_dataset(block)),
        str(terrain_wgs84),
    ])
    write_terrain_pngs_from_wgs84(
        terrain_wgs84,
        usgs_coned_sf_2m_focus_elevation_png(block),
        usgs_coned_sf_2m_focus_texture_png(block),
        usgs_coned_sf_2m_focus_relief_texture_png(block),
        usgs_coned_sf_2m_focus_composite_texture_png(block),
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        18,
    )
    return terrain_metadata(
        str(block["sourceId"]),
        str(block["sourceLabel"]),
        terrain_wgs84,
        usgs_coned_sf_2m_focus_elevation_png(block),
        usgs_coned_sf_2m_focus_texture_png(block),
        usgs_coned_sf_2m_focus_relief_texture_png(block),
        usgs_coned_sf_2m_focus_composite_texture_png(block),
        None,
        None,
        None,
        float(block["terrainMinimum"]),
        float(block["terrainMaximum"]),
        str(block["note"]),
    )


def generate_usgs_2023_sf_lidar_dem_terrain_asset() -> dict[str, Any]:
    build_usgs_2023_sf_lidar_dem_vrt()
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-ts",
        str(USGS_2023_SF_LIDAR_DEM_TERRAIN_SIZE),
        "0",
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-srcnodata",
        "-999999",
        "-dstnodata",
        "-9999",
        str(USGS_2023_SF_LIDAR_DEM_VRT),
        str(USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84),
    ])
    clean_usgs_2023_sf_lidar_dem_nodata()
    write_terrain_pngs_from_wgs84(
        USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_ELEVATION_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_TEXTURE_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_RELIEF_TEXTURE_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_MIN_M,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_MAX_M,
        20,
    )
    return terrain_metadata(
        "usgs_2023_sf_lidar_dem",
        source_label("usgs_2023_sf_lidar_dem"),
        USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_ELEVATION_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_TEXTURE_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_RELIEF_TEXTURE_PNG,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_COMPOSITE_TEXTURE_PNG,
        None,
        None,
        None,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_MIN_M,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_MAX_M,
        "USGS 2023 San Francisco 1 m LiDAR DEM land inset. It sharpens above-water terrain and shoreline relief near San Francisco, but it is not an offshore bathymetry survey.",
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
    command = [
        "gdalwarp",
        "-q",
        "-overwrite",
        "-b",
        "1",
        "-t_srs",
        "EPSG:4326",
    ]
    clip_bounds = block.get("clipBounds")
    if clip_bounds:
        command.extend([
            "-te_srs",
            "EPSG:4326",
            "-te",
            str(clip_bounds["west"]),
            str(clip_bounds["south"]),
            str(clip_bounds["east"]),
            str(clip_bounds["north"]),
        ])
    command.extend([
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
    run(command)
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
    if "_1p5m" in source_id:
        return 25
    if "_2m" in source_id:
        return 20
    if "_4m" in source_id:
        return 16
    if "_8m" in source_id:
        return 14
    if "_10m" in source_id or "farallon_escarpment" in source_id:
        return 12
    if "_16m" in source_id:
        return 10
    if "vr" in source_id:
        return 10
    if "_32m" in source_id:
        return 8
    if "_64m" in source_id:
        return 6
    if "_128m" in source_id:
        return 4
    return 0


def best_available_fusion_ranked_records() -> list[tuple[int, int, str, Path]]:
    ordered_sources: list[tuple[int, int, str, Path]] = [
        (10, 0, "noaa_crm_vol7_3as", CRM_TERRAIN_WGS84),
        (20, 0, "noaa_cudem_1_9as", CUDEM_TERRAIN_WGS84),
        *(
            [(30, 20, "usgs_coned_sf_2m", USGS_CONED_SF_2M_TERRAIN_WGS84)]
            if active_usgs_coned_sf_2m()
            else []
        ),
        *[
            (
                32,
                index,
                str(block["sourceId"]),
                usgs_coned_sf_2m_focus_terrain_wgs84(block),
            )
            for index, block in enumerate(active_usgs_coned_sf_2m_focus_blocks())
        ],
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
        *(
            [(82, 30, "usgs_2023_sf_lidar_dem", USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84)]
            if active_usgs_2023_sf_lidar_dem()
            else []
        ),
        *[
            (
                75 if str(block["sourceId"]).startswith("noaa_ncei") else 85 if not ("farallon" in str(block["sourceId"]) or "rittenburg" in str(block["sourceId"])) else 90,
                fusion_resolution_rank(str(block["sourceId"])),
                str(block["sourceId"]),
                bathymetry_block_terrain_wgs84(block),
            )
            for block in BATHYMETRY_BLOCKS
        ],
        (95, 20, "usgs_ds684_dem4", DS684_TERRAIN_WGS84),
    ]
    ordered_sources.sort(key=lambda item: (item[0], item[1], item[2]))
    return ordered_sources


def best_available_fusion_input_records() -> list[tuple[str, Path]]:
    return [
        (source_id, path)
        for _, _, source_id, path in best_available_fusion_ranked_records()
        if path.exists()
    ]


def best_available_fusion_inputs() -> list[Path]:
    return [path for _, path in best_available_fusion_input_records()]


def source_quality_category(source_id: str) -> str:
    if source_id.startswith("noaa_crm"):
        return "CRM fallback"
    if source_id.startswith("noaa_cudem"):
        return "CUDEM support"
    if source_id == "usgs_coned_sf_2m":
        return "USGS CoNED broad"
    if source_id.startswith("usgs_coned_sf_2m_"):
        return "USGS CoNED focus"
    if source_id.startswith("noaa_ocm_area_a"):
        return "NOAA OCM survey"
    if source_id.startswith("noaa_nos"):
        return "NOAA BAG survey"
    if source_id.startswith("noaa_ncei"):
        return "NOAA multibeam"
    if source_id.startswith("usgs_2023_sf_lidar"):
        return "USGS land LiDAR"
    if source_id.startswith("usgs_csmp") or source_id.startswith("usgs_ds684"):
        return "USGS nearshore"
    if "farallon" in source_id or "rittenburg" in source_id:
        return "USGS offshore"
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return "USGS Bay DEM overview"
    if source_id.startswith("usgs_sf_bay_1m"):
        return "USGS Bay DEM"
    return "other"


def source_quality_color(category: str) -> tuple[int, int, int]:
    colors = {
        "CRM fallback": (35, 48, 76),
        "CUDEM support": (43, 104, 142),
        "USGS CoNED broad": (92, 180, 132),
        "USGS CoNED focus": (132, 236, 148),
        "NOAA OCM survey": (42, 202, 170),
        "NOAA BAG survey": (74, 218, 255),
        "NOAA multibeam": (99, 160, 255),
        "USGS land LiDAR": (236, 241, 222),
        "USGS nearshore": (248, 207, 82),
        "USGS offshore": (188, 126, 255),
        "USGS Bay DEM overview": (75, 214, 150),
        "USGS Bay DEM": (105, 245, 163),
        "other": (220, 230, 240),
    }
    return colors.get(category, colors["other"])


def source_quality_categories() -> list[str]:
    return [
        "CRM fallback",
        "CUDEM support",
        "USGS CoNED broad",
        "USGS CoNED focus",
        "NOAA OCM survey",
        "NOAA BAG survey",
        "NOAA multibeam",
        "USGS land LiDAR",
        "USGS nearshore",
        "USGS offshore",
        "USGS Bay DEM overview",
        "USGS Bay DEM",
        "other",
    ]


def source_quality_category_codes_from_texture(path: Path) -> tuple[np.ndarray, dict[str, int]]:
    category_codes = {category: index + 1 for index, category in enumerate(source_quality_categories())}
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    codes = np.zeros(rgba.shape[:2], dtype=np.uint8)
    for category, code in category_codes.items():
        color = source_quality_color(category)
        mask = (
            (rgba[:, :, 0] == color[0])
            & (rgba[:, :, 1] == color[1])
            & (rgba[:, :, 2] == color[2])
            & (rgba[:, :, 3] > 0)
        )
        codes[mask] = code
    return codes, category_codes


def lon_lat_to_source_pixel(lon: float, lat: float, source_shape: tuple[int, int]) -> tuple[int, int]:
    height, width = source_shape
    west = float(BEST_AVAILABLE_BOUNDS["west"])
    east = float(BEST_AVAILABLE_BOUNDS["east"])
    south = float(BEST_AVAILABLE_BOUNDS["south"])
    north = float(BEST_AVAILABLE_BOUNDS["north"])
    x = round(((lon - west) / (east - west)) * (width - 1))
    y = round(((north - lat) / (north - south)) * (height - 1))
    return int(np.clip(x, 0, width - 1)), int(np.clip(y, 0, height - 1))


def source_weight_to_elevation_weight(source_weight: np.ndarray, elevation_shape: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(np.rint(source_weight * 255).astype(np.uint8), "L")
    resized = image.resize((elevation_shape[1], elevation_shape[0]), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32) / 255.0


def best_available_seam_edge_mask(source_codes: np.ndarray, category_codes: dict[str, int]) -> tuple[np.ndarray, int]:
    mask = np.zeros(source_codes.shape, dtype=bool)
    height, width = source_codes.shape
    selected_count = 0
    radius = BEST_AVAILABLE_SEAM_BLEND_EDGE_WINDOW_SOURCE_PIXELS

    for target in BEST_AVAILABLE_SEAM_BLEND_TARGETS:
        category_a, category_b = target["categories"]
        code_a = category_codes[category_a]
        code_b = category_codes[category_b]
        center_x, center_y = lon_lat_to_source_pixel(float(target["lon"]), float(target["lat"]), source_codes.shape)
        x0 = max(0, center_x - radius)
        x1 = min(width - 1, center_x + radius)
        y0 = max(0, center_y - radius)
        y1 = min(height - 1, center_y + radius)
        window = source_codes[y0:y1 + 1, x0:x1 + 1]

        right = (window[:, :-1] != window[:, 1:]) & (
            ((window[:, :-1] == code_a) & (window[:, 1:] == code_b))
            | ((window[:, :-1] == code_b) & (window[:, 1:] == code_a))
        )
        down = (window[:-1, :] != window[1:, :]) & (
            ((window[:-1, :] == code_a) & (window[1:, :] == code_b))
            | ((window[:-1, :] == code_b) & (window[1:, :] == code_a))
        )

        local_mask = np.zeros(window.shape, dtype=bool)
        local_mask[:, :-1] |= right
        local_mask[:, 1:] |= right
        local_mask[:-1, :] |= down
        local_mask[1:, :] |= down
        if local_mask.any():
            selected_count += 1
            mask[y0:y1 + 1, x0:x1 + 1] |= local_mask

    return mask, selected_count


def apply_best_available_seam_edge_blend(heights: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if not BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG.exists():
        print("Skipping best-available seam blend: source-quality texture is not available yet.")
        return heights

    source_codes, category_codes = source_quality_category_codes_from_texture(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG)
    source_edge_mask, selected_count = best_available_seam_edge_mask(source_codes, category_codes)
    if not source_edge_mask.any():
        print("Skipping best-available seam blend: no configured source edges were found.")
        return heights

    distance = distance_transform_edt(~source_edge_mask)
    source_weight = np.clip(
        1.0 - (distance / BEST_AVAILABLE_SEAM_BLEND_RADIUS_SOURCE_PIXELS),
        0.0,
        1.0,
    )
    elevation_weight = source_weight_to_elevation_weight(source_weight, heights.shape)

    valid_float = valid.astype(np.float32)
    filled = np.where(valid, heights, 0.0).astype(np.float32)
    weighted_sum = gaussian_filter(
        filled * valid_float,
        sigma=BEST_AVAILABLE_SEAM_BLEND_SMOOTH_SIGMA_ELEVATION_PIXELS,
    )
    weight_sum = gaussian_filter(
        valid_float,
        sigma=BEST_AVAILABLE_SEAM_BLEND_SMOOTH_SIGMA_ELEVATION_PIXELS,
    )
    smoothed = np.divide(weighted_sum, weight_sum, out=heights.copy(), where=weight_sum > 0.0001)
    blended = heights.copy()
    blended[valid] = (
        (heights[valid] * (1.0 - elevation_weight[valid]))
        + (smoothed[valid] * elevation_weight[valid])
    )
    print(
        "Applied best-available seam edge blend: "
        f"{selected_count}/{len(BEST_AVAILABLE_SEAM_BLEND_TARGETS)} configured targets found."
    )
    return blended


def write_best_available_source_quality_texture(records: list[tuple[str, Path]]) -> dict[str, Any]:
    if not records:
        return {}

    categories = source_quality_categories()
    category_codes = {category: index + 1 for index, category in enumerate(categories)}
    code_to_category = {code: category for category, code in category_codes.items()}

    width = 0
    height = 0
    provenance: np.ndarray | None = None
    source_provenance: np.ndarray | None = None
    source_codes = {source_id: index + 1 for index, (source_id, _) in enumerate(records)}
    code_to_source_id = {code: source_id for source_id, code in source_codes.items()}
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
                source_provenance = np.zeros((height, width), dtype=np.uint16)

            valid = np.isfinite(values) & (values > -9000) & (values < 1_000_000)
            category = source_quality_category(source_id)
            provenance[valid] = category_codes[category]
            if source_provenance is not None:
                source_provenance[valid] = source_codes[source_id]

    if provenance is None or source_provenance is None:
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

    source_summary: list[dict[str, Any]] = []
    source_total = int((source_provenance > 0).sum())
    for code, source_id in code_to_source_id.items():
        count = int((source_provenance == code).sum())
        if count == 0:
            continue
        kind = terrain_source_kind(source_id)
        source_summary.append({
            "sourceId": source_id,
            "sourceLabel": source_label(source_id),
            "category": source_quality_category(source_id),
            "pixelCount": count,
            "pixelPercent": round((count / source_total) * 100, 2) if source_total else 0,
            "renderPriority": kind["renderPriority"],
            "resolutionMeters": kind["resolutionMeters"],
        })
    source_summary.sort(key=lambda item: (-float(item["pixelPercent"]), str(item["sourceId"])))

    provenance_payload = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "texture": "/" + str(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG.relative_to(ROOT / "public")),
        "pixelSize": [width, height],
        "categoryPixelCounts": summary,
        "categoryPixelPercents": {
            category: round((count / total) * 100, 2)
            for category, count in summary.items()
            if total
        },
        "sourceWinners": source_summary,
        "note": "Exact sampled-source provenance for the best-available fused terrain. Later/higher-priority valid sources overwrite broader support surfaces.",
    }
    BEST_AVAILABLE_TERRAIN_SOURCE_PROVENANCE_JSON.write_text(json.dumps(provenance_payload, indent=2) + "\n")

    return {
        "texture": "/" + str(BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG.relative_to(ROOT / "public")),
        "detailUrl": "/" + str(BEST_AVAILABLE_TERRAIN_SOURCE_PROVENANCE_JSON.relative_to(ROOT / "public")),
        "pixelSize": [width, height],
        "pixelCounts": summary,
        "pixelPercents": {
            category: round((count / total) * 100, 2)
            for category, count in summary.items()
            if total
        },
        "topSourceWinners": source_summary[:10],
        "note": "Lower-resolution source-quality texture for the fused terrain. It shows which input class won each sampled pixel after broad-to-detailed stacking; detailUrl contains exact source winner counts.",
    }


def generate_best_available_terrain_asset() -> dict[str, Any]:
    records = best_available_fusion_input_records()
    inputs = [path for _, path in records]
    if len(inputs) < 2:
        raise SystemExit("Best-available terrain fusion needs at least two prepared WGS84 terrain sources.")
    if len(inputs) < BEST_AVAILABLE_MIN_FUSION_INPUTS:
        raise SystemExit(
            "Best-available terrain fusion found only "
            f"{len(inputs)} prepared WGS84 terrain sources; expected at least "
            f"{BEST_AVAILABLE_MIN_FUSION_INPUTS}. Run the full paleo-coastlines generator first "
            "so the browser terrain is not overwritten by a thin fallback stack."
        )

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
    source_confidence_summary = write_best_available_source_quality_texture(records)
    write_terrain_pngs_from_wgs84(
        BEST_AVAILABLE_TERRAIN_WGS84,
        BEST_AVAILABLE_TERRAIN_ELEVATION_PNG,
        BEST_AVAILABLE_TERRAIN_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG,
        BEST_AVAILABLE_TERRAIN_MIN_M,
        BEST_AVAILABLE_TERRAIN_MAX_M,
        height_filter=apply_best_available_seam_edge_blend,
    )
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
        "Derived best-available terrain fusion for the Golden Gate, San Francisco Bar, nearshore shelf, and Farallones approach. It stacks CRM/CUDEM continuity first, then available NOAA OCM, NOAA BAG, NOAA/NCEI multibeam, USGS/CSMP, Farallon/Rittenburg, and DS684 survey surfaces where they exist. This is a visual continuity layer, not a new measured survey.",
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
        USGS_2023_SF_LIDAR_DEM_VRT,
        USGS_2023_SF_LIDAR_DEM_TERRAIN_WGS84,
        CRM_TERRAIN_WGS84,
        CUDEM_TERRAIN_WGS84,
        USGS_CONED_SF_2M_TERRAIN_WGS84,
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
    for block in active_usgs_coned_sf_2m_focus_blocks():
        usgs_coned_sf_2m_focus_terrain_wgs84(block).unlink(missing_ok=True)
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
        *([generate_usgs_coned_sf_2m_terrain_asset()] if active_usgs_coned_sf_2m() else []),
        *[generate_usgs_coned_sf_2m_focus_terrain_asset(block) for block in active_usgs_coned_sf_2m_focus_blocks()],
        generate_noaa_ocm_area_a_interferometric_terrain_asset(),
        *[generate_usgs_sf_bay_1m_terrain_asset(block) for block in active_usgs_sf_bay_1m_blocks()],
        *[generate_noaa_ocm_area_a_terrain_asset(block) for block in NOAA_OCM_AREA_A_BLOCKS],
        *[generate_nos_bag_terrain_asset(block) for block in NOS_BAG_BLOCKS],
        *([generate_usgs_2023_sf_lidar_dem_terrain_asset()] if active_usgs_2023_sf_lidar_dem() else []),
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
    if source_id == "usgs_2023_sf_lidar_dem":
        return "USGS 2023 San Francisco 1 m LiDAR DEM"
    if source_id == "usgs_coned_sf_2m":
        return "USGS CoNED San Francisco 2 m topobathymetry"
    for block in USGS_CONED_SF_2M_FOCUS_BLOCKS:
        if source_id == block["sourceId"]:
            return str(block["sourceLabel"])
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
        if not block.get("skipContours")
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
            "datumNote": "NOAA BAG and NOAA OCM source-survey tiles use survey-specific vertical references; NOAA CUDEM, USGS 2023 land LiDAR, USGS CSMP, Farallon, Rittenburg Bank, and DS684 sources use NAVD88-style vertical references; NOAA CRM and ETOPO use broader sea-level/EGM-style vertical references. Sea-level offsets are approximate relative values, not a full local tidal-datum correction.",
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
        "method": "Downloaded a NOAA CRM Vol. 7 SF/Farallones subset, clipped NOAA CUDEM 1/9 arc-second California topobathymetry tiles, clipped the USGS CoNED San Francisco 2 m topobathymetry WCS layer when the local GeoTIFF is present, added smaller high-pixel-density USGS CoNED focus clips when present, added a NOAA OCM Area A 1 m interferometric Bay-floor mosaic, added NOAA OCM Area A 1 m Central Bay multibeam source-survey GeoTIFFs, NOAA/NOS H12109, H12110, H12111, H12112, and H12113 Golden Gate/Gulf of the Farallones BAG survey patches plus NOAA/NOS H11965, H13334, W00477, W00614, W00431, W00442, W00433, W00443, W00444, W00447, and W00478 Farallon-region / outer-shelf BAG survey patches, added NOAA/NCEI EX0907 50 m gridded multibeam bathymetry for the northwest offshore shelf and NOAA/NCEI EX1505 75 m gridded multibeam bathymetry for the southern offshore shelf as gap-filling measured layers below sharper BAG/CSMP sources, multiple USGS/CSMP nearshore 2 m bathymetry blocks, USGS Farallon Escarpment/Rittenburg Bank offshore multibeam bathymetry, the USGS 2023 San Francisco 1 m LiDAR DEM land inset when local tiles are present, and the USGS DS684 San Francisco Bar 2 m DEM tile, generated fixed elevation contours with GDAL, exported broad plus local browser terrain images, and built a derived best-available Golden Gate-to-Farallones fusion surface from the prepared WGS84 terrain sources. NOAA ETOPO 2022 remains documented as a fallback broad source.",
        "rawDatasets": [
            str(CRM_TIF.relative_to(ROOT)),
            str(CUDEM_TIF.relative_to(ROOT)),
            *([str(USGS_CONED_SF_2M_TIF.relative_to(ROOT))] if active_usgs_coned_sf_2m() else []),
            *[
                str(usgs_coned_sf_2m_focus_dataset(block).relative_to(ROOT))
                for block in active_usgs_coned_sf_2m_focus_blocks()
            ],
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
                str(tile.relative_to(ROOT))
                for tile in usgs_2023_sf_lidar_dem_tiles()
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
            *([
                str(USGS_CONED_SF_2M_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
                str(USGS_CONED_SF_2M_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
                str(USGS_CONED_SF_2M_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
                str(USGS_CONED_SF_2M_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
            ] if active_usgs_coned_sf_2m() else []),
            *[
                str(path.relative_to(ROOT))
                for block in active_usgs_coned_sf_2m_focus_blocks()
                for path in (
                    usgs_coned_sf_2m_focus_elevation_png(block),
                    usgs_coned_sf_2m_focus_texture_png(block),
                    usgs_coned_sf_2m_focus_relief_texture_png(block),
                    usgs_coned_sf_2m_focus_composite_texture_png(block),
                )
                if path.exists()
            ],
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
            *([
                str(USGS_2023_SF_LIDAR_DEM_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
                str(USGS_2023_SF_LIDAR_DEM_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
                str(USGS_2023_SF_LIDAR_DEM_TERRAIN_RELIEF_TEXTURE_PNG.relative_to(ROOT)),
                str(USGS_2023_SF_LIDAR_DEM_TERRAIN_COMPOSITE_TEXTURE_PNG.relative_to(ROOT)),
            ] if active_usgs_2023_sf_lidar_dem() else []),
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
