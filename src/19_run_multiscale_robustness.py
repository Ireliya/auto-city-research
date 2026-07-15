#!/usr/bin/env python3
"""Rebuild and compare the need audit at 250 m, 500 m, and 1000 m."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
import seaborn as sns
import yaml
from PIL import Image

from evidence_utils import (
    INDICATOR_COLUMNS,
    add_need_indicators,
    add_scenario_scores,
    exact_stable_mismatch,
    load_need_scenarios,
    require_finite,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildings-csv", type=Path, default=Path("data/derived/xbd_core_v1/xbd_buildings.csv"))
    parser.add_argument("--weights-config", type=Path, default=Path("configs/weight_scenarios.yaml"))
    parser.add_argument("--experiment-config", type=Path, default=Path("configs/evidence_hardening.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/multiscale_v1"))
    parser.add_argument("--figure-dir", type=Path, default=Path("reports/figures"))
    parser.add_argument("--worldpop-raw-dir", type=Path, default=Path("data/raw/worldpop_rasters"))
    parser.add_argument("--osm-cache-dir", type=Path, default=Path("data/derived/osm_context_v1/osmnx_cache"))
    parser.add_argument("--cell-sizes", default="", help="Optional comma-separated override")
    parser.add_argument(
        "--skip-preparation",
        action="store_true",
        help="Analyze already prepared worldpop_<scale>m joined grids in --out-dir.",
    )
    return parser.parse_args()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def run_command(command: list[str]) -> tuple[str, str]:
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout[-4000:]}\nstderr:\n{result.stderr[-4000:]}"
        )
    return result.stdout, result.stderr


def validate_osm_fetch(log_path: Path) -> None:
    fetch = pd.read_csv(log_path)
    road_ok = fetch["road_status"].isin(["ok", "ok_no_intersections", "empty"])
    facility_ok = fetch["facility_status"].isin(["ok", "empty"])
    if not (road_ok & facility_ok).all():
        failed = fetch.loc[~(road_ok & facility_ok), ["event", "road_status", "facility_status", "error"]]
        raise RuntimeError("OSM source retrieval failed:\n" + failed.to_string(index=False))


def prepare_scales(args: argparse.Namespace, cell_sizes: list[int]) -> list[dict]:
    damage_dir = args.out_dir / "damage"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    logs: list[dict] = []
    command = [
        sys.executable,
        "src/02_build_xbd_damage_grid.py",
        "--buildings-csv",
        str(args.buildings_csv),
        "--out-dir",
        str(damage_dir),
        "--cell-sizes",
        ",".join(str(size) for size in cell_sizes),
    ]
    run_command(command)
    footprints = damage_dir / "event_footprints.csv"

    for cell_m in cell_sizes:
        entry: dict[str, object] = {
            "cell_m": cell_m,
            "status": "started",
            "error": "",
        }
        try:
            damage_grid = damage_dir / f"damage_grid_{cell_m}m.geojson"
            osm_dir = args.out_dir / f"osm_{cell_m}m"
            osm_command = [
                sys.executable,
                "src/03_fetch_osm_context.py",
                "--damage-grid",
                str(damage_grid),
                "--footprints-csv",
                str(footprints),
                "--out-dir",
                str(osm_dir),
                "--cell-m",
                str(cell_m),
                "--cache-dir",
                str(args.osm_cache_dir),
            ]
            run_command(osm_command)
            validate_osm_fetch(osm_dir / "osm_fetch_log.csv")

            worldpop_dir = args.out_dir / f"worldpop_{cell_m}m"
            worldpop_command = [
                sys.executable,
                "src/04_join_worldpop_population.py",
                "--input-grid",
                str(osm_dir / f"damage_osm_grid_{cell_m}m.geojson"),
                "--out-dir",
                str(worldpop_dir),
                "--raw-dir",
                str(args.worldpop_raw_dir),
                "--cell-m",
                str(cell_m),
                "--mode",
                "raster-download",
                "--worldpop-resolution",
                "1km_ua",
            ]
            run_command(worldpop_command)
            entry["status"] = "complete"
            entry["joined_grid"] = display_path(
                worldpop_dir / f"damage_osm_worldpop_grid_{cell_m}m.geojson"
            )
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)[-4000:]
            if cell_m != 250:
                logs.append(entry)
                pd.DataFrame(logs).to_csv(args.out_dir / "preparation_log.csv", index=False)
                raise
        logs.append(entry)
        pd.DataFrame(logs).to_csv(args.out_dir / "preparation_log.csv", index=False)
    return logs


def analyze_scales(
    args: argparse.Namespace,
    cell_sizes: list[int],
    top_shares: list[float],
    scenarios: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    summary_rows: list[dict] = []
    cell_rows: list[dict] = []
    completed: list[int] = []

    for cell_m in cell_sizes:
        grid_path = args.out_dir / f"worldpop_{cell_m}m" / f"damage_osm_worldpop_grid_{cell_m}m.geojson"
        if not grid_path.exists():
            if cell_m == 250:
                continue
            raise FileNotFoundError(f"Required multiscale grid is missing: {grid_path}")
        grid = gpd.read_file(grid_path)
        prepared = add_need_indicators(pd.DataFrame(grid.drop(columns="geometry")), "damage_index_D")
        prepared = add_scenario_scores(prepared, scenarios)
        require_finite(prepared, INDICATOR_COLUMNS, f"{cell_m}m need indicators")
        completed.append(cell_m)

        for event, event_df in prepared.groupby("event", sort=True):
            event_df = event_df.copy()
            for top_share in top_shares:
                mismatch, scenario_counts, k = exact_stable_mismatch(
                    event_df,
                    damage_column="damage_index_D",
                    scenarios=scenarios,
                    top_share=top_share,
                )
                stable = event_df.loc[mismatch]
                cell_area_km2 = (cell_m * cell_m) / 1_000_000.0
                summary_rows.append(
                    {
                        "event": event,
                        "cell_m": cell_m,
                        "top_share": top_share,
                        "cells": int(len(event_df)),
                        "exact_budget_k": k,
                        "study_grid_area_km2": float(len(event_df) * cell_area_km2),
                        "stable_mismatch_count": int(mismatch.sum()),
                        "stable_mismatch_share": float(mismatch.mean()),
                        "stable_mismatch_area_km2": float(mismatch.sum() * cell_area_km2),
                        "stable_mismatch_area_share": float(mismatch.mean()),
                        "stable_mismatch_population_sum": float(stable["worldpop_population"].sum()),
                    }
                )
                if abs(top_share - 0.20) < 1e-9:
                    for row_index, source in event_df.iterrows():
                        cell_rows.append(
                            {
                                "event": event,
                                "cell_m": cell_m,
                                "cell_id": str(source["cell_id"]),
                                "stable_mismatch": bool(mismatch.loc[row_index]),
                                "need_top_scenario_count": int(scenario_counts.loc[row_index]),
                                "cell_area_km2": cell_area_km2,
                                "damage_index_D": float(source["damage_index_D"]),
                                "worldpop_population": float(source["worldpop_population"]),
                                "road_density_m_per_km2": float(source["road_density_m_per_km2"]),
                                "facility_count": int(source["facility_count"]),
                                "cell_center_lon": float(source["cell_center_lon"]),
                                "cell_center_lat": float(source["cell_center_lat"]),
                            }
                        )
    return pd.DataFrame(summary_rows), pd.DataFrame(cell_rows), completed


def make_figure(summary: pd.DataFrame, figure_dir: Path) -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.9)
    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42, "ps.fonttype": 42})
    figure_dir.mkdir(parents=True, exist_ok=True)
    top20 = summary[summary["top_share"].round(2) == 0.20].copy()
    top20["event_label"] = top20["event"].map(EVENT_LABELS).fillna(top20["event"])

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.3), constrained_layout=True)
    sns.lineplot(
        data=top20,
        x="cell_m",
        y="stable_mismatch_area_km2",
        hue="event_label",
        marker="o",
        palette="colorblind",
        ax=axes[0],
    )
    axes[0].set_title("a  Mismatch area across grid scales")
    axes[0].set_xlabel("Grid size (m)")
    axes[0].set_ylabel("Mismatch grid area (km2)")
    axes[0].set_xticks(sorted(top20["cell_m"].unique()))
    axes[0].legend(title="", fontsize=7)

    sns.lineplot(
        data=top20,
        x="cell_m",
        y="stable_mismatch_area_share",
        hue="event_label",
        marker="o",
        palette="colorblind",
        legend=False,
        ax=axes[1],
    )
    axes[1].set_title("b  Mismatch share across grid scales")
    axes[1].set_xlabel("Grid size (m)")
    axes[1].set_ylabel("Share of analyzed cells")
    axes[1].set_xticks(sorted(top20["cell_m"].unique()))
    for ax in axes:
        ax.grid(axis="y", color="0.88", linewidth=0.6)
        ax.grid(axis="x", visible=False)

    png = figure_dir / "fig9_multiscale_robustness.png"
    pdf = figure_dir / "fig9_multiscale_robustness.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    Image.open(png).convert("L").convert("RGB").save(
        figure_dir / "fig9_multiscale_robustness_grayscale.png"
    )


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.experiment_config.read_text(encoding="utf-8"))
    configured_sizes = [int(value) for value in config["multiscale"]["cell_sizes_m"]]
    cell_sizes = [int(value.strip()) for value in args.cell_sizes.split(",") if value.strip()] or configured_sizes
    top_shares = [float(value) for value in config["top_shares"]]
    scenarios = load_need_scenarios(args.weights_config)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    preparation = [] if args.skip_preparation else prepare_scales(args, cell_sizes)
    summary, cells, completed = analyze_scales(args, cell_sizes, top_shares, scenarios)
    summary.to_csv(args.out_dir / "multiscale_event_summary.csv", index=False)
    cells.to_csv(args.out_dir / "multiscale_cell_or_area_summary.csv", index=False)
    make_figure(summary, args.figure_dir)

    if 500 in completed:
        legacy_total = int(
            summary.loc[
                (summary["cell_m"] == 500) & (summary["top_share"].round(2) == 0.20),
                "stable_mismatch_count",
            ].sum()
        )
        if legacy_total != 109:
            raise AssertionError(f"500m exact top-20 result changed: expected 109, got {legacy_total}")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/19_run_multiscale_robustness.py",
        "cell_sizes_requested_m": cell_sizes,
        "cell_sizes_completed_m": completed,
        "top_shares": top_shares,
        "ranking_rule": "exact top-k; high need in at least two fixed scenarios and outside damage-only top-k",
        "source_rebuild": "Each scale is rebuilt from building-level xBD records, OSM roads/facilities, and WorldPop rasters.",
        "preparation": preparation,
        "outputs": [
            "multiscale_event_summary.csv",
            "multiscale_cell_or_area_summary.csv",
            "preparation_log.csv",
            "reports/figures/fig9_multiscale_robustness.png",
            "reports/figures/fig9_multiscale_robustness.pdf",
        ],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    top20 = summary[summary["top_share"].round(2) == 0.20]
    print(top20[["event", "cell_m", "cells", "stable_mismatch_count", "stable_mismatch_area_km2"]].to_string(index=False))
    print(f"completed_scales={completed}")
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
