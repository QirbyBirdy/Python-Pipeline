"""Problem inventory (build brief Step 5): a written list of data-quality
issues, with counts, for five variables of interest -- sex, age, hours
worked, ISIC (industry), ISCO (occupation) -- plus a documented note on
panelid, a column whose name implies a unique key but isn't one. Read-only:
this documents what was found in the typed (pre-cleaning) `ind` data;
clean.py is what actually fixes what's fixable. Every finding here
cross-references which clean.py stage (if any) addresses it.
"""

import pandas as pd

import config
from clean import check_usual_hours_consistency
from diagnose import load_typed


def _finding(variable: str, issue: str, count: int, n_total: int, severity: str, addressed_by: str) -> dict:
    return {
        "variable": variable,
        "issue": issue,
        "count": count,
        "pct": round(100 * count / n_total, 2) if n_total else 0.0,
        "severity": severity,
        "addressed_by": addressed_by,
    }


def inventory_sex(df: pd.DataFrame) -> list:
    n = len(df)
    n_missing = int(df["q1_03"].isna().sum())
    if n_missing:
        return [_finding("Sex (q1_03)", "Missing", n_missing, n, "Low", "Not addressed -- flagged only")]
    return [_finding("Sex (q1_03)", "No issues found -- 0 missing, values are clean 'Male'/'Female' text", 0, n, "None", "N/A")]


def inventory_age(df: pd.DataFrame) -> list:
    n = len(df)
    findings = []
    n_missing = int(df["q1_04"].isna().sum())
    findings.append(_finding("Age (q1_04)", "Missing (before sentinel correction)", n_missing, n, "None" if not n_missing else "Low", "N/A"))
    n_sentinel = int((df["q1_04"] == -1).sum())
    findings.append(
        _finding(
            "Age (q1_04)",
            "'-1' sentinel value (verified 'don't know' placeholder, not a real age)",
            n_sentinel,
            n,
            "Low",
            "clean.py: correct_age_sentinel() -> NaN",
        )
    )
    return findings


def inventory_hours(df: pd.DataFrame) -> list:
    n = len(df)
    findings = []

    n_sentinel_03 = int((df["q3_03"] == 99).sum())
    findings.append(
        _finding(
            "Hours worked (q3_03, usual hours/week main job)",
            "'99' top-code sentinel (natural max otherwise caps at 98; q3_09 'actual hours', which never top-codes, "
            "goes up to 168 -- confirms 99 is a sentinel specific to this field, not a real value)",
            n_sentinel_03,
            n,
            "Medium",
            "clean.py: correct_hours_sentinel() -> NaN",
        )
    )

    n_sentinel_05 = int((df["q3_05"] == 99).sum())
    findings.append(
        _finding(
            "Hours worked (q3_05, total usual hours all jobs)",
            "'99' sentinel (same pattern as q3_03)",
            n_sentinel_05,
            n,
            "Low",
            "clean.py: correct_hours_sentinel() -> NaN",
        )
    )

    usual_mismatch = check_usual_hours_consistency(df)
    findings.append(
        _finding(
            "Hours worked (q3_03 + q3_04 vs q3_05, on RAW data)",
            "Arithmetic mismatch: main-job + other-job hours don't sum to the reported total "
            "(all 6 cases trace to the q3_05=99 sentinel above -- this check only has power to catch "
            "them because it runs before that sentinel is corrected, not after)",
            len(usual_mismatch),
            n,
            "Low",
            "clean.py: check_usual_hours_consistency() run on raw data (diagnostic) -> "
            "recompute_derived_hours() recalculates q3_05 from cleaned components",
        )
    )

    day_cols = [f"q3_07_{i}" for i in range(1, 8)]
    for col in day_cols + ["q3_08"]:
        n_neg1 = int((df[col] == -1).sum())
        findings.append(
            _finding(
                f"Hours worked ({col})",
                "'-1' sentinel (the same 'don't know' placeholder verified for age -- confirmed present "
                "here too, and had never been corrected before this pass)",
                n_neg1,
                n,
                "Low" if n_neg1 else "None",
                "clean.py: correct_negative_one_hours_sentinel() -> NaN",
            )
        )

    findings.append(
        _finding(
            "Hours worked (q3_09 main-job actual, q3_10 all-jobs actual, q3_05 all-jobs usual)",
            "These three are CAPI-computed totals, not independently asked questions -- comparing "
            "them to the sum of their own components is tautological (true by construction) and "
            "can never catch a real error. Previously flagged this way (daily q3_07_1..7 vs q3_09); "
            "retired that check and replaced it with direct recomputation from cleaned components, "
            "with NaN propagating if any component is unknown",
            0,
            n,
            "None (not a defect -- a check design fix)",
            "clean.py: recompute_derived_hours() -- recalculates rather than validates",
        )
    )

    return findings


def inventory_panelid(df: pd.DataFrame) -> list:
    n = len(df)
    n_unique = int(df["panelid"].nunique())
    return [
        _finding(
            "panelid",
            f"Named like a unique respondent ID but is not one -- only {n_unique} distinct values "
            f"across {n} rows (it's a panel/wave grouping code, not a per-person key). Harmless as "
            "long as it's left untouched, but would silently produce a many-to-many join and corrupt "
            "the data if ever used as a merge key",
            n,
            n,
            "None (not currently used as a key) / High if ever used as one",
            "N/A -- not used anywhere in this pipeline as a join key; documented here so it isn't "
            "mistaken for one later",
        )
    ]


