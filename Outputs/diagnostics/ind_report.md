# Diagnostics report: ind

- Rows: 13853
- Columns: 175

## Missingness (top 15 columns by % missing)

| Column | % missing | # missing |
| --- | --- | --- |
| q6_05f | 100.0 | 13853 |
| q6_04f | 99.99 | 13852 |
| q6_05g | 99.99 | 13851 |
| q6_12b | 99.98 | 13850 |
| q6_05i | 99.95 | 13846 |
| q6_05c | 99.82 | 13828 |
| q6_04e | 99.8 | 13825 |
| q6_13b | 99.79 | 13824 |
| q6_11b | 99.78 | 13823 |
| q6_05e | 99.75 | 13819 |
| q6_04a | 99.63 | 13802 |
| q4_06 | 99.62 | 13801 |
| q2_13 | 99.62 | 13801 |
| q6_04d | 99.62 | 13800 |
| q6_05h | 99.43 | 13774 |

## Missingness: structural vs incidental (bounded set of verified skip gates)

| Column | Gate | Missing | Structural | Incidental | % structural |
| --- | --- | --- | --- | --- | --- |
| q2_02 | q2_01 | 13304 | 13304 | 0 | 100.0 |
| q2_03 | q2_01 | 13304 | 13304 | 0 | 100.0 |
| q1_12 | q1_11 | 1600 | 1600 | 0 | 100.0 |
| q1_13 | q1_11 | 1600 | 1600 | 0 | 100.0 |
| q3_04 | q3_01 | 13690 | 13690 | 0 | 100.0 |
| q3_05 | q3_01 | 13690 | 13690 | 0 | 100.0 |
| q2_15 | q2_14 | 13150 | 13150 | 0 | 100.0 |

## Duplicate rows on natural key ['hhid', 'member'] (0 rows involved)

- none found

## Range checks

- **q1_04**: 12 value(s) out of range

## Named-variable distributions

### Sex (q1_03)

Missing: 0

| Label | Count | % of valid |
| --- | --- | --- |
| Female | 7073 | 51.06 |
| Male | 6780 | 48.94 |

### Age group (q1_04, bucketed)

Missing: 12

| Label | Count | % of valid |
| --- | --- | --- |
| 0-14 | 3752 | 27.11 |
| 15-24 | 2757 | 19.92 |
| 25-34 | 1771 | 12.8 |
| 35-44 | 1750 | 12.64 |
| 45-54 | 1641 | 11.86 |
| 55-64 | 1129 | 8.16 |
| 65+ | 1041 | 7.52 |

### Employment status, main job (q3_16)

Missing: 9064

| Label | Count | % of valid |
| --- | --- | --- |
| Employee (for another person, for a company or for the government) | 3168 | 66.15 |
| Self-employed (without paid help) | 1125 | 23.49 |
| Self-employed (with paid help) | 274 | 5.72 |
| Unpaid family worker | 222 | 4.64 |

## Recommendations

- No duplicate hhid+member rows -- this is a reliable natural key, no dedup logic needed.
- q1_04: 12 value(s) out of range, all exactly -1 -- looks like a missing/'don't know' sentinel, not a real data error. Treat as NaN when cleaning rather than a literal value.
- 60 columns are >90% missing -- almost entirely expected survey skip patterns (e.g. q6_* income sub-questions only apply to employees with that income source), not a data-quality problem by itself. Worth distinguishing structural vs. incidental missingness per-variable once cleaning scope is known.
- Sex is 48.9% male / 51.1% female with 0 missing -- close to balanced, no coverage concern for this variable.
- 'Employee (for another person, for a company or for the government)' dominates employment status (66.15% of valid responses); 9064 rows are missing this field entirely (not currently employed, so q3_16 correctly does not apply) -- do not treat that as missing data to impute, it's a structural skip.
- All checked skip-gate columns (q2_02/q2_03, q1_12-q1_16, q3_04/q3_05, q2_15) have missingness that's almost entirely structural -- confirms the CAPI skip logic worked as designed for these fields.
- 1422 near-duplicate value pair(s) found across the free-text columns (Jaro-Winkler >= 0.90) -- see ind_near_duplicates.csv for manual review before building any value-consolidation mapping.
- All 99 category columns are casing-consistent (confirms the Stata-labeled-export hypothesis) -- no 'M'/'m'/'Male'-style normalization is needed for the pre-coded fields.
