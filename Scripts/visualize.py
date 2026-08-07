"""Charts for the named-variable distributions from diagnose.py (sex, age
groups, employment status), saved as JPEG to Outputs/charts/.

These are static report charts, not an interactive web component, so this
follows the project's dataviz skill's form/color/label rules (single hue
for a single-series bar chart -- the axis labels already carry category
identity, so per-bar hue would be decorative, not informative; recessive
gridlines; selective direct labels; no chart junk) but skips the parts
specific to interactive HTML (hover tooltips, dark-mode toggle, JS palette
validator) since there's no such runtime here.
"""

import textwrap

import matplotlib.pyplot as plt
import pandas as pd

import config
from diagnose import age_group_distribution, load_typed, value_counts_labeled

# Validated default palette (dataviz skill, references/palette.md), light surface.
_SURFACE = "#fcfcfb"
_BAR_COLOR = "#2a78d6"  # categorical slot 1 (blue) -- single-series, single hue
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_GRIDLINE = "#e1e0d9"
_BASELINE = "#c3c2b7"


def _wrap_label(text: str, width: int = 28) -> str:
    """Wrap a category label for display on a chart axis. Display-only --
    never mutates the underlying data/tables, just what's drawn."""
    return "\n".join(textwrap.wrap(str(text), width=width)) or str(text)


def plot_distribution(table: pd.DataFrame, title: str, out_path, figsize=(8, 4.5)) -> None:
    """Horizontal single-series bar chart of a value_counts_labeled()-shaped
    table (columns: label, count, pct_of_valid). Horizontal bars handle the
    long category text some of these variables have (e.g. employment
    status) without label collisions. Saves a JPEG to out_path."""
    plot_table = table.iloc[::-1]  # reverse: barh draws bottom-up, so largest ends up on top
    labels = [_wrap_label(label) for label in plot_table["label"]]

    fig, ax = plt.subplots(figsize=figsize, dpi=150)
    bars = ax.barh(labels, plot_table["count"], height=0.6, color=_BAR_COLOR)

    ax.set_facecolor(_SURFACE)
    fig.set_facecolor(_SURFACE)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.xaxis.grid(True, color=_GRIDLINE, linewidth=1)
    ax.set_axisbelow(True)
    ax.xaxis.set_ticks([])
    ax.tick_params(axis="y", colors=_PRIMARY_INK, labelsize=10, length=0)
    ax.set_title(title, fontsize=13, color=_PRIMARY_INK, loc="left", pad=14)
    ax.margins(x=0.12)  # room for the tip labels

    # Selective direct labels: value at the tip of every bar -- with at most
    # 7 bars per chart here, this stays readable instead of becoming noise.
    for bar, count in zip(bars, plot_table["count"]):
        ax.annotate(
            f"{count:,}",
            xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(6, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=9,
            color=_SECONDARY_INK,
        )

    fig.tight_layout()
    fig.savefig(out_path, format="jpeg", pil_kwargs={"quality": 92})
    plt.close(fig)


def make_charts(datasets: dict) -> dict:
    """Generate the three named-variable distribution charts for ind (sex,
    age group, employment status) as JPEG. Returns {chart_name: output_path}."""
    df = load_typed("ind", datasets)

    sex_table, _ = value_counts_labeled(df["q1_03"])
    age_table, _ = age_group_distribution(df["q1_04"])
    emp_table, _ = value_counts_labeled(df["q3_16"])

    charts = {
        "sex_distribution": (sex_table, "Sex distribution (ind, q1_03)"),
        "age_group_distribution": (age_table, "Age group distribution (ind, q1_04 bucketed)"),
        "employment_status_distribution": (emp_table, "Employment status, main job (ind, q3_16)"),
    }

    out_paths = {}
    for chart_name, (table, title) in charts.items():
        out_path = config.CHARTS_DIR / f"{chart_name}.jpg"
        plot_distribution(table, title, out_path)
        out_paths[chart_name] = out_path
        print(f"-> {out_path}")

    return out_paths


if __name__ == "__main__":
    make_charts(config.DATASETS)
