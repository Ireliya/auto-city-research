#!/usr/bin/env python3
"""Join GHSL built-up surface as an independent urban-form robustness layer."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import requests
import seaborn as sns
from PIL import Image
from rasterstats import zonal_stats
from scipy.stats import spearmanr


GHSL_ROOT = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A"
DEFAULT_EPOCH = 2015
DEFAULT_RESOLUTION_M = 1000
EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}


def ghsl_url(epoch: int, resolution_m: int) -> str:
    product = f"GHS_BUILT_S_E{epoch}_GLOBE_R2023A_54009_{resolution_m}"
    filename = f"{product}_V1_0.zip"
    return f"{GHSL_ROOT}/{product}/V1-0/{filename}"


def download_file(url: str, out_path: Path, timeout_seconds: int, chunk_size: int = 1024 * 1024) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and out_path.stat().st_size > 0:
        return {"status": "cached", "bytes": out_path.stat().st_size, "elapsed_seconds": 0.0}

    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    start = time.time()
    bytes_written = 0
    with requests.get(url, stream=True, timeout=(30, 120)) as response:
        response.raise_for_status()
        with tmp_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                bytes_written += len(chunk)
                if time.time() - start > timeout_seconds:
                    raise TimeoutError(f"download timed out after {timeout_seconds}s with {bytes_written} bytes")
    shutil.move(tmp_path, out_path)
    return {
        "status": "downloaded",
        "bytes": out_path.stat().st_size,
        "elapsed_seconds": round(time.time() - start, 2),
    }


def safe_extract_first_tif(zip_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        tif_names = [name for name in zf.namelist() if name.lower().endswith((".tif", ".tiff"))]
        if not tif_names:
            raise ValueError(f"No GeoTIFF found in {zip_path}")
        tif_name = sorted(tif_names)[0]
        target = out_dir / Path(tif_name).name
        if target.exists() and target.stat().st_size > 0:
            return target
        with zf.open(tif_name) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return target


def standardized_difference(a: pd.Series, b: pd.Series) -> float:
    a = pd.to_numeric(a, errors="coerce").dropna()
    b = pd.to_numeric(b, errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if pooled == 0 or np.isnan(pooled):
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def join_ghsl(grid: gpd.GeoDataFrame, raster_path: Path, resolution_m: int, cell_m: int) -> pd.DataFrame:
    with rasterio.open(raster_path) as src:
        grid_for_raster = grid.to_crs(src.crs)
        stats = zonal_stats(
            grid_for_raster.geometry,
            str(raster_path),
            stats=["sum", "mean", "max", "count"],
            all_touched=True,
            nodata=src.nodata,
        )

    rows = []
    raster_cell_area = float(resolution_m * resolution_m)
    analysis_cell_area = float(cell_m * cell_m)
    for cell_id, stat in zip(grid["cell_id"], stats):
        mean_value = stat.get("mean")
        sum_value = stat.get("sum")
        max_value = stat.get("max")
        count = int(stat.get("count") or 0)
        mean_value = 0.0 if mean_value is None or np.isnan(mean_value) else float(mean_value)
        sum_value = 0.0 if sum_value is None or np.isnan(sum_value) else float(sum_value)
        max_value = 0.0 if max_value is None or np.isnan(max_value) else float(max_value)
        if resolution_m >= cell_m:
            built_surface_m2 = mean_value * (analysis_cell_area / raster_cell_area)
            method = "mean_density_scaled_to_analysis_cell"
        else:
            built_surface_m2 = sum_value
            method = "sum_finer_resolution_pixels"
        rows.append(
            {
                "cell_id": cell_id,
                "ghsl_built_surface_m2": built_surface_m2,
                "ghsl_built_fraction": built_surface_m2 / analysis_cell_area,
                "ghsl_raster_mean_m2_per_pixel": mean_value,
                "ghsl_raster_max_m2_per_pixel": max_value,
                "ghsl_pixel_count": count,
                "ghsl_join_method": method,
            }
        )
    return pd.DataFrame(rows)


def build_profiles(joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    profile_rows = []
    summary_rows = []
    correlation_rows = []
    variables = [
        ("ghsl_built_fraction", "GHSL built fraction"),
        ("ghsl_built_surface_m2", "GHSL built surface"),
        ("total_area_m2", "xBD mapped building area"),
        ("building_count", "xBD building count"),
    ]

    for group_name, group_df in [("all_events", joined), *sorted(joined.groupby("event"), key=lambda x: x[0])]:
        group_df = group_df.copy()
        stable = group_df[group_df["stable_mismatch"].astype(bool)]
        other = group_df[~group_df["stable_mismatch"].astype(bool)]
        summary_rows.append(
            {
                "group": group_name,
                "cells": int(len(group_df)),
                "stable_mismatch_count": int(len(stable)),
                "stable_mismatch_share": float(len(stable) / len(group_df)) if len(group_df) else np.nan,
                "stable_ghsl_built_fraction_mean": float(stable["ghsl_built_fraction"].mean()) if len(stable) else np.nan,
                "other_ghsl_built_fraction_mean": float(other["ghsl_built_fraction"].mean()) if len(other) else np.nan,
                "stable_ghsl_built_surface_m2_mean": float(stable["ghsl_built_surface_m2"].mean()) if len(stable) else np.nan,
                "other_ghsl_built_surface_m2_mean": float(other["ghsl_built_surface_m2"].mean()) if len(other) else np.nan,
            }
        )
        for column, label in variables:
            if column not in group_df.columns:
                continue
            profile_rows.append(
                {
                    "group": group_name,
                    "variable": column,
                    "label": label,
                    "stable_n": int(stable[column].notna().sum()) if len(stable) else 0,
                    "other_n": int(other[column].notna().sum()) if len(other) else 0,
                    "stable_mean": float(stable[column].mean()) if len(stable) else np.nan,
                    "other_mean": float(other[column].mean()) if len(other) else np.nan,
                    "standardized_mean_difference": standardized_difference(stable[column], other[column]),
                }
            )
        valid = group_df[["ghsl_built_fraction", "total_area_m2"]].replace([np.inf, -np.inf], np.nan).dropna()
        rho, p_value = (np.nan, np.nan)
        if len(valid) >= 3 and valid["ghsl_built_fraction"].nunique() > 1 and valid["total_area_m2"].nunique() > 1:
            rho, p_value = spearmanr(valid["ghsl_built_fraction"], valid["total_area_m2"])
        correlation_rows.append(
            {
                "group": group_name,
                "n": int(len(valid)),
                "spearman_ghsl_fraction_vs_xbd_area": float(rho) if not np.isnan(rho) else np.nan,
                "spearman_p_value": float(p_value) if not np.isnan(p_value) else np.nan,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(profile_rows), pd.DataFrame(correlation_rows)


def make_figure(profile: pd.DataFrame, correlations: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="paper", font_scale=0.95)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )

    data = profile[
        profile["group"].isin(["all_events", "hurricane-harvey", "santa-rosa-wildfire"])
        & profile["variable"].isin(["ghsl_built_fraction", "total_area_m2", "building_count"])
    ].copy()
    data["group_label"] = data["group"].replace(
        {
            "all_events": "All",
            "hurricane-harvey": "Harvey",
            "santa-rosa-wildfire": "Santa Rosa",
        }
    )
    matrix = data.pivot(index="label", columns="group_label", values="standardized_mean_difference").reindex(
        ["GHSL built fraction", "xBD mapped building area", "xBD building count"]
    )[["All", "Harvey", "Santa Rosa"]]

    corr = correlations[correlations["group"] != "all_events"].copy()
    corr["event_label"] = corr["group"].map(EVENT_LABELS)
    corr = corr.set_index("event_label").reindex(["Harvey", "Mexico EQ", "Palu", "Santa Rosa"]).reset_index()

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), constrained_layout=True)
    sns.heatmap(
        matrix,
        ax=axes[0],
        cmap="RdBu_r",
        center=0,
        annot=True,
        fmt=".2f",
        cbar_kws={"label": "SMD\n(mismatch - other)"},
    )
    axes[0].set_title("a  Urban-form profile")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")

    axes[1].barh(
        corr["event_label"],
        corr["spearman_ghsl_fraction_vs_xbd_area"],
        color=sns.color_palette("colorblind", n_colors=len(corr)),
    )
    axes[1].axvline(0, color="0.3", linewidth=0.8)
    axes[1].set_xlim(-1, 1)
    axes[1].set_xlabel("Spearman rho")
    axes[1].set_ylabel("")
    axes[1].set_title("b  GHSL vs xBD area")
    axes[1].grid(axis="x", color="0.88", linewidth=0.6)
    axes[1].grid(axis="y", visible=False)

    fig.savefig(out_dir / "fig7_ghsl_urban_form_robustness.png")
    fig.savefig(out_dir / "fig7_ghsl_urban_form_robustness.pdf")
    plt.close(fig)
    image = Image.open(out_dir / "fig7_ghsl_urban_form_robustness.png").convert("L")
    image.save(out_dir / "fig7_ghsl_urban_form_robustness_grayscale.png")


def write_manifest(out_dir: Path, args: argparse.Namespace, url: str, raster_path: Path, download_info: dict) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/16_join_ghsl_built_surface.py",
        "input_grid": str(args.input_grid),
        "raw_dir": str(args.raw_dir),
        "ghsl_url": url,
        "ghsl_epoch": args.epoch,
        "ghsl_resolution_m": args.resolution_m,
        "ghsl_raster_path": str(raster_path),
        "download_info": download_info,
        "interpretation": "Independent urban-form robustness layer. The current main priority mismatch definition is not changed.",
        "built_surface_definition": "GHS-BUILT-S values are built-up square metres per source raster cell. For 1km data joined to 500m cells, values are treated as built fraction and scaled to the 500m analysis cell area.",
        "outputs": [
            "ghsl_grid_features_500m.csv",
            "priority_mismatch_with_ghsl_500m.csv",
            "priority_mismatch_with_ghsl_500m.geojson",
            "ghsl_urban_form_event_summary.csv",
            "ghsl_urban_form_profile.csv",
            "ghsl_xbd_area_correlation.csv",
        ],
        "known_limitations": [
            "The default 1km GHSL layer is coarser than the 500m analysis grid and is used as a robustness layer, not as a replacement for xBD building polygons.",
            "The default epoch is 2015, which is pre-disaster for the selected 2017/2018 events but not event-month specific.",
            "Zonal statistics use all_touched=True and do not use fractional raster-polygon weighting.",
        ],
        "citation": "Pesaresi and Politis, GHS-BUILT-S R2023A, European Commission Joint Research Centre, doi:10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA.",
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-grid", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--figure-dir", required=True, type=Path)
    parser.add_argument("--epoch", type=int, default=DEFAULT_EPOCH)
    parser.add_argument("--resolution-m", type=int, default=DEFAULT_RESOLUTION_M)
    parser.add_argument("--cell-m", type=int, default=500)
    parser.add_argument("--ghsl-zip", type=Path, default=None)
    parser.add_argument("--ghsl-raster", type=Path, default=None)
    parser.add_argument("--download-timeout-seconds", type=int, default=1800)
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    url = ghsl_url(args.epoch, args.resolution_m)
    download_info: dict = {"status": "not_needed"}

    if args.ghsl_raster is not None:
        raster_path = args.ghsl_raster
    else:
        zip_path = args.ghsl_zip or args.raw_dir / Path(url).name
        if not zip_path.exists():
            if args.skip_download:
                raise FileNotFoundError(f"GHSL zip not found and --skip-download was set: {zip_path}")
            download_info = download_file(url, zip_path, args.download_timeout_seconds)
        else:
            download_info = {"status": "cached", "bytes": zip_path.stat().st_size, "elapsed_seconds": 0.0}
        raster_path = safe_extract_first_tif(zip_path, args.raw_dir / "extracted")

    grid = gpd.read_file(args.input_grid)
    if "stable_mismatch" not in grid.columns:
        raise ValueError("Input grid must include stable_mismatch")
    features = join_ghsl(grid, raster_path, args.resolution_m, args.cell_m)
    joined = grid.merge(features, on="cell_id", how="left")

    joined.drop(columns="geometry").to_csv(args.out_dir / "priority_mismatch_with_ghsl_500m.csv", index=False)
    joined.to_file(args.out_dir / "priority_mismatch_with_ghsl_500m.geojson", driver="GeoJSON")
    features.to_csv(args.out_dir / "ghsl_grid_features_500m.csv", index=False)

    summary, profile, correlations = build_profiles(pd.DataFrame(joined.drop(columns="geometry")))
    summary.to_csv(args.out_dir / "ghsl_urban_form_event_summary.csv", index=False)
    profile.to_csv(args.out_dir / "ghsl_urban_form_profile.csv", index=False)
    correlations.to_csv(args.out_dir / "ghsl_xbd_area_correlation.csv", index=False)
    make_figure(profile, correlations, args.figure_dir)
    write_manifest(args.out_dir, args, url, raster_path, download_info)

    print(f"joined={args.out_dir / 'priority_mismatch_with_ghsl_500m.csv'}")
    print(f"summary={args.out_dir / 'ghsl_urban_form_event_summary.csv'}")
    print(f"profile={args.out_dir / 'ghsl_urban_form_profile.csv'}")
    print(f"figure={args.figure_dir / 'fig7_ghsl_urban_form_robustness.png'}")


if __name__ == "__main__":
    main()
