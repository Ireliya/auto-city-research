#!/usr/bin/env python3
"""Download the pinned Hugging Face reproducibility snapshot."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOW_PATTERNS = [
    "data/**",
    "reports/figures/**",
    "reports/pdf/**",
    "records/evidence_index.csv",
    "records/materials_registry.csv",
    "records/stage2_evidence_hardening_20260715-1057.md",
    "MANIFEST.csv",
]


def release_config() -> dict:
    path = ROOT / "configs" / "public_release.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    config = release_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=config["huggingface_dataset"])
    parser.add_argument("--revision", default=config["huggingface_revision"])
    parser.add_argument("--local-dir", type=Path, default=ROOT)
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
    print(f"repo_id={args.repo_id}")
    print(f"revision={args.revision}")
    print(f"downloaded_to={downloaded}")


if __name__ == "__main__":
    main()
