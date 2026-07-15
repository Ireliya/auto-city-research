#!/usr/bin/env python3
"""Create the global, multi-scale study overview and website map assets.

The figure is schematic where it explains the audit logic, but every map,
count, event location, and scale-retention state is generated from frozen
project outputs. It does not imply global coverage or verified unmet need.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import geopandas as gpd
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd
from shapely.geometry import Point, box


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from figure_style import (  # noqa: E402
    BLUE,
    CMAP_ROSE,
    EVENT_COLORS,
    EVENT_MARKERS,
    GOLD,
    GRID,
    INK,
    LIGHT_NEUTRAL,
    MUTED,
    ROSE,
    TEAL,
    add_panel_label,
    apply_publication_style,
    mm_to_inches,
    save_publication_figure,
)


OVERVIEW_BASENAME = "study_overview_global_multiscale"
FOCUS_CELL_ID = "mexico-earthquake_500m_3_38"
EVENT_ORDER = [
    "hurricane-harvey",
    "mexico-earthquake",
    "palu-tsunami",
    "santa-rosa-wildfire",
]
EVENT_META = {
    "hurricane-harvey": {
        "name": "Hurricane Harvey",
        "short": "Harvey",
        "hazard": "Flooding",
    },
    "mexico-earthquake": {
        "name": "Mexico earthquake",
        "short": "Mexico EQ",
        "hazard": "Earthquake",
    },
    "palu-tsunami": {
        "name": "Palu tsunami",
        "short": "Palu",
        "hazard": "Tsunami",
    },
    "santa-rosa-wildfire": {
        "name": "Santa Rosa wildfire",
        "short": "Santa Rosa",
        "hazard": "Wildfire",
    },
}
SCALE_SUPPORT_COLUMNS = {
    250: "scale_250m_support_both_resolutions",
    500: "scale_500m_support_both_resolutions",
    1000: "scale_1000m_support_both_resolutions",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports" / "figures",
        help="Publication figure output directory.",
    )
    parser.add_argument(
        "--derived-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "derived" / "study_overview_v1",
        help="Manifest and compact summary output directory.",
    )
    parser.add_argument(
        "--site-dir",
        type=Path,
        default=PROJECT_ROOT / "docs",
        help="Static website root for generated assets and data.",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_paths() -> dict[str, Path]:
    base = PROJECT_ROOT / "data" / "derived"
    return {
        "world": base / "study_overview_v1" / "ne_110m_admin_0_countries.geojson",
        "buildings": base / "xbd_core_v1" / "xbd_buildings.csv",
        "primary_grid": base / "multiscale_100m_v1" / "worldpop_500m" / "damage_osm_worldpop_grid_500m.geojson",
        "scale_250": base / "multiscale_100m_v1" / "worldpop_250m" / "damage_osm_worldpop_grid_250m.geojson",
        "scale_500": base / "multiscale_100m_v1" / "worldpop_500m" / "damage_osm_worldpop_grid_500m.geojson",
        "scale_1000": base / "multiscale_100m_v1" / "worldpop_1000m" / "damage_osm_worldpop_grid_1000m.geojson",
        "primary_summary": base / "priority_mismatch_100m_v1" / "event_mismatch_summary.csv",
        "strict_summary": base / "strict_budget_100m_v1" / "strict_budget_event_summary.csv",
        "candidates": base / "final_consensus_v1" / "final_consensus_candidates.geojson",
        "final_summary": base / "final_consensus_v1" / "final_consensus_event_summary.csv",
        "historical_osm": base / "historical_osm_v1" / "historical_osm_event_summary.csv",
    }


def require_inputs(paths: dict[str, Path]) -> None:
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing study-overview inputs: " + ", ".join(missing))


def load_event_overview(paths: dict[str, Path]) -> pd.DataFrame:
    building_counts = (
        pd.read_csv(paths["buildings"], usecols=["event"])
        .groupby("event")
        .size()
        .rename("buildings")
    )
    grid = gpd.read_file(paths["primary_grid"])
    locations = (
        grid.groupby("event")
        .agg(
            cells=("cell_id", "size"),
            longitude=("cell_center_lon", "mean"),
            latitude=("cell_center_lat", "mean"),
        )
    )
    primary = pd.read_csv(paths["primary_summary"]).set_index("event")
    strict = pd.read_csv(paths["strict_summary"])
    strict = strict[np.isclose(strict["top_share"], 0.20)].set_index("event")
    final = pd.read_csv(paths["final_summary"]).set_index("event")
    historical = pd.read_csv(paths["historical_osm"]).set_index("event")

    overview = locations.join(building_counts).join(
        primary[["stable_mismatch_count"]]
    ).join(
        strict[["strict_stable_mismatch_count"]]
    ).join(
        final[["high_confidence_disagreement_cells", "temporally_supported_high_confidence_cells"]]
    ).join(
        historical[["temporal_evidence"]]
    )
    overview = overview.reindex(EVENT_ORDER).reset_index()
    overview["name"] = overview["event"].map(lambda event: EVENT_META[event]["name"])
    overview["short_name"] = overview["event"].map(lambda event: EVENT_META[event]["short"])
    overview["hazard"] = overview["event"].map(lambda event: EVENT_META[event]["hazard"])
    overview = overview.rename(
        columns={
            "stable_mismatch_count": "percentile_disagreement",
            "strict_stable_mismatch_count": "exact_top20_disagreement",
            "high_confidence_disagreement_cells": "robust_non_temporal",
            "temporally_supported_high_confidence_cells": "temporal_support",
            "temporal_evidence": "historical_osm_evidence",
        }
    )
    numeric = [
        "cells",
        "buildings",
        "percentile_disagreement",
        "exact_top20_disagreement",
        "robust_non_temporal",
        "temporal_support",
    ]
    overview[numeric] = overview[numeric].astype(int)
    return overview


def load_focus_data(paths: dict[str, Path]) -> tuple[gpd.GeoDataFrame, dict[int, gpd.GeoDataFrame], gpd.GeoDataFrame, tuple[float, float, float, float]]:
    candidates = gpd.read_file(paths["candidates"])
    focus = candidates[candidates["cell_id"] == FOCUS_CELL_ID].copy()
    if len(focus) != 1:
        raise RuntimeError(f"Expected one focus cell {FOCUS_CELL_ID!r}, found {len(focus)}")
    focus = focus.to_crs(4326)
    center = focus.geometry.iloc[0].centroid

    half_width = 0.016
    half_height = 0.013
    bounds = (
        center.x - half_width,
        center.y - half_height,
        center.x + half_width,
        center.y + half_height,
    )
    crop = box(*bounds)

    scale_grids: dict[int, gpd.GeoDataFrame] = {}
    for scale in (250, 500, 1000):
        frame = gpd.read_file(paths[f"scale_{scale}"]).to_crs(4326)
        frame = frame[(frame["event"] == "mexico-earthquake") & frame.geometry.intersects(crop)].copy()
        frame["retained_here"] = bool(focus.iloc[0][SCALE_SUPPORT_COLUMNS[scale]])
        scale_grids[scale] = frame

    building_columns = ["event", "damage_subtype", "damage_score", "lon_centroid", "lat_centroid"]
    buildings = pd.read_csv(paths["buildings"], usecols=building_columns)
    buildings = buildings[
        (buildings["event"] == "mexico-earthquake")
        & buildings["lon_centroid"].between(bounds[0], bounds[2])
        & buildings["lat_centroid"].between(bounds[1], bounds[3])
    ].copy()
    building_points = gpd.GeoDataFrame(
        buildings,
        geometry=gpd.points_from_xy(buildings["lon_centroid"], buildings["lat_centroid"]),
        crs=4326,
    )
    return focus, scale_grids, building_points, bounds


def style_map_axis(ax: plt.Axes, bounds: tuple[float, float, float, float]) -> None:
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.55)
        spine.set_edgecolor("#B9C1C6")


def make_reference_mesh(
    grid: gpd.GeoDataFrame,
    bounds: tuple[float, float, float, float],
    scale: int,
) -> gpd.GeoDataFrame:
    """Reconstruct the regular projected lattice behind occupied grid cells."""
    epsg = int(grid["utm_epsg"].iloc[0])
    crop_utm = gpd.GeoSeries([box(*bounds)], crs=4326).to_crs(epsg)
    min_x, min_y, max_x, max_y = crop_utm.total_bounds
    origin_x = float(grid["grid_origin_x"].iloc[0])
    origin_y = float(grid["grid_origin_y"].iloc[0])
    start_x = origin_x + np.floor((min_x - origin_x) / scale) * scale
    start_y = origin_y + np.floor((min_y - origin_y) / scale) * scale
    geometries = []
    for x_value in np.arange(start_x, max_x + scale, scale):
        for y_value in np.arange(start_y, max_y + scale, scale):
            geometries.append(box(x_value, y_value, x_value + scale, y_value + scale))
    mesh = gpd.GeoDataFrame({"geometry": geometries}, crs=epsg).to_crs(4326)
    return mesh[mesh.geometry.intersects(box(*bounds))]


def plot_scale_map(
    ax: plt.Axes,
    grid: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    focus: gpd.GeoDataFrame,
    bounds: tuple[float, float, float, float],
    scale: int,
    *,
    dark: bool = False,
) -> None:
    background = "#11181B" if dark else "#F5F7F8"
    boundary = "#6E8088" if dark else "#AAB5BB"
    neutral_points = "#A8B5BA" if dark else "#7C858A"
    ax.set_facecolor(background)

    mesh = make_reference_mesh(grid, bounds, scale)
    mesh.boundary.plot(
        ax=ax,
        color="#26343A" if dark else "#E2E6E8",
        linewidth=0.38 if scale == 250 else 0.58,
        alpha=0.92,
        zorder=1,
    )

    values = grid["damage_index_D"].fillna(0).astype(float)
    upper = max(float(values.quantile(0.96)), 0.05)
    cmap = (
        LinearSegmentedColormap.from_list(
            "site_dark_damage",
            ["#1A252A", "#334249", "#6B4850", "#B6435A"],
        )
        if dark
        else CMAP_ROSE
    )
    grid.plot(
        ax=ax,
        column="damage_index_D",
        cmap=cmap,
        norm=Normalize(vmin=0, vmax=upper),
        edgecolor=boundary,
        linewidth=0.35 if scale == 250 else 0.6,
        alpha=0.96 if dark else 0.72,
        zorder=2,
    )

    undamaged = buildings[buildings["damage_score"].fillna(0) <= 0]
    damaged = buildings[buildings["damage_score"].fillna(0) > 0]
    if not undamaged.empty:
        undamaged.plot(ax=ax, color=neutral_points, markersize=2.1 if dark else 1.5, alpha=0.62, zorder=4)
    if not damaged.empty:
        damaged.plot(ax=ax, color="#F37777" if dark else ROSE, markersize=9, alpha=0.95, zorder=5)

    center = focus.geometry.iloc[0].centroid
    point = Point(center.x, center.y)
    containing = grid[grid.geometry.covers(point)]
    if containing.empty:
        containing = grid[grid.geometry.intersects(point.buffer(1e-8))]
    if not containing.empty:
        containing.boundary.plot(ax=ax, color="#F5B942" if dark else GOLD, linewidth=2.0, zorder=7)
    ax.scatter(
        [center.x],
        [center.y],
        marker="*",
        s=42 if dark else 30,
        color="#F5B942" if dark else GOLD,
        edgecolor="#11181B" if dark else "white",
        linewidth=0.5,
        zorder=8,
    )
    style_map_axis(ax, bounds)


def add_world_map(ax: plt.Axes, world: gpd.GeoDataFrame, overview: pd.DataFrame) -> None:
    continent_col = "CONTINENT" if "CONTINENT" in world.columns else None
    if continent_col:
        world = world[world[continent_col] != "Antarctica"]
    world.plot(ax=ax, facecolor="#E8ECEF", edgecolor="#AEB8BE", linewidth=0.32)
    ax.set_xlim(-170, 155)
    ax.set_ylim(-50, 72)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    label_offsets = {
        "hurricane-harvey": (8, 14),
        "mexico-earthquake": (-8, -19),
        "palu-tsunami": (9, -15),
        "santa-rosa-wildfire": (-7, 16),
    }
    alignments = {
        "hurricane-harvey": "left",
        "mexico-earthquake": "right",
        "palu-tsunami": "left",
        "santa-rosa-wildfire": "right",
    }
    for row in overview.itertuples(index=False):
        short = EVENT_META[row.event]["short"]
        color = EVENT_COLORS[short]
        marker = EVENT_MARKERS[short]
        ax.scatter(
            row.longitude,
            row.latitude,
            marker=marker,
            s=43,
            facecolor=color,
            edgecolor="white",
            linewidth=0.8,
            zorder=5,
        )
        offset = label_offsets[row.event]
        annotation = ax.annotate(
            f"{row.name}\n{row.buildings:,} buildings | {row.cells} cells",
            xy=(row.longitude, row.latitude),
            xytext=offset,
            textcoords="offset points",
            ha=alignments[row.event],
            va="center",
            fontsize=6.0,
            color=INK,
            linespacing=1.15,
            arrowprops={"arrowstyle": "-", "color": color, "linewidth": 0.65},
            zorder=6,
        )
        annotation.set_path_effects([path_effects.withStroke(linewidth=2.2, foreground="white")])

    ax.text(
        0.01,
        0.03,
        "Four selected xBD study footprints; marker positions are event-footprint centroids.",
        transform=ax.transAxes,
        fontsize=6.0,
        color=MUTED,
        ha="left",
        va="bottom",
    )
    ax.text(
        0.99,
        0.03,
        "Countries: Natural Earth (public domain)",
        transform=ax.transAxes,
        fontsize=5.7,
        color=MUTED,
        ha="right",
        va="bottom",
    )


def rounded_box(
    ax: plt.Axes,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    *,
    facecolor: str = "white",
    edgecolor: str = LIGHT_NEUTRAL,
    textcolor: str = INK,
    fontsize: float = 6.1,
    min_fontsize: float = 4.4,
    weight: str = "normal",
) -> None:
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=0.7,
        edgecolor=edgecolor,
        facecolor=facecolor,
    )
    ax.add_patch(patch)
    label = ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color=textcolor,
        fontweight=weight,
        linespacing=1.15,
        clip_on=True,
    )
    label.set_clip_path(patch)

    # Fit against the rendered patch, not an estimated character count. This
    # keeps SVG/PDF labels inside their boxes across font backends.
    current_size = fontsize
    for _ in range(16):
        ax.figure.canvas.draw()
        renderer = ax.figure.canvas.get_renderer()
        text_box = label.get_window_extent(renderer=renderer)
        patch_box = patch.get_window_extent(renderer=renderer)
        if text_box.width <= patch_box.width * 0.88 and text_box.height <= patch_box.height * 0.82:
            break
        current_size = max(min_fontsize, current_size - 0.18)
        label.set_fontsize(current_size)
        if current_size <= min_fontsize:
            break


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], color: str = "#8C989E") -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=7,
            linewidth=0.7,
            color=color,
            shrinkA=2,
            shrinkB=2,
        )
    )


def draw_audit_framework(ax: plt.Axes) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Fixed-gate disagreement audit", loc="left", fontsize=7.5, color=INK, pad=5)

    rounded_box(ax, (0.02, 0.81), 0.41, 0.13, "Damage-only\nrankings", facecolor="#F8E7EA", edgecolor="#D8A3AE", textcolor="#7F2946", weight="bold")
    rounded_box(ax, (0.57, 0.81), 0.41, 0.13, "Multi-source priority\nscenarios", facecolor="#E8F1F5", edgecolor="#9DBDCE", textcolor=BLUE, weight="bold")
    ax.text(0.50, 0.875, "versus", ha="center", va="center", fontsize=5.1, color=MUTED)

    ax.text(
        0.50,
        0.735,
        "4 damage baselines  |  20,000 weight draws\n2 population products  |  3 rebuilt scales",
        ha="center",
        va="center",
        fontsize=5.35,
        color=MUTED,
        linespacing=1.25,
    )
    arrow(ax, (0.50, 0.695), (0.50, 0.665))

    stages = [
        (0.06, 0.545, 0.88, 0.11, "1,448 cells", "Audited universe", "#F2F4F5", "#AEB8BE", INK),
        (0.10, 0.390, 0.80, 0.11, "73 percentile / 115 exact top-20%", "Diagnostic disagreements", "#E8F1F5", "#9DBDCE", BLUE),
        (0.18, 0.225, 0.64, 0.12, "4 cells", "Cross-definition robust\nMexico only", "#F7EDD9", "#D8B871", "#76551B"),
        (0.27, 0.070, 0.46, 0.11, "0 cells", "Historical OSM support", "#F8E7EA", "#D8A3AE", "#7F2946"),
    ]
    for index, (x, y, w, h, headline, subline, face, edge, color) in enumerate(stages):
        rounded_box(ax, (x, y), w, h, f"{headline}\n{subline}", facecolor=face, edgecolor=edge, textcolor=color, fontsize=5.75, weight="bold" if index >= 2 else "normal")
        if index < len(stages) - 1:
            next_y = stages[index + 1][1] + stages[index + 1][3]
            arrow(ax, (0.50, y - 0.008), (0.50, next_y + 0.008))

    ax.text(
        0.50,
        0.01,
        "External proxies remain mixed and construct-specific;\nnone is treated as true unmet need.",
        ha="center",
        va="bottom",
        fontsize=4.45,
        color=MUTED,
        linespacing=1.12,
    )


def make_publication_overview(
    world: gpd.GeoDataFrame,
    overview: pd.DataFrame,
    focus: gpd.GeoDataFrame,
    scale_grids: dict[int, gpd.GeoDataFrame],
    buildings: gpd.GeoDataFrame,
    bounds: tuple[float, float, float, float],
    output_dir: Path,
) -> dict[str, Path]:
    apply_publication_style(6.8)
    fig = plt.figure(figsize=(mm_to_inches(183), mm_to_inches(139)))
    outer = fig.add_gridspec(2, 2, height_ratios=[0.93, 1.07], width_ratios=[1.78, 1.0], hspace=0.20, wspace=0.16)

    world_ax = fig.add_subplot(outer[0, :])
    add_world_map(world_ax, world, overview)
    add_panel_label(world_ax, "a", x=-0.005, y=0.99)
    world_ax.set_title("A four-event audit across hazards and urban contexts", loc="left", fontsize=8.0, color=INK, pad=3)

    scale_container = outer[1, 0].subgridspec(1, 3, wspace=0.08)
    scale_axes = []
    for index, scale in enumerate((250, 500, 1000)):
        ax = fig.add_subplot(scale_container[0, index])
        plot_scale_map(ax, scale_grids[scale], buildings, focus, bounds, scale)
        retained = bool(focus.iloc[0][SCALE_SUPPORT_COLUMNS[scale]])
        ax.set_title(
            f"{scale:,} m\n{'retained' if retained else 'not retained'}",
            fontsize=6.4,
            color=INK if retained else MUTED,
            pad=4,
        )
        scale_axes.append(ax)
    add_panel_label(scale_axes[0], "b", x=-0.16, y=1.12)
    scale_axes[0].text(
        0.0,
        1.25,
        "Same Mexico candidate area, independently rebuilt grids",
        transform=scale_axes[0].transAxes,
        fontsize=7.5,
        color=INK,
        ha="left",
        va="bottom",
        clip_on=False,
    )
    scale_axes[0].text(
        0.0,
        -0.13,
        "Gray points: no-damage labels  |  rose: damaged labels  |  gold: containing cell",
        transform=scale_axes[0].transAxes,
        fontsize=5.4,
        color=MUTED,
        ha="left",
        va="top",
        clip_on=False,
    )

    framework_ax = fig.add_subplot(outer[1, 1])
    draw_audit_framework(framework_ax)
    add_panel_label(framework_ax, "c", x=-0.08, y=1.02)

    fig.subplots_adjust(left=0.035, right=0.985, top=0.965, bottom=0.055)
    return save_publication_figure(fig, output_dir, OVERVIEW_BASENAME, dpi=600)


def make_site_hero(world: gpd.GeoDataFrame, overview: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    apply_publication_style(8.0)
    fig = plt.figure(figsize=(12, 6.5), facecolor="#11181B")
    ax = fig.add_axes([0.31, 0.04, 0.67, 0.92])
    ax.set_facecolor("#11181B")
    continent_col = "CONTINENT" if "CONTINENT" in world.columns else None
    if continent_col:
        world = world[world[continent_col] != "Antarctica"]
    world.plot(ax=ax, facecolor="#263239", edgecolor="#4B5A61", linewidth=0.45)
    ax.set_xlim(-170, 155)
    ax.set_ylim(-50, 72)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    for row in overview.itertuples(index=False):
        short = EVENT_META[row.event]["short"]
        color = EVENT_COLORS[short]
        marker = EVENT_MARKERS[short]
        ax.scatter(row.longitude, row.latitude, s=76, marker=marker, color=color, edgecolor="#EEF3F5", linewidth=1.0, zorder=4)

    fig.savefig(output_path, dpi=200, facecolor="#11181B", bbox_inches=None, pad_inches=0)
    plt.close(fig)


def padded_event_bounds(frame: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = frame.total_bounds
    span_x = max(max_x - min_x, 0.025)
    span_y = max(max_y - min_y, 0.025)
    pad_x = max(span_x * 0.13, 0.018)
    pad_y = max(span_y * 0.16, 0.018)
    min_x, min_y, max_x, max_y = min_x - pad_x, min_y - pad_y, max_x + pad_x, max_y + pad_y
    span_x = max_x - min_x
    span_y = max_y - min_y
    latitude = (min_y + max_y) / 2
    geographic_aspect = 1 / max(np.cos(np.deg2rad(latitude)), 0.35)
    target_display_ratio = 8.6 / 5.2
    current_display_ratio = span_x / (geographic_aspect * span_y)
    if current_display_ratio < target_display_ratio:
        required_x = target_display_ratio * geographic_aspect * span_y
        extra = (required_x - span_x) / 2
        min_x -= extra
        max_x += extra
    else:
        required_y = span_x / (target_display_ratio * geographic_aspect)
        extra = (required_y - span_y) / 2
        min_y -= extra
        max_y += extra
    return min_x, min_y, max_x, max_y


def add_map_scale_and_north(
    ax: plt.Axes,
    bounds: tuple[float, float, float, float],
    latitude: float,
) -> None:
    min_x, min_y, max_x, max_y = bounds
    span_x = max_x - min_x
    span_y = max_y - min_y
    kilometres_per_degree = max(111.32 * np.cos(np.deg2rad(latitude)), 25.0)
    target_km = span_x * kilometres_per_degree * 0.18
    choices = np.array([1, 2, 5, 10, 20, 50, 100, 200], dtype=float)
    valid = choices[choices <= target_km]
    scale_km = float(valid[-1] if len(valid) else choices[0])
    scale_degrees = scale_km / kilometres_per_degree
    x0 = min_x + span_x * 0.055
    y0 = min_y + span_y * 0.07
    ax.plot([x0, x0 + scale_degrees], [y0, y0], color="#F4F7F8", linewidth=2.2, zorder=10)
    ax.plot([x0, x0], [y0 - span_y * 0.008, y0 + span_y * 0.008], color="#F4F7F8", linewidth=1.0, zorder=10)
    ax.plot(
        [x0 + scale_degrees, x0 + scale_degrees],
        [y0 - span_y * 0.008, y0 + span_y * 0.008],
        color="#F4F7F8",
        linewidth=1.0,
        zorder=10,
    )
    ax.text(
        x0 + scale_degrees / 2,
        y0 + span_y * 0.018,
        f"{scale_km:g} km",
        color="#F4F7F8",
        fontsize=7.0,
        ha="center",
        va="bottom",
        zorder=10,
    )
    ax.annotate(
        "N",
        xy=(max_x - span_x * 0.06, max_y - span_y * 0.06),
        xytext=(max_x - span_x * 0.06, max_y - span_y * 0.17),
        color="#F4F7F8",
        fontsize=8.0,
        fontweight="bold",
        ha="center",
        va="center",
        arrowprops={"arrowstyle": "-|>", "color": "#F4F7F8", "linewidth": 1.2},
        zorder=10,
    )


def make_site_event_assets(
    world: gpd.GeoDataFrame,
    event_grid: gpd.GeoDataFrame,
    candidates: gpd.GeoDataFrame,
    overview: pd.DataFrame,
    asset_dir: Path,
) -> list[Path]:
    """Render a distinct, data-bearing local map for every event tab."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    dark_cmap = LinearSegmentedColormap.from_list(
        "event_damage_dark",
        ["#203036", "#3A4C53", "#74515A", "#D45C70"],
    )
    continent_col = "CONTINENT" if "CONTINENT" in world.columns else None
    base_world = world[world[continent_col] != "Antarctica"].copy() if continent_col else world.copy()

    for row in overview.itertuples(index=False):
        frame = event_grid[event_grid["event"] == row.event].copy()
        if frame.empty:
            raise RuntimeError(f"No 500 m analysis cells available for {row.event}")
        bounds = padded_event_bounds(frame)
        crop = box(*bounds)
        local_world = base_world[base_world.geometry.intersects(crop)]
        event_candidates = candidates[candidates["event"] == row.event]

        fig, ax = plt.subplots(figsize=(8.6, 5.2), facecolor="#11181B")
        ax.set_facecolor("#11181B")
        if not local_world.empty:
            local_world.plot(ax=ax, facecolor="#243138", edgecolor="#53636A", linewidth=0.8, zorder=0)

        values = frame["damage_index_D"].fillna(0).astype(float)
        upper = max(float(values.quantile(0.96)), 0.05)
        frame.plot(
            ax=ax,
            column="damage_index_D",
            cmap=dark_cmap,
            norm=Normalize(vmin=0, vmax=upper),
            edgecolor="#6E8189",
            linewidth=0.30,
            alpha=0.96,
            zorder=3,
        )
        if not event_candidates.empty:
            event_candidates.boundary.plot(ax=ax, color="#F5B942", linewidth=2.0, zorder=7)

        short = EVENT_META[row.event]["short"]
        ax.scatter(
            [row.longitude],
            [row.latitude],
            marker=EVENT_MARKERS[short],
            s=92,
            facecolor=EVENT_COLORS[short],
            edgecolor="#F4F7F8",
            linewidth=1.2,
            zorder=8,
        )
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_aspect(1 / max(np.cos(np.deg2rad(row.latitude)), 0.35), adjustable="box")
        ax.axis("off")
        add_map_scale_and_north(ax, bounds, float(row.latitude))
        fig.subplots_adjust(left=0.012, right=0.988, top=0.988, bottom=0.012)
        output = asset_dir / f"event_{row.event}.png"
        fig.savefig(output, dpi=180, facecolor="#11181B", bbox_inches=fig.bbox_inches, pad_inches=0)
        plt.close(fig)
        outputs.append(output)
    return outputs


