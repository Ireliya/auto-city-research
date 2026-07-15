#!/usr/bin/env python3
"""Stress-test damage baselines and need-weight uncertainty with exact top-k ranks."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yaml

from evidence_utils import (
    INDICATOR_COLUMNS,
    add_need_indicators,
    add_scenario_scores,
    exact_stable_mismatch,
    exact_top_ids,
    load_need_scenarios,
    require_finite,
)
from figure_style import (
    CMAP_BLUE,
    add_panel_label,
    apply_publication_style,
    color_for_event,
    mm_to_inches,
    save_publication_figure,
    set_heatmap_annotation_contrast,
    style_numeric_axis,
)


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"


EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priority-grid",
        type=Path,
        default=Path("data/derived/priority_mismatch_v1/priority_mismatch_grid_500m.csv"),
    )
    parser.add_argument("--weights-config", type=Path, default=Path("configs/weight_scenarios.yaml"))
    parser.add_argument("--experiment-config", type=Path, default=Path("configs/evidence_hardening.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/derived/evidence_hardening_v1"))
    parser.add_argument("--figure-dir", type=Path, default=Path("reports/figures"))
    return parser.parse_args()


def load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = ["random_seed", "top_shares", "damage_baselines", "weight_uncertainty"]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Experiment config is missing: {missing}")
    return config


def run_baselines(
    grid: pd.DataFrame,
    baselines: dict[str, dict],
    scenarios: list[dict],
    top_shares: list[float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries: list[dict] = []
    cell_rows: list[dict] = []
    baseline_names = list(baselines)

    for event, raw_event_df in grid.groupby("event", sort=True):
        event_flags: dict[tuple[float, str], pd.Series] = {}
        for baseline in baseline_names:
            prepared = add_need_indicators(raw_event_df, damage_column=baseline)
            prepared = add_scenario_scores(prepared, scenarios)
            for top_share in top_shares:
                mismatch, scenario_counts, k = exact_stable_mismatch(
                    prepared,
                    damage_column=baseline,
                    scenarios=scenarios,
                    top_share=top_share,
                )
                mismatch = pd.Series(mismatch.to_numpy(), index=prepared["cell_id"].astype(str))
                event_flags[(top_share, baseline)] = mismatch
                mismatch_rows = prepared.loc[mismatch.to_numpy()]
                damage_top_ids = exact_top_ids(
                    prepared,
                    baseline,
                    top_share,
                    tie_columns=[
                        "damaged_building_count",
                        "severe_building_count",
                        "damage_weighted_area_m2",
                    ],
                )
                outside_damage_top = ~prepared["cell_id"].astype(str).isin(damage_top_ids)
                summaries.append(
                    {
                        "event": event,
                        "baseline": baseline,
                        "baseline_label": baselines[baseline].get("label", baseline),
                        "top_share": top_share,
                        "cells": int(len(prepared)),
                        "exact_budget_k": k,
                        "stable_mismatch_count": int(mismatch.sum()),
                        "stable_mismatch_share": float(mismatch.mean()),
                        "stable_mismatch_population_sum": float(mismatch_rows["worldpop_population"].sum()),
                        "all_scenario_mismatch_count": int(
                            ((scenario_counts == len(scenarios)) & outside_damage_top).sum()
                        ),
                    }
                )

        lookup = raw_event_df.set_index(raw_event_df["cell_id"].astype(str))
        for top_share in top_shares:
            flags = pd.DataFrame(
                {baseline: event_flags[(top_share, baseline)] for baseline in baseline_names}
            ).fillna(False)
            for cell_id, row in flags.iterrows():
                source = lookup.loc[cell_id]
                cell_rows.append(
                    {
                        "event": event,
                        "top_share": top_share,
                        "cell_id": cell_id,
                        "baselines_mismatch_count": int(row.sum()),
                        "baseline_mismatch_probability": float(row.mean()),
                        "robust_across_3_of_4_baselines": bool(row.sum() >= 3),
                        "worldpop_population": float(source.get("worldpop_population", 0.0)),
                        "cell_center_lon": float(source.get("cell_center_lon", np.nan)),
                        "cell_center_lat": float(source.get("cell_center_lat", np.nan)),
                        **{f"mismatch_{baseline}": bool(row[baseline]) for baseline in baseline_names},
                    }
                )
    return pd.DataFrame(summaries), pd.DataFrame(cell_rows)


def plausible_weights(rng: np.random.Generator, n: int, settings: dict) -> tuple[np.ndarray, int]:
    accepted: list[np.ndarray] = []
    drawn = 0
    while sum(len(batch) for batch in accepted) < n:
        batch_size = max(4096, n - sum(len(batch) for batch in accepted))
        batch = rng.dirichlet(np.ones(4), size=batch_size)
        drawn += batch_size
        keep = (
            (batch[:, 0] >= float(settings["damage_weight_min"]))
            & (batch[:, 0] <= float(settings["damage_weight_max"]))
            & (batch[:, 1:] >= float(settings["other_weight_min"])).all(axis=1)
        )
        if keep.any():
            accepted.append(batch[keep])
        if drawn > n * 1000:
            raise RuntimeError("Policy-plausible weight rejection sampling did not converge")
    return np.vstack(accepted)[:n], drawn


def ordered_top_indices(scores: np.ndarray) -> np.ndarray:
    return np.argsort(-scores, axis=1, kind="stable")


def run_weight_uncertainty(
    grid: pd.DataFrame,
    config: dict,
    top_shares: list[float],
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    settings = config["weight_uncertainty"]
    n_samples = int(settings["samples_per_regime"])
    seed = int(config["random_seed"])
    regimes: dict[str, np.ndarray] = {}
    metadata: dict[str, object] = {"samples_per_regime": n_samples, "seed": seed}

    unconstrained_rng = np.random.default_rng(seed)
    plausible_rng = np.random.default_rng(seed + 1)
    regimes["unconstrained"] = unconstrained_rng.dirichlet(np.ones(4), size=n_samples)
    regimes["policy_plausible"], drawn = plausible_weights(
        plausible_rng,
        n_samples,
        settings["regimes"]["policy_plausible"],
    )
    metadata["policy_plausible_draws"] = int(drawn)

    event_rows: list[dict] = []
    cell_rows: list[dict] = []
    thresholds = [float(value) for value in settings.get("probability_thresholds", [0.5, 0.8])]

    prepared_grid = add_need_indicators(grid, damage_column="damage_index_D")
    require_finite(prepared_grid, INDICATOR_COLUMNS, "weight-uncertainty indicators")

    for event, raw_event_df in prepared_grid.groupby("event", sort=True):
        event_df = raw_event_df.sort_values("cell_id", kind="mergesort").reset_index(drop=True)
        indicators = event_df[INDICATOR_COLUMNS].to_numpy(dtype=float)
        for regime_name, weights in regimes.items():
            scores = weights @ indicators.T
            ranking = ordered_top_indices(scores)
            for top_share in top_shares:
                k = int(math.ceil(len(event_df) * top_share))
                damage_top_ids = exact_top_ids(
                    event_df,
                    "damage_index_D",
                    top_share,
                    tie_columns=["damaged_building_count", "severe_building_count", "damage_weighted_area_m2"],
                )
                damage_top = event_df["cell_id"].astype(str).isin(damage_top_ids).to_numpy()
                need_top = np.zeros((n_samples, len(event_df)), dtype=bool)
                row_indices = np.arange(n_samples)[:, None]
                need_top[row_indices, ranking[:, :k]] = True
                mismatch = need_top & (~damage_top[None, :])
                mismatch_counts = mismatch.sum(axis=1)
                probabilities = mismatch.mean(axis=0)
                row = {
                    "event": event,
                    "regime": regime_name,
                    "top_share": top_share,
                    "cells": int(len(event_df)),
                    "exact_budget_k": k,
                    "samples": n_samples,
                    "mismatch_count_median": float(np.median(mismatch_counts)),
                    "mismatch_count_q025": float(np.quantile(mismatch_counts, 0.025)),
                    "mismatch_count_q975": float(np.quantile(mismatch_counts, 0.975)),
                    "samples_with_any_mismatch_share": float((mismatch_counts > 0).mean()),
                }
                for threshold in thresholds:
                    suffix = str(threshold).replace(".", "_")
                    row[f"cells_probability_ge_{suffix}"] = int((probabilities >= threshold).sum())
                event_rows.append(row)

                for idx, source in event_df.iterrows():
                    cell_rows.append(
                        {
                            "event": event,
                            "regime": regime_name,
                            "top_share": top_share,
                            "cell_id": str(source["cell_id"]),
                            "mismatch_probability": float(probabilities[idx]),
                            "mismatch_in_at_least_half_weights": bool(probabilities[idx] >= 0.5),
                            "mismatch_in_at_least_80pct_weights": bool(probabilities[idx] >= 0.8),
                            "damage_index_D": float(source["damage_index_D"]),
                            "worldpop_population": float(source["worldpop_population"]),
                            "cell_center_lon": float(source.get("cell_center_lon", np.nan)),
                            "cell_center_lat": float(source.get("cell_center_lat", np.nan)),
                        }
                    )
    return pd.DataFrame(event_rows), pd.DataFrame(cell_rows), metadata


def make_figure(baseline_summary: pd.DataFrame, weight_summary: pd.DataFrame, figure_dir: Path) -> None:
    sns.set_theme(style="white", context="paper")
    apply_publication_style()
    figure_dir.mkdir(parents=True, exist_ok=True)

    baseline_top20 = baseline_summary[baseline_summary["top_share"].round(2) == 0.20].copy()
    baseline_top20["event_label"] = baseline_top20["event"].map(EVENT_LABELS).fillna(baseline_top20["event"])
    event_order = ["Harvey", "Mexico EQ", "Palu", "Santa Rosa"]
    baseline_order = [
        "Area-weighted mean severity",
        "Damage-weighted building area",
        "Damaged building count",
        "Severe building count",
    ]
    baseline_display = {
        "Area-weighted mean severity": "Mean severity",
        "Damage-weighted building area": "Weighted area",
        "Damaged building count": "Damage count",
        "Severe building count": "Severe count",
    }
    pivot = (
        baseline_top20.pivot(index="event_label", columns="baseline_label", values="stable_mismatch_count")
        .reindex(event_order)[baseline_order]
        .rename(columns=baseline_display)
    )

    weights_top20 = weight_summary[
        (weight_summary["top_share"].round(2) == 0.20)
        & (weight_summary["regime"] == "policy_plausible")
    ].copy()
    weights_top20["event_label"] = weights_top20["event"].map(EVENT_LABELS).fillna(weights_top20["event"])
    weights_top20 = weights_top20.set_index("event_label").reindex(event_order).reset_index()

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(84)),
        constrained_layout=True,
    )
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap=CMAP_BLUE,
        vmin=0,
        linewidths=0.6,
        linecolor="white",
        cbar_kws={"label": "Mismatch cells", "shrink": 0.82, "pad": 0.025},
        ax=axes[0],
    )
    axes[0].set_title("Damage-baseline robustness (top 20%)", loc="left", pad=7)
    add_panel_label(axes[0], "a", x=-0.17, y=1.04)
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")
    axes[0].tick_params(axis="x", rotation=0, labelsize=6.1)
    set_heatmap_annotation_contrast(axes[0], pivot.to_numpy())

    y = np.arange(len(weights_top20))
    med = weights_top20["mismatch_count_median"].to_numpy()
    lower = med - weights_top20["mismatch_count_q025"].to_numpy()
    upper = weights_top20["mismatch_count_q975"].to_numpy() - med
    for idx, row in weights_top20.iterrows():
        axes[1].errorbar(
            med[idx],
            y[idx],
            xerr=np.array([[lower[idx]], [upper[idx]]]),
            fmt="o",
            color=color_for_event(row["event_label"]),
            capsize=2.5,
            elinewidth=1.2,
            markersize=4.8,
        )
        axes[1].text(float(row["mismatch_count_q975"]) + 1.2, y[idx], f"{med[idx]:.0f}", va="center", fontsize=6.3)
    axes[1].set_yticks(y, weights_top20["event_label"])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Mismatch cells, median and 95% interval")
    axes[1].set_title("Policy-plausible weight uncertainty", loc="left", pad=7)
    add_panel_label(axes[1], "b", x=-0.18, y=1.04)
    axes[1].margins(x=0.12)
    style_numeric_axis(axes[1], axis="x")

    save_publication_figure(fig, figure_dir, "fig8_baseline_weight_robustness")


def main() -> None:
    args = parse_args()
    config = load_config(args.experiment_config)
    scenarios = load_need_scenarios(args.weights_config)
    grid = pd.read_csv(args.priority_grid, low_memory=False)
    baselines = config["damage_baselines"]
    missing = [column for column in baselines if column not in grid.columns]
    if missing:
        raise ValueError(f"Priority grid is missing configured damage baselines: {missing}")
    if grid["cell_id"].duplicated().any():
        raise ValueError("cell_id must be globally unique")

    top_shares = [float(value) for value in config["top_shares"]]
    baseline_summary, baseline_cells = run_baselines(grid, baselines, scenarios, top_shares)
    weight_summary, weight_cells, weight_metadata = run_weight_uncertainty(grid, config, top_shares)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    baseline_summary.to_csv(args.out_dir / "baseline_event_summary.csv", index=False)
    baseline_cells.to_csv(args.out_dir / "baseline_cell_consensus.csv", index=False)
    weight_summary.to_csv(args.out_dir / "weight_uncertainty_event_summary.csv", index=False)
    weight_cells.to_csv(args.out_dir / "weight_uncertainty_cells.csv", index=False)
    make_figure(baseline_summary, weight_summary, args.figure_dir)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/18_run_baseline_weight_robustness.py",
        "input_grid": str(args.priority_grid),
        "weights_config": str(args.weights_config),
        "experiment_config": str(args.experiment_config),
        "random_seed": int(config["random_seed"]),
        "top_shares": top_shares,
        "damage_baselines": baselines,
        "need_scenarios": scenarios,
        "weight_uncertainty": weight_metadata,
        "ranking_rule": "exact top-k per event with deterministic stable tie-breaking",
        "outputs": [
            "baseline_event_summary.csv",
            "baseline_cell_consensus.csv",
            "weight_uncertainty_event_summary.csv",
            "weight_uncertainty_cells.csv",
            "reports/figures/fig8_baseline_weight_robustness.png",
            "reports/figures/fig8_baseline_weight_robustness.pdf",
        ],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    top20_baselines = baseline_summary[baseline_summary["top_share"].round(2) == 0.20]
    top20_weights = weight_summary[
        (weight_summary["top_share"].round(2) == 0.20)
        & (weight_summary["regime"] == "policy_plausible")
    ]
    print("baseline_top20_mismatch_counts")
    print(top20_baselines[["event", "baseline", "stable_mismatch_count"]].to_string(index=False))
    print("policy_plausible_top20_weight_summary")
    print(top20_weights[["event", "mismatch_count_median", "mismatch_count_q025", "mismatch_count_q975"]].to_string(index=False))
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
