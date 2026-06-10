# EW9505 Raw Multibeam Scout

This note records a bounds-only VPS scout of `EW9505` raw sonar files for weak cell `qg-03-06`.

Plain English: EW9505 looked promising at the survey-rectangle level, but file-level bounds are the real test. The file-level scout says EW9505 does not help this exact cell.

## Result

| Check | Result |
|---|---:|
| Raw files listed | 29 |
| Files with usable bounds | 26 |
| Files overlapping `qg-03-06` | 0 |

Three files produced no valid points after filtering:

```text
9505hs.d172.mb21.gz
9505hs.d175.mb21.gz
9505hs.d187.mb21.gz
```

That does not affect the decision for `qg-03-06`, because none of the successful file bounds touched the cell.

## Decision

Do not use EW9505 as confirmation for the B00012 `qg-03-06` candidate.

B00012 remains supported by NOAA CRM at the center, but not by EW9505 raw-file coverage.

## Public Artifact

```text
public/data/paleo-coastlines/ew9505_raw_multibeam_scout.json
```
