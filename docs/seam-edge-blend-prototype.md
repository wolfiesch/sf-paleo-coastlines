# Seam Edge Blend Prototype

This note records the first targeted repair experiment after the local seam-height audit, plus the production follow-up.

The early prototype did **not** overwrite production terrain. The production generator now applies the same idea directly to the best-available terrain layer.

## Plain-English Result

The best first prototype candidate was `severe-r12-sigma7`.

It smooths a thin strip around source-category edges at the 16 severe local seam targets. That means it does not blur the whole map; it only softens the final height image around source joins that the audit already marked as severe.

The production pass now uses a wider controlled list: 37 audited seam points. It also uses a slightly wider smoothing strip than the first prototype, because the first production run proved that several land-to-Bay source joins still had fake ledges.

## Production Result

After the second production pass:

| Audit level | Before second pass | After second pass |
|---|---:|---:|
| Severe | 11 | 0 |
| Suspicious | 20 | 17 |
| Calm | 98 | 112 |

Plain English: the obvious fake ledges are gone from the audit. The remaining questionable joins are smaller and mostly sit in the "inspect this" bucket, not the "this is clearly bad" bucket.

The worst remaining local seam after the second pass is:

| Categories | Lon/lat | 95% step |
|---|---|---:|
| CUDEM support / USGS offshore | `-123.303675, 37.782137` | 16.447 m |

That is probably the point where simple seam smoothing starts to hit diminishing returns. Further improvement will likely need source-specific vertical-offset handling, not just a wider blur.

## Post-Resample Round (2026-06-12)

The anti-aliased per-source VRT resampling fix moved source-category boundaries, so seams re-appeared at locations the existing target list did not cover: the post-resample audit found 14 severe targets, none of them matching a configured blend point. The list was widened by 21 points (the 14 severe plus the 7 suspicious with a 95% step of 20 m or more), bringing it to 64 targets total.

| Audit level | Before this round | After this round |
|---|---:|---:|
| Severe | 14 | 1 |
| Suspicious | 30 | 25 |
| Calm | 96 | 114 |

The one target still marked severe is the CRM fallback / USGS CoNED broad join at `-123.127923, 37.347048`, the southern cut edge of the CoNED broad warp:

| Before median | Before 95% | After median | After 95% |
|---:|---:|---:|---:|
| 87.055 m | 107.667 m | 12.106 m | 16.348 m |

It stays technically severe because the median threshold is 10 m, but the residual step matches a ~22 degree slope at the ~30 m source pixel there, which is plausible real continental-slope gradient. Blurring harder at that point would start erasing legitimate bathymetry, so the residual is accepted. This is the same diminishing-returns endpoint the earlier production round hit.

## Visual Check

Use two screenshot types when reviewing this work:

| Screenshot type | Overlays | What it answers |
|---|---|---|
| Audit view | Seams, gaps, coverage, labels as needed | Where are the suspicious source joins? |
| Quality view | Grid, seams, gaps, labels, and coverage off | Does the terrain itself look natural? |

The grid overlay is useful for finding bad joins, but it makes the underlying map harder to judge. For the terrain-quality review, use the clean quality screenshots.

The first clean before/after check used:

| View | Screenshot |
|---|---|
| Production close-up | `output/playwright/seam-blend-compare/before-close-edge-production.png` |
| Candidate close-up | `output/playwright/seam-blend-compare/after-close-edge-candidate.png` |

The candidate did not visibly wash out the terrain in that close-up. The measured seam improvement is much stronger than the visible change, which is the right direction: targeted repair without obvious broad blurring.

## Candidate Comparison

| Candidate | Before severe | After severe | After suspicious | After calm | Mean 95% step change | Read |
|---|---:|---:|---:|---:|---:|---|
| `severe-r6-sigma4` | 16 | 4 | 11 | 1 | -15.984 m | Helps, but leaves several strong ledges. |
| `severe-r8-sigma5` | 16 | 4 | 9 | 3 | -17.289 m | Better, but still leaves the same main offshore ledges severe. |
| `severe-r12-sigma7` | 16 | 1 | 7 | 8 | -18.979 m | Best current tradeoff; strongest improvement without blending unrelated areas. |

## Prototype Remaining Worst Target

The one target still marked severe after `severe-r12-sigma7` is:

| Categories | Lon/lat | Before 95% step | After 95% step |
|---|---|---:|---:|
| CUDEM support / USGS offshore | `-123.352735, 37.802308` | 38.508 m | 14.438 m |

It is technically still classified severe because the audit threshold is strict, but the height step is much smaller than before.

## Next Decision

Before making this production terrain, capture a visual before/after using the candidate elevation PNG. If the terrain looks better and not washed out, the production path should be:

1. Add the edge-blend step to the best-available terrain generation pipeline.
2. Regenerate the best-available elevation, relief, composite texture, seam audit, and terrain tiles where needed.
3. Re-run local seam-height audit.
4. Re-capture Shelf and NW Gap screenshots.
