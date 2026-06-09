#!/usr/bin/env python3
"""Audit where terrain detail can be limited by browser display resolution.

Source data can be 1 m or 2 m, but the browser does not always draw every
source pixel. This report compares each important terrain source's stated
source resolution with the encoded PNG size used by the app.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
MANIFEST_JSON = PALEO_DIR / "paleo_manifest.json"
TERRAIN_TILE_ROOT = PALEO_DIR / "terrain-tiles"
OUT_JSON = PALEO_DIR / "terrain_display_resolution_audit.json"
OUT_MD = ROOT / "docs" / "terrain-display-resolution-audit.md"

KEY_SOURCE_IDS = {
    "best_available_gate_shelf_fusion",
    "usgs_2023_sf_lidar_dem",
    "usgs_coned_sf_2m_gate_shelf",
    "usgs_coned_sf_2m_farallon_shelf",
    "usgs_coned_sf_2m_south_bay_edge",
    "usgs_sf_bay_1m_north_navd88_overview",
    "usgs_sf_bay_1m_central_navd88",
    "usgs_sf_bay_1m_south_navd88",
}


@dataclass(frozen=True)
class DisplayAuditRow:
    source_id: str
    label: str
    source_resolution_m: float | None
    encoded_image_size: tuple[int, int]
    approx_encoded_pixel_m: float
    tile_zoom_range: str
    likely_limit: str
    plain_english_read: str
    next_action: str


def asset_path(url: str) -> Path:
    prefix = "/data/paleo-coastlines/"
    if not url.startswith(prefix):
        raise SystemExit(f"Unexpected paleo asset URL: {url}")
    return PALEO_DIR / url.removeprefix(prefix)


def meters_between(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    radius_m = 6_371_008.8
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    d_phi = math.radians(lat_b - lat_a)
    d_lambda = math.radians(lon_b - lon_a)
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_m * math.asin(min(1, math.sqrt(h)))


def approx_pixel_m(bounds: list[float], width: int, height: int) -> float:
    west, south, east, north = [float(value) for value in bounds]
    mid_lat = (south + north) / 2
    mid_lon = (west + east) / 2
    width_m = meters_between(west, mid_lat, east, mid_lat)
    height_m = meters_between(mid_lon, south, mid_lon, north)
    return max(width_m / width, height_m / height)


def tile_zoom_range(source_id: str) -> str:
    path = TERRAIN_TILE_ROOT / source_id / "tileset.json"
    if not path.exists():
        return "not tiled"
    payload = json.loads(path.read_text())
    return f"z{payload.get('minZoom')}-z{payload.get('maxZoom')}"


def display_limit(row: dict[str, Any], encoded_pixel_m: float) -> tuple[str, str, str]:
    source_resolution = row.get("resolutionMeters")
    source_id = str(row["sourceId"])

    if source_resolution is None:
        return (
            "source is variable or broad",
            "The source does not expose a simple meter-per-pixel number, so visual softness is probably about the source class or local terrain shape.",
            "Use the source-quality layer first; chase better data only where this is broad support.",
        )

    source_resolution = float(source_resolution)
    ratio = encoded_pixel_m / source_resolution if source_resolution else 0

    if ratio >= 6:
        return (
            "browser image is much coarser than source",
            f"The source is about {source_resolution:g} m, but the encoded browser image is about {encoded_pixel_m:.1f} m per pixel. Fine source detail is being compressed.",
            "Use a smaller focused terrain image or add higher-resolution tiles for this source.",
        )
    if ratio >= 2.5:
        return (
            "browser image is somewhat coarser than source",
            f"The source is about {source_resolution:g} m, while the encoded browser image is about {encoded_pixel_m:.1f} m per pixel. Some detail is lost, but big landforms should remain.",
            "Compare Sharp smoothing and single-source mode before increasing tile/image resolution.",
        )
    if source_id == "best_available_gate_shelf_fusion":
        return (
            "fusion layer is intentionally broad",
            "This layer is a continuity surface for the full Gate-to-Farallones view, not the place to preserve every 1 m or 2 m source pixel.",
            "Use focused overlays or source mode when judging small local details.",
        )
    return (
        "display resolution is close to source",
        f"The encoded browser image is about {encoded_pixel_m:.1f} m per pixel, close enough that source data or real flatness is probably the main limit.",
        "If it still looks soft, compare Smooth vs Sharp and inspect the raw source shape.",
    )


def terrain_rows() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST_JSON.read_text())
    terrains = manifest["slices"][0]["terrains"]
    return [terrain for terrain in terrains if terrain["sourceId"] in KEY_SOURCE_IDS]


def audit() -> list[DisplayAuditRow]:
    rows: list[DisplayAuditRow] = []
    for terrain in terrain_rows():
        image_path = asset_path(terrain["elevationData"])
        image = Image.open(image_path)
        encoded_pixel = approx_pixel_m(terrain["bounds"], image.width, image.height)
        likely_limit, read, action = display_limit(terrain, encoded_pixel)
        rows.append(DisplayAuditRow(
            source_id=terrain["sourceId"],
            label=terrain["sourceLabel"],
            source_resolution_m=terrain.get("resolutionMeters"),
            encoded_image_size=(image.width, image.height),
            approx_encoded_pixel_m=round(encoded_pixel, 2),
            tile_zoom_range=tile_zoom_range(terrain["sourceId"]),
            likely_limit=likely_limit,
            plain_english_read=read,
            next_action=action,
        ))
    rows.sort(key=lambda row: (
        row.likely_limit != "browser image is much coarser than source",
        row.source_id,
    ))
    return rows


def write_outputs(rows: list[DisplayAuditRow]) -> None:
    payload = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "plainEnglishPurpose": (
            "Compare source resolution with the encoded browser terrain image size "
            "so blurry areas can be separated into data limits versus display limits."
        ),
        "renderingNotes": [
            "Ultra terrain uses tiled PNGs where available.",
            "The app's Smooth terrain mode applies two small height-smoothing passes.",
            "Sharp mode skips that smoothing and is better for diagnosis.",
        ],
        "sources": [row.__dict__ for row in rows],
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Terrain Display Resolution Audit",
        "",
        "This file is generated by `python3 scripts/audit_terrain_display_resolution.py`.",
        "",
        "Plain-English purpose: separate missing-data blur from browser-display blur.",
        "",
        "## Key Findings",
        "",
        "| Source | Source res | Browser image | Approx browser pixel | Tiles | Likely limit | Next action |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        source_res = "variable" if row.source_resolution_m is None else f"{row.source_resolution_m:g} m"
        image_size = f"{row.encoded_image_size[0]} x {row.encoded_image_size[1]}"
        lines.append(
            f"| {row.label} | {source_res} | {image_size} | {row.approx_encoded_pixel_m:g} m | "
            f"{row.tile_zoom_range} | {row.likely_limit} | {row.next_action} |"
        )

    lines.extend([
        "",
        "## How To Use This",
        "",
        "- If the source is detailed but the browser pixel is much larger, the display path is compressing detail.",
        "- If the source and browser pixel are close, the limiting factor is probably the actual source shape, the local flatness, or smoothing.",
        "- For visual diagnosis, first compare `Smoothing: Sharp`, `Source mode: Source`, and the relevant focused source before downloading more data.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    rows = audit()
    write_outputs(rows)
    for row in rows:
        print(f"{row.source_id}: {row.approx_encoded_pixel_m:g} m browser pixel, {row.likely_limit}")


if __name__ == "__main__":
    main()
