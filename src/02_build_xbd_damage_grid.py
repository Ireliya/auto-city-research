#!/usr/bin/env python3
"""Aggregate xBD building damage into event-level metric grids.

The first reproducible damage layer uses building centroids to assign each
post-disaster xBD building to a metric grid. This keeps the baseline simple
and auditable before auxiliary need variables are added.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box


DAMAGED_SUBTYPES = {"minor-damage", "major-damage", "destroyed"}
SEVERE_SUBTYPES = {"major-damage", "destroyed"}
DAMAGE_SUBTYPES = ["no-damage", "minor-damage", "major-damage", "destroyed", "un-classified"]


def parse_cell_sizes(raw: str) -> list[int]:
    sizes = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        size = int(item)
        if size <= 0:
            raise ValueError(f"Cell size must be positive: {size}")
        sizes.append(size)
    if not sizes:
        raise ValueError("At least one cell size is required")
    return sizes


def estimate_utm_epsg(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def read_buildings(path: Path, events: set[str] | None) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    if events is not None:
        df = df[df["event"].isin(events)].copy()

    numeric_cols = [
        "damage_score",
        "lon_centroid",
        "lat_centroid",
        "lnglat_min_lon",
        "lnglat_min_lat",
        "lnglat_max_lon",
        "lnglat_max_lat",
        "area_m2_approx",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["valid_coordinate"] = (
        df["lon_centroid"].between(-180, 180)
        & df["lat_centroid"].between(-90, 90)
        & df["lon_centroid"].notna()
        & df["lat_centroid"].notna()
    )
    df["valid_area"] = df["area_m2_approx"].fillna(0) > 0
    df["classified"] = df["damage_score"].notna()
    df["damaged"] = df["damage_subtype"].isin(DAMAGED_SUBTYPES)
    df["severe_damage"] = df["damage_subtype"].isin(SEVERE_SUBTYPES)
    df["usable_for_grid"] = df["valid_coordinate"] & df["valid_area"]
    df["classified_area_m2"] = np.where(
        df["classified"] & df["valid_area"],
        df["area_m2_approx"],
        0.0,
    )
    df["damage_weighted_area_m2"] = np.where(
        df["classified"] & df["valid_area"],
        df["area_m2_approx"] * df["damage_score"].fillna(0.0),
        0.0,
    )
    return df


def percentile(values: pd.Series, q: float) -> float:
    valid = values.dropna()
    if valid.empty:
        return float("nan")
    return float(valid.quantile(q))


def build_geometry_qa(df: pd.DataFrame, cell_counts: dict[tuple[str, int], int]) -> pd.DataFrame:
    rows = []
    for event, event_df in sorted(df.groupby("event")):
        valid = event_df[event_df["valid_coordinate"]]
        usable = event_df[event_df["usable_for_grid"]]
        bbox_valid = (
            event_df["lnglat_min_lon"].notna()
            & event_df["lnglat_min_lat"].notna()
            & event_df["lnglat_max_lon"].notna()
            & event_df["lnglat_max_lat"].notna()
            & (event_df["lnglat_min_lon"] <= event_df["lnglat_max_lon"])
            & (event_df["lnglat_min_lat"] <= event_df["lnglat_max_lat"])
        )
        if valid.empty:
            lon_mean = float("nan")
            lat_mean = float("nan")
            utm_epsg = None
        else:
            lon_mean = float(valid["lon_centroid"].mean())
            lat_mean = float(valid["lat_centroid"].mean())
            utm_epsg = estimate_utm_epsg(lon_mean, lat_mean)

        row = {
            "event": event,
            "rows_total": int(len(event_df)),
            "valid_coordinate_count": int(event_df["valid_coordinate"].sum()),
            "invalid_coordinate_count": int((~event_df["valid_coordinate"]).sum()),
            "valid_area_count": int(event_df["valid_area"].sum()),
            "nonpositive_or_missing_area_count": int((~event_df["valid_area"]).sum()),
            "bbox_valid_count": int(bbox_valid.sum()),
            "bbox_invalid_count": int((~bbox_valid).sum()),
            "usable_for_grid_count": int(event_df["usable_for_grid"].sum()),
            "classified_count": int(event_df["classified"].sum()),
            "unclassified_count": int((~event_df["classified"]).sum()),
            "lon_min": float(valid["lon_centroid"].min()) if not valid.empty else float("nan"),
            "lat_min": float(valid["lat_centroid"].min()) if not valid.empty else float("nan"),
            "lon_max": float(valid["lon_centroid"].max()) if not valid.empty else float("nan"),
            "lat_max": float(valid["lat_centroid"].max()) if not valid.empty else float("nan"),
            "lon_mean": lon_mean,
            "lat_mean": lat_mean,
            "estimated_utm_epsg": utm_epsg,
            "area_m2_p50": percentile(usable["area_m2_approx"], 0.50),
            "area_m2_p95": percentile(usable["area_m2_approx"], 0.95),
            "area_m2_p99": percentile(usable["area_m2_approx"], 0.99),
            "area_m2_max": float(usable["area_m2_approx"].max()) if not usable.empty else float("nan"),
        }
        for (cell_event, cell_m), count in sorted(cell_counts.items()):
            if cell_event == event:
                row[f"grid_cells_{cell_m}m"] = int(count)
        rows.append(row)
    return pd.DataFrame(rows)


def build_event_footprints(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    rows = []
    geometries = []
    for event, event_df in sorted(df[df["valid_coordinate"]].groupby("event")):
        min_lon = float(event_df["lon_centroid"].min())
        min_lat = float(event_df["lat_centroid"].min())
        max_lon = float(event_df["lon_centroid"].max())
        max_lat = float(event_df["lat_centroid"].max())
        rows.append(
            {
                "event": event,
                "building_count": int(len(event_df)),
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }
        )
        geometries.append(box(min_lon, min_lat, max_lon, max_lat))

    footprint_gdf = gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4326")
    footprint_gdf.to_file(out_dir / "event_footprints.geojson", driver="GeoJSON")
    footprint_gdf.drop(columns="geometry").to_csv(out_dir / "event_footprints.csv", index=False)
    return footprint_gdf.drop(columns="geometry")


def aggregate_one_event(event_df: pd.DataFrame, cell_m: int) -> gpd.GeoDataFrame:
    event = str(event_df["event"].iloc[0])
    lon_mean = float(event_df["lon_centroid"].mean())
    lat_mean = float(event_df["lat_centroid"].mean())
    utm_epsg = estimate_utm_epsg(lon_mean, lat_mean)

    points = gpd.GeoDataFrame(
        event_df.copy(),
        geometry=gpd.points_from_xy(event_df["lon_centroid"], event_df["lat_centroid"]),
        crs="EPSG:4326",
    ).to_crs(epsg=utm_epsg)

    points["_x"] = points.geometry.x
    points["_y"] = points.geometry.y
    x0 = math.floor(points["_x"].min() / cell_m) * cell_m
    y0 = math.floor(points["_y"].min() / cell_m) * cell_m
    points["ix"] = np.floor((points["_x"] - x0) / cell_m).astype(int)
    points["iy"] = np.floor((points["_y"] - y0) / cell_m).astype(int)

    group_cols = ["ix", "iy"]
    grouped = points.groupby(group_cols, dropna=False)
    grid = grouped.agg(
        building_count=("building_uid", "count"),
        classified_building_count=("classified", "sum"),
        damaged_building_count=("damaged", "sum"),
        severe_building_count=("severe_damage", "sum"),
        total_area_m2=("area_m2_approx", "sum"),
        classified_area_m2=("classified_area_m2", "sum"),
        damage_weighted_area_m2=("damage_weighted_area_m2", "sum"),
        mean_damage_score=("damage_score", "mean"),
    ).reset_index()

    subtype_counts = (
        points.pivot_table(
            index=group_cols,
            columns="damage_subtype",
            values="building_uid",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for subtype in DAMAGE_SUBTYPES:
        if subtype not in subtype_counts.columns:
            subtype_counts[subtype] = 0
    subtype_counts = subtype_counts.rename(
        columns={subtype: f"count_{subtype.replace('-', '_')}" for subtype in DAMAGE_SUBTYPES}
    )
    grid = grid.merge(subtype_counts, on=group_cols, how="left")

    grid["event"] = event
    grid["cell_m"] = int(cell_m)
    grid["utm_epsg"] = int(utm_epsg)
    grid["grid_origin_x"] = float(x0)
    grid["grid_origin_y"] = float(y0)
    grid["x_min"] = x0 + grid["ix"] * cell_m
    grid["y_min"] = y0 + grid["iy"] * cell_m
    grid["x_max"] = grid["x_min"] + cell_m
    grid["y_max"] = grid["y_min"] + cell_m
    grid["x_center"] = grid["x_min"] + cell_m / 2.0
    grid["y_center"] = grid["y_min"] + cell_m / 2.0
    grid["cell_id"] = (
        grid["event"].astype(str)
        + "_"
        + grid["cell_m"].astype(str)
        + "m_"
        + grid["ix"].astype(str)
        + "_"
        + grid["iy"].astype(str)
    )

    grid["damage_index_D"] = np.where(
        grid["classified_area_m2"] > 0,
        grid["damage_weighted_area_m2"] / grid["classified_area_m2"],
        np.nan,
    )
    grid["damaged_building_share"] = np.where(
        grid["classified_building_count"] > 0,
        grid["damaged_building_count"] / grid["classified_building_count"],
        np.nan,
    )
    grid["severe_building_share"] = np.where(
        grid["classified_building_count"] > 0,
        grid["severe_building_count"] / grid["classified_building_count"],
        np.nan,
    )

    geometries = [
        box(row.x_min, row.y_min, row.x_max, row.y_max)
        for row in grid[["x_min", "y_min", "x_max", "y_max"]].itertuples(index=False)
    ]
    grid_gdf = gpd.GeoDataFrame(grid, geometry=geometries, crs=f"EPSG:{utm_epsg}")
    centers = gpd.GeoSeries(
        [Point(x, y) for x, y in zip(grid_gdf["x_center"], grid_gdf["y_center"])],
        crs=f"EPSG:{utm_epsg}",
    ).to_crs("EPSG:4326")
    grid_gdf["cell_center_lon"] = centers.x
    grid_gdf["cell_center_lat"] = centers.y
    return grid_gdf.to_crs("EPSG:4326")


def aggregate_grids(df: pd.DataFrame, out_dir: Path, cell_sizes: list[int]) -> dict[tuple[str, int], int]:
    usable = df[df["usable_for_grid"]].copy()
    cell_counts: dict[tuple[str, int], int] = {}
    for cell_m in cell_sizes:
        event_grids = []
        for event, event_df in sorted(usable.groupby("event")):
            if event_df.empty:
                continue
            event_grid = aggregate_one_event(event_df, cell_m)
            event_grids.append(event_grid)
            cell_counts[(event, cell_m)] = int(len(event_grid))

        if not event_grids:
            continue
        grid_gdf = pd.concat(event_grids, ignore_index=True)
        grid_gdf = gpd.GeoDataFrame(grid_gdf, geometry="geometry", crs="EPSG:4326")
        grid_gdf["damage_rank_desc"] = grid_gdf.groupby("event")["damage_index_D"].rank(
            method="min",
            ascending=False,
        )
        grid_gdf["damage_area_rank_desc"] = grid_gdf.groupby("event")["damage_weighted_area_m2"].rank(
            method="min",
            ascending=False,
        )
        grid_gdf.to_file(out_dir / f"damage_grid_{cell_m}m.geojson", driver="GeoJSON")
        csv_df = grid_gdf.drop(columns="geometry").copy()
        bounds = grid_gdf.bounds.rename(
            columns={"minx": "cell_min_lon", "miny": "cell_min_lat", "maxx": "cell_max_lon", "maxy": "cell_max_lat"}
        )
        csv_df = pd.concat([csv_df, bounds], axis=1)
        csv_df.to_csv(out_dir / f"damage_grid_{cell_m}m.csv", index=False)
    return cell_counts


def write_manifest(
    out_dir: Path,
    input_csv: Path,
    events: set[str] | None,
    cell_sizes: list[int],
    rows_total: int,
    rows_usable: int,
) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/02_build_xbd_damage_grid.py",
        "input_csv": str(input_csv),
        "events": sorted(events) if events is not None else "all",
        "cell_sizes_m": cell_sizes,
        "assignment_rule": "building centroid assigned to metric grid cell after event-level UTM projection",
        "damage_index_D": "sum(area_m2_approx * damage_score) / sum(classified area_m2_approx)",
        "damage_score_mapping": {
            "no-damage": 0.0,
            "minor-damage": 1.0 / 3.0,
            "major-damage": 2.0 / 3.0,
            "destroyed": 1.0,
            "un-classified": None,
        },
        "rows_total": int(rows_total),
        "rows_usable_for_grid": int(rows_usable),
        "known_limitations": [
            "Grid assignment uses building centroids, not polygon-grid intersections.",
            "Area is approximated from image-space polygon area and image GSD.",
            "Event footprint is a bounding box over building centroids, not a disaster-impact boundary.",
        ],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildings-csv", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--events", default="", help="Optional comma-separated event names")
    parser.add_argument("--cell-sizes", default="500", help="Comma-separated metric grid sizes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    events = {item.strip() for item in args.events.split(",") if item.strip()} or None
    cell_sizes = parse_cell_sizes(args.cell_sizes)

    buildings = read_buildings(args.buildings_csv, events)
    if buildings.empty:
        raise ValueError("No building rows available for the requested event filter")

    cell_counts = aggregate_grids(buildings, out_dir, cell_sizes)
    geometry_qa = build_geometry_qa(buildings, cell_counts)
    geometry_qa.to_csv(out_dir / "geometry_qa.csv", index=False)
    build_event_footprints(buildings, out_dir)
    write_manifest(
        out_dir=out_dir,
        input_csv=args.buildings_csv,
        events=events,
        cell_sizes=cell_sizes,
        rows_total=len(buildings),
        rows_usable=int(buildings["usable_for_grid"].sum()),
    )

    print(f"rows_total={len(buildings)}")
    print(f"rows_usable_for_grid={int(buildings['usable_for_grid'].sum())}")
    for cell_m in cell_sizes:
        print(f"damage_grid_{cell_m}m={out_dir / f'damage_grid_{cell_m}m.csv'}")
    print(f"geometry_qa={out_dir / 'geometry_qa.csv'}")
    print(f"manifest={out_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
