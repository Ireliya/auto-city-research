#!/usr/bin/env python3
"""Fetch OSM road/facility context and join it to the xBD damage grid."""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import box
from sklearn.neighbors import NearestNeighbors


EVENT_OSM_DATES = {
    "hurricane-harvey": "2017-08-31",
    "mexico-earthquake": "2017-09-20",
    "palu-tsunami": "2018-09-29",
    "santa-rosa-wildfire": "2017-10-11",
}

FACILITY_TAGS = {
    "amenity": [
        "hospital",
        "clinic",
        "doctors",
        "pharmacy",
        "school",
        "college",
        "university",
        "police",
        "fire_station",
        "social_facility",
        "community_centre",
        "shelter",
    ],
    "emergency": ["ambulance_station", "assembly_point"],
    "healthcare": True,
    "social_facility": True,
}

HEALTH_VALUES = {"hospital", "clinic", "doctors", "pharmacy", "ambulance_station"}
EDUCATION_VALUES = {"school", "college", "university"}
EMERGENCY_VALUES = {"police", "fire_station", "ambulance_station", "assembly_point"}
SOCIAL_VALUES = {"social_facility", "community_centre", "shelter"}


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


def facility_category(row: pd.Series) -> str:
    values = {
        str(row.get("amenity", "")) if pd.notna(row.get("amenity", "")) else "",
        str(row.get("emergency", "")) if pd.notna(row.get("emergency", "")) else "",
        str(row.get("healthcare", "")) if pd.notna(row.get("healthcare", "")) else "",
        str(row.get("social_facility", "")) if pd.notna(row.get("social_facility", "")) else "",
    }
    if values & HEALTH_VALUES or pd.notna(row.get("healthcare")):
        return "health"
    if values & EDUCATION_VALUES:
        return "education"
    if values & EMERGENCY_VALUES:
        return "emergency"
    if values & SOCIAL_VALUES or pd.notna(row.get("social_facility")):
        return "social"
    return "other"


def empty_event_metrics(event_grid: gpd.GeoDataFrame, event: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event": event,
            "cell_id": event_grid["cell_id"].to_numpy(),
            "road_length_m": 0.0,
            "road_density_m_per_km2": 0.0,
            "facility_count": 0,
            "facility_health_count": 0,
            "facility_education_count": 0,
            "facility_emergency_count": 0,
            "facility_social_count": 0,
            "nearest_facility_m": np.nan,
        }
    )


