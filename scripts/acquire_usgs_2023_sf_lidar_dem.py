#!/usr/bin/env python3
"""Acquire the 2023 USGS San Francisco 1 m LiDAR DEM tiles.

The source lives in the public USGS TNM S3 bucket as many small GeoTIFF tiles.
By default this script writes a lightweight manifest. Use --download to fetch
the tiles into the local raw data folder used by the terrain generator.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "paleo-coastlines" / "raw" / "usgs-2023-sf-lidar-dem"
OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "usgs_2023_sf_lidar_dem_manifest.json"
OUT_MD = ROOT / "docs" / "usgs-2023-sf-lidar-dem.md"

S3_BUCKET_URL = "https://prd-tnm.s3.amazonaws.com"
S3_PREFIX = "StagedProducts/Elevation/OPR/Projects/CA_SanFrancisco_B23/CA_SanFrancisco_1_B23/TIFF/"
INDEX_URL = f"{S3_BUCKET_URL}/index.html?prefix={S3_PREFIX}"
LIST_URL = f"{S3_BUCKET_URL}/?list-type=2&prefix={urllib.parse.quote(S3_PREFIX, safe='/')}&max-keys=1000"
SOURCE_URL = "https://apps.nationalmap.gov/downloader/#/search-results?datasets=Digital%20Elevation%20Model%20%28DEM%29%201%20meter&bbox=-122.6,37.65,-122.25,38.0"


def human_size(size: int | float | None) -> str:
    if size is None:
        return "unknown"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value:.0f} B"
        value /= 1024
    return f"{value:.1f} TB"


def fetch_tile_index() -> list[dict[str, Any]]:
    request = urllib.request.Request(LIST_URL, headers={"User-Agent": "sf-paleo-coastlines/0.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        xml = response.read()
    root = ET.fromstring(xml)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

    tiles: list[dict[str, Any]] = []
    for item in root.findall("s3:Contents", namespace):
        key = item.findtext("s3:Key", default="", namespaces=namespace)
        if not key.lower().endswith((".tif", ".tiff")):
            continue
        size = int(item.findtext("s3:Size", default="0", namespaces=namespace))
        name = Path(key).name
        tiles.append({
            "name": name,
            "key": key,
            "url": f"{S3_BUCKET_URL}/{urllib.parse.quote(key, safe='/')}",
            "sizeBytes": size,
            "sizeHuman": human_size(size),
            "localPath": str((RAW_DIR / name).relative_to(ROOT)),
        })

    tiles.sort(key=lambda tile: tile["name"])
    return tiles


def existing_file_is_usable(path: Path, expected_size: int) -> bool:
    return path.exists() and path.stat().st_size == expected_size


def local_status(tiles: list[dict[str, Any]]) -> dict[str, Any]:
    present = 0
    bytes_present = 0
    for tile in tiles:
        path = RAW_DIR / tile["name"]
        if existing_file_is_usable(path, int(tile["sizeBytes"])):
            present += 1
            bytes_present += int(tile["sizeBytes"])
    total = sum(int(tile["sizeBytes"]) for tile in tiles)
    return {
        "expectedCount": len(tiles),
        "presentCount": present,
        "missingCount": len(tiles) - present,
        "totalBytes": total,
        "totalHuman": human_size(total),
        "presentBytes": bytes_present,
        "presentHuman": human_size(bytes_present),
        "complete": present == len(tiles) and bool(tiles),
    }


def require_free_space(tiles: list[dict[str, Any]], minimum_free_gb: float | None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    missing_bytes = sum(
        int(tile["sizeBytes"])
        for tile in tiles
        if not existing_file_is_usable(RAW_DIR / tile["name"], int(tile["sizeBytes"]))
    )
    if minimum_free_gb is not None:
        required = int(minimum_free_gb * 1024 * 1024 * 1024)
    else:
        # Keep room for .part files, VRT/warped terrain, PNG outputs, and a build.
        required = int(missing_bytes * 1.35 + (3 * 1024 * 1024 * 1024))
    available = shutil.disk_usage(RAW_DIR).free
    if available < required:
        raise RuntimeError(
            f"Not enough free disk space: available {human_size(available)}, "
            f"need about {human_size(required)} before downloading {human_size(missing_bytes)}."
        )


def download_tile(tile: dict[str, Any], force: bool) -> dict[str, Any]:
    target = RAW_DIR / tile["name"]
    expected_size = int(tile["sizeBytes"])
    if not force and existing_file_is_usable(target, expected_size):
        return {"name": tile["name"], "status": "cached", "bytes": expected_size}

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    if force:
        target.unlink(missing_ok=True)
        part.unlink(missing_ok=True)

    command = [
        "curl",
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "4",
        "--retry-delay",
        "3",
        "--connect-timeout",
        "20",
        "--max-time",
        "900",
        "-C",
        "-",
        "-o",
        str(part),
        str(tile["url"]),
    ]
    subprocess.run(command, check=True)
    actual_size = part.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(f"{tile['name']} expected {expected_size} bytes, got {actual_size}")
    part.replace(target)
    return {"name": tile["name"], "status": "downloaded", "bytes": expected_size}


def download_tiles(tiles: list[dict[str, Any]], workers: int, force: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        future_to_tile = {pool.submit(download_tile, tile, force): tile for tile in tiles}
        for index, future in enumerate(concurrent.futures.as_completed(future_to_tile), start=1):
            result = future.result()
            results.append(result)
            if index % 25 == 0 or result["status"] == "downloaded":
                print(f"[{index}/{len(tiles)}] {result['status']}: {result['name']} ({human_size(result['bytes'])})")
    results.sort(key=lambda item: item["name"])
    return results


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_doc(manifest: dict[str, Any]) -> None:
    status = manifest["localStatus"]
    lines = [
        "# USGS 2023 San Francisco 1 m LiDAR DEM",
        "",
        "This file is generated by `python3 scripts/acquire_usgs_2023_sf_lidar_dem.py`.",
        "",
        "Plain-English purpose: this is a high-resolution land DEM for San Francisco. It sharpens the above-water terrain and shoreline edge in the 3D scene, which helps make the waterline recession view feel less like a smooth blanket and more like real topography.",
        "",
        f"- Source browser: {SOURCE_URL}",
        f"- Public USGS S3 index: {INDEX_URL}",
        f"- Raw folder: `{RAW_DIR.relative_to(ROOT)}`",
        f"- Tile count: {status['expectedCount']}",
        f"- Present locally: {status['presentCount']} of {status['expectedCount']}",
        f"- Total source size: {status['totalHuman']}",
        "",
        "## Rebuild",
        "",
        "```bash",
        "pnpm paleo-coastlines:usgs-2023-sf-dem --download",
        "pnpm paleo-coastlines:generate",
        "```",
        "",
        "## Caveats",
        "",
        "- This is land LiDAR, not a new offshore bathymetry survey.",
        "- It improves visual detail where the modern land surface exists; it does not model paleo erosion, sediment, marsh growth, or tectonic movement.",
        "- Treat exact waterline alignment as approximate until the whole stack gets a local vertical-datum pass.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))


def build_manifest(download_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    tiles = fetch_tile_index()
    manifest = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "id": "usgs_2023_sf_lidar_dem",
        "label": "2023 USGS Lidar DEM: San Francisco, CA",
        "sourceFamily": "USGS 3DEP / The National Map",
        "sourceUrl": SOURCE_URL,
        "s3IndexUrl": INDEX_URL,
        "s3ListUrl": LIST_URL,
        "rawDir": str(RAW_DIR.relative_to(ROOT)),
        "localStatus": local_status(tiles),
        "tiles": tiles,
    }
    if download_results is not None:
        manifest["downloadResults"] = download_results
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download all missing GeoTIFF tiles.")
    parser.add_argument("--force", action="store_true", help="Redownload existing tiles.")
    parser.add_argument("--workers", type=int, default=8, help="Parallel downloads. Default: 8.")
    parser.add_argument("--minimum-free-gb", type=float, default=None, help="Require this much free space before downloading.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest()
    results: list[dict[str, Any]] | None = None

    if args.download:
        require_free_space(manifest["tiles"], args.minimum_free_gb)
        results = download_tiles(manifest["tiles"], args.workers, args.force)
        manifest = build_manifest(results)

    write_json(OUT_JSON, manifest)
    write_doc(manifest)

    status = manifest["localStatus"]
    print(
        f"USGS 2023 SF LiDAR DEM manifest: {status['presentCount']}/{status['expectedCount']} tiles present, "
        f"{status['presentHuman']} of {status['totalHuman']}."
    )
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
