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

Interpretation: building damage is important, but it is not the same thing as recovery need. A disaster AI should expose where damage-only and need-aware rankings disagree, rather than treating visible building damage as the final priority list.

## Quick Reproduction

```bash
git clone https://github.com/Ireliya/auto-city-research.git
cd auto-city-research

conda env create -f environment.yml
conda activate city

python -m pip install -r requirements.txt
python scripts/download_data.py
python scripts/smoke_reproduce.py
```

The smoke test verifies the headline counts from the downloadable derived data. It does not require raw satellite imagery or GPU.

## Recreate Main Tables And Figures

After downloading the Hugging Face data snapshot:

```bash
python src/05_analyze_priority_mismatch.py
python src/06_profile_mismatch_drivers.py
python src/07_make_result_figures.py
python src/08_make_case_maps.py
python src/11_run_robustness_checks.py
python src/15_run_strict_budget_check.py
python src/17_fetch_osm_building_form.py
```

Scripts `03`, `04`, `16`, and `17` can call public web services or download public data and may take longer or fail if upstream services are unavailable. For offline review, use the derived data snapshot on Hugging Face and run the smoke test first.

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