def make_site_scale_assets(
    focus: gpd.GeoDataFrame,
    scale_grids: dict[int, gpd.GeoDataFrame],
    buildings: gpd.GeoDataFrame,
    bounds: tuple[float, float, float, float],
    asset_dir: Path,
) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    for scale in (250, 500, 1000):
        fig, ax = plt.subplots(figsize=(8.6, 5.2), facecolor="#11181B")
        plot_scale_map(ax, scale_grids[scale], buildings, focus, bounds, scale, dark=True)
        fig.subplots_adjust(left=0.015, right=0.985, top=0.985, bottom=0.015)
        fig.savefig(
            asset_dir / f"scale_mexico_{scale}m.png",
            dpi=180,
            facecolor="#11181B",
            bbox_inches="tight",
            pad_inches=0.03,
        )
        plt.close(fig)


def copy_site_assets(asset_dir: Path, overview_png: Path) -> list[Path]:
    """Copy stable brand and result assets into the standalone website."""
    asset_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "team_logo.png": PROJECT_ROOT / "reports" / "assets" / "team_logo.png",
        "github_icon.png": PROJECT_ROOT / "reports" / "assets" / "github_icon.png",
        "huggingface_icon.png": PROJECT_ROOT / "reports" / "assets" / "huggingface_icon.png",
        f"{OVERVIEW_BASENAME}.png": overview_png,
        "fig9_multiscale_robustness.png": PROJECT_ROOT / "reports" / "figures" / "fig9_multiscale_robustness.png",
        "fig11_consensus_audit.png": PROJECT_ROOT / "reports" / "figures" / "fig11_consensus_audit.png",
        "fig12_external_proxy_divergence.png": PROJECT_ROOT / "reports" / "figures" / "fig12_external_proxy_divergence.png",
    }
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in sources.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing website assets: " + ", ".join(missing))
    outputs = []
    for destination_name, source in sources.items():
        destination = asset_dir / destination_name
        shutil.copy2(source, destination)
        outputs.append(destination)
    return outputs


