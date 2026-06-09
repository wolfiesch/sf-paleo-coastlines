# NA107 Raw Multibeam Scout

This note records a bounds-only VPS scout of selected `NA107` raw sonar files.

Plain English: we sampled files across the survey timeline to see whether NA107 passes through the weak map cells before spending time on full gridding.

## Result

The sampled NA107 files did **not** overlap the current weak-cell boxes from `external_bathymetry_candidates.json`.

| File index | Bounds | Valid points | Plain-English location |
|---:|---|---:|---|
| 0 | `-120.924207, 34.257248, -120.680172, 34.339086` | 822,052 | Southern California, far south of the study area |
| 20 | `-121.867378, 34.751010, -121.706902, 34.946999` | 513,403 | Still south of the study area |
| 40 | `-122.564836, 35.746346, -122.387926, 35.941595` | 169,210 | South of the Bay Area |
| 60 | `-123.260002, 37.829665, -123.126758, 37.891630` | 3,907,393 | Near the broader Bay Area, but east of our weak offshore cells |
| 80 | `-123.765413, 38.682976, -123.674803, 38.824951` | 4,182,469 | North/west of the target weak cells |
| 100 | `-123.684961, 38.495919, -123.572729, 38.669326` | 3,415,467 | North/west of the target weak cells |
| 140 | `-123.712647, 38.508553, -123.607627, 38.668084` | 2,973,733 | North/west of the target weak cells |
| 160 | `-123.816192, 38.660789, -123.715960, 38.813308` | 3,556,999 | North/west of the target weak cells |
| 180 | `-123.832225, 38.648533, -123.728401, 38.806660` | 3,082,498 | North/west of the target weak cells |
| 200 | `-123.479213, 38.395399, -123.456240, 38.423567` | 621,740 | North of the current weak northwest cell |

## Decision

Do not spend the next production pass on NA107 for `qg-03-06`.

NA085 is the better immediate path because three of its files have proven overlap with `qg-03-06`.

## Remote Artifact

```text
/home/wolfie/Projects/sf-paleo-coastlines/data/paleo-coastlines/raw-sonar-probe/na107-scout-summary.json
```
