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

Two NA085 files cover that target area:

| Raw file | Covers target center | Full valid points | Preview points used | Bounds | Preview grid |
|---|---:|---:|---:|---|---|
| `0001_20170813_002546_Nautilus.all.mb58.gz` | yes | 1,032,124 | 103,213 | lon `-123.462166` to `-123.430208`, lat `38.084322` to `38.132349` | `na085-0001-linear.sample-grid.tif` |
| `0003_20170813_005510_Nautilus.all.mb58.gz` | yes | 866,854 | 86,686 | lon `-123.456463` to `-123.416771`, lat `38.081189` to `38.133199` | `na085-0003-linear.sample-grid.tif` |

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
| NA085 has real coverage over the weak northwest cell. | This is a concrete candidate for improving the map in that area. |
| The first NA107 file is not near San Francisco. | Survey-level overlap is not enough; we need file-level indexing before downloading many large files. |
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
```

## Next Step

Build a file-level raw-sonar indexer for candidate surveys. It should download or inspect raw files just enough to record each file's real bounds, then choose only files that touch our weak cells.

Suggested order:

1. Index all 9 `NA085` files from the reports already produced.
2. Index `NA107` and `NA080` by file bounds before gridding anything else.
3. Turn only target-overlapping files into production candidate grids.
4. Add a coverage mask so gridded sonar does not smear across unsurveyed space.
5. Compare the sonar candidate against the current terrain stack before letting it into `best_available_gate_shelf_fusion`.
