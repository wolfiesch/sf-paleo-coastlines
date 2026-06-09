#!/usr/bin/env python3
"""Build a lightweight data-quality inventory for the paleo coastline sources.

This does not regenerate terrain. It reads the browser manifest plus the source
definitions in generate_paleo_coastlines.py, checks which raw files exist
locally, scores the data sources, and writes audit files that are small enough
to commit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "public" / "data" / "paleo-coastlines" / "paleo_manifest.json"
OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "survey_inventory.json"
OUT_MD = ROOT / "docs" / "survey-inventory.md"
GENERATOR_PATH = ROOT / "scripts" / "generate_paleo_coastlines.py"


NEXT_DATA_CANDIDATES: list[dict[str, Any]] = [
    {
        "id": "usgs_2023_sf_lidar_dem",
        "label": "2023 USGS Lidar DEM: San Francisco, CA",
        "sourceFamily": "USGS 3DEP / The National Map",
        "sourceUrl": "https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/OPR/Projects/CA_SanFrancisco_B23/CA_SanFrancisco_1_B23/TIFF/",
        "priority": "highest",
        "reason": "High-resolution modern land DEM that sharpens San Francisco terrain and shoreline relief in the 3D waterline view.",
        "nextAction": "Keep active as a land/shoreline detail source, then compare overlap against DS684, CUDEM, and local datum conversions before using it for exact sea-level claims.",
    },
    {
        "id": "usgs_coned_sf_bay_2m",
        "label": "USGS CoNED San Francisco Bay 2 m topobathymetric DEM",
        "sourceFamily": "USGS CoNED",
        "sourceUrl": "https://www.usgs.gov/special-topics/coastal-national-elevation-database-applications-project/science/topobathymetric-0",
        "priority": "highest",
        "reason": "Best candidate for a unified local land-plus-bay foundation at research-grade resolution.",
        "nextAction": "Download through CoNED/The National Map, clip to project bounds, compare vertical datum and overlap against CUDEM/CRM/DS684.",
    },
    {
        "id": "usgs_sf_bay_1m_dem",
        "label": "USGS high-resolution 1 m DEM of San Francisco Bay",
        "sourceFamily": "USGS SF Bay bathymetry",
        "sourceUrl": "https://www.usgs.gov/data/high-resolution-1-m-digital-elevation-model-dem-san-francisco-bay-california-created-using",
        "priority": "highest",
        "reason": "Likely the biggest Bay-interior detail upgrade; it targets the bay floor rather than just the outer coast.",
        "nextAction": "Run `pnpm paleo-coastlines:usgs-bay-dem` to refresh exact ScienceBase file metadata, then download NAVD88 sections one at a time and add them as Bay-focused terrain insets above CUDEM but below small survey patches.",
    },
    {
        "id": "noaa_ocm_area_a",
        "label": "NOAA OCM San Francisco Bay Area A 1 m source-survey GeoTIFFs",
        "sourceFamily": "NOAA OCM acoustic bathymetry",
        "sourceUrl": "https://www.fisheries.noaa.gov/inport/item/47860",
        "priority": "highest",
        "reason": "Practical high-detail Central Bay source grids exposed as individual public S3 GeoTIFFs, avoiding the flaky ScienceBase stitched-DEM download.",
        "nextAction": "Keep Area A active as Central Bay detail. Area B/C metadata exists, but the public InPort pages currently expose no downloadable distribution, so treat them as blocked until a NOAA/NCEI download path is found.",
    },
    {
        "id": "noaa_ocm_area_b_c_blocked",
        "label": "NOAA OCM San Francisco Bay Area B/C 1 m survey grids",
        "sourceFamily": "NOAA OCM acoustic bathymetry",
        "sourceUrl": "https://www.fisheries.noaa.gov/inport/item/47864",
        "priority": "high",
        "reason": "Potentially valuable north/south Bay detail, but the official InPort records currently say no distributions are available.",
        "nextAction": "Do not block the app on this. Re-check NOAA/NCEI discovery and public S3/FTP mirrors later, or contact NOAA OCM/NCEI for the Area B/C grid download path.",
    },
    {
        "id": "noaa_ocm_area_a_interferometric",
        "label": "NOAA OCM Area A 1 m interferometric Bay-floor mosaic",
        "sourceFamily": "NOAA OCM acoustic bathymetry",
        "sourceUrl": "https://www.fisheries.noaa.gov/inport/item/47862",
        "priority": "highest",
        "reason": "Broad 1 m Bay-floor source-grid coverage from 73 public NOAA GeoTIFF tiles, useful for visible shallow-bay relief where the multibeam-only subset is sparse.",
        "nextAction": "Keep as the broad high-detail Bay-floor blanket; prefer multibeam, BAG, or USGS Bay DEM sources where they overlap and have cleaner datum metadata.",
    },
    {
        "id": "noaa_bdv_query",
        "label": "NOAA/NCEI Bathymetric Data Viewer survey search",
        "sourceFamily": "NOAA/NCEI discovery",
        "sourceUrl": "https://www.ncei.noaa.gov/products/bathymetry",
        "priority": "high",
        "reason": "Authoritative discovery path for more BAG, multibeam, singlebeam, lidar, and DEM coverage.",
        "nextAction": "Query every survey footprint intersecting the study bounds and add missing high-resolution BAG/multibeam patches.",
    },
    {
        "id": "nw_gap_noaa_bag_candidates",
        "label": "NW Gap NOAA/NCEI BAG candidates",
        "sourceFamily": "NOAA/NCEI BAG bathymetry",
        "sourceUrl": "/data/paleo-coastlines/nw_gap_source_candidates.json",
        "priority": "highest",
        "reason": "The machine query for the northwest outer-shelf gap found BAG survey groups W00433, W00443, W00444, and W00478 that are not currently in the local terrain stack.",
        "nextAction": "Inspect these BAG groups first; if their downloadable BAG files cover the broad-support cells, add the best one as the next northwest shelf terrain inset.",
    },
    {
        "id": "noaa_multibeam_archive",
        "label": "NOAA/NCEI multibeam bathymetry archive",
        "sourceFamily": "NOAA/NCEI multibeam",
        "sourceUrl": "https://www.ngdc.noaa.gov/mgg/bathymetry/multibeam/",
        "priority": "high",
        "reason": "Potential source of additional offshore swath data beyond the currently baked survey patches.",
        "nextAction": "Search the Farallones shelf and nearby outer shelf for cruises with public gridded products or processable soundings.",
    },
    {
        "id": "usgs_csmp_geology_services",
        "label": "USGS/CSMP map series geology, habitat, and web-service layers",
        "sourceFamily": "USGS/CSMP interpretation",
        "sourceUrl": "https://data.usgs.gov/datacatalog/data/USGS%3A632748c2-f4e3-46cf-bf4c-aaeeb99d6064",
        "priority": "medium",
        "reason": "Adds scientific meaning: mapped bottom type, substrate, geology, and habitat context over the 3D terrain.",
        "nextAction": "Bring interpreted polygons in as optional overlays tied to source confidence and bottom type.",
    },
]


def load_generator_module() -> Any:
    spec = importlib.util.spec_from_file_location("generate_paleo_coastlines", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def source_family(source_id: str) -> str:
    if source_id.startswith("best_available"):
        return "Derived fused terrain"
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        return "NOAA OCM acoustic bathymetry"
    if source_id.startswith("noaa_ocm_area_a"):
        return "NOAA OCM acoustic bathymetry"
    if source_id.startswith("noaa_nos"):
        return "NOAA NOS BAG"
    if source_id.startswith("noaa_ncei"):
        return "NOAA/NCEI multibeam"
    if source_id.startswith("usgs_csmp"):
        return "USGS/CSMP DS 781"
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return "USGS SF Bay DEM overview fallback"
    if source_id.startswith("usgs_sf_bay_1m"):
        return "USGS SF Bay 1 m DEM"
    if source_id.startswith("usgs_2023_sf_lidar"):
        return "USGS 3DEP / The National Map"
    if source_id.startswith("usgs_coned_sf_2m"):
        return "USGS CoNED"
    if source_id.startswith("usgs_farallon") or source_id.startswith("usgs_rittenburg"):
        return "USGS OFR 2014-1234"
    if source_id.startswith("usgs_ds684"):
        return "USGS DS684"
    if source_id.startswith("noaa_cudem"):
        return "NOAA CUDEM"
    if source_id.startswith("noaa_crm"):
        return "NOAA CRM"
    if source_id.startswith("noaa_etopo"):
        return "NOAA ETOPO"
    return "Other"


def datum_note(source_id: str) -> str:
    if source_id.startswith("best_available"):
        return "Mixed-source visual fusion; useful for continuity, but not a single vertical datum."
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        return "NOAA OCM interferometric source-survey vertical reference; use as visual/detail evidence, but compare against multibeam, USGS Bay DEM, CUDEM, and VDatum before exact sea-level alignment."
    if source_id.startswith("noaa_ocm_area_a"):
        return "NOAA OCM source-survey vertical reference; compare against USGS Bay DEM, CUDEM, and VDatum before exact sea-level alignment."
    if source_id.startswith("noaa_nos"):
        return "MLLW; needs tidal-datum conversion before exact sea-level alignment."
    if source_id.startswith("noaa_ncei"):
        return "Source gridded multibeam depth values; useful for measured offshore shape, but still compare overlap against BAG, CUDEM, and VDatum before exact sea-level alignment."
    if source_id.startswith("noaa_crm") or source_id.startswith("noaa_etopo"):
        return "Broad sea-level/geoid-style reference; useful for continuity, not local datum precision."
    if source_id.startswith("noaa_cudem"):
        return "NOAA topobathy product; verify local vertical reference against CoNED/NAVD88 before exact contours."
    if source_id.startswith("usgs_coned_sf_2m"):
        return "USGS CoNED topobathymetry; compare overlap against CUDEM, USGS Bay DEM, DS684, and MLLW BAG patches before exact sea-level alignment."
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return "NAVD88 overview fallback from the USGS North Bay DEM package; useful for visible shape, but lower-detail than the missing full 1 m BigTIFF."
    if source_id.startswith("usgs_sf_bay_1m") and source_id.endswith("_mllw"):
        return "MLLW; useful for Bay-floor visual detail, but needs tidal-datum conversion before exact sea-level alignment with NAVD88 sources."
    if source_id.startswith("usgs_sf_bay_1m"):
        return "NAVD88; best first-fit datum among the candidate Bay DEM files, but still compare overlap against CUDEM, DS684, and MLLW BAG patches."
    if source_id.startswith("usgs_2023_sf_lidar"):
        return "NAVD88-style land DEM; useful for above-water terrain detail, but compare overlap against DS684, CUDEM, and tidal-datum sources before exact waterline alignment."
    return "NAVD88-style or source-projected DEM; verify against local datum before exact contours."


def approximate_native_resolution_m(source_id: str, label: str) -> float | None:
    text = f"{source_id} {label}".lower()
    if source_id.startswith("best_available"):
        return 20.0
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return 2.0
    if "1 m" in text or "_1m" in text:
        return 1.0
    if "2 m" in text or "_2m" in text:
        return 2.0
    if "10 m" in text or "_10m" in text:
        return 10.0
    if "50 m" in text or "_50m" in text:
        return 50.0
    if "1_9as" in text or "1/9 arc-second" in text:
        return 3.4
    if "3as" in text or "3 arc-second" in text:
        return 90.0
    if "15s" in text or "15 arc-second" in text:
        return 450.0
    return None


def resolution_label(source_id: str, label: str) -> str:
    if "vr" in source_id:
        return "variable-resolution BAG"
    value = approximate_native_resolution_m(source_id, label)
    if value is None:
        return "unknown"
    if value >= 100:
        return f"about {value:.0f} m"
    if value == int(value):
        return f"{int(value)} m"
    return f"about {value:.1f} m"


def detail_score(source_id: str, label: str, textures: dict[str, Any]) -> int:
    if source_id.startswith("best_available"):
        return 4

    value = approximate_native_resolution_m(source_id, label)
    score = 2
    if "vr" in source_id:
        score = 4
    elif value is not None and value <= 2:
        score = 5
    elif value is not None and value <= 10:
        score = 4
    elif value is not None and value <= 100:
        score = 2
    elif value is not None:
        score = 1

    if "sonarBackscatter" in textures:
        score += 1
    if "seafloorCharacter" in textures:
        score += 1
    return min(score, 7)


def footprint_area_sqkm(bounds: list[float]) -> float:
    west, south, east, north = bounds
    mean_lat = math.radians((south + north) / 2)
    km_per_degree_lon = 111.32 * math.cos(mean_lat)
    km_per_degree_lat = 110.57
    return max(0.0, (east - west) * km_per_degree_lon) * max(0.0, (north - south) * km_per_degree_lat)


def raw_file_candidates(module: Any, source_id: str) -> list[Path]:
    paths: list[Path] = []
    if source_id.startswith("best_available"):
        return paths

    for block in module.NOS_BAG_BLOCKS:
        if block["sourceId"] == source_id:
            paths.append(module.RAW_DIR / block["folder"] / block["fileName"])
            return paths

    for block in module.NOAA_OCM_AREA_A_BLOCKS:
        if block["sourceId"] == source_id:
            paths.append(module.RAW_DIR / block["folder"] / block["fileName"])
            return paths

    if source_id == module.NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceId"]:
        return [
            module.noaa_ocm_area_a_interferometric_dataset(tile_id)
            for tile_id in module.NOAA_OCM_AREA_A_INTERFEROMETRIC_TILES
        ]

    for block in module.BATHYMETRY_BLOCKS:
        if block["sourceId"] == source_id:
            folder = module.RAW_DIR / block["folder"]
            paths.append(folder / block["datasetName"])
            if block.get("zipName"):
                paths.append(folder / block["zipName"])
            if block.get("xyzGzipName"):
                paths.append(folder / block["xyzGzipName"])
            if block.get("xyzName"):
                paths.append(folder / block["xyzName"])
            for zip_name in block.get("backscatterZipNames", []):
                paths.append(folder / zip_name)
            if block.get("characterZipName"):
                paths.append(folder / block["characterZipName"])
            return paths

    for block in module.USGS_SF_BAY_1M_BLOCKS:
        if block["sourceId"] == source_id:
            folder = module.RAW_DIR / block["folder"]
            paths.append(folder / block["datasetName"])
            if block.get("zipName"):
                paths.append(folder / block["zipName"])
            return paths

    if source_id == "usgs_2023_sf_lidar_dem":
        return module.usgs_2023_sf_lidar_dem_tiles()

    if source_id == "usgs_coned_sf_2m":
        return [module.USGS_CONED_SF_2M_TIF]

    for block in module.USGS_CONED_SF_2M_FOCUS_BLOCKS:
        if block["sourceId"] == source_id:
            return [module.usgs_coned_sf_2m_focus_dataset(block)]

    if source_id == "noaa_crm_vol7_3as":
        paths.append(module.CRM_TIF)
    elif source_id == "noaa_cudem_1_9as":
        paths.append(module.CUDEM_TIF)
    elif source_id == "usgs_ds684_dem4":
        paths.extend([module.DS684_TIF, module.DS684_ZIP])
    elif source_id == "noaa_etopo_2022":
        paths.append(module.RAW_NETCDF)
    return paths


def source_url(module: Any, source_id: str) -> str | None:
    if source_id.startswith("best_available"):
        return None

    if source_id == module.NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceId"]:
        return str(module.NOAA_OCM_AREA_A_INTERFEROMETRIC_MOSAIC["sourceUrl"])

    for block in [
        *module.USGS_CONED_SF_2M_FOCUS_BLOCKS,
        *module.NOS_BAG_BLOCKS,
        *module.NOAA_OCM_AREA_A_BLOCKS,
        *module.BATHYMETRY_BLOCKS,
        *module.USGS_SF_BAY_1M_BLOCKS,
    ]:
        if block["sourceId"] == source_id:
            return str(block["sourceUrl"])
    if source_id == "noaa_crm_vol7_3as":
        return "https://www.ncei.noaa.gov/products/coastal-relief-model"
    if source_id == "noaa_cudem_1_9as":
        return "https://coast.noaa.gov/htdata/raster2/elevation/NCEI_ninth_Topobathy_2014_8483/"
    if source_id == "usgs_2023_sf_lidar_dem":
        return "https://prd-tnm.s3.amazonaws.com/index.html?prefix=StagedProducts/Elevation/OPR/Projects/CA_SanFrancisco_B23/CA_SanFrancisco_1_B23/TIFF/"
    if source_id == "usgs_coned_sf_2m":
        return "https://topotools.cr.usgs.gov/topobathy_viewer/"
    if source_id == "usgs_ds684_dem4":
        return "https://pubs.usgs.gov/ds/684/ds684_DEM_GeoTIFF_files/"
    return None


def raw_status(paths: list[Path]) -> dict[str, Any]:
    existing = [path for path in paths if path.exists()]
    return {
        "expectedCount": len(paths),
        "presentCount": len(existing),
        "present": bool(existing),
        "paths": [str(path.relative_to(ROOT)) for path in existing[:10]],
        "bytes": sum(path.stat().st_size for path in existing if path.is_file()),
    }


def maybe_gdalinfo(path: Path | None, enabled: bool) -> dict[str, Any] | None:
    if not enabled or path is None or not path.exists():
        return None
    try:
        result = subprocess.run(
            ["gdalinfo", "-json", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads(result.stdout)
    except Exception as cause:  # noqa: BLE001 - audit should continue.
        return {"error": str(cause)}

    return {
        "driver": payload.get("driverShortName"),
        "size": payload.get("size"),
        "coordinateSystem": payload.get("coordinateSystem", {}).get("wkt", "")[:160],
        "geoTransform": payload.get("geoTransform"),
    }


def png_size(public_url: str) -> list[int] | None:
    if not public_url.startswith("/"):
        return None
    path = ROOT / "public" / public_url.removeprefix("/")
    if not path.exists():
        return None
    with Image.open(path) as image:
        return [image.width, image.height]


def source_record(module: Any, terrain: dict[str, Any], with_gdalinfo: bool) -> dict[str, Any]:
    source_id = terrain["sourceId"]
    label = terrain["sourceLabel"]
    textures = terrain.get("textures") or {}
    raw_paths = raw_file_candidates(module, source_id)
    primary_raw = next((path for path in raw_paths if path.exists() and path.suffix.lower() != ".zip"), None)
    score = detail_score(source_id, label, textures)
    area = footprint_area_sqkm(terrain["bounds"])

    limitations: list[str] = []
    if source_id.startswith("noaa_crm"):
        limitations.append("coarse broad surface; use only for continuity where better survey coverage is missing")
    if source_id.startswith("noaa_cudem"):
        limitations.append("broad inset; sharper than CRM but still not a substitute for local survey data")
    if source_id.startswith("noaa_nos"):
        limitations.append("MLLW vertical datum; exact paleo contour alignment needs conversion")
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        limitations.append("broad interferometric source-survey mosaic; NOAA notes it is less accurate than multibeam in deeper water")
    elif source_id.startswith("noaa_ocm_area_a"):
        limitations.append("source-survey grid, not a seamless Bay DEM; vertical reference must be checked before exact paleo contour use")
    if source_id.startswith("usgs_csmp"):
        limitations.append("nearshore/state-water patch, not seamless offshore coverage")
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        limitations.append("2 m overview fallback; lower-detail than the unavailable full 1 m North Bay BigTIFF")
        limitations.append("modern interpreted Bay DEM; does not model paleo sediment, marsh, erosion, or river-channel change")
    elif source_id.startswith("usgs_sf_bay_1m"):
        limitations.append("modern interpreted Bay DEM; does not model paleo sediment, marsh, erosion, or river-channel change")
    if source_id.startswith("usgs_2023_sf_lidar"):
        limitations.append("modern land LiDAR; improves above-water and shoreline relief, not offshore bathymetry")
    if source_id.startswith("usgs_farallon") or source_id.startswith("usgs_rittenburg"):
        limitations.append("excellent multibeam patch, but geographically small")
    if source_id.startswith("best_available"):
        limitations.append("derived support mosaic; improves continuity but does not add new measurements")

    return {
        "id": source_id,
        "label": label,
        "sourceFamily": source_family(source_id),
        "sourceUrl": source_url(module, source_id),
        "bounds": terrain["bounds"],
        "approxFootprintSqKm": round(area, 1),
        "heightRangeMeters": terrain["heightRangeMeters"],
        "nativeResolution": resolution_label(source_id, label),
        "browserElevationPng": terrain["elevationData"],
        "browserElevationPngSize": png_size(terrain["elevationData"]),
        "textures": sorted(textures.keys()),
        "datumNote": datum_note(source_id),
        "detailScore": score,
        "qualityTier": quality_tier(score),
        "raw": raw_status(raw_paths),
        "gdalInfo": maybe_gdalinfo(primary_raw, with_gdalinfo),
        "limitations": limitations,
        "nextAction": next_action_for_source(source_id, score),
    }


def quality_tier(score: int) -> str:
    if score >= 6:
        return "excellent local detail"
    if score >= 4:
        return "high detail patch"
    if score >= 2:
        return "broad support surface"
    return "coarse fallback"


def next_action_for_source(source_id: str, score: int) -> str:
    if source_id.startswith("best_available"):
        return "Use as the clean support surface beneath raw survey patches; next improve it with datum-aware blending and CoNED/USGS Bay DEM inputs."
    if source_id.startswith("noaa_crm"):
        return "Keep as continuity base, but replace visually/scientifically wherever CoNED, CUDEM, BAG, or CSMP exists."
    if source_id.startswith("noaa_cudem"):
        return "Compare against USGS CoNED and use whichever has cleaner Bay/coast coverage and datum metadata."
    if source_id.startswith("noaa_nos"):
        return "Add VDatum/tidal-datum conversion before using as exact sea-level contour authority."
    if source_id.startswith("noaa_ocm_area_a_interferometric"):
        return "Use as broad high-detail Bay-floor terrain; let multibeam/BAG/USGS DEM sources override it where better data exists."
    if source_id.startswith("noaa_ocm_area_a"):
        return "Use as high-detail Central Bay terrain now; compare overlap against the stitched USGS 1 m Bay DEM when that download becomes available."
    if source_id.startswith("usgs_csmp"):
        return "Keep bathymetry plus backscatter/character; add geology/habitat polygons from CSMP web services."
    if source_id == "usgs_sf_bay_1m_north_navd88_overview":
        return "Use as an honest North Bay visual/detail fallback while requesting repair or republishing of the full USGS North Bay 1 m BigTIFF."
    if source_id.startswith("usgs_sf_bay_1m"):
        return "Use as the preferred Bay-interior terrain and contour source after overlap/datum checks against CUDEM, DS684, and NOAA BAG patches."
    if source_id.startswith("usgs_farallon") or source_id.startswith("usgs_rittenburg"):
        return "Search NOAA/NCEI for neighboring multibeam/BAG surveys to reduce patch-edge gaps."
    if source_id.startswith("usgs_ds684"):
        return "Keep for Golden Gate/SF Bar; compare against CoNED and newer Bay DEMs."
    if score <= 2:
        return "Replace with higher-resolution source where any exists."
    return "Keep and improve metadata/datum handling."


def write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# Survey Inventory",
        "",
        "This file is generated by `python3 scripts/build_survey_inventory.py`.",
        "",
        "It is a small audit of data quality, not a replacement for the raw DEMs.",
        "",
        "## Current Source Scores",
        "",
        "| Source | Family | Resolution | Area sq km | Score | Tier | Datum caution |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for item in payload["sources"]:
        lines.append(
            f"| {item['label']} | {item['sourceFamily']} | {item['nativeResolution']} | "
            f"{item['approxFootprintSqKm']} | {item['detailScore']} | {item['qualityTier']} | "
            f"{item['datumNote']} |"
        )

    lines.extend([
        "",
        "## Highest-Value Next Data Chases",
        "",
        "| Candidate | Priority | Why | Next action |",
        "|---|---|---|---|",
    ])
    for candidate in payload["nextDataCandidates"]:
        lines.append(
            f"| [{candidate['label']}]({candidate['sourceUrl']}) | {candidate['priority']} | "
            f"{candidate['reason']} | {candidate['nextAction']} |"
        )

    lines.extend([
        "",
        "## Plain-English Reading",
        "",
        "- A high score means the source has fine elevation detail and/or measured sonar/bottom-type context.",
        "- A low score does not mean the source is useless. It usually means it is a broad background surface that keeps the scene continuous.",
        "- The biggest scientific risk is vertical datum mismatch: the app currently combines sources whose zero-height references are not all the same.",
        "- The biggest detail gap is not around the nearshore CSMP blocks; it is seamless high-resolution coverage across the Bay interior and the offshore shelf gaps between survey patches.",
        "",
    ])
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))


def build_inventory(with_gdalinfo: bool) -> dict[str, Any]:
    module = load_generator_module()
    manifest = read_json(MANIFEST_PATH)
    terrains = manifest["slices"][0]["terrains"]
    sources = [source_record(module, terrain, with_gdalinfo) for terrain in terrains]
    sources.sort(key=lambda item: (-item["detailScore"], item["sourceFamily"], item["label"]))

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "studyBounds": manifest["studyBounds"],
        "summary": {
            "sourceCount": len(sources),
            "excellentLocalDetailCount": sum(1 for item in sources if item["qualityTier"] == "excellent local detail"),
            "highDetailPatchCount": sum(1 for item in sources if item["qualityTier"] == "high detail patch"),
            "broadSupportSurfaceCount": sum(1 for item in sources if item["qualityTier"] == "broad support surface"),
            "rawPresentCount": sum(1 for item in sources if item["raw"]["present"]),
            "summedApproxFootprintSqKm": round(sum(item["approxFootprintSqKm"] for item in sources), 1),
            "summedAreaNote": "Footprints overlap; this is useful for inventory scale, not unique dissolved coverage.",
        },
        "sources": sources,
        "nextDataCandidates": NEXT_DATA_CANDIDATES,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-gdalinfo", action="store_true", help="Run gdalinfo on primary local raw rasters.")
    args = parser.parse_args()

    payload = build_inventory(with_gdalinfo=args.with_gdalinfo)
    write_json(OUT_JSON, payload)
    write_markdown(payload)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
