#!/usr/bin/env python3
"""Generate browser-ready terrain tiles from existing encoded terrain PNGs.

The app's single terrain PNGs are already RGB-encoded for deck.gl. This script
cuts those images into slippy-map z/x/y tiles without changing the RGB height
values for elevation tiles.
"""

from __future__ import annotations

import argparse
import os
import json
import math
import shutil
from concurrent.futures import ThreadPoolExecutor
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
  TerrainTileset("best_available_gate_shelf_fusion", 8, 15),
  TerrainTileset("usgs_2023_sf_lidar_dem", 8, 16),
  TerrainTileset("usgs_coned_sf_2m_gate_shelf", 8, 15),
  TerrainTileset("usgs_coned_sf_2m_farallon_shelf", 8, 15),
  TerrainTileset("usgs_coned_sf_2m_south_bay_edge", 8, 14),
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


def tile_jobs(bounds: list[float], min_zoom: int, max_zoom: int) -> list[tuple[int, int, int]]:
  jobs = []
  for zoom in range(min_zoom, max_zoom + 1):
    x_range, y_range = tile_range(bounds, zoom)
    for x in x_range:
      for y in y_range:
        jobs.append((zoom, x, y))
  return jobs


def zoom_pixel_span(bounds: list[float], zoom: int) -> tuple[float, float]:
  west, south, east, north = bounds
  px_w = (lon_to_tile_x(east, zoom) - lon_to_tile_x(west, zoom)) * TILE_SIZE
  px_h = (lat_to_tile_y(south, zoom) - lat_to_tile_y(north, zoom)) * TILE_SIZE
  return px_w, px_h


def box_filtered_elevation(image: np.ndarray, target: tuple[int, int]) -> np.ndarray:
  """Downsample RGB-encoded elevation by averaging in decoded 24-bit code space.

  Height is linear in the packed code, so averaging codes averages heights.
  Averaging the R/G/B bytes independently and re-rounding would corrupt
  heights (a half-step rounding error in R alone is 1/512 of the full range).
  Codes stay below 2**24, so float32 represents them exactly.
  """
  rgb = image[:, :, :3]
  codes = rgb[:, :, 0].astype(np.float32) * 65536 + rgb[:, :, 1].astype(np.float32) * 256 + rgb[:, :, 2].astype(np.float32)
  resized = np.asarray(Image.fromarray(codes, mode="F").resize(target, Image.Resampling.BOX))
  packed = np.clip(np.rint(resized), 0, 16_777_215).astype(np.uint32)
  filtered = np.zeros((target[1], target[0], 3), dtype=np.uint8)
  filtered[:, :, 0] = ((packed >> 16) & 255).astype(np.uint8)
  filtered[:, :, 1] = ((packed >> 8) & 255).astype(np.uint8)
  filtered[:, :, 2] = (packed & 255).astype(np.uint8)
  return filtered


def write_tiles(
  image_path: Path,
  bounds: list[float],
  output_dir: Path,
  min_zoom: int,
  max_zoom: int,
  resampling: str,
  skip_existing: bool,
  workers: int,
) -> int:
  source_image = Image.open(image_path)
  image = np.asarray(source_image)
  jobs = tile_jobs(bounds, min_zoom, max_zoom)

  # Low zooms downsample the source by large factors, and point sampling there
  # aliases: textures turn into moire and elevation picks up building-scale
  # height noise that the relief shading amplifies into patchwork. Prefilter
  # per zoom with a box filter; elevation averages in decoded code space.
  images_by_zoom: dict[int, np.ndarray] = {}
  for zoom in range(min_zoom, max_zoom + 1):
    px_w, px_h = zoom_pixel_span(bounds, zoom)
    scale = min(image.shape[1] / max(px_w, 1.0), image.shape[0] / max(px_h, 1.0))
    if scale > 2.0:
      target = (max(int(round(px_w * 2)), 1), max(int(round(px_h * 2)), 1))
      if resampling == "bilinear":
        images_by_zoom[zoom] = np.asarray(source_image.resize(target, Image.Resampling.BOX))
      else:
        images_by_zoom[zoom] = box_filtered_elevation(image, target)
      continue
    images_by_zoom[zoom] = image

  def write_one(job: tuple[int, int, int]) -> int:
    zoom, x, y = job
    tile_path = output_dir / str(zoom) / str(x) / f"{y}.png"
    if skip_existing and tile_path.exists():
      return 0

    zoom_image = images_by_zoom[zoom]
    src_x, src_y = tile_sample_grid(bounds, zoom, x, y)
    if resampling == "nearest":
      tile = nearest_tile(zoom_image, src_x, src_y)
    else:
      tile = bilinear_tile(zoom_image, src_x, src_y)

    tile_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(tile).save(tile_path, optimize=True)
    return 1

  if workers <= 1 or len(jobs) <= 1:
    return sum(write_one(job) for job in jobs)

  with ThreadPoolExecutor(max_workers=workers) as pool:
    return sum(pool.map(write_one, jobs))


