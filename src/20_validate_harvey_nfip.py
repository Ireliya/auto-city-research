#!/usr/bin/env python3
"""Validate Harvey priority rankings against tract-level NFIP loss proxies."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_proj_data = Path(sys.prefix) / "share" / "proj"
if _proj_data.exists():
    os.environ.setdefault("PROJ_DATA", str(_proj_data))

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
import yaml
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import ndcg_score

from evidence_utils import add_need_indicators, add_scenario_scores, load_need_scenarios, minmax
from figure_style import (
    BLUE,
    NEUTRAL,
    add_panel_label,
    apply_publication_style,
    mm_to_inches,
    save_publication_figure,
    style_numeric_axis,
)


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"


FEMA_API = "https://www.fema.gov/api/open/v2/FimaNfipClaims"
TRACT_LAYER_SOURCES = [
    {
        "url": (
            "https://services.arcgis.com/lqRTrQp2HrfnJt8U/arcgis/rest/services/"
            "tl_2017_48_tract_ACS_join_ExportFeatures_yr/FeatureServer/0/query"
        ),
        "vintage": "2017",
        "provenance": "ArcGIS mirror of US Census Bureau 2017 Texas TIGER/Line tracts",
    },
    {
        "url": (
            "https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2017/"
            "Tracts_Blocks/MapServer/3/query"
        ),
        "vintage": "2017",
        "provenance": "US Census Bureau TIGERweb generalized ACS 2017 tracts",
    },
    {
        "url": (
            "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
            "tigerWMS_ACS2017/MapServer/8/query"
        ),
        "vintage": "2017",
        "provenance": "US Census Bureau TIGERweb ACS 2017 tracts",
    },
]

BASELINE_MODELS = {
    "damage_area_weighted_mean_severity": "damage_index_D",
    "damage_weighted_area": "damage_weighted_area_m2",
    "damage_building_count": "damaged_building_count",
    "damage_severe_count": "severe_building_count",
}
MODEL_LABELS = {
    "damage_area_weighted_mean_severity": "Damage severity",
    "damage_weighted_area": "Damage area",
    "damage_building_count": "Damaged buildings",
    "damage_severe_count": "Severe buildings",
    "need_balanced_need": "Need: balanced",
    "need_population_sensitive": "Need: population",
    "need_accessibility_sensitive": "Need: accessibility",
}
PRIMARY_DAMAGE_MODEL = "damage_area_weighted_mean_severity"
OUTCOME_COLUMNS = ["claim_count", "total_reported_damage_amount", "total_paid_amount"]
METRIC_NAMES = ["spearman_rho", "kendall_tau", "ndcg_at_20pct", "top20_recall"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.geojson"),
    )
    parser.add_argument("--weights-config", type=Path, default=Path("configs/weight_scenarios.yaml"))
    parser.add_argument("--experiment-config", type=Path, default=Path("configs/evidence_hardening.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/harvey_external_validation_v1"))
    parser.add_argument("--figure-dir", type=Path, default=Path("reports/figures"))
    parser.add_argument("--tracts-file", type=Path, help="Optional local tract polygons with an 11-digit GEOID.")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument(
        "--claims-cache",
        type=Path,
        default=Path("data/cache/harvey_nfip_tract_aggregate.csv"),
        help="Privacy-safe tract aggregate checkpoint; no individual claim rows are saved.",
    )
    parser.add_argument("--refresh-claims", action="store_true")
    parser.add_argument("--reuse-aggregated", action="store_true")
    parser.add_argument(
        "--figure-only",
        action="store_true",
        help="Regenerate Figure 10 from an existing metrics CSV without recomputing bootstrap results.",
    )
    return parser.parse_args()


def request_json(
    session: requests.Session,
    url: str,
    params: dict,
    timeout: int = 180,
    attempts: int = 4,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            return payload
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Request failed after {attempts} attempts: {url}: {last_error}")


def clean_tract(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    digits = "".join(character for character in str(value) if character.isdigit())
    if len(digits) == 10:
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("48"):
        return None
    return digits


def paid_amount(record: dict, preferred: str, fallback: str) -> float:
    value = record.get(preferred)
    if value is None:
        value = record.get(fallback)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if np.isfinite(numeric) else 0.0


def numeric_amount(record: dict, field: str) -> float:
    try:
        numeric = float(record.get(field))
    except (TypeError, ValueError):
        return 0.0
    return numeric if np.isfinite(numeric) else 0.0


def fetch_nfip_tract_aggregate(
    settings: dict,
    page_size: int,
    max_pages: int,
) -> tuple[pd.DataFrame, dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": "auto-city-research/1.0 (academic reproducibility)"})
    start = settings["loss_date_start"]
    end = settings["loss_date_end"]
    state = settings["state"]
    filter_text = (
        f"state eq '{state}' and dateOfLoss ge '{start}T00:00:00.000Z' "
        f"and dateOfLoss le '{end}T23:59:59.999Z'"
    )
    selected = ",".join(
        [
            "censusTract",
            "policyCount",
            "buildingDamageAmount",
            "contentsDamageAmount",
            "amountPaidOnBuildingClaim",
            "amountPaidOnContentsClaim",
            "netBuildingPaymentAmount",
            "netContentsPaymentAmount",
            "floodEvent",
            "asOfDate",
        ]
    )
    aggregate: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "claim_count": 0.0,
            "policy_count": 0.0,
            "building_damage_amount": 0.0,
            "contents_damage_amount": 0.0,
            "building_paid_amount": 0.0,
            "contents_paid_amount": 0.0,
        }
    )
    records_seen = 0
    records_valid_tract = 0
    pages = 0
    select_supported = True
    as_of_dates: set[str] = set()

    for page in range(max_pages):
        params: dict[str, object] = {
            "$top": page_size,
            "$skip": page * page_size,
            "$filter": filter_text,
        }
        if select_supported:
            params["$select"] = selected
        try:
            payload = request_json(session, FEMA_API, params, timeout=180)
        except RuntimeError:
            if page == 0 and select_supported:
                select_supported = False
                params.pop("$select", None)
                payload = request_json(session, FEMA_API, params, timeout=180)
            else:
                raise
        records = payload.get("FimaNfipClaims", [])
        if not isinstance(records, list):
            raise ValueError("Unexpected OpenFEMA response: FimaNfipClaims is not a list")
        pages += 1
        records_seen += len(records)
        for record in records:
            if record.get("asOfDate"):
                as_of_dates.add(str(record["asOfDate"]))
            tract = clean_tract(record.get("censusTract"))
            if tract is None:
                continue
            records_valid_tract += 1
            row = aggregate[tract]
            row["claim_count"] += 1
            row["policy_count"] += numeric_amount(record, "policyCount") or 1.0
            row["building_damage_amount"] += numeric_amount(record, "buildingDamageAmount")
            row["contents_damage_amount"] += numeric_amount(record, "contentsDamageAmount")
            row["building_paid_amount"] += paid_amount(
                record,
                "amountPaidOnBuildingClaim",
                "netBuildingPaymentAmount",
            )
            row["contents_paid_amount"] += paid_amount(
                record,
                "amountPaidOnContentsClaim",
                "netContentsPaymentAmount",
            )
        if len(records) < page_size:
            break
        if pages % 10 == 0:
            print(
                f"NFIP progress: pages={pages}, records={records_seen}, "
                f"valid_tract_records={records_valid_tract}",
                file=sys.stderr,
                flush=True,
            )
    else:
        raise RuntimeError(f"OpenFEMA pagination reached --max-pages={max_pages}")

    rows = []
    for tract, values in sorted(aggregate.items()):
        rows.append(
            {
                "tract_geoid": tract,
                **values,
                "total_reported_damage_amount": values["building_damage_amount"]
                + values["contents_damage_amount"],
                "total_paid_amount": values["building_paid_amount"] + values["contents_paid_amount"],
            }
        )
    metadata = {
        "pages": pages,
        "records_seen": records_seen,
        "records_valid_texas_tract": records_valid_tract,
        "aggregated_tracts": len(rows),
        "filter": filter_text,
        "select_supported": select_supported,
        "as_of_dates": sorted(as_of_dates),
    }
    return pd.DataFrame(rows), metadata


def property_value(properties: pd.Series, names: list[str]) -> object | None:
    lookup = {str(column).upper(): column for column in properties.index}
    for name in names:
        if name.upper() in lookup:
            return properties[lookup[name.upper()]]
    return None


def normalize_tract_geoid(tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    tracts = tracts.copy()
    if "tract_geoid" in tracts.columns:
        source = tracts["tract_geoid"]
    else:
        values = []
        for _, row in tracts.drop(columns="geometry").iterrows():
            direct = property_value(row, ["GEOID", "GEOID10", "GEOID20"])
            if direct is not None:
                values.append(direct)
                continue
            state = property_value(row, ["STATE", "STATEFP", "STATEFP10"])
            county = property_value(row, ["COUNTY", "COUNTYFP", "COUNTYFP10"])
            tract = property_value(row, ["TRACT", "TRACTCE", "TRACTCE10"])
            values.append(f"{state}{county}{tract}" if state is not None else None)
        source = pd.Series(values, index=tracts.index)
    tracts["tract_geoid"] = source.map(clean_tract)
    tracts = tracts[tracts["tract_geoid"].notna()].copy()
    tracts = tracts.drop_duplicates("tract_geoid")
    if tracts.empty:
        raise ValueError("No valid Texas tract GEOIDs found in tract polygons")
    return tracts[["tract_geoid", "geometry"]]


def fetch_tracts(grid: gpd.GeoDataFrame, tracts_file: Path | None) -> tuple[gpd.GeoDataFrame, dict]:
    if tracts_file is not None:
        tracts = normalize_tract_geoid(gpd.read_file(tracts_file).to_crs("EPSG:4326"))
        return tracts, {"source": str(tracts_file), "vintage": "user_supplied"}

    bounds = grid.to_crs("EPSG:4326").total_bounds
    envelope = ",".join(f"{value:.8f}" for value in bounds)
    session = requests.Session()
    session.headers.update({"User-Agent": "auto-city-research/1.0 (academic reproducibility)"})
    errors: list[str] = []
    for source in TRACT_LAYER_SOURCES:
        url = source["url"]
        params = {
            "where": "1=1",
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "GEOID,STATEFP,COUNTYFP,TRACTCE",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
        try:
            payload = request_json(session, url, params, timeout=60, attempts=2)
            features = payload.get("features", [])
            if not features:
                raise ValueError("TIGERweb returned no tract features")
            tracts = normalize_tract_geoid(gpd.GeoDataFrame.from_features(features, crs="EPSG:4326"))
            return tracts, {
                "source": url,
                "vintage": source["vintage"],
                "provenance": source["provenance"],
                "features": len(tracts),
            }
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("All TIGERweb tract sources failed:\n" + "\n".join(errors))


def build_grid_models(grid: gpd.GeoDataFrame, scenarios: list[dict]) -> tuple[gpd.GeoDataFrame, list[str]]:
    harvey = grid[grid["event"] == "hurricane-harvey"].copy()
    if harvey.empty:
        raise ValueError("Priority grid contains no hurricane-harvey rows")
    base = pd.DataFrame(harvey.drop(columns="geometry"))
    model_columns: list[str] = []
    for model, damage_column in BASELINE_MODELS.items():
        base[model] = minmax(pd.to_numeric(base[damage_column], errors="coerce").fillna(0.0))
        model_columns.append(model)
    prepared = add_need_indicators(base, "damage_index_D")
    prepared = add_scenario_scores(prepared, scenarios)
    for scenario in scenarios:
        model = f"need_{scenario['name']}"
        prepared[model] = prepared[f"score_{scenario['name']}"]
        model_columns.append(model)
    result = harvey[["cell_id", "geometry"]].merge(
        prepared[["cell_id", *model_columns]],
        on="cell_id",
        how="inner",
        validate="one_to_one",
    )
    return gpd.GeoDataFrame(result, geometry="geometry", crs=harvey.crs), model_columns


def aggregate_models_to_tracts(
    grid: gpd.GeoDataFrame,
    tracts: gpd.GeoDataFrame,
    model_columns: list[str],
) -> pd.DataFrame:
    grid_projected = grid.to_crs("EPSG:32615")
    tracts_projected = tracts.to_crs("EPSG:32615")
    overlay = gpd.overlay(
        grid_projected[["cell_id", *model_columns, "geometry"]],
        tracts_projected[["tract_geoid", "geometry"]],
        how="intersection",
        keep_geom_type=False,
    )
    overlay = overlay[~overlay.geometry.is_empty & overlay.geometry.notna()].copy()
    overlay["intersection_area_m2"] = overlay.geometry.area
    overlay = overlay[overlay["intersection_area_m2"] > 0].copy()
    if overlay.empty:
        raise ValueError("No intersections between Harvey xBD grid and Census tracts")

    rows: list[dict] = []
    for tract, tract_df in overlay.groupby("tract_geoid", sort=True):
        weights = tract_df["intersection_area_m2"].to_numpy(dtype=float)
        row: dict[str, object] = {
            "tract_geoid": tract,
            "grid_intersection_count": int(tract_df["cell_id"].nunique()),
            "covered_area_km2": float(weights.sum() / 1_000_000.0),
        }
        for model in model_columns:
            values = tract_df[model].to_numpy(dtype=float)
            row[f"{model}__mean"] = float(np.average(values, weights=weights))
            row[f"{model}__max"] = float(np.max(values))
        rows.append(row)
    return pd.DataFrame(rows)


def exact_top_indices(values: np.ndarray, ids: np.ndarray, top_share: float) -> set[int]:
    k = int(math.ceil(len(values) * top_share))
    frame = pd.DataFrame({"value": values, "id": ids, "position": np.arange(len(values))})
    ranked = frame.sort_values(["value", "id"], ascending=[False, True], kind="mergesort")
    return set(ranked.head(k)["position"].astype(int))


def rank_metrics(y_true: np.ndarray, y_score: np.ndarray, ids: np.ndarray, top_share: float) -> dict[str, float]:
    rho = spearmanr(y_true, y_score).statistic
    tau = kendalltau(y_true, y_score).statistic
    k = int(math.ceil(len(y_true) * top_share))
    if np.allclose(y_true, 0):
        ndcg = np.nan
        recall = np.nan
    else:
        ndcg = float(ndcg_score(y_true.reshape(1, -1), y_score.reshape(1, -1), k=k))
        true_top = exact_top_indices(y_true, ids, top_share)
        predicted_top = exact_top_indices(y_score, ids, top_share)
        recall = float(len(true_top & predicted_top) / len(true_top)) if true_top else np.nan
    return {
        "spearman_rho": float(rho) if np.isfinite(rho) else np.nan,
        "kendall_tau": float(tau) if np.isfinite(tau) else np.nan,
        "ndcg_at_20pct": ndcg,
        "top20_recall": recall,
    }


def evaluate_models(
    tract_data: pd.DataFrame,
    model_columns: list[str],
    top_share: float,
    bootstrap_replicates: int,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    point_rows: list[dict] = []
    bootstrap_rows: list[dict] = []
    ids = tract_data["tract_geoid"].astype(str).to_numpy()
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(tract_data), size=(bootstrap_replicates, len(tract_data)))

    for aggregation in ["mean", "max"]:
        for outcome in OUTCOME_COLUMNS:
            y_true = tract_data[outcome].to_numpy(dtype=float)
            for model in model_columns:
                score_column = f"{model}__{aggregation}"
                y_score = tract_data[score_column].to_numpy(dtype=float)
                point = rank_metrics(y_true, y_score, ids, top_share)
                for metric, value in point.items():
                    point_rows.append(
                        {
                            "aggregation": aggregation,
                            "outcome": outcome,
                            "model": model,
                            "model_label": MODEL_LABELS.get(model, model),
                            "metric": metric,
                            "value": value,
                            "tracts": int(len(tract_data)),
                        }
                    )
                for replicate, sample in enumerate(samples):
                    replicate_metrics = rank_metrics(
                        y_true[sample],
                        y_score[sample],
                        ids[sample],
                        top_share,
                    )
                    for metric, value in replicate_metrics.items():
                        bootstrap_rows.append(
                            {
                                "replicate": replicate,
                                "aggregation": aggregation,
                                "outcome": outcome,
                                "model": model,
                                "metric": metric,
                                "value": value,
                            }
                        )

    points = pd.DataFrame(point_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    finite_bootstrap = bootstrap[np.isfinite(bootstrap["value"])].copy()
    intervals = (
        finite_bootstrap.groupby(["aggregation", "outcome", "model", "metric"])["value"]
        .quantile([0.025, 0.975])
        .unstack()
        .reset_index()
        .rename(columns={0.025: "ci_low", 0.975: "ci_high"})
    )
    points = points.merge(intervals, on=["aggregation", "outcome", "model", "metric"], how="left")

    baseline_bootstrap = bootstrap[bootstrap["model"] == PRIMARY_DAMAGE_MODEL].rename(
        columns={"value": "baseline_bootstrap_value"}
    )
    paired = bootstrap.merge(
        baseline_bootstrap[
            ["replicate", "aggregation", "outcome", "metric", "baseline_bootstrap_value"]
        ],
        on=["replicate", "aggregation", "outcome", "metric"],
        how="left",
    )
    paired["delta_vs_primary_damage"] = paired["value"] - paired["baseline_bootstrap_value"]
    finite_delta = paired[np.isfinite(paired["delta_vs_primary_damage"])].copy()
    delta_intervals = (
        finite_delta.groupby(["aggregation", "outcome", "model", "metric"])["delta_vs_primary_damage"]
        .quantile([0.025, 0.975])
        .unstack()
        .reset_index()
        .rename(columns={0.025: "delta_ci_low", 0.975: "delta_ci_high"})
    )
    baseline_points = points[points["model"] == PRIMARY_DAMAGE_MODEL][
        ["aggregation", "outcome", "metric", "value"]
    ].rename(columns={"value": "primary_damage_value"})
    points = points.merge(baseline_points, on=["aggregation", "outcome", "metric"], how="left")
    points["delta_vs_primary_damage"] = points["value"] - points["primary_damage_value"]
    points = points.merge(
        delta_intervals,
        on=["aggregation", "outcome", "model", "metric"],
        how="left",
    )
    return points, bootstrap


def round_numeric_output(frame: pd.DataFrame, decimals: int = 12) -> pd.DataFrame:
    """Freeze harmless floating-point serialization noise across repeated runs."""
    rounded = frame.copy()
    numeric_columns = rounded.select_dtypes(include=[np.number]).columns
    rounded[numeric_columns] = rounded[numeric_columns].round(decimals)
    return rounded


def make_figure(metrics: pd.DataFrame, figure_dir: Path) -> None:
    selected = metrics[
        (metrics["aggregation"] == "mean")
        & (metrics["outcome"] == "total_paid_amount")
        & (metrics["metric"].isin(["spearman_rho", "ndcg_at_20pct"]))
    ].copy()
    if selected.empty:
        return
    sns.set_theme(style="white", context="paper")
    apply_publication_style()
    figure_dir.mkdir(parents=True, exist_ok=True)
    order = [MODEL_LABELS.get(model, model) for model in MODEL_LABELS if model in set(selected["model"])]
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(92)),
        constrained_layout=True,
    )
    for panel_label, ax, metric, title in zip(
        ["a", "b"],
        axes,
        ["spearman_rho", "ndcg_at_20pct"],
        ["Rank correlation with NFIP paid loss", "Top-20% NDCG with NFIP paid loss"],
    ):
        data = selected[selected["metric"] == metric].set_index("model_label").reindex(order).reset_index()
        y = np.arange(len(data))
        lower = data["value"].to_numpy() - data["ci_low"].to_numpy()
        upper = data["ci_high"].to_numpy() - data["value"].to_numpy()
        colors = [NEUTRAL if not str(label).startswith("Need:") else BLUE for label in data["model_label"]]
        for idx in range(len(data)):
            ax.errorbar(
                data.loc[idx, "value"],
                y[idx],
                xerr=np.array([[lower[idx]], [upper[idx]]]),
                fmt="o",
                color=colors[idx],
                capsize=2.5,
                elinewidth=1.15,
                markersize=4.5,
            )
            ax.text(
                float(data.loc[idx, "ci_high"]) + 0.012,
                y[idx],
                f"{float(data.loc[idx, 'value']):.2f}",
                va="center",
                fontsize=6.1,
                color=colors[idx],
            )
        ax.set_yticks(y, data["model_label"])
        ax.invert_yaxis()
        ax.axhline(3.5, color="#D9DEE3", linewidth=0.8)
        if metric == "spearman_rho":
            ax.axvline(0, color="#9A9A9A", linewidth=0.75, linestyle="--")
        ax.set_title(title, loc="left", pad=7)
        add_panel_label(ax, panel_label, x=-0.18, y=1.04)
        ax.set_xlabel("Metric value with 95% tract-bootstrap interval")
        ax.margins(x=0.12)
        style_numeric_axis(ax, axis="x")
    tract_n = int(selected["tracts"].max())
    fig.text(
        0.5,
        -0.015,
        f"Harvey NFIP total paid amount | n = {tract_n} tracts | intervals from tract bootstrap",
        ha="center",
        va="top",
        fontsize=6.3,
        color="#555555",
    )
    save_publication_figure(fig, figure_dir, "fig10_harvey_nfip_validation")


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.experiment_config.read_text(encoding="utf-8"))
    settings = config["external_validation"]
    scenarios = load_need_scenarios(args.weights_config)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = args.out_dir / "harvey_nfip_tract_outcomes.csv"

    if args.figure_only:
        metrics_path = args.out_dir / "harvey_external_validation_metrics.csv"
        if not metrics_path.exists():
            raise FileNotFoundError(f"Missing metrics for --figure-only: {metrics_path}")
        make_figure(pd.read_csv(metrics_path), args.figure_dir)
        print(f"figure_outputs={args.figure_dir}")
        return

    grid = gpd.read_file(args.priority_grid)
    grid_models, model_columns = build_grid_models(grid, scenarios)

    if args.reuse_aggregated and outcomes_path.exists():
        tract_data = pd.read_csv(outcomes_path, dtype={"tract_geoid": str})
        source_metadata: dict[str, object] = {"mode": "reuse_aggregated"}
    else:
        claims_metadata_path = args.claims_cache.with_suffix(".metadata.json")
        if args.claims_cache.exists() and not args.refresh_claims:
            claims = pd.read_csv(args.claims_cache, dtype={"tract_geoid": str})
            if claims_metadata_path.exists():
                claims_metadata = json.loads(claims_metadata_path.read_text(encoding="utf-8"))
            else:
                claims_metadata = {"mode": "aggregate_cache", "cache": str(args.claims_cache)}
            print(
                f"Reusing privacy-safe NFIP tract aggregate: {args.claims_cache}",
                file=sys.stderr,
                flush=True,
            )
        else:
            claims, claims_metadata = fetch_nfip_tract_aggregate(
                settings,
                page_size=args.page_size,
                max_pages=args.max_pages,
            )
            args.claims_cache.parent.mkdir(parents=True, exist_ok=True)
            cache_tmp = args.claims_cache.with_suffix(".tmp.csv")
            claims.to_csv(cache_tmp, index=False)
            cache_tmp.replace(args.claims_cache)
            claims_metadata_path.write_text(
                json.dumps(claims_metadata, indent=2, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            print(
                f"Saved privacy-safe NFIP tract aggregate: {args.claims_cache}",
                file=sys.stderr,
                flush=True,
            )
        tracts, tract_metadata = fetch_tracts(grid_models, args.tracts_file)
        tract_scores = aggregate_models_to_tracts(grid_models, tracts, model_columns)
        tract_data = tract_scores.merge(claims, on="tract_geoid", how="left")
        for column in [
            "claim_count",
            "policy_count",
            "building_damage_amount",
            "contents_damage_amount",
            "building_paid_amount",
            "contents_paid_amount",
            "total_reported_damage_amount",
            "total_paid_amount",
        ]:
            tract_data[column] = pd.to_numeric(tract_data[column], errors="coerce").fillna(0.0)
        tract_data = round_numeric_output(tract_data)
        tract_data.to_csv(outcomes_path, index=False)
        source_metadata = {"claims": claims_metadata, "tracts": tract_metadata}

    metrics, bootstrap = evaluate_models(
        tract_data,
        model_columns,
        top_share=float(settings["top_share"]),
        bootstrap_replicates=int(settings["bootstrap_replicates"]),
        seed=int(config["random_seed"]),
    )
    metrics = round_numeric_output(metrics)
    bootstrap = round_numeric_output(bootstrap)
    metrics.to_csv(args.out_dir / "harvey_external_validation_metrics.csv", index=False)
    bootstrap.to_csv(args.out_dir / "harvey_external_validation_bootstrap.csv", index=False)
    make_figure(metrics, args.figure_dir)

    primary_subset = metrics[
        (metrics["aggregation"] == "mean")
        & (metrics["outcome"] == "total_paid_amount")
        & (metrics["model"].str.startswith("need_"))
    ]
    supported_metrics = primary_subset[
        (primary_subset["delta_vs_primary_damage"] > 0)
        & (primary_subset["delta_ci_low"] >= 0)
    ]
    decision = (
        "supporting_external_evidence"
        if supported_metrics["metric"].nunique() >= 2
        else "mixed_or_null_external_evidence_narrow_claim"
    )
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/20_validate_harvey_nfip.py",
        "event": settings["event"],
        "outcome_proxy": settings["outcome_proxy_note"],
        "source_metadata": source_metadata,
        "models": model_columns,
        "outcomes": OUTCOME_COLUMNS,
        "metrics": METRIC_NAMES,
        "bootstrap_replicates": int(settings["bootstrap_replicates"]),
        "random_seed": int(config["random_seed"]),
        "decision": decision,
        "privacy": "Only tract-level aggregates are written; individual NFIP claim rows are never saved.",
        "outputs": [
            "harvey_nfip_tract_outcomes.csv",
            "harvey_external_validation_metrics.csv",
            "harvey_external_validation_bootstrap.csv",
            "reports/figures/fig10_harvey_nfip_validation.png",
            "reports/figures/fig10_harvey_nfip_validation.pdf",
        ],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    print(f"tracts={len(tract_data)}")
    print(f"nfip_claims_in_study_tracts={int(tract_data['claim_count'].sum())}")
    print(f"decision={decision}")
    print(
        metrics[
            (metrics["aggregation"] == "mean")
            & (metrics["outcome"] == "total_paid_amount")
        ][["model", "metric", "value", "ci_low", "ci_high", "delta_vs_primary_damage"]].to_string(index=False)
    )
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
