# GLFS Data Cleaning & Imputation Pipeline

Bureau of Statistics — Guyana, Analytical Unit Technical Capability Assessment.
Dataset: GLFS 2017 Q4 microdata (round 174), two tracks — individual records (`ind`)
and the household emigration module (`emig`).

## Status

All ten build steps in the brief's Section 2.1 are implemented, wired into
a single entry point, and verified end to end from a clean checkout:
ingest → diagnose → clean → problem inventory → impute → data dictionary →
export → automated report → charts. Every stage below is real, run, and
documented with its actual output — nothing here is aspirational.

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
- `Scripts/impute.py` — basic imputation on the cleaned dataset (brief
  Step 7 / Section 3.3), scoped to the same named variables as the problem
  inventory: median imputation for age and hours worked, restricted to
  each variable's actual applicable population; industry/occupation left
  missing (confirmed structural); every imputed value tracked in a
  `<column>_imputed` flag column
- `Scripts/data_dictionary.py` — the data dictionary deliverable (brief
  Step 8 / Section 4.2): one row per variable, covering every column in
  the final dataset (not just the cleaning/imputation-scope ones) — type,
  label, observed value set/range, % missing raw vs. after cleaning,
  imputation treatment, and notes
- `Scripts/export.py` — the four-format export deliverable (brief Step 9 /
  Section 4.1): `.parquet`, `.xlsx` (data + data dictionary sheets),
  `.sav`, and `.dta` (variable labels on every column, value labels on the
  ten imputation-flag columns), all written from the final imputed
  dataset and round-trip-verified after writing
