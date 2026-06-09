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
