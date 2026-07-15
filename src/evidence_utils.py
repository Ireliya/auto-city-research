#!/usr/bin/env python3
"""Shared deterministic ranking helpers for Stage 2 evidence experiments."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


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


def load_need_scenarios(path: Path) -> list[dict]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios: list[dict] = []
    for item in config.get("active_scenarios", []):
        if item.get("name") == "damage_only_baseline":
            continue
        weights = {str(key): float(value) for key, value in item.get("weights", {}).items()}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError(f"Scenario has nonpositive weight sum: {item.get('name')}")
        missing = sorted(set(INDICATOR_COLUMNS) - set(weights))
        if missing:
            raise ValueError(f"Scenario {item.get('name')} is missing indicators: {missing}")
        scenarios.append(
            {
                "name": str(item["name"]),
                "role": str(item.get("role", "")),
                "weights": {key: value / total for key, value in weights.items()},
            }
        )
    if not scenarios:
        raise ValueError("No active need-aware scenarios found")
    return scenarios


def add_need_indicators(frame: pd.DataFrame, damage_column: str = "damage_index_D") -> pd.DataFrame:
    required = [
        damage_column,
        "worldpop_population",
        "road_density_m_per_km2",
        "facility_count",
        "nearest_facility_m",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns for need indicators: {missing}")

    parts: list[pd.DataFrame] = []
    for _, event_df in frame.groupby("event", sort=True):
        event_df = event_df.copy()
        damage = pd.to_numeric(event_df[damage_column], errors="coerce").fillna(0.0)
        population = pd.to_numeric(event_df["worldpop_population"], errors="coerce").fillna(0.0)
        roads = pd.to_numeric(event_df["road_density_m_per_km2"], errors="coerce").fillna(0.0)
        facilities = pd.to_numeric(event_df["facility_count"], errors="coerce").fillna(0.0)
        nearest = pd.to_numeric(event_df["nearest_facility_m"], errors="coerce")
        nearest_fill = nearest.max(skipna=True)
        nearest = nearest.fillna(0.0 if pd.isna(nearest_fill) else nearest_fill)

        event_df["damage_norm"] = minmax(damage)
        event_df["population_norm"] = minmax(np.log1p(population))
        event_df["accessibility_need_norm"] = minmax(-np.log1p(roads))
        event_df["service_need_norm"] = 0.5 * minmax(nearest) + 0.5 * minmax(-np.log1p(facilities))
        parts.append(event_df)
    return pd.concat(parts, ignore_index=True)


def add_scenario_scores(frame: pd.DataFrame, scenarios: list[dict]) -> pd.DataFrame:
    result = frame.copy()
    for scenario in scenarios:
        score = pd.Series(np.zeros(len(result)), index=result.index, dtype=float)
        for indicator, weight in scenario["weights"].items():
            score += pd.to_numeric(result[indicator], errors="coerce").fillna(0.0) * float(weight)
        result[f"score_{scenario['name']}"] = score
    return result


def exact_top_ids(
    frame: pd.DataFrame,
    score_column: str,
    top_share: float,
    tie_columns: list[str] | None = None,
) -> set[str]:
    if not 0 < top_share <= 1:
        raise ValueError(f"top_share must be in (0, 1]: {top_share}")
    k = int(math.ceil(len(frame) * top_share))
    columns = [score_column]
    ascending = [False]
    for column in tie_columns or []:
        if column in frame.columns and column not in columns:
            columns.append(column)
            ascending.append(column == "cell_id")
    if "cell_id" not in columns:
        columns.append("cell_id")
        ascending.append(True)
    ranked = frame.sort_values(columns, ascending=ascending, kind="mergesort")
    return set(ranked.head(k)["cell_id"].astype(str))


def exact_stable_mismatch(
    event_df: pd.DataFrame,
    damage_column: str,
    scenarios: list[dict],
    top_share: float,
) -> tuple[pd.Series, pd.Series, int]:
    k = int(math.ceil(len(event_df) * top_share))
    damage_top = exact_top_ids(
        event_df,
        damage_column,
        top_share,
        tie_columns=["damaged_building_count", "severe_building_count", "damage_weighted_area_m2"],
    )
    counts = pd.Series(np.zeros(len(event_df), dtype=int), index=event_df.index)
    for scenario in scenarios:
        top_ids = exact_top_ids(
            event_df,
            f"score_{scenario['name']}",
            top_share,
            tie_columns=[damage_column, "worldpop_population"],
        )
        counts += event_df["cell_id"].astype(str).isin(top_ids).astype(int)
    damage_mask = event_df["cell_id"].astype(str).isin(damage_top)
    mismatch = (counts >= 2) & (~damage_mask)
    return mismatch, counts, k


def require_finite(frame: pd.DataFrame, columns: list[str], context: str) -> None:
    values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"Non-finite values found in {context}: {columns}")

