#!/usr/bin/env python3
"""Measure height differences where prepared terrain sources overlap."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_paleo_coastlines as paleo  # noqa: E402


OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "vertical_overlap_audit.json"
OUT_MD = ROOT / "docs" / "vertical-overlap-audit.md"


def run(args: list[str]) -> None:
    subprocess.run(args, check=True)


def source_rank(source_id: str) -> tuple[int, int, str]:
    for priority, resolution_rank, candidate_id, _path in paleo.best_available_fusion_ranked_records():
        if candidate_id == source_id:
            return priority, resolution_rank, source_id
    return 0, 0, source_id


def warp_source(source_id: str, source_path: Path, out_path: Path, width: int) -> None:
    bounds = paleo.BEST_AVAILABLE_BOUNDS
    run([
        "gdalwarp",
        "-q",
        "-overwrite",
        "-t_srs",
        "EPSG:4326",
        "-te",
        str(bounds["west"]),
        str(bounds["south"]),
        str(bounds["east"]),
        str(bounds["north"]),
        "-ts",
        str(width),
        "0",
        "-r",
        "bilinear",
        "-ot",
        "Float32",
        "-srcnodata",
        "-9999",
        "-dstnodata",
        "-9999",
        str(source_path),
        str(out_path),
    ])


def load_array(path: Path) -> np.ndarray:
    image = Image.open(path)
    values = np.asarray(image, dtype=np.float32)
    if values.ndim > 2:
        values = values[:, :, 0]
    return values


def is_valid(values: np.ndarray) -> np.ndarray:
    return np.isfinite(values) & (values > -9000) & (values < 1_000_000)


def percentile(values: np.ndarray, q: float) -> float:
    return round(float(np.percentile(values, q)), 3)


def pair_stats(
    low_id: str,
    low_values: np.ndarray,
    high_id: str,
    high_values: np.ndarray,
    pixel_area_sq_km: float,
    min_overlap_pixels: int,
) -> dict[str, Any] | None:
    overlap = is_valid(low_values) & is_valid(high_values)
    count = int(overlap.sum())
    if count < min_overlap_pixels:
        return None

    delta = high_values[overlap] - low_values[overlap]
    abs_delta = np.abs(delta)
    low_priority, low_resolution_rank, _ = source_rank(low_id)
    high_priority, high_resolution_rank, _ = source_rank(high_id)
    return {
        "lowerSourceId": low_id,
        "lowerSourceLabel": paleo.source_label(low_id),
        "lowerCategory": paleo.source_quality_category(low_id),
        "lowerPriority": low_priority,
        "lowerResolutionRank": low_resolution_rank,
        "higherSourceId": high_id,
        "higherSourceLabel": paleo.source_label(high_id),
        "higherCategory": paleo.source_quality_category(high_id),
        "higherPriority": high_priority,
        "higherResolutionRank": high_resolution_rank,
        "overlapPixels": count,
        "approxOverlapSqKm": round(count * pixel_area_sq_km, 2),
        "medianMeters": percentile(delta, 50),
        "meanMeters": round(float(delta.mean()), 3),
        "meanAbsMeters": round(float(abs_delta.mean()), 3),
        "p10Meters": percentile(delta, 10),
        "p90Meters": percentile(delta, 90),
        "p95AbsMeters": percentile(abs_delta, 95),
        "plainEnglishRead": describe_pair(delta, abs_delta),
    }


def describe_pair(delta: np.ndarray, abs_delta: np.ndarray) -> str:
    median = float(np.median(delta))
    p95_abs = float(np.percentile(abs_delta, 95))
    if p95_abs < 1:
        return "Very close match over most overlap pixels."
    if abs(median) < 1 and p95_abs < 5:
        return "Mostly aligned, with local texture differences rather than a clear up/down shift."
    if abs(median) >= 5:
        direction = "higher" if median > 0 else "lower"
        return f"Possible vertical offset: the later source is typically {direction} by about {abs(median):.1f} m."
    return "Mixed difference pattern; inspect the seam before applying any correction."


def build_report(width: int, max_sources: int, min_overlap_pixels: int) -> dict[str, Any]:
    ranked_records = paleo.best_available_fusion_ranked_records()
    records = [
        {
            "priority": priority,
            "resolutionRank": resolution_rank,
            "sourceId": source_id,
            "path": path,
            "label": paleo.source_label(source_id),
            "category": paleo.source_quality_category(source_id),
        }
        for priority, resolution_rank, source_id, path in ranked_records
        if path.exists()
    ]

    winners_path = paleo.BEST_AVAILABLE_TERRAIN_SOURCE_PROVENANCE_JSON
    if winners_path.exists():
        winners = json.loads(winners_path.read_text()).get("sourceWinners", [])
        winner_ids = {item["sourceId"] for item in winners[:max_sources]}
        records = [record for record in records if record["sourceId"] in winner_ids]

    records.sort(key=lambda item: (item["priority"], item["resolutionRank"], item["sourceId"]))

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        arrays: dict[str, np.ndarray] = {}
        shape: tuple[int, int] | None = None
        for record in records:
            out_path = temp_root / f"{record['sourceId']}.tif"
            warp_source(str(record["sourceId"]), Path(record["path"]), out_path, width)
            values = load_array(out_path)
            arrays[str(record["sourceId"])] = values
            if shape is None:
                shape = values.shape

        if shape is None:
            raise SystemExit("No source rasters were available for overlap audit.")

        bounds = paleo.BEST_AVAILABLE_BOUNDS
        approx_area_sq_km = (
            (float(bounds["east"]) - float(bounds["west"])) * 111.32
            * (float(bounds["north"]) - float(bounds["south"])) * 111.32
        )
        pixel_area_sq_km = approx_area_sq_km / float(shape[0] * shape[1])

        pairs: list[dict[str, Any]] = []
        for low_index, low_record in enumerate(records):
            for high_record in records[low_index + 1:]:
                stats = pair_stats(
                    str(low_record["sourceId"]),
                    arrays[str(low_record["sourceId"])],
                    str(high_record["sourceId"]),
                    arrays[str(high_record["sourceId"])],
                    pixel_area_sq_km,
                    min_overlap_pixels,
                )
                if stats:
                    pairs.append(stats)

    pairs.sort(key=lambda item: (-item["p95AbsMeters"], -item["approxOverlapSqKm"], item["higherSourceId"]))
    high_confidence_offsets = [
        pair for pair in pairs
        if abs(float(pair["medianMeters"])) >= 5 and float(pair["approxOverlapSqKm"]) >= 5
    ]
    mixed_seams = [
        pair for pair in pairs
        if abs(float(pair["medianMeters"])) < 5 and float(pair["p95AbsMeters"]) >= 10 and float(pair["approxOverlapSqKm"]) >= 5
    ]

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bounds": paleo.BEST_AVAILABLE_BOUNDS,
        "sampleWidth": width,
        "sourceCount": len(records),
        "pairCount": len(pairs),
        "minimumOverlapPixels": min_overlap_pixels,
        "sources": [
            {
                key: value
                for key, value in record.items()
                if key != "path"
            } | {"path": str(Path(record["path"]).relative_to(ROOT))}
            for record in records
        ],
        "topPairsByP95AbsMeters": pairs[:30],
        "highConfidenceOffsets": high_confidence_offsets[:20],
        "mixedSeams": mixed_seams[:20],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Vertical Overlap Audit",
        "",
        "This file is generated by `python3 scripts/audit_vertical_overlaps.py`.",
        "",
        "It compares prepared terrain sources where they overlap. In plain English: if two source grids cover the same place, this checks whether they put the seafloor or land at roughly the same height.",
        "",
        "A large repeated difference can mean the sources use different height references, or that one source has local detail the other cannot see. This report is a warning system; it does not automatically prove a correction is safe.",
        "",
        "## Summary",
        "",
        f"- Sources sampled: {report['sourceCount']}",
        f"- Overlapping source pairs measured: {report['pairCount']}",
        f"- Sample grid width: {report['sampleWidth']} pixels",
        f"- Minimum overlap used: {report['minimumOverlapPixels']} pixels",
        f"- High-confidence possible offsets: {len(report['highConfidenceOffsets'])}",
        f"- Mixed seams needing visual inspection: {len(report['mixedSeams'])}",
        "",
    ]

    if report["highConfidenceOffsets"]:
        lines.extend([
            "## Possible Vertical Offsets",
            "",
            "| Later source | Earlier source | Median difference | 95% absolute difference | Overlap | Plain-English read |",
            "|---|---|---:|---:|---:|---|",
        ])
        for pair in report["highConfidenceOffsets"][:12]:
            lines.append(
                f"| {pair['higherSourceLabel']} | {pair['lowerSourceLabel']} | "
                f"{pair['medianMeters']} m | {pair['p95AbsMeters']} m | "
                f"{pair['approxOverlapSqKm']} sq km | {pair['plainEnglishRead']} |"
            )
        lines.append("")

    if report["mixedSeams"]:
        lines.extend([
            "## Mixed Seams To Inspect",
            "",
            "| Later source | Earlier source | Median difference | 95% absolute difference | Overlap | Plain-English read |",
            "|---|---|---:|---:|---:|---|",
        ])
        for pair in report["mixedSeams"][:12]:
            lines.append(
                f"| {pair['higherSourceLabel']} | {pair['lowerSourceLabel']} | "
                f"{pair['medianMeters']} m | {pair['p95AbsMeters']} m | "
                f"{pair['approxOverlapSqKm']} sq km | {pair['plainEnglishRead']} |"
            )
        lines.append("")

    lines.extend([
        "## Largest Differences",
        "",
        "| Later source | Earlier source | Median difference | 95% absolute difference | Overlap | Plain-English read |",
        "|---|---|---:|---:|---:|---|",
    ])
    for pair in report["topPairsByP95AbsMeters"][:20]:
        lines.append(
            f"| {pair['higherSourceLabel']} | {pair['lowerSourceLabel']} | "
            f"{pair['medianMeters']} m | {pair['p95AbsMeters']} m | "
            f"{pair['approxOverlapSqKm']} sq km | {pair['plainEnglishRead']} |"
        )
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--max-sources", type=int, default=30)
    parser.add_argument("--min-overlap-pixels", type=int, default=250)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        width=args.width,
        max_sources=args.max_sources,
        min_overlap_pixels=args.min_overlap_pixels,
    )
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
