#!/usr/bin/env python3
"""Download the Hugging Face reproducibility dataset for this project."""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


DEFAULT_REPO_ID = "Ireliya/auto-city-research"
DEFAULT_ALLOW_PATTERNS = [
    "data/**",
    "reports/figures/**",
    "reports/pdf/**",
    "records/evidence_index.csv",
    "records/materials_registry.csv",
    "MANIFEST.csv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO_ID, help="Hugging Face dataset repo id.")
    parser.add_argument("--revision", default=None, help="Optional dataset revision, branch, tag, or commit.")
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=Path("."),
        help="Project root where data/reports/records folders should be restored.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.local_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = snapshot_download(
        repo_id=args.repo_id,
        repo_type="dataset",
        revision=args.revision,
        local_dir=out_dir,
        allow_patterns=DEFAULT_ALLOW_PATTERNS,
    )
    print(f"Downloaded dataset snapshot to: {downloaded}")
    print("Next: python scripts/smoke_reproduce.py")


if __name__ == "__main__":
    main()
