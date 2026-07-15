#!/usr/bin/env python3
"""Fetch OSM building footprints as an independent urban-form robustness layer."""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr
from shapely.geometry import box

from figure_style import (
    CMAP_DIVERGING,
    INK,
    add_panel_label,
    apply_publication_style,
    color_for_event,
    mm_to_inches,
    save_publication_figure,
    style_numeric_axis,
)


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"


EVENT_OSM_DATES = {
    "hurricane-harvey": "2017-08-31",
    "mexico-earthquake": "2017-09-20",
    "palu-tsunami": "2018-09-29",
    "santa-rosa-wildfire": "2017-10-11",
}
EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}
BUILDING_TAGS = {"building": True}


def estimate_utm_epsg(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def set_osmnx_settings(out_dir: Path, date_mode: str, event: str, timeout: int) -> str:
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(out_dir / "osmnx_cache")
    ox.settings.requests_timeout = timeout
    ox.settings.overpass_rate_limit = True
    ox.settings.log_console = False
    ox.settings.overpass_settings = "[out:json][timeout:{timeout}]{maxsize}"
    if date_mode == "historical":
        event_date = EVENT_OSM_DATES[event]
        ox.settings.overpass_settings = f'[out:json][timeout:{{timeout}}][date:"{event_date}T00:00:00Z"]{{maxsize}}'
        return event_date
    return "current"


def buffered_event_polygon(footprint_row: pd.Series, buffer_deg: float) -> box:
    return box(
        float(footprint_row["min_lon"]) - buffer_deg,
        float(footprint_row["min_lat"]) - buffer_deg,
        float(footprint_row["max_lon"]) + buffer_deg,
        float(footprint_row["max_lat"]) + buffer_deg,
    )


def fetch_buildings(polygon, event: str, args: argparse.Namespace, out_dir: Path) -> tuple[gpd.GeoDataFrame, dict]:
    snapshot = set_osmnx_settings(out_dir, args.date_mode, event, args.timeout)
    log = {
        "event": event,
        "date_mode": args.date_mode,
        "osm_snapshot": snapshot,
        "buffer_deg": args.buffer_deg,
        "status": "not_run",
        "raw_features": 0,
        "polygon_features": 0,
        "error": "",
    }
    try:
        features = ox.features_from_polygon(polygon, tags=BUILDING_TAGS)
        log["raw_features"] = int(len(features))
        if features.empty:
            log["status"] = "empty"
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log
        keep = [col for col in ["building", "name", "geometry"] if col in features.columns]
        buildings = features[keep].copy()
        buildings = buildings[buildings.geometry.notna() & ~buildings.geometry.is_empty].copy()
        buildings = buildings[buildings.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        buildings = gpd.GeoDataFrame(buildings, geometry="geometry", crs="EPSG:4326")
        log["polygon_features"] = int(len(buildings))
        log["status"] = "ok"
        return buildings, log
    except Exception:
        log["status"] = "error"
        log["error"] = traceback.format_exc(limit=2).replace("\n", " ")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log


def building_metrics(event_grid: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, utm_epsg: int, cell_m: int) -> pd.DataFrame:
    metrics = pd.DataFrame({"cell_id": event_grid["cell_id"].to_numpy()})
    metrics["osm_building_count"] = 0
    metrics["osm_building_area_m2"] = 0.0
    if buildings.empty:
        metrics["osm_building_density_per_km2"] = 0.0
        metrics["osm_building_area_fraction"] = 0.0
        return metrics

    grid_proj = event_grid[["cell_id", "geometry"]].to_crs(epsg=utm_epsg).reset_index(drop=True)
    grid_proj["grid_idx"] = grid_proj.index
    buildings_proj = buildings[["geometry"]].to_crs(epsg=utm_epsg).reset_index(drop=True)
    buildings_proj = buildings_proj[buildings_proj.geometry.notna() & ~buildings_proj.geometry.is_empty].copy()
    buildings_proj["building_idx"] = buildings_proj.index
    buildings_proj["point_geometry"] = buildings_proj.geometry.representative_point()

    points = gpd.GeoDataFrame(
        buildings_proj[["building_idx"]],
        geometry=buildings_proj["point_geometry"],
        crs=buildings_proj.crs,
    )
    count_join = gpd.sjoin(points, grid_proj[["grid_idx", "cell_id", "geometry"]], how="inner", predicate="within")
    if not count_join.empty:
        counts = count_join.groupby("cell_id").size().rename("osm_building_count")
        metrics = metrics.drop(columns=["osm_building_count"]).merge(counts, on="cell_id", how="left")
        metrics["osm_building_count"] = metrics["osm_building_count"].fillna(0).astype(int)

    candidates = gpd.sjoin(
        buildings_proj[["building_idx", "geometry"]],
        grid_proj[["grid_idx", "cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    if not candidates.empty:
        grid_geometries = grid_proj.set_index("grid_idx")["geometry"]
        areas = []
        for row in candidates[["geometry", "grid_idx"]].itertuples(index=False):
            areas.append(row.geometry.intersection(grid_geometries.loc[row.grid_idx]).area)
        candidates = candidates.copy()
        candidates["building_area_m2"] = areas
        area_by_cell = candidates.groupby("cell_id")["building_area_m2"].sum().rename("osm_building_area_m2")
        metrics = metrics.drop(columns=["osm_building_area_m2"]).merge(area_by_cell, on="cell_id", how="left")
        metrics["osm_building_area_m2"] = metrics["osm_building_area_m2"].fillna(0.0)

    cell_area_km2 = (cell_m * cell_m) / 1_000_000.0
    cell_area_m2 = cell_m * cell_m
    metrics["osm_building_density_per_km2"] = metrics["osm_building_count"] / cell_area_km2
    metrics["osm_building_area_fraction"] = metrics["osm_building_area_m2"] / cell_area_m2
    return metrics


def standardized_difference(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if pooled == 0 or np.isnan(pooled):
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def build_profiles(joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows = []
    profile_rows = []
    correlation_rows = []
    variables = [
        ("osm_building_area_fraction", "OSM building area fraction"),
        ("osm_building_density_per_km2", "OSM building density"),
        ("osm_building_area_m2", "OSM building area"),
        ("total_area_m2", "xBD mapped building area"),
        ("building_count", "xBD building count"),
    ]
    groups = [("all_events", joined)] + sorted(joined.groupby("event"), key=lambda item: item[0])
    for group_name, group_df in groups:
        stable = group_df[group_df["stable_mismatch"].astype(bool)]
        other = group_df[~group_df["stable_mismatch"].astype(bool)]
        summary_rows.append(
            {
                "group": group_name,
                "cells": int(len(group_df)),
                "stable_mismatch_count": int(len(stable)),
                "stable_mismatch_share": float(len(stable) / len(group_df)) if len(group_df) else np.nan,
                "stable_osm_building_area_fraction_mean": float(stable["osm_building_area_fraction"].mean()) if len(stable) else np.nan,
                "other_osm_building_area_fraction_mean": float(other["osm_building_area_fraction"].mean()) if len(other) else np.nan,
                "stable_osm_building_density_mean": float(stable["osm_building_density_per_km2"].mean()) if len(stable) else np.nan,
                "other_osm_building_density_mean": float(other["osm_building_density_per_km2"].mean()) if len(other) else np.nan,
            }
        )
        for column, label in variables:
            profile_rows.append(
                {
                    "group": group_name,
                    "variable": column,
                    "label": label,
                    "stable_n": int(stable[column].notna().sum()) if len(stable) else 0,
                    "other_n": int(other[column].notna().sum()) if len(other) else 0,
                    "stable_mean": float(stable[column].mean()) if len(stable) else np.nan,
                    "other_mean": float(other[column].mean()) if len(other) else np.nan,
                    "standardized_mean_difference": standardized_difference(stable[column], other[column]),
                }
            )
        valid = group_df[["osm_building_area_fraction", "total_area_m2"]].replace([np.inf, -np.inf], np.nan).dropna()
        rho, p_value = (np.nan, np.nan)
        if len(valid) >= 3 and valid["osm_building_area_fraction"].nunique() > 1 and valid["total_area_m2"].nunique() > 1:
            rho, p_value = spearmanr(valid["osm_building_area_fraction"], valid["total_area_m2"])
        correlation_rows.append(
            {
                "group": group_name,
                "n": int(len(valid)),
                "spearman_osm_area_fraction_vs_xbd_area": float(rho) if not np.isnan(rho) else np.nan,
                "spearman_p_value": float(p_value) if not np.isnan(p_value) else np.nan,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(profile_rows), pd.DataFrame(correlation_rows)


def make_figure(profile: pd.DataFrame, correlations: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="white", context="paper")
    apply_publication_style()
    data = profile[
        profile["group"].isin(["all_events", "hurricane-harvey", "santa-rosa-wildfire"])
        & profile["variable"].isin(["osm_building_area_fraction", "osm_building_density_per_km2", "total_area_m2"])
    ].copy()
    data["group_label"] = data["group"].replace(
        {
            "all_events": "All",
            "hurricane-harvey": "Harvey",
            "santa-rosa-wildfire": "Santa Rosa",
        }
    )
    matrix = data.pivot(index="label", columns="group_label", values="standardized_mean_difference").reindex(
        ["OSM building area fraction", "OSM building density", "xBD mapped building area"]
    )[["All", "Harvey", "Santa Rosa"]]

    corr = correlations[correlations["group"] != "all_events"].copy()
    corr["event_label"] = corr["group"].map(EVENT_LABELS)
    corr = corr.set_index("event_label").reindex(["Harvey", "Mexico EQ", "Palu", "Santa Rosa"]).reset_index()

    max_abs = max(1.0, float(matrix.abs().max().max()))
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(80)),
        constrained_layout=True,
    )
    sns.heatmap(
        matrix,
        ax=axes[0],
        cmap=CMAP_DIVERGING,
        center=0,
        vmin=-max_abs,
        vmax=max_abs,
        annot=True,
        fmt=".2f",
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "Standardized mean difference\n(disagreement - other)", "shrink": 0.82},
    )
    axes[0].set_title("Independent building-form profile", loc="left", pad=7)
    add_panel_label(axes[0], "a", x=-0.17, y=1.04)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")
    axes[0].tick_params(axis="x", rotation=0)
    for text, value in zip(axes[0].texts, matrix.to_numpy().ravel()):
        text.set_color("white" if abs(float(value)) >= 0.58 * max_abs else INK)
        text.set_fontsize(6.8)

    values = corr["spearman_osm_area_fraction_vs_xbd_area"].to_numpy()
    y = np.arange(len(corr))
    axes[1].hlines(y, 0, values, color="#D6DCE1", linewidth=1.5, zorder=1)
    axes[1].scatter(
        values,
        y,
        s=34,
        color=[color_for_event(label) for label in corr["event_label"]],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    for idx, row in corr.iterrows():
        value = float(row["spearman_osm_area_fraction_vs_xbd_area"])
        axes[1].text(value + 0.035, idx, f"{value:.2f}  n={int(row['n']):,}", va="center", fontsize=6.2)
    axes[1].set_yticks(y, corr["event_label"])
    axes[1].invert_yaxis()
    axes[1].axvline(0, color="#777777", linewidth=0.8)
    axes[1].set_xlim(-1, 1)
    axes[1].set_xlabel("Spearman rho")
    axes[1].set_ylabel("")
    axes[1].set_title("OSM vs xBD mapped area", loc="left", pad=7)
    add_panel_label(axes[1], "b", x=-0.18, y=1.04)
    style_numeric_axis(axes[1], axis="x")

    save_publication_figure(fig, out_dir, "fig7_osm_building_form_robustness")


def write_manifest(out_dir: Path, args: argparse.Namespace, fetch_logs: list[dict]) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/17_fetch_osm_building_form.py",
        "input_grid": str(args.input_grid),
        "event_footprints": str(args.footprints_csv),
        "date_mode": args.date_mode,
        "buffer_deg": args.buffer_deg,
        "cell_m": args.cell_m,
        "reused_building_grid": str(args.reuse_building_grid) if args.reuse_building_grid else None,
        "building_tags": BUILDING_TAGS,
        "interpretation": "Independent urban-form robustness layer from OSM building footprints. The primary priority mismatch score is unchanged.",
        "outputs": [
            "osm_building_grid_features_500m.csv",
            "priority_mismatch_with_osm_buildings_500m.csv",
            "priority_mismatch_with_osm_buildings_500m.geojson",
            "osm_building_urban_form_event_summary.csv",
            "osm_building_urban_form_profile.csv",
            "osm_building_xbd_area_correlation.csv",
            "osm_building_fetch_log.csv",
        ],
        "known_limitations": [
            "Current OSM buildings may include post-disaster edits and uneven mapper coverage.",
            "OSM building footprints are used only as a robustness layer, not as a replacement for xBD damage labels.",
            "Building counts use representative points inside cells; building areas use polygon-grid intersections.",
        ],
        "fetch_logs": fetch_logs,
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grid", required=True, type=Path)
    parser.add_argument("--footprints-csv", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--figure-dir", required=True, type=Path)
    parser.add_argument("--date-mode", choices=["current", "historical"], default="current")
    parser.add_argument("--buffer-deg", type=float, default=0.002)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--cell-m", type=int, default=500)
    parser.add_argument(
        "--reuse-building-grid",
        type=Path,
        help="Reuse a previously audited osm_building_grid_features_<cell_m>m.csv.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    grid = gpd.read_file(args.input_grid)
    if "stable_mismatch" not in grid.columns:
        raise ValueError("Input grid must include stable_mismatch")
    footprints = pd.read_csv(args.footprints_csv).set_index("event")

    if args.reuse_building_grid:
        osm_metrics = pd.read_csv(args.reuse_building_grid)
        required_keys = set(zip(grid["event"].astype(str), grid["cell_id"].astype(str)))
        available_keys = set(
            zip(osm_metrics["event"].astype(str), osm_metrics["cell_id"].astype(str))
        )
        if required_keys != available_keys:
            raise ValueError("Reusable OSM building grid does not match the priority grid cells")
        source_log = args.reuse_building_grid.parent / "osm_building_fetch_log.csv"
        fetch_logs = pd.read_csv(source_log).to_dict(orient="records") if source_log.exists() else []
        print(f"reused_building_grid={args.reuse_building_grid}")
    else:
        all_metrics = []
        fetch_logs = []
        for event in sorted(grid["event"].unique()):
            event_grid = grid[grid["event"] == event].copy()
            if event not in footprints.index:
                raise ValueError(f"Missing event footprint for {event}")
            event_center_lon = float(event_grid["cell_center_lon"].mean())
            event_center_lat = float(event_grid["cell_center_lat"].mean())
            utm_epsg = estimate_utm_epsg(event_center_lon, event_center_lat)
            polygon = buffered_event_polygon(footprints.loc[event], args.buffer_deg)
            buildings, fetch_log = fetch_buildings(polygon, event, args, args.out_dir)
            metrics = building_metrics(event_grid, buildings, utm_epsg, args.cell_m)
            metrics.insert(0, "event", event)
            all_metrics.append(metrics)
            fetch_log["utm_epsg"] = utm_epsg
            fetch_logs.append(fetch_log)
            print(
                event,
                f"status={fetch_log['status']}",
                f"raw={fetch_log['raw_features']}",
                f"polygons={fetch_log['polygon_features']}",
            )
        osm_metrics = pd.concat(all_metrics, ignore_index=True)
    osm_metrics.to_csv(args.out_dir / f"osm_building_grid_features_{args.cell_m}m.csv", index=False)

    joined = grid.merge(osm_metrics.drop(columns=["event"]), on="cell_id", how="left")
    joined.drop(columns="geometry").to_csv(args.out_dir / f"priority_mismatch_with_osm_buildings_{args.cell_m}m.csv", index=False)
    joined.to_file(args.out_dir / f"priority_mismatch_with_osm_buildings_{args.cell_m}m.geojson", driver="GeoJSON")

    summary, profile, correlations = build_profiles(pd.DataFrame(joined.drop(columns="geometry")))
    summary.to_csv(args.out_dir / "osm_building_urban_form_event_summary.csv", index=False)
    profile.to_csv(args.out_dir / "osm_building_urban_form_profile.csv", index=False)
    correlations.to_csv(args.out_dir / "osm_building_xbd_area_correlation.csv", index=False)
    pd.DataFrame(fetch_logs).to_csv(args.out_dir / "osm_building_fetch_log.csv", index=False)
    make_figure(profile, correlations, args.figure_dir)
    write_manifest(args.out_dir, args, fetch_logs)

    print(f"features={args.out_dir / f'osm_building_grid_features_{args.cell_m}m.csv'}")
    print(f"summary={args.out_dir / 'osm_building_urban_form_event_summary.csv'}")
    print(f"profile={args.out_dir / 'osm_building_urban_form_profile.csv'}")
    print(f"figure={args.figure_dir / 'fig7_osm_building_form_robustness.png'}")


if __name__ == "__main__":
    main()
