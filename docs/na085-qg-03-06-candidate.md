# NA085 qg-03-06 Candidate Grid

This note records the first masked candidate grid made from raw `NA085` sonar for weak cell `qg-03-06`.

Plain English: this is not yet merged into the live terrain. It is a candidate patch that shows where NA085 can add real detail and where it still has no data.

## Inputs

| Source file | Cropped points used |
|---|---:|
| `NA085-0001` | 107,566 |
| `NA085-0003` | 6,136 |
| `NA085-0005` | 0 |
| Total | 113,702 |

The target weak-cell bounds were:

```text
[-123.4625, 38.0919069, -123.4478027, 38.1062593]
```

The candidate used a `0.003` degree buffer around that cell before gridding.

## Result

| Check | Result |
|---|---:|
| Grid size | `512 x 512` |
| Mask radius | `0.00035` degrees |
| Masked valid coverage | `14.29%` |
| Minimum depth/elevation | `-1065.705` |
| Maximum depth/elevation | `-128.932` |
| Mean valid value | `-185.595` |

The exact weak-cell center is still no-data:

```text
lon -123.4551513
lat  38.0990831
value -9999
mask 0
```

That means NA085 improves nearby north/east terrain, but it does not fully solve the weak point we were chasing.

## Public Artifacts

```text
public/data/paleo-coastlines/raw-sonar-candidates/na085-qg-03-06/na085-qg-03-06.candidate-summary.json
public/data/paleo-coastlines/raw-sonar-candidates/na085-qg-03-06/na085-qg-03-06.masked-512.cog.tif
public/data/paleo-coastlines/raw-sonar-candidates/na085-qg-03-06/na085-qg-03-06.mask-512.tif
```

## Decision

Do not merge this candidate directly into `best_available_gate_shelf_fusion` yet.

Use it as partial coverage evidence, then look for another source for the west/center part of `qg-03-06`.
