#!/usr/bin/env python3
"""Regenerate only the best-available fusion terrain and republish its JSON.

The full generate_paleo_coastlines.py main() pipeline re-downloads sources and
rebuilds every terrain asset, which takes hours. When only the fusion canvases
change (bounds, encode range, seam blend, textures), this driver rebuilds the
fusion from the WGS84 work tifs already on disk and rewrites the fusion's
terrain entry in every published JSON that embeds it:

- public/data/paleo-coastlines/paleo_manifest.json
- public/data/paleo-coastlines/slices/*.json
- public/data/paleo-coastlines/paleo_coastlines.json (legacy all-in-one)
- public/data/paleo-coastlines/paleo_coastline_metadata.json (terrainAssets)

Tile regeneration is separate; afterwards run:
  python3 scripts/generate_terrain_tiles.py \
    --source-id best_available_gate_shelf_fusion --clean
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_paleo_coastlines as paleo  # noqa: E402

FUSION_SOURCE_ID = "best_available_gate_shelf_fusion"
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"

# Earlier fusion outputs that the current constants no longer write. The
# canvas PNG names are stable; only renamed side products belong here.
ORPHANED_OUTPUTS = [
    PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.png",
    PALEO_DIR / "terrain" / "best_available_gate_shelf_source_quality.json",
]


def replace_fusion_entry(terrains: list[dict[str, Any]], entry: dict[str, Any]) -> int:
    replaced = 0
    for index, terrain in enumerate(terrains):
        if terrain.get("sourceId") == FUSION_SOURCE_ID:
            terrains[index] = entry
            replaced += 1
    return replaced


def write_compact(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")) + "\n")


def fusion_asset_paths() -> list[str]:
    return [
        str(path.relative_to(ROOT))
        for path in (
            paleo.BEST_AVAILABLE_TERRAIN_ELEVATION_PNG,
            paleo.BEST_AVAILABLE_TERRAIN_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_TERRAIN_RELIEF_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_TERRAIN_COMPOSITE_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_DETAIL_ELEVATION_PNG,
            paleo.BEST_AVAILABLE_DETAIL_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_DETAIL_RELIEF_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_DETAIL_COMPOSITE_TEXTURE_PNG,
            paleo.BEST_AVAILABLE_TERRAIN_SOURCE_TEXTURE_PNG,
        )
    ]


def patch_terrain_assets(assets: list[str]) -> list[str]:
    marker = "terrain/best_available_"
    insert_at = next(
        (index for index, asset in enumerate(assets) if marker in asset),
        len(assets),
    )
    kept = [asset for asset in assets if marker not in asset]
    insert_at = min(insert_at, len(kept))
    return kept[:insert_at] + fusion_asset_paths() + kept[insert_at:]


def main() -> int:
    entry = paleo.generate_best_available_terrain_asset()

    manifest_path = PALEO_DIR / "paleo_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    replaced = sum(
        replace_fusion_entry(item.get("terrains", []), entry)
        for item in manifest["slices"]
    )
    if replaced == 0:
        raise SystemExit(f"{FUSION_SOURCE_ID} was not found in {manifest_path}")
    write_compact(manifest_path, manifest)
    print(f"Patched {replaced} fusion entries in {manifest_path.relative_to(ROOT)}")

    for slice_path in sorted((PALEO_DIR / "slices").glob("*.json")):
        slice_payload = json.loads(slice_path.read_text())
        if replace_fusion_entry(slice_payload.get("terrains", []), entry):
            write_compact(slice_path, slice_payload)
            print(f"Patched {slice_path.relative_to(ROOT)}")

    legacy_path = PALEO_DIR / "paleo_coastlines.json"
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text())
        replaced = sum(
            replace_fusion_entry(item.get("terrains", []), entry) for item in legacy
        )
        if replaced:
            write_compact(legacy_path, legacy)
            print(f"Patched {replaced} fusion entries in {legacy_path.relative_to(ROOT)}")

    metadata_path = PALEO_DIR / "paleo_coastline_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["terrainAssets"] = patch_terrain_assets(metadata["terrainAssets"])
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Patched terrainAssets in {metadata_path.relative_to(ROOT)}")

    for orphan in ORPHANED_OUTPUTS:
        if orphan.exists():
            orphan.unlink()
            print(f"Removed orphaned {orphan.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
