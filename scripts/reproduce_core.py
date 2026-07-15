#!/usr/bin/env python3
"""Download, verify, and recompute the offline core evidence in one command."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--revision", default="", help="Override configs/public_release.yaml")
    parser.add_argument("--work-dir", type=Path, default=Path("data/reproduced/core_v1"))
    parser.add_argument("--figure-dir", type=Path, default=Path("reports/reproduced_figures"))
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_download_manifest() -> int:
    manifest_path = ROOT / "MANIFEST.csv"
    if not manifest_path.exists():
        raise FileNotFoundError("MANIFEST.csv was not downloaded")
    checked = 0
    allowed_prefixes = ("data/", "reports/figures/", "reports/pdf/")
    allowed_exact = {
        "records/evidence_index.csv",
        "records/materials_registry.csv",
        "records/stage2_evidence_hardening_20260715-1057.md",
    }
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            relative = row["path"]
            if not (relative.startswith(allowed_prefixes) or relative in allowed_exact):
                continue
            path = ROOT / relative
            if not path.exists():
                continue
            expected_bytes = int(row["bytes"])
            expected_hash = row["sha256"]
            if path.stat().st_size != expected_bytes:
                raise AssertionError(f"Manifest byte mismatch: {relative}")
            if sha256_file(path) != expected_hash:
                raise AssertionError(f"Manifest SHA-256 mismatch: {relative}")
            checked += 1
    if checked < 20:
        raise AssertionError(f"Manifest verification checked too few files: {checked}")
    return checked


def run(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout[-6000:]}\nstderr:\n{result.stderr[-6000:]}"
        )
    print("+", " ".join(command))
    if result.stdout.strip():
        print(result.stdout.strip())
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


def assert_recomputed(work_dir: Path) -> dict[str, int]:
    primary = pd.read_csv(work_dir / "priority" / "event_mismatch_summary.csv")
    strict = pd.read_csv(work_dir / "strict" / "strict_budget_event_summary.csv")
    evidence = pd.read_csv(work_dir / "evidence" / "baseline_event_summary.csv")
    multiscale = pd.read_csv(work_dir / "multiscale" / "multiscale_event_summary.csv")
    counts = {
        "primary_stable_mismatch_total": int(primary["stable_mismatch_count"].sum()),
        "strict_top20_stable_mismatch_total": int(
            strict.loc[strict["top_share"].round(2) == 0.20, "strict_stable_mismatch_count"].sum()
        ),
        "stage2_current_baseline_top20_total": int(
            evidence.loc[
                (evidence["baseline"] == "damage_index_D")
                & (evidence["top_share"].round(2) == 0.20),
                "stable_mismatch_count",
            ].sum()
        ),
        "multiscale_500m_top20_total": int(
            multiscale.loc[
                (multiscale["cell_m"] == 500) & (multiscale["top_share"].round(2) == 0.20),
                "stable_mismatch_count",
            ].sum()
        ),
    }
    expected = {
        "primary_stable_mismatch_total": 67,
        "strict_top20_stable_mismatch_total": 109,
        "stage2_current_baseline_top20_total": 109,
        "multiscale_500m_top20_total": 109,
    }
    if counts != expected:
        raise AssertionError(f"Recomputed headline mismatch: expected {expected}, got {counts}")
    return counts


def main() -> None:
    args = parse_args()
    release = yaml.safe_load((ROOT / "configs/public_release.yaml").read_text(encoding="utf-8"))
    revision = args.revision or release["huggingface_revision"]
    work_dir = args.work_dir if args.work_dir.is_absolute() else ROOT / args.work_dir
    figure_dir = args.figure_dir if args.figure_dir.is_absolute() else ROOT / args.figure_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    commands: list[dict] = []

    if not args.skip_download:
        commands.append(
            run(
                [
                    sys.executable,
                    "scripts/download_data.py",
                    "--revision",
                    revision,
                ]
            )
        )
    manifest_files_checked = verify_download_manifest()
    commands.append(run([sys.executable, "scripts/smoke_reproduce.py"]))

    priority_dir = work_dir / "priority"
    driver_dir = work_dir / "drivers"
    commands.append(
        run(
            [
                sys.executable,
                "src/05_analyze_priority_mismatch.py",
                "--input-grid",
                "data/derived/worldpop_context_v1/damage_osm_worldpop_grid_500m.geojson",
                "--weights-config",
                "configs/weight_scenarios.yaml",
                "--out-dir",
                str(priority_dir),
            ]
        )
    )
    commands.append(
        run(
            [
                sys.executable,
                "src/06_profile_mismatch_drivers.py",
                "--input-grid",
                str(priority_dir / "priority_mismatch_grid_500m.csv"),
                "--out-dir",
                str(driver_dir),
            ]
        )
    )
    commands.append(
        run(
            [
                sys.executable,
                "src/07_make_result_figures.py",
                "--priority-dir",
                str(priority_dir),
                "--driver-dir",
                str(driver_dir),
                "--out-dir",
                str(figure_dir),
            ]
        )
    )
    commands.append(
        run(
            [
                sys.executable,
                "src/11_run_robustness_checks.py",
                "--priority-grid",
                str(priority_dir / "priority_mismatch_grid_500m.csv"),
                "--xbd-event-summary",
                "data/derived/xbd_core_v1/xbd_event_summary.csv",
                "--out-dir",
                str(work_dir / "robustness"),
                "--figure-dir",
                str(figure_dir),
            ]
        )
    )
    commands.append(
        run(
            [
                sys.executable,
                "src/15_run_strict_budget_check.py",
                "--priority-grid",
                str(priority_dir / "priority_mismatch_grid_500m.csv"),
                "--primary-summary",
                str(priority_dir / "event_mismatch_summary.csv"),
                "--out-dir",
                str(work_dir / "strict"),
                "--figure-dir",
                str(figure_dir),
            ]
        )
    )
    commands.append(
        run(
            [
                sys.executable,
                "src/18_run_baseline_weight_robustness.py",
                "--priority-grid",
                str(priority_dir / "priority_mismatch_grid_500m.csv"),
                "--weights-config",
                "configs/weight_scenarios.yaml",
                "--experiment-config",
                "configs/evidence_hardening.yaml",
                "--out-dir",
                str(work_dir / "evidence"),
                "--figure-dir",
                str(figure_dir),
            ]
        )
    )
    multiscale_dir = work_dir / "multiscale"
    for cell_m in (250, 500, 1000):
        source = ROOT / "data/derived/multiscale_v1" / f"worldpop_{cell_m}m"
        target = multiscale_dir / f"worldpop_{cell_m}m"
        if not source.exists():
            raise FileNotFoundError(f"Missing released multiscale input: {source}")
        shutil.copytree(source, target, dirs_exist_ok=True)
    commands.append(
        run(
            [
                sys.executable,
                "src/19_run_multiscale_robustness.py",
                "--skip-preparation",
                "--out-dir",
                str(multiscale_dir),
                "--figure-dir",
                str(figure_dir),
            ]
        )
    )
    counts = assert_recomputed(work_dir)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "huggingface_dataset": release["huggingface_dataset"],
        "huggingface_revision": revision,
        "manifest_files_checked": manifest_files_checked,
        "headline_counts": counts,
        "commands": commands,
        "network_dependent_steps_excluded": ["03", "04", "17", "20"],
    }
    report_path = work_dir / "reproduction_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"core reproduction OK: {report_path}")


if __name__ == "__main__":
    main()
