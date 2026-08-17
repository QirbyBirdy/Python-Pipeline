# GLFS Data Cleaning & Imputation Pipeline

Bureau of Statistics — Guyana, Analytical Unit Technical Capability Assessment.
Dataset: GLFS 2017 Q4 microdata (round 174), two tracks — individual records (`ind`)
and the household emigration module (`emig`).

## Status

Project reset back to a basic ingest-only overview, since extended with
actual dtype conversion, exploratory diagnostics, a problem inventory,
charts, and a cleaning stage. Current state:

- `Scripts/config.py` — every path used by the pipeline, in one place, plus
  the skip-gate table, free-text/monetary column lists, and the
  value-mapping store
- `Scripts/ingest.py` — loads the raw CSVs, validates them against their
  dictionaries, verifies row/household counts against the source
  methodological report, recommends a pandas dtype per column, and applies
  those recommendations to produce a typed copy (raw string copy kept
  untouched alongside it)
- `Scripts/diagnose.py` — missingness (including structural vs. incidental
  for a verified subset of skip gates), duplicate-key and range checks,
  free-text near-duplicate detection, category-casing consistency check,
  and a named-variable distribution/recommendations spotlight (sex, age
  groups, employment status)
- `Scripts/problem_inventory.py` — a written, counted list of data-quality
  issues in six items of interest (sex, age, hours worked, ISIC industry,
  ISCO occupation, and `panelid`'s misleading name), cross-referenced
  against what `clean.py` actually does about each one
- `Scripts/clean.py` — the actual cleaning stage: exact-duplicate removal,
  three verified auto-corrections (age `-1`, hours `99`, and hours `-1`
  sentinels → `NaN`), recomputation of the CAPI-derived hours totals from
  their cleaned components, flag-only validation rules (skip-pattern
  logic, monetary IQR outliers), automatic high-confidence free-text
  consolidation, and ISIC-section / ISCO-major-group classification —
  exports the cleaned dataset as parquet *and* xlsx
- `Scripts/visualize.py` — renders six distributions (sex, age group,
  employment status, ISIC section, ISCO major group, hours worked) as JPEG
  charts
- `Scripts/run_pipeline.py` — the single command entry point (brief
  Section 2.2.1): runs ingest → diagnose → clean → problem inventory →
  charts, for both datasets, in that order
- `Outputs/` — regenerated end to end by `python Scripts/run_pipeline.py`

See `CLEANING_PLAN.md` for the full design/reasoning behind the cleaning
stage before it was built, and [Course-correction](#course-correction-self-audit)
below for a self-audit pass that found and fixed four checks that had lost
their diagnostic power. Not yet done: automated Word report generation,
`.sav`/`.dta` export, a formal data dictionary deliverable.

## Folder layout

```text
Data/                       raw GLFS CSVs + data dictionaries + methodological report + official ISIC/ISCO structure files (never edited in place)
Scripts/
  config.py                  every path used by the pipeline, in one place
  ingest.py                  load + validate + verify counts + dtype recommend/apply + metadata-exploration helpers
  diagnose.py                missingness (+structural/incidental) + duplicates + range checks + near-duplicates + casing check + named-variable distributions
  problem_inventory.py        written, counted data-quality findings for sex/age/hours/ISIC/ISCO/panelid
  clean.py                   dedup removal + sentinel corrections + derived-hours recomputation + validation rules (flag/correct) + auto-consolidation + ISIC/ISCO classification + parquet/xlsx export
  visualize.py                renders six distributions as JPEG charts (3 donut, 2 bar, 1 histogram)
  run_pipeline.py              single entry point -- runs every stage above in order
Outputs/
  interim/                    raw string-typed parquet cache (untouched safety net, gitignored)
  typed/                      dtype-converted parquet (<name>_typed.parquet) and cleaned parquet (<name>_cleaned.parquet), gitignored
  diagnostics/                 diagnostics report (.md) + missingness table (.csv) per dataset
  problem_inventory/           problem inventory report (.md)
  charts/                      six distribution charts (.jpg)
  logs/                       ingest/dtype/cleaning logs, flagged-for-review CSVs, near-duplicate and casing-check CSVs
  <name>_cleaned.xlsx          the fully cleaned dataset, one file per dataset (tracked, not gitignored)
```

## Setup

```bash
python -m pip install -r requirements.txt
```

## Running the whole pipeline

```bash
python Scripts/run_pipeline.py
```

The single entry point the brief requires (Section 2.2.1: "there must be
one entry point... that executes every stage in the correct order"). Runs
ingest → diagnose → clean → problem inventory → charts for both datasets,
in the order each stage actually depends on the one before it, and
regenerates everything under `Outputs/`. The per-stage sections below
document what each step does and how to run it individually while
iterating.

## Running ingest

```bash
python Scripts/ingest.py
```

Loads both datasets, validates their columns against their dictionaries,
checks row/household counts against the methodological report, and writes
`Outputs/interim/<name>_raw.parquet` plus `Outputs/logs/<name>_ingest.log`.
Then applies the recommended dtypes to a fresh load of each dataset and
writes `Outputs/typed/<name>_typed.parquet` plus
`Outputs/logs/<name>_dtype_coercion.log`. The raw interim parquet is never
overwritten by the typed conversion — if a dtype recommendation turns out to
be wrong later, the untouched raw copy is still there to redo it from.

## Running diagnostics

```bash
python Scripts/ingest.py     # must run first -- diagnose.py reads the typed output
python Scripts/diagnose.py
```

For each dataset, writes `Outputs/diagnostics/<name>_report.md` (missingness,
duplicate-key check, range checks, and — for `ind` only — sex/age-group/
employment-status distributions with recommendations) and
`Outputs/diagnostics/<name>_diagnostics.csv` (the full missingness table).
Nothing here modifies the data; every function reports.

Key functions in `Scripts/diagnose.py`:

- `missingness_report(df)` — % missing per column, worst first
- `find_duplicates(df, key_columns)` — exact-match duplicate check on a natural key
- `range_check(df, column, low, high)` — flags non-missing values outside `[low, high]`
- `value_counts_labeled(series, labels=None)` — frequency table for one column
- `age_group_distribution(age_series)` — buckets a numeric age column into standard groups
- `classify_missingness(df, dependent_col, gate_col, applies_when)` — structural vs. incidental split for one verified skip-gate pair
- `find_near_duplicate_values(series, threshold=0.95)` — Jaro-Winkler near-duplicate pairs within a free-text column
- `check_casing_consistency(series)` — `True` if a category column has no case/whitespace variants

## Problem inventory

```bash
python Scripts/ingest.py     # must run first
python Scripts/problem_inventory.py
```

Brief Step 5: a written, counted list of data-quality issues for six items
of interest — sex, age, hours worked, industry (ISIC), occupation (ISCO),
and `panelid`'s misleading name — read-only on the *typed* (pre-cleaning)
`ind` data, so it documents what's wrong before describing what fixes it.
Writes `Outputs/problem_inventory/ind_problem_inventory.md`. Every row of
the table's "Addressed by" column points at the exact `clean.py` function
(or says "not addressed" / "N/A — correctly not imputed" when nothing
should touch it).

Findings, in brief:

| Variable | Worst issue found | Verdict |
| --- | --- | --- |
| Sex | none | clean — 0 missing, no casing issues |
| Age | 12 rows, `-1` sentinel | small, fully corrected |
| Hours worked | 88 rows, `99` sentinel in `q3_03`; the same `-1` sentinel verified for age also live, uncorrected, in 8 more columns (`q3_07_1..7`, `q3_08`) | the most issues of the six; `q3_09`/`q3_10`/`q3_05` are CAPI-computed totals, not independent measurements, so they're recomputed from cleaned components rather than validated against themselves — see [Course-correction](#course-correction-self-audit) |
| Industry (ISIC) | 206 rows lost a leading zero on export | corrected via zero-padding before classification; 0 codes failed to classify |
| Occupation (ISCO) | 12 non-4-digit codes (same leading-zero pattern + one likely typo) | corrected/best-effort; 0 codes failed to classify |
| panelid | claims to be a unique ID but has only 18 distinct values across 13,853 rows | not a defect on its own — harmless untouched, but would corrupt a join if ever used as a merge key; documented so it isn't mistaken for a real ID later |

High missingness on ISIC/ISCO (65.4%) is called out explicitly as
**structural, not a quality problem** — the question only applies to people
with a main job — rather than left ambiguous.

## Running cleaning

```bash
python Scripts/ingest.py     # must run first -- clean.py reads the typed output
python Scripts/clean.py
```

Design doc: `CLEANING_PLAN.md` (written and reviewed before any of this was
built). For each dataset, writes `Outputs/typed/<name>_cleaned.parquet`,
`Outputs/<name>_cleaned.xlsx` (the same cleaned data, tracked in git so it's
directly inspectable), `Outputs/logs/<name>_cleaning.log` (row counts
before/after, what changed), and `Outputs/logs/<name>_flagged_for_review.csv`
(every row a validation rule flagged, tagged with `rule_name` — flagged,
never silently altered).

Key functions in `Scripts/clean.py`:

- `drop_exact_duplicates(df, key_columns)` — exact-match dedup, keep first
- `correct_age_sentinel(df, name)` — verified `-1` age sentinel → `NaN`
- `correct_hours_sentinel(df, name)` — verified `99` hours top-code → `NaN` (`q3_03`/`q3_05` only)
- `correct_negative_one_hours_sentinel(df, name)` — the same `-1` sentinel verified for age, generalized to the 8 hours columns where it also occurs (`q3_07_1..7`, `q3_08`)
- `recompute_derived_hours(df, name)` — recalculates `q3_09`/`q3_10`/`q3_05` directly from their cleaned components instead of validating the raw CAPI-computed totals (`ind` only) — see [Course-correction](#course-correction-self-audit)
- `check_usual_hours_consistency(df)` — diagnostic only, run once on raw data before any correction (see [Course-correction](#course-correction-self-audit)); not part of the flagged-for-review output
- `check_employment_skip_logic(df)` — flags `isco_code` filled in when none of q2_04/05/06/07/10 show any evidence of employment (`ind` only)
- `flag_monetary_outliers(df, name)` — 1.5×IQR outlier flag per column in `config.MONETARY_COLUMNS`
- `build_consolidation_mapping(near_duplicates, min_similarity=0.98)` — clusters near-duplicate free-text values (union-find) and maps each cluster to its most frequent member
- `apply_value_mapping(df, column, mapping)` — applies any mapping (manual `config.VALUE_MAPPINGS`, or the auto-built one above)
- `classify_isic_section(isic_series)` / `classify_isco_major_group(isco_series)` — see below

### What actually changes vs. what's flagged

Five things happen automatically to the data: exact-duplicate removal (0
found), the age `-1` → `NaN` correction (12 rows `ind` / 28 `emig`), the
hours `99` → `NaN` correction (88 rows in `q3_03`, 6 in `q3_05`), the hours
`-1` → `NaN` correction (14–15 rows each in `q3_07_1..7`, 1 in `q3_08`),
the recomputation of `q3_09`/`q3_10`/`q3_05` from their now-cleaned
components, and free-text consolidation at ≥0.98 similarity (436 variants
merged across 6 `ind` columns, 4 in `emig` — see below). Everything else —
the employment skip-logic check, monetary outliers — is flag-only, written
to `flagged_for_review.csv`, never altered in the cleaned data. This
matches the brief's "flag or correct, depending on what's defensible" —
only verified, evidence-backed patterns get corrected automatically;
everything with real judgment involved gets flagged instead.

### Real findings from running it

- **Duplicates**: still zero — nothing dropped.
- **Age sentinel**: 12 (`ind`) / 28 (`emig`) values corrected, matching the
  counts `diagnose.py` already found.
- **Hours sentinel (`99`)**: `q3_03` (usual hours, main job) had **88**
  values of exactly `99`, with every other value capping at 98 — a classic
  "99 or more" top-code. `q3_05` had 6 more, matching the earlier
  usual-hours-mismatch flags exactly. Checked every other hours-related
  column before correcting anything: **zero** of them ever use `99`,
  despite some going as high as 168 — confirms this is a sentinel specific
  to these two "usual hours" fields, not a general hours convention.
- **Hours sentinel (`-1`)**: the same "don't know" sentinel already
  verified for age, found still live and uncorrected in `q3_07_1..7` (the
  seven daily-hours columns, 14–15 rows each) and `q3_08` (1 row) — see
  [Course-correction](#course-correction-self-audit).
- **Recomputed hours totals**: `q3_09` changed for 17 rows, `q3_10` for 3,
  `q3_05` for 6 — all 6 originally-flagged `q3_05` mismatches now resolve
  to a real recovered total (5 rows) or correctly become unknown (1 row,
  whose own `q3_03` was itself a `99` sentinel), not silently dropped.
- **Employment skip-logic**: 0 unexplained violations — see
  [Course-correction](#course-correction-self-audit) for how the original
  version missed 23 real rows.
- **Monetary outliers**: 583 total flags across 18 fields (1.5×IQR), led by
  `q6_01` (exact net salary, 154 flags) and `q6_07` (value of business
  products consumed at home, 143 flags) — expected for right-skewed income
  data, not necessarily errors; that's exactly why these are flagged for a
  human look, not dropped.
- **Free-text consolidation**: at the ≥0.98 threshold, 436 variants merged
  into their canonical (most frequent) form across `ind`'s 6 free-text
  columns (e.g. "GOLDSMITH"/"GOLD SMITH" → whichever was more common),
  affecting 648 rows total; 4 more in `emig`. Only pairs checked by eye at
  0.98+ and confirmed as unambiguous typo/spacing/pluralization variants —
  the noisier 0.90–0.97 band stays flag-only in `near_duplicates.csv` for
  manual review, not auto-merged.
- **Casing consistency**: confirmed across *all* 99 `ind` + 13 `emig`
  category columns, not just the spot-checked ones from before — zero
  inconsistencies. The "no code→label mapping needed" finding from the
  dtype section holds up at full scale.
- **Near-duplicate threshold**: `CLEANING_PLAN.md` proposed 0.90 Jaro-Winkler
  as a starting point. Checked before trusting it — 0.90 let through
  clearly-wrong pairs like *"CUTTING CANE"* / *"CUTTING HAIR"* and
  *"SELLING FISH"* / *"SELLING OF LIME"* (Jaro-Winkler over-rewards a
  shared prefix on short strings). Raised to **0.95**, which keeps genuine
  variants (*"GUYANA SUGAR CORPORATION (GUYSUCO)"* vs. *"...( GUYSUCO)"*)
  while cutting the false positives — 1,422 pairs in `ind`, down from
  6,153.
- **`SKIP_PATTERNS` self-correction**: originally included `q1_14`/`q1_15`/
  `q1_16` as gated by `q1_11` alone. Running `classify_missingness()`
  showed only 12–43% of their missingness was "structural" under that
  model — too low to be measurement noise. They actually branch further off
  `q1_13`'s specific value (education level), a nested gate the bounded
  single-parent model doesn't capture. Removed from the table rather than
  reported under a misleading label; the remaining 7 gates are all 100%
  structural, fully verified.

### ISIC section / ISCO major-group classification

Per direction: `isic_code` (4-digit ISIC Rev. 4 class code) is classified
down to its **section** (the letter A–U, e.g. `8412` → section `O`, Public
administration); `isco_code` (4-digit ISCO-08 code) is classified down to
its **major group** (the first digit, e.g. `3131` → major group `3`,
Technicians and Associate Professionals).

The lookup tables aren't hand-transcribed — `clean.py` reads them directly
from the official structure files, `Data/isic-rev4-structure.csv` and
`Data/isco-08-structure.xlsx` (both public reference data, not
survey-specific). A hand-built version was written first and cross-checked
against these files column-by-column (every ISIC division and all 10 ISCO
major groups matched exactly), then replaced with functions that load from
the files directly (`clean.py`'s `_load_isic_division_to_section()` /
`_load_isco_major_group_labels()`, both cached) — one source of truth
instead of a copy that could drift from it.

One real data-quality issue this surfaced: **both code columns
inconsistently lose a leading zero** in this dataset's export (`isic_code`
`"0729"` sometimes appears as `"729"`; `isco_code`'s Major Group 0 — Armed
forces — codes like `"0110"` appear as `"110"`). Confirmed by checking that
the "short" codes are exclusively the divisions/major-groups that start
with a real `0`, not random truncation. Both classification functions
zero-pad to 4 digits before reading the leading digits, so this doesn't
silently misclassify — e.g. `"729"` correctly resolves to division 07
(section B, Mining and quarrying), not division 72. Result: **4,789 of
4,789** `ind` rows with a code got a section/major-group classification —
full coverage, including the one 5-digit anomaly (`"61111"`, likely a
typo), which best-effort-classifies on its leading digit.

## Course-correction (self-audit)

A self-audit of the first pass of `clean.py` found the same underlying
mistake in four places: a check or correction that could never have caught
a real problem even if one existed, because of how it was scoped or
ordered. The standard applied to find and fix all four: *after a check
reports "no problems," would it have caught one if it existed?*

1. **Ordering bug**: the `q3_03`+`q3_04` vs. `q3_05` consistency check ran
   *after* the `99` sentinel correction, so the 6 rows it should have
   flagged were already corrected to `NaN` before the check ever saw them
   — a check validating already-cleaned data can't flag the very rows the
   cleaning explained. Fixed by running `check_usual_hours_consistency()`
   once, deliberately, on the raw data before any correction — it's a
   diagnostic now, not part of the ongoing flagged-for-review output.
2. **Tautological check**: `q3_09` (main-job actual hours) is a
   CAPI-*computed* total — the questionnaire sums `q3_07_1..7` for you, it
   isn't independently asked. The old check compared `q3_09` to the sum of
   its own components, which is true by construction on genuine data and
   can never fail. Removed; replaced by `recompute_derived_hours()`, which
   treats `q3_09`/`q3_10`/`q3_05` as derived fields to be *recalculated*
   from cleaned components, not raw totals to be validated. NaN propagates
   deliberately — a week with one unknown day doesn't get to report a true
   weekly total.
3. **Sentinel not generalized**: the `-1` "don't know" convention verified
   for age was never checked against the hours-worked block. It turned out
   to be live, uncorrected, in all seven daily-hours columns (`q3_07_1..7`)
   and `q3_08`. Fixed by `correct_negative_one_hours_sentinel()` — the same
   mechanism as the age correction, applied to the columns where it
   actually occurs.
4. **Wrong rows inspected**: the employment skip-logic check required a
   literal `"No"` on all four screening questions (q2_04/05/07/10) before
   flagging a filled-in `isco_code` as a violation. But the CAPI skip logic
   leaves most genuinely not-employed respondents *blank* on these
   questions instead of an explicit "No" — 48% of not-employed rows have
   all four blank. Blank silently failed the old equality check, so those
   rows were never inspected at all. Treating blank the same as "No"
   surfaced the 23 rows the old version missed entirely. Tracing those 23
   by hand found every one has `q2_06` answered (an informal
   cooking/handicraft-for-sale question that independently routes to job
   coding, correctly skipping q2_07/q2_10) — `q2_06` wasn't in the original
   check at all. With it included, the complete, correct version finds
   **0** unexplained violations, not 23: the 23 were gaps in the *check*,
   not in the data.

**Two smaller items** addressed in the same pass:

- `Scripts/run_pipeline.py` added as the single command entry point the
  brief calls critical (Section 2.2.1).
- `panelid` looks like a unique respondent ID but isn't — only 18 distinct
  values across 13,853 rows. Not used as a merge key anywhere in this
  pipeline, so it's harmless as-is; now documented in the problem
  inventory so it isn't mistaken for a real ID and used as one later.

## Charts

```bash
python Scripts/ingest.py     # must run first
python Scripts/diagnose.py   # needed for the near-duplicate/consolidation input clean.py uses
python Scripts/clean.py      # must run first -- isic_section/isco_major_group and sentinel corrections only exist post-cleaning
python Scripts/visualize.py
```

Six charts, saved as JPEG to `Outputs/charts/`, read from
`Outputs/typed/ind_cleaned.parquet` (so every chart reflects the corrected
data — no `99`/`-1` sentinels skewing anything):

**Three donuts** (2–7 categories each) — `sex_distribution.jpg`,
`age_group_distribution.jpg`, `employment_status_distribution.jpg`. A
centered total-N figure, every wedge externally labeled (name, count, %) on
a leader line rather than a legend box, fixed-order categorical hues for
the two nominal variables (each category is a genuinely distinct identity)
but a single light→dark blue ramp for age group (ordinal — the gradient
reads as a progression). Label placement spaces labels evenly within each
side (left/right) rather than at each wedge's raw angle, which matters for
the employment-status chart where two small adjacent wedges (4.6% and
5.7%) would otherwise collide.

**Two horizontal bar charts** — `isic_section_distribution.jpg` (21
categories) and `isco_major_group_distribution.jpg` (10 categories). A
donut was the wrong form here: the dataviz skill's series-count ladder caps
meaningful multi-color categorical identity around 7–8 slots, and both of
these exceed it. Single hue, axis labels carry identity, sorted
largest-first. Figure height scales with total *wrapped line count*, not
just category count — one ISIC section name is over 100 characters and
wraps to several lines; sizing by category count alone caused real label
collisions with short neighboring labels, caught by actually rendering and
looking at the first version.

**One histogram** — `hours_worked_distribution.jpg` (`q3_03`, usual hours
per week, main job): the brief's chart requirements explicitly call for a
distribution of key numeric variables, which none of the categorical forms
above can show. Mean line at 44.5 hours; visible spike at the standard
40-hour week.

Note: the project's dataviz skill recommends a horizontal stacked bar over
a pie/donut for part-to-whole comparison generally — bar length is easier
to judge precisely than wedge angle. Donuts were a deliberate choice for
the three low-cardinality (2–7 category) variables; the two
higher-cardinality variables (ISIC, ISCO) use bars for exactly that reason.

`Scripts/visualize.py` reuses `diagnose.py`'s
`value_counts_labeled()`/`age_group_distribution()` rather than
recomputing anything, so the chart numbers always match the diagnostics
report (for sex/age/employment) or the cleaned data directly (for
ISIC/ISCO/hours, which don't exist pre-cleaning).

## Metadata-exploration helpers (`Scripts/ingest.py`)

All of these take `(name, config.DATASETS)` unless noted:

- `load_dataset(name, datasets)` — returns the loaded DataFrame (all columns as strings)
- `load_dictionary(name, datasets)` — returns the raw dictionary (column, description, type, choices)
- `get_fields(df)` — list of column names
- `get_num_fields(df)` — column count
- `get_dtypes(df)` — current pandas dtype per column (all `object`, since everything loads as string)
- `get_documented_types(name, datasets)` — the dictionary's declared Stata type per column
- `recommend_dtypes(name, datasets)` — per column: declared Stata type, recommended pandas dtype, and why
- `apply_dtypes(df, name, datasets)` — applies those recommendations to a loaded DataFrame; returns `(typed_df, coercion_report)`, does not modify `df` in place
- `render_coercion_report(name, coercion_report)` — markdown summary of `apply_dtypes()`'s coercion report
- `verify_counts(name, df, expected_counts)` — row/household counts vs. `config.EXPECTED_COUNTS`

Example:

```python
import sys; sys.path.insert(0, "Scripts")
import config
from ingest import load_dataset, get_fields, get_num_fields, recommend_dtypes

df = load_dataset("ind", config.DATASETS)
print(get_num_fields(df), "fields")
print(get_fields(df))
print(recommend_dtypes("ind", config.DATASETS))
```

## Verifying output

Run `python Scripts/ingest.py` and check:

1. It exits without raising — a column mismatch (CSV vs. dictionary) or a
   row/household count mismatch (vs. the methodological report) raises
   immediately rather than continuing on unverified data.
2. `Outputs/logs/<name>_ingest.log` — states rows/columns/households loaded
   and, for `ind`, whether they match the report's documented sample
   (3,783 households / 13,853 individuals). `emig` has no equivalent
   documented figure, so its counts are logged without a pass/fail.
3. `Outputs/interim/<name>_raw.parquet` exists and is non-trivial size.
4. `Outputs/logs/<name>_dtype_coercion.log` — one row per column: dtype
   applied, how many values were missing before conversion, and how many
   *new* NaNs the conversion introduced (a value that existed in the raw
   string data but didn't parse as the target type). Currently 0 for every
   column in both datasets — confirms the dtype recommendations match what's
   actually in the data, not just what the dictionary says it should be.
5. `Outputs/typed/<name>_typed.parquet` — load it and check `.dtypes`; should
   match `recommend_dtypes()`'s `recommended_dtype` column exactly.

## Data types: recommended and applied

`recommend_dtypes()` computes the advice below; `apply_dtypes()`/`type_dataset()`
actually apply it (this is real conversion now, not advisory-only). Verified
result: 0 columns in either dataset had coercion introduce a new NaN, so
every recommendation held up against the real data.

Both dictionaries' `type` column is a Stata storage type, not a pandas one.
General rule, derived from that column plus whether a `choices` label-set is
documented:

| Stata type | Has `choices`? | Recommended pandas dtype | Why |
| --- | --- | --- | --- |
| `byte` | yes | `category` | Coded categorical response (e.g. `q1_03` Sex, label-set name `Sex` — see note below) |
| `byte` | no | `Int8` (nullable) | Small numeric count (age, hours/week, block, week) |
| `int` | — | `Int32` (nullable) | Larger numeric (panel ID, quarter, total hours, emigration year) |
| `long` | — | `Int64` (nullable) | Monetary amounts (income, pensions, transfers) — can be large |
| `float` / `double` | — | `float64` | Weight, PSU centroid lat/long |
| `strN`, N ≤ 20 | — | `string` | Short code/ID field — keep as string, leading characters matter (e.g. region `"01"`) |
| `strN`, N > 20 | — | `string`, but low priority | Free-text field — see below |

**Correction from earlier exploration:** we'd previously flagged that the
CSV dictionaries only name a value-label *set* (e.g. `Sex`), not its actual
codes, and that `ind` has no `.dta` to resolve real labels from. Turns out
this doesn't matter in practice — verified empirically that every `category`
column's raw CSV values are **already the resolved label text** (`q1_03`
contains `"Male"`/`"Female"` directly, not `"1"`/`"2"`; same for
`domain`, `area`, `zone`, `q1_02`, `q3_16`, etc.). Stata's export wrote out
labeled values rather than raw codes. So `category` dtype is still the
right call, but there's no code→label mapping step needed at all — the data
is human-readable as-is.

Counts from `recommend_dtypes("ind", ...)`: 99 categorical, 31 monetary
(`Int64`), 20 small counts (`Int8`), 14 string/ID, 8 `Int32`, 3 `float64`.

**Free-text fields** (`ind`: `q2_02`, `q3_15b`, `q3_30`, `q3_31`, `q3_32`,
`q3_33`; `emig`: `q7_08`, `q7_15`) have no coded companion and no realistic
way to standardize under "basic methods only" (no NLP). Keep them for
context/reporting, but they're poor candidates for cleaning/imputation
effort unless your assigned scope specifically names one.

**Two dictionary quirks worth knowing about, not treating as real signal:**

- `q3_29` and `q3_36` are typed as short strings (`str3`, `str9`) rather than
  `byte`/`category` even though they're "check all that apply" questions in
  the original questionnaire — the export likely concatenates selected
  option digits into one string (e.g. `"12"` = options 1 and 2). Don't treat
  them as free text or as a single numeric code.
- Within the otherwise-parallel `q6_04a`–`f` and `q6_05a`–`i` groups (income
  and in-kind compensation amounts), most fields are `long` but `q6_04e` is
  `int` and `q6_05f` is `byte` — almost certainly just narrower ranges
  observed in this quarter's data, not a real difference in what the field
  means. Treat the whole group consistently (`Int64`) rather than following
  the dictionary literally column-by-column.

## Diagnostics findings (from `python Scripts/diagnose.py`)

- **Duplicates**: none. `hhid`+`member` (`ind`) and `hhid`+`emig` (`emig`)
  are both reliable natural keys with zero duplicate rows.
- **Range checks**: `q1_04` (Age, `ind`, 12 rows) and `q7_06` (Age, `emig`,
  28 rows) each flagged values outside `[0, 115]` — but every single flagged
  value is exactly `-1` in both cases. That's a missing/"don't know"
  sentinel (the same convention the questionnaire documents explicitly for
  `q7_09`), not a real data error — treat `-1` as `NaN` when cleaning these
  two columns, don't leave it as a literal age. Hours-worked and weight had
  no flags.
- **Missingness**: heavily dominated by expected survey skip patterns —
  60 `ind` columns are >90% missing, almost entirely `q6_*` income
  sub-questions that only apply to people with that specific income source.
  This is structural, not a quality problem, but per the brief
  ("distinguish structural missing from incidental where possible") each
  variable in the final assigned cleaning scope should get that distinction
  made explicitly rather than assumed.
- **Sex** (`q1_03`): 51.1% female / 48.9% male, 0 missing — balanced, no
  coverage concern.
- **Age groups** (`q1_04` bucketed): 0–14 is the largest single group
  (27.1%) — expected, since demographics are collected for every household
  member regardless of age, not just the working-age population.
- **Employment status, main job** (`q3_16`): dominated by "Employee" (66.2%
  of valid responses), then self-employed without paid help (23.5%);
  self-employed with paid help and unpaid family workers are both under 6%.
  9,064 rows (65.4%) have no value here at all — correctly so, since `q3_16`
  only applies to people who reported having a main job; don't treat that as
  missing data to impute.

## Keep/drop guidance

The *public* dataset already excludes every administrative/CAPI/PII field
(interviewer identity, device IDs, passwords, respondent names, timestamps,
etc.) that appears in the restricted codebook — everything in
`Data/glfs-174-*-public-dictionary.csv` is either a design/identifier
variable or actual survey content. There is no "obviously drop this" admin
clutter left to prune.

What that leaves to decide:

- **Always keep**: `hhid`, `weight`, `stratum`, `psu`, `domain`, `region`,
  `area`, `zone` — sample design and identifier variables. The brief says
  not to *apply* weights, but preserve them regardless.
- **Keep, core content**: every coded (`category`) and numeric response
  column — this is the actual labor force data the survey exists to collect.
- **Keep but deprioritize**: the free-text fields listed above.
- **Scope-dependent**: don't drop or expand beyond whatever specific
  variables the evaluating office assigns for the cleaning phase (not yet
  received — flagged as an open item). Use `get_fields`/`recommend_dtypes`
  to explore the full set now; the real keep/drop decision for *cleaning
  effort* happens once that scope arrives.
