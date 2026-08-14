# Cleaning Stage — Implementation Plan

**Status: implemented** (`Scripts/clean.py`, plus extensions to
`Scripts/diagnose.py` and `Scripts/config.py`). This document is kept as
the design record; see the README's "Running cleaning" section for what
actually shipped, including a few corrections made during implementation
(the `SKIP_PATTERNS` table lost 3 entries that turned out not to be
single-parent gates, and the near-duplicate threshold moved from 0.90 to
0.95 after checking real output).

Original framing, unchanged below: this was written as a document only, no
code touched, for review before anything got implemented.

## Ground rules

- Targets the **existing** pipeline skeleton at the project root — `Data/`,
  `Scripts/`, `Outputs/`. No new folders. New capability goes into new
  **files** inside these existing folders, following the same pattern as
  `config.py` / `ingest.py` / `diagnose.py` / `visualize.py`.
- Draws selectively on the separate `Cleaning data/` reference project's
  *approach* (arithmetic consistency checks, a flagged-for-review output
  pattern, sentinel-code scanning) where it's genuinely useful, adapted to
  our actual 175-column real dataset and our own tooling (CSV/parquet, not
  Excel) — not copied wholesale, since that project was built against a
  different, smaller demo dictionary with no real response data loaded.
- Still open: the evaluating office hasn't sent the assigned cleaning-scope
  variables. Every design below defaults to operating on the full dataset
  (matching how `ingest.py`/`diagnose.py` already work), but should be
  re-scoped down to just the assigned variables once known — see the open
  questions at the end.

## File plan (no new folders)

| File | Status | What changes |
|---|---|---|
| `Scripts/config.py` | extend | new path entries (existing folders, new filenames) + new `SKIP_PATTERNS` / `VALUE_MAPPINGS` dicts |
| `Scripts/ingest.py` | no change | type coercion + NA reporting already live here — see Part 1 |
| `Scripts/diagnose.py` | extend | add structural/incidental missingness classification, a free-text near-duplicate finder, and a casing-consistency check — all stay read-only |
| `Scripts/clean.py` | **new file** | the actual value-changing operations: dedup removal, rule-based flag/correct, mapping application |
| `requirements.txt` | extend | add `rapidfuzz` |

Outputs land in existing folders: `Outputs/typed/` gets a new
`<name>_cleaned.parquet` per dataset (sits next to the existing
`<name>_typed.parquet`); `Outputs/logs/` gets new log/CSV files
(`<name>_cleaning.log`, `<name>_flagged_for_review.csv`,
`<name>_near_duplicates.csv`). No new subfolders anywhere.

---

## 1. Type conversion + coercion-NA reporting — already built

Checking what you asked for against what already exists:

- *"Identify all variables"* → `get_fields()` / `get_num_fields()` /
  `recommend_dtypes()` in `Scripts/ingest.py` already enumerate and classify
  every column (175 `ind`, 28 `emig`).
- *"create a script to convert columns from metadata into appropriate
  types"* → `apply_dtypes()` / `type_dataset()` in `Scripts/ingest.py`.
- *"report columns where coercion created NAs"* → `render_coercion_report()`,
  written to `Outputs/logs/<name>_dtype_coercion.log`.

Verified result (already run): **0 columns** across all 203 columns had
coercion introduce a new NaN.

One thing worth deciding now, informed by the diagnostics findings: `q1_04`
(age, `ind`) and `q7_06` (age, `emig`) both use `-1` as a "don't know"
sentinel, which survives type conversion as a literal `-1`, not `NaN` —
coercion only reports values that *fail* to parse, not values that parse
fine but are semantically a missing-value placeholder. Handling that is a
**cleaning** decision (Part 4 below), not a type-coercion one — flagged here
so it isn't lost between sections.

---

## 2. Missingness: structural vs incidental

### What exists now

`missingness_report()` in `diagnose.py` computes % missing per column — no
classification of *why* a value is missing.

### Design

Structural missingness = the question logically didn't apply to that
respondent (a skip pattern). Incidental = the question applied but wasn't
answered (real nonresponse). Telling these apart requires knowing, for each
column, which earlier answer "gates" it.

