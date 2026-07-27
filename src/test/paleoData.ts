/// <reference types="node" />

import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Test-only reader for the generated browser data tree.
 *
 * `public/data/paleo-coastlines` is about 3.4 GB and lives in Git LFS. CI
 * deliberately builds without pulling it, and a contributor can legitimately
 * work on the app against a remote `VITE_DATA_BASE_URL`. In both cases the
 * files on disk are either absent or LFS pointer stubs, so data-backed suites
 * must skip rather than fail on a parse error.
 *
 * Returns the file contents, or null when the data tree is not materialised.
 */
export function readPaleoData(relativePath: string): string | null {
  const filePath = path.join(process.cwd(), "public", "data", "paleo-coastlines", relativePath);
  let raw: string;
  try {
    raw = readFileSync(filePath, "utf8");
  } catch {
    return null;
  }
  return raw.startsWith("version https://git-lfs.github.com/spec/v1") ? null : raw;
}
