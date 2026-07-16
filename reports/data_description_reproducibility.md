# Data Description and Reproducibility Guide

Project: **Damage Is Not Need**  
Team: **Auto-City-Research**  
Project website: [ireliya.github.io/auto-city-research](https://ireliya.github.io/auto-city-research/)  
Code: [github.com/Ireliya/auto-city-research](https://github.com/Ireliya/auto-city-research)  
Data: [huggingface.co/datasets/Ireliya/auto-city-research](https://huggingface.co/datasets/Ireliya/auto-city-research)

## 1. Scope and Claim Boundary

This guide documents the data, derived artifacts, fixed configurations, execution order, and verification rules for the submission. The analysis asks where a damage-only post-disaster ranking disagrees with transparent multi-source priority scenarios that additionally represent population exposure, road accessibility, critical facilities, and urban form.

The output is a **priority-disagreement audit**. Neither the multi-source scenarios nor the external proxies are treated as true unmet-need labels, and the workflow is not an operational dispatch system.

The submission contains:

- English research paper: `reports/pdf/paper_en.pdf`;
- Chinese competition report: `reports/pdf/competition_report_cn.pdf`;
- AI collaboration summary and full logs;
- fixed code, configurations, manifests, derived evidence, and figures; and
- a claim-to-evidence ledger at `records/evidence_index.csv`.

## 2. Dataset Ledger

| Source | Role | Spatial/temporal use | Released artifact | Important boundary |
| --- | --- | --- | --- | --- |
| xView2/xBD | Building geometry and ordinal damage | Four event footprints; building and 250/500/1,000 m grid aggregation | Derived CSV/GeoJSON and manifests | Raw satellite imagery is not redistributed |
| WorldPop 100 m R2025A | Primary population exposure | Event-year national rasters intersected with each study grid | Population-enriched grid tables | Population is modeled exposure, not a household census |
| WorldPop 1 km Global1 | Resolution sensitivity | Same events and grids | Population-enriched grid tables | Retained as a lower-resolution comparison |
| OpenStreetMap current snapshot | Roads, facilities, buildings | Current mapped context for all events | Derived grid metrics and figures | Coverage and post-event edits may differ by place |
| ohsome API / OSM history | Pre-event roads, facilities, buildings | Snapshot immediately before each event | Event summaries, grid table, fetch log | Failed or low-coverage queries are never converted to zero |
| CDC SVI 2016 | Social vulnerability proxy | Harvey-intersecting Census tracts | Tract aggregates and bootstrap metrics | Measures vulnerability, not realized disaster need |
| OpenFEMA NFIP Claims v2 | Insured-property loss proxy | Harvey-period Texas claims aggregated to tracts | Privacy-safe tract aggregates and bootstrap metrics | Individual claims are never released |
| OpenFEMA RI-IHP | Assistance proxy | Harvey-relevant ZIP aggregates from one assistance table | ZIP aggregates and bootstrap metrics | Registration and payment processes introduce selection |
| Census TIGER/Line | Spatial support | Tracts and ZIP-compatible geographies | Only joined aggregates | Source geometries are fetched at acquisition time |

References and provider URLs are in `reports/references.bib` and `reports/data_access_license_notes.md`.

## 3. Study Inventory

| Event | xBD buildings | 500 m cells | WorldPop year/product |
| --- | ---: | ---: | --- |
| Hurricane Harvey | 23,014 | 612 | USA 2017, 100 m primary and 1 km check |
| Mexico earthquake | 32,271 | 288 | Mexico 2017, 100 m primary and 1 km check |
| Palu tsunami | 31,394 | 196 | Indonesia 2018, 100 m primary and 1 km check |
| Santa Rosa wildfire | 12,950 | 352 | USA 2017, 100 m primary and 1 km check |
| **Total** | **99,629** | **1,448** | four event footprints |

The 100 m population join matched all 1,448 reference cells with no missing, non-finite, or negative values. Event totals and 100 m versus 1 km rank diagnostics are recorded in `data/derived/population_resolution_audit_v1/`.

## 4. Environment

The published analysis is CPU-only. The reference environment is recorded in `configs/environment_city.yml` and can be checked with:

```bash
python scripts/verify_city_environment.py
```

Core dependencies include Python 3.11, pandas, NumPy, GeoPandas, Shapely, PyProj, Rasterio, Fiona, Pyogrio, Rtree, Rasterstats, OSMnx, NetworkX, SciPy, scikit-learn, statsmodels, Matplotlib, Seaborn, PyArrow, and PyYAML.

On the reference server, `PROJ_DATA` points to the `city` environment's `share/proj` directory. `scripts/verify_city_environment.py` tests imports, coordinate transformation, raster support, graph support, and statistical routines.

## 5. Fixed Analysis Contract

The final audit is governed by `configs/evidence_hardening.yaml`, `configs/weight_scenarios.yaml`, and `configs/final_evidence.yaml`.

- Random seed: `20260715`.
- Reference selection budget: exact Top 20%, with `k = ceil(n x 0.20)` per event.
- Damage baselines: area-weighted severity, damage-weighted building area, damaged-building count, and severe/destroyed-building count.
- Weight analysis: 10,000 `Dirichlet(1,1,1,1)` draws and 10,000 policy-bounded draws.
- Policy bounds: damage weight 0.20-0.50; every other component at least 0.05.
- Population products: WorldPop 100 m and 1 km.
- Grid scales: 250 m, 500 m, and 1,000 m, each rebuilt from building-level inputs.
- External-proxy uncertainty: 1,000 fixed-seed bootstrap replicates.

A final robust disagreement must satisfy all non-temporal gates:

1. at least three of four damage baselines support the cell;
2. policy-bounded disagreement probability is at least 0.80;
3. the cell appears under both population products; and
4. its area overlaps disagreement evidence at two or more grid scales by at least 0.50.

Historical OSM evidence is reported separately as `support`, `does_not_support`, or `not_assessable`; its threshold is not lowered to increase the number of candidates.

## 6. Source-to-Result Pipeline

Run acquisition and full reconstruction from the project root in the following order when raw-source access is available:

```bash
python src/01_parse_xbd_labels.py
python src/02_build_xbd_damage_grid.py
python src/03_fetch_osm_context.py
python src/04_join_worldpop_population.py
python src/05_analyze_priority_mismatch.py
python src/06_profile_mismatch_drivers.py
python src/11_run_robustness_checks.py
python src/15_run_strict_budget_check.py
python src/17_fetch_osm_building_form.py
python src/18_run_baseline_weight_robustness.py
python src/19_run_multiscale_robustness.py
python src/20_validate_harvey_nfip.py
python src/22_run_historical_osm_sensitivity.py
python src/23_validate_svi_ihp.py
python src/26_audit_population_resolution.py
python src/24_build_final_consensus.py
python src/21_regenerate_publication_figures.py
```

Acquisition scripts expose command-line arguments for paths and output directories. The exact commands used on the reference server are retained in `logs/command_log.md`; public files use portable relative paths.

Main output groups:

| Output | Purpose |
| --- | --- |
| `data/derived/xbd_core_v1/` | building-level parsed labels and event inventory |
| `data/derived/worldpop_context_100m_v1/` | primary 500 m grid with 100 m population estimates |
| `data/derived/worldpop_context_v1/` | 1 km population-resolution check |
| `data/derived/priority_mismatch_100m_v1/` | primary scenario disagreement |
| `data/derived/evidence_hardening_100m_v1/` | damage-baseline and weight uncertainty |
| `data/derived/multiscale_100m_v1/` | independently reconstructed 250/500/1,000 m results |
| `data/derived/historical_osm_v1/` | pre-event OSM coverage and temporal sensitivity |
| `data/derived/harvey_external_validation_v1/` | NFIP tract aggregates and bootstrap metrics |
| `data/derived/external_proxies_v1/` | CDC SVI and FEMA assistance proxy metrics |
| `data/derived/final_consensus_v1/` | final gate flags, four candidates, event summary, and manifest |
| `reports/figures/` | editable SVG, vector PDF, 600 dpi RGB PNG, and grayscale checks |

Some internal columns and directories retain earlier `need_*` or `mismatch_*` names so published hashes and schema compatibility are not broken. Their public interpretation is always **multi-source priority scenario** or **priority disagreement**, as fixed in `records/final_terminology_ledger.md`.

## 7. Public One-Command Reproduction

The public route starts from released derived inputs, so it does not require redistribution of xBD imagery or repeated calls to mutable public APIs:

```bash
git clone https://github.com/Ireliya/auto-city-research.git
cd auto-city-research
python scripts/reproduce_core.py --profile final
```

The command performs six checks:

1. download the Hugging Face dataset revision fixed in `configs/public_release.yaml`;
2. verify file sizes and SHA-256 hashes from `MANIFEST.csv`;
3. run data and schema smoke tests;
4. recompute the legacy 1 km core and verify the published `67/109` invariants;
5. recompute the 100 m analysis, weight robustness, multiscale audit, and final consensus; and
6. verify the exact four released candidate keys and regenerate Figures 11-12.

For a local dataset already downloaded from the fixed revision:

```bash
python scripts/reproduce_core.py --profile final --skip-download
```

The reproduction report is written to `data/reproduced/core_v1/reproduction_report.json`. Time fields may differ; deterministic numerical outputs and candidate keys must not.

## 8. Verification Invariants

The final package and continuous-integration checks enforce:

- strict Top-k size equals `ceil(n x share)` for every event and threshold;
- all analysis metrics are finite;
- primary 100 m provisional counts are 73 by percentile consensus and 115 by exact Top 20%;
- legacy 1 km checks remain 67 and 109;
- the final event counts are Harvey 0, Mexico 4, Palu 0, Santa Rosa 0;
- no final candidate is labeled temporally supported;
- figure exports exist in all four required formats; and
- no raw imagery, raw claim records, credentials, private paths, or cache files enter the public package.

## 9. Reproducibility Levels

| Level | What can be reproduced | Requirements |
| --- | --- | --- |
| Public deterministic | Core rankings, robustness tables, final consensus, final evidence figures | GitHub code + pinned Hugging Face derived data |
| Full source reconstruction | xBD parsing, WorldPop joins, OSM acquisition, external proxy aggregation | Original source access and live public endpoints |
| Submission audit | PDFs, package manifest, hashes, path/secret checks | Complete competition project directory |

Network-dependent outputs are released with fetch logs and manifests. A failed API request is an error or `not_assessable`, never a zero observation.

## 10. Data Protection and Redistribution

Included:

- derived and aggregated tables;
- selected derived geospatial layers;
- scripts, fixed configs, logs, manifests, and checksums;
- reports and figures.

Excluded:

- raw xBD satellite imagery and full source archive;
- raw WorldPop rasters and bulk OSM extracts/caches;
- individual NFIP or FEMA assistance records;
- credentials, IP addresses, private absolute paths, and temporary files.

The public artifact supports scientific audit but does not replace provider-specific source access. See `reports/data_access_license_notes.md` for attribution and source-level restrictions.

## 11. Known Validity Boundaries

- No observed variable is a ground-truth label for unmet rescue or recovery need.
- The four retained cells are robust to the fixed non-temporal specifications but are not supported by historical OSM persistence.
- OSM completeness varies spatially and historically; one Harvey historical comparison is `not_assessable` under the fixed coverage rule.
- WorldPop is model-based and resolution-sensitive; NFIP, SVI, and FEMA assistance measure distinct selected populations and processes.
- The selected xBD footprints are not complete disaster extents, and the audit is neither causal evidence nor an autonomous allocation rule.
