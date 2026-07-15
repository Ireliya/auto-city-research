#!/usr/bin/env python3
"""Audit 100-m WorldPop completeness and sensitivity against the 1-km product."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grid-1km",
        type=Path,
        default=Path("data/derived/worldpop_context_v1/damage_osm_worldpop_grid_500m.csv"),
    )
    parser.add_argument(
        "--grid-100m",
        type=Path,
        default=Path(
            "data/derived/worldpop_context_100m_v1/damage_osm_worldpop_grid_500m.csv"
        ),
    )
    parser.add_argument("--config", type=Path, default=Path("configs/final_evidence.yaml"))
    parser.add_argument(
        "--out-dir", type=Path, default=Path("data/derived/population_resolution_audit_v1")
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_top_ids(frame: pd.DataFrame, column: str, share: float) -> set[str]:
    k = max(1, int(math.ceil(len(frame) * share)))
    ranked = frame.sort_values([column, "cell_id"], ascending=[False, True], kind="mergesort")
    return set(ranked.head(k)["cell_id"].astype(str))


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    review_threshold = float(config["worldpop"]["total_difference_review_threshold"])
    one_km = pd.read_csv(args.grid_1km, usecols=["event", "cell_id", "worldpop_population"])
    one_hundred = pd.read_csv(
        args.grid_100m, usecols=["event", "cell_id", "worldpop_population"]
    )
    one_km = one_km.rename(columns={"worldpop_population": "population_1km"})
    one_hundred = one_hundred.rename(columns={"worldpop_population": "population_100m"})
    joined = one_km.merge(
        one_hundred,
        on=["event", "cell_id"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    rows = []
    for event, group in joined.groupby("event", sort=True):
        matched = group["_merge"].eq("both")
        values_1km = pd.to_numeric(group["population_1km"], errors="coerce")
        values_100m = pd.to_numeric(group["population_100m"], errors="coerce")
        finite_100m = np.isfinite(values_100m.to_numpy(dtype=float))
        nonnegative_100m = values_100m.fillna(-1).ge(0)
        complete = bool(matched.all() and finite_100m.all() and nonnegative_100m.all())
        total_1km = float(values_1km.sum())
        total_100m = float(values_100m.sum())
        relative_difference = (
            abs(total_100m - total_1km) / total_1km if total_1km > 0 else np.nan
        )
        valid = matched & values_1km.notna() & values_100m.notna()
        rho = float(spearmanr(values_1km[valid], values_100m[valid]).statistic)
        valid_frame = group.loc[valid, ["cell_id"]].copy()
        valid_frame["population_1km"] = values_1km[valid]
        valid_frame["population_100m"] = values_100m[valid]
        top_1km = exact_top_ids(valid_frame, "population_1km", 0.20)
        top_100m = exact_top_ids(valid_frame, "population_100m", 0.20)
        union = top_1km | top_100m
        top_jaccard = len(top_1km & top_100m) / len(union) if union else 1.0
        basic_quality_pass = bool(complete and total_100m > 0)
        review_required = bool(
            basic_quality_pass
            and np.isfinite(relative_difference)
            and relative_difference > review_threshold
        )
        if not basic_quality_pass:
            status = "fail"
        elif review_required:
            status = "pass_with_total_difference_review"
        else:
            status = "pass"
        rows.append(
            {
                "event": event,
                "cells_union": int(len(group)),
                "cells_matched": int(matched.sum()),
                "missing_100m_cells": int((group["_merge"] == "left_only").sum()),
                "nonfinite_100m_cells": int((~finite_100m).sum()),
                "negative_100m_cells": int((~nonnegative_100m).sum()),
                "zero_population_share_1km": float(values_1km.eq(0).mean()),
                "zero_population_share_100m": float(values_100m.eq(0).mean()),
                "population_total_1km": total_1km,
                "population_total_100m": total_100m,
                "total_relative_difference": relative_difference,
                "cell_rank_spearman": rho,
                "population_top20_jaccard": top_jaccard,
                "review_threshold": review_threshold,
                "quality_status": status,
            }
        )
    audit = pd.DataFrame(rows)
    eligible = bool((audit["quality_status"] != "fail").all() and len(audit) == 4)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.out_dir / "population_resolution_event_audit.csv"
    audit.to_csv(output_path, index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "src/26_audit_population_resolution.py",
        "inputs": [
            {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in [args.grid_1km, args.grid_100m, args.config]
        ],
        "events_expected": 4,
        "worldpop_100m_primary_eligible": eligible,
        "review_rule": (
            "A total difference above the configured threshold triggers interpretation review, "
            "not automatic rejection, because the 100-m constrained raster and 1-km UA product "
            "use different spatial allocation semantics."
        ),
        "outputs": [output_path.name],
    }
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(audit.to_string(index=False))
    print(f"worldpop_100m_primary_eligible={eligible}")
    print(f"outputs={args.out_dir}")


if __name__ == "__main__":
    main()
