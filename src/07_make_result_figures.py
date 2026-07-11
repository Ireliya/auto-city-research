#!/usr/bin/env python3
"""Create manuscript/report figures for the first Urban Cup results."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}

SCENARIO_LABELS = {
    "balanced_need": "Balanced",
    "population_sensitive": "Population",
    "accessibility_sensitive": "Accessibility",
}

DRIVER_LABELS = {
    "worldpop_population": "Population",
    "road_density_m_per_km2": "Road density",
    "nearest_facility_m": "Facility distance",
    "facility_count": "Facility count",
    "building_count": "Building count",
    "total_area_m2": "Building area",
    "damaged_building_share": "Damaged share",
    "severe_building_share": "Severe share",
}


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.95)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )


def save_figure(fig: plt.Figure, out_dir: Path, basename: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{basename}.png")
    fig.savefig(out_dir / f"{basename}.pdf")
    plt.close(fig)


def figure_event_summary(summary: pd.DataFrame, out_dir: Path) -> None:
    data = summary.copy()
    data["event_label"] = data["event"].map(EVENT_LABELS)
    data = data.sort_values("stable_mismatch_share", ascending=True)
    palette = sns.color_palette("colorblind", n_colors=len(data))

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), constrained_layout=True)

    axes[0].barh(data["event_label"], data["stable_mismatch_share"] * 100, color=palette)
    axes[0].set_xlabel("Stable mismatch cells (%)")
    axes[0].set_ylabel("")
    axes[0].set_title("a  Mismatch prevalence")
    for y, (_, row) in enumerate(data.iterrows()):
        axes[0].text(row["stable_mismatch_share"] * 100 + 0.2, y, f"n={int(row['stable_mismatch_count'])}", va="center", fontsize=7)

    axes[1].barh(data["event_label"], data["stable_mismatch_population_sum"] / 1000, color=palette)
    axes[1].set_xlabel("Population in mismatch cells (thousand)")
    axes[1].set_ylabel("")
    axes[1].set_title("b  Exposed population")

    for ax in axes:
        ax.grid(axis="x", color="0.88", linewidth=0.6)
        ax.grid(axis="y", visible=False)

    save_figure(fig, out_dir, "fig1_event_mismatch_summary")


def figure_scenario_heatmaps(metrics: pd.DataFrame, out_dir: Path) -> None:
    data = metrics.copy()
    data["event_label"] = data["event"].map(EVENT_LABELS)
    data["scenario_label"] = data["scenario"].map(SCENARIO_LABELS)
    event_order = ["Harvey", "Mexico EQ", "Palu", "Santa Rosa"]
    scenario_order = ["Balanced", "Population", "Accessibility"]

    jaccard = data.pivot(index="event_label", columns="scenario_label", values="top_jaccard").reindex(event_order)[scenario_order]
    count = data.pivot(index="event_label", columns="scenario_label", values="high_need_low_damage_count").reindex(event_order)[scenario_order]

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), constrained_layout=True)
    sns.heatmap(
        jaccard,
        ax=axes[0],
        cmap="viridis",
        annot=True,
        fmt=".2f",
        vmin=0,
        vmax=1,
        cbar_kws={"label": "Top-20 Jaccard"},
    )
    axes[0].set_title("a  Damage-need top overlap")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")

    sns.heatmap(
        count,
        ax=axes[1],
        cmap="magma",
        annot=True,
        fmt=".0f",
        cbar_kws={"label": "Cells"},
    )
    axes[1].set_title("b  High-need / low-damage cells")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("")

    save_figure(fig, out_dir, "fig2_scenario_sensitivity")


def figure_driver_profile(profile: pd.DataFrame, out_dir: Path) -> None:
    data = profile[
        profile["group"].isin(["all_events", "hurricane-harvey", "santa-rosa-wildfire"])
        & profile["variable"].isin(DRIVER_LABELS)
    ].copy()
    data["group_label"] = data["group"].replace(
        {
            "all_events": "All",
            "hurricane-harvey": "Harvey",
            "santa-rosa-wildfire": "Santa Rosa",
        }
    )
    data["driver_label"] = data["variable"].map(DRIVER_LABELS)

    driver_order = [
        "Population",
        "Road density",
        "Facility distance",
        "Facility count",
        "Building count",
        "Building area",
        "Damaged share",
        "Severe share",
    ]
    group_order = ["All", "Harvey", "Santa Rosa"]
    matrix = data.pivot(index="driver_label", columns="group_label", values="standardized_mean_difference").reindex(driver_order)[group_order]

    fig, ax = plt.subplots(figsize=(4.8, 4.2), constrained_layout=True)
    sns.heatmap(
        matrix,
        ax=ax,
        cmap="RdBu_r",
        center=0,
        annot=True,
        fmt=".2f",
        cbar_kws={"label": "Std. mean difference\n(mismatch - other)"},
    )
    ax.set_title("Driver profile of stable mismatch cells")
    ax.set_xlabel("")
    ax.set_ylabel("")
    save_figure(fig, out_dir, "fig3_driver_profile")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-dir", required=True, type=Path)
    parser.add_argument("--driver-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_style()
    summary = pd.read_csv(args.priority_dir / "event_mismatch_summary.csv")
    metrics = pd.read_csv(args.priority_dir / "scenario_rank_metrics.csv")
    profile = pd.read_csv(args.driver_dir / "mismatch_driver_profile.csv")
    figure_event_summary(summary, args.out_dir)
    figure_scenario_heatmaps(metrics, args.out_dir)
    figure_driver_profile(profile, args.out_dir)
    print(f"figures={args.out_dir}")


if __name__ == "__main__":
    main()
