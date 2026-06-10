# B00012 qg-03-06 Candidate Grid

This note records a masked candidate grid made from raw `B00012` sonar for weak cell `qg-03-06`.

Plain English: this is the first candidate in this lane that actually covers the exact weak-cell center.

## Inputs

| Source file | Cropped points used |
|---|---:|
| `B00012-85142-1810` | 39,462 |
| `B00012-85150-2150` | 9,994 |
| Total | 49,456 |

The target weak-cell bounds were:

```text
[-123.4625, 38.0919069, -123.4478027, 38.1062593]
```

The candidate used a `0.003` degree buffer around that cell before gridding.

## Result

| Check | Result |
|---|---:|
| Grid size | `512 x 512` |
| Strict mask radius | `0.00035` degrees |
| Masked valid coverage | `99.77%` |
| Minimum depth/elevation | `-207.0` |
| Maximum depth/elevation | `-148.0` |
| Mean valid value | `-168.265` |

The exact weak-cell center is covered:

```text
lon -123.4551513
lat  38.0990831
value -166.0
mask 1
```

For comparison, the current `best_available_gate_shelf_terrain_wgs84.tif` value at the same point is about:

```text
-197.6373
```

So this B00012 candidate is about `31.6 m` shallower at the weak-cell center.

Nearby source samples at the same point:

| Source | Center value |
|---|---:|
| Current best available | `-197.6373` |
| NOAA CUDEM 1/9 arc-second | `-197.7472` |
| NOAA CRM Vol. 7 | `-163.1757` |
| B00012 candidate | `-166.0` |
| NA085 candidate | no-data |
| W00478 BAG | no-data |
| EX0907 50 m | no-data |

Plain English: B00012 is much shallower than the current CUDEM-backed value, but it is close to the NOAA CRM value. That makes it a stronger candidate than it would be if B00012 were the only source saying this.

## Public Artifacts

```text
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-03-06/b00012-qg-03-06.candidate-summary.json
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-03-06/b00012-qg-03-06.masked-512.cog.tif
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-03-06/b00012-qg-03-06.mask-512.tif
```

## Decision

This is a real candidate for improving `qg-03-06`, but do not merge it blindly.

The source is older 1985 sonar, and the center value differs materially from the current terrain. The next step is to compare neighboring B00012/B00016/EW9505 coverage and then decide whether B00012 plus CRM support is enough to promote a masked patch into `best_available_gate_shelf_fusion`.
