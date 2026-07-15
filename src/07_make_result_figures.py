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

from figure_style import (
    CMAP_BLUE,
    CMAP_DIVERGING,
    CMAP_ROSE,
    INK,
    add_panel_label,
    apply_publication_style,
    color_for_event,
    mm_to_inches,
    save_publication_figure,
    set_heatmap_annotation_contrast,
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
    sns.set_theme(style="white", context="paper")
    apply_publication_style()


def save_figure(fig: plt.Figure, out_dir: Path, basename: str) -> None:
    save_publication_figure(fig, out_dir, basename)


def figure_event_summary(summary: pd.DataFrame, out_dir: Path) -> None:
    data = summary.copy()
    data["event_label"] = data["event"].map(EVENT_LABELS)
    data = data.sort_values("stable_mismatch_share", ascending=True)
    colors = [color_for_event(label) for label in data["event_label"]]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(74)),
        constrained_layout=True,
    )

    axes[0].barh(data["event_label"], data["stable_mismatch_share"] * 100, color=colors, height=0.62)
    axes[0].set_xlabel("Stable mismatch cells (%)")
    axes[0].set_ylabel("")
    axes[0].set_title("Mismatch prevalence", loc="left", pad=7)
    add_panel_label(axes[0], "a", x=-0.17, y=1.04)
    for y, (_, row) in enumerate(data.iterrows()):
        axes[0].text(
            row["stable_mismatch_share"] * 100 + 0.16,
            y,
            f"n = {int(row['stable_mismatch_count'])}",
            va="center",
            fontsize=6.5,
            color=INK,
        )
    axes[0].margins(x=0.16)

    exposed = data["stable_mismatch_population_sum"] / 1000
    axes[1].barh(data["event_label"], exposed, color=colors, height=0.62)
    axes[1].set_xlabel("Population in mismatch cells (thousands)")
    axes[1].set_ylabel("")
    axes[1].set_title("Exposed population", loc="left", pad=7)
    add_panel_label(axes[1], "b", x=-0.17, y=1.04)
    for y, value in enumerate(exposed):
        if value > 0:
            axes[1].text(
                value + max(exposed.max() * 0.018, 0.05),
                y,
                f"{value:.1f}",
                va="center",
                fontsize=6.5,
                color=INK,
            )
    axes[1].margins(x=0.17)

    for ax in axes:
        style_numeric_axis(ax, axis="x")

    save_figure(fig, out_dir, "fig1_event_mismatch_summary")


def figure_scenario_heatmaps(metrics: pd.DataFrame, out_dir: Path) -> None:
    data = metrics.copy()
    data["event_label"] = data["event"].map(EVENT_LABELS)
    data["scenario_label"] = data["scenario"].map(SCENARIO_LABELS)
    event_order = ["Harvey", "Mexico EQ", "Palu", "Santa Rosa"]
    scenario_order = ["Balanced", "Population", "Accessibility"]

    jaccard = data.pivot(index="event_label", columns="scenario_label", values="top_jaccard").reindex(event_order)[scenario_order]
    count = data.pivot(index="event_label", columns="scenario_label", values="high_need_low_damage_count").reindex(event_order)[scenario_order]

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(75)),
        constrained_layout=True,
    )
    sns.heatmap(
        jaccard,
        ax=axes[0],
        cmap=CMAP_BLUE,
        annot=True,
        fmt=".2f",
        vmin=0,
        vmax=1,
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "Top-20 Jaccard", "shrink": 0.78, "pad": 0.025},
    )
    axes[0].set_title("Damage-need top overlap", loc="left", pad=7)
    add_panel_label(axes[0], "a", x=-0.18, y=1.04)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")
    axes[0].tick_params(axis="x", rotation=0)
    set_heatmap_annotation_contrast(axes[0], jaccard.to_numpy())

    sns.heatmap(
        count,
        ax=axes[1],
        cmap=CMAP_ROSE,
        annot=True,
        fmt=".0f",
        vmin=0,
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "Mismatch cells", "shrink": 0.78, "pad": 0.025},
    )
    axes[1].set_title("High-need / low-damage cells", loc="left", pad=7)
    add_panel_label(axes[1], "b", x=-0.18, y=1.04)
    axes[1].set_xlabel("")
    axes[1].set_ylabel("")
    axes[1].tick_params(axis="x", rotation=0)
    set_heatmap_annotation_contrast(axes[1], count.to_numpy())

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

    max_abs = max(2.0, float(matrix.abs().max().max()))
    fig, ax = plt.subplots(
        figsize=(mm_to_inches(112), mm_to_inches(102)),
        constrained_layout=True,
    )
    sns.heatmap(
        matrix,
        ax=ax,
        cmap=CMAP_DIVERGING,
        center=0,
        vmin=-max_abs,
        vmax=max_abs,
        annot=True,
        fmt=".2f",
        linewidths=0.55,
        linecolor="white",
        cbar_kws={"label": "Standardized mean difference\n(mismatch - other)", "shrink": 0.82},
    )
    ax.set_title("Mismatch cells have distinct urban profiles", loc="left", pad=8)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0)
    for text, value in zip(ax.texts, matrix.to_numpy().ravel()):
        text.set_color("white" if abs(float(value)) >= 1.0 else INK)
        text.set_fontsize(6.8)
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
