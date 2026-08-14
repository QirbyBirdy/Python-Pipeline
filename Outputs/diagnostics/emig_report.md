# Diagnostics report: emig

- Rows: 659
- Columns: 28

## Missingness (top 15 columns by % missing)

| Column | % missing | # missing |
| --- | --- | --- |
| q7_10 | 85.89 | 566 |
| q7_08 | 78.0 | 514 |
| q7_17 | 70.26 | 463 |
| q7_14 | 47.19 | 311 |
| q7_15 | 47.19 | 311 |
| q7_13 | 8.5 | 56 |
| q7_16 | 8.5 | 56 |
| q7_07 | 1.67 | 11 |
| week | 1.52 | 10 |
| hhid | 0.0 | 0 |
| weight | 0.0 | 0 |
| emig | 0.0 | 0 |
| zone | 0.0 | 0 |
| area | 0.0 | 0 |
| region | 0.0 | 0 |

## Duplicate rows on natural key ['hhid', 'emig'] (0 rows involved)

- none found

## Range checks

- **q7_06**: 28 value(s) out of range

## Named-variable distributions

## Recommendations

- No duplicate hhid+emig rows -- reliable natural key.
- q7_06: 28 value(s) out of range, all exactly -1 -- looks like a missing/'don't know' sentinel, not a real data error. Treat as NaN when cleaning rather than a literal value.
- 21 near-duplicate value pair(s) found across the free-text columns -- see emig_near_duplicates.csv for manual review.
- All 13 category columns are casing-consistent.
