#!/usr/bin/env python3
"""Measure local height steps around source seam audit targets."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_source_seams as seams  # noqa: E402


SEAM_JSON = ROOT / "public/data/paleo-coastlines/source_seam_audit_targets.json"
OUT_MD = ROOT / "docs/local-seam-height-audit.md"
MANIFEST_JSON = ROOT / "public/data/paleo-coastlines/paleo_manifest.json"
SOURCE_TEXTURE = ROOT / "public/data/paleo-coastlines/terrain/best_available_gate_shelf_source_quality.png"
ELEVATION_PNG = ROOT / "public/data/paleo-coastlines/terrain/best_available_gate_shelf_elevation.png"
WINDOW_RADIUS_SOURCE_PIXELS = 34


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def best_available_terrain(manifest: dict[str, Any]) -> dict[str, Any]:
    for item in manifest["slices"]:
        for terrain in item.get("terrains", []):
            if terrain.get("sourceId") == "best_available_gate_shelf_fusion":
                return terrain
    raise SystemExit("best_available_gate_shelf_fusion was not found in paleo_manifest.json")


def decode_elevation_png(path: Path, height_range: list[float]) -> np.ndarray:
    image = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint32)
    encoded = (image[:, :, 0] << 16) + (image[:, :, 1] << 8) + image[:, :, 2]
    low, high = float(height_range[0]), float(height_range[1])
    return (encoded.astype(np.float32) / 16_777_215.0) * (high - low) + low


def source_to_elevation_xy(source_x: int, source_y: int, source_shape: tuple[int, int], elevation_shape: tuple[int, int]) -> tuple[int, int]:
    source_height, source_width = source_shape
    elevation_height, elevation_width = elevation_shape
    elevation_x = round((source_x / max(source_width - 1, 1)) * (elevation_width - 1))
    elevation_y = round((source_y / max(source_height - 1, 1)) * (elevation_height - 1))
    return elevation_x, elevation_y


def height_at_source_pixel(elevation: np.ndarray, source_x: int, source_y: int, source_shape: tuple[int, int]) -> float:
    elevation_x, elevation_y = source_to_elevation_xy(source_x, source_y, source_shape, elevation.shape)
    return float(elevation[elevation_y, elevation_x])


def percentile(values: np.ndarray, q: float) -> float:
    return round(float(np.percentile(values, q)), 3)


def severity_label(level: str) -> str:
    if level == "severe":
        return "severe local height step"
    if level == "suspicious":
        return "suspicious local height step"
    if level == "calm":
        return "locally calm"
    return "no local seam edges found"


def severity_level(abs_steps: np.ndarray) -> str:
    if abs_steps.size == 0:
        return "no_edges"
    median_abs = float(np.median(abs_steps))
    p95_abs = float(np.percentile(abs_steps, 95))
    if median_abs >= 10 or p95_abs >= 35:
        return "severe"
    if median_abs >= 4 or p95_abs >= 15:
        return "suspicious"
    return "calm"


def plain_read(level: str, median_abs: float | None, p95_abs: float | None) -> str:
    if level == "severe":
        return f"Height changes sharply right at this source join: median step {median_abs} m, 95% step {p95_abs} m."
    if level == "suspicious":
        return f"The join has a noticeable local height step: median {median_abs} m, 95% {p95_abs} m."
    if level == "calm":
        return f"The final fused height image is locally calm across this join: median step {median_abs} m."
    return "The local window did not contain enough matching source-edge pixels to measure a step."


def measure_target(
    target: dict[str, Any],
    categories: list[str],
    source_codes: np.ndarray,
    elevation: np.ndarray,
) -> dict[str, Any]:
    category_a, category_b = categories
    code_a = seams.CATEGORY_CODES[category_a]
    code_b = seams.CATEGORY_CODES[category_b]
    source_height, source_width = source_codes.shape
    center_x = int(round(float(target["pixel"][0])))
    center_y = int(round(float(target["pixel"][1])))
    radius = WINDOW_RADIUS_SOURCE_PIXELS
    x0 = max(0, center_x - radius)
    x1 = min(source_width - 1, center_x + radius)
    y0 = max(0, center_y - radius)
    y1 = min(source_height - 1, center_y + radius)

    signed_steps: list[float] = []
    local_heights: list[float] = []

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            code = int(source_codes[y, x])
            if code in (code_a, code_b):
                local_heights.append(height_at_source_pixel(elevation, x, y, source_codes.shape))

            if x < x1:
                signed = signed_step_for_pair(source_codes, elevation, x, y, x + 1, y, code_a, code_b)
                if signed is not None:
                    signed_steps.append(signed)
            if y < y1:
                signed = signed_step_for_pair(source_codes, elevation, x, y, x, y + 1, code_a, code_b)
                if signed is not None:
                    signed_steps.append(signed)

    signed_array = np.asarray(signed_steps, dtype=np.float32)
    abs_array = np.abs(signed_array)
    local_height_array = np.asarray(local_heights, dtype=np.float32)
    level = severity_level(abs_array)
    median_abs = percentile(abs_array, 50) if abs_array.size else None
    p95_abs = percentile(abs_array, 95) if abs_array.size else None

    return {
        "level": level,
        "label": severity_label(level),
        "edgePairCount": int(abs_array.size),
        "windowRadiusSourcePixels": WINDOW_RADIUS_SOURCE_PIXELS,
        "medianSignedStepMeters": percentile(signed_array, 50) if signed_array.size else None,
        "medianAbsStepMeters": median_abs,
        "p95AbsStepMeters": p95_abs,
        "maxAbsStepMeters": round(float(abs_array.max()), 3) if abs_array.size else None,
        "localHeightRangeMeters": round(float(local_height_array.max() - local_height_array.min()), 3) if local_height_array.size else None,
        "plainEnglishRead": plain_read(level, median_abs, p95_abs),
    }


def signed_step_for_pair(
    source_codes: np.ndarray,
    elevation: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    code_a: int,
    code_b: int,
) -> float | None:
    left_code = int(source_codes[y0, x0])
    right_code = int(source_codes[y1, x1])
    if {left_code, right_code} != {code_a, code_b}:
        return None

    left_height = height_at_source_pixel(elevation, x0, y0, source_codes.shape)
    right_height = height_at_source_pixel(elevation, x1, y1, source_codes.shape)
    if left_code == code_a:
        return right_height - left_height
    return left_height - right_height


def enriched_report() -> dict[str, Any]:
    report = read_json(SEAM_JSON)
    manifest = read_json(MANIFEST_JSON)
    terrain = best_available_terrain(manifest)
    source_codes = seams.category_codes_from_texture(SOURCE_TEXTURE)
    elevation = decode_elevation_png(ELEVATION_PNG, terrain["heightRangeMeters"])

    counts: Counter[str] = Counter()
    top_targets: list[dict[str, Any]] = []
    for transition in report["topTransitions"]:
        categories = transition["categories"]
        for target in transition["targets"]:
            local_height = measure_target(target, categories, source_codes, elevation)
            target["localHeight"] = local_height
            counts[local_height["level"]] += 1
            top_targets.append({
                "categories": categories,
                "lon": target["lon"],
                "lat": target["lat"],
                "edgePixelsInCluster": target["edgePixelsInCluster"],
                "localHeight": local_height,
                "verticalOverlap": transition.get("verticalOverlap"),
                "recommendedView": transition["recommendedView"],
            })

    top_targets.sort(
        key=lambda item: (
            {"severe": 3, "suspicious": 2, "calm": 1, "no_edges": 0}.get(item["localHeight"]["level"], 0),
            item["localHeight"]["p95AbsStepMeters"] or 0,
            item["edgePixelsInCluster"],
        ),
        reverse=True,
    )

    report["localHeightAudit"] = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "elevation": str(ELEVATION_PNG.relative_to(ROOT)),
        "sourceQuality": str(SOURCE_TEXTURE.relative_to(ROOT)),
        "windowRadiusSourcePixels": WINDOW_RADIUS_SOURCE_PIXELS,
        "targetCountByLevel": dict(sorted(counts.items())),
        "plainEnglishPurpose": "Measure the final fused elevation image right across each seam target. This catches local height steps that may be visible as ledges.",
        "topTargetsByLocalHeightStep": top_targets[:24],
    }
    return report


def write_markdown(report: dict[str, Any]) -> None:
    audit = report["localHeightAudit"]
    lines = [
        "# Local Seam Height Audit",
        "",
        "This file is generated by `python3 scripts/audit_local_seam_heights.py`.",
        "",
        "It samples the final fused elevation PNG around each source seam target. In plain English: it checks whether the finished height image jumps right where the source category changes.",
        "",
        "## Summary",
        "",
        f"- Elevation image: `{audit['elevation']}`",
        f"- Source-quality image: `{audit['sourceQuality']}`",
        f"- Window radius: {audit['windowRadiusSourcePixels']} source pixels",
        "",
        "| Local result | Target count |",
        "|---|---:|",
    ]
    for level in ("severe", "suspicious", "calm", "no_edges"):
        lines.append(f"| {severity_label(level)} | {audit['targetCountByLevel'].get(level, 0)} |")

    lines.extend([
        "",
        "## Worst Local Targets",
        "",
        "| Categories | Lon/lat | Local result | Median step | 95% step | Edge pairs | Existing overlap warning | Suggested view |",
        "|---|---|---|---:|---:|---:|---|---|",
    ])
    for item in audit["topTargetsByLocalHeightStep"][:18]:
        local = item["localHeight"]
        overlap = item.get("verticalOverlap") or {}
        lines.append(
            f"| {' / '.join(item['categories'])} | `{item['lon']}, {item['lat']}` | "
            f"{local['label']} | {local['medianAbsStepMeters']} m | {local['p95AbsStepMeters']} m | "
            f"{local['edgePairCount']} | {overlap.get('label', 'n/a')} | {item['recommendedView']} |"
        )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    report = enriched_report()
    SEAM_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report)
    print(f"Wrote {SEAM_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
