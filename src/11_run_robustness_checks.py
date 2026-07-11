#!/usr/bin/env python3
"""Run threshold and scenario-consensus robustness checks for priority mismatch.

The main analysis defines stable mismatch at a top-20 inspection budget. This
script stress-tests that decision by varying the inspection budget and by
summarizing how many need-aware scenarios agree on each high-need / low-damage
cell. It uses only derived CSV outputs; no raw imagery or GPU is required.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from PIL import Image


EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}

EVENT_ORDER = ["hurricane-harvey", "mexico-earthquake", "palu-tsunami", "santa-rosa-wildfire"]
TOP_SHARES = [0.10, 0.15, 0.20, 0.25, 0.30]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv"),
        help="Priority mismatch grid CSV from src/05_analyze_priority_mismatch.py.",
    )
    parser.add_argument(
        "--xbd-event-summary",
        type=Path,
        default=Path("data/derived/xbd_core_v1/xbd_event_summary.csv"),
        help="xBD event summary CSV from src/01_parse_xbd_labels.py.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/derived/robustness_v1"),
        help="Output directory for robustness tables.",
    )
    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=Path("reports/figures"),
        help="Output directory for Figure 5.",
    )
    return parser.parse_args()


def scenario_names(grid: pd.DataFrame) -> list[str]:
    names = []
    for col in grid.columns:
        if col.startswith("priority_pct_"):
            names.append(col.removeprefix("priority_pct_"))
    return sorted(names)


def top_mask(event_df: pd.DataFrame, pct_col: str, top_share: float) -> pd.Series:
    cut = event_df[pct_col].quantile(1.0 - top_share)
    return event_df[pct_col] >= cut


def add_threshold_flags(event_df: pd.DataFrame, scenarios: list[str], top_share: float) -> pd.DataFrame:
    event_df = event_df.copy()
    event_df["robust_top_damage"] = top_mask(event_df, "damage_priority_pct", top_share)
    need_cols = []
    for scenario in scenarios:
        col = f"robust_top_need_{scenario}"
        event_df[col] = top_mask(event_df, f"priority_pct_{scenario}", top_share)
        need_cols.append(col)
    event_df["robust_need_top_scenario_count"] = event_df[need_cols].sum(axis=1)
    event_df["robust_stable_mismatch"] = (event_df["robust_need_top_scenario_count"] >= 2) & (~event_df["robust_top_damage"])
    return event_df


def threshold_sensitivity(grid: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    rows = []
    for top_share in TOP_SHARES:
        for event, event_df in grid.groupby("event", sort=True):
            flagged = add_threshold_flags(event_df, scenarios, top_share)
            stable = flagged[flagged["robust_stable_mismatch"]]
            rows.append(
                {
                    "event": event,
                    "top_share": top_share,
                    "cells": int(len(flagged)),
                    "top_damage_count": int(flagged["robust_top_damage"].sum()),
                    "top_damage_actual_share": float(flagged["robust_top_damage"].mean()),
                    "stable_mismatch_count": int(len(stable)),
                    "stable_mismatch_share": float(len(stable) / len(flagged)),
                    "stable_mismatch_population_sum": float(stable["worldpop_population"].sum()),
                    "stable_mismatch_mean_damage_D": float(stable["damage_index_D"].mean()) if len(stable) else 0.0,
                    "stable_mismatch_all_three_scenarios": int((stable["robust_need_top_scenario_count"] == 3).sum()),
                    "stable_mismatch_exactly_two_scenarios": int((stable["robust_need_top_scenario_count"] == 2).sum()),
                }
            )
    return pd.DataFrame(rows)


def scenario_stability(grid: pd.DataFrame, scenarios: list[str], top_share: float = 0.20) -> pd.DataFrame:
    rows = []
    for event, event_df in grid.groupby("event", sort=True):
        flagged = add_threshold_flags(event_df, scenarios, top_share)
        candidates = flagged[~flagged["robust_top_damage"]]
        for need_count in range(0, len(scenarios) + 1):
            subset = candidates[candidates["robust_need_top_scenario_count"] == need_count]
            rows.append(
                {
                    "event": event,
                    "top_share": top_share,
                    "need_top_scenario_count": need_count,
                    "outside_damage_top_cells": int(len(candidates)),
                    "cell_count": int(len(subset)),
                    "cell_share_of_event": float(len(subset) / len(flagged)),
                    "population_sum": float(subset["worldpop_population"].sum()),
                    "mean_damage_D": float(subset["damage_index_D"].mean()) if len(subset) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def low_damage_diagnostic(grid: pd.DataFrame, xbd_summary: pd.DataFrame, scenarios: list[str]) -> pd.DataFrame:
    rows = []
    xbd_by_event = xbd_summary.set_index("event")
    for event, event_df in grid.groupby("event", sort=True):
        flagged = add_threshold_flags(event_df, scenarios, 0.20)
        xbd = xbd_by_event.loc[event] if event in xbd_by_event.index else pd.Series(dtype=float)
        buildings = float(xbd.get("buildings", 0.0))
        damaged_labels = float(xbd.get("damage_destroyed", 0.0)) + float(xbd.get("damage_major-damage", 0.0)) + float(xbd.get("damage_minor-damage", 0.0))
        rows.append(
            {
                "event": event,
                "cells": int(len(event_df)),
                "unique_damage_index_values": int(event_df["damage_index_D"].nunique(dropna=True)),
                "zero_damage_cells": int((event_df["damage_index_D"] == 0).sum()),
                "zero_damage_cell_share": float((event_df["damage_index_D"] == 0).mean()),
                "mean_damage_D": float(event_df["damage_index_D"].mean()),
                "max_damage_D": float(event_df["damage_index_D"].max()),
                "top20_damage_count": int(flagged["robust_top_damage"].sum()),
                "top20_damage_actual_share": float(flagged["robust_top_damage"].mean()),
                "xbd_buildings": int(buildings),
                "xbd_damaged_label_count": int(damaged_labels),
                "xbd_damaged_label_share": float(damaged_labels / buildings) if buildings else 0.0,
            }
        )
    return pd.DataFrame(rows)


def write_summary(
    out_dir: Path,
    threshold: pd.DataFrame,
    stability: pd.DataFrame,
    diagnostics: pd.DataFrame,
    scenarios: list[str],
) -> None:
    primary = threshold[threshold["top_share"] == 0.20].copy()
    total_stable = int(primary["stable_mismatch_count"].sum())
    stable_two_plus = stability[stability["need_top_scenario_count"] >= 2].groupby("event")["cell_count"].sum()
    lines = [
        "# Robustness Checks v1",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Purpose",
        "",
        "Stress-test whether the main mismatch claim depends on a single top-20 threshold or a single need-weight scenario.",
        "",
        "## Inputs",
        "",
        "- `data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv`",
        "- `data/derived/xbd_core_v1/xbd_event_summary.csv`",
        "",
        "## Scenarios",
        "",
        ", ".join(f"`{name}`" for name in scenarios),
        "",
        "## Key Findings",
        "",
        f"- At the pre-registered top-20 threshold, stable mismatch remains `{total_stable}` cells.",
        "- Threshold sensitivity shows whether the same event ordering persists as the inspection budget changes from 10% to 30%.",
        "- Scenario stability reports how many outside-damage-top cells are high need in one, two, or all three need-aware scenarios.",
        "- Low-damage diagnostics identify Mexico as a boundary case where the damage-only top set is inflated by tied near-zero damage scores.",
        "",
        "## Top-20 Event Summary",
        "",
        "| Event | Stable mismatch cells | Stable mismatch share | Population in stable mismatch cells |",
        "| --- | ---: | ---: | ---: |",
    ]
    for event in EVENT_ORDER:
        row = primary[primary["event"] == event].iloc[0]
        lines.append(
            f"| {EVENT_LABELS.get(event, event)} | {int(row['stable_mismatch_count'])} | {row['stable_mismatch_share'] * 100:.2f}% | {row['stable_mismatch_population_sum']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Threshold Stress Test",
            "",
            "| Event | Stable cells at top-10 | top-20 | top-30 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for event in EVENT_ORDER:
        event_rows = threshold[threshold["event"] == event].set_index("top_share")
        lines.append(
            f"| {EVENT_LABELS.get(event, event)} | {int(event_rows.loc[0.10, 'stable_mismatch_count'])} | {int(event_rows.loc[0.20, 'stable_mismatch_count'])} | {int(event_rows.loc[0.30, 'stable_mismatch_count'])} |"
        )
    lines.extend(
        [
            "",
            "## Scenario Consensus at Top-20",
            "",
            "| Event | 1 scenario | 2 scenarios | 3 scenarios | Stable total (2+) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for event in EVENT_ORDER:
        event_rows = stability[stability["event"] == event].set_index("need_top_scenario_count")
        one = int(event_rows.loc[1, "cell_count"])
        two = int(event_rows.loc[2, "cell_count"])
        three = int(event_rows.loc[3, "cell_count"])
        total = int(stable_two_plus.get(event, 0))
        lines.append(f"| {EVENT_LABELS.get(event, event)} | {one} | {two} | {three} | {total} |")
    lines.extend(
        [
            "",
            "## Low-Damage Boundary Diagnostic",
            "",
            "| Event | Zero-damage cells | Top-20 damage actual share | xBD damaged-label share |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for event in EVENT_ORDER:
        row = diagnostics[diagnostics["event"] == event].iloc[0]
        lines.append(
            f"| {EVENT_LABELS.get(event, event)} | {int(row['zero_damage_cells'])} | {row['top20_damage_actual_share'] * 100:.2f}% | {row['xbd_damaged_label_share'] * 100:.2f}% |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Limit",
            "",
            "These checks do not create a new allocation rule. They only test how sensitive the audit signal is to inspection-budget and scenario-consensus assumptions.",
        ]
    )
    (out_dir / "robustness_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.95)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )


def make_figure(threshold: pd.DataFrame, stability: pd.DataFrame, figure_dir: Path) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    threshold = threshold.copy()
    threshold["event_label"] = threshold["event"].map(EVENT_LABELS)
    threshold["inspection_budget_pct"] = threshold["top_share"] * 100
    stability = stability[stability["need_top_scenario_count"].isin([1, 2, 3])].copy()
    stability["event_label"] = stability["event"].map(EVENT_LABELS)
    matrix = (
        stability.pivot(index="event_label", columns="need_top_scenario_count", values="cell_count")
        .reindex([EVENT_LABELS[e] for e in EVENT_ORDER])
        .fillna(0)
    )
    matrix.columns = [f"{int(col)} scenario" if int(col) == 1 else f"{int(col)} scenarios" for col in matrix.columns]

    palette = sns.color_palette("colorblind", n_colors=len(EVENT_ORDER))
    markers = ["o", "s", "^", "D"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), constrained_layout=True)

    for idx, event in enumerate(EVENT_ORDER):
        event_df = threshold[threshold["event"] == event]
        axes[0].plot(
            event_df["inspection_budget_pct"],
            event_df["stable_mismatch_count"],
            marker=markers[idx],
            linewidth=1.7,
            markersize=4.5,
            color=palette[idx],
            label=EVENT_LABELS[event],
        )
    axes[0].set_title("a  Threshold sensitivity")
    axes[0].set_xlabel("Priority inspection budget (% cells)")
    axes[0].set_ylabel("Stable mismatch cells")
    axes[0].set_xticks([10, 15, 20, 25, 30])
    axes[0].legend(frameon=False, fontsize=7, loc="upper left")
    axes[0].grid(axis="y", color="0.88", linewidth=0.6)
    axes[0].grid(axis="x", visible=False)

    sns.heatmap(
        matrix,
        ax=axes[1],
        cmap="magma",
        annot=True,
        fmt=".0f",
        linewidths=0.4,
        linecolor="white",
        cbar_kws={"label": "Cells outside damage top-20"},
    )
    axes[1].set_title("b  Scenario consensus at top-20")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("")

    fig.savefig(figure_dir / "fig5_robustness_checks.png")
    fig.savefig(figure_dir / "fig5_robustness_checks.pdf")
    plt.close(fig)

    with Image.open(figure_dir / "fig5_robustness_checks.png") as img:
        img.convert("L").save(figure_dir / "fig5_robustness_checks_grayscale.png")


def main() -> None:
    args = parse_args()
    grid = pd.read_csv(args.priority_grid)
    xbd_summary = pd.read_csv(args.xbd_event_summary)
    scenarios = scenario_names(grid)
    if not scenarios:
        raise ValueError("No scenario priority columns found")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    threshold = threshold_sensitivity(grid, scenarios)
    stability = scenario_stability(grid, scenarios, top_share=0.20)
    diagnostics = low_damage_diagnostic(grid, xbd_summary, scenarios)

    threshold.to_csv(args.out_dir / "threshold_sensitivity.csv", index=False)
    stability.to_csv(args.out_dir / "scenario_stability_top20.csv", index=False)
    diagnostics.to_csv(args.out_dir / "low_damage_event_diagnostic.csv", index=False)
    write_summary(args.out_dir, threshold, stability, diagnostics, scenarios)
    setup_style()
    make_figure(threshold, stability, args.figure_dir)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/11_run_robustness_checks.py",
        "inputs": [str(args.priority_grid), str(args.xbd_event_summary)],
        "scenarios": scenarios,
        "top_shares": TOP_SHARES,
        "outputs": [
            "threshold_sensitivity.csv",
            "scenario_stability_top20.csv",
            "low_damage_event_diagnostic.csv",
            "robustness_summary.md",
            "reports/figures/fig5_robustness_checks.png",
            "reports/figures/fig5_robustness_checks.pdf",
            "reports/figures/fig5_robustness_checks_grayscale.png",
        ],
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    primary = threshold[threshold["top_share"] == 0.20]
    print(f"scenarios={','.join(scenarios)}")
    print(f"top20_stable_mismatch={int(primary['stable_mismatch_count'].sum())}")
    print(f"threshold_sensitivity={args.out_dir / 'threshold_sensitivity.csv'}")
    print(f"scenario_stability={args.out_dir / 'scenario_stability_top20.csv'}")
    print(f"low_damage_diagnostic={args.out_dir / 'low_damage_event_diagnostic.csv'}")
    print(f"figure={args.figure_dir / 'fig5_robustness_checks.png'}")


if __name__ == "__main__":
    main()
