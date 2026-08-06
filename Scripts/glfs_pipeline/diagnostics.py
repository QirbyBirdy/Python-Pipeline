"""Stage 2: per-column exploratory diagnostics on the interim parquet."""

from pathlib import Path

import pandas as pd


def column_diagnostics(df: pd.DataFrame, dictionary: pd.DataFrame) -> pd.DataFrame:
    label_set_by_column = dict(zip(dictionary["column"], dictionary["choices"]))
    n_rows = len(df)
    rows = []
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        top_counts = series.value_counts(dropna=True).head(5)
        label_set = label_set_by_column.get(col, "")
        if pd.isna(label_set):
            label_set = ""
        rows.append(
            {
                "column": col,
                "dtype": str(series.dtype),
                "pct_missing": round(100 * n_missing / n_rows, 2) if n_rows else 0.0,
                "n_unique": int(series.nunique(dropna=True)),
                "top_values": "; ".join(f"{val}={cnt}" for val, cnt in top_counts.items()),
                "label_set": label_set,
            }
        )
    return pd.DataFrame(rows)


def render_report(name: str, df: pd.DataFrame, diagnostics: pd.DataFrame) -> str:
    n_rows, n_cols = df.shape
    overall_missing = diagnostics["pct_missing"].mean() if n_cols else 0.0
    flagged = diagnostics.loc[diagnostics["pct_missing"] > 50, "column"].tolist()
    constant_cols = diagnostics.loc[diagnostics["n_unique"] <= 1, "column"].tolist()

    lines = [
        f"# Diagnostics report: {name}",
        "",
        f"- Rows: {n_rows}",
        f"- Columns: {n_cols}",
        f"- Average missingness across columns: {overall_missing:.2f}%",
        "",
        f"## Columns >50% missing ({len(flagged)})",
        "",
    ]
    lines += [f"- {c}" for c in flagged] if flagged else ["- none"]
    lines += ["", f"## Constant / single-value columns ({len(constant_cols)})", ""]
    lines += [f"- {c}" for c in constant_cols] if constant_cols else ["- none"]
    return "\n".join(lines) + "\n"


def diagnose(name: str, datasets: dict) -> tuple[Path, Path]:
    paths = datasets[name]
    df = pd.read_parquet(paths["interim"])
    dictionary = pd.read_csv(paths["dictionary"])

    diagnostics = column_diagnostics(df, dictionary)
    diagnostics.to_csv(paths["diagnostics_csv"], index=False)

    report = render_report(name, df, diagnostics)
    paths["diagnostics_report"].write_text(report, encoding="utf-8")

    return paths["diagnostics_csv"], paths["diagnostics_report"]


def diagnose_all(datasets: dict) -> dict:
    return {name: diagnose(name, datasets) for name in datasets}
