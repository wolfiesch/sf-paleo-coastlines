#!/usr/bin/env python3
"""Generate first-pass paleo-coastline contours from public elevation grids.

The browser layer uses NOAA CRM Vol. 7 for broad SF/Farallones coverage and
the higher-resolution USGS DS684 San Francisco Bar tile for local Golden Gate
detail where that tile covers the requested sea-level contour.
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

RAW_NETCDF = RAW_DIR / "etopo_2022_sf_bay_coast_15s.nc"
CONTOURS_RAW = WORK_DIR / "etopo_2022_contours_raw.geojson"
CRM_DIR = RAW_DIR / "noaa-crm"
CRM_TIF = CRM_DIR / "crm_vol7_sf_farallones_3as.tif"
CRM_CONTOURS_RAW = WORK_DIR / "noaa_crm_vol7_contours_raw.geojson"
CRM_CONTOURS_BROWSER = WORK_DIR / "noaa_crm_vol7_contours_browser.geojson"
CRM_TERRAIN_WGS84 = WORK_DIR / "noaa_crm_vol7_sf_farallones_terrain_wgs84.tif"
CRM_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_elevation.png"
CRM_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "crm_vol7_sf_farallones_color.png"
DS684_DIR = RAW_DIR / "usgs-ds684"
DS684_ZIP = DS684_DIR / "DEM_4_GeoTIFF.zip"
DS684_TIF = DS684_DIR / "DEM_4_GeoTIFF" / "DEM_4_GeoTIFF.tif"
DS684_CONTOURS_RAW = WORK_DIR / "usgs_ds684_dem4_contours_raw.geojson"
DS684_CONTOURS_WGS84 = WORK_DIR / "usgs_ds684_dem4_contours_wgs84.geojson"
DS684_TERRAIN_WGS84 = WORK_DIR / "usgs_ds684_dem4_terrain_wgs84.tif"
DS684_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "dem4_elevation.png"
DS684_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "dem4_color.png"
ETOPO_TERRAIN_WGS84 = WORK_DIR / "etopo_2022_bay_farallones_terrain_wgs84.tif"
ETOPO_TERRAIN_ELEVATION_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_elevation.png"
ETOPO_TERRAIN_TEXTURE_PNG = TERRAIN_PUBLIC_DIR / "etopo_bay_farallones_color.png"
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
DS684_DEM4_URL = "https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/DEM_4_GeoTIFF.zip"

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


def write_terrain_pngs_from_wgs84(source_path: Path, elevation_path: Path, texture_path: Path, minimum: float, maximum: float) -> None:
    source = Image.open(source_path)
    elevation = Image.new("L", source.size)
    texture = Image.new("RGBA", source.size)

    elevation_pixels = []
    texture_pixels = []
    scale = 255.0 / (maximum - minimum)

    for raw in source.getdata():
        height = float(raw)
        if not is_valid_height(height):
            elevation_pixels.append(0)
            texture_pixels.append((0, 0, 0, 0))
            continue

        elevation_pixels.append(clamp_byte((height - minimum) * scale))
        texture_pixels.append((*terrain_color(height), 255))

    elevation.putdata(elevation_pixels)
    texture.putdata(texture_pixels)
    elevation.save(elevation_path)
    texture.save(texture_path)


def terrain_metadata(
    source_id: str,
    source_label_value: str,
    wgs84_tif: Path,
    elevation_png: Path,
    texture_png: Path,
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

    return {
        "sourceId": source_id,
        "sourceLabel": source_label_value,
        "elevationData": public_url(elevation_png),
        "texture": public_url(texture_png),
        "bounds": [round(west, 7), round(south, 7), round(east, 7), round(north, 7)],
        "heightRangeMeters": [minimum, maximum],
        "verticalExaggeration": TERRAIN_VERTICAL_EXAGGERATION,
        "elevationDecoder": {
            "rScaler": ((maximum - minimum) / 255.0) * TERRAIN_VERTICAL_EXAGGERATION,
            "gScaler": 0,
            "bScaler": 0,
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
        DS684_TERRAIN_MIN_M,
        DS684_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "usgs_ds684_dem4",
        source_label("usgs_ds684_dem4"),
        DS684_TERRAIN_WGS84,
        DS684_TERRAIN_ELEVATION_PNG,
        DS684_TERRAIN_TEXTURE_PNG,
        DS684_TERRAIN_MIN_M,
        DS684_TERRAIN_MAX_M,
        "Higher-resolution 2 m terrain inset for the Golden Gate, Ocean Beach, Marin Headlands, and San Francisco Bar.",
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
        ETOPO_TERRAIN_MIN_M,
        ETOPO_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "noaa_etopo_2022",
        source_label("noaa_etopo_2022"),
        ETOPO_TERRAIN_WGS84,
        ETOPO_TERRAIN_ELEVATION_PNG,
        ETOPO_TERRAIN_TEXTURE_PNG,
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
        CRM_TERRAIN_MIN_M,
        CRM_TERRAIN_MAX_M,
    )
    return terrain_metadata(
        "noaa_crm_vol7_3as",
        source_label("noaa_crm_vol7_3as"),
        CRM_TERRAIN_WGS84,
        CRM_TERRAIN_ELEVATION_PNG,
        CRM_TERRAIN_TEXTURE_PNG,
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
        CRM_TERRAIN_WGS84,
        CRM_TERRAIN_ELEVATION_PNG,
        CRM_TERRAIN_TEXTURE_PNG,
        ETOPO_TERRAIN_WGS84,
        ETOPO_TERRAIN_ELEVATION_PNG,
        ETOPO_TERRAIN_TEXTURE_PNG,
    ):
        target.unlink(missing_ok=True)

    return [
        generate_crm_terrain_asset(),
        generate_usgs_terrain_asset(),
    ]


def normalize_lon(value: float) -> float:
    return value - 360 if value > 180 else value


def transform_coordinates(coords: Any) -> Any:
    if (
        isinstance(coords, list)
        and len(coords) >= 2
        and isinstance(coords[0], (int, float))
        and isinstance(coords[1], (int, float))
    ):
        return [round(normalize_lon(float(coords[0])), 6), round(float(coords[1]), 6)]
    if isinstance(coords, list):
        return [transform_coordinates(item) for item in coords]
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
            "coordinates": transform_coordinates(coordinates) if normalize_360_lon else coordinates,
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


def features_for_level(
    level: float,
    crm_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
    preferred_source_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    level_key = rounded_level(level)
    if preferred_source_id == "usgs_ds684_dem4" and usgs_by_level.get(level_key):
        return "usgs_ds684_dem4", usgs_by_level[level_key]
    if preferred_source_id == "noaa_crm_vol7_3as" and crm_by_level.get(level_key):
        return "noaa_crm_vol7_3as", crm_by_level[level_key]

    usgs_features = usgs_by_level.get(rounded_level(level), [])
    if usgs_features:
        return "usgs_ds684_dem4", usgs_features
    return "noaa_crm_vol7_3as", crm_by_level.get(rounded_level(level), [])


def probe_features_for_level(
    level: float,
    crm_by_level: dict[float, list[dict[str, Any]]],
    usgs_by_level: dict[float, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    level_key = rounded_level(level)
    features: list[dict[str, Any]] = []
    features.extend(crm_by_level.get(level_key, []))
    features.extend(usgs_by_level.get(level_key, []))
    return features


def source_label(source_id: str) -> str:
    if source_id == "usgs_ds684_dem4":
        return "USGS DS684 DEM 4, 2 m San Francisco Bar / Ocean Beach tile"
    if source_id == "noaa_crm_vol7_3as":
        return "NOAA CRM Vol. 7, 3 arc-second Bay-to-Farallones grid"
    return "NOAA ETOPO 2022 15 arc-second broad Bay/offshore grid"


def build_browser_payload() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    crm_by_level = build_level_index(CRM_CONTOURS_BROWSER, "noaa_crm_vol7_3as", 0.004, False)
    usgs_by_level = build_level_index(DS684_CONTOURS_WGS84, "usgs_ds684_dem4", 0.003, False)
    terrain = generate_terrain_assets()

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload: list[dict[str, Any]] = []
    waterline_probe_features: list[dict[str, Any]] = []

    for level in WATERLINE_PROBE_LEVELS:
        for feature in probe_features_for_level(level, crm_by_level, usgs_by_level):
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

        estimate_source_id, estimate_source_features = features_for_level(center, crm_by_level, usgs_by_level)
        coastline_features = [
            clone_feature(
                feature,
                {
                    "slice_id": item["id"],
                    "label": item["label"],
                    "line_role": "estimate",
                    "elevation_m": center,
                    "years_before_present": item["yearsBeforePresent"],
                    "source_id": estimate_source_id,
                    "source_label": source_label(estimate_source_id),
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
                        "source_id": uncertainty_source_id,
                        "source_label": source_label(uncertainty_source_id),
                    },
                    bool(feature["properties"].get("normalize_360_lon")),
                )
                for feature in uncertainty_source_features
            )

        payload.append({
            **item,
            "generatedAt": generated_at,
            "sourceModel": source_label(estimate_source_id),
            "datumNote": "USGS DS684 uses NAVD88; NOAA CRM and ETOPO use broad sea-level/EGM-style vertical references. Sea-level offsets are approximate relative values, not a full local tidal-datum correction.",
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
        "method": "Downloaded a NOAA CRM Vol. 7 SF/Farallones subset plus the USGS DS684 San Francisco Bar 2 m DEM tile, generated fixed elevation contours with GDAL, and exported broad plus local browser terrain images. NOAA ETOPO 2022 remains documented as a fallback broad source.",
        "rawDatasets": [
            str(CRM_TIF.relative_to(ROOT)),
            str(RAW_NETCDF.relative_to(ROOT)),
            str(DS684_TIF.relative_to(ROOT)),
        ],
        "browserDataset": "public/data/paleo-coastlines/paleo_coastlines.json",
        "terrainAssets": [
            str(CRM_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(CRM_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
            str(DS684_TERRAIN_ELEVATION_PNG.relative_to(ROOT)),
            str(DS684_TERRAIN_TEXTURE_PNG.relative_to(ROOT)),
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
    (PUBLIC_DIR / "paleo_coastlines.json").write_text(json.dumps(payload, indent=2) + "\n")
    (PUBLIC_DIR / "paleo_coastline_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    print(f"Wrote {PUBLIC_DIR / 'paleo_coastlines.json'}")
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
