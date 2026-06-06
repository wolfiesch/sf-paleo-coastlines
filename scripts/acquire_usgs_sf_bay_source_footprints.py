#!/usr/bin/env python3
"""Acquire USGS source-footprint polygons for the 1 m SF Bay DEM."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "paleo-coastlines" / "raw" / "usgs-sf-bay-source-footprints"
WORK_DIR = ROOT / "data" / "paleo-coastlines" / "work" / "usgs-sf-bay-source-footprints"
PUBLIC_DIR = ROOT / "public" / "data" / "paleo-coastlines"
OUT_GEOJSON = PUBLIC_DIR / "usgs_sf_bay_source_footprints.geojson"
OUT_MANIFEST = PUBLIC_DIR / "usgs_sf_bay_source_footprints_manifest.json"
OUT_DOC = ROOT / "docs" / "usgs-sf-bay-source-footprints.md"

SECTIONS = [
    {
        "id": "north",
        "label": "North Bay",
        "itemId": "5e169180e4b0ecf25c57fb1a",
        "zipName": "NorthSFBay_DEM_DataSources.zip",
        "shapefileStem": "NorthSFBay_DEM_DataSources",
        "catalogUrl": "https://www.sciencebase.gov/catalog/item/5e169180e4b0ecf25c57fb1a",
    },
    {
        "id": "central",
        "label": "Central Bay",
        "itemId": "607df19dd34e8564d67e3af3",
        "zipName": "CentralSFBay_DEM_DataSources.zip",
        "shapefileStem": "CentralSFBay_DEM_DataSources",
        "catalogUrl": "https://www.sciencebase.gov/catalog/item/607df19dd34e8564d67e3af3",
    },
    {
        "id": "south",
        "label": "South Bay",
        "itemId": "607df1b6d34e8564d67e3af6",
        "zipName": "SouthSFBay_DEM_DataSources.zip",
        "shapefileStem": "SouthSFBay_DEM_DataSources",
        "catalogUrl": "https://www.sciencebase.gov/catalog/item/607df1b6d34e8564d67e3af6",
    },
]


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def fetch_json(url: str) -> dict[str, Any] | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "sf-paleo-coastlines/0.1"})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def download_url(item_id: str) -> str:
    return f"https://www.sciencebase.gov/catalog/file/get/{item_id}"


def download(section: dict[str, str], force: bool) -> Path:
    target_dir = RAW_DIR / section["id"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / section["zipName"]
    if target.exists() and not force:
        return target

    part = target.with_suffix(target.suffix + ".part")
    part.unlink(missing_ok=True)
    command = [
        "curl",
        "-L",
        "--fail",
        "--connect-timeout",
        "20",
        "--max-time",
        "180",
        "--retry",
        "3",
        "--retry-delay",
        "4",
        "-o",
        str(part),
        download_url(section["itemId"]),
    ]
    run(command)
    if part.stat().st_size < 1024:
        raise RuntimeError(f"{section['label']} source-footprint download was unexpectedly tiny")
    part.replace(target)
    return target


def extract(zip_path: Path, section: dict[str, str]) -> Path:
    extract_dir = WORK_DIR / section["id"]
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    return extract_dir


def shapefile_path(extract_dir: Path, section: dict[str, str]) -> Path:
    stem = section["shapefileStem"]
    candidates = list(extract_dir.glob(f"**/{stem}.shp"))
    if not candidates:
        raise RuntimeError(f"{section['label']} zip did not contain {stem}.shp")
    return candidates[0]


def validate_shapefile(path: Path) -> tuple[bool, str]:
    required = [path, path.with_suffix(".shx"), path.with_suffix(".dbf"), path.with_suffix(".prj")]
    missing = [item.name for item in required if not item.exists() or item.stat().st_size == 0]
    if missing:
        return False, f"missing or empty shapefile sidecars: {', '.join(missing)}"

    result = run(["ogrinfo", "-al", "-so", str(path)], check=False)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, "valid"


def strip_z(coordinates: Any) -> Any:
    if isinstance(coordinates, list) and coordinates and all(isinstance(value, (int, float)) for value in coordinates):
        return coordinates[:2]
    if isinstance(coordinates, list):
        return [strip_z(value) for value in coordinates]
    return coordinates


def normalize_feature(feature: dict[str, Any], section: dict[str, str], index: int) -> dict[str, Any]:
    props = feature.get("properties", {})
    survey = str(props.get("Survey") or "unknown")
    year = props.get("year")
    sensor_type = str(props.get("sensor_typ") or "unknown")
    interpolation = str(props.get("interp_req") or "unknown")
    resolution = str(props.get("resolution") or "unknown")
    agency = str(props.get("Agency") or "unknown")
    datum = str(props.get("datum") or "unknown")
    area_sq_m = props.get("Shape_Area")

    quality_parts = []
    if "multi" in sensor_type.lower() or "interferometric" in sensor_type.lower():
        quality_parts.append("sound-survey")
    if resolution.lower() == "1 m":
        quality_parts.append("1m")
    if interpolation.lower() == "no":
        quality_parts.append("direct")
    quality_class = " ".join(quality_parts) if quality_parts else "lower-detail"

    geometry = feature.get("geometry") or {}
    return {
        "type": "Feature",
        "id": f"{section['id']}-{index:03d}-{survey}",
        "properties": {
            "source_section": section["label"],
            "section_id": section["id"],
            "agency": agency,
            "survey": survey,
            "year": int(year) if isinstance(year, (int, float)) else None,
            "resolution": resolution,
            "datum": datum,
            "interpolation": interpolation,
            "sensor_type": sensor_type,
            "source_location": props.get("location") or "",
            "area_sq_m": round(float(area_sq_m), 1) if isinstance(area_sq_m, (int, float)) else None,
            "quality_class": quality_class,
            "sciencebase_item_id": section["itemId"],
            "sciencebase_item_url": section["catalogUrl"],
        },
        "geometry": {
            "type": geometry.get("type"),
            "coordinates": strip_z(geometry.get("coordinates")),
        },
    }


def convert_to_geojson(path: Path, section: dict[str, str]) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_geojson = Path(tmpdir) / f"{section['id']}.geojson"
        run([
            "ogr2ogr",
            "-f",
            "GeoJSON",
            str(temp_geojson),
            str(path),
            "-t_srs",
            "EPSG:4326",
            "-lco",
            "COORDINATE_PRECISION=6",
        ])
        payload = json.loads(temp_geojson.read_text())
    return [normalize_feature(feature, section, index) for index, feature in enumerate(payload.get("features", []), start=1)]


def write_doc(manifest: dict[str, Any]) -> None:
    lines = [
        "# USGS SF Bay 1 m DEM Source Footprints",
        "",
        "This file is generated by `python3 scripts/acquire_usgs_sf_bay_source_footprints.py`.",
        "",
        "These polygons are not new terrain heights. They show which original surveys were used by USGS to build the 1 m San Francisco Bay DEM.",
        "In plain English: this layer tells us where the Bay DEM is based on multibeam, interferometric, or single-beam source surveys, which year the survey came from, which datum it used, and whether interpolation was needed.",
        "",
        f"- Browser GeoJSON: `{OUT_GEOJSON.relative_to(ROOT)}`",
        f"- Browser manifest: `{OUT_MANIFEST.relative_to(ROOT)}`",
        "",
        "## Section Status",
        "",
        "| Section | Status | Features | Note |",
        "|---|---:|---:|---|",
    ]
    for section in manifest["sections"]:
        lines.append(
            f"| [{section['label']}]({section['catalogUrl']}) | {section['status']} | {section['featureCount']} | {section['note']} |"
        )
    lines.extend([
        "",
        "## Caveats",
        "",
        "- The source-footprint layer explains data provenance. It does not add 1 m terrain heights by itself.",
        "- North and South Bay packages have recently returned incomplete shapefile sidecars from ScienceBase in this environment. The script records that problem and will include them automatically once valid packages are available.",
        "- The Central Bay source layer is currently the usable checked-in browser overlay.",
        "",
    ])
    OUT_DOC.write_text("\n".join(lines))


def build(force: bool) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    features: list[dict[str, Any]] = []
    section_results = []

    for section in SECTIONS:
        item_json = fetch_json(f"https://www.sciencebase.gov/catalog/item/{section['itemId']}?format=json")
        title = item_json.get("title") if item_json else f"{section['label']} source footprints"
        try:
            zip_path = download(section, force=force)
            extract_dir = extract(zip_path, section)
            shp = shapefile_path(extract_dir, section)
            valid, note = validate_shapefile(shp)
            if not valid:
                raise RuntimeError(note)
            section_features = convert_to_geojson(shp, section)
            features.extend(section_features)
            section_results.append({
                "id": section["id"],
                "label": section["label"],
                "status": "included",
                "featureCount": len(section_features),
                "catalogUrl": section["catalogUrl"],
                "downloadUrl": download_url(section["itemId"]),
                "title": title,
                "note": "valid shapefile converted to WGS84 GeoJSON",
            })
        except Exception as cause:
            section_results.append({
                "id": section["id"],
                "label": section["label"],
                "status": "skipped",
                "featureCount": 0,
                "catalogUrl": section["catalogUrl"],
                "downloadUrl": download_url(section["itemId"]),
                "title": title,
                "note": str(cause).replace("\n", " ")[:260],
            })

    payload = {
        "type": "FeatureCollection",
        "name": "USGS SF Bay 1 m DEM source footprints",
        "features": features,
    }
    OUT_GEOJSON.write_text(json.dumps(payload, separators=(",", ":")) + "\n")

    manifest = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "USGS ScienceBase source-footprint items for the high-resolution 1 m San Francisco Bay DEM",
        "browserGeoJsonUrl": "/data/paleo-coastlines/usgs_sf_bay_source_footprints.geojson",
        "featureCount": len(features),
        "sections": section_results,
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    write_doc(manifest)

    print(f"Wrote {OUT_GEOJSON.relative_to(ROOT)} with {len(features)} features")
    print(f"Wrote {OUT_MANIFEST.relative_to(ROOT)}")
    print(f"Wrote {OUT_DOC.relative_to(ROOT)}")

    if not features:
        print("No valid source-footprint shapefiles were available.", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-download source packages even if they already exist locally")
    args = parser.parse_args()
    build(force=args.force)


if __name__ == "__main__":
    main()
