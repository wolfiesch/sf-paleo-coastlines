#!/usr/bin/env python3
"""Generate the last-glacial-lowstand paleo-drainage network as browser GeoJSON.

Usage:
  python3 scripts/generate_paleo_rivers.py            # defaults below
  python3 scripts/generate_paleo_rivers.py --dem data/.../best_available_gate_shelf_terrain_wgs84.tif
  python3 scripts/generate_paleo_rivers.py --hydro-width 1200 --channel-quantile 0.9985
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
from osgeo import gdal

from paleo_hydrology import (
    d8_flow_directions,
    fill_depressions,
    flow_accumulation,
    simplify_polyline,
    trace_channels,
)

gdal.UseExceptions()

ROOT = Path(__file__).resolve().parent.parent
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work"
PUBLIC_DIR = ROOT / "public" / "data" / "paleo-coastlines"
DEFAULT_DEM = WORK_DIR / "noaa_cudem_1_9as_terrain_wgs84.tif"
OUTPUT_GEOJSON = PUBLIC_DIR / "paleo_rivers.geojson"

LOWSTAND_SEA_LEVEL_M = -120.0
DEFAULT_HYDRO_WIDTH = 1400        # downsample width keeps pure-python hydrology fast
DEFAULT_CHANNEL_QUANTILE = 0.997  # accumulation percentile that becomes "river"
DEFAULT_SIMPLIFY_DEG = 0.0008     # ~80 m DP tolerance in degrees
NODATA = -9999.0


def read_downsampled_dem(dem_path: Path, target_width: int):
    """Return (elev float32 2D, geotransform) downsampled to target_width via gdal."""
    src = gdal.Open(str(dem_path))
    if src is None:
        raise FileNotFoundError(f"Cannot open DEM: {dem_path}")
    full_w = src.RasterXSize
    full_h = src.RasterYSize
    scale = min(1.0, target_width / full_w)
    out_w = max(1, int(round(full_w * scale)))
    out_h = max(1, int(round(full_h * scale)))

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    gdal.Warp(
        tmp_path,
        src,
        width=out_w,
        height=out_h,
        resampleAlg="bilinear",
        srcNodata=NODATA,
        dstNodata=NODATA,
        outputType=gdal.GDT_Float32,
    )
    src = None

    ds = gdal.Open(tmp_path)
    band = ds.GetRasterBand(1)
    elev = band.ReadAsArray().astype(np.float32)
    gt = ds.GetGeoTransform()
    ds = None
    Path(tmp_path).unlink(missing_ok=True)
    return elev, gt


def pixel_to_lonlat(r: int, c: int, gt) -> tuple[float, float]:
    """Cell-centre lon/lat from a GDAL geotransform."""
    lon = gt[0] + (c + 0.5) * gt[1] + (r + 0.5) * gt[2]
    lat = gt[3] + (c + 0.5) * gt[4] + (r + 0.5) * gt[5]
    return lon, lat


def flow_order(max_flow: float, flow_breaks: list[float]) -> int:
    """Bucket a channel's max accumulation into a 1..len(breaks) display order."""
    order = 1
    for i, brk in enumerate(flow_breaks):
        if max_flow >= brk:
            order = i + 1
    return order


def build_feature_collection(lines, elev, gt, simplify_deg):
    if not lines:
        return {"type": "FeatureCollection", "features": []}, []

    flows = sorted(line["max_flow"] for line in lines)
    # Order breakpoints at the 50/80/95/99th percentiles of channel size.
    flow_breaks = [flows[int(q * (len(flows) - 1))] for q in (0.0, 0.5, 0.8, 0.95, 0.99)]

    features = []
    for line in lines:
        raw = [pixel_to_lonlat(r, c, gt) for (r, c) in line["cells"]]
        simplified = simplify_polyline(raw, tolerance=simplify_deg)
        # Re-attach elevation per kept vertex by nearest source cell.
        coords = []
        elevations = []
        for (lon, lat), (r, c) in zip(raw, line["cells"]):
            if (lon, lat) not in simplified:
                continue
            e = float(elev[r, c])
            coords.append([round(lon, 6), round(lat, 6), round(e, 1)])
            elevations.append(e)
        if len(coords) < 2:
            coords = [[round(lon, 6), round(lat, 6), round(float(elev[r, c]), 1)]
                      for (lon, lat), (r, c) in zip(raw, line["cells"])]
            elevations = [float(elev[r, c]) for (r, c) in line["cells"]]
        features.append({
            "type": "Feature",
            "properties": {
                "flow": round(line["max_flow"], 1),
                "order": flow_order(line["max_flow"], flow_breaks),
                "min_elevation_m": round(min(elevations), 1),
                "max_elevation_m": round(max(elevations), 1),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    return {"type": "FeatureCollection", "features": features}, flow_breaks


def write_compact_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dem", type=Path, default=DEFAULT_DEM)
    parser.add_argument("--hydro-width", type=int, default=DEFAULT_HYDRO_WIDTH)
    parser.add_argument("--channel-quantile", type=float, default=DEFAULT_CHANNEL_QUANTILE)
    parser.add_argument("--simplify-deg", type=float, default=DEFAULT_SIMPLIFY_DEG)
    parser.add_argument("--output", type=Path, default=OUTPUT_GEOJSON)
    args = parser.parse_args()

    elev, gt = read_downsampled_dem(args.dem, args.hydro_width)
    print(f"DEM read: {elev.shape[1]}x{elev.shape[0]} px from {args.dem.name}")

    valid = (elev > LOWSTAND_SEA_LEVEL_M) & (elev != NODATA) & np.isfinite(elev)
    print(f"subaerial cells at lowstand: {int(valid.sum())}")

    filled = fill_depressions(elev, valid)
    flowdir = d8_flow_directions(filled, valid)
    acc = flow_accumulation(flowdir, valid)

    acc_valid = acc[valid]
    threshold = float(np.quantile(acc_valid, args.channel_quantile))
    print(f"channel accumulation threshold (q={args.channel_quantile}): {threshold:.1f}")

    lines = trace_channels(flowdir, acc, valid, threshold=threshold)
    print(f"traced {len(lines)} channel polylines")

    fc, flow_breaks = build_feature_collection(lines, elev, gt, args.simplify_deg)
    fc["properties"] = {
        "source_dem": args.dem.name,
        "lowstand_sea_level_m": LOWSTAND_SEA_LEVEL_M,
        "hydro_width_px": int(elev.shape[1]),
        "channel_quantile": args.channel_quantile,
        "flow_order_breaks": [round(b, 1) for b in flow_breaks],
        "note": (
            "Paleo-drainage traced on topobathymetry with sea level at the "
            "last-glacial lowstand (-120 m). Channels are flow-accumulation "
            "estimates for visualization, not surveyed paleo-river courses."
        ),
    }
    write_compact_json(args.output, fc)
    print(f"wrote {len(fc['features'])} river features -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