Building this for all 175 columns would mean reconstructing the entire GLFS
skip-pattern flow chart from the questionnaire (Annex 3) — a large,
error-prone undertaking and arguably scope creep before the assigned
variables are known. Instead:

**Bounded, verified approach**: build a small `SKIP_PATTERNS` table only for
gate relationships that are single-parent and explicitly documented in the
questionnaire text (the "Ask only if X" instructions in
`Data/glfs-q4-2017-methodological-report.pdf`, Annex 3) — a real, defensible
subset, not exhaustive, and this document says so plainly rather than
implying full coverage.

Confirmed single-parent gates:

| Dependent column(s) | Gate column | Applies when gate = |
|---|---|---|
| `q2_02`, `q2_03` | `q2_01` | "Yes" (received training) |
| `q1_12`–`q1_16` | `q1_11` | "Yes" (ever attended school) |
| `q3_04`, `q3_05` | `q3_01` | "Yes" (more than one job) |
| `q2_15` | `q2_14` | "Yes" (looked for job in last 30 days) |
| `q6_04a`…`q6_04f` | matching `q6_02a`…`q6_02f` | "Yes" (received that income type) |
| `q6_05a`…`q6_05i` | matching `q6_03a`…`q6_03i` | "Yes" (received that in-kind benefit) |
| `q3_18`, `q3_19` | `q3_16` | "Employee..." (written-contract questions only apply to employees) |

Everything else — including the more complex multi-path gates like `q3_16`
itself, which depends on a combination of `q2_04`/`q2_05`/`q2_07`/`q2_10` —
is reported as plain missingness without a structural/incidental label.

New function, `Scripts/diagnose.py`:

```python
def classify_missingness(df, dependent_col, gate_col, applies_when) -> dict:
    """Returns n_missing, n_structural (gate says 'doesn't apply' AND
    dependent is missing), n_incidental (gate says 'applies' AND dependent
    is still missing), pct_structural."""
```

Called once per row of the `SKIP_PATTERNS` table (living in `config.py`,
alongside `EXPECTED_COUNTS`), results folded into the existing diagnostics
report under a new "Missingness: structural vs incidental" section.

### Verify

For a known case like `q2_02`/`q2_03` gated by `q2_01`: `n_incidental`
should be at or near 0 (if someone said "Yes" to training, the CAPI
application should have forced the follow-up questions) — a nonzero
incidental count there would itself be a real finding worth reporting, not
a bug in the check.

---

## 3. Deduplication: exact-match (done) + approximate (new)

### Exact-match — already built

`find_duplicates(df, key_columns)` in `diagnose.py`, keyed on `hhid`+`member`
(`ind`) / `hhid`+`emig` (`emig`). Already run: **zero duplicates in either
dataset.** Nothing left to build except the *removal* logic for if a future
data pull does have exact duplicates — trivial
(`df.drop_duplicates(subset=key_columns, keep="first")`), goes in
`clean.py`, logged with a before/after row count per the brief's logging
requirement.

### Approximate matching — new, and scoped tightly

The brief caps this at Jaro/Jaro-Winkler/Levenshtein via `rapidfuzz` or
`jellyfish` — "do not go beyond this."

Where it actually applies here: **not** person-matching — the public
dataset has no name/address fields to fuzzy-match people on (stripped for
confidentiality). The legitimate use case is **free-text response
normalization** — finding near-duplicate *values* within a single free-text
column (e.g. job title `q3_32`: "Cashier" / "cashier" / "Cashier " are
probably the same real-world answer, entered inconsistently).

