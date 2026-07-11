# B00012 qg-05-12 Candidate Grid

This note records the masked raw-sonar patch promoted for weak cell `qg-05-12`.

## Inputs

| B00012 file | Cropped points used |
|---|---:|
| `85122-0120.sbo.mb15` | 4,884 |
| `85143-0450.sbo.mb15` | 39,304 |
| `85152-0700.sbo.mb15` | 5,699 |
| **Total** | **49,887** |

Five other B00012 files had broad catalog bounds intersecting the cell but contributed no actual points inside the buffered candidate box. They were excluded from the final grid.

## Result

| Check | Result |
|---|---:|
| Grid size | `512 × 512` |
| Mask radius | `0.00040°` |
| Masked valid coverage | `99.78%` |
| Minimum elevation | `-226 m` |
| Maximum elevation | `-115 m` |
| Mean valid elevation | `-176.40 m` |
| Exact cell-center value | `-162 m` |
| Nearest measured point to center | `38.15 m` |

The mask radius was tested from `0.00035°` through `0.00050°`. The original `0.00035°` rule left a tiny hole at the exact center. `0.00040°` is the smallest tested radius that covers the center; larger radii were rejected because they add interpolation without adding evidence.

## Cross-check

| Source | Cell-center elevation |
|---|---:|
| B00012 candidate | `-162 m` |
| NOAA CRM | `-155.90 m` |
| NOAA CUDEM | `-193.14 m` |

B00012 and CRM independently support the shallower surface. CUDEM is about 31 m deeper, consistent with the broader CUDEM offset already detected against many measured sources.

## Promotion rule

The patch is ranked above CRM, CUDEM, CoNED support, and the broad NOAA OCM mosaic, but below modern named surveys. Its strict mask is preserved, so it cannot overwrite unsurveyed space.

Public review artifacts:

```text
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-05-12/b00012-qg-05-12.candidate-summary.json
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-05-12/b00012-qg-05-12.masked-512.cog.tif
public/data/paleo-coastlines/raw-sonar-candidates/b00012-qg-05-12/b00012-qg-05-12.mask-512.tif
```
