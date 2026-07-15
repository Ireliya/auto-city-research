#!/usr/bin/env python3
"""Verify published headline and Stage 2 evidence tables."""

from __future__ import annotations

from pathlib import Path

import numpy as np
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
        raise FileNotFoundError(f"Missing {path}. Run `python scripts/download_data.py` first.")
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

    evidence = pd.read_csv(require("data/derived/evidence_hardening_v1/baseline_event_summary.csv"))
    weights = pd.read_csv(require("data/derived/evidence_hardening_v1/weight_uncertainty_event_summary.csv"))
    current_top20 = evidence[
        (evidence["baseline"] == "damage_index_D") & (evidence["top_share"].round(2) == 0.20)
    ]
    assert_equal("stage2_current_baseline_top20_total", int(current_top20["stable_mismatch_count"].sum()), 109)
    assert_equal("stage2_baseline_summary_rows", len(evidence), 80)
    assert_equal("stage2_weight_summary_rows", len(weights), 40)
    if weights.select_dtypes("number").isna().any().any():
        raise AssertionError("Stage 2 weight summary contains NaN values")

    multiscale = pd.read_csv(require("data/derived/multiscale_v1/multiscale_event_summary.csv"))
    scale_500 = multiscale[
        (multiscale["cell_m"] == 500) & (multiscale["top_share"].round(2) == 0.20)
    ]
    assert_equal("multiscale_500m_top20_total", int(scale_500["stable_mismatch_count"].sum()), 109)
    completed_scales = sorted(multiscale["cell_m"].unique().tolist())
    if completed_scales != [250, 500, 1000]:
        raise AssertionError(f"multiscale_completed_m: expected [250, 500, 1000], got {completed_scales}")
    print("multiscale_completed_m:", completed_scales)

    nfip = pd.read_csv(require("data/derived/harvey_external_validation_v1/harvey_nfip_tract_outcomes.csv"))
    metrics = pd.read_csv(
        require("data/derived/harvey_external_validation_v1/harvey_external_validation_metrics.csv")
    )
    bootstrap = pd.read_csv(
        require("data/derived/harvey_external_validation_v1/harvey_external_validation_bootstrap.csv")
    )
    assert_equal("harvey_nfip_intersecting_tracts", len(nfip), 149)
    assert_equal("harvey_nfip_claims", int(nfip["claim_count"].sum()), 10_134)
    for name, frame in [("metrics", metrics), ("bootstrap", bootstrap)]:
        numeric = frame.select_dtypes(include="number").to_numpy()
        if not np.isfinite(numeric).all():
            raise AssertionError(f"Harvey NFIP {name} contains NaN or infinite values")

    print("smoke reproduction OK")


if __name__ == "__main__":
    main()
