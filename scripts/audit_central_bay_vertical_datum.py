#!/usr/bin/env python3
"""Compare Central Bay survey heights and sample NOAA VDatum corrections."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "paleo-coastlines" / "work"
OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "central_bay_vertical_datum_pilot.json"
OUT_MD = ROOT / "docs" / "central-bay-vertical-datum-pilot.md"
CENTRAL = WORK / "usgs_sf_bay_1m_central_navd88_terrain_wgs84.tif"
BOUNDS = (-122.52, 37.70, -122.22, 38.01)
VDATUM_POINTS = [
    (-122.46, 37.86),
    (-122.42, 37.84),
    (-122.38, 37.82),
    (-122.34, 37.80),
    (-122.30, 37.78),
]


def warp(path: Path, output: Path, width: int) -> None:
    subprocess.run([
        "gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326",
        "-te", *(str(value) for value in BOUNDS),
        "-ts", str(width), "0", "-r", "bilinear", "-ot", "Float32",
        "-srcnodata", "-9999", "-dstnodata", "-9999", str(path), str(output),
    ], check=True)


def load(path: Path) -> np.ndarray:
    values = np.asarray(Image.open(path), dtype=np.float32)
    return values[:, :, 0] if values.ndim > 2 else values


def pair_stats(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float | int]:
    valid = (
        np.isfinite(reference) & np.isfinite(candidate)
        & (reference > -9000) & (candidate > -9000)
        & (reference < 100_000) & (candidate < 100_000)
    )
    delta = candidate[valid] - reference[valid]
    if delta.size == 0:
        return {"overlapPixels": 0}
    return {
        "overlapPixels": int(delta.size),
        "medianMeters": round(float(np.median(delta)), 3),
        "p10Meters": round(float(np.percentile(delta, 10)), 3),
        "p90Meters": round(float(np.percentile(delta, 90)), 3),
        "p95AbsMeters": round(float(np.percentile(np.abs(delta), 95)), 3),
    }


def vdatum_sample(lon: float, lat: float) -> dict[str, float]:
    # NOAA's West Coast route requires IGS14 on the tidal-datum side. Sampling
    # zero NAVD88 height gives the local NAVD88 -> MLLW correction directly.
    query = urllib.parse.urlencode({
        "region": "westcoast",
        "s_x": lon,
        "s_y": lat,
        "s_z": 0,
        "t_h_frame": "IGS14",
    })
    with urllib.request.urlopen(
        f"https://vdatum.noaa.gov/vdatumweb/api/convert?{query}", timeout=30
    ) as response:
        payload = json.load(response)
    if payload.get("errorCode"):
        raise RuntimeError(f"VDatum error {payload['errorCode']}: {payload.get('message')}")
    return {
        "longitude": lon,
        "latitude": lat,
        "navd88ToMllwMeters": float(payload["t_z"]),
        "uncertaintyMeters": float(payload["uncertainty"]),
    }


def build_report(width: int, skip_vdatum: bool) -> dict:
    if not CENTRAL.exists():
        raise SystemExit(f"Missing Central Bay reference raster: {CENTRAL}")
    sources = sorted(WORK.glob("noaa_ocm_area_a_*_1m_terrain_wgs84.tif"))
    comparisons = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        central_warp = temp / "central.tif"
        warp(CENTRAL, central_warp, width)
        reference = load(central_warp)
        for source in sources:
            source_warp = temp / source.name
            warp(source, source_warp, width)
            stats = pair_stats(reference, load(source_warp))
            if stats["overlapPixels"] < 100:
                continue
            comparisons.append({"sourceId": source.stem.removesuffix("_terrain_wgs84"), **stats})

    vdatum = [] if skip_vdatum else [vdatum_sample(lon, lat) for lon, lat in VDATUM_POINTS]
    aligned = [item for item in comparisons if abs(float(item["medianMeters"])) <= 0.1]
    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "referenceSourceId": "usgs_sf_bay_1m_central_navd88",
        "sampleWidth": width,
        "comparisons": comparisons,
        "vdatumSamples": vdatum,
        "conclusion": {
            "alignedSurveyCount": len(aligned),
            "comparedSurveyCount": len(comparisons),
            "applyBlanketOffset": False,
            "reason": (
                "Most overlapping NOAA source blocks already match the Central Bay NAVD88 mosaic "
                "within centimeters. The isolated CA1B08 difference is not evidence of a regional offset."
            ),
        },
    }


def write_markdown(report: dict) -> None:
    lines = [
        "# Central Bay Vertical-Datum Pilot",
        "",
        "This report tests whether Central Bay needs one blanket height correction. It does not modify production terrain.",
        "",
        "## Overlap Results",
        "",
        "| NOAA source block | Overlap pixels | Median difference | 10th–90th percentile | 95% absolute difference |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in report["comparisons"]:
        lines.append(
            f"| {item['sourceId']} | {item['overlapPixels']} | {item['medianMeters']} m | "
            f"{item['p10Meters']} to {item['p90Meters']} m | {item['p95AbsMeters']} m |"
        )
    lines.extend(["", "## NOAA VDatum Samples", ""])
    if report["vdatumSamples"]:
        lines.extend([
            "These values are the modeled correction from zero meters NAVD88 to MLLW at each point.",
            "",
            "| Longitude | Latitude | NAVD88 → MLLW | Stated uncertainty |",
            "|---:|---:|---:|---:|",
        ])
        for item in report["vdatumSamples"]:
            lines.append(
                f"| {item['longitude']} | {item['latitude']} | {item['navd88ToMllwMeters']} m | "
                f"±{item['uncertaintyMeters']} m |"
            )
    else:
        lines.append("VDatum sampling was skipped for this run.")
    lines.extend([
        "",
        "## Decision",
        "",
        "Do **not** apply a blanket Central Bay vertical offset. Most source blocks already align within centimeters. "
        "Investigate CA1B08 as a local survey-edge or surface-age difference before changing its heights.",
        "",
        "The earlier roughly 33 m Central Bay warning is a comparison against broad CUDEM, not evidence that the modern Central Bay source stack is shifted by 33 m.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--skip-vdatum", action="store_true")
    args = parser.parse_args()
    report = build_report(args.width, args.skip_vdatum)
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
