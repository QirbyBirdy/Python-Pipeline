"""Stage 3: draft a severity-ranked, human-editable problem inventory from
the diagnostics table. Descriptive only -- no data is altered here."""

from pathlib import Path

import pandas as pd


def _severity(row: pd.Series) -> str:
    if row["pct_missing"] > 50:
        return "High"
    if row["n_unique"] <= 1:
        return "Medium"
    return "Informational"


def _issue(row: pd.Series) -> str:
    if row["pct_missing"] > 50:
        return f"{row['pct_missing']}% missing"
    if row["n_unique"] <= 1:
        return "constant / single-value column"
    return "no issue detected"


def draft_findings(diagnostics: pd.DataFrame) -> pd.DataFrame:
    findings = diagnostics.copy()
    findings["severity"] = findings.apply(_severity, axis=1)
    findings["issue"] = findings.apply(_issue, axis=1)

    order = {"High": 0, "Medium": 1, "Informational": 2}
    findings["_order"] = findings["severity"].map(order)
    findings = findings.sort_values(["_order", "column"]).drop(columns="_order")

    return findings[["column", "issue", "severity", "label_set", "n_unique", "pct_missing"]]


def render_inventory(name: str, findings: pd.DataFrame) -> str:
    lines = [
        f"# Problem inventory (draft): {name}",
        "",
        "Auto-drafted from diagnostics. Descriptive only -- no cleaning applied. Edit freely.",
        "",
        "| Column | Issue | Severity | Label set | # unique | % missing |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in findings.iterrows():
        lines.append(
            f"| {row['column']} | {row['issue']} | {row['severity']} | "
            f"{row['label_set']} | {row['n_unique']} | {row['pct_missing']} |"
        )
    return "\n".join(lines) + "\n"


def draft(name: str, datasets: dict) -> Path:
    paths = datasets[name]
    diagnostics = pd.read_csv(paths["diagnostics_csv"])
    diagnostics["label_set"] = diagnostics["label_set"].fillna("")
    findings = draft_findings(diagnostics)
    inventory = render_inventory(name, findings)
    paths["problem_inventory"].write_text(inventory, encoding="utf-8")
    return paths["problem_inventory"]


def draft_all(datasets: dict) -> dict:
    return {name: draft(name, datasets) for name in datasets}
