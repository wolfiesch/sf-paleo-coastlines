# Raw Sonar VPS Processing

This note records the first VPS proof that raw multibeam sonar can be turned into map-ready raster grids for the paleo-coastline terrain work.

## What Was Proven

| Item | Result |
|---|---|
| VPS host | `hostinger-devbox` / `/home/wolfie/Projects/sf-paleo-coastlines` |
| Tool path | Docker image `mbari/mbsystem:latest` |
| MB-System tools available in container | `mbinfo`, `mbgrid`, `mblist` |
| Host tools available | `gdalinfo`, `gdal_grid`, `gdalbuildvrt`, `python3`, `curl` |
| Raw format tested | Kongsberg `.all.mb58.gz`, MB-System format `58` |
| Small proof survey | `NA085` |
| Larger probe survey | `NA107` |

Plain English: the VPS can now read the raw sonar files, pull out individual depth points, filter out bad startup navigation, and make GeoTIFF grids.

## NA085 Target Evidence

The weak northwest target center we checked was approximately:

```text
lon -123.4551513
lat   38.0990831
```

Three NA085 files cover that target area:

| Raw file | Covers target center | Full valid points | Preview points used | Bounds | Preview grid |
|---|---:|---:|---:|---|---|
| `0001_20170813_002546_Nautilus.all.mb58.gz` | yes | 1,032,124 | 103,213 | lon `-123.462166` to `-123.430208`, lat `38.084322` to `38.132349` | `na085-0001-linear.sample-grid.tif` |
| `0003_20170813_005510_Nautilus.all.mb58.gz` | yes | 866,854 | 86,686 | lon `-123.456463` to `-123.416771`, lat `38.081189` to `38.133199` | `na085-0003-linear.sample-grid.tif` |
| `0005_20170813_013434_Nautilus.all.mb58.gz` | yes | 1,329,166 | 132,917 | lon `-123.447967` to `-123.410656`, lat `38.072545` to `38.132164` | `na085-0005-linear.sample-grid.tif` |

The preview grids used:

```text
linear:nodata=-9999
thin-every 10
grid-size 384
```

That means the preview keeps every tenth valid sonar point, builds a faster grid, and marks empty cells as no-data instead of pretending empty space is shallow water.

## Important Findings

| Finding | Why it matters |
|---|---|
| The raw processing path works. | We are no longer blocked by missing MB-System tools on the Mac. |
| NA085 has real coverage over the weak northwest cell. | Three files are concrete candidates for improving the map in that area. |
| The first NA107 file is not near San Francisco. | Survey-level overlap is not enough; we need file-level indexing before downloading many large files. |
| The NA107 route scout did not hit current weak cells. | Ten sampled files ran from Southern California to north/west of San Francisco, but none overlapped the current weak-cell boxes. |
| The NA085 candidate is partial. | A masked candidate grid covers 14.29% of the buffered `qg-03-06` rectangle, but the exact weak-cell center remains no-data. |
| The B00012 candidate covers `qg-03-06`. | A strict masked candidate covers 99.77% of the buffered rectangle and samples `-166.0` at the exact weak-cell center. |
| Full-point safe gridding is slow. | A 512 grid with local neighbor search took too long for batch preview work. |
| Fast rectangle gridding is risky. | It can fill empty space with fake values, including `0`, which can look like real shallow water. |
| Thinned linear preview is a good middle path. | It finished quickly and preserved no-data behavior for review. |

## Remote Artifacts

These are on the VPS, not committed to the repo:

```text
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-batch-summary.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0001-linear/na085-0001-linear.sample-report.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0001-linear/na085-0001-linear.sample-grid.tif
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0003-linear/na085-0003-linear.sample-report.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0003-linear/na085-0003-linear.sample-grid.tif
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0005-linear/na085-0005-linear.sample-report.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-0005-linear/na085-0005-linear.sample-grid.tif
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-file-index.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na085-file-index.md
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na107-scout-summary.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-candidates/na085-qg-03-06-scripted/na085-qg-03-06.candidate-summary.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-candidates/na085-qg-03-06-scripted/na085-qg-03-06.masked-512.cog.tif
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-03-06-strict/b00012-qg-03-06-strict.candidate-summary.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-03-06-strict/b00012-qg-03-06-strict.masked-512.cog.tif
```

## Next Step

Use the B00012 candidate as the leading `qg-03-06` terrain patch candidate, then compare it against nearby source layers before promotion.

Suggested order:

1. Keep both NA085 and B00012 out of `best_available_gate_shelf_fusion` until source-quality review is done.
2. Compare B00012 against nearby modern layers and current best-available values around `qg-03-06`.
3. Check B00016 or EW9505 only if they can confirm or improve the B00012 center value.
4. Promote a raw-sonar patch only with a mask and clear source priority rule.
