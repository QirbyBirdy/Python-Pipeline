"""Charts for the named-variable distributions from diagnose.py (sex, age
groups, employment status), saved as JPEG to Outputs/charts/.

Donut charts with a centered total-N figure and external leader-line
labels. Static report charts, not an interactive web component, so this
follows the project's dataviz skill's color/label rules (fixed-order
categorical hues for nominal variables; a single-hue light->dark ramp for
the age groups, since age is ordinal, not arbitrary categories; text never
carries the series color; a legend would only restate what's already on
every wedge's direct label, so it's skipped) but skips the parts specific
to interactive HTML (hover tooltips, dark-mode toggle, JS palette
validator) since there's no such runtime here.

Note: the dataviz skill's own form guidance recommends a (horizontal)
stacked bar over a pie for part-to-whole comparison -- bar length is easier
to judge precisely than wedge angle/area. Donuts here are a deliberate
choice for these specific 2-7 category shares, not a default to reach for.
"""

import textwrap

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

import config
from diagnose import age_group_distribution, value_counts_labeled

# Validated default palette (dataviz skill, references/palette.md), light surface.
_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED_INK = "#898781"

# Categorical slots, fixed order -- for nominal variables (sex, employment status).
_CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# Sequential blue ramp, light->dark -- for the ordinal age-group variable.
_SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def _wrap_label(text: str, width: int = 24) -> str:
    """Wrap a category label for display on a chart. Display-only -- never
    mutates the underlying data/tables, just what's drawn."""
    return "\n".join(textwrap.wrap(str(text), width=width)) or str(text)


def _donut_colors(n: int, mode: str) -> list:
    if mode == "sequential":
        # Evenly sample the 7-step ramp down to however many slices exist.
        idx = np.linspace(0, len(_SEQUENTIAL_BLUE) - 1, n).round().astype(int)
        return [_SEQUENTIAL_BLUE[i] for i in idx]
    return [_CATEGORICAL[i % len(_CATEGORICAL)] for i in range(n)]


def plot_donut(
    table: pd.DataFrame,
    title: str,
    out_path,
    color_mode: str = "categorical",
    center_label: str = "",
    figsize=(8, 7),
) -> None:
    """Donut chart of a value_counts_labeled()-shaped table (columns: label,
    count, pct_of_valid), sorted largest-first starting at 12 o'clock,
    clockwise. Every wedge gets an external label (name, count, %) connected
    by a thin leader line -- no legend, since the labels already carry
    identity. Saves a JPEG to out_path."""
    colors = _donut_colors(len(table), color_mode)

    fig, ax = plt.subplots(figsize=figsize, dpi=150, subplot_kw=dict(aspect="equal"))
    fig.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    wedges, _ = ax.pie(
        table["count"],
        colors=colors,
        startangle=90,
        counterclock=False,
        radius=1.0,
        wedgeprops=dict(width=0.42, edgecolor=_SURFACE, linewidth=3),
    )

    # Center figure: total N across every wedge (valid responses only).
    total = int(table["count"].sum())
    ax.text(0, 0.06, f"{total:,}", ha="center", va="center", fontsize=22, color=_PRIMARY_INK, weight="bold")
    ax.text(0, -0.10, center_label, ha="center", va="center", fontsize=10, color=_MUTED_INK)

    # External labels on leader lines, with collision avoidance: labels on
    # the same side (left/right) are evenly spread top-to-bottom rather
    # than placed at their raw wedge angle, so two small adjacent wedges
    # (close in angle) never produce overlapping label text.
    items = []
    for wedge, (_, row) in zip(wedges, table.iterrows()):
        ang = (wedge.theta2 - wedge.theta1) / 2 + wedge.theta1
        x, y = np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))
        items.append({"ang": ang, "x": x, "y": y, "row": row})

    bbox_props = dict(boxstyle="round,pad=0.3", fc=_SURFACE, ec="none")
    for side_items, ha, x_text in (
        (sorted([it for it in items if it["x"] < 0], key=lambda it: -it["y"]), "right", -1.4),
        (sorted([it for it in items if it["x"] >= 0], key=lambda it: -it["y"]), "left", 1.4),
    ):
        n = len(side_items)
        if n == 0:
            continue
        top = max(0.95, max(it["y"] for it in side_items) * 1.15)
        bottom = min(-0.95, min(it["y"] for it in side_items) * 1.15)
        y_positions = [top] if n == 1 else np.linspace(top, bottom, n)
        for it, y_pos in zip(side_items, y_positions):
            row = it["row"]
            label_text = f"{_wrap_label(row['label'])}\n{row['count']:,} ({row['pct_of_valid']:.1f}%)"
            ax.annotate(
                label_text,
                xy=(it["x"], it["y"]),
                xytext=(x_text, y_pos),
                horizontalalignment=ha,
                va="center",
                fontsize=10,
                color=_SECONDARY_INK,
                bbox=bbox_props,
                arrowprops=dict(arrowstyle="-", color=_MUTED_INK, lw=1, connectionstyle="arc3,rad=0"),
                zorder=0,
            )

    ax.set_title(title, fontsize=13, color=_PRIMARY_INK, loc="left", pad=8)
    ax.set_xlim(-2.1, 2.1)
    ax.set_ylim(-1.5, 1.5)

    fig.savefig(out_path, format="jpeg", pil_kwargs={"quality": 92}, bbox_inches="tight", facecolor=_SURFACE)
    plt.close(fig)


