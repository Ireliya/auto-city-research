#!/usr/bin/env python3
"""Run exact top-k budget checks for priority mismatch.

The primary mismatch analysis uses event-wise top-percentile flags. That is a
reasonable audit rule, but low-damage events can contain many tied damage
scores. This script adds a stricter operational interpretation: if responders
can inspect exactly k cells per event, which cells are high need in at least two
need-aware scenarios but outside the exact damage-only budget?
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from figure_style import (
    BLUE,
    LIGHT_NEUTRAL,
    NEUTRAL,
    add_direct_line_labels,
    add_panel_label,
    apply_publication_style,
    color_for_event,
    marker_for_event,
    mm_to_inches,
    save_publication_figure,
    style_numeric_axis,
)


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"


EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}

EVENT_ORDER = ["hurricane-harvey", "mexico-earthquake", "palu-tsunami", "santa-rosa-wildfire"]
TOP_SHARES = [0.10, 0.15, 0.20, 0.25, 0.30]

DAMAGE_SORT_COLUMNS = [
    "damage_index_D",
    "damaged_building_count",
    "severe_building_count",
    "damage_weighted_area_m2",
    "cell_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv"),
        help="Priority mismatch grid CSV from src/05_analyze_priority_mismatch.py.",
    )
    parser.add_argument(
        "--primary-summary",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/event_mismatch_summary.csv"),
        help="Primary top-percentile event summary CSV.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/derived/strict_budget_v1"),
        help="Output directory for strict-budget tables.",
    )
    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=Path("reports/figures"),
        help="Output directory for Figure 6.",
    )
    return parser.parse_args()


def scenario_names(grid: pd.DataFrame) -> list[str]:
    preferred = ["balanced_need", "population_sensitive", "accessibility_sensitive"]
    found = [col.removeprefix("score_") for col in grid.columns if col.startswith("score_")]
    return [name for name in preferred if name in found] + sorted(set(found) - set(preferred))


def exact_top_cell_ids(event_df: pd.DataFrame, sort_columns: list[str], ascending: list[bool], k: int) -> set[str]:
    available = [col for col in sort_columns if col in event_df.columns]
    available_ascending = [ascending[sort_columns.index(col)] for col in available]
    ranked = event_df.sort_values(available, ascending=available_ascending, kind="mergesort")
    return set(ranked.head(k)["cell_id"].astype(str))


def add_budget_flags(event_df: pd.DataFrame, scenarios: list[str], top_share: float) -> pd.DataFrame:
    event_df = event_df.copy()
    k = int(math.ceil(len(event_df) * top_share))
    event_df["strict_budget_k"] = k
    event_df["strict_top_share"] = top_share

    damage_top = exact_top_cell_ids(
        event_df,
        DAMAGE_SORT_COLUMNS,
        [False, False, False, False, True],
        k,
    )
    event_df["strict_top_damage"] = event_df["cell_id"].astype(str).isin(damage_top)

    need_cols = []
    for scenario in scenarios:
        col = f"strict_top_need_{scenario}"
        need_top = exact_top_cell_ids(
            event_df,
            [f"score_{scenario}", "damage_index_D", "worldpop_population", "cell_id"],
            [False, False, False, True],
            k,
        )
        event_df[col] = event_df["cell_id"].astype(str).isin(need_top)
        need_cols.append(col)

    event_df["strict_need_top_scenario_count"] = event_df[need_cols].sum(axis=1)
    event_df["strict_stable_mismatch"] = (
        event_df["strict_need_top_scenario_count"] >= 2
    ) & (~event_df["strict_top_damage"])
    return event_df


def event_summary(grid: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for top_share in TOP_SHARES:
        for event, event_df in grid.groupby("event", sort=True):
            flagged = add_budget_flags(event_df, scenarios, top_share)
            stable = flagged[flagged["strict_stable_mismatch"]]
            rows.append(
                {
                    "event": event,
                    "top_share": top_share,
                    "cells": int(len(flagged)),
                    "strict_budget_k": int(flagged["strict_budget_k"].iloc[0]),
                    "strict_stable_mismatch_count": int(len(stable)),
                    "strict_stable_mismatch_share": float(len(stable) / len(flagged)),
                    "strict_stable_mismatch_population_sum": float(stable["worldpop_population"].sum()),
                    "strict_stable_mismatch_mean_damage_D": float(stable["damage_index_D"].mean()) if len(stable) else 0.0,
                    "strict_all_three_scenarios": int((stable["strict_need_top_scenario_count"] == 3).sum()),
                    "strict_exactly_two_scenarios": int((stable["strict_need_top_scenario_count"] == 2).sum()),
                }
            )
    return pd.DataFrame(rows)


def scenario_metrics(grid: pd.DataFrame, scenarios: list[str], top_share: float = 0.20) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for event, event_df in grid.groupby("event", sort=True):
        flagged = add_budget_flags(event_df, scenarios, top_share)
        damage_top = set(flagged.loc[flagged["strict_top_damage"], "cell_id"].astype(str))
        for scenario in scenarios:
            need_top = set(flagged.loc[flagged[f"strict_top_need_{scenario}"], "cell_id"].astype(str))
            overlap = damage_top & need_top
            union = damage_top | need_top
            mismatch = flagged[flagged[f"strict_top_need_{scenario}"] & (~flagged["strict_top_damage"])]
            rows.append(
                {
                    "event": event,
                    "scenario": scenario,
                    "top_share": top_share,
                    "cells": int(len(flagged)),
                    "strict_budget_k": int(flagged["strict_budget_k"].iloc[0]),
                    "strict_top_overlap_count": int(len(overlap)),
                    "strict_top_jaccard": float(len(overlap) / len(union)) if union else 0.0,
                    "strict_high_need_low_damage_count": int(len(mismatch)),
                    "strict_high_need_low_damage_share": float(len(mismatch) / len(flagged)),
                    "strict_mismatch_population_sum": float(mismatch["worldpop_population"].sum()),
                    "strict_mismatch_mean_damage_D": float(mismatch["damage_index_D"].mean()) if len(mismatch) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def top20_cells(grid: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for _, event_df in grid.groupby("event", sort=True):
        flagged = add_budget_flags(event_df, scenarios, 0.20)
        keep = flagged[flagged["strict_stable_mismatch"]].copy()
        parts.append(keep)
    if not parts:
        return pd.DataFrame()
    cols = [
        "event",
        "cell_id",
        "strict_budget_k",
        "strict_need_top_scenario_count",
        "damage_index_D",
        "worldpop_population",
        "road_density_m_per_km2",
        "facility_count",
        "nearest_facility_m",
        "cell_center_lon",
        "cell_center_lat",
    ]
    return pd.concat(parts, ignore_index=True)[cols].sort_values(
        ["event", "strict_need_top_scenario_count", "worldpop_population"],
        ascending=[True, False, False],
    )


def setup_style() -> None:
    sns.set_theme(style="white", context="paper")
    apply_publication_style()


def make_figure(summary: pd.DataFrame, primary_summary: pd.DataFrame, out_dir: Path) -> None:
    setup_style()
    out_dir.mkdir(parents=True, exist_ok=True)

    data = summary.copy()
    data["event_label"] = data["event"].map(EVENT_LABELS)
    data["budget_label"] = (data["top_share"] * 100).round().astype(int).astype(str) + "%"
    event_order_labels = [EVENT_LABELS[event] for event in EVENT_ORDER]

    top20 = data[data["top_share"] == 0.20].copy()
    primary = primary_summary[["event", "stable_mismatch_count"]].copy()
    primary["rule"] = "Percentile rule"
    primary = primary.rename(columns={"stable_mismatch_count": "count"})
    strict = top20[["event", "strict_stable_mismatch_count"]].copy()
    strict["rule"] = "Exact top-k budget"
    strict = strict.rename(columns={"strict_stable_mismatch_count": "count"})
    compare = pd.concat([primary, strict], ignore_index=True)
    compare["event_label"] = compare["event"].map(EVENT_LABELS)

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(80)),
        constrained_layout=True,
    )

    line_frames = []
    for event in EVENT_ORDER:
        event_df = data[data["event"] == event]
        label = EVENT_LABELS[event]
        axes[0].plot(
            event_df["top_share"],
            event_df["strict_stable_mismatch_count"],
            color=color_for_event(label),
            marker=marker_for_event(label),
            label=label,
        )
        line_frames.append((label, event_df))
    axes[0].set_title("Exact-budget sensitivity", loc="left", pad=7)
    add_panel_label(axes[0], "a", x=-0.15, y=1.04)
    axes[0].set_xlabel("Inspection budget")
    axes[0].set_ylabel("Stable mismatch cells")
    axes[0].set_xticks(TOP_SHARES)
    axes[0].set_xticklabels([f"{int(s * 100)}%" for s in TOP_SHARES])
    style_numeric_axis(axes[0], axis="y")
    add_direct_line_labels(
        axes[0],
        line_frames,
        x_col="top_share",
        y_col="strict_stable_mismatch_count",
    )

    paired = compare.pivot(index="event_label", columns="rule", values="count").reindex(event_order_labels)
    y = list(range(len(paired)))
    primary_values = paired["Percentile rule"].to_numpy()
    strict_values = paired["Exact top-k budget"].to_numpy()
    for idx, (left, right) in enumerate(zip(primary_values, strict_values)):
        axes[1].plot([left, right], [idx, idx], color=LIGHT_NEUTRAL, linewidth=2.0, zorder=1)
    axes[1].scatter(
        primary_values,
        y,
        s=28,
        facecolors="white",
        edgecolors=NEUTRAL,
        linewidths=1.1,
        label="Percentile rule",
        zorder=3,
    )
    axes[1].scatter(
        strict_values,
        y,
        s=30,
        color=BLUE,
        label="Exact top-k budget",
        zorder=4,
    )
    for idx, value in enumerate(strict_values):
        axes[1].text(value + 1.2, idx, f"{int(value)}", va="center", fontsize=6.3, color=BLUE)
    axes[1].set_yticks(y, event_order_labels)
    axes[1].invert_yaxis()
    axes[1].set_title("Top-20 rule comparison", loc="left", pad=7)
    add_panel_label(axes[1], "b", x=-0.18, y=1.04)
    axes[1].set_xlabel("Stable mismatch cells")
    axes[1].set_ylabel("")
    axes[1].legend(loc="lower right", fontsize=6.2, handletextpad=0.4)
    axes[1].margins(x=0.16)
    style_numeric_axis(axes[1], axis="x")

    save_publication_figure(fig, out_dir, "fig6_strict_budget_check")


def write_summary(
    out_dir: Path,
    summary: pd.DataFrame,
    primary_summary: pd.DataFrame,
    scenario_table: pd.DataFrame,
    scenarios: list[str],
) -> None:
    top20 = summary[summary["top_share"] == 0.20].set_index("event")
    primary = primary_summary.set_index("event")
    strict_total = int(top20["strict_stable_mismatch_count"].sum())
    primary_total = int(primary["stable_mismatch_count"].sum())
    lines = [
        "# Strict Budget Check v1",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Purpose",
        "",
        "Test the priority-mismatch claim under an exact top-k inspection budget. This complements the primary percentile rule and is especially useful for events with many tied low-damage cells.",
        "",
        "## Inputs",
        "",
        "- `data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv`",
        "- `data/derived/priority_mismatch_v1/event_mismatch_summary.csv`",
        "",
        "## Ranking Rule",
        "",
        "- Damage-only top-k uses xBD-derived damage variables only, then `cell_id` for deterministic final tie-breaking.",
        "- Need-aware top-k is computed separately for each active scenario.",
        "- A strict-budget stable mismatch cell is high need in at least two need-aware scenarios and outside the exact damage-only top-k.",
        f"- Active scenarios: {', '.join(f'`{name}`' for name in scenarios)}.",
        "",
        "## Top-20 Comparison",
        "",
        f"- Primary percentile-rule stable mismatch cells: `{primary_total}`.",
        f"- Strict exact-budget stable mismatch cells at top-20: `{strict_total}`.",
        "",
        "| Event | Primary percentile-rule cells | Strict exact-budget cells | Strict mismatch population |",
        "| --- | ---: | ---: | ---: |",
    ]
    for event in EVENT_ORDER:
        primary_count = int(primary.loc[event, "stable_mismatch_count"])
        strict_count = int(top20.loc[event, "strict_stable_mismatch_count"])
        strict_pop = float(top20.loc[event, "strict_stable_mismatch_population_sum"])
        lines.append(
            f"| {EVENT_LABELS[event]} | {primary_count} | {strict_count} | {strict_pop:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Threshold Sensitivity Under Exact Budgets",
            "",
            "| Event | Top-10 | Top-15 | Top-20 | Top-25 | Top-30 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for event in EVENT_ORDER:
        event_rows = summary[summary["event"] == event].set_index("top_share")
        counts = [int(event_rows.loc[share, "strict_stable_mismatch_count"]) for share in TOP_SHARES]
        lines.append(f"| {EVENT_LABELS[event]} | " + " | ".join(str(v) for v in counts) + " |")

    lines.extend(
        [
            "",
            "## Scenario-Level Top-20 Exact-Budget Counts",
            "",
            "| Event | Scenario | High-need / low-damage cells | Top-k Jaccard |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for _, row in scenario_table.sort_values(["event", "scenario"]).iterrows():
        lines.append(
            f"| {EVENT_LABELS.get(row['event'], row['event'])} | `{row['scenario']}` | {int(row['strict_high_need_low_damage_count'])} | {row['strict_top_jaccard']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The exact-budget rule preserves the main Harvey and Santa Rosa signals, and it turns Mexico from a zero-count primary case into a clear low-damage tie-boundary case. Under a strict top-20 budget, Mexico has high-need cells outside the exact damage-only budget even though the primary percentile rule marks all Mexico cells as damage-top because of tied near-zero damage ranks.",
            "",
            "## Limitations",
            "",
            "The exact-budget tie-break is deterministic but still arbitrary at the final tie level. It should be interpreted as a robustness diagnostic, not as a replacement for local operational triage.",
        ]
    )
    (out_dir / "strict_budget_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(out_dir: Path, scenarios: list[str]) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/15_run_strict_budget_check.py",
        "inputs": [
            "data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv",
            "data/derived/priority_mismatch_v1/event_mismatch_summary.csv",
        ],
        "top_shares": TOP_SHARES,
        "scenarios": scenarios,
        "ranking_rule": "exact top-k per event; damage-only ties use xBD damage variables then cell_id",
        "outputs": [
            "strict_budget_event_summary.csv",
            "strict_budget_scenario_metrics_top20.csv",
            "strict_budget_top20_cells.csv",
            "strict_budget_summary.md",
            "reports/figures/fig6_strict_budget_check.png",
            "reports/figures/fig6_strict_budget_check.pdf",
            "reports/figures/fig6_strict_budget_check_grayscale.png",
        ],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    grid = pd.read_csv(args.priority_grid)
    primary_summary = pd.read_csv(args.primary_summary)
    scenarios = scenario_names(grid)

    summary = event_summary(grid, scenarios)
    scenario_table = scenario_metrics(grid, scenarios, top_share=0.20)
    cells = top20_cells(grid, scenarios)

    summary.to_csv(args.out_dir / "strict_budget_event_summary.csv", index=False)
    scenario_table.to_csv(args.out_dir / "strict_budget_scenario_metrics_top20.csv", index=False)
    cells.to_csv(args.out_dir / "strict_budget_top20_cells.csv", index=False)

    write_summary(args.out_dir, summary, primary_summary, scenario_table, scenarios)
    write_manifest(args.out_dir, scenarios)
    make_figure(summary, primary_summary, args.figure_dir)

    top20_total = int(summary.loc[summary["top_share"] == 0.20, "strict_stable_mismatch_count"].sum())
    print(f"strict_budget_summary={args.out_dir / 'strict_budget_summary.md'}")
    print(f"top20_strict_stable_mismatch={top20_total}")
    print(f"figure={args.figure_dir / 'fig6_strict_budget_check.png'}")


if __name__ == "__main__":
    main()
