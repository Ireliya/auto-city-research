#!/usr/bin/env python3
"""Verify headline reproducibility numbers from downloaded derived tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


EXPECTED = {
    "xbd_buildings_rows": 99_629,
    "damage_grid_cells": 1_448,
    "primary_stable_mismatch_total": 67,
    "strict_top20_stable_mismatch_total": 109,
    "osm_building_polygons_total": 813_352,
}


def require(path: str) -> Path:
    target = ROOT / path
    if not target.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run `python scripts/download_data.py` from the repository root first."
        )
    return target


def assert_equal(name: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}")
    print(f"{name}: {actual}")


def main() -> None:
    buildings = pd.read_csv(require("data/derived/xbd_core_v1/xbd_buildings.csv"), low_memory=False)
    damage_grid = pd.read_csv(require("data/derived/xbd_damage_grid_v1/damage_grid_500m.csv"))
    primary = pd.read_csv(require("data/derived/priority_mismatch_v1/event_mismatch_summary.csv"))
    strict = pd.read_csv(require("data/derived/strict_budget_v1/strict_budget_event_summary.csv"))
    osm_fetch = pd.read_csv(require("data/derived/osm_building_form_v1/osm_building_fetch_log.csv"))

    assert_equal("xbd_buildings_rows", len(buildings), EXPECTED["xbd_buildings_rows"])
    assert_equal("damage_grid_cells", len(damage_grid), EXPECTED["damage_grid_cells"])
    assert_equal(
        "primary_stable_mismatch_total",
        int(primary["stable_mismatch_count"].sum()),
        EXPECTED["primary_stable_mismatch_total"],
    )

    strict_top20 = strict[strict["top_share"].round(2) == 0.20]
    assert_equal(
        "strict_top20_stable_mismatch_total",
        int(strict_top20["strict_stable_mismatch_count"].sum()),
        EXPECTED["strict_top20_stable_mismatch_total"],
    )
    assert_equal(
        "osm_building_polygons_total",
        int(osm_fetch["polygon_features"].sum()),
        EXPECTED["osm_building_polygons_total"],
    )

    print("smoke reproduction OK")


if __name__ == "__main__":
    main()
