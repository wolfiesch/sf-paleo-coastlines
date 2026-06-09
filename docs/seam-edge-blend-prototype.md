# Seam Edge Blend Prototype

This note records the first targeted repair experiment after the local seam-height audit.

The blend does **not** overwrite production terrain yet. It creates candidate elevation PNGs under `output/seam-blend-experiment/` and compares the same severe seam targets before and after.

## Plain-English Result

The best first candidate is `severe-r12-sigma7`.

It smooths a thin strip around source-category edges at the 16 severe local seam targets. That means it does not blur the whole map; it only softens the final height image around source joins that the audit already marked as severe.

## Candidate Comparison

| Candidate | Before severe | After severe | After suspicious | After calm | Mean 95% step change | Read |
|---|---:|---:|---:|---:|---:|---|
| `severe-r6-sigma4` | 16 | 4 | 11 | 1 | -15.984 m | Helps, but leaves several strong ledges. |
| `severe-r8-sigma5` | 16 | 4 | 9 | 3 | -17.289 m | Better, but still leaves the same main offshore ledges severe. |
| `severe-r12-sigma7` | 16 | 1 | 7 | 8 | -18.979 m | Best current tradeoff; strongest improvement without blending unrelated areas. |

## Remaining Worst Target

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
