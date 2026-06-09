#!/usr/bin/env python3
"""Find official NOAA bathymetry candidates for current source-quality gaps."""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from osgeo import gdal

gdal.UseExceptions()


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work"
GAP_SUMMARY = PALEO_DIR / "source_quality_gaps_summary.json"
OUT_JSON = PALEO_DIR / "external_bathymetry_candidates.json"
OUT_MD = ROOT / "docs" / "external-bathymetry-candidates.md"

BAG_QUERY_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/bag_bathymetry/ImageServer/query"
MULTIBEAM_QUERY_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_footprints/MapServer/0/query"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def cell_center(cell: dict[str, Any]) -> tuple[float, float]:
    lon, lat = cell["center"]
    return float(lon), float(lat)


def distance_degrees(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def expanded_bounds(bounds: list[float], padding: float = 0.08) -> list[float]:
    west, south, east, north = [float(value) for value in bounds]
    return [west - padding, south - padding, east + padding, north + padding]


def matching_local_rasters(name: str | None) -> list[Path]:
    if not name:
        return []
    needle = name.lower().split("_")[0]
    return sorted(WORK_DIR.glob(f"*{needle}*terrain_wgs84.tif"))


def local_raster_coverage(path: Path, bounds: list[float], center: tuple[float, float]) -> dict[str, Any] | None:
    ds = gdal.Open(str(path))
    if ds is None:
        return None
    gt = ds.GetGeoTransform()
    inv = gdal.InvGeoTransform(gt)
    if inv is None:
        return None

    def world_to_pixel(lon: float, lat: float) -> tuple[int, int]:
        x = int(math.floor(inv[0] + inv[1] * lon + inv[2] * lat))
        y = int(math.floor(inv[3] + inv[4] * lon + inv[5] * lat))
        return x, y

    west, south, east, north = bounds
    px0, py0 = world_to_pixel(west, north)
    px1, py1 = world_to_pixel(east, south)
    x0, x1 = sorted((px0, px1))
    y0, y1 = sorted((py0, py1))
    x0 = max(0, min(ds.RasterXSize - 1, x0))
    x1 = max(0, min(ds.RasterXSize, x1 + 1))
    y0 = max(0, min(ds.RasterYSize - 1, y0))
    y1 = max(0, min(ds.RasterYSize, y1 + 1))
    if x1 <= x0 or y1 <= y0:
        return {
            "path": str(path.relative_to(ROOT)),
            "overlapsCell": False,
            "validPixelPercentInCell": 0.0,
            "centerValue": None,
        }

    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray(x0, y0, x1 - x0, y1 - y0)
    nodata = band.GetNoDataValue()
    valid = np.isfinite(arr)
    if nodata is not None:
        valid &= arr != nodata

    cx, cy = world_to_pixel(center[0], center[1])
    center_value = None
    if 0 <= cx < ds.RasterXSize and 0 <= cy < ds.RasterYSize:
        value = band.ReadAsArray(cx, cy, 1, 1)
        if value is not None:
            numeric = float(value[0][0])
            if np.isfinite(numeric) and (nodata is None or numeric != nodata):
                center_value = round(numeric, 3)

    return {
        "path": str(path.relative_to(ROOT)),
        "overlapsCell": True,
        "validPixelPercentInCell": round((int(valid.sum()) / int(valid.size)) * 100, 2) if valid.size else 0.0,
        "centerValue": center_value,
    }


def add_local_coverage(candidate: dict[str, Any], cell: dict[str, Any]) -> dict[str, Any]:
    names = [candidate.get("surveyId"), candidate.get("name"), candidate.get("nceiId")]
    rasters: list[Path] = []
    for name in names:
        for path in matching_local_rasters(str(name) if name else None):
            if path not in rasters:
                rasters.append(path)
    center = cell_center(cell)
    candidate["localRasterCoverage"] = [
        coverage for path in rasters
        if (coverage := local_raster_coverage(path, cell["bounds"], center)) is not None
    ]
    return candidate


def bag_candidates_for_cell(cell: dict[str, Any]) -> list[dict[str, Any]]:
    west, south, east, north = expanded_bounds(cell["bounds"])
    center = cell_center(cell)
    where = (
        f"CenterX >= {west} AND CenterX <= {east} "
        f"AND CenterY >= {south} AND CenterY <= {north}"
    )
    payload = fetch_json(BAG_QUERY_URL, {
        "f": "json",
        "where": where,
        "outFields": "Name,SurveyID,CenterX,CenterY,LowPSActual,HighPSActual,ProductName,GroupName",
        "returnGeometry": "false",
        "resultRecordCount": 50,
    })
    candidates = []
    for feature in payload.get("features", []):
        attrs = feature.get("attributes", {})
        candidate_center = (float(attrs.get("CenterX") or 0), float(attrs.get("CenterY") or 0))
        candidates.append(add_local_coverage({
            "kind": "NOAA BAG",
            "name": attrs.get("Name"),
            "surveyId": attrs.get("SurveyID"),
            "center": [round(candidate_center[0], 7), round(candidate_center[1], 7)],
            "distanceDegrees": round(distance_degrees(center, candidate_center), 5),
            "lowPixelSizeDegrees": attrs.get("LowPSActual"),
            "highPixelSizeDegrees": attrs.get("HighPSActual"),
            "downloadHint": "Use NOAA Bathymetric Data Viewer or BAG service item name.",
        }, cell))
    return sorted(candidates, key=lambda item: (item["distanceDegrees"], item.get("highPixelSizeDegrees") or 9))


def multibeam_candidates_for_cell(cell: dict[str, Any]) -> list[dict[str, Any]]:
    west, south, east, north = [float(value) for value in cell["bounds"]]
    payload = fetch_json(MULTIBEAM_QUERY_URL, {
        "f": "json",
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "NCEI_ID,SURVEY_ID,PLATFORM,SOURCE,INSTRUMENT,SURVEY_YEAR,DOWNLOAD_URL",
        "returnGeometry": "false",
        "resultRecordCount": 50,
    })
    candidates = []
    for feature in payload.get("features", []):
        attrs = feature.get("attributes", {})
        candidates.append(add_local_coverage({
            "kind": "NOAA multibeam",
            "name": attrs.get("SURVEY_ID"),
            "nceiId": attrs.get("NCEI_ID"),
            "platform": attrs.get("PLATFORM"),
            "source": attrs.get("SOURCE"),
            "instrument": attrs.get("INSTRUMENT"),
            "surveyYear": attrs.get("SURVEY_YEAR"),
            "downloadUrl": attrs.get("DOWNLOAD_URL"),
        }, cell))
    return sorted(candidates, key=lambda item: (-(item.get("surveyYear") or 0), item.get("name") or ""))


def build_audit(limit: int = 12) -> dict[str, Any]:
    summary = read_json(GAP_SUMMARY)
    cells = summary.get("representativePriorityCells", [])[:limit]
    audited_cells = []
    for cell in cells:
        audited_cells.append({
            "cellId": cell["cellId"],
            "center": cell["center"],
            "bounds": cell["bounds"],
            "tierLabel": cell["tierLabel"],
            "dominantCategory": cell["dominantCategory"],
            "broadFallbackPercent": cell["broadFallbackPercent"],
            "measuredDetailPercent": cell["measuredDetailPercent"],
            "bagCandidates": bag_candidates_for_cell(cell)[:8],
            "multibeamCandidates": multibeam_candidates_for_cell(cell)[:8],
        })

    unique_surveys: dict[str, dict[str, Any]] = {}
    for cell in audited_cells:
        for candidate in cell["bagCandidates"] + cell["multibeamCandidates"]:
            key = f"{candidate['kind']}:{candidate.get('surveyId') or candidate.get('name') or candidate.get('nceiId')}"
            unique_surveys[key] = candidate

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "plainEnglishPurpose": (
            "Query official NOAA bathymetry services for the current representative "
            "source-quality gap cells, so the next data hunt starts from concrete candidates."
        ),
        "services": {
            "bagQueryUrl": BAG_QUERY_URL,
            "multibeamQueryUrl": MULTIBEAM_QUERY_URL,
        },
        "auditedCells": audited_cells,
        "uniqueCandidateCount": len(unique_surveys),
    }


