#!/usr/bin/env python3
"""Re-derive the cross-check tables behind the promoted raw-sonar patches.

Both B00012 raw-sonar patches were promoted above NOAA CUDEM on the strength of
a cross-check table sampled by hand. Those tables were recorded before commit
e648d085 fixed a compound-CRS warp bug that had shifted the prepared CUDEM and
USGS LiDAR rasters by about 33 m (see docs/cudem-lidar-vertical-reference-audit.md).
The hand-written tables therefore outlived the rasters they were computed from,
and nothing in the repository noticed.

This script re-samples every source at each promoted cell from the rasters that
are on disk right now, diffs against the values the candidate docs recorded, and
stamps each sampled window with a content hash. Re-running it after any pipeline
change shows immediately whether a promotion rationale still holds.

    python3 scripts/audit_raw_sonar_promotions.py

Writes docs/raw-sonar-promotion-audit.md and
public/data/paleo-coastlines/raw_sonar_promotion_audit.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work"
CANDIDATE_DIR = ROOT / "public" / "data" / "paleo-coastlines" / "raw-sonar-candidates"
PUBLIC_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "raw_sonar_promotion_audit.json"
DOC_PATH = ROOT / "docs" / "raw-sonar-promotion-audit.md"

# Values below this are fill rims, not measurements. The fusion pipeline already
# masks near-FLT_MAX fill; mirror that here so a fill pixel never reads as depth.
ABSURD_MAGNITUDE = 1e30

# Shared surfaces sampled at every cell, in the order the candidate docs used.
SHARED_SOURCES: list[tuple[str, Path]] = [
    ("Current best available (full extent)", WORK_DIR / "best_available_full_extent_terrain_wgs84.tif"),
    ("Current best available (gate shelf)", WORK_DIR / "best_available_gate_shelf_terrain_wgs84.tif"),
    ("NOAA CUDEM 1/9 arc-second", WORK_DIR / "noaa_cudem_1_9as_terrain_wgs84.tif"),
    ("NOAA CRM Vol. 7", WORK_DIR / "noaa_crm_vol7_sf_farallones_terrain_wgs84.tif"),
    ("USGS CoNED 2 m broad", WORK_DIR / "usgs_coned_sf_2m_terrain_wgs84.tif"),
    ("USGS CoNED 2 m Farallon shelf", WORK_DIR / "usgs_coned_sf_2m_farallon_shelf_terrain_wgs84.tif"),
    ("NOAA/NCEI EX0907 50 m", WORK_DIR / "noaa_ncei_ex0907_sanctuary_50m_multibeam_terrain_wgs84.tif"),
    ("NOAA NOS W00478 VR BAG", WORK_DIR / "noaa_nos_w00478_vr_bag_terrain_wgs84.tif"),
]

# Values the hand-written candidate docs recorded at each cell centre, with the
# doc line they came from. Sampled before the CUDEM warp fix.
RECORDED: dict[str, dict[str, Any]] = {
    "b00012-qg-03-06": {
        "doc": "docs/b00012-qg-03-06-candidate.md",
        "lines": "55-58",
        "values": {
            "Current best available (full extent)": -197.6373,
            "NOAA CUDEM 1/9 arc-second": -197.7472,
            "NOAA CRM Vol. 7": -163.1757,
            "B00012 candidate": -166.0,
            "NA085 candidate": None,
            "NOAA NOS W00478 VR BAG": None,
            "NOAA/NCEI EX0907 50 m": None,
        },
    },
    "b00012-qg-05-12": {
        "doc": "docs/b00012-qg-05-12-candidate.md",
        "lines": "33-37",
        "values": {
            "B00012 candidate": -162.0,
            "NOAA CRM Vol. 7": -155.90,
            "NOAA CUDEM 1/9 arc-second": -193.14,
        },
    },
}


def window_sample(path: Path, west: float, south: float, east: float, north: float) -> dict[str, Any]:
    """Sample a raster over a lon/lat box: centre value plus valid-pixel stats.

    Returns a `covered: False` record when the raster does not reach the box or
    holds only nodata there, which is what "no-data" meant in the hand tables.
    """
    if not path.exists():
        return {"covered": False, "reason": "raster missing from disk"}

    dataset = gdal.Open(str(path))
    transform = dataset.GetGeoTransform()
    if transform[2] or transform[4]:
        return {"covered": False, "reason": "rotated geotransform is unsupported"}

    origin_x, pixel_w, _, origin_y, _, pixel_h = transform
    # pixel_h is negative for north-up rasters, so north maps to the low row.
    col_lo = int((west - origin_x) / pixel_w)
    col_hi = int((east - origin_x) / pixel_w)
    row_lo = int((north - origin_y) / pixel_h)
    row_hi = int((south - origin_y) / pixel_h)
    col_lo, col_hi = sorted((col_lo, col_hi))
    row_lo, row_hi = sorted((row_lo, row_hi))

    col_start = max(col_lo, 0)
    row_start = max(row_lo, 0)
    col_end = min(col_hi + 1, dataset.RasterXSize)
    row_end = min(row_hi + 1, dataset.RasterYSize)
    if col_end <= col_start or row_end <= row_start:
        return {"covered": False, "reason": "cell falls outside the raster extent"}

    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray(col_start, row_start, col_end - col_start, row_end - row_start)
    values = np.asarray(values, dtype="float64")

    valid = np.isfinite(values) & (np.abs(values) < ABSURD_MAGNITUDE)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        valid &= values != nodata
    # -9999 is the fill the raw-sonar gridding writes, and some candidate COGs
    # carry it without declaring it as nodata.
    valid &= values != -9999.0

    if not valid.any():
        return {"covered": False, "reason": "only nodata inside the cell"}

    centre_col = int(((west + east) / 2 - origin_x) / pixel_w)
    centre_row = int(((north + south) / 2 - origin_y) / pixel_h)
    centre: float | None = None
    if col_start <= centre_col < col_end and row_start <= centre_row < row_end:
        raw = float(values[centre_row - row_start, centre_col - col_start])
        if np.isfinite(raw) and abs(raw) < ABSURD_MAGNITUDE and raw != -9999.0 and raw != nodata:
            centre = round(raw, 4)

    kept = values[valid]
    return {
        "covered": True,
        "centreMeters": centre,
        "medianMeters": round(float(np.median(kept)), 4),
        "minMeters": round(float(kept.min()), 4),
        "maxMeters": round(float(kept.max()), 4),
        "validPixels": int(kept.size),
        "totalPixels": int(values.size),
        "validPercent": round(100.0 * kept.size / values.size, 2),
        # Hashing the sampled window, not the whole file, keeps this cheap on
        # multi-gigabyte rasters while still detecting any change at this cell.
        "windowSha256": hashlib.sha256(values.tobytes()).hexdigest()[:16],
        "sourceBytes": path.stat().st_size,
        "sourceModified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


def cell_sources(cell_id: str) -> list[tuple[str, Path]]:
    """Shared surfaces plus every raw-sonar candidate grid covering this cell."""
    sources = list(SHARED_SOURCES)
    cell_suffix = cell_id.split("-", 1)[1]
    for candidate in sorted(CANDIDATE_DIR.glob(f"*-{cell_suffix}")):
        survey = candidate.name.split("-", 1)[0].upper()
        cog = candidate / f"{candidate.name}.masked-512.cog.tif"
        if cog.exists():
            sources.append((f"{survey} candidate", cog))
    return sources


def audit_cell(cell_dir: Path) -> dict[str, Any]:
    summary = json.loads((cell_dir / f"{cell_dir.name}.candidate-summary.json").read_text())
    west, south, east, north = summary["cellBounds"]
    recorded = RECORDED.get(cell_dir.name, {})
    recorded_values: dict[str, Any] = recorded.get("values", {})

    samples = []
    for label, path in cell_sources(cell_dir.name):
        sample = window_sample(path, west, south, east, north)
        sample["source"] = label
        sample["path"] = str(path.relative_to(ROOT))
        if label in recorded_values:
            was = recorded_values[label]
            now = sample.get("centreMeters") if sample["covered"] else None
            sample["recordedMeters"] = was
            sample["driftMeters"] = None if was is None or now is None else round(now - was, 4)
        samples.append(sample)

    return {
        "cell": cell_dir.name,
        "bounds": [west, south, east, north],
        "centre": [round((west + east) / 2, 7), round((south + north) / 2, 7)],
        "recordedIn": recorded.get("doc"),
        "recordedLines": recorded.get("lines"),
        "samples": samples,
    }


def format_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Raw Sonar Promotion Audit",
        "",
        "This file is generated by `python3 scripts/audit_raw_sonar_promotions.py`.",
        "",
        "It re-samples every source at the cells where a B00012 raw-sonar patch was",
        "promoted into `best_available_gate_shelf_fusion`, and compares the result",
        "against the values the hand-written candidate docs recorded.",
        "",
        "Why this exists: the candidate cross-check tables were sampled before commit",
        "`e648d085` fixed a compound-CRS warp bug that had shifted the prepared CUDEM",
        "and USGS LiDAR rasters by about 33 m. A promotion rationale must not outlive",
        "the raster it was computed from, so this audit regenerates instead of aging.",
        "",
        f"Generated at: `{audit['generatedAt']}`",
        "",
    ]

    for cell in audit["cells"]:
        west, south, east, north = cell["bounds"]
        lines += [
            f"## {cell['cell']}",
            "",
            f"Cell centre `{cell['centre'][0]}, {cell['centre'][1]}`, "
            f"bounds `[{west}, {south}, {east}, {north}]`.",
            "",
        ]
        if cell["recordedIn"]:
            lines += [
                f"Recorded values come from `{cell['recordedIn']}:{cell['recordedLines']}`.",
                "",
            ]
        lines += [
            "| Source | Recorded | Now (centre) | Drift | Cell median | Valid px | Window hash |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for sample in cell["samples"]:
            recorded = sample.get("recordedMeters")
            recorded_text = "no-data" if "recordedMeters" in sample and recorded is None else (
                f"`{recorded}`" if recorded is not None else "not recorded"
            )
            if not sample["covered"]:
                lines.append(
                    f"| {sample['source']} | {recorded_text} | no-data | | | 0 | "
                    f"{sample['reason']} |"
                )
                continue
            drift = sample.get("driftMeters")
            drift_text = "" if drift is None else f"`{drift:+.2f}`"
            centre = sample["centreMeters"]
            centre_text = "no-data" if centre is None else f"`{centre}`"
            lines.append(
                f"| {sample['source']} | {recorded_text} | {centre_text} | {drift_text} | "
                f"`{sample['medianMeters']}` | {sample['validPixels']} | `{sample['windowSha256']}` |"
            )
        lines.append("")

    lines += [
        "## How To Read This",
        "",
        "- `Recorded` is what the hand-written candidate doc claimed at this cell.",
        "- `Drift` is the current centre value minus the recorded one. A large drift",
        "  means the promotion rationale was computed against a raster that has since",
        "  changed, and the ranking decision needs re-deriving.",
        "- `Window hash` covers the raw pixel values inside the cell only, so it is",
        "  cheap on multi-gigabyte rasters and still changes whenever this cell does.",
        "- This audit reports measurements. It does not change any source ranking.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", action="append", help="limit to one cell id, repeatable")
    args = parser.parse_args()

    cell_dirs = sorted(d for d in CANDIDATE_DIR.iterdir() if d.is_dir())
    if args.cell:
        wanted = set(args.cell)
        cell_dirs = [d for d in cell_dirs if d.name in wanted]
    if not cell_dirs:
        raise SystemExit("No candidate cells found.")

    audit = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cells": [audit_cell(cell_dir) for cell_dir in cell_dirs],
    }

    PUBLIC_JSON.write_text(json.dumps(audit, separators=(",", ":")) + "\n")
    DOC_PATH.write_text(format_markdown(audit))
    print(f"Wrote {PUBLIC_JSON.relative_to(ROOT)}")
    print(f"Wrote {DOC_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
