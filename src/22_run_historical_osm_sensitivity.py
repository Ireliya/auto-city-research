#!/usr/bin/env python3
"""Compare current OSM context with pre-disaster snapshots from ohsome."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time

_proj_data = Path(sys.prefix) / "share" / "proj"
if _proj_data.exists():
    os.environ.setdefault("PROJ_DATA", str(_proj_data))

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely import union_all
from shapely.geometry import shape
from sklearn.neighbors import NearestNeighbors
import yaml

from evidence_utils import add_need_indicators, add_scenario_scores, exact_stable_mismatch, load_need_scenarios


FEATURE_FILTERS = {
    "roads": "highway=* and type:way",
    "facilities": (
        "(amenity in (hospital,clinic,doctors,pharmacy,school,college,university,"
        "police,fire_station,social_facility,community_centre,shelter)) or "
        "(emergency in (ambulance_station,assembly_point)) or healthcare=* or social_facility=*"
    ),
    "buildings": "building=* and building!=no and (type:way or type:relation)",
}

HEALTH_VALUES = {"hospital", "clinic", "doctors", "pharmacy", "ambulance_station"}
EDUCATION_VALUES = {"school", "college", "university"}
EMERGENCY_VALUES = {"police", "fire_station", "ambulance_station", "assembly_point"}
SOCIAL_VALUES = {"social_facility", "community_centre", "shelter"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.geojson"),
    )
    parser.add_argument(
        "--current-building-grid",
        type=Path,
        default=Path("data/derived/osm_building_form_v1/osm_building_grid_features_500m.csv"),
    )
    parser.add_argument(
        "--current-osm-fetch-log",
        type=Path,
        default=Path("data/derived/osm_context_v1/osm_fetch_log.csv"),
    )
    parser.add_argument("--config", type=Path, default=Path("configs/final_evidence.yaml"))
    parser.add_argument("--weights-config", type=Path, default=Path("configs/weight_scenarios.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/historical_osm_v1"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/ohsome_historical"))
    parser.add_argument("--events", default="", help="Optional comma-separated event names")
    return parser.parse_args()


def estimate_utm_epsg(lon: float, lat: float) -> int:
    zone = min(max(int(math.floor((lon + 180.0) / 6.0) + 1), 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def iter_tiles(bounds: tuple[float, float, float, float], step: float) -> list[tuple[int, tuple[float, float, float, float]]]:
    minx, miny, maxx, maxy = bounds
    x0 = math.floor(minx / step) * step
    y0 = math.floor(miny / step) * step
    tiles: list[tuple[int, tuple[float, float, float, float]]] = []
    tile_id = 0
    x = x0
    while x < maxx:
        y = y0
        while y < maxy:
            tiles.append((tile_id, (x, y, min(x + step, maxx), min(y + step, maxy))))
            tile_id += 1
            y += step
        x += step
    return tiles


def valid_feature_collection(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list)


def fetch_tile(
    api_root: str,
    event: str,
    kind: str,
    snapshot: str,
    tile_id: int,
    bbox: tuple[float, float, float, float],
    cache_dir: Path,
    max_attempts: int,
    retry_seconds: int,
) -> tuple[list[dict], dict]:
    cache_path = cache_dir / event / kind / f"tile_{tile_id:04d}.geojson"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    log = {
        "event": event,
        "kind": kind,
        "snapshot": snapshot,
        "tile_id": tile_id,
        "bbox": ",".join(f"{value:.6f}" for value in bbox),
        "status": "not_started",
        "attempts": 0,
        "features": 0,
        "bytes": 0,
        "error": "",
    }
    if cache_path.exists() and valid_feature_collection(cache_path):
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        log.update(status="cached", features=len(payload["features"]), bytes=cache_path.stat().st_size)
        return payload["features"], log

    data = {
        "bboxes": ",".join(str(value) for value in bbox),
        "time": snapshot,
        "filter": FEATURE_FILTERS[kind],
        "properties": "tags,metadata",
        "clipGeometry": "true",
    }
    for attempt in range(1, max_attempts + 1):
        log["attempts"] = attempt
        try:
            response = requests.post(f"{api_root}/elements/geometry", data=data, timeout=180)
            response.raise_for_status()
            payload = response.json()
            if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
                raise ValueError("ohsome did not return a GeoJSON FeatureCollection")
            tmp_path = cache_path.with_suffix(".geojson.part")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
            tmp_path.replace(cache_path)
            log.update(
                status="ok" if payload["features"] else "empty",
                features=len(payload["features"]),
                bytes=cache_path.stat().st_size,
            )
            return payload["features"], log
        except Exception as exc:
            log["error"] = repr(exc)
            if attempt < max_attempts:
                time.sleep(retry_seconds * attempt)
    log["status"] = "error"
    return [], log


def deduplicate_features(features: list[dict]) -> gpd.GeoDataFrame:
    rows: list[dict] = []
    for index, feature in enumerate(features):
        geometry = feature.get("geometry")
        if geometry is None:
            continue
        parsed = shape(geometry)
        if parsed.is_empty:
            continue
        properties = feature.get("properties") or {}
        rows.append(
            {
                "osm_id": str(properties.get("@osmId") or feature.get("id") or f"anonymous/{index}"),
                "properties": properties,
                "geometry": parsed,
            }
        )
    if not rows:
        return gpd.GeoDataFrame(columns=["osm_id", "properties", "geometry"], geometry="geometry", crs="EPSG:4326")
    raw = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    merged_rows = []
    for osm_id, group in raw.groupby("osm_id", sort=False):
        merged_rows.append(
            {
                "osm_id": osm_id,
                "properties": group.iloc[0]["properties"],
                    "geometry": union_all(group.geometry.to_numpy()),
            }
        )
    return gpd.GeoDataFrame(merged_rows, geometry="geometry", crs="EPSG:4326")


def fetch_kind(event: str, kind: str, snapshot: str, bounds, config: dict, cache_dir: Path) -> tuple[gpd.GeoDataFrame, list[dict], bool]:
    features: list[dict] = []
    logs: list[dict] = []
    for tile_id, bbox in iter_tiles(bounds, float(config["tile_degrees"])):
        tile_features, log = fetch_tile(
            config["api_root"],
            event,
            kind,
            snapshot,
            tile_id,
            bbox,
            cache_dir,
            int(config["max_attempts"]),
            int(config["retry_seconds"]),
        )
        features.extend(tile_features)
        logs.append(log)
    complete = all(log["status"] in {"ok", "empty", "cached"} for log in logs)
    return deduplicate_features(features) if complete else deduplicate_features([]), logs, complete


def facility_category(properties: dict) -> str:
    values = {
        str(properties.get("amenity", "")),
        str(properties.get("emergency", "")),
        str(properties.get("healthcare", "")),
        str(properties.get("social_facility", "")),
    }
    if values & HEALTH_VALUES or properties.get("healthcare"):
        return "health"
    if values & EDUCATION_VALUES:
        return "education"
    if values & EMERGENCY_VALUES:
        return "emergency"
    if values & SOCIAL_VALUES or properties.get("social_facility"):
        return "social"
    return "other"


def aggregate_roads(grid: gpd.GeoDataFrame, roads: gpd.GeoDataFrame, utm_epsg: int, complete: bool) -> pd.DataFrame:
    result = pd.DataFrame({"cell_id": grid["cell_id"].astype(str)})
    if not complete:
        result["historical_road_length_m"] = np.nan
        return result
    result["historical_road_length_m"] = 0.0
    if roads.empty:
        return result
    grid_p = grid[["cell_id", "geometry"]].to_crs(utm_epsg).reset_index(drop=True)
    grid_p["grid_index"] = grid_p.index
    roads_p = roads[["osm_id", "geometry"]].to_crs(utm_epsg).explode(index_parts=False, ignore_index=True)
    roads_p = roads_p[roads_p.geom_type.isin(["LineString", "MultiLineString"])].copy()
    if roads_p.empty:
        return result
    candidates = gpd.sjoin(
        roads_p,
        grid_p[["grid_index", "cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    if candidates.empty:
        return result
    cell_geometry = grid_p.set_index("grid_index")["geometry"]
    candidates["segment_length_m"] = [
        row.geometry.intersection(cell_geometry.loc[row.grid_index]).length
        for row in candidates.itertuples()
    ]
    totals = candidates.groupby("cell_id")["segment_length_m"].sum()
    result["historical_road_length_m"] = result["cell_id"].map(totals).fillna(0.0)
    return result


def aggregate_facilities(grid: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame, utm_epsg: int, complete: bool) -> pd.DataFrame:
    result = pd.DataFrame({"cell_id": grid["cell_id"].astype(str)})
    count_columns = [
        "historical_facility_count",
        "historical_facility_health_count",
        "historical_facility_education_count",
        "historical_facility_emergency_count",
        "historical_facility_social_count",
    ]
    if not complete:
        for column in count_columns:
            result[column] = np.nan
        result["historical_nearest_facility_m"] = np.nan
        return result
    for column in count_columns:
        result[column] = 0
    result["historical_nearest_facility_m"] = np.nan
    if facilities.empty:
        return result
    points = facilities.copy()
    points["facility_category"] = points["properties"].map(facility_category)
    points["geometry"] = points.geometry.representative_point()
    points = gpd.GeoDataFrame(points, geometry="geometry", crs="EPSG:4326").to_crs(utm_epsg)
    grid_p = grid[["cell_id", "geometry"]].to_crs(utm_epsg)
    joined = gpd.sjoin(points[["facility_category", "geometry"]], grid_p, how="inner", predicate="within")
    if not joined.empty:
        total = joined.groupby("cell_id").size()
        result["historical_facility_count"] = result["cell_id"].map(total).fillna(0).astype(int)
        for category in ["health", "education", "emergency", "social"]:
            values = joined[joined["facility_category"] == category].groupby("cell_id").size()
            result[f"historical_facility_{category}_count"] = result["cell_id"].map(values).fillna(0).astype(int)
    facility_xy = np.column_stack([points.geometry.x, points.geometry.y])
    centroids = grid_p.geometry.centroid
    distances, _ = NearestNeighbors(n_neighbors=1).fit(facility_xy).kneighbors(
        np.column_stack([centroids.x, centroids.y])
    )
    result["historical_nearest_facility_m"] = distances[:, 0]
    return result


def aggregate_buildings(grid: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, utm_epsg: int, complete: bool) -> pd.DataFrame:
    result = pd.DataFrame({"cell_id": grid["cell_id"].astype(str)})
    if not complete:
        result["historical_osm_building_count"] = np.nan
        result["historical_osm_building_area_m2"] = np.nan
        return result
    result["historical_osm_building_count"] = 0
    result["historical_osm_building_area_m2"] = 0.0
    if buildings.empty:
        return result
    building_p = buildings[["osm_id", "geometry"]].to_crs(utm_epsg).explode(index_parts=False, ignore_index=True)
    building_p = building_p[building_p.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if building_p.empty:
        return result
    grid_p = grid[["cell_id", "geometry"]].to_crs(utm_epsg)
    points = building_p.copy()
    points["geometry"] = points.geometry.representative_point()
    counted = gpd.sjoin(points, grid_p, how="inner", predicate="within").groupby("cell_id").size()
    result["historical_osm_building_count"] = result["cell_id"].map(counted).fillna(0).astype(int)
    areas = gpd.overlay(building_p, grid_p, how="intersection")
    if not areas.empty:
        areas["intersection_area_m2"] = areas.geometry.area
        totals = areas.groupby("cell_id")["intersection_area_m2"].sum()
        result["historical_osm_building_area_m2"] = result["cell_id"].map(totals).fillna(0.0)
    return result


def mismatch_flags(frame: pd.DataFrame, scenarios: list[dict], top_share: float) -> tuple[pd.Series, int]:
    prepared = add_scenario_scores(add_need_indicators(frame, "damage_index_D"), scenarios)
    flags, _, k = exact_stable_mismatch(prepared, "damage_index_D", scenarios, top_share)
    return pd.Series(flags.to_numpy(), index=prepared["cell_id"].astype(str)), k


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    osm_config = config["historical_osm"]
    scenarios = load_need_scenarios(args.weights_config)
    top_share = float(config["consensus"]["top_share"])
    selected_events = {value.strip() for value in args.events.split(",") if value.strip()}
    grid = gpd.read_file(args.priority_grid).to_crs("EPSG:4326")
    if selected_events:
        grid = grid[grid["event"].isin(selected_events)].copy()
    current_buildings = pd.read_csv(args.current_building_grid) if args.current_building_grid.exists() else pd.DataFrame()
    current_fetch = (
        pd.read_csv(args.current_osm_fetch_log)
        if args.current_osm_fetch_log.exists()
        else pd.DataFrame()
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_cells: list[gpd.GeoDataFrame] = []
    summaries: list[dict] = []
    fetch_logs: list[dict] = []
    for event, event_grid in grid.groupby("event", sort=True):
        event_grid = event_grid.copy()
        snapshot = str(osm_config["snapshots"][event])
        center = union_all(event_grid.geometry.to_numpy()).centroid
        utm_epsg = estimate_utm_epsg(center.x, center.y)
        bounds = tuple(float(value) for value in event_grid.total_bounds)
        feature_sets = {}
        complete = {}
        for kind in FEATURE_FILTERS:
            features, logs, is_complete = fetch_kind(
                event, kind, snapshot, bounds, osm_config, args.cache_dir
            )
            feature_sets[kind] = features
            complete[kind] = is_complete
            fetch_logs.extend(logs)
            print(event, kind, f"complete={is_complete}", f"features={len(features)}")

        cells = event_grid[["event", "cell_id", "geometry"]].copy()
        cells = cells.merge(aggregate_roads(event_grid, feature_sets["roads"], utm_epsg, complete["roads"]), on="cell_id")
        cells = cells.merge(
            aggregate_facilities(event_grid, feature_sets["facilities"], utm_epsg, complete["facilities"]),
            on="cell_id",
        )
        cells = cells.merge(
            aggregate_buildings(event_grid, feature_sets["buildings"], utm_epsg, complete["buildings"]),
            on="cell_id",
        )
        cells["historical_road_density_m_per_km2"] = cells["historical_road_length_m"] / 0.25

        current = pd.DataFrame(event_grid.drop(columns="geometry"))
        current_flags, budget_k = mismatch_flags(current, scenarios, top_share)
        cells["current_strict_mismatch"] = cells["cell_id"].map(current_flags)
        current_by_cell = current.set_index(current["cell_id"].astype(str))
        historical_by_cell = cells.set_index(cells["cell_id"].astype(str))
        current_nonzero = current_by_cell["road_length_m"] > 0
        historical_nonzero = historical_by_cell["historical_road_length_m"].fillna(0) > 0
        road_coverage_ratio = (
            float((current_nonzero & historical_nonzero).sum() / current_nonzero.sum())
            if current_nonzero.sum()
            else np.nan
        )
        current_facility_nonzero = current_by_cell["facility_count"].fillna(0) > 0
        historical_facility_nonzero = historical_by_cell["historical_facility_count"].fillna(0) > 0
        facility_coverage_ratio = (
            float(
                (current_facility_nonzero & historical_facility_nonzero).sum()
                / current_facility_nonzero.sum()
            )
            if current_facility_nonzero.sum()
            else np.nan
        )
        rank_assessable = bool(
            complete["roads"]
            and complete["facilities"]
            and cells["historical_nearest_facility_m"].notna().any()
            and road_coverage_ratio >= float(osm_config["comparable_road_coverage_ratio"])
            and facility_coverage_ratio
            >= float(osm_config["comparable_facility_coverage_ratio"])
        )
        mismatch_jaccard = np.nan
        historical_count = np.nan
        status = "not_assessable"
        if rank_assessable:
            historical = current.copy()
            lookup = cells.set_index("cell_id")
            historical["road_length_m"] = historical["cell_id"].map(lookup["historical_road_length_m"])
            historical["road_density_m_per_km2"] = historical["cell_id"].map(
                lookup["historical_road_density_m_per_km2"]
            )
            for target, source in [
                ("facility_count", "historical_facility_count"),
                ("facility_health_count", "historical_facility_health_count"),
                ("facility_education_count", "historical_facility_education_count"),
                ("facility_emergency_count", "historical_facility_emergency_count"),
                ("facility_social_count", "historical_facility_social_count"),
                ("nearest_facility_m", "historical_nearest_facility_m"),
            ]:
                historical[target] = historical["cell_id"].map(lookup[source])
            historical_flags, _ = mismatch_flags(historical, scenarios, top_share)
            cells["historical_strict_mismatch"] = cells["cell_id"].map(historical_flags)
            cells["temporal_persistence"] = cells["current_strict_mismatch"] & cells["historical_strict_mismatch"]
            current_ids = set(current_flags[current_flags].index)
            historical_ids = set(historical_flags[historical_flags].index)
            union = current_ids | historical_ids
            mismatch_jaccard = len(current_ids & historical_ids) / len(union) if union else 1.0
            historical_count = int(historical_flags.sum())
            status = (
                "support"
                if mismatch_jaccard >= float(osm_config["minimum_mismatch_jaccard"])
                else "does_not_support"
            )
        else:
            cells["historical_strict_mismatch"] = np.nan
            cells["temporal_persistence"] = np.nan

        current_building_event = current_buildings[current_buildings.get("event", pd.Series(dtype=str)) == event]
        current_fetch_event = current_fetch[current_fetch.get("event", pd.Series(dtype=str)) == event]
        historical_building_nonzero = historical_by_cell["historical_osm_building_count"].fillna(0) > 0
        if len(current_building_event):
            current_building_nonzero = (
                current_building_event.set_index(current_building_event["cell_id"].astype(str))[
                    "osm_building_count"
                ].reindex(historical_by_cell.index, fill_value=0)
                > 0
            )
        else:
            current_building_nonzero = pd.Series(False, index=historical_by_cell.index)
        summaries.append(
            {
                "event": event,
                "snapshot": snapshot,
                "cells": int(len(event_grid)),
                "exact_budget_k": budget_k,
                "roads_complete": complete["roads"],
                "facilities_complete": complete["facilities"],
                "buildings_complete": complete["buildings"],
                "historical_roads": int(len(feature_sets["roads"])),
                "historical_facilities": int(len(feature_sets["facilities"])),
                "historical_buildings": int(len(feature_sets["buildings"])),
                "current_road_edges": int(current_fetch_event["road_edges"].iloc[0]) if len(current_fetch_event) else np.nan,
                "current_facilities": int(current_fetch_event["facilities"].iloc[0]) if len(current_fetch_event) else np.nan,
                "current_osm_buildings": int(current_building_event["osm_building_count"].sum()) if len(current_building_event) else np.nan,
                "road_nonzero_coverage_ratio": road_coverage_ratio,
                "facility_nonzero_coverage_ratio": facility_coverage_ratio,
                "current_road_nonzero_cell_share": float(current_nonzero.mean()),
                "historical_road_nonzero_cell_share": float(historical_nonzero.mean()),
                "current_facility_nonzero_cell_share": float(current_facility_nonzero.mean()),
                "historical_facility_nonzero_cell_share": float(historical_facility_nonzero.mean()),
                "current_building_nonzero_cell_share": float(current_building_nonzero.mean()),
                "historical_building_nonzero_cell_share": float(historical_building_nonzero.mean()),
                "current_strict_mismatch_count": int(current_flags.sum()),
                "historical_strict_mismatch_count": historical_count,
                "mismatch_jaccard": mismatch_jaccard,
                "temporal_evidence": status,
            }
        )
        all_cells.append(cells)

    output_cells = gpd.GeoDataFrame(pd.concat(all_cells, ignore_index=True), geometry="geometry", crs="EPSG:4326")
    output_cells.to_file(args.out_dir / "historical_osm_grid_500m.geojson", driver="GeoJSON")
    output_cells.drop(columns="geometry").to_csv(args.out_dir / "historical_osm_grid_500m.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.out_dir / "historical_osm_event_summary.csv", index=False)
    pd.DataFrame(fetch_logs).to_csv(args.out_dir / "ohsome_fetch_log.csv", index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/22_run_historical_osm_sensitivity.py",
        "api_root": osm_config["api_root"],
        "attribution": "OpenStreetMap contributors; data retrieved through the ohsome API",
        "snapshots": osm_config["snapshots"],
        "filters": FEATURE_FILTERS,
        "failure_policy": "A failed tile is never converted to zero; the affected event is not assessable.",
        "temporal_evidence_rule": {
            "minimum_road_coverage_ratio": osm_config["comparable_road_coverage_ratio"],
            "minimum_facility_coverage_ratio": osm_config[
                "comparable_facility_coverage_ratio"
            ],
            "minimum_mismatch_jaccard": osm_config["minimum_mismatch_jaccard"],
        },
        "outputs": [
            "historical_osm_grid_500m.csv",
            "historical_osm_grid_500m.geojson",
            "historical_osm_event_summary.csv",
            "ohsome_fetch_log.csv",
        ],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(pd.DataFrame(summaries).to_string(index=False))
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
