#!/usr/bin/env python3
"""Verify the published headline and final evidence tables."""

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
    "primary_100m_stable_mismatch_total": 73,
    "strict_100m_top20_stable_mismatch_total": 115,
    "final_consensus_candidates": 4,
}
EXPECTED_CANDIDATES = {
    ("mexico-earthquake", "mexico-earthquake_500m_3_38"),
    ("mexico-earthquake", "mexico-earthquake_500m_17_2"),
    ("mexico-earthquake", "mexico-earthquake_500m_17_3"),
    ("mexico-earthquake", "mexico-earthquake_500m_18_3"),
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


def assert_strict_budgets(frame: pd.DataFrame, label: str) -> None:
    expected = np.ceil(frame["cells"] * frame["top_share"]).astype(int)
    actual = frame["strict_budget_k"].astype(int)
    if not actual.equals(expected):
        raise AssertionError(f"{label}: strict budget does not equal ceil(cells * top_share)")
    print(f"{label}_strict_budget_rows:", len(frame))


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
    assert_strict_budgets(strict, "comparison")
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
    assert_equal("comparison_baseline_top20_total", int(current_top20["stable_mismatch_count"].sum()), 109)
    assert_equal("evidence_baseline_summary_rows", len(evidence), 80)
    assert_equal("evidence_weight_summary_rows", len(weights), 40)
    if weights.select_dtypes("number").isna().any().any():
        raise AssertionError("Weight-uncertainty summary contains NaN values")

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

    primary_100m = pd.read_csv(
        require("data/derived/priority_mismatch_100m_v1/event_mismatch_summary.csv")
    )
    strict_100m = pd.read_csv(
        require("data/derived/strict_budget_100m_v1/strict_budget_event_summary.csv")
    )
    assert_equal(
        "primary_100m_stable_mismatch_total",
        int(primary_100m["stable_mismatch_count"].sum()),
        EXPECTED["primary_100m_stable_mismatch_total"],
    )
    assert_equal(
        "strict_100m_top20_stable_mismatch_total",
        int(
            strict_100m.loc[
                strict_100m["top_share"].round(2) == 0.20,
                "strict_stable_mismatch_count",
            ].sum()
        ),
        EXPECTED["strict_100m_top20_stable_mismatch_total"],
    )
    assert_strict_budgets(strict_100m, "primary_100m")

    population_audit = pd.read_csv(
        require("data/derived/population_resolution_audit_v1/population_resolution_event_audit.csv")
    )
    assert_equal("population_resolution_events", len(population_audit), 4)
    if population_audit["quality_status"].str.lower().eq("fail").any():
        raise AssertionError("WorldPop population-resolution audit contains a failed event")

    historical = pd.read_csv(
        require("data/derived/historical_osm_v1/historical_osm_event_summary.csv")
    )
    expected_historical = {
        "hurricane-harvey": "not_assessable",
        "mexico-earthquake": "does_not_support",
        "palu-tsunami": "does_not_support",
        "santa-rosa-wildfire": "support",
    }
    actual_historical = dict(zip(historical["event"], historical["temporal_evidence"]))
    if actual_historical != expected_historical:
        raise AssertionError(
            f"historical OSM status mismatch: expected {expected_historical}, got {actual_historical}"
        )
    print("historical_osm_statuses:", actual_historical)

    proxy_metrics = pd.read_csv(
        require("data/derived/external_proxies_v1/external_proxy_rank_metrics.csv")
    )
    if len(proxy_metrics) < 1000:
        raise AssertionError(f"external proxy metric rows: expected at least 1000, got {len(proxy_metrics)}")
    if not np.isfinite(proxy_metrics[["value", "ci_low", "ci_high", "units"]].to_numpy()).all():
        raise AssertionError("external proxy metrics contain NaN or infinite values")

    candidates = pd.read_csv(
        require("data/derived/final_consensus_v1/final_consensus_candidates.csv")
    )
    event_summary = pd.read_csv(
        require("data/derived/final_consensus_v1/final_consensus_event_summary.csv")
    )
    actual_candidates = set(
        map(tuple, candidates[["event", "cell_id"]].astype(str).to_numpy())
    )
    if actual_candidates != EXPECTED_CANDIDATES:
        raise AssertionError(
            f"final candidate mismatch: expected {sorted(EXPECTED_CANDIDATES)}, got {sorted(actual_candidates)}"
        )
    assert_equal(
        "final_consensus_candidates",
        len(candidates),
        EXPECTED["final_consensus_candidates"],
    )
    gate_failures = candidates[
        (candidates["baseline_support_1km"] < 3)
        | (candidates["baseline_support_100m"] < 3)
        | (candidates["policy_probability_1km"] < 0.80)
        | (candidates["policy_probability_100m"] < 0.80)
        | (candidates["population_resolutions_supported"] < 2)
        | (candidates["spatial_scales_supported"] < 2)
        | ~candidates["high_confidence_disagreement"].astype(bool)
    ]
    if not gate_failures.empty:
        raise AssertionError(
            f"final candidates fail fixed gates: {gate_failures['cell_id'].tolist()}"
        )
    print("final_candidate_fixed_gates: pass")
    assert_equal(
        "temporally_supported_final_candidates",
        int(event_summary["temporally_supported_high_confidence_cells"].sum()),
        0,
    )

    print("smoke reproduction OK")


if __name__ == "__main__":
    main()
