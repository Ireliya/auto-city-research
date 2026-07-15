#!/usr/bin/env python3
"""Build the fixed-threshold, cross-resolution final disagreement audit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys

_proj_data = Path(sys.prefix) / "share" / "proj"
if _proj_data.exists():
    os.environ.setdefault("PROJ_DATA", str(_proj_data))

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import union_all
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOLUTIONS = ("1km", "100m")
SCALES = (250, 500, 1000)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/final_evidence.yaml"))
    parser.add_argument(
        "--priority-1km",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.geojson"),
    )
    parser.add_argument(
        "--priority-100m",
        type=Path,
        default=Path(
            "data/derived/priority_mismatch_100m_v1/priority_mismatch_grid_500m.geojson"
        ),
    )
    parser.add_argument(
        "--evidence-1km",
        type=Path,
        default=Path("data/derived/evidence_hardening_v1"),
    )
    parser.add_argument(
        "--evidence-100m",
        type=Path,
        default=Path("data/derived/evidence_hardening_100m_v1"),
    )
    parser.add_argument(
        "--multiscale-1km",
        type=Path,
        default=Path("data/derived/multiscale_v1"),
    )
    parser.add_argument(
        "--multiscale-100m",
        type=Path,
        default=Path("data/derived/multiscale_100m_v1"),
    )
    parser.add_argument(
        "--historical-osm",
        type=Path,
        default=Path("data/derived/historical_osm_v1"),
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("data/derived/final_consensus_v1")
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return path.name


def read_resolution_evidence(
    evidence_dir: Path,
    resolution: str,
    top_share: float,
    regime: str,
    minimum_baselines: int,
    minimum_probability: float,
) -> pd.DataFrame:
    baseline_path = evidence_dir / "baseline_cell_consensus.csv"
    weight_path = evidence_dir / "weight_uncertainty_cells.csv"
    baseline = pd.read_csv(baseline_path)
    weights = pd.read_csv(weight_path)
    baseline = baseline[np.isclose(baseline["top_share"], top_share)].copy()
    weights = weights[
        np.isclose(weights["top_share"], top_share) & weights["regime"].eq(regime)
    ].copy()
    if baseline.duplicated(["event", "cell_id"]).any():
        raise ValueError(f"Duplicate baseline cells in {baseline_path}")
    if weights.duplicated(["event", "cell_id"]).any():
        raise ValueError(f"Duplicate weight cells in {weight_path}")
    result = baseline[["event", "cell_id", "baselines_mismatch_count"]].merge(
        weights[["event", "cell_id", "mismatch_probability"]],
        on=["event", "cell_id"],
        how="outer",
        validate="one_to_one",
    )
    if result[["baselines_mismatch_count", "mismatch_probability"]].isna().any().any():
        raise ValueError(f"Incomplete baseline/weight join for {resolution}")
    result = result.rename(
        columns={
            "baselines_mismatch_count": f"baseline_support_{resolution}",
            "mismatch_probability": f"policy_probability_{resolution}",
        }
    )
    result[f"passes_baselines_{resolution}"] = (
        result[f"baseline_support_{resolution}"] >= minimum_baselines
    )
    result[f"passes_policy_{resolution}"] = (
        result[f"policy_probability_{resolution}"] >= minimum_probability
    )
    result[f"passes_resolution_{resolution}"] = (
        result[f"passes_baselines_{resolution}"] & result[f"passes_policy_{resolution}"]
    )
    return result


def read_scale_geometries(multiscale_dir: Path) -> dict[int, gpd.GeoDataFrame]:
    summary_path = multiscale_dir / "multiscale_cell_or_area_summary.csv"
    summary = pd.read_csv(summary_path)
    outputs: dict[int, gpd.GeoDataFrame] = {}
    for scale in SCALES:
        geometry_path = (
            multiscale_dir
            / f"worldpop_{scale}m"
            / f"damage_osm_worldpop_grid_{scale}m.geojson"
        )
        geometry = gpd.read_file(geometry_path)[["event", "cell_id", "geometry"]]
        flags = summary[summary["cell_m"].eq(scale)][
            ["event", "cell_id", "stable_mismatch"]
        ].copy()
        flags["stable_mismatch"] = flags["stable_mismatch"].astype(bool)
        merged = geometry.merge(
            flags,
            on=["event", "cell_id"],
            how="left",
            validate="one_to_one",
        )
        if merged["stable_mismatch"].isna().any():
            raise ValueError(f"Missing stable-mismatch flags for {geometry_path}")
        outputs[scale] = gpd.GeoDataFrame(merged, geometry="geometry", crs=geometry.crs)
    return outputs


def area_overlap_support(
    reference: gpd.GeoDataFrame,
    scale_cells: gpd.GeoDataFrame,
    minimum_overlap: float,
) -> pd.Series:
    support = pd.Series(False, index=reference.index, dtype=bool)
    for event, event_reference in reference.groupby("event", sort=True):
        mismatch = scale_cells[
            scale_cells["event"].eq(event) & scale_cells["stable_mismatch"]
        ].copy()
        if mismatch.empty:
            continue
        local_crs = event_reference.estimate_utm_crs()
        if local_crs is None:
            raise ValueError(f"Cannot estimate a projected CRS for {event}")
        reference_p = event_reference.to_crs(local_crs)
        mismatch_p = mismatch.to_crs(local_crs)
        mismatch_union = union_all(mismatch_p.geometry.to_numpy())
        ratios = reference_p.geometry.intersection(mismatch_union).area / reference_p.geometry.area
        support.loc[event_reference.index] = ratios.to_numpy() >= minimum_overlap
    return support


def add_temporal_evidence(
    cells: pd.DataFrame,
    historical_dir: Path,
) -> tuple[pd.DataFrame, dict[str, str], list[Path]]:
    grid_path = historical_dir / "historical_osm_grid_500m.csv"
    summary_path = historical_dir / "historical_osm_event_summary.csv"
    if not grid_path.exists() or not summary_path.exists():
        result = cells.copy()
        result["historical_osm_event_evidence"] = "not_assessable"
        result["historical_osm_cell_persistence"] = "not_assessable"
        statuses = {event: "not_assessable" for event in result["event"].unique()}
        return result, statuses, []
    historical_grid = pd.read_csv(grid_path)
    historical_summary = pd.read_csv(summary_path)
    statuses = dict(
        zip(
            historical_summary["event"].astype(str),
            historical_summary["temporal_evidence"].astype(str),
        )
    )
    keep = historical_grid[["event", "cell_id", "temporal_persistence"]].copy()
    keep["historical_osm_cell_persistence"] = np.where(
        keep["temporal_persistence"].isna(),
        "not_assessable",
        np.where(keep["temporal_persistence"].astype(bool), "support", "does_not_support"),
    )
    keep = keep.drop(columns="temporal_persistence")
    result = cells.merge(keep, on=["event", "cell_id"], how="left", validate="one_to_one")
    result["historical_osm_event_evidence"] = result["event"].map(statuses).fillna(
        "not_assessable"
    )
    result["historical_osm_cell_persistence"] = result[
        "historical_osm_cell_persistence"
    ].fillna("not_assessable")
    return result, statuses, [grid_path, summary_path]


def ensure_finite(frame: pd.DataFrame, columns: list[str]) -> None:
    values = frame[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"Non-finite values detected in {columns}")


def write_geojson(frame: gpd.GeoDataFrame, path: Path) -> None:
    if frame.empty:
        path.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")
    else:
        frame.to_file(path, driver="GeoJSON")


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    rules = config["consensus"]
    top_share = float(rules["top_share"])
    minimum_baselines = int(rules["minimum_damage_baselines"])
    regime = str(rules["weight_regime"])
    minimum_probability = float(rules["minimum_weight_probability"])
    minimum_resolutions = int(rules["minimum_population_resolutions"])
    minimum_scales = int(rules["minimum_spatial_scales"])
    minimum_overlap = float(rules["minimum_area_overlap"])
    if minimum_resolutions != len(RESOLUTIONS):
        raise ValueError("This final audit requires both configured population resolutions")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    priority_1km = gpd.read_file(args.priority_1km)
    priority_100m = gpd.read_file(args.priority_100m)
    reference = priority_1km[["event", "cell_id", "geometry"]].copy()
    population = priority_1km[["event", "cell_id", "worldpop_population"]].rename(
        columns={"worldpop_population": "population_1km"}
    )
    population_100m = priority_100m[["event", "cell_id", "worldpop_population"]].rename(
        columns={"worldpop_population": "population_100m"}
    )
    cells = reference.merge(population, on=["event", "cell_id"], validate="one_to_one")
    cells = cells.merge(population_100m, on=["event", "cell_id"], validate="one_to_one")
    cells = gpd.GeoDataFrame(cells, geometry="geometry", crs=priority_1km.crs)

    input_paths = [args.config, args.priority_1km, args.priority_100m]
    evidence_dirs = {"1km": args.evidence_1km, "100m": args.evidence_100m}
    multiscale_dirs = {"1km": args.multiscale_1km, "100m": args.multiscale_100m}
    for resolution in RESOLUTIONS:
        evidence = read_resolution_evidence(
            evidence_dirs[resolution],
            resolution,
            top_share,
            regime,
            minimum_baselines,
            minimum_probability,
        )
        cells = cells.merge(evidence, on=["event", "cell_id"], how="left", validate="one_to_one")
        if cells[f"passes_resolution_{resolution}"].isna().any():
            raise ValueError(f"Reference cells missing {resolution} evidence")
        input_paths.extend(
            [
                evidence_dirs[resolution] / "baseline_cell_consensus.csv",
                evidence_dirs[resolution] / "weight_uncertainty_cells.csv",
            ]
        )

    cells["population_resolutions_supported"] = sum(
        cells[f"passes_resolution_{resolution}"].astype(int) for resolution in RESOLUTIONS
    )
    scale_support_columns: list[str] = []
    for resolution in RESOLUTIONS:
        scale_geometries = read_scale_geometries(multiscale_dirs[resolution])
        input_paths.append(multiscale_dirs[resolution] / "multiscale_cell_or_area_summary.csv")
        for scale in SCALES:
            column = f"scale_{scale}m_support_{resolution}"
            cells[column] = area_overlap_support(cells, scale_geometries[scale], minimum_overlap)
            input_paths.append(
                multiscale_dirs[resolution]
                / f"worldpop_{scale}m"
                / f"damage_osm_worldpop_grid_{scale}m.geojson"
            )
    for scale in SCALES:
        column = f"scale_{scale}m_support_both_resolutions"
        cells[column] = cells[f"scale_{scale}m_support_1km"] & cells[
            f"scale_{scale}m_support_100m"
        ]
        scale_support_columns.append(column)
    cells["spatial_scales_supported"] = cells[scale_support_columns].sum(axis=1).astype(int)
    cells["high_confidence_disagreement"] = (
        (cells["population_resolutions_supported"] >= minimum_resolutions)
        & (cells["spatial_scales_supported"] >= minimum_scales)
    )

    cells, temporal_statuses, temporal_paths = add_temporal_evidence(cells, args.historical_osm)
    input_paths.extend(temporal_paths)
    cells["temporally_supported_high_confidence"] = (
        cells["high_confidence_disagreement"]
        & cells["historical_osm_cell_persistence"].eq("support")
    )
    numeric_columns = [
        "population_1km",
        "population_100m",
        "baseline_support_1km",
        "baseline_support_100m",
        "policy_probability_1km",
        "policy_probability_100m",
        "population_resolutions_supported",
        "spatial_scales_supported",
    ]
    ensure_finite(cells, numeric_columns)

    event_rows = []
    for event, group in cells.groupby("event", sort=True):
        event_rows.append(
            {
                "event": event,
                "cells": int(len(group)),
                "resolution_consensus_cells": int(
                    (group["population_resolutions_supported"] >= minimum_resolutions).sum()
                ),
                "scale_consensus_cells": int(
                    (group["spatial_scales_supported"] >= minimum_scales).sum()
                ),
                "high_confidence_disagreement_cells": int(
                    group["high_confidence_disagreement"].sum()
                ),
                "temporally_supported_high_confidence_cells": int(
                    group["temporally_supported_high_confidence"].sum()
                ),
                "historical_osm_evidence": temporal_statuses.get(event, "not_assessable"),
            }
        )
    event_summary = pd.DataFrame(event_rows)
    candidates = cells[cells["high_confidence_disagreement"]].copy()

    all_csv = args.out_dir / "final_consensus_all_cells.csv"
    candidate_csv = args.out_dir / "final_consensus_candidates.csv"
    candidate_geojson = args.out_dir / "final_consensus_candidates.geojson"
    event_csv = args.out_dir / "final_consensus_event_summary.csv"
    cells.drop(columns="geometry").to_csv(all_csv, index=False)
    candidates.drop(columns="geometry").to_csv(candidate_csv, index=False)
    write_geojson(candidates, candidate_geojson)
    event_summary.to_csv(event_csv, index=False)

    unique_inputs = sorted({path.resolve() for path in input_paths if path.exists()})
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/24_build_final_consensus.py",
        "claim_label": "robust disagreement",
        "rules": {
            "top_share": top_share,
            "minimum_damage_baselines": minimum_baselines,
            "weight_regime": regime,
            "minimum_weight_probability": minimum_probability,
            "required_population_resolutions": list(RESOLUTIONS),
            "minimum_spatial_scales": minimum_scales,
            "minimum_reference_area_overlap": minimum_overlap,
            "scale_rule": "A scale counts only when both population resolutions overlap.",
            "historical_osm_rule": "Reported separately and never used to relax consensus thresholds.",
        },
        "inputs": [
            {"path": portable_path(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in unique_inputs
        ],
        "events": event_summary.to_dict(orient="records"),
        "high_confidence_candidates": int(len(candidates)),
        "outputs": [path.name for path in [all_csv, candidate_csv, candidate_geojson, event_csv]],
    }
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(event_summary.to_string(index=False))
    print(f"high_confidence_candidates={len(candidates)}")
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