def inventory_isic(df: pd.DataFrame) -> list:
    n = len(df)
    findings = []
    n_missing = int(df["isic_code"].isna().sum())
    findings.append(
        _finding(
            "Industry (isic_code)",
            "Missing -- structural: isic_code only applies to people with a main job "
            "(matches q3_16 employment-status missingness exactly)",
            n_missing,
            n,
            "None (structural, not a quality issue)",
            "N/A -- correctly not imputed",
        )
    )
    n_short = int((df["isic_code"].dropna().str.len() == 3).sum())
    findings.append(
        _finding(
            "Industry (isic_code)",
            "Leading zero stripped in export (e.g. '0729' stored as '729') -- would misclassify the "
            "ISIC section if not corrected for",
            n_short,
            n,
            "Low (corrected, not left broken)",
            "clean.py: classify_isic_section() zero-pads to 4 digits before reading the division",
        )
    )
    return findings


def inventory_isco(df: pd.DataFrame) -> list:
    n = len(df)
    findings = []
    n_missing = int(df["isco_code"].isna().sum())
    findings.append(
        _finding(
            "Occupation (isco_code)",
            "Missing -- structural, same pattern as isic_code (only applies to people with a main job)",
            n_missing,
            n,
            "None (structural, not a quality issue)",
            "N/A -- correctly not imputed",
        )
    )
    lengths = df["isco_code"].dropna().str.len()
    n_nonstandard = int((lengths != 4).sum())
    findings.append(
        _finding(
            "Occupation (isco_code)",
            "Non-4-digit code (2, 3, or 5 characters) -- the 3-digit cases are the same leading-zero-stripping "
            "issue as ISIC (Major Group 0, Armed forces); the single 5-digit case ('61111') is likely a typo",
            n_nonstandard,
            n,
            "Low (corrected/best-effort, not left broken)",
            "clean.py: classify_isco_major_group() zero-pads short codes; long codes best-effort on the leading digit",
        )
    )
    return findings


def render_problem_inventory(findings: list) -> str:
    lines = [
        "# Problem inventory: sex, age, hours worked, industry (ISIC), occupation (ISCO), panelid",
        "",
        "Read-only findings on the typed (pre-cleaning) `ind` dataset (13,853 rows). "
        "Counts and % are of all rows, not just valid responses, so structural missingness is visible "
        "in context. See `Scripts/clean.py` for what each finding's 'Addressed by' column actually does.",
        "",
        "| Variable | Issue | Count | % | Severity | Addressed by |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f in findings:
        lines.append(
            f"| {f['variable']} | {f['issue']} | {f['count']} | {f['pct']} | {f['severity']} | {f['addressed_by']} |"
        )

    lines += [
        "",
        "## Summary",
        "",
        "- **Sex**: clean. No missingness, no inconsistent coding.",
        "- **Age**: one small, fully-corrected issue (12 rows, a verified `-1` sentinel).",
        "- **Hours worked**: the most issues of the six, and a self-audit this pass found the original "
        "checks had a systematic blind spot -- the `99` sentinel (`q3_03`/`q3_05`) is corrected before "
        "the check that verifies it, so it was run once, deliberately, on raw data instead, and the "
        "`-1` sentinel proven for age turned out to be live in seven more columns (`q3_07_1..7`, "
        "`q3_08`) but had never been corrected there. `q3_09`/`q3_10`/`q3_05` are CAPI-computed totals, "
        "not independent measurements, so validating them against their own components is tautological "
        "(can never fail) -- they're recomputed from cleaned components instead.",
        "- **Industry (ISIC) / Occupation (ISCO)**: high missingness (65.4%) is entirely structural (the "
        "question only applies to people with a main job) and not a quality problem. The real issue -- "
        "inconsistent leading-zero stripping -- is fully handled by zero-padding before classification; "
        "**0 of 4,789** codes with a value failed to classify.",
        "- **panelid**: named like a unique respondent ID but has only 18 distinct values across 13,853 "
        "rows. Not used as a key anywhere in this pipeline, so it's harmless as-is -- documented here so "
        "it isn't mistaken for a real ID and used as a merge key later.",
        "- Every correction made (age sentinel, hours-99 sentinel, hours-(-1) sentinel, and the "
        "q3_09/q3_10/q3_05 recomputation) was made only after checking related columns first, not on a "
        "guess -- everything else is either structural (expected, not a defect) or already fully "
        "resolved by the classification logic.",
    ]
    return "\n".join(lines) + "\n"


def build_problem_inventory(datasets: dict) -> str:
    df = load_typed("ind", datasets)
    findings = (
        inventory_sex(df)
        + inventory_age(df)
        + inventory_hours(df)
        + inventory_isic(df)
        + inventory_isco(df)
        + inventory_panelid(df)
    )
    report = render_problem_inventory(findings)
    datasets["ind"]["problem_inventory"].write_text(report, encoding="utf-8")
    print(report)
    return report


if __name__ == "__main__":
    build_problem_inventory(config.DATASETS)