def write_markdown(audit: dict[str, Any]) -> None:
    lines = [
        "# External Bathymetry Candidates",
        "",
        "This file is generated by `python3 scripts/audit_external_bathymetry_candidates.py`.",
        "",
        "Plain-English purpose: look up official NOAA bathymetry records that overlap the current broad-data gap cells.",
        "",
        "## Best Next Lead",
        "",
        "Start with the northwest outer shelf cells that return local BAG and newer multibeam candidates. These are the best bet for replacing broad CUDEM support with more specific survey data.",
        "",
        "## Candidate Cells",
        "",
        "| Cell | Current weak source | BAG candidates | Multibeam candidates | Local coverage finding | First thing to try |",
        "|---|---|---:|---:|---|---|",
    ]
    for cell in audit["auditedCells"]:
        bag_names = ", ".join(item["name"] for item in cell["bagCandidates"][:3] if item.get("name")) or "none found"
        mb_names = ", ".join(item["name"] for item in cell["multibeamCandidates"][:3] if item.get("name")) or "none found"
        first = bag_names if bag_names != "none found" else mb_names
        coverage_notes = []
        for candidate in cell["bagCandidates"] + cell["multibeamCandidates"]:
            for coverage in candidate.get("localRasterCoverage", [])[:1]:
                coverage_notes.append(
                    f"{candidate.get('name')}: {coverage['validPixelPercentInCell']}% valid local pixels"
                )
        coverage_text = "; ".join(coverage_notes[:2]) or "no matching local raster coverage measured"
        lines.append(
            f"| {cell['cellId']} `{cell['center']}` | {cell['dominantCategory']} "
            f"({cell['broadFallbackPercent']}% broad) | {len(cell['bagCandidates'])} | "
            f"{len(cell['multibeamCandidates'])} | {coverage_text} | {first} |"
        )
        if bag_names != "none found" or mb_names != "none found":
            lines.append(
                f"|  |  |  |  |  | BAG: {bag_names}; multibeam: {mb_names} |"
            )

    lines.extend([
        "",
        "## How To Read This",
        "",
        "- `BAG` means a gridded bathymetry product. If it covers the gap, it is usually easier to plug into the terrain pipeline than raw ship tracks.",
        "- `Multibeam` means ship sonar coverage. It may be excellent evidence, but raw lines can require more processing before becoming a clean terrain surface.",
        "- A candidate here is not automatically better than the current terrain. The next step is to download one or two high-promise candidates, check coverage, check vertical datum, and compare against the current fused surface.",
        "",
        "## Official Services Queried",
        "",
        f"- BAG catalog: `{audit['services']['bagQueryUrl']}`",
        f"- Multibeam footprints: `{audit['services']['multibeamQueryUrl']}`",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    audit = build_audit()
    write_json(OUT_JSON, audit)
    write_markdown(audit)
    for cell in audit["auditedCells"]:
        print(
            f"{cell['cellId']}: {len(cell['bagCandidates'])} BAG, "
            f"{len(cell['multibeamCandidates'])} multibeam candidates"
        )


if __name__ == "__main__":
    main()
