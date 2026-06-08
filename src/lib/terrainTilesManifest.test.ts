/// <reference types="node" />

import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { TERRAIN_TILESETS } from "../layers/paleoCoastlineLayer";

interface TileManifestEntry {
  sourceId: string;
  minZoom: number;
  maxZoom: number;
  elevationData: string;
  textures: Record<string, string>;
  tileCounts: Record<string, number>;
}

interface TileManifest {
  generated: TileManifestEntry[];
}

const tileFolders: Record<string, string> = {
  elevation: "elevation",
  shadedRelief: "relief",
  depthColor: "color",
  surveyComposite: "composite",
};

function manifestPathToDisk(url: string) {
  const prefix = "/data/paleo-coastlines/";
  if (!url.startsWith(prefix)) throw new Error(`Unexpected tile URL: ${url}`);
  return path.join(process.cwd(), "public", "data", "paleo-coastlines", url.slice(prefix.length));
}

function countPngTiles(root: string, minZoom: number, maxZoom: number) {
  let count = 0;
  for (let zoom = minZoom; zoom <= maxZoom; zoom += 1) {
    const zoomRoot = path.join(root, String(zoom));
    if (!existsSync(zoomRoot)) continue;
    for (const x of readdirSync(zoomRoot)) {
      const xRoot = path.join(zoomRoot, x);
      count += readdirSync(xRoot).filter((file) => file.endsWith(".png")).length;
    }
  }
  return count;
}

describe("terrain tile manifest", () => {
  const manifest = JSON.parse(
    readFileSync(path.join(process.cwd(), "public/data/paleo-coastlines/terrain-tiles/terrain_tiles_manifest.json"), "utf8"),
  ) as TileManifest;

  it("matches the terrain tile URLs used by the viewer", () => {
    for (const entry of manifest.generated) {
      const viewerTileset = TERRAIN_TILESETS[entry.sourceId];
      expect(viewerTileset, entry.sourceId).toBeDefined();
      expect(viewerTileset.elevationData).toBe(entry.elevationData);
      expect(viewerTileset.minZoom).toBe(entry.minZoom);
      expect(viewerTileset.maxZoom).toBe(entry.maxZoom);
      expect(viewerTileset.tileSize).toBe(256);
      expect(viewerTileset.textures).toEqual(entry.textures);
    }
  });

  it("matches tile metadata counts to files on disk", () => {
    for (const entry of manifest.generated) {
      const sourceRoot = manifestPathToDisk(entry.elevationData).split("/elevation/{z}/")[0];

      for (const [kind, expectedCount] of Object.entries(entry.tileCounts)) {
        const folder = tileFolders[kind];
        expect(folder, `${entry.sourceId} ${kind}`).toBeDefined();

        const tileRoot = path.join(sourceRoot, folder);
        expect(existsSync(tileRoot), `${entry.sourceId} ${kind}`).toBe(true);
        expect(countPngTiles(tileRoot, entry.minZoom, entry.maxZoom), `${entry.sourceId} ${kind}`).toBe(expectedCount);
      }
    }
  });
});
