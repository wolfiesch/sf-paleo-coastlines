#!/usr/bin/env python3
"""Prototype a thin edge blend around locally severe source seams."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_local_seam_heights as local_audit  # noqa: E402
import audit_source_seams as seams  # noqa: E402


DEFAULT_OUT_DIR = ROOT / "output/seam-blend-experiment"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--levels", default="severe", help="Comma-separated local seam levels to blend.")
    parser.add_argument("--edge-window-source-pixels", type=int, default=54)
    parser.add_argument("--blend-radius-source-pixels", type=float, default=8.0)
    parser.add_argument("--smooth-sigma-elevation-pixels", type=float, default=5.0)
    return parser.parse_args()


def encode_elevation_png(heights: np.ndarray, height_range: list[float], out_path: Path) -> None:
    low, high = float(height_range[0]), float(height_range[1])
    normalized = np.clip((heights - low) / (high - low), 0.0, 1.0)
    encoded = np.rint(normalized * 16_777_215).astype(np.uint32)
    pixels = np.zeros((heights.shape[0], heights.shape[1], 3), dtype=np.uint8)
    pixels[:, :, 0] = ((encoded >> 16) & 255).astype(np.uint8)
    pixels[:, :, 1] = ((encoded >> 8) & 255).astype(np.uint8)
    pixels[:, :, 2] = (encoded & 255).astype(np.uint8)
    Image.fromarray(pixels, "RGB").save(out_path)


def source_to_elevation_mask(mask: np.ndarray, elevation_shape: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(np.rint(mask * 255).astype(np.uint8), "L")
    resized = image.resize((elevation_shape[1], elevation_shape[0]), Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32) / 255.0


def edge_mask_for_targets(report: dict[str, Any], source_codes: np.ndarray, levels: set[str], window_radius: int) -> tuple[np.ndarray, list[dict[str, Any]]]:
    mask = np.zeros(source_codes.shape, dtype=bool)
    selected: list[dict[str, Any]] = []
    height, width = source_codes.shape

    for transition in report["topTransitions"]:
        code_a = seams.CATEGORY_CODES[transition["categories"][0]]
        code_b = seams.CATEGORY_CODES[transition["categories"][1]]
        for target in transition["targets"]:
            local_height = target.get("localHeight")
            if local_height is None or local_height.get("level") not in levels:
                continue

            selected.append({
                "categories": transition["categories"],
                "target": target,
                "recommendedView": transition["recommendedView"],
            })
            center_x = int(round(float(target["pixel"][0])))
            center_y = int(round(float(target["pixel"][1])))
            x0 = max(0, center_x - window_radius)
            x1 = min(width - 1, center_x + window_radius)
            y0 = max(0, center_y - window_radius)
            y1 = min(height - 1, center_y + window_radius)
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
            mask[y0:y1 + 1, x0:x1 + 1] |= local_mask

    return mask, selected


def severity_rank(level: str) -> int:
    return {
        "severe": 3,
        "suspicious": 2,
        "calm": 1,
        "no_edges": 0,
    }.get(level, 0)


def compare_selected_targets(selected: list[dict[str, Any]], source_codes: np.ndarray, before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    before_counts: Counter[str] = Counter()
    after_counts: Counter[str] = Counter()

    for item in selected:
        categories = item["categories"]
        target = item["target"]
        before_local = local_audit.measure_target(target, categories, source_codes, before)
        after_local = local_audit.measure_target(target, categories, source_codes, after)
        before_counts[before_local["level"]] += 1
        after_counts[after_local["level"]] += 1
        before_p95 = before_local["p95AbsStepMeters"] or 0
        after_p95 = after_local["p95AbsStepMeters"] or 0
        before_median = before_local["medianAbsStepMeters"] or 0
        after_median = after_local["medianAbsStepMeters"] or 0
        rows.append({
            "categories": categories,
            "lon": target["lon"],
            "lat": target["lat"],
            "recommendedView": item["recommendedView"],
            "before": before_local,
            "after": after_local,
            "deltaP95AbsMeters": round(after_p95 - before_p95, 3),
            "deltaMedianAbsMeters": round(after_median - before_median, 3),
        })

    rows.sort(key=lambda row: (severity_rank(row["before"]["level"]), row["before"]["p95AbsStepMeters"] or 0), reverse=True)
    return {
        "beforeCounts": dict(sorted(before_counts.items())),
        "afterCounts": dict(sorted(after_counts.items())),
        "targets": rows,
    }


def write_markdown(report: dict[str, Any], out_path: Path) -> None:
    lines = [
        "# Seam Edge Blend Prototype",
        "",
        "This file is generated by `python3 scripts/prototype_seam_edge_blend.py`.",
        "",
        "It does not overwrite the production terrain. It creates a candidate blended elevation PNG and compares the same local seam-height audit before and after the blend.",
        "",
        "## Settings",
        "",
        f"- Levels blended: {', '.join(report['levels'])}",
        f"- Source edge window: {report['edgeWindowSourcePixels']} px",
        f"- Blend radius: {report['blendRadiusSourcePixels']} source px",
        f"- Smooth sigma: {report['smoothSigmaElevationPixels']} elevation px",
        f"- Candidate elevation PNG: `{report['candidateElevationPng']}`",
        f"- Blend mask PNG: `{report['blendMaskPng']}`",
        "",
        "## Result Counts",
        "",
        "| Level | Before | After |",
        "|---|---:|---:|",
    ]
    levels = sorted(set(report["comparison"]["beforeCounts"]) | set(report["comparison"]["afterCounts"]))
    for level in levels:
        lines.append(
            f"| {level} | {report['comparison']['beforeCounts'].get(level, 0)} | "
            f"{report['comparison']['afterCounts'].get(level, 0)} |"
        )

    lines.extend([
        "",
        "## Target Changes",
        "",
        "| Categories | Lon/lat | Before | After | P95 change | Median change |",
        "|---|---|---|---|---:|---:|",
    ])
    for row in report["comparison"]["targets"][:24]:
        lines.append(
            f"| {' / '.join(row['categories'])} | `{row['lon']}, {row['lat']}` | "
            f"{row['before']['label']} ({row['before']['p95AbsStepMeters']} m p95) | "
            f"{row['after']['label']} ({row['after']['p95AbsStepMeters']} m p95) | "
            f"{row['deltaP95AbsMeters']} m | {row['deltaMedianAbsMeters']} m |"
        )

    out_path.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    args = parse_args()
    args.out_dir = args.out_dir.resolve()
    levels = {level.strip() for level in args.levels.split(",") if level.strip()}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    seam_report = local_audit.read_json(local_audit.SEAM_JSON)
    manifest = local_audit.read_json(local_audit.MANIFEST_JSON)
    terrain = local_audit.best_available_terrain(manifest)
    source_codes = seams.category_codes_from_texture(local_audit.SOURCE_TEXTURE)
    heights = local_audit.decode_elevation_png(local_audit.ELEVATION_PNG, terrain["heightRangeMeters"])

    source_edge_mask, selected = edge_mask_for_targets(
        seam_report,
        source_codes,
        levels,
        args.edge_window_source_pixels,
    )
    if not selected:
        raise SystemExit("No seam targets matched the requested levels.")

    distance = distance_transform_edt(~source_edge_mask)
    source_weight = np.clip(1.0 - (distance / max(args.blend_radius_source_pixels, 0.1)), 0.0, 1.0)
    elevation_weight = source_to_elevation_mask(source_weight, heights.shape)
    smoothed = gaussian_filter(heights, sigma=args.smooth_sigma_elevation_pixels)
    blended = (heights * (1.0 - elevation_weight)) + (smoothed * elevation_weight)

    candidate_png = args.out_dir / "candidate_blended_elevation.png"
    mask_png = args.out_dir / "candidate_blend_mask.png"
    report_json = args.out_dir / "seam_edge_blend_report.json"
    report_md = args.out_dir / "seam_edge_blend_report.md"

    encode_elevation_png(blended, terrain["heightRangeMeters"], candidate_png)
    Image.fromarray(np.rint(elevation_weight * 255).astype(np.uint8), "L").save(mask_png)

    report = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "levels": sorted(levels),
        "selectedTargetCount": len(selected),
        "edgeWindowSourcePixels": args.edge_window_source_pixels,
        "blendRadiusSourcePixels": args.blend_radius_source_pixels,
        "smoothSigmaElevationPixels": args.smooth_sigma_elevation_pixels,
        "candidateElevationPng": str(candidate_png.relative_to(ROOT)),
        "blendMaskPng": str(mask_png.relative_to(ROOT)),
        "comparison": compare_selected_targets(selected, source_codes, heights, blended),
    }
    report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report, report_md)
    print(f"Wrote {candidate_png.relative_to(ROOT)}")
    print(f"Wrote {mask_png.relative_to(ROOT)}")
    print(f"Wrote {report_json.relative_to(ROOT)}")
    print(f"Wrote {report_md.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