New function, `Scripts/diagnose.py` (still read-only — flags candidates,
doesn't merge anything):

```python
def find_near_duplicate_values(series, threshold=0.90) -> pd.DataFrame:
    """Unique non-null values in `series`, pairwise Jaro-Winkler similarity
    (rapidfuzz.distance.JaroWinkler.similarity), returns pairs >= threshold
    sorted by similarity descending. Only realistic for the free-text
    columns identified in ingest.py's recommend_dtypes() output
    (ind: q2_02, q3_15b, q3_30, q3_31, q3_32, q3_33; emig: q7_08, q7_15)."""
```

Applied to each of those 8 columns; results written to
`Outputs/logs/<name>_near_duplicates.csv` for manual review. This is
flag-only — the brief's "flag or correct, depending on what's defensible"
cuts toward *flag* here, since auto-merging free text on a similarity score
risks silently conflating genuinely different answers.

### Verify

Spot-check the top-scoring pairs by eye for at least one column (e.g.
`q3_32`) before trusting the threshold — 0.90 is a starting point, not a
validated constant.

---

## 4. Validate against obvious rules — flag or correct

### What exists now

`range_check()` in `diagnose.py`, currently applied to 4 `ind` fields (age,
two hours fields, weight) + 2 `emig` fields. Flags only, doesn't correct
anything.

### Extending it — three kinds of rule, each with an explicit flag-vs-correct call

**a) Range checks — extend coverage, mostly flag, one confirmed correct**

- The `-1` age sentinel (both datasets): already confirmed via `diagnose.py`'s
  `_describe_flagged()` that every flagged value is exactly `-1`.
  **Correct**: map to `NaN` — defensible because the pattern was verified,
  not guessed at.
- Monetary fields (`q6_01`, `q6_04a`–`f`, `q6_05a`–`i`, `q6_06`–`q6_24`,
  pensions): currently unchecked. Add an IQR-based outlier flag (the brief
  explicitly allows z-score or IQR for "outlier flagging") — **flag only**,
  per "flag; do not silently drop."

**b) Arithmetic consistency checks — flag only** (adapted from the
`Cleaning data/` reference project's Step 5, which identified real checks
specific to this exact questionnaire):

- `q3_05` (total usual hours, all jobs) should ≈ `q3_03` (main job) + `q3_04`
  (other jobs) — allow small rounding slack.
- `q3_09` (total actual hours, main job, last 7 days) should ≈ the sum of
  the seven daily columns `q3_07_1`…`q3_07_7`.

Both are internal-consistency checks on the *same respondent's own answers*
— a mismatch is either a data-entry error or an interviewer/CAPI issue,
always worth a human look, never worth auto-correcting (which of the two
conflicting numbers would even be "right"?).

**c) Skip-pattern logic checks — flag only**

- If `q2_04`, `q2_05`, `q2_07`, `q2_10` are all "No" (not employed, no
  business, no unpaid family work, not temporarily absent), then
  `q3_16`/`isco_code`/`isic_code` should all be empty. A violation means
  either a genuine data issue or a `q3_16` gate more complex than currently
  modeled — flag for review either way.

New function, `Scripts/clean.py`:

```python
def apply_validation_rules(df, name) -> tuple:
    """Returns (df_with_corrections_applied, flagged_rows). flagged_rows
    columns: row identifier (hhid+member), rule_name, detail. Only the
    confirmed-safe corrections (the age -1 sentinel) actually modify df;
    everything else is flag-only and left untouched."""
```

Mirrors the reference project's `flagged_for_review.xlsx` pattern:
`Outputs/logs/<name>_flagged_for_review.csv`, one row per flagged record
with a `rule_name` column so multiple flags on the same record stay
traceable.

### Verify

- Rerun `diagnose.py`'s range check on age after the `-1`→`NaN` correction —
  should report 0 remaining flags.
- Spot-check 5–10 rows from each arithmetic-consistency flag by hand against
  the raw CSV before trusting the check at scale.

---

## 5. Clean inconsistent codings — verify first, then build only if needed

### Important scoping note, based on what's already been found

The classic example (`"M"`/`"m"`/`"Male"` → `"Male"`) assumes raw numeric or
inconsistently-cased codes. This week's diagnostics already established that
the public CSVs' *coded* categorical fields are exported with the resolved
label text already applied consistently by Stata (e.g. `q1_03` only ever
contains exactly `"Male"` or `"Female"`, never a case/spelling variant) —
Stata enforces one string per code for a labeled variable, so there's no
realistic inconsistent-casing problem to fix *in the pre-coded fields*.
Spot checks on `q1_02`, `q1_03`, `domain`, `area`, `zone`, `q3_16` found
zero variants.

