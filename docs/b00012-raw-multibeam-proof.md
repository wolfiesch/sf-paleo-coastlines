# B00012 Raw Multibeam Proof

This note records the first raw-sonar proof for weak cell `qg-05-12`, the cell where the W00478 BAG survey was nearby but had 0% valid pixels inside the cell.

## What Was Proven

| Item | Result |
|---|---|
| Weak cell | `qg-05-12` |
| Cell bounds | `[-123.375, 38.0628604, -123.3603027, 38.0772128]` |
| Raw survey | `B00012` |
| Raw file | `85122-0120.sbo.mb15` |
| MB-System format | `15` |
| Processing host | `hostinger-devbox` |
| Processing tool | Docker image `mbari/mbsystem:latest` |
| Raw file size | 1,549,312 bytes |
| Total valid points in file | 286,006 |
| Points inside `qg-05-12` | 3,448 |
| Depths inside `qg-05-12` | about `-222 m` to `-153 m` |

Plain English: this file has real measured sonar points inside the blurry weak cell. So `qg-05-12` is not hopeless; it can likely be improved by turning B00012 raw sonar into a careful terrain patch.

## Preview Grid

The first safe preview grid used:

```text
thin-every 5
grid-size 384
invdistnn:power=2.0:radius=0.0015:max_points=12:min_points=1:nodata=-9999
```

That preview kept empty space as no-data. GDAL reported `STATISTICS_VALID_PERCENT=7.262`, which is what we want for a ship-track source: only areas close to real sonar points should be filled.

The earlier linear preview filled the whole rectangle with valid pixels, so it is useful only as a proof that gridding works. It should not be used as terrain because it smears across unsurveyed space.

## Remote Artifacts

These are on the VPS, not committed to the repo:

```text
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/b00012-85122-0120/b00012-85122-0120-85122-0120.sbo.mb15.sample-report.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/b00012-85122-0120-local/b00012-85122-0120-local-85122-0120.sbo.mb15.sample-report.json
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/b00012-85122-0120-local/b00012-85122-0120-local-85122-0120.sbo.mb15.sample-grid.tif
```

## Next Step

Process the rest of the B00012 files at bounds-only scale first. Then build a combined candidate grid only from files with proven points inside `qg-05-12` or adjacent weak cells.
