#!/usr/bin/env python3
"""Build a masked candidate grid from already-extracted raw sonar points."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def capture(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE).stdout


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("sources must look like LABEL=/path/to/points.csv")
    label, path = value.split("=", 1)
    return label, Path(path)


def crop_points(sources: list[tuple[str, Path]], output_csv: Path, bounds: list[float]) -> dict[str, object]:
    min_lon, min_lat, max_lon, max_lat = bounds
    counts: dict[str, int] = {}
    total = 0
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["lon", "lat", "z", "source"])
        for label, path in sources:
            kept = 0
            with path.open() as source_file:
                reader = csv.DictReader(source_file)
                for row in reader:
                    lon = float(row["lon"])
                    lat = float(row["lat"])
                    z = float(row["z"])
                    if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                        writer.writerow([f"{lon:.10f}", f"{lat:.10f}", f"{z:.4f}", label])
                        kept += 1
                        total += 1
                        min_x = min(min_x, lon)
                        max_x = max(max_x, lon)
                        min_y = min(min_y, lat)
                        max_y = max(max_y, lat)
                        min_z = min(min_z, z)
                        max_z = max(max_z, z)
            counts[label] = kept
    if total == 0:
        raise RuntimeError("No points remained after crop.")
    return {
        "totalPoints": total,
        "pointsBySource": counts,
        "pointBounds": [min_x, min_y, max_x, max_y],
        "depthRange": [min_z, max_z],
    }


def write_vrt(path: Path, csv_name: str, layer_name: str) -> None:
    src_layer = Path(csv_name).stem
    path.write_text(f"""<OGRVRTDataSource>
  <OGRVRTLayer name="{layer_name}">
    <SrcDataSource relativeToVRT="1">{csv_name}</SrcDataSource>
    <SrcLayer>{src_layer}</SrcLayer>
    <GeometryType>wkbPoint25D</GeometryType>
    <LayerSRS>EPSG:4326</LayerSRS>
    <Field name="z" type="Real" />
    <GeometryField encoding="PointFromColumns" x="lon" y="lat" z="z" />
  </OGRVRTLayer>
</OGRVRTDataSource>
""")


def gdal_info_stats(path: Path) -> dict[str, float | None]:
    info = capture(["gdalinfo", "-stats", str(path)])
    stats: dict[str, float | None] = {}
    for line in info.splitlines():
        text = line.strip()
        if text.startswith("STATISTICS_VALID_PERCENT="):
            stats["validPercent"] = float(text.split("=", 1)[1])
        elif text.startswith("STATISTICS_MINIMUM="):
            stats["minimum"] = float(text.split("=", 1)[1])
        elif text.startswith("STATISTICS_MAXIMUM="):
            stats["maximum"] = float(text.split("=", 1)[1])
        elif text.startswith("STATISTICS_MEAN="):
            stats["mean"] = float(text.split("=", 1)[1])
    return stats


def sample(path: Path, lon: float, lat: float) -> float | None:
    output = capture(["gdallocationinfo", "-wgs84", "-valonly", str(path), str(lon), str(lat)]).strip()
    if not output:
        return None
    return float(output.splitlines()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a masked raw-sonar candidate grid.")
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--source", action="append", type=parse_source, required=True)
    parser.add_argument("--cell-bounds", nargs=4, type=float, metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"), required=True)
    parser.add_argument("--buffer-degrees", type=float, default=0.003)
    parser.add_argument("--grid-size", type=int, default=512)
    parser.add_argument("--mask-radius", type=float, default=0.00035)
    parser.add_argument("--center", nargs=2, type=float, metavar=("LON", "LAT"))
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    cell_min_lon, cell_min_lat, cell_max_lon, cell_max_lat = args.cell_bounds
    bounds = [
        cell_min_lon - args.buffer_degrees,
        cell_min_lat - args.buffer_degrees,
        cell_max_lon + args.buffer_degrees,
        cell_max_lat + args.buffer_degrees,
    ]
    safe_id = args.cell_id.lower().replace("_", "-")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    points_csv = args.out_dir / f"{safe_id}.points.csv"
    points_vrt = args.out_dir / f"{safe_id}.points.vrt"
    grid = args.out_dir / f"{safe_id}.linear-{args.grid_size}.tif"
    count = args.out_dir / f"{safe_id}.count-{args.grid_size}.tif"
    mask = args.out_dir / f"{safe_id}.mask-{args.grid_size}.tif"
    masked = args.out_dir / f"{safe_id}.masked-{args.grid_size}.tif"
    cog = args.out_dir / f"{safe_id}.masked-{args.grid_size}.cog.tif"
    summary_path = args.out_dir / f"{safe_id}.candidate-summary.json"
    layer_name = safe_id.replace("-", "_") + "_points"

    crop = crop_points(args.source, points_csv, bounds)
    write_vrt(points_vrt, points_csv.name, layer_name)
    for path in [grid, count, mask, masked, cog]:
        path.unlink(missing_ok=True)
        Path(f"{path}.aux.xml").unlink(missing_ok=True)

    run([
        "gdal_grid", "-q", "-zfield", "z", "-a", "linear:nodata=-9999",
        "-txe", str(bounds[0]), str(bounds[2]), "-tye", str(bounds[1]), str(bounds[3]),
        "-outsize", str(args.grid_size), str(args.grid_size), "-of", "GTiff", "-ot", "Float32",
        "-l", layer_name, str(points_vrt), str(grid),
    ])
    run([
        "gdal_grid", "-q", "-zfield", "z",
        "-a", f"count:radius1={args.mask_radius}:radius2={args.mask_radius}:min_points=1:nodata=0",
        "-txe", str(bounds[0]), str(bounds[2]), "-tye", str(bounds[1]), str(bounds[3]),
        "-outsize", str(args.grid_size), str(args.grid_size), "-of", "GTiff", "-ot", "Float32",
        "-l", layer_name, str(points_vrt), str(count),
    ])
    run([
        "gdal_calc.py", f"-A={count}", f"--outfile={mask}", "--calc=A>0",
        "--type=Byte", "--NoDataValue=0", "--co", "COMPRESS=DEFLATE", "--overwrite", "--quiet",
    ])
    run([
        "gdal_calc.py", f"-A={mask}", f"-B={grid}", f"--outfile={masked}",
        "--calc=where(A>0,B,-9999)", "--type=Float32", "--NoDataValue=-9999",
        "--co", "COMPRESS=DEFLATE", "--co", "PREDICTOR=3", "--overwrite", "--quiet",
    ])
    run(["gdal_translate", "-q", "-of", "COG", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3", str(masked), str(cog)])

    center_sample = None
    if args.center:
        center_sample = {
            "lon": args.center[0],
            "lat": args.center[1],
            "value": sample(cog, args.center[0], args.center[1]),
            "mask": sample(mask, args.center[0], args.center[1]),
        }

    summary = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cellId": args.cell_id,
        "cellBounds": args.cell_bounds,
        "bufferDegrees": args.buffer_degrees,
        "candidateBounds": bounds,
        "gridSize": args.grid_size,
        "maskRadius": args.mask_radius,
        "sources": [{"label": label, "path": str(path)} for label, path in args.source],
        **crop,
        "grid": str(grid),
        "count": str(count),
        "mask": str(mask),
        "masked": str(masked),
        "maskedCog": str(cog),
        "gridStats": gdal_info_stats(grid),
        "maskStats": gdal_info_stats(mask),
        "maskedStats": gdal_info_stats(cog),
        "centerSample": center_sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
