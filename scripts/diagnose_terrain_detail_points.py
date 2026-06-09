#!/usr/bin/env python3
"""Sample fused terrain source quality at named map points.

This is a small evidence helper for visual QA. It answers: "why does this
place look sharper or blurrier than that place?" by checking which source class
won in the best-available terrain source-quality texture.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
SUMMARY_JSON = PALEO_DIR / "source_quality_gaps_summary.json"
SOURCE_TEXTURE = PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.png"
SOURCE_PROVENANCE = PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.json"
OUT_JSON = PALEO_DIR / "terrain_detail_point_diagnosis.json"
OUT_MD = ROOT / "docs" / "terrain-detail-point-diagnosis.md"


SOURCE_COLORS = {
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


DEFAULT_POINTS = [
    {
        "id": "marin_headlands",
        "label": "Marin Headlands / north Golden Gate",
        "lon": -122.535,
        "lat": 37.835,
        "note": "Representative crisp headlands area visible in the screenshot.",
    },
    {
        "id": "golden_gate_channel",
        "label": "Golden Gate channel",
        "lon": -122.49,
        "lat": 37.82,
        "note": "The narrow modern Gate and adjacent nearshore bathymetry.",
    },
    {
        "id": "presidio_north_sf",
        "label": "Presidio / north San Francisco",
        "lon": -122.47,
        "lat": 37.80,
        "note": "San Francisco land side with local LiDAR coverage.",
    },
    {
        "id": "ocean_beach_west_sf",
        "label": "Ocean Beach / west San Francisco",
        "lon": -122.51,
        "lat": 37.76,
        "note": "San Francisco ocean-facing side near the SF Bar detail data.",
    },
    {
        "id": "central_bay_floor",
        "label": "Central Bay floor east of San Francisco",
        "lon": -122.35,
        "lat": 37.80,
        "note": "A flatter Bay-floor area that can look smoother even with good data.",
    },
    {
        "id": "east_bay_broad_coned",
        "label": "Farther east Bay smooth area",
        "lon": -122.22,
        "lat": 37.80,
        "note": "Representative area where the current source-quality map often falls back to broad CoNED.",
    },
]


@dataclass(frozen=True)
class PointDiagnosis:
    id: str
    label: str
    lon: float
    lat: float
    pixel: tuple[int, int]
    source_category: str
    source_family: str
    likely_visual_read: str
    next_action: str
    note: str


def load_points(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return DEFAULT_POINTS
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise SystemExit("Point file must be a JSON array of {id,label,lon,lat,note} objects.")
    return payload


def category_for_pixel(pixel: tuple[int, int, int, int]) -> str:
    rgb = pixel[:3]
    for category, color in SOURCE_COLORS.items():
        if rgb == color:
            return category
    return "unknown"


def category_family(category: str) -> str:
    if category in {"CRM fallback", "CUDEM support"}:
        return "Broad fallback/support"
    if category in {"USGS CoNED broad", "USGS CoNED focus"}:
        return "CoNED foundation"
    if category == "unknown":
        return "Unknown"
    return "Measured detail"


def likely_visual_read(category: str) -> str:
    if category in {"CRM fallback", "CUDEM support"}:
        return "Most likely to look smooth or generic because this is broad support data."
    if category == "USGS CoNED broad":
        return "Usually solid but can look soft because it is a broad 2 m base, not a rich survey texture."
    if category == "USGS CoNED focus":
        return "Usually sharper than broad CoNED because the focused clip keeps more pixels per mile."
    if category == "USGS land LiDAR":
        return "Should sharpen modern above-water land, but it will not improve underwater bathymetry."
    if category in {"USGS Bay DEM", "USGS Bay DEM overview"}:
        return "Good Bay-floor data, though flat mudflats and channels can still look visually smooth."
    if category in {"USGS nearshore", "USGS offshore", "NOAA BAG survey", "NOAA OCM survey", "NOAA multibeam"}:
        return "Backed by measured survey data; if it still looks blurry, check browser downsampling or terrain smoothing."
    return "The source class was not recognized; inspect the source-quality texture and provenance JSON."


def recommended_next_action(category: str) -> str:
    if category in {"CRM fallback", "CUDEM support"}:
        return "Search for a better local bathymetry or terrain source before visual polish."
    if category == "USGS CoNED broad":
        return "Try a smaller focused CoNED clip or look for overlapping survey texture."
    if category == "USGS CoNED focus":
        return "Look for survey/backscatter overlays only if this area still needs more texture."
    if category == "USGS land LiDAR":
        return "Use the LiDAR layer for land detail; add bathymetry only if the blurry area is underwater."
    if category in {"USGS Bay DEM", "USGS Bay DEM overview"}:
        return "Check whether the surface is truly flat, then compare sharp vs smooth rendering."
    if category in {"USGS nearshore", "USGS offshore", "NOAA BAG survey", "NOAA OCM survey", "NOAA multibeam"}:
        return "Compare source mode, sharp smoothing, and higher tile/detail settings before chasing new data."
    return "Inspect manually."


def lon_lat_to_pixel(lon: float, lat: float, bounds: list[float], width: int, height: int) -> tuple[int, int]:
    west, south, east, north = bounds
    x = round(((lon - west) / (east - west)) * (width - 1))
    y = round(((north - lat) / (north - south)) * (height - 1))
    return max(0, min(width - 1, x)), max(0, min(height - 1, y))


def diagnose(points: list[dict[str, Any]]) -> list[PointDiagnosis]:
    summary = json.loads(SUMMARY_JSON.read_text())
    bounds = [float(value) for value in summary["bounds"]]
    image = Image.open(SOURCE_TEXTURE).convert("RGBA")
    diagnoses: list[PointDiagnosis] = []

    for point in points:
        lon = float(point["lon"])
        lat = float(point["lat"])
        pixel = lon_lat_to_pixel(lon, lat, bounds, image.width, image.height)
        category = category_for_pixel(image.getpixel(pixel))
        diagnoses.append(PointDiagnosis(
            id=str(point.get("id") or point["label"]),
            label=str(point["label"]),
            lon=lon,
            lat=lat,
            pixel=pixel,
            source_category=category,
            source_family=category_family(category),
            likely_visual_read=likely_visual_read(category),
            next_action=recommended_next_action(category),
            note=str(point.get("note", "")),
        ))

    return diagnoses


def write_outputs(diagnoses: list[PointDiagnosis]) -> None:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "generatedAt": generated_at,
        "plainEnglishPurpose": (
            "Sample named places against the best-available terrain source-quality texture "
            "so visual sharpness/blurriness can be tied to the data source currently winning there."
        ),
        "sourceTexture": str(SOURCE_TEXTURE.relative_to(ROOT)),
        "sourceProvenance": str(SOURCE_PROVENANCE.relative_to(ROOT)),
        "points": [diagnosis.__dict__ for diagnosis in diagnoses],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Terrain Detail Point Diagnosis",
        "",
        "This file is generated by `python3 scripts/diagnose_terrain_detail_points.py`.",
        "",
        "Plain-English purpose: tie visible sharpness or blurriness to the terrain source currently winning at named map points.",
        "",
        "## Sampled Points",
        "",
        "| Place | Winning source class | Source family | Likely visual read | Next action |",
        "|---|---|---|---|---|",
    ]
    for diagnosis in diagnoses:
        lines.append(
            f"| {diagnosis.label} | {diagnosis.source_category} | {diagnosis.source_family} | "
            f"{diagnosis.likely_visual_read} | {diagnosis.next_action} |"
        )

    lines.extend([
        "",
        "## How To Read This",
        "",
        "- `Winning source class` means the source-quality texture says that source type supplied the final fused terrain at that point.",
        "- This does not prove the terrain is scientifically perfect. It only explains the current visual data source.",
        "- Steep real-world terrain can look sharper than flat terrain even when both use good data.",
        "- If a measured-detail point still looks blurry, first compare `Sharp` smoothing, `Source` mode, and terrain tile/detail settings before chasing new data.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose terrain source detail at named lon/lat points.")
    parser.add_argument("--points", type=Path, help="Optional JSON array of named lon/lat points to sample.")
    args = parser.parse_args()

    diagnoses = diagnose(load_points(args.points))
    write_outputs(diagnoses)
    for diagnosis in diagnoses:
        print(f"{diagnosis.label}: {diagnosis.source_category} ({diagnosis.source_family})")


if __name__ == "__main__":
    main()
