#!/usr/bin/env python3
"""Create OSM-context case figures for damage-vs-need priority mismatch."""

from __future__ import annotations

import argparse
from pathlib import Path

import contextily as cx
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Patch, Rectangle
import pandas as pd

from figure_style import (
    CMAP_BLUE,
    INK,
    ROSE,
    add_panel_label,
    apply_publication_style,
    mm_to_inches,
    save_publication_figure,
)


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"


CASE_EVENTS = ["hurricane-harvey", "santa-rosa-wildfire"]
EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "santa-rosa-wildfire": "Santa Rosa",
}
NEED_SCORE_COLS = [
    "score_balanced_need",
    "score_population_sensitive",
    "score_accessibility_sensitive",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-grid",
        default="data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv",
        help="Priority mismatch grid CSV.",
    )
    parser.add_argument(
        "--out-dir",
        default="reports/figures",
        help="Directory for exported figures.",
    )
    parser.add_argument(
        "--basename",
        default="fig4_case_map_mismatch",
        help="Output basename without extension.",
    )
    parser.add_argument(
        "--tile-cache-dir",
        default="data/cache/contextily",
        help="Cache directory for OpenStreetMap basemap tiles.",
    )
    parser.add_argument(
        "--no-basemap",
        action="store_true",
        help="Render the analytical grid without network basemap tiles.",
    )
    return parser.parse_args()


def set_style() -> None:
    apply_publication_style(font_size=7.0)


def add_grid_layer(
    ax: plt.Axes,
    df: pd.DataFrame,
    value_col: str,
    cmap: mpl.colors.Colormap,
    norm: mpl.colors.Normalize,
) -> PatchCollection:
    patches = [
        Rectangle(
            (row.x_min, row.y_min),
            row.x_max - row.x_min,
            row.y_max - row.y_min,
        )
        for row in df.itertuples(index=False)
    ]
    collection = PatchCollection(
        patches,
        cmap=cmap,
        norm=norm,
        linewidths=0.08,
        edgecolors="#f4f4f4",
        alpha=0.72,
    )
    collection.set_array(df[value_col].to_numpy())
    ax.add_collection(collection)
    return collection


def add_mismatch_outlines(ax: plt.Axes, df: pd.DataFrame) -> None:
    mismatch = df[df["stable_mismatch"].astype(bool)]
    for row in mismatch.itertuples(index=False):
        x = row.x_min
        y = row.y_min
        w = row.x_max - row.x_min
        h = row.y_max - row.y_min
        ax.add_patch(
            Rectangle(
                (x, y),
                w,
                h,
                fill=False,
                edgecolor=ROSE,
                linewidth=1.25,
                zorder=5,
            )
        )
        ax.add_patch(
            Rectangle(
                (x + 0.03 * w, y + 0.03 * h),
                0.94 * w,
                0.94 * h,
                fill=False,
                edgecolor="white",
                linewidth=0.55,
                hatch="///",
                zorder=6,
            )
        )


def add_scale_bar(ax: plt.Axes, length_km: float = 5.0) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + 0.06 * (x1 - x0)
    y = y0 + 0.06 * (y1 - y0)
    length_m = length_km * 1000.0
    ax.plot([x, x + length_m], [y, y], color="black", lw=1.5, solid_capstyle="butt")
    ax.text(
        x + length_m / 2,
        y + 0.015 * (y1 - y0),
        f"{length_km:g} km",
        ha="center",
        va="bottom",
        fontsize=7,
        color="black",
    )


def format_map_axis(ax: plt.Axes, df: pd.DataFrame) -> None:
    pad_x = max(500.0, (df.x_max.max() - df.x_min.min()) * 0.03)
    pad_y = max(500.0, (df.y_max.max() - df.y_min.min()) * 0.03)
    ax.set_xlim(df.x_min.min() - pad_x, df.x_max.max() + pad_x)
    ax.set_ylim(df.y_min.min() - pad_y, df.y_max.max() + pad_y)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    add_scale_bar(ax)


def crop_to_mismatch_window(df: pd.DataFrame, buffer_m: float = 3000.0) -> pd.DataFrame:
    """Return cells inside a mismatch-centered case window.

    The full Harvey footprint is vertically long and makes the grid visually tiny.
    A stable-mismatch window preserves the case-study argument while allowing
    readers to inspect the local spatial pattern.
    """
    mismatch = df[df["stable_mismatch"].astype(bool)]
    if mismatch.empty:
        return df.copy()
    x_min = mismatch.x_min.min() - buffer_m
    x_max = mismatch.x_max.max() + buffer_m
    y_min = mismatch.y_min.min() - buffer_m
    y_max = mismatch.y_max.max() + buffer_m
    window = df[
        (df.x_max >= x_min)
        & (df.x_min <= x_max)
        & (df.y_max >= y_min)
        & (df.y_min <= y_max)
    ].copy()
    return window if not window.empty else df.copy()


