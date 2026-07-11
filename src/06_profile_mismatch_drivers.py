#!/usr/bin/env python3
"""Profile variables associated with stable priority mismatch cells."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


DRIVER_VARIABLES = [
    ("worldpop_population", "population_exposure"),
    ("population_density_per_km2", "population_density"),
    ("road_density_m_per_km2", "road_accessibility"),
    ("nearest_facility_m", "facility_distance"),
    ("facility_count", "facility_count"),
    ("building_count", "building_count"),
    ("total_area_m2", "building_area"),
    ("damaged_building_share", "damaged_building_share"),
    ("severe_building_share", "severe_building_share"),
    ("damage_index_D", "damage_index"),
]


def safe_stats(series: pd.Series) -> dict:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return {"n": 0, "mean": np.nan, "median": np.nan, "std": np.nan}
    return {
        "n": int(len(values)),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
    }


def standardized_difference(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if pooled == 0 or np.isnan(pooled):
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def profile_group(df: pd.DataFrame, group_label: str) -> list[dict]:
    rows = []
    mismatch = df[df["stable_mismatch"].astype(bool)]
    other = df[~df["stable_mismatch"].astype(bool)]
    for column, label in DRIVER_VARIABLES:
        if column not in df.columns:
            continue
        m = safe_stats(mismatch[column])
        o = safe_stats(other[column])
        rows.append(
            {
                "group": group_label,
                "variable": column,
                "driver_label": label,
                "mismatch_n": m["n"],
                "other_n": o["n"],
                "mismatch_mean": m["mean"],
                "other_mean": o["mean"],
                "mean_difference": m["mean"] - o["mean"] if pd.notna(m["mean"]) and pd.notna(o["mean"]) else np.nan,
                "mean_ratio": m["mean"] / o["mean"] if pd.notna(m["mean"]) and pd.notna(o["mean"]) and o["mean"] != 0 else np.nan,
                "mismatch_median": m["median"],
                "other_median": o["median"],
                "median_difference": m["median"] - o["median"] if pd.notna(m["median"]) and pd.notna(o["median"]) else np.nan,
                "standardized_mean_difference": standardized_difference(mismatch[column], other[column]),
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grid", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.input_grid)
    if "stable_mismatch" not in df.columns:
        raise ValueError("Input grid must contain stable_mismatch")

    rows = profile_group(df, "all_events")
    for event, event_df in sorted(df.groupby("event")):
        rows.extend(profile_group(event_df, event))
    profile = pd.DataFrame(rows)
    profile.to_csv(args.out_dir / "mismatch_driver_profile.csv", index=False)

    event_counts = (
        df.groupby("event")
        .agg(
            cells=("cell_id", "count"),
            stable_mismatch_count=("stable_mismatch", "sum"),
            population_sum=("worldpop_population", "sum"),
            stable_mismatch_population_sum=("worldpop_population", lambda s: float(s[df.loc[s.index, "stable_mismatch"].astype(bool)].sum())),
        )
        .reset_index()
    )
    event_counts["stable_mismatch_share"] = event_counts["stable_mismatch_count"] / event_counts["cells"]
    event_counts.to_csv(args.out_dir / "mismatch_driver_event_counts.csv", index=False)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/06_profile_mismatch_drivers.py",
        "input_grid": str(args.input_grid),
        "driver_variables": DRIVER_VARIABLES,
        "interpretation_note": "Associational profile only; not a causal model.",
        "outputs": [
            "mismatch_driver_profile.csv",
            "mismatch_driver_event_counts.csv",
        ],
    }
    with (args.out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)

    print(f"profile={args.out_dir / 'mismatch_driver_profile.csv'}")
    print(f"event_counts={args.out_dir / 'mismatch_driver_event_counts.csv'}")
    print(f"stable_mismatch={int(df['stable_mismatch'].sum())}")


if __name__ == "__main__":
    main()