def copy_site_documents(site_dir: Path) -> list[Path]:
    """Copy the two reviewer-facing reports into the GitHub Pages artifact."""
    download_dir = site_dir / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "paper_en.pdf": PROJECT_ROOT / "reports" / "pdf" / "paper_en.pdf",
        "competition_report_cn.pdf": PROJECT_ROOT / "reports" / "pdf" / "competition_report_cn.pdf",
    }
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in sources.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing website report downloads: " + ", ".join(missing))
    outputs = []
    for destination_name, source in sources.items():
        destination = download_dir / destination_name
        shutil.copy2(source, destination)
        outputs.append(destination)
    return outputs


def write_site_data(overview: pd.DataFrame, focus: gpd.GeoDataFrame, site_dir: Path) -> Path:
    data_dir = site_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    candidate = focus.iloc[0]
    events = []
    for row in overview.itertuples(index=False):
        events.append(
            {
                "id": row.event,
                "name": row.name,
                "short_name": row.short_name,
                "hazard": row.hazard,
                "longitude": round(float(row.longitude), 6),
                "latitude": round(float(row.latitude), 6),
                "buildings": int(row.buildings),
                "cells": int(row.cells),
                "percentile_disagreement": int(row.percentile_disagreement),
                "exact_top20_disagreement": int(row.exact_top20_disagreement),
                "robust_non_temporal": int(row.robust_non_temporal),
                "temporal_support": int(row.temporal_support),
                "historical_osm_evidence": str(row.historical_osm_evidence),
                "map_image": f"assets/event_{row.event}.png",
            }
        )
    payload = {
        "study": {
            "events": 4,
            "buildings": int(overview["buildings"].sum()),
            "cells": int(overview["cells"].sum()),
            "percentile_disagreements": int(overview["percentile_disagreement"].sum()),
            "exact_top20_disagreements": int(overview["exact_top20_disagreement"].sum()),
            "robust_non_temporal": int(overview["robust_non_temporal"].sum()),
            "temporal_support": int(overview["temporal_support"].sum()),
        },
        "events": events,
        "focus_candidate": {
            "cell_id": str(candidate["cell_id"]),
            "event": str(candidate["event"]),
            "policy_probability_100m": round(float(candidate["policy_probability_100m"]), 4),
            "policy_probability_1km": round(float(candidate["policy_probability_1km"]), 4),
            "scale_support": {
                str(scale): bool(candidate[column]) for scale, column in SCALE_SUPPORT_COLUMNS.items()
            },
        },
        "claim_boundary": "This audit compares rankings. It does not estimate true unmet need or prescribe dispatch.",
    }
    output = data_dir / "study.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def write_manifest(
    paths: dict[str, Path],
    overview: pd.DataFrame,
    focus: gpd.GeoDataFrame,
    derived_dir: Path,
    figure_outputs: dict[str, Path],
    site_outputs: list[Path],
) -> None:
    derived_dir.mkdir(parents=True, exist_ok=True)
    event_path = derived_dir / "event_overview.csv"
    overview.to_csv(event_path, index=False)
    focus_path = derived_dir / "scale_focus_candidate.csv"
    focus.drop(columns="geometry").to_csv(focus_path, index=False)

    outputs = [event_path, focus_path, *figure_outputs.values(), *site_outputs]
    manifest = {
        "artifact": OVERVIEW_BASENAME,
        "focus_cell_id": FOCUS_CELL_ID,
        "scope": "Four selected xBD event footprints; not global coverage.",
        "claim_boundary": "Ranking-disagreement audit; not an estimator of true unmet need.",
        "sources": {
            name: {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(path),
            }
            for name, path in paths.items()
        },
        "outputs": {
            str(path.relative_to(PROJECT_ROOT)): {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in outputs
            if path.exists()
        },
        "natural_earth": {
            "license": "Public domain",
            "source": "https://www.naturalearthdata.com/",
        },
    }
    manifest_path = derived_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generate_all(output_dir: Path, derived_dir: Path, site_dir: Path) -> dict[str, object]:
    """Generate publication, website, compact-data, and manifest artifacts."""
    paths = input_paths()
    require_inputs(paths)
    overview = load_event_overview(paths)
    focus, scale_grids, buildings, bounds = load_focus_data(paths)
    world = gpd.read_file(paths["world"]).to_crs(4326)
    event_grid = gpd.read_file(paths["primary_grid"]).to_crs(4326)
    candidates = gpd.read_file(paths["candidates"]).to_crs(4326)

    figure_outputs = make_publication_overview(
        world,
        overview,
        focus,
        scale_grids,
        buildings,
        bounds,
        output_dir,
    )
    asset_dir = site_dir / "assets"
    hero_path = asset_dir / "hero_world.png"
    make_site_hero(world, overview, hero_path)
    event_map_paths = make_site_event_assets(world, event_grid, candidates, overview, asset_dir)
    make_site_scale_assets(focus, scale_grids, buildings, bounds, asset_dir)
    copied_site_assets = copy_site_assets(asset_dir, figure_outputs["png"])
    copied_site_documents = copy_site_documents(site_dir)
    site_data_path = write_site_data(overview, focus, site_dir)
    site_outputs = [
        hero_path,
        *event_map_paths,
        asset_dir / "scale_mexico_250m.png",
        asset_dir / "scale_mexico_500m.png",
        asset_dir / "scale_mexico_1000m.png",
        site_data_path,
        *copied_site_assets,
        *copied_site_documents,
    ]
    write_manifest(paths, overview, focus, derived_dir, figure_outputs, site_outputs)

    return {
        "overview": overview,
        "figure_outputs": figure_outputs,
        "hero_path": hero_path,
        "site_outputs": site_outputs,
    }


def main() -> None:
    args = parse_args()
    generated = generate_all(args.output_dir, args.derived_dir, args.site_dir)
    overview = generated["overview"]
    figure_outputs = generated["figure_outputs"]
    hero_path = generated["hero_path"]

    print(f"event_cells={int(overview['cells'].sum())}")
    print(f"buildings={int(overview['buildings'].sum())}")
    print(f"percentile_disagreements={int(overview['percentile_disagreement'].sum())}")
    print(f"exact_top20_disagreements={int(overview['exact_top20_disagreement'].sum())}")
    print(f"robust_non_temporal={int(overview['robust_non_temporal'].sum())}")
    print(f"temporal_support={int(overview['temporal_support'].sum())}")
    print(f"publication_figure={figure_outputs['png']}")
    print(f"site_hero={hero_path}")


if __name__ == "__main__":
    main()