def road_metrics(event_grid: gpd.GeoDataFrame, polygon, network_type: str, utm_epsg: int) -> tuple[pd.Series, int, str]:
    graph = ox.graph_from_polygon(
        polygon,
        network_type=network_type,
        simplify=True,
        retain_all=True,
        truncate_by_edge=True,
    )
    if graph.number_of_edges() == 0:
        return pd.Series(dtype=float), 0, "empty"
    edges = ox.graph_to_gdfs(graph, nodes=False, edges=True, fill_edge_geometry=True)
    if edges.empty:
        return pd.Series(dtype=float), 0, "empty"

    grid_proj = event_grid[["cell_id", "geometry"]].to_crs(epsg=utm_epsg).reset_index(drop=True)
    grid_proj["grid_idx"] = grid_proj.index
    edges_proj = edges[["geometry"]].to_crs(epsg=utm_epsg).reset_index(drop=True)
    edges_proj["edge_idx"] = edges_proj.index
    edges_proj = edges_proj[~edges_proj.geometry.is_empty & edges_proj.geometry.notna()].copy()
    if edges_proj.empty:
        return pd.Series(dtype=float), 0, "empty"

    candidates = gpd.sjoin(
        edges_proj[["edge_idx", "geometry"]],
        grid_proj[["grid_idx", "cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    if candidates.empty:
        return pd.Series(dtype=float), int(len(edges_proj)), "ok_no_intersections"

    grid_geometries = grid_proj.set_index("grid_idx")["geometry"]
    lengths = []
    for row in candidates[["geometry", "grid_idx"]].itertuples(index=False):
        lengths.append(row.geometry.intersection(grid_geometries.loc[row.grid_idx]).length)
    candidates = candidates.copy()
    candidates["segment_length_m"] = lengths
    return candidates.groupby("cell_id")["segment_length_m"].sum(), int(len(edges_proj)), "ok"


def facility_metrics(
    event_grid: gpd.GeoDataFrame,
    polygon,
    utm_epsg: int,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame, int, str]:
    features = ox.features_from_polygon(polygon, tags=FACILITY_TAGS)
    if features.empty:
        return pd.DataFrame(), gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), 0, "empty"

    keep_cols = [col for col in ["amenity", "emergency", "healthcare", "social_facility", "name", "geometry"] if col in features.columns]
    facilities = features[keep_cols].copy()
    facilities = facilities[~facilities.geometry.is_empty & facilities.geometry.notna()].copy()
    if facilities.empty:
        return pd.DataFrame(), gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), 0, "empty"

    facilities["facility_category"] = facilities.apply(facility_category, axis=1)
    facilities["geometry"] = facilities.geometry.representative_point()
    facilities = gpd.GeoDataFrame(facilities, geometry="geometry", crs="EPSG:4326")

    grid_proj = event_grid[["cell_id", "geometry"]].to_crs(epsg=utm_epsg)
    facilities_proj = facilities.to_crs(epsg=utm_epsg)
    joined = gpd.sjoin(
        facilities_proj[["facility_category", "geometry"]],
        grid_proj,
        how="inner",
        predicate="within",
    )

    metrics = pd.DataFrame({"cell_id": event_grid["cell_id"].to_numpy()})
    if not joined.empty:
        counts = joined.groupby("cell_id").size().rename("facility_count")
        by_category = (
            joined.pivot_table(
                index="cell_id",
                columns="facility_category",
                values="geometry",
                aggfunc="count",
                fill_value=0,
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )
        metrics = metrics.merge(counts, on="cell_id", how="left").merge(by_category, on="cell_id", how="left")

    for col in ["facility_count", "health", "education", "emergency", "social"]:
        if col not in metrics.columns:
            metrics[col] = 0
    metrics = metrics.rename(
        columns={
            "health": "facility_health_count",
            "education": "facility_education_count",
            "emergency": "facility_emergency_count",
            "social": "facility_social_count",
        }
    )

    if len(facilities_proj) > 0:
        facility_xy = np.column_stack([facilities_proj.geometry.x, facilities_proj.geometry.y])
        centroids = grid_proj.geometry.centroid
        grid_xy = np.column_stack([centroids.x, centroids.y])
        nearest = NearestNeighbors(n_neighbors=1).fit(facility_xy)
        distances, _ = nearest.kneighbors(grid_xy)
        metrics["nearest_facility_m"] = distances[:, 0]
    else:
        metrics["nearest_facility_m"] = np.nan

    return metrics, facilities, int(len(facilities)), "ok"


def process_event(
    event: str,
    event_grid: gpd.GeoDataFrame,
    footprint_row: pd.Series,
    args: argparse.Namespace,
    out_dir: Path,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame, dict]:
    event_center_lon = float(event_grid["cell_center_lon"].mean())
    event_center_lat = float(event_grid["cell_center_lat"].mean())
    utm_epsg = estimate_utm_epsg(event_center_lon, event_center_lat)
    event_date = set_osmnx_settings(out_dir, args.date_mode, event, args.timeout)
    polygon = buffered_event_polygon(footprint_row, args.buffer_deg)

    metrics = empty_event_metrics(event_grid, event)
    fetch_log = {
        "event": event,
        "date_mode": args.date_mode,
        "osm_snapshot": event_date,
        "network_type": args.network_type,
        "utm_epsg": utm_epsg,
        "buffer_deg": args.buffer_deg,
        "road_status": "not_run",
        "road_edges": 0,
        "facility_status": "not_run",
        "facilities": 0,
        "error": "",
    }

    facilities = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    try:
        roads_by_cell, edge_count, road_status = road_metrics(event_grid, polygon, args.network_type, utm_epsg)
        metrics = metrics.merge(roads_by_cell.rename("road_length_m"), on="cell_id", how="left", suffixes=("", "_new"))
        if "road_length_m_new" in metrics.columns:
            metrics["road_length_m"] = metrics["road_length_m_new"].fillna(metrics["road_length_m"])
            metrics = metrics.drop(columns=["road_length_m_new"])
        metrics["road_length_m"] = metrics["road_length_m"].fillna(0.0)
        fetch_log["road_status"] = road_status
        fetch_log["road_edges"] = edge_count
    except Exception:
        fetch_log["road_status"] = "error"
        fetch_log["error"] += "road_error: " + traceback.format_exc(limit=2).replace("\n", " ") + " "

    try:
        facility_df, facilities, facility_count, facility_status = facility_metrics(event_grid, polygon, utm_epsg)
        if not facility_df.empty:
            drop_cols = [
                "facility_count",
                "facility_health_count",
                "facility_education_count",
                "facility_emergency_count",
                "facility_social_count",
                "nearest_facility_m",
            ]
            metrics = metrics.drop(columns=[col for col in drop_cols if col in metrics.columns])
            metrics = metrics.merge(facility_df, on="cell_id", how="left")
        fetch_log["facility_status"] = facility_status
        fetch_log["facilities"] = facility_count
    except Exception:
        fetch_log["facility_status"] = "error"
        fetch_log["error"] += "facility_error: " + traceback.format_exc(limit=2).replace("\n", " ") + " "

    for col in [
        "facility_count",
        "facility_health_count",
        "facility_education_count",
        "facility_emergency_count",
        "facility_social_count",
    ]:
        metrics[col] = metrics[col].fillna(0).astype(int)
    metrics["road_length_m"] = metrics["road_length_m"].fillna(0.0)
    metrics["road_density_m_per_km2"] = metrics["road_length_m"] / ((args.cell_m * args.cell_m) / 1_000_000.0)

    return metrics, facilities, fetch_log


def write_manifest(out_dir: Path, args: argparse.Namespace, fetch_logs: list[dict]) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/03_fetch_osm_context.py",
        "damage_grid": str(args.damage_grid),
        "event_footprints": str(args.footprints_csv),
        "date_mode": args.date_mode,
        "network_type": args.network_type,
        "cell_m": args.cell_m,
        "facility_tags": FACILITY_TAGS,
        "outputs": [
            "osm_grid_features_500m.csv",
            "damage_osm_grid_500m.csv",
            "damage_osm_grid_500m.geojson",
            "osm_facilities.geojson",
            "osm_fetch_log.csv",
        ],
        "source_notes": [
            "OSM roads and facilities are retrieved through OSMnx/Overpass.",
            "Current OSM reflects present map state and can encode post-disaster edits.",
            "Historical mode adds Overpass date filters, but coverage may be lower for older snapshots.",
        ],
        "fetch_logs": fetch_logs,
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--damage-grid", required=True, type=Path)
    parser.add_argument("--footprints-csv", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--date-mode", choices=["current", "historical"], default="current")
    parser.add_argument("--network-type", default="drive")
    parser.add_argument("--buffer-deg", type=float, default=0.01)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--cell-m", type=int, default=500)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    damage_grid = gpd.read_file(args.damage_grid)
    footprints = pd.read_csv(args.footprints_csv).set_index("event")

    all_metrics = []
    all_facilities = []
    fetch_logs = []

    for event in sorted(damage_grid["event"].unique()):
        event_grid = damage_grid[damage_grid["event"] == event].copy()
        if event not in footprints.index:
            raise ValueError(f"Missing event footprint for {event}")
        metrics, facilities, fetch_log = process_event(event, event_grid, footprints.loc[event], args, out_dir)
        all_metrics.append(metrics)
        fetch_logs.append(fetch_log)
        if not facilities.empty:
            facilities = facilities.copy()
            facilities["event"] = event
            all_facilities.append(facilities)
        print(
            event,
            f"roads={fetch_log['road_status']}:{fetch_log['road_edges']}",
            f"facilities={fetch_log['facility_status']}:{fetch_log['facilities']}",
        )

    osm_metrics = pd.concat(all_metrics, ignore_index=True)
    osm_metrics.to_csv(out_dir / f"osm_grid_features_{args.cell_m}m.csv", index=False)

    joined = damage_grid.merge(osm_metrics.drop(columns=["event"]), on="cell_id", how="left")
    joined.to_csv(out_dir / f"damage_osm_grid_{args.cell_m}m.csv", index=False)
    joined.to_file(out_dir / f"damage_osm_grid_{args.cell_m}m.geojson", driver="GeoJSON")

    if all_facilities:
        facilities_gdf = pd.concat(all_facilities, ignore_index=True)
        facilities_gdf = gpd.GeoDataFrame(facilities_gdf, geometry="geometry", crs="EPSG:4326")
        facilities_gdf.to_file(out_dir / "osm_facilities.geojson", driver="GeoJSON")
    else:
        with (out_dir / "osm_facilities.geojson").open("w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": []}, f)

    pd.DataFrame(fetch_logs).to_csv(out_dir / "osm_fetch_log.csv", index=False)
    write_manifest(out_dir, args, fetch_logs)

    print(f"osm_grid={out_dir / f'osm_grid_features_{args.cell_m}m.csv'}")
    print(f"damage_osm_grid={out_dir / f'damage_osm_grid_{args.cell_m}m.csv'}")
    print(f"fetch_log={out_dir / 'osm_fetch_log.csv'}")


if __name__ == "__main__":
    main()
