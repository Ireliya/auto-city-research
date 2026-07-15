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
- `multiscale_500m_top20_total: 109`
- `harvey_nfip_intersecting_tracts: 149`
- `harvey_nfip_claims: 10134`

## Level 2: Rebuild Derived Analysis From Downloaded Tables

This level uses the pinned Hugging Face derived tables and regenerates priority tables, robustness checks, and figures with one command.

```bash
python scripts/reproduce_core.py
```

The orchestrator supplies the required paths to scripts `05`, `06`, `07`, `11`, `15`, `18`, and `19`, verifies the downloaded manifest, and asserts the `67/109` invariants. Script `19` uses released prepared 250/500/1000 m grids, so the scale analysis is offline and deterministic at this level. This level is CPU-only.

## Level 3: Rebuild From Raw/Public Sources

This level reruns source ingestion and public-data joins:

```bash
python src/01_parse_xbd_labels.py --help
python src/02_build_xbd_damage_grid.py --help
python src/03_fetch_osm_context.py --help
python src/04_join_worldpop_population.py --help
python src/17_fetch_osm_building_form.py --help
python src/19_run_multiscale_robustness.py --help
python src/20_validate_harvey_nfip.py --help
```

Raw xBD imagery and labels are not redistributed in this repository. You need your own permitted xBD/xView2 data access and then pass the local label paths to `src/01_parse_xbd_labels.py`.

OpenStreetMap and WorldPop steps depend on external services and may vary with service availability, current OSM coverage, and network state.

The Harvey NFIP validation writes only Census-tract aggregates. It never saves individual insurance claim rows, and NFIP loss is interpreted as an insured-loss proxy rather than ground-truth unmet recovery need.

## Environment

The recommended conda environment is:

```bash
conda env create -f environment.yml
conda activate city
```

The published workflow is CPU-only and does not require GPU.
