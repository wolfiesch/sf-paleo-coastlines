#!/usr/bin/env python3
"""Discover and optionally download the USGS 1 m San Francisco Bay DEM.

The full dataset is multi-gigabyte. By default this script only refreshes a
small manifest from ScienceBase, so we can make careful download choices before
adding the source to the terrain generator.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import urllib.parse
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "paleo-coastlines" / "raw" / "usgs-sf-bay-1m-dem"
OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "usgs_sf_bay_1m_dem_manifest.json"
OUT_MD = ROOT / "docs" / "usgs-sf-bay-1m-dem.md"

SCIENCEBASE_ITEM_URL = "https://www.sciencebase.gov/catalog/item/{item_id}?format=json"

USGS_SF_BAY_1M_ITEMS: list[dict[str, Any]] = [
    {
        "section": "north",
        "datum": "NAVD88",
        "itemId": "5e1cb737e4b0ecf25c5f0bf6",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/NorthSFBay_DEM_Mosaic_NAVD88_1m_metadata.html",
        "fileName": "NorthSFBay_DEM_Mosaic_NAVD88_1m.tif",
        "sizeBytes": 4_390_436_473,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/5e1cb737e4b0ecf25c5f0bf6?f=__disk__1a%2F72%2F37%2F1a723772343e6b17b31de1fdb5a3adc3943491a5",
        "bounds": {"minX": -122.494946625, "maxX": -121.863425774, "minY": 37.954045436, "maxY": 38.136493633},
    },
    {
        "section": "central",
        "datum": "NAVD88",
        "itemId": "607df15ad34e8564d67e3ae9",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/CentralSFBay_DEM_Mosaic_NAVD88_1m_metadata.html",
        "fileName": "CentralSFBay_DEM_Mosaic_NAVD88_1M.zip",
        "sizeBytes": 962_525_101,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/607df15ad34e8564d67e3ae9?name=CentralSFBay_DEM_Mosaic_NAVD88_1M.zip",
        "bounds": {"minX": -122.516735, "maxX": -122.235097, "minY": 37.725137, "maxY": 37.994263},
    },
    {
        "section": "south",
        "datum": "NAVD88",
        "itemId": "607df17bd34e8564d67e3af0",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/SouthSFBay_DEM_Mosaic_NAVD88_1m_metadata.html",
        "fileName": "SouthSFBay_DEM_Mosaic_NAVD88_1m.zip",
        "sizeBytes": 1_051_095_550,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/607df17bd34e8564d67e3af0?f=__disk__fb%2Fe0%2F85%2Ffbe085c476effe78fe49486c657844f95ac47a24",
        "bounds": {"minX": -122.563558, "maxX": -121.779581, "minY": 37.40643, "maxY": 37.781613},
    },
    {
        "section": "north",
        "datum": "MLLW",
        "itemId": "5e16baa2e4b0ecf25c57fc3a",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/NorthSFBay_DEM_Mosaic_MLLW_1m_metadata.html",
        "fileName": "NorthSFBay_DEM_Mosaic_MLLW_1m.tif",
        "sizeBytes": 4_390_436_649,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/5e16baa2e4b0ecf25c57fc3a?f=__disk__c8%2F83%2Fa2%2Fc883a2d9ad177aac7bc240710b1e7d6cfb5ea84b",
        "bounds": {"minX": -122.494946625, "maxX": -121.863425774, "minY": 37.954045436, "maxY": 38.136493633},
    },
    {
        "section": "central",
        "datum": "MLLW",
        "itemId": "606b73efd34e3d0429b204d3",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/CentralSFBay_DEM_Mosaic_MLLW_1m_metadata.html",
        "fileName": "CentralSFBay_DEM_Mosaic_MLLW_1M.zip",
        "sizeBytes": 964_530_175,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/606b73efd34e3d0429b204d3?name=CentralSFBay_DEM_Mosaic_MLLW_1M.zip",
        "bounds": {"minX": -122.516735, "maxX": -122.235097, "minY": 37.725137, "maxY": 37.994263},
    },
    {
        "section": "south",
        "datum": "MLLW",
        "itemId": "607df116d34e8564d67e3ae6",
        "metadataUrl": "https://cmgds.marine.usgs.gov/catalog/pcmsc/DataReleases/ScienceBase/DR_P9TJTS8M/SouthSFBay_DEM_Mosaic_MLLW_1m_metadata.html",
        "fileName": "SouthSFBay_DEM_Mosaic_MLLW_1m.zip",
        "sizeBytes": 1_050_702_742,
        "downloadUrl": "https://www.sciencebase.gov/catalog/file/get/607df116d34e8564d67e3ae6?name=SouthSFBay_DEM_Mosaic_MLLW_1m.zip",
        "bounds": {"minX": -122.563558, "maxX": -121.779581, "minY": 37.40643, "maxY": 37.781613},
    },
]


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "sf-paleo-coastlines/0.1"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception as cause:  # noqa: BLE001 - retry public science endpoints.
            last_error = cause
            if attempt < 2:
                time.sleep(2 + attempt * 4)
    assert last_error is not None
    raise last_error


def cached_item(seed: dict[str, str]) -> dict[str, Any] | None:
    if not OUT_JSON.exists():
        return None
    try:
        payload = json.loads(OUT_JSON.read_text())
    except json.JSONDecodeError:
        return None
    for item in payload.get("items", []):
        if item.get("itemId") == seed["itemId"]:
            return item
    return None


def file_url(file_record: dict[str, Any]) -> str:
    return str(file_record.get("url") or file_record.get("downloadUri") or "")


def public_sciencebase_file_url(item_id: str, file_name: str) -> str:
    quoted_name = urllib.parse.quote(file_name)
    return f"https://www.sciencebase.gov/catalog/file/get/{item_id}?name={quoted_name}"


def normalized_file_url(item_id: str, file_record: dict[str, Any]) -> str:
    url = file_url(file_record)
    name = str(file_record.get("name") or "")
    if name and "/manager/item/" in url:
        return public_sciencebase_file_url(item_id, name)
    return url


def normalized_file_name(file_record: dict[str, Any]) -> str:
    return str(file_record.get("name") or "").replace("..", ".")


def is_primary_dem_file(file_record: dict[str, Any]) -> bool:
    name = str(file_record.get("name", "")).lower()
    if not (name.endswith(".tif") or name.endswith(".zip")):
        return False
    ignored_suffixes = (".ovr", ".aux.xml", ".xml", ".tfw", ".jpg")
    return not name.endswith(ignored_suffixes)


def local_download_path(record: dict[str, Any], file_record: dict[str, Any]) -> Path:
    raw_name = normalized_file_name(file_record)
    return RAW_DIR / record["datum"].lower() / record["section"] / raw_name


def human_size(size: int | float | None) -> str:
    if size is None:
        return "unknown"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value:.0f} B"
        value /= 1024
    return f"{value:.1f} TB"


def parse_gb(value: float) -> int:
    return int(value * 1024 * 1024 * 1024)


def available_bytes_for(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free


def require_free_space(target: Path, expected_size: int | None, minimum_free_gb: float | None) -> None:
    if minimum_free_gb is not None:
        required = parse_gb(minimum_free_gb)
        reason = f"user-requested minimum of {minimum_free_gb:g} GB"
    elif expected_size is not None:
        # Leave room for the .part file, a later unzip, and generated terrain derivatives.
        required = int(expected_size * 3.0 + parse_gb(1.5))
        reason = "download, validation copy, later unzip, and generated derivatives"
    else:
        required = parse_gb(5.0)
        reason = "unknown source file size"

    available = available_bytes_for(target.parent)
    if available < required:
        raise RuntimeError(
            f"Not enough free disk space for {target.name}: "
            f"available {human_size(available)}, need about {human_size(required)} for {reason}. "
            "Free space first or rerun with a smaller section."
        )


def item_record(seed: dict[str, str]) -> dict[str, Any]:
    try:
        item = fetch_json(SCIENCEBASE_ITEM_URL.format(item_id=seed["itemId"]))
    except Exception as cause:  # noqa: BLE001 - cached manifest is enough for downloads.
        cached = cached_item(seed)
        if cached is not None:
            primary_files = cached.get("primaryDemFiles") or []
            cached["localPrimaryPresent"] = [
                existing_file_is_usable(
                    ROOT / path,
                    primary_files[index].get("sizeBytes") if index < len(primary_files) else None,
                )
                for index, path in enumerate(cached.get("localPrimaryPaths", []))
            ]
            cached["metadataRefreshError"] = str(cause)
            return cached
        return fallback_item_record(seed, cause)
    files = [
        {
            "name": normalized_file_name(file),
            "sizeBytes": file.get("size"),
            "sizeHuman": human_size(file.get("size")),
            "url": normalized_file_url(seed["itemId"], file),
            "originalUrl": file_url(file),
            "primaryDemFile": is_primary_dem_file(file),
        }
        for file in item.get("files", [])
    ]
    primary_files = [file for file in files if file["primaryDemFile"]]
    local_primary_paths = [
        str(local_download_path(seed, {"name": file["name"]}).relative_to(ROOT))
        for file in primary_files
        if file.get("name")
    ]

    return {
        "section": seed["section"],
        "datum": seed["datum"],
        "itemId": seed["itemId"],
        "title": item.get("title"),
        "scienceBaseUrl": item.get("link", {}).get("url") or f"https://www.sciencebase.gov/catalog/item/{seed['itemId']}",
        "metadataUrl": seed["metadataUrl"],
        "doi": "https://doi.org/10.5066/P9TJTS8M",
        "dates": item.get("dates", []),
        "bounds": item.get("spatial", {}).get("boundingBox"),
        "lastUpdated": item.get("provenance", {}).get("lastUpdated"),
        "files": files,
        "primaryDemFiles": primary_files,
        "localPrimaryPaths": local_primary_paths,
        "localPrimaryPresent": [
            existing_file_is_usable(ROOT / path, primary_files[index].get("sizeBytes"))
            for index, path in enumerate(local_primary_paths)
        ],
    }


def fallback_item_record(seed: dict[str, Any], cause: Exception) -> dict[str, Any]:
    file = {
        "name": seed["fileName"],
        "sizeBytes": seed["sizeBytes"],
        "sizeHuman": human_size(seed["sizeBytes"]),
        "url": seed["downloadUrl"],
        "originalUrl": seed["downloadUrl"],
        "primaryDemFile": True,
    }
    local_path = str(local_download_path(seed, file).relative_to(ROOT))
    return {
        "section": seed["section"],
        "datum": seed["datum"],
        "itemId": seed["itemId"],
        "title": f"USGS SF Bay 1 m DEM {seed['section']} ({seed['datum']})",
        "scienceBaseUrl": f"https://www.sciencebase.gov/catalog/item/{seed['itemId']}",
        "metadataUrl": seed["metadataUrl"],
        "doi": "https://doi.org/10.5066/P9TJTS8M",
        "dates": [],
        "bounds": seed.get("bounds"),
        "lastUpdated": None,
        "files": [file],
        "primaryDemFiles": [file],
        "localPrimaryPaths": [local_path],
        "localPrimaryPresent": [existing_file_is_usable(ROOT / local_path, seed["sizeBytes"])],
        "metadataRefreshError": str(cause),
        "metadataSource": "built-in last-known ScienceBase metadata",
    }


def selected_records(datum: str, section: str) -> list[dict[str, Any]]:
    records = USGS_SF_BAY_1M_ITEMS
    if datum != "all":
        records = [record for record in records if record["datum"].lower() == datum]
    if section != "all":
        records = [record for record in records if record["section"] == section]
    return records


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "# USGS SF Bay 1 m DEM Acquisition",
        "",
        "This file is generated by `python3 scripts/acquire_usgs_sf_bay_1m_dem.py`.",
        "",
        "The source is the USGS high-resolution 1 m digital elevation model of San Francisco Bay, DOI: https://doi.org/10.5066/P9TJTS8M.",
        "",
        "Plain-English purpose: this is the dataset we want for a much sharper Bay floor. It should improve the parts of the scene inside San Francisco Bay, while the existing CSMP, NOAA BAG, CRM, and CUDEM layers still matter for the Golden Gate, coast, and Farallones.",
        "",
        "## Recommended Import Order",
        "",
        "1. Start with NAVD88, because the paleo waterline model is closer to a land/topobathy elevation question than a nautical chart question.",
        "2. Download central and south first. They are large but manageable zipped GeoTIFF packages.",
        "3. Treat north carefully: the NAVD88 primary GeoTIFF is about 4.4 GB before any local overviews or processed outputs.",
        "4. After import, compare overlaps against CUDEM, DS684, and NOAA BAG patches before trusting exact contour positions.",
        "5. Regenerate `pnpm paleo-coastlines:generate` after a full zip/tif is present; the generator auto-detects local NAVD88 Bay DEM sections and adds them as optional terrain/contour sources.",
        "",
        "## Discovered Files",
        "",
        "| Section | Datum | Primary file | Size | Local target | Bounds |",
        "|---|---|---|---:|---|---|",
    ]
    for item in payload["items"]:
        bounds = item.get("bounds") or {}
        bounds_text = (
            f"{bounds.get('minX')}, {bounds.get('minY')} to {bounds.get('maxX')}, {bounds.get('maxY')}"
            if bounds else "unknown"
        )
        primary_files = item.get("primaryDemFiles") or []
        if not primary_files:
            lines.append(
                f"| {item['section']} | {item['datum']} | none found | n/a | n/a | {bounds_text} |"
            )
            continue
        for index, file in enumerate(primary_files):
            target = item["localPrimaryPaths"][index] if index < len(item["localPrimaryPaths"]) else "n/a"
            lines.append(
                f"| [{item['section']}]({item['scienceBaseUrl']}) | {item['datum']} | "
                f"[{file['name']}]({file['url']}) | {file['sizeHuman']} | `{target}` | {bounds_text} |"
            )

    lines.extend([
        "",
        "## Download Commands",
        "",
        "Refresh manifest only:",
        "",
        "```bash",
        "pnpm paleo-coastlines:usgs-bay-dem",
        "```",
        "",
        "Download one manageable NAVD88 section:",
        "",
        "```bash",
        "python3 scripts/acquire_usgs_sf_bay_1m_dem.py --datum navd88 --section central --download",
        "```",
        "",
        "Download every NAVD88 section only when there is enough free disk space:",
        "",
        "```bash",
        "python3 scripts/acquire_usgs_sf_bay_1m_dem.py --datum navd88 --section all --download",
        "```",
        "",
        "## Caveats",
        "",
        "- The DEM is very detailed, but it is still an interpreted continuous surface. Gaps between survey swaths were interpolated.",
        "- These files describe modern Bay bathymetry, not paleo erosion, sediment, marsh growth, or river-channel migration.",
        "- MLLW is useful for nautical/bathymetric comparison. NAVD88 is the better first fit for our land-plus-waterline simulation.",
        "- ScienceBase may stream these large files slowly or fail mid-transfer. The acquisition script validates file size and rejects HTML/error responses before treating a download as complete.",
        "",
    ])
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))


def existing_file_is_usable(target: Path, expected_size: int | None) -> bool:
    if not target.exists():
        return False
    if expected_size is not None and target.stat().st_size < expected_size * 0.98:
        return False
    with target.open("rb") as handle:
        prefix = handle.read(64).lower()
    return not prefix.startswith(b"<!doctype html") and not prefix.startswith(b"<html")


def download_file(
    url: str,
    target: Path,
    force: bool,
    expected_size: int | None,
    minimum_free_gb: float | None,
) -> None:
    if not force and existing_file_is_usable(target, expected_size):
        print(f"Using existing file: {target.relative_to(ROOT)}")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    require_free_space(target, expected_size, minimum_free_gb)
    part_path = target.with_name(f"{target.name}.part")

    if shutil.which("curl") is not None:
        # ScienceBase S3-backed files may ignore byte-range requests. A normal
        # one-piece transfer has proven more reliable than curl resume here.
        part_path.unlink(missing_ok=True)
        print(f"Downloading {url}")
        print(f"to {target.relative_to(ROOT)}")
        subprocess.run(
            [
                "curl",
                "--location",
                "--fail",
                "--retry",
                "5",
                "--retry-delay",
                "5",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--speed-limit",
                "1",
                "--speed-time",
                "120",
                "--max-time",
                "7200",
                "--output",
                str(part_path),
                url,
            ],
            check=True,
        )
        validate_download(part_path, target, expected_size)
        part_path.replace(target)
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=target.suffix) as tmp:
        tmp_path = Path(tmp.name)

    print(f"Downloading {url}")
    print(f"to {target.relative_to(ROOT)}")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "sf-paleo-coastlines/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, tmp_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        validate_download(tmp_path, target, expected_size)
        tmp_path.replace(target)
    finally:
        tmp_path.unlink(missing_ok=True)


def validate_download(path: Path, target: Path, expected_size: int | None) -> None:
    if expected_size is not None and path.stat().st_size < expected_size * 0.98:
        raise RuntimeError(
            f"Download was too small for {target.name}: "
            f"got {human_size(path.stat().st_size)}, expected about {human_size(expected_size)}"
        )
    with path.open("rb") as handle:
        prefix = handle.read(64).lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        raise RuntimeError(f"Download returned HTML instead of DEM data: {target.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datum", choices=["navd88", "mllw", "all"], default="navd88")
    parser.add_argument("--section", choices=["north", "central", "south", "all"], default="all")
    parser.add_argument("--download", action="store_true", help="Download selected primary DEM files.")
    parser.add_argument("--force", action="store_true", help="Redownload files even when local targets exist.")
    parser.add_argument(
        "--minimum-free-gb",
        type=float,
        default=None,
        help="Require this many GB free before each download. Defaults to a dynamic safety margin based on file size.",
    )
    args = parser.parse_args()

    seeds = selected_records(args.datum, args.section)
    items = [item_record(seed) for seed in seeds]
    payload = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "label": "USGS high-resolution 1 m DEM of San Francisco Bay",
            "doi": "https://doi.org/10.5066/P9TJTS8M",
            "landingPage": "https://www.usgs.gov/data/high-resolution-1-m-digital-elevation-model-dem-san-francisco-bay-california-created-using",
        },
        "selection": {
            "datum": args.datum,
            "section": args.section,
        },
        "items": items,
    }

    write_json(OUT_JSON, payload)
    write_markdown(payload)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")

    if args.download:
        for item in items:
            for file in item["primaryDemFiles"]:
                if not file.get("url") or not file.get("name"):
                    continue
                target = local_download_path(item, file)
                download_file(str(file["url"]), target, args.force, file.get("sizeBytes"), args.minimum_free_gb)
        for item in items:
            item["localPrimaryPresent"] = [(ROOT / path).exists() for path in item["localPrimaryPaths"]]
        write_json(OUT_JSON, payload)
        write_markdown(payload)

    total_bytes = sum(
        int(file.get("sizeBytes") or 0)
        for item in items
        for file in item["primaryDemFiles"]
    )
    print(json.dumps({
        "items": len(items),
        "primaryFileCount": sum(len(item["primaryDemFiles"]) for item in items),
        "selectedPrimarySize": human_size(total_bytes),
        "downloaded": bool(args.download),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