- `Scripts/report.py` — the automated Word report (brief Step 10 /
  Section 4.3): a `.docx` per dataset covering all six required sections,
  with five charts drawn fresh from the final data by this module's own
  matplotlib code (not copies of visualize.py's JPEGs) — every number in
  the report is computed at render time, none hand-typed
- `Scripts/visualize.py` — renders six distributions (sex, age group,
  employment status, ISIC section, ISCO major group, hours worked) as JPEG
  charts
- `Scripts/run_pipeline.py` — the single command entry point (brief
  Section 2.2.1): runs ingest → diagnose → clean → problem inventory →
  impute → data dictionary → export → report → charts, for both datasets,
  in that order
- `Outputs/` — regenerated end to end by `python Scripts/run_pipeline.py`

See `CLEANING_PLAN.md` for the full design/reasoning behind the cleaning
stage before it was built, and [Course-correction](#course-correction-self-audit)
below for a self-audit pass that found and fixed four checks that had lost
their diagnostic power. All ten build-brief steps (Section 2.1) are now
implemented.

### Contents

- [Folder layout](#folder-layout)
- [Setup](#setup)
- [Reproduce everything](#reproduce-everything) — start here to regenerate every deliverable from a clean checkout
- [Running the whole pipeline](#running-the-whole-pipeline)
- [Running ingest](#running-ingest)
- [Running diagnostics](#running-diagnostics)
- [Problem inventory](#problem-inventory)
- [Running cleaning](#running-cleaning)
- [Running imputation](#running-imputation)
- [Running the data dictionary](#running-the-data-dictionary)
- [Running the export](#running-the-export)
- [Running the report](#running-the-report)
- [Course-correction (self-audit)](#course-correction-self-audit)
- [Charts](#charts)
- [Metadata-exploration helpers](#metadata-exploration-helpers-scriptsingestpy)
- [Verifying output](#verifying-output)
- [Data types: recommended and applied](#data-types-recommended-and-applied)
- [Diagnostics findings](#diagnostics-findings-from-python-scriptsdiagnosepy)
- [Keep/drop guidance](#keepdrop-guidance)

## Folder layout

```text
Data/                       raw GLFS CSVs + data dictionaries + methodological report + official ISIC/ISCO structure files (never edited in place)
Scripts/
  config.py                  every path used by the pipeline, in one place
  ingest.py                  load + validate + verify counts + dtype recommend/apply + metadata-exploration helpers
  diagnose.py                missingness (+structural/incidental) + duplicates + range checks + near-duplicates + casing check + named-variable distributions
  problem_inventory.py        written, counted data-quality findings for sex/age/hours/ISIC/ISCO/panelid
  clean.py                   dedup removal + sentinel corrections + derived-hours recomputation + validation rules (flag/correct) + auto-consolidation + ISIC/ISCO classification + parquet/xlsx export
  impute.py                   median imputation (age, hours worked) scoped to each variable's applicable population + imputed-flag columns + re-derives hours totals
  data_dictionary.py          one row per variable (type/label/value set/% missing raw+cleaned/imputation treatment/notes) -> CSV + xlsx
  export.py                   final dataset -> .parquet + .xlsx (data + dictionary sheets) + .sav + .dta, with variable/value labels, round-trip verified
  report.py                   automated Word report (.docx) per dataset, 5 fresh matplotlib charts, every figure computed at render time
  visualize.py                renders six distributions as JPEG charts (3 donut, 2 bar, 1 histogram)
  run_pipeline.py              single entry point -- runs every stage above in order
Outputs/
  interim/                    raw string-typed parquet cache (untouched safety net, gitignored)
  typed/                      dtype-converted parquet (<name>_typed.parquet), cleaned parquet (<name>_cleaned.parquet), and imputed parquet (<name>_imputed.parquet), gitignored
  diagnostics/                 diagnostics report (.md) + missingness table (.csv) per dataset
  problem_inventory/           problem inventory report (.md)
  data_dictionary/             data dictionary (.csv + .xlsx) per dataset
  export/                     the four required formats (.parquet/.xlsx/.sav/.dta) per dataset -- the actual Section 4.1 deliverable
  report/                     the automated Word report (.docx) per dataset -- the Section 4.3 deliverable
  charts/                      six distribution charts (.jpg)
  logs/                       ingest/dtype/cleaning/imputation/data-dictionary/export/report logs, flagged-for-review CSVs, near-duplicate and casing-check CSVs
  <name>_cleaned.xlsx          the fully cleaned dataset, one file per dataset (tracked, not gitignored)
```

## Setup

Requires Python 3.10+ (developed and tested on 3.12).

```bash
python -m pip install -r requirements.txt
```

No other setup — no database, no API keys, no cloud service, no separate
Quarto/R install. Everything runs locally against the CSVs already in
`Data/` (brief Section 2.2.2: "locally reproducible... no cloud services,
no remote databases, no API keys").

## Reproduce everything

The short version, for a reviewer who just wants the outputs:

```bash
python -m pip install -r requirements.txt
python Scripts/run_pipeline.py
```

One command, ~2 minutes (most of it is writing the 189-column `.xlsx`/`.sav`
exports). No arguments, no manual steps in between, no cell-by-cell
notebook to babysit — this is the brief's Section 2.2.1 "single-command
run" requirement.

What you'll have afterward, all under `Outputs/` (see
[Folder layout](#folder-layout) above for the full map):

| Deliverable | Where | Brief reference |
| --- | --- | --- |
| Cleaned + imputed data, 4 formats | `Outputs/export/<name>_final.{parquet,xlsx,sav,dta}` | Section 4.1 |
| Data dictionary | `Outputs/data_dictionary/<name>_data_dictionary.{csv,xlsx}` | Section 4.2 |
| Automated Word report | `Outputs/report/<name>_report.docx` | Section 4.3 |
| Problem inventory | `Outputs/problem_inventory/ind_problem_inventory.md` | Build Step 5 |
| Diagnostics | `Outputs/diagnostics/<name>_report.md` + `.csv` | Build Step 4 |
| Charts | `Outputs/charts/*.jpg` | Section 4.3's chart requirements |
| Every intermediate log | `Outputs/logs/*.log`, `*.csv` | Section 2.2.2 "logged" requirement |

`<name>` is `ind` or `emig` — both tracks run automatically, no flag
needed. If anything fails partway, it fails loudly with a traceback and a
stage label (`=== N/9 stage-name ===` printed just before each stage
starts) rather than continuing on bad data — see
[Verifying output](#verifying-output) for what a *successful* run's logs
should say.

To rebuild one stage in isolation while iterating instead of the whole
pipeline, see that stage's own section below — each one lists its exact
upstream dependency (e.g. `python Scripts/clean.py` needs `ingest.py` to
have produced the typed parquet first) and can be run on its own with
`python Scripts/<stage>.py`.

## Running the whole pipeline

```bash
python Scripts/run_pipeline.py
```

The single entry point the brief requires (Section 2.2.1: "there must be
one entry point... that executes every stage in the correct order"). Runs
ingest (raw caching *and* dtype typing — see [Running ingest](#running-ingest)) →
diagnose → clean → problem inventory → impute → data dictionary → export →
report → charts for both datasets, in the order each stage actually
depends on the one before it, and regenerates everything under `Outputs/`.
The per-stage sections below document what each step does and how to run
it individually while iterating.

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
  the noisier 0.95–0.97 band (everything the near-duplicate detection below
  finds but doesn't auto-merge) stays flag-only in `near_duplicates.csv`
  for manual review, not auto-merged.
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

## Running imputation

```bash
python Scripts/clean.py      # must run first -- impute.py reads the cleaned output
python Scripts/impute.py
```

Brief Step 7 / Section 3.3 ("pick the method that fits the variable type
and the missingness pattern; brief justification is enough"), scoped to
the same named variables as the problem inventory. Writes
`Outputs/typed/<name>_imputed.parquet` and
`Outputs/logs/<name>_imputation.log` (before/after counts and the method
used for every variable, including the ones deliberately left missing).

Method chosen per variable, checked against the actual cleaned data before
deciding, not assumed:

- **Age** (`q1_04` `ind` / `q7_06` `emig`) — median. Both numeric with a
  real right skew after `clean.py`'s `-1` sentinel correction (`ind`: 12
  missing, mean 30.7 vs. median 26.0, skew 0.52; `emig`: 28 missing, mean
  39.7 vs. median 38.0, skew 0.29) — the brief calls out median for
  "numeric variables with skew or outliers."
- **Hours worked, main job** (`q3_03`) and the **seven daily hours
  columns** (`q3_07_1..7`) — median, restricted to respondents who
  actually have a main job (`q3_16` not null): 88 rows for `q3_03`, 14–15
  per daily column, all genuinely incidental gaps left by `clean.py`'s
  sentinel corrections.
- **Hours worked, other job actual** (`q3_08`) — median, restricted to the
  much narrower population that actually has a second job (`q3_01 ==
  "Yes"`, n=163). Imputing over the "has a main job" population instead
  (like `q3_03`) would have manufactured **4,626** fake values for people
  never asked the question — scoped correctly, only **1** row is
  genuinely incidental.
- **Hours worked, other job usual** (`q3_04`) — **left missing**. 100% of
  its missingness (13,690 of 13,853 rows) is structural, gated by
  `q3_01 == "Yes"`; confirmed 0 incidental gaps among the 163 rows the
  question actually applies to.
- **`q3_05`/`q3_09`/`q3_10`** (all-jobs usual/actual totals) — not
  independently imputed. These are derived fields; `clean.py`'s
  `recompute_derived_hours()` is re-run after the base components above
  are imputed, so the totals reflect the now-more-complete data (`q3_09`:
  17 rows changed, `q3_10`: 3, `q3_05`: 2) instead of carrying stale `NaN`.
- **Industry** (`isic_code`) **/ Occupation** (`isco_code`) — **left
  missing**. Confirmed structural: missingness (9,064 rows) exactly
  matches the population with no main job. Imputing a job classification
  for someone never asked about a job would invent data, not fill a gap.
- **Sex** (`q1_03`) — 0 missing in the cleaned data; nothing to impute.

Every imputed value is tracked in a companion `<column>_imputed` boolean
column (10 added to `ind`, 1 to `emig`), so the eventual report step can
chart observed-vs-imputed values (brief Section 4.3) without re-deriving
which rows were touched. Medians are rounded to the nearest whole number
before filling — every column imputed here is a whole-number nullable
`Int8` (years, hours), and an even-count median can otherwise land on a
`.5` the column's dtype can't hold.

## Running the data dictionary

```bash
python Scripts/impute.py     # must run first -- data_dictionary.py reads typed/cleaned/imputed
python Scripts/data_dictionary.py
```

Brief Step 8 / Section 4.2: "one row per variable: name, type, label,
valid range or value set, % missing in raw data, % missing after
cleaning, imputation treatment, notes... included as a sheet in the Excel
output and also saved as CSV." Writes
`Outputs/data_dictionary/<name>_data_dictionary.csv` and the same table as
a single-sheet `<name>_data_dictionary.xlsx` (sheet name
`data_dictionary`) — the export stage (brief Step 9) will merge this sheet
into the final combined workbook alongside the data, reusing this same
function rather than rebuilding it.

Deliberately covers **every** column in the final dataset (189 for `ind`,
29 for `emig`), not just the five cleaning/imputation-scope variables — a
reviewer needs to understand the whole exported file, not only the part
this project's cleaning touched. For the ~180 columns outside that scope,
the dictionary says so honestly ("Not imputed — outside assigned
cleaning/imputation scope") rather than inventing a finding; it still
picks up real, programmatically-verifiable context for free where it
applies — free-text columns note the auto-consolidation, monetary columns
note the IQR outlier check, and columns in `config.SKIP_PATTERNS` note
their structural gate.

"Raw" means `Outputs/typed/<name>_typed.parquet` — right after `ingest.py`'s
dtype conversion, before `clean.py` has touched a single sentinel value —
since the true raw CSV (all-string dtype) would give a less meaningful
type/range reading. Columns `clean.py`/`impute.py` added (the four
ISIC/ISCO classification columns, the ten `<column>_imputed` flags) didn't
exist at that point, so their raw-missingness cell reads "N/A (derived
column)" rather than a fabricated number.

## Running the export

```bash
python Scripts/data_dictionary.py   # must run first -- export.py reuses its labels + table
python Scripts/export.py
```

Brief Step 9 / Section 4.1: "the cleaned dataset must be exported in all
four formats, with variable labels and value labels preserved where
supported." Reads `Outputs/typed/<name>_imputed.parquet` — the fully
cleaned *and* imputed data, since Step 7 (impute) runs before Step 9
(export) in the brief's own build order; Section 4.1's "cleaned dataset"
phrase is read here as "the final processed dataset," not a pre-imputation
snapshot. Writes to `Outputs/export/<name>_final.<ext>`:

- **`.parquet`** — `pandas.to_parquet()`, no conversion needed.
- **`.xlsx`** — data on one sheet, the data dictionary on a second (per
  the brief's Table 4), via `data_dictionary.build_dictionary()` rather
  than a second copy of that logic.
- **`.sav` / `.dta`** — `pyreadstat`. Verified by round-tripping a sample
  first rather than assuming: every pandas nullable dtype this pipeline
  uses (`Int8`/`16`/`32`/`64`, `boolean`, `category`, `string`) is handled
  correctly on its own — nullable integers become `float64` with real
  `NaN` preserved; category/string columns keep their text, with missing
  values round-tripping as an empty string rather than `NaN` (the standard
  SPSS/Stata convention for missing string data, not a defect introduced
  here). Stata version is left at `pyreadstat`'s default of 15, matching
  the brief's own "Stata v15+ recommended for Unicode."

**Variable labels** are attached to all 189 (`ind`) / 29 (`emig`) columns,
reusing `data_dictionary.column_labels()` — the exact same labels
documented in the data dictionary, not a second copy that could drift
from it.

**Value labels** are a numeric-variable-only feature in both formats.
This dataset's categorical columns already store resolved label *text*,
not numeric codes — confirmed back in the diagnostics stage (the source
dictionaries only name a Stata label-*set*, e.g. `"yesno"`; the exported
values are already `"Male"`/`"Female"`, never a code needing a lookup) —
so there is no code → label mapping to preserve for them. The one place
this genuinely applies: the ten (`ind`) / one (`emig`) `<column>_imputed`
flag columns, recoded from `True`/`False` to `1`/`0` specifically so a
real value-label pair can be attached (`{0: "Not imputed", 1: "Imputed"}`)
— a plain boolean column can't carry a value label in either format.

**Verified**: every format is read back immediately after writing and its
shape checked against the source dataframe (`Outputs/logs/<name>_export.log`);
`.sav`/`.dta` metadata was additionally spot-checked by hand — `q1_04`'s
label round-trips as `"Age"`, and `q1_04_imputed`'s value labels round-trip
as `{0: "Not imputed", 1: "Imputed"}` in both formats.

## Running the report

```bash
python Scripts/export.py    # must run first -- report.py reads typed/cleaned/imputed
python Scripts/report.py
```

Brief Step 10 / Section 4.3: an automated Word report, rendered by the
pipeline itself, "no manual copy-paste of figures or numbers." Writes
`Outputs/report/<name>_report.docx` with all six required sections:

1. **Dataset overview** — source, size, variable scope, and the raw CSV's
   first git-commit date (queried live via `git log`, not hand-typed —
   there is no separate download timestamp to log).
2. **Data quality diagnostics (before cleaning)** — every count in the
   bullet list and the missingness-overview chart is recomputed from
   `Outputs/typed/<name>_typed.parquet` at render time.
3. **Cleaning decisions** — a table built by re-running the same
   `clean.py` functions used in the real cleaning stage
   (`flag_monetary_outliers()`, `check_employment_skip_logic()`) rather
   than re-deriving the logic a second time or hardcoding last-run's
   numbers.
4. **Imputation applied** — reuses `impute.py`'s `<column>_imputed` flag
   columns; the "applicable population" per variable is generated from a
   small classifier, not a copy-pasted sentence repeated for every row.
5. **Post-cleaning summary** — final row/column counts, summary
   statistics, and two distribution charts (age, hours worked).
6. **A chart that tells a story** — employment status (`ind`) / most
   important reason for emigrating (`emig`), a genuinely substantive
   categorical breakdown, not a repeat of an earlier chart.
7. **Limitations and known risks** — the same honest scope boundaries
   documented throughout this README (bounded `SKIP_PATTERNS` coverage,
   `>=0.98`-only auto-consolidation, median-only imputation, IQR-flagged
   monetary fields, `panelid`'s misleading name).

**Charts**: five per report (missingness before/after, observed-vs-imputed
for one imputed variable, two numeric distributions, one categorical
"chart of choice") — all five drawn by this module's own matplotlib code
against the final data, satisfying the brief's "charts must be reproduced
directly from the cleaned dataset by the rendering step itself... pasted
static images do not count." Reuses `visualize.py`'s already-validated
palette (dataviz skill) for a consistent theme rather than picking new
colors.

**python-docx over Quarto**: this project has used python-docx throughout
(the three weekly reports); there is no existing Quarto/Jupyter setup to
add, and the brief lists python-docx as an equally acceptable option.

**Rendered and looked at, not just run**: the first version had a legend
overlapping a bar on the single-variable `emig` chart, a repeated
boilerplate sentence copy-pasted across ten table rows, an un-substituted
`<name>` placeholder, and two evidence numbers ("0 of 4,789...", "see the
log file") that were typed by hand instead of computed — all four were
only caught by exporting the actual `.docx` to PDF and inspecting every
page, not by reading the code.

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
- **Scope-dependent**: this project treated sex (`q1_03`), age (`q1_04`/
  `q7_06`), hours worked (`q3_03` and related columns), industry
  (`isic_code`), and occupation (`isco_code`) as the working cleaning/
  imputation scope throughout — the same five named variables
  `problem_inventory.py` documents findings for. No separate scope
  assignment arrived from the evaluating office during this build; if one
  ever does and it differs, `config.py`'s column lists
  (`SKIP_PATTERNS`/`FREE_TEXT_COLUMNS`/`MONETARY_COLUMNS`) and the hardcoded
  variable names in `clean.py`/`impute.py`/`problem_inventory.py` are the
  places to re-scope. Every other column stays fully documented (use
  `get_fields`/`recommend_dtypes`, or just read
  `Outputs/data_dictionary/<name>_data_dictionary.csv`) but untouched by
  cleaning.
