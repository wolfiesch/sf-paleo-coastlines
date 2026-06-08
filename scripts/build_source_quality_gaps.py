#!/usr/bin/env python3
"""Build a geographic source-quality gap audit for the fused terrain.

This script reads the low-resolution source-quality texture generated for the
best-available terrain. The texture says which source class won each sampled
pixel after the broad-to-detailed terrain stack was fused. We aggregate that
texture into a small GeoJSON grid so the project can see where the terrain is
mostly true survey detail, mostly CoNED foundation, or still broad fallback.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
MANIFEST_PATH = PALEO_DIR / "paleo_manifest.json"
SOURCE_QUALITY_JSON = PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.json"
SOURCE_QUALITY_PNG = PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.png"
OUT_GEOJSON = PALEO_DIR / "source_quality_gaps.geojson"
OUT_SUMMARY = PALEO_DIR / "source_quality_gaps_summary.json"
OUT_MD = ROOT / "docs" / "source-quality-gaps.md"


CATEGORY_COLORS: dict[str, tuple[int, int, int]] = {
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
    "USGS Bay DEM": (105, 245, 163),
    "other": (220, 230, 240),
}

BROAD_CATEGORIES = {"CRM fallback", "CUDEM support"}
CONED_CATEGORIES = {"USGS CoNED broad", "USGS CoNED focus"}
DETAIL_CATEGORIES = {
    "NOAA OCM survey",
    "NOAA BAG survey",
    "NOAA multibeam",
    "USGS land LiDAR",
    "USGS nearshore",
    "USGS offshore",
    "USGS Bay DEM",
}

TIER_LABELS = {
    "critical_gap": "Critical broad-data gap",
    "support_gap": "Broad support gap",
    "coned_foundation": "Good CoNED foundation, low measured detail",
    "mixed_foundation": "Mixed foundation",
    "measured_detail": "Measured local detail",
    "high_detail": "High-detail survey/source patch",
}

PRIORITY_ZONES: list[dict[str, Any]] = [
    {
        "id": "outer_shelf_northwest",
        "label": "Northwest outer shelf",
        "bounds": [-123.55, 37.95, -123.15, 38.15],
        "whyItMatters": "This is the broadest visible fallback area near the far-west/northwest part of the current fused scene.",
    },
    {
        "id": "farallon_shelf",
        "label": "Farallon Islands and shelf",
        "bounds": [-123.30, 37.40, -122.70, 38.02],
        "whyItMatters": "This is where the 20k shoreline story gets most interesting, because islands and submerged shelf highs emerge as sea level drops.",
    },
    {
        "id": "farallon_to_gate_corridor",
        "label": "Farallon-to-Golden-Gate corridor",
        "bounds": [-123.10, 37.62, -122.62, 37.92],
        "whyItMatters": "This is the visual path between the old outer coast and today's Golden Gate.",
    },
    {
        "id": "golden_gate_sf_bar",
        "label": "Golden Gate and San Francisco Bar",
        "bounds": [-122.82, 37.62, -122.42, 37.88],
        "whyItMatters": "This is the key constriction where old drainage, bathymetry, and the modern bay entrance meet.",
    },
    {
        "id": "central_bay",
        "label": "Central Bay floor",
        "bounds": [-122.55, 37.65, -122.18, 38.08],
        "whyItMatters": "This is where Bay-floor survey detail can make the modern-bay interior look much less smooth.",
    },
    {
        "id": "north_bay_edge",
        "label": "North Bay edge",
        "bounds": [-122.70, 37.88, -122.15, 38.15],
        "whyItMatters": "This helps separate true measured Bay detail from broad support on the northern side of the scene.",
    },
    {
        "id": "south_bay_edge",
        "label": "South Bay edge",
        "bounds": [-122.62, 37.35, -122.15, 37.72],
        "whyItMatters": "This area has large shallow modern-bay surfaces where extra survey data can visibly change the exposed-waterline story.",
    },
    {
        "id": "outer_shelf_south",
        "label": "Southern outer shelf",
        "bounds": [-123.55, 37.35, -122.70, 37.65],
        "whyItMatters": "This captures the lower-left offshore portion of the current scene and helps avoid only optimizing the Golden Gate.",
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path == OUT_GEOJSON:
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
        return
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def best_available_bounds(manifest: dict[str, Any]) -> list[float]:
    terrains = manifest["slices"][0].get("terrains", [])
    terrain = next(
        item for item in terrains
        if item.get("sourceId") == "best_available_gate_shelf_fusion"
    )
    return [float(value) for value in terrain["bounds"]]


def footprint_area_sqkm(bounds: list[float]) -> float:
    west, south, east, north = bounds
    mean_lat = math.radians((south + north) / 2)
    km_per_degree_lon = 111.32 * math.cos(mean_lat)
    km_per_degree_lat = 110.57
    return max(0.0, (east - west) * km_per_degree_lon) * max(0.0, (north - south) * km_per_degree_lat)


def color_category_lookup() -> dict[tuple[int, int, int], str]:
    return {rgb: category for category, rgb in CATEGORY_COLORS.items()}


def classify_tier(broad_pct: float, coned_pct: float, detail_pct: float) -> str:
    if broad_pct >= 70:
        return "critical_gap"
    if broad_pct >= 35:
        return "support_gap"
    if detail_pct >= 70:
        return "high_detail"
    if detail_pct >= 40:
        return "measured_detail"
    if coned_pct >= 70:
        return "coned_foundation"
    return "mixed_foundation"


def next_action(tier: str, dominant_category: str) -> str:
    if tier == "critical_gap":
        return "Search NOAA/NCEI Bathymetric Data Viewer, USGS/CSMP, and regional multibeam/BAG records before adding more visual polish here."
    if tier == "support_gap":
        return "Replace CRM/CUDEM support with CoNED, BAG, multibeam, or CSMP patches if coverage exists."
    if tier == "coned_foundation":
        return "CoNED is already a strong 2 m base; the next leap is measured survey texture, sonar/backscatter, or datum-checked local DEM overlays."
    if tier == "measured_detail":
        return "Keep this as visual evidence; improve exact paleo claims by checking vertical datum and patch-edge blending."
    if tier == "high_detail":
        return "This is one of the current best areas; use it as the visual benchmark for weaker cells."
    if dominant_category == "USGS CoNED focus":
        return "Good focused CoNED coverage; look for overlapping survey products only if we want more texture and scientific context."
    return "Mixed source area; inspect the source-quality overlay before prioritizing another download."


def quality_score(broad_pct: float, coned_pct: float, detail_pct: float) -> float:
    """Return a 0-100 score where higher means better source quality."""
    return round((detail_pct * 1.0) + (coned_pct * 0.72) + ((100 - broad_pct) * 0.08), 2)


def gap_score(broad_pct: float, coned_pct: float, detail_pct: float) -> float:
    """Return a 0-100 score where higher means a better place to chase data."""
    score = (broad_pct * 0.9) + (max(0.0, 55.0 - detail_pct) * 0.55)
    if coned_pct >= 70 and detail_pct < 20:
        score += 8.0
    return round(min(score, 100.0), 2)


def pct(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def cell_bounds(
    terrain_bounds: list[float],
    width: int,
    height: int,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> list[float]:
    west, south, east, north = terrain_bounds
    cell_west = west + (x0 / width) * (east - west)
    cell_east = west + (x1 / width) * (east - west)
    cell_north = north - (y0 / height) * (north - south)
    cell_south = north - (y1 / height) * (north - south)
    return [
        round(cell_west, 7),
        round(cell_south, 7),
        round(cell_east, 7),
        round(cell_north, 7),
    ]


def polygon_from_bounds(bounds: list[float]) -> list[list[list[float]]]:
    west, south, east, north = bounds
    return [[
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]]


def center_from_bounds(bounds: list[float]) -> list[float]:
    west, south, east, north = bounds
    return [round((west + east) / 2, 7), round((south + north) / 2, 7)]


def contains_point(bounds: list[float], point: list[float]) -> bool:
    west, south, east, north = bounds
    lon, lat = point
    return west <= lon <= east and south <= lat <= north


def representative_cells(cells: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for cell in cells:
        center = cell["center"]
        if any(abs(center[0] - other["center"][0]) < 0.08 and abs(center[1] - other["center"][1]) < 0.08 for other in selected):
            continue
        selected.append(cell)
        if len(selected) >= limit:
            break
    return selected


def build_zone_summaries(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for zone in PRIORITY_ZONES:
        cells = [
            feature for feature in features
            if contains_point(zone["bounds"], feature["properties"]["center"])
        ]
        total_weight = sum(float(feature["properties"]["validPixelCount"]) for feature in cells)
        if total_weight == 0:
            continue

        broad = sum(
            float(feature["properties"]["broadFallbackPercent"]) * float(feature["properties"]["validPixelCount"])
            for feature in cells
        ) / total_weight
        coned = sum(
            float(feature["properties"]["conedFoundationPercent"]) * float(feature["properties"]["validPixelCount"])
            for feature in cells
        ) / total_weight
        detail = sum(
            float(feature["properties"]["measuredDetailPercent"]) * float(feature["properties"]["validPixelCount"])
            for feature in cells
        ) / total_weight
        gap = sum(
            float(feature["properties"]["gapPriorityScore"]) * float(feature["properties"]["validPixelCount"])
            for feature in cells
        ) / total_weight
        quality = sum(
            float(feature["properties"]["qualityScore"]) * float(feature["properties"]["validPixelCount"])
            for feature in cells
        ) / total_weight
        tier = classify_tier(broad, coned, detail)
        dominant_tiers = Counter(str(feature["properties"]["tier"]) for feature in cells)
        dominant_categories = Counter(str(feature["properties"]["dominantCategory"]) for feature in cells)
        category_weights: Counter[str] = Counter()
        for feature in cells:
            valid_pixels = float(feature["properties"]["validPixelCount"])
            for category, percent in feature["properties"]["categoryPercents"].items():
                category_weights[category] += valid_pixels * (float(percent) / 100)
        category_percents = {
            category: round((weight / total_weight) * 100, 2)
            for category, weight in sorted(category_weights.items())
        }
        top_categories = [
            {"category": category, "percent": percent}
            for category, percent in sorted(category_percents.items(), key=lambda item: (-item[1], item[0]))[:4]
        ]
        summaries.append({
            "id": zone["id"],
            "label": zone["label"],
            "bounds": zone["bounds"],
            "cellCount": len(cells),
            "dominantTier": dominant_tiers.most_common(1)[0][0],
            "dominantCategory": dominant_categories.most_common(1)[0][0],
            "broadFallbackPercent": round(broad, 2),
            "conedFoundationPercent": round(coned, 2),
            "measuredDetailPercent": round(detail, 2),
            "gapPriorityScore": round(gap, 2),
            "qualityScore": round(quality, 2),
            "tier": tier,
            "tierLabel": TIER_LABELS[tier],
            "whyItMatters": zone["whyItMatters"],
            "nextAction": next_action(tier, dominant_categories.most_common(1)[0][0]),
            "categoryPercents": category_percents,
            "topCategories": top_categories,
        })
    summaries.sort(
        key=lambda item: (
            -float(item["gapPriorityScore"]),
            -float(item["broadFallbackPercent"]),
            str(item["label"]),
        )
    )
    return summaries


def build_gap_grid(columns: int, min_valid_fraction: float) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = read_json(MANIFEST_PATH)
    source_quality = read_json(SOURCE_QUALITY_JSON)
    terrain_bounds = best_available_bounds(manifest)

    with Image.open(SOURCE_QUALITY_PNG) as image:
        rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)

    height, width = rgba.shape[:2]
    rows = max(1, round(columns * height / width))
    lookup = color_category_lookup()
    global_counts = Counter()
    features: list[dict[str, Any]] = []
    tier_counts = Counter()
    tier_area_sqkm = Counter()
    priority_cells: list[dict[str, Any]] = []

    for y_index in range(rows):
        y0 = round((y_index / rows) * height)
        y1 = round(((y_index + 1) / rows) * height)
        for x_index in range(columns):
            x0 = round((x_index / columns) * width)
            x1 = round(((x_index + 1) / columns) * width)
            block = rgba[y0:y1, x0:x1]
            if block.size == 0:
                continue

            valid = block[:, :, 3] > 0
            valid_count = int(valid.sum())
            total_count = int(block.shape[0] * block.shape[1])
            if total_count == 0 or (valid_count / total_count) < min_valid_fraction:
                continue

            rgb_values = block[:, :, :3][valid]
            counts: Counter[str] = Counter()
            for rgb in rgb_values:
                counts[lookup.get(tuple(int(value) for value in rgb), "other")] += 1

            if not counts:
                continue

            global_counts.update(counts)
            dominant_category, dominant_count = counts.most_common(1)[0]
            broad_count = sum(counts[category] for category in BROAD_CATEGORIES)
            coned_count = sum(counts[category] for category in CONED_CATEGORIES)
            detail_count = sum(counts[category] for category in DETAIL_CATEGORIES)
            broad_pct = pct(broad_count, valid_count)
            coned_pct = pct(coned_count, valid_count)
            detail_pct = pct(detail_count, valid_count)
            tier = classify_tier(broad_pct, coned_pct, detail_pct)
            bounds = cell_bounds(terrain_bounds, width, height, x0, x1, y0, y1)
            center = center_from_bounds(bounds)
            area_sqkm = round(footprint_area_sqkm(bounds), 2)
            tier_counts[tier] += 1
            tier_area_sqkm[tier] += area_sqkm

            category_pcts = {
                category: pct(count, valid_count)
                for category, count in sorted(counts.items())
            }
            properties = {
                "cellId": f"qg-{y_index:02d}-{x_index:02d}",
                "gridColumn": x_index,
                "gridRow": y_index,
                "center": center,
                "dominantCategory": dominant_category,
                "dominantPercent": pct(dominant_count, valid_count),
                "broadFallbackPercent": broad_pct,
                "conedFoundationPercent": coned_pct,
                "measuredDetailPercent": detail_pct,
                "qualityScore": quality_score(broad_pct, coned_pct, detail_pct),
                "gapPriorityScore": gap_score(broad_pct, coned_pct, detail_pct),
                "tier": tier,
                "tierLabel": TIER_LABELS[tier],
                "approxAreaSqKm": area_sqkm,
                "validPixelCount": valid_count,
                "categoryPercents": category_pcts,
                "nextAction": next_action(tier, dominant_category),
            }
            feature = {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": polygon_from_bounds(bounds),
                },
            }
            features.append(feature)
            priority_cells.append({
                "cellId": properties["cellId"],
                "bounds": bounds,
                "center": center,
                "dominantCategory": dominant_category,
                "dominantPercent": properties["dominantPercent"],
                "broadFallbackPercent": broad_pct,
                "conedFoundationPercent": coned_pct,
                "measuredDetailPercent": detail_pct,
                "gapPriorityScore": properties["gapPriorityScore"],
                "tier": tier,
                "tierLabel": properties["tierLabel"],
                "nextAction": properties["nextAction"],
            })

    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    priority_cells.sort(
        key=lambda item: (
            -float(item["gapPriorityScore"]),
            -float(item["broadFallbackPercent"]),
            str(item["cellId"]),
        )
    )
    features.sort(key=lambda item: str(item["properties"]["cellId"]))
    zone_summaries = build_zone_summaries(features)

    total_pixels = sum(global_counts.values())
    global_percents = {
        category: pct(count, total_pixels)
        for category, count in sorted(global_counts.items())
    }
    broad_total = sum(global_counts[category] for category in BROAD_CATEGORIES)
    coned_total = sum(global_counts[category] for category in CONED_CATEGORIES)
    detail_total = sum(global_counts[category] for category in DETAIL_CATEGORIES)

    summary = {
        "generatedAt": generated_at,
        "sourceTexture": "/" + str(SOURCE_QUALITY_PNG.relative_to(ROOT / "public")),
        "sourceProvenance": "/" + str(SOURCE_QUALITY_JSON.relative_to(ROOT / "public")),
        "grid": {
            "columns": columns,
            "rows": rows,
            "featureCount": len(features),
            "minValidFraction": min_valid_fraction,
        },
        "bounds": terrain_bounds,
        "sourceQualityPixelSize": source_quality.get("pixelSize"),
        "globalCategoryPercentsFromCells": global_percents,
        "globalCategoryPercentsFromSource": source_quality.get("categoryPixelPercents", {}),
        "sourceFamilyPercents": {
            "broadFallbackOrSupport": pct(broad_total, total_pixels),
            "conedFoundation": pct(coned_total, total_pixels),
            "measuredDetail": pct(detail_total, total_pixels),
        },
        "tierCounts": dict(sorted(tier_counts.items())),
        "tierAreaSqKm": {
            tier: round(area, 2)
            for tier, area in sorted(tier_area_sqkm.items())
        },
        "topPriorityCells": priority_cells[:20],
        "representativePriorityCells": representative_cells(priority_cells),
        "priorityZones": zone_summaries,
        "note": "Cells are derived from the fused terrain source-quality texture. They show current source confidence, not scientific certainty about paleo sea level.",
    }

    geojson = {
        "type": "FeatureCollection",
        "name": "source_quality_gaps",
        "generatedAt": generated_at,
        "properties": {
            "summaryUrl": "/" + str(OUT_SUMMARY.relative_to(ROOT / "public")),
            "sourceTexture": "/" + str(SOURCE_QUALITY_PNG.relative_to(ROOT / "public")),
            "note": summary["note"],
        },
        "features": features,
    }
    return geojson, summary


def write_markdown(summary: dict[str, Any]) -> None:
    source_family = summary["sourceFamilyPercents"]
    lines = [
        "# Source Quality Gaps",
        "",
        "This file is generated by `python3 scripts/build_source_quality_gaps.py`.",
        "",
        "It answers a practical question: where is the 3D terrain already backed by measured local data, and where are we still relying on broad background surfaces?",
        "",
        "## Current Terrain Mix",
        "",
        "| Source family | Share of visible fused surface | Plain-English meaning |",
        "|---|---:|---|",
        f"| Broad fallback/support | {source_family['broadFallbackOrSupport']}% | Useful for continuity, but not where the best detail lives. |",
        f"| CoNED foundation | {source_family['conedFoundation']}% | Strong 2 m land-plus-seafloor base; good, but not as visually rich as survey/backscatter patches. |",
        f"| Measured detail | {source_family['measuredDetail']}% | The best current visual/scientific detail: BAG, OCM, NOAA multibeam, USGS Bay DEM, LiDAR, CSMP, and offshore survey patches. |",
        "",
        "## Cell Types",
        "",
        "| Cell type | Cell count | Approx area sq km | What to do next |",
        "|---|---:|---:|---|",
    ]

    for tier, label in TIER_LABELS.items():
        count = summary["tierCounts"].get(tier, 0)
        area = summary["tierAreaSqKm"].get(tier, 0)
        action = {
            "critical_gap": "Chase new bathymetry first.",
            "support_gap": "Replace broad support where survey/CoNED exists.",
            "coned_foundation": "Look for survey texture or scientific overlays.",
            "mixed_foundation": "Inspect case by case.",
            "measured_detail": "Keep, then datum-check.",
            "high_detail": "Use as quality benchmark.",
        }[tier]
        lines.append(f"| {label} | {count} | {area} | {action} |")

    lines.extend([
        "",
        "## Priority Zones",
        "",
        "| Zone | Broad fallback | CoNED base | Measured detail | Gap score | What it means | Next action |",
        "|---|---:|---:|---:|---:|---|---|",
    ])

    for zone in summary["priorityZones"]:
        lines.append(
            f"| {zone['label']} | {zone['broadFallbackPercent']}% | "
            f"{zone['conedFoundationPercent']}% | {zone['measuredDetailPercent']}% | "
            f"{zone['gapPriorityScore']} | {zone['whyItMatters']} | {zone['nextAction']} |"
        )

    lines.extend([
        "",
        "## Highest-Priority Data Gaps",
        "",
        "| Cell | Dominant source | Broad fallback | CoNED base | Measured detail | Score | Bounds | Next action |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ])

    for cell in summary["representativePriorityCells"]:
        bounds = ", ".join(str(value) for value in cell["bounds"])
        lines.append(
            f"| {cell['cellId']} | {cell['dominantCategory']} | "
            f"{cell['broadFallbackPercent']}% | {cell['conedFoundationPercent']}% | "
            f"{cell['measuredDetailPercent']}% | {cell['gapPriorityScore']} | "
            f"`[{bounds}]` | {cell['nextAction']} |"
        )

    lines.extend([
        "",
        "## How To Read This",
        "",
        "- A high gap score means the cell is a good place to chase more real data.",
        "- A CoNED-only cell is not bad. It means we have a solid 2 m base, but not much measured survey texture or bottom-character context there yet.",
        "- A broad fallback cell is where the view is most likely to look smooth or generic, because it is leaning on CRM/CUDEM support rather than local high-detail patches.",
        "- This is a source-quality map, not a paleo-certainty map. It does not solve vertical datum mismatches, erosion, sediment, marsh growth, or tectonic motion.",
        "",
    ])
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a source-quality gap GeoJSON and report.")
    parser.add_argument("--columns", type=int, default=96, help="Number of grid columns to emit.")
    parser.add_argument(
        "--min-valid-fraction",
        type=float,
        default=0.15,
        help="Minimum fraction of a cell that must have source-quality pixels.",
    )
    args = parser.parse_args()

    geojson, summary = build_gap_grid(
        columns=args.columns,
        min_valid_fraction=args.min_valid_fraction,
    )
    write_json(OUT_GEOJSON, geojson)
    write_json(OUT_SUMMARY, summary)
    write_markdown(summary)
    print(f"Wrote {OUT_GEOJSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
