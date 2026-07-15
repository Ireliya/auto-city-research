#!/usr/bin/env python3
"""Analyze disagreement between damage-only and multi-source priority rankings."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr


INDICATOR_COLUMNS = [
    "damage_norm",
    "population_norm",
    "accessibility_need_norm",
    "service_need_norm",
]


def minmax(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    lo = values.min(skipna=True)
    hi = values.max(skipna=True)
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(np.zeros(len(values)), index=series.index, dtype=float)
    return ((values - lo) / (hi - lo)).fillna(0.0)


def load_scenarios(path: Path) -> list[dict]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = []
    for scenario in config.get("active_scenarios", []):
        weights = scenario.get("weights", {})
        if not isinstance(weights, dict):
            continue
        if scenario["name"] == "damage_only_baseline":
            continue
        weight_sum = sum(float(v) for v in weights.values())
        if weight_sum <= 0:
            raise ValueError(f"Scenario has nonpositive weight sum: {scenario['name']}")
        scenarios.append(
            {
                "name": scenario["name"],
                "role": scenario.get("role", ""),
                "weights": {key: float(value) / weight_sum for key, value in weights.items()},
            }
        )
    if not scenarios:
        raise ValueError("No active multi-source priority scenarios found")
    return scenarios


def add_indicators(grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    grid = grid.copy()
    grid["damage_index_D"] = pd.to_numeric(grid["damage_index_D"], errors="coerce").fillna(0.0)
    grid["worldpop_population"] = pd.to_numeric(grid["worldpop_population"], errors="coerce").fillna(0.0)
    grid["road_density_m_per_km2"] = pd.to_numeric(grid["road_density_m_per_km2"], errors="coerce").fillna(0.0)
    grid["facility_count"] = pd.to_numeric(grid["facility_count"], errors="coerce").fillna(0.0)
    grid["nearest_facility_m"] = pd.to_numeric(grid["nearest_facility_m"], errors="coerce")

    parts = []
    for event, event_df in grid.groupby("event", sort=True):
        event_df = event_df.copy()
        event_df["damage_norm"] = minmax(event_df["damage_index_D"])
        event_df["population_norm"] = minmax(np.log1p(event_df["worldpop_population"]))
        event_df["accessibility_need_norm"] = minmax(-np.log1p(event_df["road_density_m_per_km2"]))
        nearest = event_df["nearest_facility_m"].fillna(event_df["nearest_facility_m"].max())
        nearest_norm = minmax(nearest)
        inverse_facility_norm = minmax(-np.log1p(event_df["facility_count"]))
        event_df["service_need_norm"] = 0.5 * nearest_norm + 0.5 * inverse_facility_norm
        event_df["damage_priority_pct"] = event_df["damage_norm"].rank(method="average", pct=True, ascending=True)
        parts.append(event_df)
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=grid.crs)


def add_scenario_scores(grid: gpd.GeoDataFrame, scenarios: list[dict]) -> gpd.GeoDataFrame:
    grid = grid.copy()
    for scenario in scenarios:
        score = pd.Series(np.zeros(len(grid)), index=grid.index, dtype=float)
        for indicator, weight in scenario["weights"].items():
            if indicator not in grid.columns:
                raise ValueError(f"Missing indicator column for scenario {scenario['name']}: {indicator}")
            score += grid[indicator] * weight
        score_col = f"score_{scenario['name']}"
        pct_col = f"priority_pct_{scenario['name']}"
        gap_col = f"underestimation_gap_{scenario['name']}"
        top_col = f"top_need_{scenario['name']}"
        grid[score_col] = score
        grid[pct_col] = grid.groupby("event")[score_col].rank(method="average", pct=True, ascending=True)
        grid[gap_col] = grid[pct_col] - grid["damage_priority_pct"]
        grid[top_col] = False
        for event, idx in grid.groupby("event").groups.items():
            event_idx = list(idx)
            top_cut = grid.loc[event_idx, pct_col].quantile(0.80)
            grid.loc[event_idx, top_col] = grid.loc[event_idx, pct_col] >= top_cut
    grid["top_damage"] = False
    for event, idx in grid.groupby("event").groups.items():
        event_idx = list(idx)
        top_cut = grid.loc[event_idx, "damage_priority_pct"].quantile(0.80)
        grid.loc[event_idx, "top_damage"] = grid.loc[event_idx, "damage_priority_pct"] >= top_cut
    need_top_cols = [f"top_need_{scenario['name']}" for scenario in scenarios]
    grid["need_top_scenario_count"] = grid[need_top_cols].sum(axis=1)
    gap_cols = [f"underestimation_gap_{scenario['name']}" for scenario in scenarios]
    grid["max_underestimation_gap"] = grid[gap_cols].max(axis=1)
    grid["mean_underestimation_gap"] = grid[gap_cols].mean(axis=1)
    grid["stable_mismatch"] = (grid["need_top_scenario_count"] >= 2) & (~grid["top_damage"])
    return grid


def scenario_metrics(grid: gpd.GeoDataFrame, scenarios: list[dict]) -> pd.DataFrame:
    rows = []
    for event, event_df in grid.groupby("event", sort=True):
        damage_top = set(event_df.loc[event_df["top_damage"], "cell_id"])
        for scenario in scenarios:
            name = scenario["name"]
            need_top = set(event_df.loc[event_df[f"top_need_{name}"], "cell_id"])
            overlap = damage_top & need_top
            union = damage_top | need_top
            rho, p_value = spearmanr(event_df["damage_norm"], event_df[f"score_{name}"])
            mismatch = event_df[event_df[f"top_need_{name}"] & (~event_df["top_damage"])]
            rows.append(
                {
                    "event": event,
                    "scenario": name,
                    "cells": int(len(event_df)),
                    "top_damage_count": int(len(damage_top)),
                    "top_need_count": int(len(need_top)),
                    "top_overlap_count": int(len(overlap)),
                    "top_jaccard": float(len(overlap) / len(union)) if union else np.nan,
                    "high_need_low_damage_count": int(len(mismatch)),
                    "high_need_low_damage_share": float(len(mismatch) / len(event_df)),
                    "spearman_damage_vs_need": float(rho) if not np.isnan(rho) else np.nan,
                    "spearman_p_value": float(p_value) if not np.isnan(p_value) else np.nan,
                    "mean_underestimation_gap_for_mismatch": float(mismatch[f"underestimation_gap_{name}"].mean()) if len(mismatch) else 0.0,
                    "mismatch_population_sum": float(mismatch["worldpop_population"].sum()),
                    "mismatch_mean_damage_D": float(mismatch["damage_index_D"].mean()) if len(mismatch) else 0.0,
                }
            )
    return pd.DataFrame(rows)


def event_summary(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for event, event_df in grid.groupby("event", sort=True):
        stable = event_df[event_df["stable_mismatch"]]
        rows.append(
            {
                "event": event,
                "cells": int(len(event_df)),
                "stable_mismatch_count": int(len(stable)),
                "stable_mismatch_share": float(len(stable) / len(event_df)),
                "stable_mismatch_population_sum": float(stable["worldpop_population"].sum()),
                "stable_mismatch_mean_damage_D": float(stable["damage_index_D"].mean()) if len(stable) else 0.0,
                "stable_mismatch_median_road_density": float(stable["road_density_m_per_km2"].median()) if len(stable) else 0.0,
                "stable_mismatch_median_nearest_facility_m": float(stable["nearest_facility_m"].median()) if len(stable) else 0.0,
                "event_population_sum": float(event_df["worldpop_population"].sum()),
                "event_mean_damage_D": float(event_df["damage_index_D"].mean()),
            }
        )
    return pd.DataFrame(rows)


def write_outputs(grid: gpd.GeoDataFrame, metrics: pd.DataFrame, summary: pd.DataFrame, out_dir: Path, scenarios: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    grid.to_file(out_dir / "priority_mismatch_grid_500m.geojson", driver="GeoJSON")
    grid.drop(columns="geometry").to_csv(out_dir / "priority_mismatch_grid_500m.csv", index=False)
    metrics.to_csv(out_dir / "scenario_rank_metrics.csv", index=False)
    summary.to_csv(out_dir / "event_mismatch_summary.csv", index=False)
    stable_cols = [
        "event",
        "cell_id",
        "damage_index_D",
        "worldpop_population",
        "road_density_m_per_km2",
        "facility_count",
        "nearest_facility_m",
        "damage_priority_pct",
        "need_top_scenario_count",
        "max_underestimation_gap",
        "mean_underestimation_gap",
        "cell_center_lon",
        "cell_center_lat",
    ]
    grid.loc[grid["stable_mismatch"], stable_cols].sort_values(
        ["event", "max_underestimation_gap"],
        ascending=[True, False],
    ).to_csv(out_dir / "stable_mismatch_cells.csv", index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/05_analyze_priority_mismatch.py",
        "scenarios": scenarios,
        "stable_mismatch_definition": "top 20% multi-source priority in at least two scenarios and outside top 20% damage-only priority",
        "outputs": [
            "priority_mismatch_grid_500m.csv",
            "priority_mismatch_grid_500m.geojson",
            "scenario_rank_metrics.csv",
            "event_mismatch_summary.csv",
            "stable_mismatch_cells.csv",
        ],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grid", required=True, type=Path)
    parser.add_argument("--weights-config", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = load_scenarios(args.weights_config)
    grid = gpd.read_file(args.input_grid)
    grid = add_indicators(grid)
    grid = add_scenario_scores(grid, scenarios)
    metrics = scenario_metrics(grid, scenarios)
    summary = event_summary(grid)
    write_outputs(grid, metrics, summary, args.out_dir, scenarios)
    print(f"rows={len(grid)}")
    print(f"stable_mismatch={int(grid['stable_mismatch'].sum())}")
    print(f"event_summary={args.out_dir / 'event_mismatch_summary.csv'}")
    print(f"scenario_metrics={args.out_dir / 'scenario_rank_metrics.csv'}")


if __name__ == "__main__":
    main()