That means, before writing any normalization code, **verify it's actually
needed**:

```python
def check_casing_consistency(series) -> bool:
    """True if series.nunique() == series.str.lower().str.strip().nunique()
    -- i.e. no case/whitespace variants exist."""
```

Run across all 99 `ind` category columns + `emig`'s equivalents. Expected
result, based on the spot checks already done: mostly/entirely `True`.

**Where inconsistency plausibly *does* exist**: the same 8 free-text columns
from Part 3 — genuinely user-typed, not Stata-labeled. Same near-duplicate
problem as Part 3, from the opposite direction: Part 3 *finds* likely
variants (via Jaro-Winkler), Part 5 is where a manual consolidation mapping
gets *applied* once a human has reviewed those candidates and decided which
are really the same thing.

New function, `Scripts/clean.py`:

```python
def apply_value_mapping(df, column, mapping: dict) -> pd.DataFrame:
    """mapping is hand-built from reviewing find_near_duplicate_values()'s
    output (Part 3) -- e.g. {"cashier": "Cashier", "Cashier ": "Cashier"}.
    Every mapping applied gets logged: column, from-value, to-value,
    n_rows_affected."""
```

`mapping` itself should be a literal dict living in `config.py` next to
`SKIP_PATTERNS`/`EXPECTED_COUNTS` — inspectable/versioned, not buried in
code — but it starts **empty**, populated only after a human reviews Part
3's candidate list. Building the function now with nothing to map yet is
fine; inventing mappings without review would not be.

### Verify

Run `check_casing_consistency()` across every category column first and
report the actual count of columns that fail it — if it's genuinely zero
(expected), that itself is worth stating plainly in the next
problem-inventory draft rather than silently building unneeded
normalization code.

---

## Build sequence (once you say go)

1. `config.py`: add `SKIP_PATTERNS`, empty `VALUE_MAPPINGS`, new output paths
   (`<name>_cleaned.parquet` in `Outputs/typed/`;
   `<name>_cleaning.log` / `<name>_flagged_for_review.csv` /
   `<name>_near_duplicates.csv` in `Outputs/logs/`). Add `rapidfuzz` to
   `requirements.txt`.
2. `diagnose.py`: add `classify_missingness()`, wire the `SKIP_PATTERNS`
   table through it, fold into the existing report.
3. `diagnose.py`: add `find_near_duplicate_values()`, run over the 8
   free-text columns, write `<name>_near_duplicates.csv`.
4. `diagnose.py`: add `check_casing_consistency()`, run over all category
   columns, confirm the "already consistent" hypothesis with real numbers.
5. `clean.py` (new file): `apply_validation_rules()` — start with the
   confirmed-safe `-1`→`NaN` age correction and the two arithmetic
   consistency flags; write `<name>_flagged_for_review.csv` and
   `<name>_cleaned.parquet`.
6. `clean.py`: `apply_value_mapping()` — built now, populated later once
   step 3's output has been reviewed by a human.
7. Update `README.md` to document the new stage, same pattern as the
   existing sections.

Each step gets its own commit, per the brief's "commit after each stage,
log row counts before/after" requirement — matches how every prior stage
in this project has been built.

---

## Open questions for you to decide before any of this is built

1. Still the standing blocker: no assigned cleaning-scope variables from the
   evaluating office yet. Build against the full dataset as drafted above,
   or wait?
2. IQR threshold for the monetary outlier flags (1.5× IQR is the
   conventional default) — fine as a starting point, or a different
   multiplier?
3. Jaro-Winkler similarity threshold for near-duplicate free-text values
   (0.90 proposed) — fine as a starting point?
4. Confirm the one correction this plan proposes making unprompted (`-1`
   age sentinel → `NaN`) is the only "auto-correct" wanted at this stage —
   everything else above is flag-only by design.
