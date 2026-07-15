#!/usr/bin/env python3
"""Create the final consensus and external-proxy divergence figures."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from figure_style import (  # noqa: E402
    BLUE,
    GRID,
    INK,
    LIGHT_NEUTRAL,
    MUTED,
    ROSE,
    add_panel_label,
    apply_publication_style,
    mm_to_inches,
    save_publication_figure,
)


EVENT_LABELS = {
    "hurricane-harvey": "Harvey",
    "mexico-earthquake": "Mexico EQ",
    "palu-tsunami": "Palu",
    "santa-rosa-wildfire": "Santa Rosa",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--consensus-dir",
        type=Path,
        default=Path("data/derived/final_consensus_v1"),
    )
    parser.add_argument(
        "--historical-osm-dir",
        type=Path,
        default=Path("data/derived/historical_osm_v1"),
    )
    parser.add_argument(
        "--external-proxy-dir",
        type=Path,
        default=Path("data/derived/external_proxies_v1"),
    )
    parser.add_argument(
        "--nfip-dir",
        type=Path,
        default=Path("data/derived/harvey_external_validation_v1"),
    )
    parser.add_argument("--figure-dir", type=Path, default=Path("reports/figures"))
    return parser.parse_args()


def make_consensus_figure(
    cells: pd.DataFrame,
    historical: pd.DataFrame,
    figure_dir: Path,
) -> None:
    events = list(EVENT_LABELS)
    stage_labels = [
        "1-km\npopulation",
        "100-m\npopulation",
        "Both\nresolutions",
        "+ >=2\nscales",
        "+ historical\nOSM",
    ]
    matrix = []
    for event in events:
        group = cells[cells["event"].eq(event)]
        high = group["high_confidence_disagreement"].astype(bool)
        matrix.append(
            [
                int(group["passes_resolution_1km"].sum()),
                int(group["passes_resolution_100m"].sum()),
                int((group["population_resolutions_supported"] >= 2).sum()),
                int(high.sum()),
                int((high & group["historical_osm_cell_persistence"].eq("support")).sum()),
            ]
        )
    values = np.asarray(matrix, dtype=float)

    fig, (ax_a, ax_b) = plt.subplots(
        1,
        2,
        figsize=(mm_to_inches(183), mm_to_inches(82)),
        gridspec_kw={"width_ratios": [1.8, 1.0], "wspace": 0.48},
    )
    shown = np.log1p(values)
    image = ax_a.imshow(shown, cmap="Blues", aspect="auto", vmin=0)
    image.set_clim(0, max(1.0, float(shown.max())))
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            normalized = shown[row, column] / max(float(shown.max()), 1.0)
            ax_a.text(
                column,
                row,
                f"{int(values[row, column])}",
                ha="center",
                va="center",
                color="white" if normalized > 0.58 else INK,
                fontsize=6.8,
            )
    ax_a.set_xticks(np.arange(len(stage_labels)), stage_labels)
    ax_a.set_yticks(np.arange(len(events)), [EVENT_LABELS[event] for event in events])
    ax_a.tick_params(axis="both", length=0)
    ax_a.tick_params(axis="x", labelsize=6.2, pad=5)
    ax_a.set_title("Cells passing each fixed evidence gate", loc="left", pad=8)
    for spine in ax_a.spines.values():
        spine.set_visible(False)
    add_panel_label(ax_a, "a", x=-0.11, y=1.05)

    status_colors = {
        "support": BLUE,
        "does_not_support": ROSE,
        "not_assessable": LIGHT_NEUTRAL,
    }
    historical_lookup = historical.set_index("event") if not historical.empty else pd.DataFrame()
    for position, event in enumerate(events):
        if not historical.empty and event in historical_lookup.index:
            row = historical_lookup.loc[event]
            value = pd.to_numeric(row.get("mismatch_jaccard"), errors="coerce")
            status = str(row.get("temporal_evidence", "not_assessable"))
        else:
            value = np.nan
            status = "not_assessable"
        if np.isfinite(value):
            ax_b.scatter(
                float(value),
                position,
                s=36,
                marker="o",
                facecolor=status_colors.get(status, LIGHT_NEUTRAL),
                edgecolor="white",
                linewidth=0.7,
                zorder=3,
            )
            label_x = min(float(value) + 0.035, 0.98)
        else:
            ax_b.scatter(0.03, position, s=36, marker="x", color=MUTED, linewidth=1.0)
            label_x = 0.08
        ax_b.text(
            label_x,
            position,
            status.replace("_", " "),
            va="center",
            ha="left",
            fontsize=6.2,
            color=status_colors.get(status, MUTED),
            clip_on=False,
        )
    ax_b.axvline(0.50, color=MUTED, linestyle="--", linewidth=0.8)
    ax_b.text(0.50, -0.65, "fixed support threshold", ha="center", va="bottom", color=MUTED, fontsize=6.0)
    ax_b.set_xlim(0, 1.0)
    ax_b.set_ylim(len(events) - 0.5, -0.85)
    ax_b.set_yticks(np.arange(len(events)), [EVENT_LABELS[event] for event in events])
    ax_b.set_xlabel("Current/pre-event Top-20% Jaccard")
    ax_b.set_title("Historical OSM sensitivity", loc="left", pad=8)
    ax_b.grid(axis="x", color=GRID, linewidth=0.55)
    ax_b.set_axisbelow(True)
    add_panel_label(ax_b, "b", x=-0.24, y=1.05)
    fig.subplots_adjust(bottom=0.22)
    fig.text(
        0.01,
        0.01,
        "Counts are not percentages. Historical OSM is reported separately and never relaxes the final gate.",
        fontsize=5.9,
        color=MUTED,
    )
    save_publication_figure(fig, figure_dir, "fig11_consensus_audit")


def require_row(frame: pd.DataFrame, **filters: object) -> pd.Series:
    selected = frame.copy()
    for column, value in filters.items():
        if isinstance(value, float):
            selected = selected[np.isclose(pd.to_numeric(selected[column], errors="coerce"), value)]
        else:
            selected = selected[selected[column].eq(value)]
    if len(selected) != 1:
        raise ValueError(f"Expected one metric row for {filters}, found {len(selected)}")
    return selected.iloc[0]


def collect_proxy_rows(external: pd.DataFrame, nfip: pd.DataFrame) -> pd.DataFrame:
    specifications = [
        ("SVI", "Overall vulnerability rank", "RPL_THEMES", None),
        ("RI-IHP", "Valid registrations", "totalValidRegistrations", 0.10),
        ("RI-IHP", "Eligible assistance amount", "ihpAmount", 0.10),
        ("RI-IHP", "Registration rate", "registration_rate_per_1000", 0.10),
    ]
    rows: list[dict] = []
    for family, label, outcome, coverage in specifications:
        proxy_family = "CDC SVI 2016" if family == "SVI" else "FEMA RI-IHP"
        common = {
            "proxy_family": proxy_family,
            "outcome": outcome,
            "metric": "spearman_rho",
        }
        if coverage is not None:
            common["coverage_threshold"] = coverage
        for model, model_label, model_family in [
            ("damage_index_D", "Damage severity", "Damage-only"),
            ("score_balanced_need", "Balanced multi-source", "Multi-source"),
        ]:
            row = require_row(external, model=model, **common)
            rows.append(
                {
                    "proxy": family,
                    "outcome_label": label,
                    "model_family": model_family,
                    "model_label": model_label,
                    "value": row["value"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                    "units": row["units"],
                }
            )
    for outcome, label in [
        ("claim_count", "Claim count"),
        ("total_paid_amount", "Paid claim amount"),
    ]:
        for model, model_label, model_family in [
            ("damage_area_weighted_mean_severity", "Damage severity", "Damage-only"),
            ("need_balanced_need", "Balanced multi-source", "Multi-source"),
        ]:
            row = require_row(
                nfip,
                aggregation="mean",
                outcome=outcome,
                model=model,
                metric="spearman_rho",
            )
            rows.append(
                {
                    "proxy": "NFIP",
                    "outcome_label": label,
                    "model_family": model_family,
                    "model_label": model_label,
                    "value": row["value"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                    "units": row["tracts"],
                }
            )
    result = pd.DataFrame(rows)
    numeric = result[["value", "ci_low", "ci_high", "units"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("External-proxy figure contains non-finite values")
    return result


def make_external_proxy_figure(
    external: pd.DataFrame,
    nfip: pd.DataFrame,
    figure_dir: Path,
) -> None:
    frame = collect_proxy_rows(external, nfip)
    order = (
        frame[["proxy", "outcome_label"]]
        .drop_duplicates()
        .assign(order=np.arange(frame[["proxy", "outcome_label"]].drop_duplicates().shape[0]))
    )
    frame = frame.merge(order, on=["proxy", "outcome_label"], validate="many_to_one")
    fig, ax = plt.subplots(figsize=(mm_to_inches(136), mm_to_inches(105)))
    style = {
        "Damage-only": {"color": ROSE, "marker": "s", "offset": -0.11},
        "Multi-source": {"color": BLUE, "marker": "o", "offset": 0.11},
    }
    for family, family_frame in frame.groupby("model_family", sort=False):
        settings = style[family]
        y = family_frame["order"].to_numpy(dtype=float) + settings["offset"]
        x = family_frame["value"].to_numpy(dtype=float)
        low = family_frame["ci_low"].to_numpy(dtype=float)
        high = family_frame["ci_high"].to_numpy(dtype=float)
        ax.errorbar(
            x,
            y,
            xerr=np.vstack([x - low, high - x]),
            fmt=settings["marker"],
            markersize=4.4,
            color=settings["color"],
            ecolor=settings["color"],
            elinewidth=1.0,
            capsize=2.0,
            markeredgecolor="white",
            markeredgewidth=0.55,
            zorder=3,
        )
    labels = [
        f"{row.proxy}  |  {row.outcome_label}"
        for row in order.sort_values("order").itertuples(index=False)
    ]
    ax.set_yticks(np.arange(len(labels)), labels)
    ax.set_ylim(len(labels) - 0.45, -0.85)
    ax.set_xlim(-0.15, 1.0)
    ax.axvline(0, color=INK, linewidth=0.75)
    ax.grid(axis="x", color=GRID, linewidth=0.55)
    ax.set_axisbelow(True)
    ax.set_xlabel("Spearman rank correlation with external proxy (95% bootstrap CI)")
    ax.set_title("External proxies disagree on which priority framing aligns best", loc="left", pad=12)
    ax.text(
        0.02,
        1.025,
        "■  Damage-only",
        transform=ax.transAxes,
        color=ROSE,
        fontsize=6.6,
        va="bottom",
    )
    ax.text(
        0.27,
        1.025,
        "●  Balanced multi-source",
        transform=ax.transAxes,
        color=BLUE,
        fontsize=6.6,
        va="bottom",
    )
    units = frame.groupby(["proxy", "outcome_label"], sort=False)["units"].first().reset_index()
    units = units.merge(order, on=["proxy", "outcome_label"], validate="one_to_one")
    for row in units.itertuples(index=False):
        ax.text(0.985, row.order, f"n={int(row.units)}", ha="right", va="center", color=MUTED, fontsize=5.9)
    fig.text(
        0.015,
        0.012,
        "SVI, RI-IHP and NFIP quantify different constructs; correlation is not proof of true unmet need.",
        fontsize=5.9,
        color=MUTED,
    )
    save_publication_figure(fig, figure_dir, "fig12_external_proxy_divergence")


def main() -> None:
    args = parse_args()
    apply_publication_style()
    cells = pd.read_csv(args.consensus_dir / "final_consensus_all_cells.csv")
    historical_path = args.historical_osm_dir / "historical_osm_event_summary.csv"
    historical = pd.read_csv(historical_path) if historical_path.exists() else pd.DataFrame()
    external = pd.read_csv(args.external_proxy_dir / "external_proxy_rank_metrics.csv")
    nfip = pd.read_csv(args.nfip_dir / "harvey_external_validation_metrics.csv")
    make_consensus_figure(cells, historical, args.figure_dir)
    make_external_proxy_figure(external, nfip, args.figure_dir)
    print(f"final_evidence_figures=2")
    print(f"figure_dir={args.figure_dir}")


if __name__ == "__main__":
    main()