def plot_bar(table: pd.DataFrame, title: str, out_path) -> None:
    """Horizontal single-hue bar chart for a value_counts_labeled()-shaped
    table with too many categories for a donut. The dataviz skill's
    series-count ladder caps meaningful multi-color categorical identity
    around 7-8 slots; ISIC section (21) and ISCO major group (10) both
    exceed it. Axis labels already carry identity, so one hue plus a bar's
    precisely-comparable length is both more readable and more accurate
    here than forcing that many colors into wedges."""
    plot_table = table.sort_values("count", ascending=True)  # ascending: barh draws bottom-up, largest ends on top
    labels = [_wrap_label(label, width=45) for label in plot_table["label"]]
    # Height scales with total wrapped LINE count, not bar count -- a few
    # very long labels (e.g. some ISIC section names) wrap to 3+ lines and
    # would otherwise collide with short single-line neighbors if every
    # row got the same fixed slot.
    total_lines = sum(label.count("\n") + 1 for label in labels)
    height = max(3.5, 0.34 * total_lines + 1.5)

    fig, ax = plt.subplots(figsize=(9, height), dpi=150)
    bars = ax.barh(labels, plot_table["count"], height=0.6, color=_SEQUENTIAL_BLUE[4])

    ax.set_facecolor(_SURFACE)
    fig.set_facecolor(_SURFACE)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.xaxis.set_ticks([])
    ax.tick_params(axis="y", colors=_PRIMARY_INK, labelsize=9, length=0)
    ax.set_title(title, fontsize=13, color=_PRIMARY_INK, loc="left", pad=12)
    ax.margins(x=0.13)

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

    fig.savefig(out_path, format="jpeg", pil_kwargs={"quality": 92}, bbox_inches="tight", facecolor=_SURFACE)
    plt.close(fig)


def plot_histogram(series: pd.Series, title: str, out_path, xlabel: str, bins: int = 20) -> None:
    """Histogram for a continuous numeric variable (hours worked) --
    the brief's chart requirements explicitly call for a distribution of
    key numeric variables, which a donut/bar-of-categories can't show."""
    valid = series.dropna().astype(float)
    mean_val = valid.mean()

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.hist(valid, bins=bins, color=_SEQUENTIAL_BLUE[4], edgecolor=_SURFACE, linewidth=1.2)

    ax.set_facecolor(_SURFACE)
    fig.set_facecolor(_SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.yaxis.grid(True, color="#e1e0d9", linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=_MUTED_INK, labelsize=9)
    ax.set_xlabel(xlabel, fontsize=10, color=_SECONDARY_INK)
    ax.set_ylabel("Number of respondents", fontsize=10, color=_SECONDARY_INK)
    ax.set_title(title, fontsize=13, color=_PRIMARY_INK, loc="left", pad=12)

    ax.axvline(mean_val, color="#eb6834", linewidth=2, linestyle="--")
    ax.annotate(
        f"mean = {mean_val:.1f}",
        xy=(mean_val, ax.get_ylim()[1]),
        xytext=(8, -4),
        textcoords="offset points",
        fontsize=9,
        color="#eb6834",
        va="top",
    )

    fig.savefig(out_path, format="jpeg", pil_kwargs={"quality": 92}, bbox_inches="tight", facecolor=_SURFACE)
    plt.close(fig)


def make_charts(datasets: dict) -> dict:
    """Generate every distribution chart for ind (sex, age group,
    employment status, ISIC section, ISCO major group, hours worked) as
    JPEG. Reads Outputs/typed/ind_cleaned.parquet -- run ingest.py,
    diagnose.py, then clean.py first (sentinel corrections and the
    isic_section/isco_major_group columns only exist post-cleaning).
    Returns {chart_name: output_path}."""
    df = pd.read_parquet(datasets["ind"]["cleaned"])

    sex_table, _ = value_counts_labeled(df["q1_03"])
    age_table, _ = age_group_distribution(df["q1_04"])
    emp_table, _ = value_counts_labeled(df["q3_16"])
    isic_table, _ = value_counts_labeled(df["isic_section_label"])
    isco_table, _ = value_counts_labeled(df["isco_major_group_label"])

    out_paths = {}

    donut_charts = {
        "sex_distribution": (sex_table, "Sex distribution (ind, q1_03)", "categorical", "respondents"),
        "age_group_distribution": (
            age_table,
            "Age group distribution (ind, q1_04 bucketed)",
            "sequential",
            "respondents",
        ),
        "employment_status_distribution": (
            emp_table,
            "Employment status, main job (ind, q3_16)",
            "categorical",
            "with a main job",
        ),
    }
    for chart_name, (table, title, color_mode, center_label) in donut_charts.items():
        out_path = config.CHARTS_DIR / f"{chart_name}.jpg"
        plot_donut(table, title, out_path, color_mode=color_mode, center_label=center_label)
        out_paths[chart_name] = out_path
        print(f"-> {out_path}")

    bar_charts = {
        "isic_section_distribution": (isic_table, "Industry (ISIC Rev.4 section), main job (ind, isic_code)"),
        "isco_major_group_distribution": (isco_table, "Occupation (ISCO-08 major group), main job (ind, isco_code)"),
    }
    for chart_name, (table, title) in bar_charts.items():
        out_path = config.CHARTS_DIR / f"{chart_name}.jpg"
        plot_bar(table, title, out_path)
        out_paths[chart_name] = out_path
        print(f"-> {out_path}")

    hours_out_path = config.CHARTS_DIR / "hours_worked_distribution.jpg"
    plot_histogram(
        df["q3_03"],
        "Usual hours worked per week, main job (ind, q3_03; 99-sentinel already corrected)",
        hours_out_path,
        xlabel="Hours per week",
    )
    out_paths["hours_worked_distribution"] = hours_out_path
    print(f"-> {hours_out_path}")

    return out_paths


if __name__ == "__main__":
    make_charts(config.DATASETS)
