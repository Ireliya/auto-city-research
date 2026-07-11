# Reproducibility Guide

This guide separates three levels of reproduction.

## Level 1: Result Smoke Test

Use this when you only want to verify the headline numbers from the released derived tables.

```bash
conda env create -f environment.yml
conda activate city
python -m pip install -r requirements.txt
python scripts/download_data.py
python scripts/smoke_reproduce.py
```

Expected output includes:

- `xbd_buildings_rows: 99629`
- `damage_grid_cells: 1448`
- `primary_stable_mismatch_total: 67`
- `strict_top20_stable_mismatch_total: 109`
- `osm_building_polygons_total: 813352`

## Level 2: Rebuild Derived Analysis From Downloaded Tables

This level uses Hugging Face derived tables and regenerates priority tables, robustness checks, and figures.

```bash
python src/05_analyze_priority_mismatch.py
python src/06_profile_mismatch_drivers.py
python src/07_make_result_figures.py
python src/08_make_case_maps.py
python src/11_run_robustness_checks.py
python src/15_run_strict_budget_check.py
```

This level is CPU-only.

## Level 3: Rebuild From Raw/Public Sources

This level reruns source ingestion and public-data joins:

```bash
python src/01_parse_xbd_labels.py --help
python src/02_build_xbd_damage_grid.py --help
python src/03_fetch_osm_context.py --help
python src/04_join_worldpop_population.py --help
python src/17_fetch_osm_building_form.py --help
```

Raw xBD imagery and labels are not redistributed in this repository. You need your own permitted xBD/xView2 data access and then pass the local label paths to `src/01_parse_xbd_labels.py`.

OpenStreetMap and WorldPop steps depend on external services and may vary with service availability, current OSM coverage, and network state.

## Environment

The recommended conda environment is:

```bash
conda env create -f environment.yml
conda activate city
```

The main workflow does not require GPU. Optional VLM experiments, if added later, must explicitly use:

```bash
CUDA_VISIBLE_DEVICES=0
```
