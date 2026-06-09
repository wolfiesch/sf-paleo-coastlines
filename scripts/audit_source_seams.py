#!/usr/bin/env python3
"""Find likely visual seam targets from the best-available source-quality image."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_paleo_coastlines as paleo  # noqa: E402


SOURCE_TEXTURE = ROOT / "public/data/paleo-coastlines/terrain/best_available_gate_shelf_source_quality.png"
OUT_JSON = ROOT / "public/data/paleo-coastlines/source_seam_audit_targets.json"
OUT_MD = ROOT / "docs/source-seam-audit-targets.md"

COLOR_TO_CATEGORY = {
    paleo.source_quality_color("CRM fallback"): "CRM fallback",
    paleo.source_quality_color("CUDEM support"): "CUDEM support",
    paleo.source_quality_color("USGS CoNED broad"): "USGS CoNED broad",
    paleo.source_quality_color("USGS CoNED focus"): "USGS CoNED focus",
    paleo.source_quality_color("NOAA OCM survey"): "NOAA OCM survey",
    paleo.source_quality_color("NOAA BAG survey"): "NOAA BAG survey",
    paleo.source_quality_color("NOAA multibeam"): "NOAA multibeam",
    paleo.source_quality_color("USGS land LiDAR"): "USGS land LiDAR",
    paleo.source_quality_color("USGS nearshore"): "USGS nearshore",
    paleo.source_quality_color("USGS offshore"): "USGS offshore",
    paleo.source_quality_color("USGS Bay DEM overview"): "USGS Bay DEM overview",
    paleo.source_quality_color("USGS Bay DEM"): "USGS Bay DEM",
}

CATEGORY_CODES = {category: index + 1 for index, category in enumerate(COLOR_TO_CATEGORY.values())}
CODE_TO_CATEGORY = {code: category for category, code in CATEGORY_CODES.items()}

PAIR_IMPORTANCE = {
    ("CRM fallback", "NOAA BAG survey"): 100,
    ("CRM fallback", "NOAA multibeam"): 100,
    ("CRM fallback", "USGS offshore"): 95,
    ("CRM fallback", "USGS CoNED focus"): 90,
    ("CUDEM support", "NOAA BAG survey"): 95,
    ("CUDEM support", "NOAA multibeam"): 95,
    ("CUDEM support", "USGS offshore"): 90,
    ("USGS CoNED focus", "NOAA BAG survey"): 85,
    ("USGS CoNED focus", "NOAA OCM survey"): 80,
    ("USGS CoNED broad", "NOAA OCM survey"): 78,
    ("USGS CoNED focus", "USGS Bay DEM overview"): 76,
    ("USGS CoNED broad", "USGS Bay DEM overview"): 76,
    ("USGS CoNED focus", "USGS Bay DEM"): 75,
    ("USGS CoNED broad", "USGS Bay DEM"): 75,
    ("USGS CoNED focus", "NOAA multibeam"): 72,
    ("USGS land LiDAR", "USGS nearshore"): 70,
}


def pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def pair_importance(left: str, right: str) -> int:
    return PAIR_IMPORTANCE.get(pair_key(left, right), 50)


def category_codes_from_texture(path: Path) -> np.ndarray:
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    codes = np.zeros(rgba.shape[:2], dtype=np.uint8)
    for color, category in COLOR_TO_CATEGORY.items():
        mask = (
            (rgba[:, :, 0] == color[0])
            & (rgba[:, :, 1] == color[1])
            & (rgba[:, :, 2] == color[2])
            & (rgba[:, :, 3] > 0)
        )
        codes[mask] = CATEGORY_CODES[category]
    return codes


def pixel_to_lon_lat(x: float, y: float, width: int, height: int) -> tuple[float, float]:
    bounds = paleo.BEST_AVAILABLE_BOUNDS
    lon = float(bounds["west"]) + (x / max(width - 1, 1)) * (float(bounds["east"]) - float(bounds["west"]))
    lat = float(bounds["north"]) - (y / max(height - 1, 1)) * (float(bounds["north"]) - float(bounds["south"]))
    return round(lon, 6), round(lat, 6)


def collect_edges(codes: np.ndarray) -> dict[tuple[str, str], list[tuple[int, int]]]:
    height, width = codes.shape
    edges: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)

    right_changed = (codes[:, :-1] != codes[:, 1:]) & (codes[:, :-1] > 0) & (codes[:, 1:] > 0)
    ys, xs = np.nonzero(right_changed)
    for y, x in zip(ys.tolist(), xs.tolist()):
        left = CODE_TO_CATEGORY[int(codes[y, x])]
        right = CODE_TO_CATEGORY[int(codes[y, x + 1])]
        edges[pair_key(left, right)].append((x, y))

    down_changed = (codes[:-1, :] != codes[1:, :]) & (codes[:-1, :] > 0) & (codes[1:, :] > 0)
    ys, xs = np.nonzero(down_changed)
    for y, x in zip(ys.tolist(), xs.tolist()):
        left = CODE_TO_CATEGORY[int(codes[y, x])]
        right = CODE_TO_CATEGORY[int(codes[y + 1, x])]
        edges[pair_key(left, right)].append((x, y))

    return edges


def choose_targets(points: list[tuple[int, int]], width: int, height: int, max_targets: int = 4) -> list[dict[str, Any]]:
    if not points:
        return []
    grid: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    bucket_size = max(24, min(width, height) // 18)
    for x, y in points:
        grid[(x // bucket_size, y // bucket_size)].append((x, y))

    buckets = sorted(grid.values(), key=len, reverse=True)
    targets: list[dict[str, Any]] = []
    for bucket in buckets:
        if len(targets) >= max_targets:
            break
        xs = np.asarray([point[0] for point in bucket], dtype=np.float32)
        ys = np.asarray([point[1] for point in bucket], dtype=np.float32)
        x = float(np.median(xs))
        y = float(np.median(ys))
        lon, lat = pixel_to_lon_lat(x, y, width, height)
        targets.append({
            "lon": lon,
            "lat": lat,
            "edgePixelsInCluster": len(bucket),
            "pixel": [round(x, 1), round(y, 1)],
        })
    return targets


def recommended_view(pair: tuple[str, str]) -> str:
    categories = set(pair)
    if "CRM fallback" in categories or "CUDEM support" in categories:
        return "Shelf or NW Gap with Gaps and Coverage enabled"
    if "USGS land LiDAR" in categories:
        return "Gate with Coverage enabled"
    if "NOAA OCM survey" in categories or "USGS Bay DEM" in categories:
        return "Gate or Bay-facing view with Bay sources and Coverage enabled"
    return "Shelf with Coverage enabled"


def build_report() -> dict[str, Any]:
    codes = category_codes_from_texture(SOURCE_TEXTURE)
    height, width = codes.shape
    edges = collect_edges(codes)
    category_counts = Counter(CODE_TO_CATEGORY[int(code)] for code in codes.reshape(-1) if int(code) in CODE_TO_CATEGORY)

    transition_reports: list[dict[str, Any]] = []
    for pair, points in edges.items():
        importance = pair_importance(pair[0], pair[1])
        transition_reports.append({
            "categories": list(pair),
            "edgePixelCount": len(points),
            "importance": importance,
            "priorityScore": round(len(points) * (importance / 100), 2),
            "recommendedView": recommended_view(pair),
            "targets": choose_targets(points, width, height),
        })
    transition_reports.sort(key=lambda item: (-item["priorityScore"], -item["edgePixelCount"], item["categories"]))

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "texture": str(SOURCE_TEXTURE.relative_to(ROOT)),
        "bounds": paleo.BEST_AVAILABLE_BOUNDS,
        "pixelSize": [width, height],
        "categoryPixelCounts": dict(sorted(category_counts.items())),
        "transitionCount": len(transition_reports),
        "topTransitions": transition_reports[:40],
        "plainEnglishPurpose": "Find source-category boundaries that are most likely to create visible seams in the fused terrain.",
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Source Seam Audit Targets",
        "",
        "This file is generated by `python3 scripts/audit_source_seams.py`.",
        "",
        "It reads the best-available source-quality image and finds places where the winning source category changes. In plain English: these are the places most likely to show a join, ledge, texture change, or lighting change.",
        "",
        "## Summary",
        "",
        f"- Source-quality image: `{report['texture']}`",
        f"- Pixel size: `{report['pixelSize']}`",
        f"- Source-category transitions found: {report['transitionCount']}",
        "",
        "## Top Seam Targets",
        "",
        "| Categories | Edge pixels | Priority | First target lon/lat | Suggested view |",
        "|---|---:|---:|---|---|",
    ]
    for transition in report["topTransitions"][:20]:
        first = transition["targets"][0] if transition["targets"] else None
        target = f"`{first['lon']}, {first['lat']}`" if first else ""
        lines.append(
            f"| {' / '.join(transition['categories'])} | {transition['edgePixelCount']} | "
            f"{transition['priorityScore']} | {target} | {transition['recommendedView']} |"
        )

    lines.extend([
        "",
        "## Target Details",
        "",
    ])
    for transition in report["topTransitions"][:12]:
        lines.extend([
            f"### {' / '.join(transition['categories'])}",
            "",
            f"- Edge pixels: {transition['edgePixelCount']}",
            f"- Suggested view: {transition['recommendedView']}",
            "- Targets:",
        ])
        for target in transition["targets"]:
            lines.append(
                f"  - `{target['lon']}, {target['lat']}` "
                f"({target['edgePixelsInCluster']} nearby edge pixels)"
            )
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    report = build_report()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
