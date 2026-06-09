#!/usr/bin/env python3
"""Process one raw multibeam sample into a small GeoTIFF grid.

This is intentionally a sample-scale tool. It proves the raw-sonar path before
we download and grid full surveys.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK_DIR = ROOT / "data" / "paleo-coastlines" / "raw-sonar-probe"
DEFAULT_IMAGE = "mbari/mbsystem:latest"


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def capture(command: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(command, cwd=cwd, check=True, text=True, stdout=subprocess.PIPE).stdout


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    with urllib.request.urlopen(url, timeout=60) as response:
        with path.open("wb") as output:
            shutil.copyfileobj(response, output)


def decompress_gzip(source: Path, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    with gzip.open(source, "rb") as compressed:
        with dest.open("wb") as output:
            shutil.copyfileobj(compressed, output)


def downloaded_raw_path(download_path: Path) -> Path:
    if download_path.name.endswith(".gz"):
        raw_path = download_path.with_name(download_path.name.removesuffix(".gz"))
        decompress_gzip(download_path, raw_path)
        return raw_path
    return download_path


def safe_stem(path: Path) -> str:
    stem = path.name.removesuffix(".gz")
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in stem)


def docker_run(image: str, work_dir: Path, inner_command: str) -> None:
    uid_gid = f"{capture(['id', '-u']).strip()}:{capture(['id', '-g']).strip()}"
    run([
        "docker",
        "run",
        "--rm",
        "--user",
        uid_gid,
        "-v",
        f"{work_dir}:/work",
        "-w",
        "/work",
        image,
        "bash",
        "-lc",
        inner_command,
    ])


def parse_xyz_rows(path: Path) -> Iterable[tuple[float, float, float]]:
    with path.open() as file:
        for line in file:
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                z = float(parts[2])
            except ValueError:
                continue
            yield lon, lat, z


def filter_points(raw_xyz: Path, valid_csv: Path, min_lon: float, min_lat: float, thin_every: int) -> dict[str, float | int]:
    count = 0
    raw_count = 0
    unthinned_valid_count = 0
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    with valid_csv.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["lon", "lat", "z"])
        for lon, lat, z in parse_xyz_rows(raw_xyz):
            raw_count += 1
            if lon >= min_lon or lat <= min_lat or z >= 0:
                continue
            unthinned_valid_count += 1
            if thin_every > 1 and (unthinned_valid_count - 1) % thin_every != 0:
                continue
            writer.writerow([f"{lon:.10f}", f"{lat:.10f}", f"{z:.4f}"])
            count += 1
            min_x = min(min_x, lon)
            max_x = max(max_x, lon)
            min_y = min(min_y, lat)
            max_y = max(max_y, lat)
            min_z = min(min_z, z)
            max_z = max(max_z, z)
    if count == 0:
        raise RuntimeError("No valid sonar points remained after filtering.")
    return {
        "rawPointCount": raw_count,
        "validPointCount": count,
        "unthinnedValidPointCount": unthinned_valid_count,
        "thinEvery": thin_every,
        "minLon": min_x,
        "maxLon": max_x,
        "minLat": min_y,
        "maxLat": max_y,
        "minZ": min_z,
        "maxZ": max_z,
    }


def write_vrt(path: Path, csv_name: str) -> None:
    layer = Path(csv_name).stem
    path.write_text(f"""<OGRVRTDataSource>
  <OGRVRTLayer name="valid_points">
    <SrcDataSource relativeToVRT="1">{csv_name}</SrcDataSource>
    <SrcLayer>{layer}</SrcLayer>
    <GeometryType>wkbPoint25D</GeometryType>
    <LayerSRS>EPSG:4326</LayerSRS>
    <Field name="z" type="Real" />
    <GeometryField encoding="PointFromColumns" x="lon" y="lat" z="z" />
  </OGRVRTLayer>
</OGRVRTDataSource>
""")


def grid_points(vrt: Path, tif: Path, stats: dict[str, float | int], grid_size: int, algorithm: str) -> str:
    tif.unlink(missing_ok=True)
    Path(f"{tif}.aux.xml").unlink(missing_ok=True)
    run([
        "gdal_grid",
        "-q",
        "-zfield",
        "z",
        "-a",
        algorithm,
        "-txe",
        str(stats["minLon"]),
        str(stats["maxLon"]),
        "-tye",
        str(stats["minLat"]),
        str(stats["maxLat"]),
        "-outsize",
        str(grid_size),
        str(grid_size),
        "-of",
        "GTiff",
        "-ot",
        "Float32",
        "-l",
        "valid_points",
        str(vrt),
        str(tif),
    ])
    return capture(["gdalinfo", "-stats", str(tif)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Process one raw multibeam sonar sample into a GeoTIFF grid.")
    parser.add_argument("--survey-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--format", type=int, default=58)
    parser.add_argument("--docker-image", default=DEFAULT_IMAGE)
    parser.add_argument("--grid-size", type=int, default=512)
    parser.add_argument(
        "--algorithm",
        default="invdistnn:power=2.0:radius=0.002:max_points=12:min_points=1:nodata=-9999",
        help=(
            "GDAL gridding algorithm. The default keeps interpolation local so empty "
            "swath-adjacent space becomes nodata instead of fake shallow water."
        ),
    )
    parser.add_argument("--min-valid-lon", type=float, default=-120.0)
    parser.add_argument("--min-valid-lat", type=float, default=30.0)
    parser.add_argument(
        "--thin-every",
        type=int,
        default=1,
        help="For preview grids, keep every Nth valid point. Use 1 to keep every point.",
    )
    parser.add_argument(
        "--skip-grid",
        action="store_true",
        help="Only extract and summarize point bounds. This is faster for file-level indexing.",
    )
    args = parser.parse_args()

    work_dir = (args.work_dir / args.survey_id.lower()).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    download_path = work_dir / Path(urllib.request.urlparse(args.url).path).name
    sample_id = f"{args.survey_id.lower()}-{safe_stem(download_path)}"
    raw_xyz = work_dir / f"{sample_id}.xyz.raw"
    valid_csv = work_dir / f"{sample_id}.valid.csv"
    vrt = work_dir / f"{sample_id}.valid.vrt"
    tif = work_dir / f"{sample_id}.sample-grid.tif"
    report_path = work_dir / f"{sample_id}.sample-report.json"

    download(args.url, download_path)
    raw_path = downloaded_raw_path(download_path)
    docker_run(args.docker_image, work_dir, (
        f"mbinfo -I {raw_path.name} -F{args.format} > {args.survey_id.lower()}.mbinfo.txt && "
        f"mblist -I {raw_path.name} -F{args.format} -OXYZ -MA > {raw_xyz.name}"
    ))
    if args.thin_every < 1:
        raise ValueError("--thin-every must be 1 or greater.")
    stats = filter_points(raw_xyz, valid_csv, args.min_valid_lon, args.min_valid_lat, args.thin_every)
    write_vrt(vrt, valid_csv.name)
    grid_info = None
    if not args.skip_grid:
        grid_info = grid_points(vrt, tif, stats, args.grid_size, args.algorithm)

    report = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "surveyId": args.survey_id,
        "url": args.url,
        "workDir": str(work_dir),
        "dockerImage": args.docker_image,
        "format": args.format,
        "gridSize": args.grid_size,
        "algorithm": args.algorithm,
        "rawFileBytes": raw_path.stat().st_size,
        "downloadFileBytes": download_path.stat().st_size,
        "gridPath": str(tif) if not args.skip_grid else None,
        "stats": stats,
        "gdalInfo": grid_info,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
