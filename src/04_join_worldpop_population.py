#!/usr/bin/env python3
"""Join WorldPop population exposure to the 500m damage/OSM grid."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.mask import mask
from rasterstats import zonal_stats
from shapely.geometry import box, mapping
from shapely.ops import unary_union


EVENT_WORLDPOP = {
    "hurricane-harvey": {"iso3": "USA", "year": 2017},
    "mexico-earthquake": {"iso3": "MEX", "year": 2017},
    "palu-tsunami": {"iso3": "IDN", "year": 2018},
    "santa-rosa-wildfire": {"iso3": "USA", "year": 2017},
}

STAC_ROOT = "https://api.stac.worldpop.org"


def worldpop_item_id(iso3: str, year: int, resolution: str) -> str:
    if resolution == "100m":
        return f"{iso3.lower()}_pop_{year}_CN_100m_R2025A_v1"
    if resolution == "1km_ua":
        return f"{iso3.lower()}_pop_{year}_CN_1km_R2025A_UA_v1"
    raise ValueError(f"Unsupported WorldPop resolution: {resolution}")


def worldpop_item_url(iso3: str, year: int, resolution: str) -> str:
    item_id = worldpop_item_id(iso3, year, resolution)
    item_url = f"{STAC_ROOT}/collections/{iso3}/items/{item_id}"
    response = requests.get(item_url, timeout=60)
    response.raise_for_status()
    item = response.json()
    return item["assets"]["data"]["href"]


def download_file(url: str, out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    head = requests.head(url, allow_redirects=True, timeout=60)
    expected_size = int(head.headers.get("content-length") or 0)
    if out_path.exists() and (expected_size == 0 or out_path.stat().st_size == expected_size):
        return {"status": "cached", "bytes": out_path.stat().st_size}

    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
    headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as response:
        response.raise_for_status()
        resumed = downloaded > 0 and response.status_code == 206
        mode = "ab" if resumed else "wb"
        with tmp_path.open(mode) as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    if expected_size and tmp_path.stat().st_size != expected_size:
        raise IOError(
            f"Incomplete download for {out_path.name}: "
            f"expected {expected_size} bytes, got {tmp_path.stat().st_size}"
        )
    shutil.move(tmp_path, out_path)
    status = "resumed_download" if resumed else "downloaded"
    return {"status": status, "bytes": out_path.stat().st_size}


def clip_event_raster(src_path: Path, event_grid: gpd.GeoDataFrame, clip_path: Path) -> dict:
    clip_path.parent.mkdir(parents=True, exist_ok=True)
    event_union = unary_union(list(event_grid.geometry))
    with rasterio.open(src_path) as src:
        grid_for_raster = event_grid.to_crs(src.crs)
        event_union = unary_union(list(grid_for_raster.geometry))
        nodata = src.nodata if src.nodata is not None else -99999.0
        out_image, out_transform = mask(
            src,
            [mapping(event_union)],
            crop=True,
            filled=True,
            nodata=nodata,
        )
        profile = src.profile.copy()
        profile.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "nodata": nodata,
                "compress": "lzw",
            }
        )
        with rasterio.open(clip_path, "w", **profile) as dst:
            dst.write(out_image)
    return {"clip_bytes": clip_path.stat().st_size}


def population_for_event(
    event_grid: gpd.GeoDataFrame,
    clip_path: Path,
    cell_m: int,
    worldpop_resolution: str,
) -> pd.DataFrame:
    with rasterio.open(clip_path) as src:
        grid_for_raster = event_grid.to_crs(src.crs)
        stats = zonal_stats(
            grid_for_raster.geometry,
            str(clip_path),
            stats=["sum", "mean", "max", "count"],
            all_touched=worldpop_resolution == "1km_ua",
            nodata=src.nodata,
        )
    rows = []
    for cell_id, stat in zip(event_grid["cell_id"], stats):
        pop_sum = stat.get("sum")
        pop_mean = stat.get("mean")
        pop_max = stat.get("max")
        count = stat.get("count") or 0
        if worldpop_resolution == "1km_ua":
            query_population = 0.0 if pop_mean is None or np.isnan(pop_mean) else float(pop_mean)
            population = query_population * ((cell_m * cell_m) / 1_000_000.0)
            density = query_population
        else:
            population = 0.0 if pop_sum is None or np.isnan(pop_sum) else float(pop_sum)
            density = population / ((cell_m * cell_m) / 1_000_000.0)
        rows.append(
            {
                "cell_id": cell_id,
                "worldpop_population": population,
                "worldpop_raster_mean": np.nan if pop_mean is None else float(pop_mean),
                "worldpop_raster_max": np.nan if pop_max is None else float(pop_max),
                "worldpop_pixel_count": int(count),
                "population_density_per_km2": density,
                "worldpop_resolution": worldpop_resolution,
            }
        )
    return pd.DataFrame(rows)


def write_manifest(out_dir: Path, args: argparse.Namespace, logs: list[dict]) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/04_join_worldpop_population.py",
        "input_grid": str(args.input_grid),
        "raw_dir": str(args.raw_dir),
        "cell_m": args.cell_m,
        "stac_root": STAC_ROOT,
        "events": EVENT_WORLDPOP,
        "mode": args.mode,
        "worldpop_resolution": args.worldpop_resolution,
        "population_definition": "stats-api mode uses WorldPop wpgppop total_population. Raster-download mode sums 100m cells or treats 1km_ua values as density allocated to the configured metric grid.",
        "outputs": [
            f"worldpop_grid_features_{args.cell_m}m.csv",
            f"damage_osm_worldpop_grid_{args.cell_m}m.csv",
            f"damage_osm_worldpop_grid_{args.cell_m}m.geojson",
            "worldpop_fetch_log.csv",
        ],
        "known_limitations": [
            "Population represents residential population estimates, not real-time post-disaster displaced population.",
            "R2025A data are generated after the disaster years and may include updated inputs.",
            "Zonal statistics are approximate and do not use fractional pixel weighting.",
            "In stats-api mode, no full country GeoTIFF is downloaded.",
            "In raster-download mode, full country GeoTIFFs are cached remotely and are not copied into the local submission root.",
        ],
        "logs": logs,
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grid", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--cell-m", type=int, default=500)
    parser.add_argument("--api-grid-m", type=int, default=1000)
    parser.add_argument("--mode", choices=["stats-api", "raster-download"], default="stats-api")
    parser.add_argument("--worldpop-resolution", choices=["100m", "1km_ua"], default="1km_ua")
    parser.add_argument("--max-workers", type=int, default=10)
    parser.add_argument("--poll-seconds", type=int, default=5)
    parser.add_argument("--max-wait-seconds", type=int, default=600)
    parser.add_argument("--partial-every", type=int, default=10)
    parser.add_argument("--events", default="", help="Optional comma-separated event names")
    parser.add_argument("--resume-cell-tasks", type=Path)
    return parser.parse_args()


def feature_collection_json(geometry) -> str:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": geometry.__geo_interface__,
                }
            ],
        },
        separators=(",", ":"),
    )


def worldpop_stats_worker(row: dict, poll_seconds: int, max_wait_seconds: int) -> dict:
    start = time.time()
    params = {
        "dataset": "wpgppop",
        "year": int(row["year"]),
        "geojson": row["geojson"],
        "runasync": "true",
    }
    result = {
        "query_id": row["query_id"],
        "event": row["event"],
        "worldpop_year": int(row["year"]),
        "status": "not_started",
        "taskid": "",
        "worldpop_population": np.nan,
        "elapsed_seconds": np.nan,
        "error_message": "",
    }
    try:
        response = requests.get("https://api.worldpop.org/v1/services/stats", params=params, timeout=90)
        response.raise_for_status()
        created = response.json()
        result["status"] = created.get("status", "created")
        result["taskid"] = created.get("taskid", "")
        if not result["taskid"]:
            result["error_message"] = json.dumps(created)[:500]
            result["status"] = "error"
            result["elapsed_seconds"] = round(time.time() - start, 2)
            return result

        while time.time() - start <= max_wait_seconds:
            task_response = requests.get(f"https://api.worldpop.org/v1/tasks/{result['taskid']}", timeout=60)
            task_response.raise_for_status()
            task = task_response.json()
            result["status"] = task.get("status", result["status"])
            if task.get("error"):
                result["status"] = "error"
                result["error_message"] = task.get("error_message") or json.dumps(task)[:500]
                break
            if task.get("status") == "finished":
                result["worldpop_population"] = float(task.get("data", {}).get("total_population") or 0.0)
                break
            time.sleep(poll_seconds)
        else:
            result["status"] = "timeout"
    except Exception as exc:
        result["status"] = "error"
        result["error_message"] = repr(exc)
    result["elapsed_seconds"] = round(time.time() - start, 2)
    return result


def estimate_utm_epsg(lon: float, lat: float) -> int:
    zone = int(np.floor((lon + 180.0) / 6.0) + 1)
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def build_api_query_cells(grid: gpd.GeoDataFrame, api_grid_m: int) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    query_parts = []
    mapping_parts = []
    for event, event_grid in sorted(grid.groupby("event")):
        lon = float(event_grid["cell_center_lon"].mean())
        lat = float(event_grid["cell_center_lat"].mean())
        utm_epsg = estimate_utm_epsg(lon, lat)
        grid_proj = event_grid.to_crs(epsg=utm_epsg).copy()
        centroids = grid_proj.geometry.centroid
        x0 = np.floor(grid_proj.total_bounds[0] / api_grid_m) * api_grid_m
        y0 = np.floor(grid_proj.total_bounds[1] / api_grid_m) * api_grid_m
        ix = np.floor((centroids.x - x0) / api_grid_m).astype(int)
        iy = np.floor((centroids.y - y0) / api_grid_m).astype(int)
        mapping = pd.DataFrame(
            {
                "cell_id": event_grid["cell_id"].to_numpy(),
                "event": event,
                "query_ix": ix.to_numpy(),
                "query_iy": iy.to_numpy(),
            }
        )
        mapping["query_id"] = (
            mapping["event"].astype(str)
            + f"_{api_grid_m}m_"
            + mapping["query_ix"].astype(str)
            + "_"
            + mapping["query_iy"].astype(str)
        )
        mapping_parts.append(mapping[["cell_id", "event", "query_id"]])

        query_unique = mapping[["query_id", "query_ix", "query_iy"]].drop_duplicates()
        geometries = []
        for row in query_unique.itertuples(index=False):
            x_min = x0 + row.query_ix * api_grid_m
            y_min = y0 + row.query_iy * api_grid_m
            geometries.append(
                {
                    "query_id": row.query_id,
                    "event": event,
                    "utm_epsg": utm_epsg,
                    "geometry": box(x_min, y_min, x_min + api_grid_m, y_min + api_grid_m),
                }
            )
        query_df = pd.DataFrame(geometries)
        query_gdf = gpd.GeoDataFrame(
            query_df.drop(columns=["geometry"]),
            geometry=query_df["geometry"],
            crs=f"EPSG:{utm_epsg}",
        )
        query_parts.append(query_gdf.to_crs("EPSG:4326"))

    return (
        gpd.GeoDataFrame(pd.concat(query_parts, ignore_index=True), geometry="geometry", crs="EPSG:4326"),
        pd.concat(mapping_parts, ignore_index=True),
    )


def join_stats_api(args: argparse.Namespace, grid: gpd.GeoDataFrame) -> None:
    query_grid, query_to_cells = build_api_query_cells(grid, args.api_grid_m)
    rows = []
    for _, row in query_grid.iterrows():
        info = EVENT_WORLDPOP[str(row["event"])]
        rows.append(
            {
                "query_id": row["query_id"],
                "event": row["event"],
                "year": int(info["year"]),
                "iso3": info["iso3"],
                "geojson": feature_collection_json(row.geometry),
            }
        )

    completed = []
    if args.resume_cell_tasks and args.resume_cell_tasks.exists():
        previous = pd.read_csv(args.resume_cell_tasks)
        completed = previous[previous["status"].eq("finished")].to_dict("records")
        completed_ids = {row["query_id"] for row in completed}
        rows = [row for row in rows if row["query_id"] not in completed_ids]
        print(f"resume_finished={len(completed)} remaining={len(rows)}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_map = {
            executor.submit(worldpop_stats_worker, row, args.poll_seconds, args.max_wait_seconds): row["query_id"]
            for row in rows
        }
        for idx, future in enumerate(concurrent.futures.as_completed(future_map), start=1):
            result = future.result()
            completed.append(result)
            if idx == 1 or idx % 25 == 0 or result["status"] != "finished":
                print(
                    f"completed={len(completed)} remaining={len(rows)-idx} "
                    f"query={result['query_id']} status={result['status']} "
                    f"pop={result['worldpop_population']}"
                )
            if idx % args.partial_every == 0:
                pd.DataFrame(completed).to_csv(args.out_dir / "worldpop_cell_tasks_partial.csv", index=False)

    tasks = pd.DataFrame(completed)
    tasks.to_csv(args.out_dir / "worldpop_cell_tasks.csv", index=False)
    if not tasks["status"].eq("finished").all():
        failed = tasks[~tasks["status"].eq("finished")]
        failed.to_csv(args.out_dir / "worldpop_failed_tasks.csv", index=False)
        raise RuntimeError(f"WorldPop stats API unfinished tasks: {len(failed)}")

    query_pop = tasks[["query_id", "event", "worldpop_year", "worldpop_population", "taskid", "elapsed_seconds"]].copy()
    query_pop = query_pop.rename(columns={"worldpop_population": "worldpop_query_population"})
    query_pop["worldpop_query_cell_m"] = args.api_grid_m
    query_pop["population_density_per_km2"] = query_pop["worldpop_query_population"] / ((args.api_grid_m * args.api_grid_m) / 1_000_000.0)
    pop_features = query_to_cells.merge(query_pop.drop(columns=["event"]), on="query_id", how="left")
    pop_features["worldpop_population"] = pop_features["population_density_per_km2"] * ((args.cell_m * args.cell_m) / 1_000_000.0)
    pop_features["worldpop_source"] = "WorldPop wpgppop stats API; 1km query grid density downscaled to 500m cells"
    pop_features.to_csv(args.out_dir / f"worldpop_grid_features_{args.cell_m}m.csv", index=False)

    joined = grid.merge(pop_features.drop(columns=["event"]), on="cell_id", how="left")
    joined.to_csv(args.out_dir / f"damage_osm_worldpop_grid_{args.cell_m}m.csv", index=False)
    joined.to_file(args.out_dir / f"damage_osm_worldpop_grid_{args.cell_m}m.geojson", driver="GeoJSON")

    logs = []
    for event, event_df in pop_features.groupby("event"):
        info = EVENT_WORLDPOP[event]
        logs.append(
            {
                "event": event,
                "iso3": info["iso3"],
                "year": info["year"],
                "mode": "stats-api",
                "cell_m": args.cell_m,
                "api_grid_m": args.api_grid_m,
                "cells": int(len(event_df)),
                "api_query_cells": int(query_grid[query_grid["event"].eq(event)]["query_id"].nunique()),
                "population_sum": float(event_df["worldpop_population"].sum()),
                "population_median": float(event_df["worldpop_population"].median()),
            }
        )
    pd.DataFrame(logs).to_csv(args.out_dir / "worldpop_fetch_log.csv", index=False)
    write_manifest(args.out_dir, args, logs)

    print(f"worldpop_grid={args.out_dir / f'worldpop_grid_features_{args.cell_m}m.csv'}")
    print(f"joined_grid={args.out_dir / f'damage_osm_worldpop_grid_{args.cell_m}m.csv'}")
    print(f"fetch_log={args.out_dir / 'worldpop_fetch_log.csv'}")


def join_raster_download(args: argparse.Namespace, grid: gpd.GeoDataFrame) -> None:
    if args.raw_dir is None:
        raise ValueError("--raw-dir is required for raster-download mode")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    clips_dir = args.out_dir / "clips"

    grid = gpd.read_file(args.input_grid)
    all_features = []
    logs = []

    country_year_to_path: dict[tuple[str, int, str], Path] = {}
    for event, info in EVENT_WORLDPOP.items():
        iso3 = info["iso3"]
        year = int(info["year"])
        event_grid = grid[grid["event"] == event].copy()
        if event_grid.empty:
            continue

        key = (iso3, year, args.worldpop_resolution)
        if key not in country_year_to_path:
            url = worldpop_item_url(iso3, year, args.worldpop_resolution)
            raster_path = args.raw_dir / f"{worldpop_item_id(iso3, year, args.worldpop_resolution)}.tif"
            download_info = download_file(url, raster_path)
            country_year_to_path[key] = raster_path
        else:
            url = worldpop_item_url(iso3, year, args.worldpop_resolution)
            raster_path = country_year_to_path[key]
            download_info = {"status": "cached_reuse", "bytes": raster_path.stat().st_size}

        clip_path = clips_dir / f"{event}_worldpop_{year}_{args.worldpop_resolution}.tif"
        clip_info = clip_event_raster(raster_path, event_grid, clip_path)
        features = population_for_event(event_grid, clip_path, args.cell_m, args.worldpop_resolution)
        features["event"] = event
        features["worldpop_iso3"] = iso3
        features["worldpop_year"] = year
        features["worldpop_source"] = f"WorldPop STAC {args.worldpop_resolution} raster"
        all_features.append(features)
        log = {
            "event": event,
            "iso3": iso3,
            "year": year,
            "url": url,
            "raw_raster": str(raster_path),
            "clip_raster": str(clip_path),
            **download_info,
            **clip_info,
            "cells": int(len(event_grid)),
            "population_sum": float(features["worldpop_population"].sum()),
        }
        logs.append(log)
        print(event, iso3, year, download_info["status"], f"population={log['population_sum']:.2f}")

    pop_features = pd.concat(all_features, ignore_index=True)
    pop_features.to_csv(args.out_dir / f"worldpop_grid_features_{args.cell_m}m.csv", index=False)
    joined = grid.merge(pop_features.drop(columns=["event"]), on="cell_id", how="left")
    joined.to_csv(args.out_dir / f"damage_osm_worldpop_grid_{args.cell_m}m.csv", index=False)
    joined.to_file(args.out_dir / f"damage_osm_worldpop_grid_{args.cell_m}m.geojson", driver="GeoJSON")
    pd.DataFrame(logs).to_csv(args.out_dir / "worldpop_fetch_log.csv", index=False)
    write_manifest(args.out_dir, args, logs)

    print(f"worldpop_grid={args.out_dir / f'worldpop_grid_features_{args.cell_m}m.csv'}")
    print(f"joined_grid={args.out_dir / f'damage_osm_worldpop_grid_{args.cell_m}m.csv'}")
    print(f"fetch_log={args.out_dir / 'worldpop_fetch_log.csv'}")


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    grid = gpd.read_file(args.input_grid)
    events = {item.strip() for item in args.events.split(",") if item.strip()}
    if events:
        grid = grid[grid["event"].isin(events)].copy()
        if grid.empty:
            raise ValueError(f"No rows remain after event filter: {sorted(events)}")
    if args.mode == "stats-api":
        join_stats_api(args, grid)
    else:
        join_raster_download(args, grid)


if __name__ == "__main__":
    main()
