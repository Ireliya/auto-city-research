# Damage Is Not Need

Auditing damage-only disaster recovery priority with multi-source urban evidence.

Team: `auto city research`  
Competition: Urban Cup 2026 Competition 2, Urban Science Vibe Research Challenge  
Code repository: https://github.com/Ireliya/auto-city-research  
Dataset repository: https://huggingface.co/datasets/Ireliya/auto-city-research

## What This Repository Does

Remote-sensing damage assessment can rapidly locate damaged buildings after a disaster. This project asks a different urban AI question:

> If a disaster-response AI ranks recovery priority only from satellite-observed building damage, will it under-rank areas that become high need once population exposure, road accessibility, critical facilities, and local urban form are considered?

The project builds a reproducible 500 m grid audit over four xBD/xView2 disaster events:

- Hurricane Harvey
- Mexico earthquake
- Palu tsunami
- Santa Rosa wildfire

The main result is a disagreement map between:

- `damage-only priority`: xBD building damage aggregated to 500 m cells
- `need-aware priority`: damage plus WorldPop population, OSM roads, OSM facilities, and building-form proxies

## Key Results

- 99,629 xBD building records parsed across four events.
- 1,448 500 m grid cells analyzed.
- 67 stable high-need / low-damage mismatch cells in the primary top-20 percentile audit:
  - Hurricane Harvey: 46
  - Mexico earthquake: 0
  - Palu tsunami: 3
  - Santa Rosa wildfire: 18
- 109 stable mismatch cells in the exact top-20 budget check:
  - Hurricane Harvey: 51
  - Mexico earthquake: 37
  - Palu tsunami: 3
  - Santa Rosa wildfire: 18
- 813,352 current OSM building polygons joined as an independent urban-form robustness layer.
- Four alternative damage-only baselines preserve mismatch in every event at an exact top-20 budget. Harvey ranges from 27 to 51 mismatch cells and Santa Rosa from 18 to 41.
- Across 10,000 policy-plausible weight vectors, the median exact top-20 mismatch count is 49 for Harvey and 21 for Santa Rosa.
- Rebuilding the complete audit at 250 m, 500 m, and 1,000 m preserves the Harvey signal; its mismatch-area share is 9.22%, 8.33%, and 8.57%, respectively. Santa Rosa remains 8.09%, 5.11%, and 4.96%.
- Harvey external validation covers 149 intersecting Census tracts and 10,134 aggregated NFIP claims. The result is mixed: need-aware rankings do not consistently outperform damage-only rankings against insured property losses.

Interpretation: building damage is important, but it is not the same thing as recovery need. A disaster AI should expose where damage-only and need-aware rankings disagree, rather than treating visible building damage as the final priority list. NFIP is an insured-property-loss proxy, not ground truth for unmet rescue or recovery need, so the released disagreement map is an audit trigger for human review rather than a validated allocation rule.

## Quick Reproduction

```bash
git clone https://github.com/Ireliya/auto-city-research.git
cd auto-city-research

conda env create -f environment.yml
conda activate city

python -m pip install -r requirements.txt
python scripts/reproduce_core.py
```

The command downloads a pinned Hugging Face snapshot, verifies its SHA-256 manifest, runs the headline smoke checks, and recomputes the offline core tables and figures. It does not require raw satellite imagery or GPU.

## Recreate Main Tables And Figures

For a fast result-only check after downloading the pinned snapshot:

```bash
python scripts/download_data.py
python scripts/smoke_reproduce.py
```

`scripts/reproduce_core.py` runs scripts `05`, `06`, `07`, `11`, `15`, `18`, and `19` with every required argument supplied. Script `19` uses the released prepared 250/500/1000 m grids so the scale analysis itself is offline and deterministic. Scripts `03`, `04`, `16`, `17`, and `20` depend on public web services or omitted source data and are excluded from per-commit CI; their released aggregate outputs remain downloadable.

## Repository Structure

```text
configs/      Fixed event, dataset, GPU, writing, and weight-scenario configs
src/          Reproducible analysis, robustness, and figure scripts
reports/      Paper/report sources and references; figures and PDF exports restored by data download
records/      Claim-to-evidence ledgers restored after Hugging Face download
data/         Lightweight data notes and manifests; derived data is downloaded from Hugging Face
scripts/      Download and smoke-test helpers for open-source reproduction
```

## Data

The GitHub repository intentionally does not store raw xBD satellite images. Use the Hugging Face dataset repository for lightweight derived tables and report artifacts:

```bash
python scripts/download_data.py --repo-id Ireliya/auto-city-research
```

The default dataset revision is pinned in `configs/public_release.yaml` so a future update to the dataset cannot silently change a reproduction run.

For data source and redistribution boundaries, see:

- `DATASET.md`
- `reports/data_access_license_notes.md`
- Hugging Face dataset card: https://huggingface.co/datasets/Ireliya/auto-city-research

## GPU Policy

The main geospatial/statistical workflow is CPU-first. No GPU is required for the published mainline results.

If optional VLM experiments are added later, they must use:

```bash
CUDA_VISIBLE_DEVICES=0
```

Multi-GPU training is out of scope for this competition submission.

## Citation

If you use this repository, please cite:

```text
auto city research. Damage Is Not Need: Auditing Damage-Only Disaster Recovery Priority with Multi-Source Urban Evidence. Urban Cup 2026 Competition 2.
```

See `CITATION.cff` for machine-readable citation metadata.
