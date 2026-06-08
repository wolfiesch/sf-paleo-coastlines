#!/usr/bin/env python3
"""Bake a land-area-exposed-per-sea-level table for the change readout.

Usage: python3 scripts/generate_sealevel_stats.py [--dem PATH] [--width N]
"""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from osgeo import gdal

from sealevel_stats import exposed_area_km2_by_level

gdal.UseExceptions()

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work"
PUBLIC_DIR = ROOT / "public" / "data" / "paleo-coastlines"
DEFAULT_DEM = WORK_DIR / "noaa_cudem_1_9as_terrain_wgs84.tif"
OUTPUT = PUBLIC_DIR / "sealevel_stats.json"
NODATA = -9999.0
LEVELS = [float(m) for m in range(-120, 5, 5)]  # -120..0 step 5 (matches probe)
EARTH_RADIUS_M = 6_371_000.0


def read_dem(dem_path: Path, target_width: int):
    src = gdal.Open(str(dem_path))
    if src is None:
        raise FileNotFoundError(f"Cannot open DEM: {dem_path}")
    scale = min(1.0, target_width / src.RasterXSize)
    out_w = max(1, int(round(src.RasterXSize * scale)))
    out_h = max(1, int(round(src.RasterYSize * scale)))
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    gdal.Warp(tmp_path, src, width=out_w, height=out_h, resampleAlg="bilinear",
              srcNodata=NODATA, dstNodata=NODATA, outputType=gdal.GDT_Float32)
    src = None
    ds = gdal.Open(tmp_path)
    elev = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    gt = ds.GetGeoTransform()
    ds = None
    Path(tmp_path).unlink(missing_ok=True)
    return elev, gt


def cell_area_grid(shape, gt) -> np.ndarray:
    """Approximate per-cell area in m^2 for a WGS84 grid (varies with latitude)."""
    rows, cols = shape
    deg_lon = abs(gt[1])
    deg_lat = abs(gt[5])
    lat_per_row = gt[3] + (np.arange(rows) + 0.5) * gt[5]
    m_per_deg_lat = (math.pi / 180.0) * EARTH_RADIUS_M
    m_per_deg_lon = m_per_deg_lat * np.cos(np.radians(lat_per_row))
    row_area = (deg_lat * m_per_deg_lat) * (deg_lon * m_per_deg_lon)  # per-row m^2
    return np.repeat(row_area[:, None], cols, axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--width", type=int, default=2000)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    elev, gt = read_dem(args.dem, args.width)
    valid = (elev != NODATA) & np.isfinite(elev)
    area = cell_area_grid(elev.shape, gt)
    rows = exposed_area_km2_by_level(elev, area, valid, LEVELS)

    payload = {
        "source_dem": args.dem.name,
        "present_level_m": 0.0,
        "levels": rows,
        "note": (
            "Land area exposed at each sea level versus today, from the "
            "topobathymetry DEM. Approximate; ignores sediment infill and "
            "post-glacial land motion."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    biggest = rows[0]
    print(f"wrote {len(rows)} levels -> {args.output}")
    print(f"at {biggest['meters']} m: {biggest['exposed_vs_present_km2']} km^2 exposed vs present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