def add_osm_basemap(ax: plt.Axes, epsg: int) -> None:
    cx.add_basemap(
        ax,
        source="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        crs=f"EPSG:{epsg}",
        attribution=False,
        reset_extent=False,
    )


def make_figure(
    df: pd.DataFrame,
    out_dir: Path,
    basename: str,
    tile_cache_dir: Path,
    use_basemap: bool,
) -> dict[str, Path]:
    set_style()
    cx.set_cache_dir(tile_cache_dir)
    df = df.copy()
    df["mean_need_score"] = df[NEED_SCORE_COLS].mean(axis=1)

    cmap = CMAP_BLUE
    norm = mpl.colors.Normalize(vmin=0, vmax=1)
    fig, axes = plt.subplots(
        nrows=len(CASE_EVENTS),
        ncols=2,
        figsize=(mm_to_inches(183), mm_to_inches(150)),
        constrained_layout=True,
    )
    fig.set_constrained_layout_pads(w_pad=0.03, h_pad=0.04, hspace=0.07, wspace=0.03)

    panel_letters = ["a", "b", "c", "d"]
    panel_idx = 0
    first_collection = None
    for row_idx, event in enumerate(CASE_EVENTS):
        event_df = df[df["event"] == event].sort_values(["iy", "ix"]).copy()
        if event_df.empty:
            raise ValueError(f"No rows found for event: {event}")
        plot_df = crop_to_mismatch_window(event_df).sort_values(["iy", "ix"])
        for col_idx, (value_col, col_title) in enumerate(
            [
                ("damage_norm", "damage-only"),
                ("mean_need_score", "multi-source"),
            ]
        ):
            ax = axes[row_idx, col_idx]
            format_map_axis(ax, plot_df)
            if use_basemap:
                add_osm_basemap(ax, int(plot_df["utm_epsg"].iloc[0]))
            collection = add_grid_layer(ax, plot_df, value_col, cmap, norm)
            if first_collection is None:
                first_collection = collection
            add_mismatch_outlines(ax, plot_df)
            mismatch_n = int(plot_df["stable_mismatch"].astype(bool).sum())
            ax.set_title(
                f"{EVENT_LABELS[event]} | {col_title}",
                loc="left",
                x=0.06,
                fontsize=7.7,
                pad=4,
            )
            add_panel_label(ax, panel_letters[panel_idx], x=-0.03, y=1.025)
            ax.text(
                0.99,
                0.965,
                f"n = {mismatch_n}",
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=6.3,
                color=INK,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "none",
                    "alpha": 0.78,
                    "pad": 1.2,
                },
                zorder=10,
            )
            panel_idx += 1

    cbar = fig.colorbar(
        first_collection,
        ax=axes.ravel().tolist(),
        orientation="horizontal",
        fraction=0.035,
        pad=0.018,
        aspect=45,
    )
    cbar.set_label("Event-normalized score (0-1)")
    axes[0, 0].legend(
        handles=[Patch(facecolor="white", edgecolor=ROSE, linewidth=1.2, hatch="///", label="Scenario-consensus disagreement")],
        loc="lower right",
        fontsize=6.3,
        handlelength=1.7,
        borderaxespad=0.25,
    )
    if use_basemap:
        axes[0, 1].text(
            0.99,
            0.01,
            "Basemap: (c) OpenStreetMap contributors, (c) CARTO",
            transform=axes[0, 1].transAxes,
            ha="right",
            va="bottom",
            fontsize=5.5,
            color="#333333",
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.72,
                "pad": 1.2,
            },
            zorder=20,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    return save_publication_figure(fig, out_dir, basename)


def main() -> None:
    args = parse_args()
    input_grid = Path(args.input_grid)
    out_dir = Path(args.out_dir)
    df = pd.read_csv(input_grid)
    missing_cols = [
        col
        for col in [
            "event",
            "x_min",
            "x_max",
            "y_min",
            "y_max",
            "damage_norm",
            "stable_mismatch",
            *NEED_SCORE_COLS,
        ]
        if col not in df.columns
    ]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    outputs = make_figure(
        df,
        out_dir,
        args.basename,
        tile_cache_dir=Path(args.tile_cache_dir),
        use_basemap=not args.no_basemap,
    )
    print("Created case map figure:")
    for label, path in outputs.items():
        print(f"- {label}: {path}")


if __name__ == "__main__":
    main()
