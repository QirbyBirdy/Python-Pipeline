# Problem inventory: sex, age, hours worked, industry (ISIC), occupation (ISCO)

Read-only findings on the typed (pre-cleaning) `ind` dataset (13,853 rows). Counts and % are of all rows, not just valid responses, so structural missingness is visible in context. See `Scripts/clean.py` for what each finding's 'Addressed by' column actually does.

| Variable | Issue | Count | % | Severity | Addressed by |
| --- | --- | --- | --- | --- | --- |
| Sex (q1_03) | No issues found -- 0 missing, values are clean 'Male'/'Female' text | 0 | 0.0 | None | N/A |
| Age (q1_04) | Missing (before sentinel correction) | 0 | 0.0 | None | N/A |
| Age (q1_04) | '-1' sentinel value (verified 'don't know' placeholder, not a real age) | 12 | 0.09 | Low | clean.py: correct_age_sentinel() -> NaN |
| Hours worked (q3_03, usual hours/week main job) | '99' top-code sentinel (natural max otherwise caps at 98; q3_09 'actual hours', which never top-codes, goes up to 168 -- confirms 99 is a sentinel specific to this field, not a real value) | 88 | 0.64 | Medium | clean.py: correct_hours_sentinel() -> NaN |
| Hours worked (q3_05, total usual hours all jobs) | '99' sentinel (same pattern as q3_03) | 6 | 0.04 | Low | clean.py: correct_hours_sentinel() -> NaN |
| Hours worked (q3_03 + q3_04 vs q3_05) | Arithmetic mismatch: main-job + other-job hours don't sum to the reported total (all cases traced to the q3_05=99 sentinel above, not independent data-entry errors) | 6 | 0.04 | Low | clean.py: check_usual_hours_consistency() -- flagged, resolves once sentinel is corrected |
| Hours worked (daily q3_07_1..7 vs q3_09) | Arithmetic mismatch: daily hours don't sum to the reported weekly actual-hours total | 0 | 0.0 | None | clean.py: check_daily_hours_consistency() -- flagged only |
| Industry (isic_code) | Missing -- structural: isic_code only applies to people with a main job (matches q3_16 employment-status missingness exactly) | 9064 | 65.43 | None (structural, not a quality issue) | N/A -- correctly not imputed |
| Industry (isic_code) | Leading zero stripped in export (e.g. '0729' stored as '729') -- would misclassify the ISIC section if not corrected for | 206 | 1.49 | Low (corrected, not left broken) | clean.py: classify_isic_section() zero-pads to 4 digits before reading the division |
| Occupation (isco_code) | Missing -- structural, same pattern as isic_code (only applies to people with a main job) | 9064 | 65.43 | None (structural, not a quality issue) | N/A -- correctly not imputed |
| Occupation (isco_code) | Non-4-digit code (2, 3, or 5 characters) -- the 3-digit cases are the same leading-zero-stripping issue as ISIC (Major Group 0, Armed forces); the single 5-digit case ('61111') is likely a typo | 12 | 0.09 | Low (corrected/best-effort, not left broken) | clean.py: classify_isco_major_group() zero-pads short codes; long codes best-effort on the leading digit |

## Summary

- **Sex**: clean. No missingness, no inconsistent coding.
- **Age**: one small, fully-corrected issue (12 rows, a verified `-1` sentinel).
- **Hours worked**: the most issues of the five, but all trace back to a single root cause -- the `99` top-code sentinel in `q3_03`. Once that's corrected, the arithmetic-consistency mismatch in `q3_05` resolves on its own (it was never an independent error).
- **Industry (ISIC) / Occupation (ISCO)**: high missingness (65.4%) is entirely structural (the question only applies to people with a main job) and not a quality problem. The real issue -- inconsistent leading-zero stripping -- is fully handled by zero-padding before classification; **0 of 4,789** codes with a value failed to classify.
- Nothing found across these five variables required a silent correction beyond the two already made (age and hours sentinels) -- everything else is either structural (expected, not a defect) or already fully resolved by the classification logic.