def count_tiles(output_dir: Path, min_zoom: int, max_zoom: int) -> int:
  total = 0
  for zoom in range(min_zoom, max_zoom + 1):
    zoom_dir = output_dir / str(zoom)
    if zoom_dir.exists():
      total += sum(1 for _ in zoom_dir.glob("*/*.png"))
  return total


def generate_tileset(
  terrain: dict,
  output_root: Path,
  min_zoom: int,
  max_zoom: int,
  clean: bool,
  skip_existing: bool,
  workers: int,
) -> dict:
  source_id = terrain["sourceId"]
  source_output = output_root / source_id
  if clean and source_output.exists():
    shutil.rmtree(source_output)

  elevation_output = source_output / "elevation"
  elevation_path = terrain_asset_path(terrain["elevationData"])
  texture_sources = {
    "shadedRelief": ("relief", terrain["textures"].get("shadedRelief")),
    "depthColor": ("color", terrain["textures"].get("depthColor")),
    "surveyComposite": ("composite", terrain["textures"].get("surveyComposite")),
  }

  existing_metadata_path = source_output / "tileset.json"
  existing_metadata = json.loads(existing_metadata_path.read_text()) if existing_metadata_path.exists() else {}
  metadata_min_zoom = min(min_zoom, int(existing_metadata.get("minZoom", min_zoom)))
  metadata_max_zoom = max(max_zoom, int(existing_metadata.get("maxZoom", max_zoom)))

  write_tiles(elevation_path, terrain["bounds"], elevation_output, min_zoom, max_zoom, "nearest", skip_existing, workers)
  elevation_count = count_tiles(elevation_output, metadata_min_zoom, metadata_max_zoom)
  tiled_textures = {}
  texture_counts = {}

  for texture_name, (folder_name, texture_url) in texture_sources.items():
    if not texture_url:
      continue
    texture_output = source_output / folder_name
    texture_path = terrain_asset_path(texture_url)
    write_tiles(texture_path, terrain["bounds"], texture_output, min_zoom, max_zoom, "bilinear", skip_existing, workers)
    tiled_textures[texture_name] = f"/data/paleo-coastlines/terrain-tiles/{source_id}/{folder_name}/{{z}}/{{x}}/{{y}}.png"
    texture_counts[texture_name] = count_tiles(texture_output, metadata_min_zoom, metadata_max_zoom)

  metadata = {
    "sourceId": source_id,
    "bounds": terrain["bounds"],
    "minZoom": metadata_min_zoom,
    "maxZoom": metadata_max_zoom,
    "tileSize": TILE_SIZE,
    "elevationData": f"/data/paleo-coastlines/terrain-tiles/{source_id}/elevation/{{z}}/{{x}}/{{y}}.png",
    "textures": tiled_textures,
    "tileCounts": {
      "elevation": elevation_count,
      **texture_counts,
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
  parser.add_argument("--skip-existing", action="store_true", help="Leave existing tile PNGs in place and write only missing tiles.")
  parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1), help="Parallel tile writers. Use 1 for the old serial behavior.")
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
    generated.append(generate_tileset(terrain, args.output_root, min_zoom, max_zoom, args.clean, args.skip_existing and not args.clean, args.workers))

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
    action = "has" if args.skip_existing and not args.clean else "wrote"
    print(f"{item['sourceId']}: {action} {total} tiles at z{item['minZoom']}-z{item['maxZoom']}")


if __name__ == "__main__":
  main()
