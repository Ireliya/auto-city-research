#!/usr/bin/env python3
"""Regenerate Figures 1-12 from fixed derived tables without rerunning experiments."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))


def load_script(filename: str, alias: str):
    path = SRC_DIR / filename
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import plotting module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--figure-dir",
        type=Path,
        default=PROJECT_ROOT / "reports" / "figures",
        help="Directory for SVG, PDF, PNG, and grayscale PNG outputs.",
    )
    parser.add_argument(
        "--no-basemap",
        action="store_true",
        help="Regenerate Figure 4 without the cached/online CARTO-OSM basemap.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    figures = load_script("07_make_result_figures.py", "project_figures_07")
    maps = load_script("08_make_case_maps.py", "project_figures_08")
    robustness = load_script("11_run_robustness_checks.py", "project_figures_11")
    strict = load_script("15_run_strict_budget_check.py", "project_figures_15")
    osm_form = load_script("17_fetch_osm_building_form.py", "project_figures_17")
    baseline = load_script("18_run_baseline_weight_robustness.py", "project_figures_18")
    multiscale = load_script("19_run_multiscale_robustness.py", "project_figures_19")
    nfip = load_script("20_validate_harvey_nfip.py", "project_figures_20")
    final_evidence = load_script("25_make_final_evidence_figures.py", "project_figures_25")

    figures.setup_style()
    figures.figure_event_summary(
        pd.read_csv(PROJECT_ROOT / "data/derived/priority_mismatch_100m_v1/event_mismatch_summary.csv"),
        args.figure_dir,
    )
    figures.figure_scenario_heatmaps(
        pd.read_csv(PROJECT_ROOT / "data/derived/priority_mismatch_100m_v1/scenario_rank_metrics.csv"),
        args.figure_dir,
    )
    figures.figure_driver_profile(
        pd.read_csv(PROJECT_ROOT / "data/derived/mismatch_drivers_100m_v1/mismatch_driver_profile.csv"),
        args.figure_dir,
    )

    maps.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/priority_mismatch_100m_v1/priority_mismatch_grid_500m.csv"),
        args.figure_dir,
        "fig4_case_map_mismatch",
        PROJECT_ROOT / "data/cache/contextily",
        use_basemap=not args.no_basemap,
    )

    robustness.setup_style()
    robustness.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/robustness_100m_v1/threshold_sensitivity.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/robustness_100m_v1/scenario_stability_top20.csv"),
        args.figure_dir,
    )
    strict.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/strict_budget_100m_v1/strict_budget_event_summary.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/priority_mismatch_100m_v1/event_mismatch_summary.csv"),
        args.figure_dir,
    )
    osm_form.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/osm_building_form_100m_v1/osm_building_urban_form_profile.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/osm_building_form_100m_v1/osm_building_xbd_area_correlation.csv"),
        args.figure_dir,
    )
    baseline.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/evidence_hardening_100m_v1/baseline_event_summary.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/evidence_hardening_100m_v1/weight_uncertainty_event_summary.csv"),
        args.figure_dir,
    )
    multiscale.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/multiscale_100m_v1/multiscale_event_summary.csv"),
        args.figure_dir,
    )
    nfip.make_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/harvey_external_validation_v1/harvey_external_validation_metrics.csv"),
        args.figure_dir,
    )
    final_evidence.make_consensus_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/final_consensus_v1/final_consensus_all_cells.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/historical_osm_v1/historical_osm_event_summary.csv"),
        args.figure_dir,
    )
    final_evidence.make_external_proxy_figure(
        pd.read_csv(PROJECT_ROOT / "data/derived/external_proxies_v1/external_proxy_rank_metrics.csv"),
        pd.read_csv(PROJECT_ROOT / "data/derived/harvey_external_validation_v1/harvey_external_validation_metrics.csv"),
        args.figure_dir,
    )

    expected = []
    for index in range(1, 13):
        matches = list(args.figure_dir.glob(f"fig{index}_*.svg"))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one editable SVG for Figure {index}, found {len(matches)}")
        expected.append(matches[0])
    print(f"publication_figures={len(expected)}")
    print(f"figure_dir={args.figure_dir}")


if __name__ == "__main__":
    main()
