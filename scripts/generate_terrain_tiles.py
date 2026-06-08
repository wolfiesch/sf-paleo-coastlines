#!/usr/bin/env python3
"""Generate browser-ready terrain tiles from existing encoded terrain PNGs.

The app's single terrain PNGs are already RGB-encoded for deck.gl. This script
cuts those images into slippy-map z/x/y tiles without changing the RGB height
values for elevation tiles.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_MANIFEST = Path("public/data/paleo-coastlines/paleo_manifest.json")
DEFAULT_OUTPUT_ROOT = Path("public/data/paleo-coastlines/terrain-tiles")
TERRAIN_ROOT = Path("public/data/paleo-coastlines/terrain")
TILE_SIZE = 256


@dataclass(frozen=True)
class TerrainTileset:
  source_id: str
  min_zoom: int
  max_zoom: int


DEFAULT_TILESETS = [
  TerrainTileset("usgs_2023_sf_lidar_dem", 12, 16),
  TerrainTileset("usgs_coned_sf_2m_gate_shelf", 12, 15),
]


def lon_to_tile_x(lon: float, zoom: int) -> float:
  return (lon + 180.0) / 360.0 * (2**zoom)


def lat_to_tile_y(lat: float, zoom: int) -> float:
  lat_rad = math.radians(lat)
  return (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * (2**zoom)


def tile_x_to_lon(x: int, zoom: int) -> float:
  return x / (2**zoom) * 360.0 - 180.0


def tile_y_to_lat(y: int, zoom: int) -> float:
  mercator_y = math.pi * (1.0 - 2.0 * y / (2**zoom))
  return math.degrees(math.atan(math.sinh(mercator_y)))


def load_terrain(manifest_path: Path, source_id: str) -> dict:
  manifest = json.loads(manifest_path.read_text())
  for terrain in manifest["slices"][0]["terrains"]:
    if terrain["sourceId"] == source_id:
      return terrain
  raise SystemExit(f"Terrain source not found in manifest: {source_id}")


def terrain_asset_path(asset_url: str) -> Path:
  prefix = "/data/paleo-coastlines/terrain/"
  if not asset_url.startswith(prefix):
    raise SystemExit(f"Unexpected terrain asset path: {asset_url}")
  return TERRAIN_ROOT / asset_url.removeprefix(prefix)


def tile_range(bounds: list[float], zoom: int) -> tuple[range, range]:
  west, south, east, north = bounds
  x_min = math.floor(lon_to_tile_x(west, zoom))
  x_max = math.floor(lon_to_tile_x(east, zoom) - 1e-9)
  y_min = math.floor(lat_to_tile_y(north, zoom))
  y_max = math.floor(lat_to_tile_y(south, zoom) - 1e-9)
  return range(x_min, x_max + 1), range(y_min, y_max + 1)


def tile_sample_grid(bounds: list[float], zoom: int, x: int, y: int) -> tuple[np.ndarray, np.ndarray]:
  west, south, east, north = bounds
  tile_west = tile_x_to_lon(x, zoom)
  tile_east = tile_x_to_lon(x + 1, zoom)

  columns = np.arange(TILE_SIZE, dtype=np.float64) + 0.5
  rows = np.arange(TILE_SIZE, dtype=np.float64) + 0.5

  lon = tile_west + (tile_east - tile_west) * (columns / TILE_SIZE)
  mercator_y = y + rows / TILE_SIZE
  lat = np.array([tile_y_to_lat(float(value), zoom) for value in mercator_y], dtype=np.float64)

  src_x = (lon - west) / (east - west)
  src_y = (north - lat) / (north - south)
  return src_x, src_y


def nearest_tile(image: np.ndarray, src_x: np.ndarray, src_y: np.ndarray) -> np.ndarray:
  height, width = image.shape[:2]
  x_index = np.clip(np.rint(src_x * (width - 1)).astype(np.int64), 0, width - 1)
  y_index = np.clip(np.rint(src_y * (height - 1)).astype(np.int64), 0, height - 1)
  return image[y_index[:, None], x_index[None, :]]


def bilinear_tile(image: np.ndarray, src_x: np.ndarray, src_y: np.ndarray) -> np.ndarray:
  height, width = image.shape[:2]
  x_float = np.clip(src_x * (width - 1), 0, width - 1)
  y_float = np.clip(src_y * (height - 1), 0, height - 1)

  x0 = np.floor(x_float).astype(np.int64)
  y0 = np.floor(y_float).astype(np.int64)
  x1 = np.clip(x0 + 1, 0, width - 1)
  y1 = np.clip(y0 + 1, 0, height - 1)

  wx = (x_float - x0)[None, :, None]
  wy = (y_float - y0)[:, None, None]

  top = image[y0[:, None], x0[None, :]] * (1 - wx) + image[y0[:, None], x1[None, :]] * wx
  bottom = image[y1[:, None], x0[None, :]] * (1 - wx) + image[y1[:, None], x1[None, :]] * wx
  tile = top * (1 - wy) + bottom * wy
  return np.clip(tile, 0, 255).astype(np.uint8)


def write_tiles(
  image_path: Path,
  bounds: list[float],
  output_dir: Path,
  min_zoom: int,
  max_zoom: int,
  resampling: str,
) -> int:
  image = np.asarray(Image.open(image_path))
  written = 0

  for zoom in range(min_zoom, max_zoom + 1):
    x_range, y_range = tile_range(bounds, zoom)
    for x in x_range:
      for y in y_range:
        src_x, src_y = tile_sample_grid(bounds, zoom, x, y)
        if resampling == "nearest":
          tile = nearest_tile(image, src_x, src_y)
        else:
          tile = bilinear_tile(image, src_x, src_y)

        tile_path = output_dir / str(zoom) / str(x) / f"{y}.png"
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(tile).save(tile_path, optimize=True)
        written += 1

  return written


def generate_tileset(terrain: dict, output_root: Path, min_zoom: int, max_zoom: int, clean: bool) -> dict:
  source_id = terrain["sourceId"]
  source_output = output_root / source_id
  if clean and source_output.exists():
    shutil.rmtree(source_output)

  elevation_output = source_output / "elevation"
  relief_output = source_output / "relief"
  elevation_path = terrain_asset_path(terrain["elevationData"])
  relief_path = terrain_asset_path(terrain["textures"]["shadedRelief"])

  elevation_count = write_tiles(elevation_path, terrain["bounds"], elevation_output, min_zoom, max_zoom, "nearest")
  relief_count = write_tiles(relief_path, terrain["bounds"], relief_output, min_zoom, max_zoom, "bilinear")

  metadata = {
    "sourceId": source_id,
    "bounds": terrain["bounds"],
    "minZoom": min_zoom,
    "maxZoom": max_zoom,
    "tileSize": TILE_SIZE,
    "elevationData": f"/data/paleo-coastlines/terrain-tiles/{source_id}/elevation/{{z}}/{{x}}/{{y}}.png",
    "textures": {
      "shadedRelief": f"/data/paleo-coastlines/terrain-tiles/{source_id}/relief/{{z}}/{{x}}/{{y}}.png",
    },
    "tileCounts": {
      "elevation": elevation_count,
      "shadedRelief": relief_count,
    },
  }
  (source_output / "tileset.json").write_text(json.dumps(metadata, indent=2) + "\n")
  return metadata


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Generate deck.gl terrain z/x/y tiles from existing terrain PNGs.")
  parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
  parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
  parser.add_argument("--source-id", action="append", help="Terrain source id to tile. Defaults to the SF LiDAR source.")
  parser.add_argument("--min-zoom", type=int, default=None)
  parser.add_argument("--max-zoom", type=int, default=None)
  parser.add_argument("--clean", action="store_true", help="Delete the selected source's tile folder before writing.")
  return parser.parse_args()


def main() -> None:
  args = parse_args()
  requested = args.source_id or [item.source_id for item in DEFAULT_TILESETS]
  defaults = {item.source_id: item for item in DEFAULT_TILESETS}
  generated = []

  for source_id in requested:
    default = defaults.get(source_id, TerrainTileset(source_id, 12, 15))
    min_zoom = args.min_zoom if args.min_zoom is not None else default.min_zoom
    max_zoom = args.max_zoom if args.max_zoom is not None else default.max_zoom
    terrain = load_terrain(args.manifest, source_id)
    generated.append(generate_tileset(terrain, args.output_root, min_zoom, max_zoom, args.clean))

  args.output_root.mkdir(parents=True, exist_ok=True)
  all_tilesets = [
    json.loads(path.read_text())
    for path in sorted(args.output_root.glob("*/tileset.json"))
  ]
  manifest = {
    "generated": all_tilesets,
  }
  (args.output_root / "terrain_tiles_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

  for item in generated:
    total = sum(item["tileCounts"].values())
    print(f"{item['sourceId']}: wrote {total} tiles at z{item['minZoom']}-z{item['maxZoom']}")


if __name__ == "__main__":
  main()
