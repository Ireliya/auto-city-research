#!/usr/bin/env python3
"""Validate priority rankings against CDC SVI and FEMA RI-IHP proxies."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import urllib.parse

_proj_data = Path(sys.prefix) / "share" / "proj"
if _proj_data.exists():
    os.environ.setdefault("PROJ_DATA", str(_proj_data))

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import rasterio
from rasterstats import zonal_stats
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import ndcg_score
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SVI_URL = "https://svi.cdc.gov/Documents/Data/2016/csv/states/SVI_2016_US.csv"
RI_IHP_API = "https://www.fema.gov/api/open/v2/RegistrationIntakeIndividualsHouseholdPrograms"
HARRIS_ZIP_API = (
    "https://services.arcgis.com/su8ic9KbA7PYVxPS/arcgis/rest/services/zipcodes/FeatureServer/0/query"
)

MODEL_LABELS = {
    "damage_index_D": "Damage severity",
    "damage_weighted_area_m2": "Damage-weighted area",
    "damaged_building_count": "Damaged buildings",
    "severe_building_count": "Severe buildings",
    "score_balanced_need": "Balanced scenario",
    "score_population_sensitive": "Population scenario",
    "score_accessibility_sensitive": "Accessibility scenario",
}
SVI_OUTCOMES = ["RPL_THEMES", "RPL_THEME1", "RPL_THEME2", "RPL_THEME3", "RPL_THEME4"]
IHP_BASE_OUTCOMES = [
    "totalValidRegistrations",
    "ihpEligible",
    "ihpAmount",
    "haEligible",
    "haAmount",
    "onaEligible",
    "onaAmount",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.geojson"),
    )
    parser.add_argument("--config", type=Path, default=Path("configs/final_evidence.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/external_proxies_v1"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/external_proxies"))
    parser.add_argument(
        "--worldpop-usa-raster",
        type=Path,
        default=Path("data/raw/worldpop_rasters/usa_pop_2017_CN_100m_R2025A_v1.tif"),
    )
    return parser.parse_args()


def source_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    response = requests.get(url, timeout=180)
    response.raise_for_status()
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(response.content)
    tmp.replace(path)


def load_nfip_module():
    module_path = PROJECT_ROOT / "src" / "20_validate_harvey_nfip.py"
    spec = importlib.util.spec_from_file_location("harvey_nfip", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metric_values(y_true: np.ndarray, y_score: np.ndarray, top_share: float) -> dict[str, float]:
    valid = np.isfinite(y_true) & np.isfinite(y_score)
    y_true = y_true[valid]
    y_score = y_score[valid]
    if len(y_true) < 3 or np.all(y_true == y_true[0]) or np.all(y_score == y_score[0]):
        return {name: np.nan for name in ["spearman_rho", "kendall_tau", "ndcg", "top_recall"]}
    k = max(1, int(math.ceil(len(y_true) * top_share)))
    true_top = set(np.argsort(-y_true, kind="stable")[:k])
    score_top = set(np.argsort(-y_score, kind="stable")[:k])
    return {
        "spearman_rho": float(spearmanr(y_true, y_score).statistic),
        "kendall_tau": float(kendalltau(y_true, y_score).statistic),
        "ndcg": float(ndcg_score(y_true.reshape(1, -1), y_score.reshape(1, -1), k=k)),
        "top_recall": float(len(true_top & score_top) / k),
    }


def stable_seed(base_seed: int, *parts: str) -> int:
    suffix = int(sha256("|".join(parts).encode("utf-8")).hexdigest()[:8], 16)
    return (base_seed + suffix) % (2**32)


def evaluate_rankings(
    frame: pd.DataFrame,
    geography: str,
    proxy_family: str,
    outcomes: list[str],
    score_columns: list[str],
    top_share: float,
    bootstrap_replicates: int,
    base_seed: int,
    coverage_threshold: float | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for outcome in outcomes:
        for score in score_columns:
            pair = frame[[outcome, score]].apply(pd.to_numeric, errors="coerce").dropna()
            point = metric_values(pair[outcome].to_numpy(), pair[score].to_numpy(), top_share)
            rng = np.random.default_rng(stable_seed(base_seed, geography, outcome, score))
            boot = {name: [] for name in point}
            for _ in range(bootstrap_replicates):
                sample = rng.integers(0, len(pair), size=len(pair))
                values = metric_values(
                    pair[outcome].to_numpy()[sample],
                    pair[score].to_numpy()[sample],
                    top_share,
                )
                for metric, value in values.items():
                    if np.isfinite(value):
                        boot[metric].append(value)
            for metric, value in point.items():
                samples = np.asarray(boot[metric], dtype=float)
                rows.append(
                    {
                        "proxy_family": proxy_family,
                        "geography": geography,
                        "coverage_threshold": coverage_threshold,
                        "outcome": outcome,
                        "model": score,
                        "model_label": MODEL_LABELS[score],
                        "model_family": "damage" if score.startswith("damage") or score in {"damaged_building_count", "severe_building_count"} else "multi_source",
                        "metric": metric,
                        "value": value,
                        "ci_low": float(np.quantile(samples, 0.025)) if len(samples) else np.nan,
                        "ci_high": float(np.quantile(samples, 0.975)) if len(samples) else np.nan,
                        "units": int(len(pair)),
                        "bootstrap_replicates": bootstrap_replicates,
                    }
                )
    return pd.DataFrame(rows)


def prepare_svi(
    harvey: gpd.GeoDataFrame,
    score_columns: list[str],
    cache_dir: Path,
) -> tuple[pd.DataFrame, dict]:
    svi_path = cache_dir / "SVI_2016_US.csv"
    download(SVI_URL, svi_path)
    svi = pd.read_csv(svi_path, low_memory=False, dtype={"FIPS": str})
    svi["FIPS"] = svi["FIPS"].str.replace(r"\.0$", "", regex=True).str.zfill(11)
    nfip_module = load_nfip_module()
    tracts, source_metadata = nfip_module.fetch_tracts(harvey, None)
    tract_scores = nfip_module.aggregate_models_to_tracts(harvey, tracts, score_columns)
    keep = ["FIPS", "ST_ABBR", *SVI_OUTCOMES]
    merged = tract_scores.merge(svi[keep], left_on="tract_geoid", right_on="FIPS", how="left")
    for outcome in SVI_OUTCOMES:
        merged[outcome] = pd.to_numeric(merged[outcome], errors="coerce")
        merged.loc[merged[outcome] < 0, outcome] = np.nan
    metadata = {
        "source_url": SVI_URL,
        "source_sha256": source_hash(svi_path),
        "tract_source": source_metadata,
        "intersecting_tracts": int(len(merged)),
        "matched_overall_svi": int(merged["RPL_THEMES"].notna().sum()),
    }
    return merged, metadata


def fetch_ri_ihp(disaster_number: int, state: str, cache_dir: Path) -> tuple[pd.DataFrame, dict]:
    cache_path = cache_dir / f"ri_ihp_dr{disaster_number}_{state.lower()}_zip.csv"
    if cache_path.exists():
        aggregated = pd.read_csv(cache_path, dtype={"zipCode": str})
        return aggregated, {"source_url": RI_IHP_API, "status": "cached", "zip_rows": int(len(aggregated))}
    records: list[dict] = []
    top = 1000
    for skip in range(0, 50000, top):
        params = {
            "$filter": f"disasterNumber eq {disaster_number} and state eq '{state}'",
            "$top": str(top),
            "$skip": str(skip),
        }
        response = requests.get(RI_IHP_API, params=params, timeout=120)
        response.raise_for_status()
        page = response.json().get("RegistrationIntakeIndividualsHouseholdPrograms", [])
        records.extend(page)
        if len(page) < top:
            break
    raw = pd.DataFrame(records)
    raw["zipCode"] = raw["zipCode"].astype(str).str.zfill(5)
    raw = raw[raw["zipCode"].str.fullmatch(r"\d{5}") & raw["zipCode"].ne("00000")].copy()
    for column in IHP_BASE_OUTCOMES:
        raw[column] = pd.to_numeric(raw[column], errors="coerce").fillna(0.0)
    aggregated = raw.groupby("zipCode", as_index=False)[IHP_BASE_OUTCOMES].sum()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    aggregated.to_csv(cache_path, index=False)
    return aggregated, {
        "source_url": RI_IHP_API,
        "status": "downloaded",
        "city_zip_rows": int(len(raw)),
        "zip_rows": int(len(aggregated)),
    }


def fetch_harris_zips() -> tuple[gpd.GeoDataFrame, dict]:
    params = {
        "where": "1=1",
        "outFields": "ZIP,POSTAL,STATE,DATE_MOD",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    response = requests.get(HARRIS_ZIP_API, params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    zips = gpd.GeoDataFrame.from_features(payload["features"], crs="EPSG:4326")
    zips = zips.rename(columns={"ZIP": "zipCode"})
    zips["zipCode"] = zips["zipCode"].astype(str).str.zfill(5)
    zips = zips.drop_duplicates("zipCode")
    return zips, {
        "source_url": HARRIS_ZIP_API,
        "provider": "Harris County public ArcGIS service",
        "features": int(len(zips)),
    }


def aggregate_grid_to_zips(
    harvey: gpd.GeoDataFrame,
    zips: gpd.GeoDataFrame,
    score_columns: list[str],
) -> pd.DataFrame:
    grid_p = harvey[["cell_id", *score_columns, "geometry"]].to_crs("EPSG:32615")
    zip_p = zips[["zipCode", "geometry"]].to_crs("EPSG:32615")
    zip_p["zip_area_m2"] = zip_p.geometry.area
    overlay = gpd.overlay(grid_p, zip_p[["zipCode", "geometry"]], how="intersection")
    overlay = overlay[overlay.geometry.notna() & ~overlay.geometry.is_empty].copy()
    overlay["intersection_area_m2"] = overlay.geometry.area
    rows: list[dict] = []
    for zip_code, group in overlay.groupby("zipCode", sort=True):
        weights = group["intersection_area_m2"].to_numpy(dtype=float)
        row = {
            "zipCode": zip_code,
            "grid_intersection_count": int(group["cell_id"].nunique()),
            "covered_area_m2": float(weights.sum()),
        }
        for score in score_columns:
            row[score] = float(np.average(group[score].to_numpy(dtype=float), weights=weights))
        rows.append(row)
    result = pd.DataFrame(rows).merge(zip_p[["zipCode", "zip_area_m2"]], on="zipCode", how="left")
    result["xbd_coverage_ratio"] = result["covered_area_m2"] / result["zip_area_m2"]
    return result


def add_worldpop_zip_population(zips: gpd.GeoDataFrame, raster_path: Path) -> pd.DataFrame:
    if not raster_path.exists():
        return pd.DataFrame({"zipCode": zips["zipCode"], "worldpop_population": np.nan})
    with rasterio.open(raster_path) as source:
        raster_zips = zips.to_crs(source.crs)
        stats = zonal_stats(
            raster_zips.geometry,
            str(raster_path),
            stats=["sum"],
            nodata=source.nodata,
            all_touched=False,
        )
    return pd.DataFrame(
        {
            "zipCode": zips["zipCode"].astype(str),
            "worldpop_population": [
                0.0 if item.get("sum") is None else float(item["sum"]) for item in stats
            ],
        }
    )


def prepare_ihp(
    harvey: gpd.GeoDataFrame,
    score_columns: list[str],
    config: dict,
    cache_dir: Path,
    worldpop_raster: Path,
) -> tuple[pd.DataFrame, dict]:
    aggregated, ihp_metadata = fetch_ri_ihp(
        int(config["ihp_disaster_number"]), str(config["ihp_state"]), cache_dir
    )
    zips, zip_metadata = fetch_harris_zips()
    scores = aggregate_grid_to_zips(harvey, zips, score_columns)
    populations = add_worldpop_zip_population(zips, worldpop_raster)
    merged = scores.merge(aggregated, on="zipCode", how="left").merge(populations, on="zipCode", how="left")
    for column in IHP_BASE_OUTCOMES:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    registrations = merged["totalValidRegistrations"].replace(0, np.nan)
    eligible = merged["ihpEligible"].replace(0, np.nan)
    population = merged["worldpop_population"].replace(0, np.nan)
    merged["registration_rate_per_1000"] = merged["totalValidRegistrations"] / population * 1000.0
    merged["ihp_eligibility_rate"] = merged["ihpEligible"] / registrations
    merged["ihp_amount_per_eligible"] = merged["ihpAmount"] / eligible
    merged["ona_amount_per_registration"] = merged["onaAmount"] / registrations
    return merged, {
        "ri_ihp": ihp_metadata,
        "zip_geometry": zip_metadata,
        "worldpop_raster": str(worldpop_raster),
        "overlapping_zips": int(len(merged)),
    }


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    external = config["external_validation"]
    seed = int(config["random_seed"])
    replicates = int(external["bootstrap_replicates"])
    top_share = float(external["top_share"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    grid = gpd.read_file(args.priority_grid)
    harvey = grid[grid["event"] == "hurricane-harvey"].copy()
    if harvey.empty:
        raise ValueError("Priority grid does not contain hurricane-harvey")
    score_columns = [column for column in MODEL_LABELS if column in harvey.columns]
    if len(score_columns) != len(MODEL_LABELS):
        missing = sorted(set(MODEL_LABELS) - set(score_columns))
        raise ValueError(f"Priority grid is missing model columns: {missing}")

    svi, svi_metadata = prepare_svi(harvey, score_columns, args.cache_dir)
    svi_score_columns = [f"{column}__mean" for column in score_columns]
    svi_for_metrics = svi.rename(columns={f"{column}__mean": column for column in score_columns})
    svi_metrics = evaluate_rankings(
        svi_for_metrics,
        "census_tract",
        "CDC SVI 2016",
        SVI_OUTCOMES,
        score_columns,
        top_share,
        replicates,
        seed,
    )
    svi.to_csv(args.out_dir / "harvey_svi_tract_scores.csv", index=False)
    svi_metrics.to_csv(args.out_dir / "harvey_svi_rank_metrics.csv", index=False)

    ihp, ihp_metadata = prepare_ihp(
        harvey,
        score_columns,
        external,
        args.cache_dir,
        args.worldpop_usa_raster,
    )
    ihp.to_csv(args.out_dir / "harvey_ihp_zip_scores.csv", index=False)
    ihp_outcomes = [
        *IHP_BASE_OUTCOMES,
        "registration_rate_per_1000",
        "ihp_eligibility_rate",
        "ihp_amount_per_eligible",
        "ona_amount_per_registration",
    ]
    ihp_metric_frames = []
    for threshold in [float(value) for value in external["ihp_coverage_sensitivity"]]:
        subset = ihp[ihp["xbd_coverage_ratio"] >= threshold].copy()
        if len(subset) < 5:
            continue
        ihp_metric_frames.append(
            evaluate_rankings(
                subset,
                "zip_code",
                "FEMA RI-IHP",
                ihp_outcomes,
                score_columns,
                top_share,
                replicates,
                seed,
                threshold,
            )
        )
    ihp_metrics = pd.concat(ihp_metric_frames, ignore_index=True)
    ihp_metrics.to_csv(args.out_dir / "harvey_ihp_rank_metrics.csv", index=False)

    combined = pd.concat([svi_metrics, ihp_metrics], ignore_index=True)
    combined.to_csv(args.out_dir / "external_proxy_rank_metrics.csv", index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/23_validate_svi_ihp.py",
        "priority_grid": str(args.priority_grid),
        "random_seed": seed,
        "bootstrap_replicates": replicates,
        "top_share": top_share,
        "score_columns": score_columns,
        "svi": svi_metadata,
        "ri_ihp": ihp_metadata,
        "interpretation": (
            "SVI, RI-IHP, and NFIP are external proxies with different constructs; "
            "none is ground-truth unmet recovery need."
        ),
        "privacy": "Only public, aggregate, non-PII FEMA records are processed and released.",
        "outputs": [
            "harvey_svi_tract_scores.csv",
            "harvey_svi_rank_metrics.csv",
            "harvey_ihp_zip_scores.csv",
            "harvey_ihp_rank_metrics.csv",
            "external_proxy_rank_metrics.csv",
        ],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(f"svi_tracts={len(svi)} matched={svi_metadata['matched_overall_svi']}")
    print(f"ihp_zips={len(ihp)}")
    print(f"metrics={len(combined)}")
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
