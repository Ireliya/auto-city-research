# Data Access and License Notes

Version ID: `20260711-0553-data-license-access-v1`

Purpose: document dataset access, attribution, redistribution boundaries, and current-submission limitations for the Urban Cup 2026 Competition 2 package.

This file is not legal advice. It is a reproducibility and submission-hygiene note that explains how the package uses public and competition data without redistributing large raw imagery or raw rasters.

## Summary

The submission package includes reproducible code, derived CSV/GeoJSON tables, figures, logs, and evidence records. It intentionally does not include raw xBD satellite imagery, raw WorldPop rasters, raw OSM extracts/caches, or raw GHSL rasters. Reviewers can audit the workflow from the included derived products and scripts, while raw-source access remains governed by each source provider's terms.

## Dataset Ledger

| Source | Role | Access or source page | License / use note | Included in package | Boundary |
| --- | --- | --- | --- | --- | --- |
| xView2 / xBD | Building damage labels, building geometry, event metadata | CMU SEI xView2 project page and xBD access page | SEI states that xBD is available for public use under a Creative Commons license; the project treats raw imagery as source data, not redistributable package content | Derived label tables, grid summaries, figures, code | Raw satellite images and full raw label archive are not copied into the submission package |
| WorldPop | Population exposure proxy | WorldPop website and catalog access endpoints | WorldPop datasets are treated as attribution-required open population data; the implemented workflow uses 1 km event-year rasters as an exposure proxy | Derived population columns joined to 500 m grid | Raw raster files are not redistributed |
| OpenStreetMap roads and amenities | Road accessibility and critical-facility context | OpenStreetMap data via OSMnx/Overpass-compatible retrieval | OSM data are open data under the Open Database License; package includes attribution and derived tables | Derived road/facility metrics and selected derived geospatial outputs | Raw OSM caches and full extracts are not redistributed |
| OpenStreetMap buildings | Independent building-form robustness | OpenStreetMap building footprints via OSMnx/Overpass-compatible retrieval | Same OSM attribution and ODbL boundary as roads/amenities | Derived OSM building-form tables and figures | Raw OSM building cache is not redistributed |
| GHSL | Optional built-up robustness route | European Commission / JRC GHSL download pages | GHSL is open/free with attribution; reuse requires source acknowledgement | Script and failed-source record only | No GHSL raster or result is claimed in the current submission |
| VIIRS | Optional economic-activity extension | EOG / VIIRS product pages | Not used in current results | Not included | Future extension only |

## Source-Specific Notes

### xView2 / xBD

xBD is the physical-damage foundation of the project. The current workflow uses post-disaster labels to build building-level and 500 m grid-level damage outputs. The submission package includes derived tables and scripts, but it does not include raw satellite imagery. This keeps the package lightweight and avoids redistributing large source imagery.

Attribution path:

- English paper bibliography: `reports/references.bib`
- Data description: `reports/data_description_reproducibility.md`
- Derived data: `data/derived/xbd_core_v1/` and `data/derived/xbd_damage_grid_v1/`

### WorldPop

WorldPop is used only as a population exposure proxy. The implemented workflow uses 1 km population rasters joined to the 500 m analysis grid. The package includes population-derived columns and fetch logs, not raw population rasters.

Attribution path:

- English paper bibliography: `reports/references.bib`
- Data description: `reports/data_description_reproducibility.md`
- Derived data: `data/derived/worldpop_context_v1/`

### OpenStreetMap

OpenStreetMap provides current roads, amenities, and building footprints. OSM is a present-day open map snapshot, so the project records time-alignment and mapping-completeness limitations. The package includes derived tables, figures, and relevant code, not raw OSM caches or bulk extracts.

Attribution path:

- English paper bibliography: `reports/references.bib`
- Data description: `reports/data_description_reproducibility.md`
- Derived data: `data/derived/osm_context_v1/` and `data/derived/osm_building_form_v1/`

### GHSL

GHSL is not part of the current result claims. A script is included as an optional robustness path, and the recorded attempt explains that official JRC/SEDAC source downloads were unavailable during the project run. Because no GHSL raster was successfully joined, no GHSL-derived table or figure is claimed.

Attribution path:

- Optional script: `src/16_join_ghsl_built_surface.py`
- Attempt record: `records/ghsl_download_attempt_20260711-0330.md`

## Redistribution Boundary

Included:

- Derived CSV tables
- Derived GeoJSON layers
- Result figures
- Report PDFs and Markdown sources
- Scripts
- Configs
- Logs and evidence records
- Package manifest and audit reports

Not included:

- Raw xBD satellite imagery
- Full raw xBD archive
- Raw WorldPop rasters
- OSMnx cache files
- Raw OSM extracts
- GHSL rasters
- Remote server paths, IP addresses, passwords, or other credentials

## Reviewer Reproduction Path

Reviewers can audit the current result without raw imagery by following:

1. `README_FIRST.md`
2. `submission/JUDGE_QUICK_START.md`
3. `reports/pdf/data_description_reproducibility.pdf`
4. `reports/pdf/paper_en.pdf`
5. `src/`
6. `configs/`
7. `data/derived/`
8. `records/evidence_index.csv`

Full raw-source reproduction requires access to the original xBD archive and public data endpoints. The package documents the expected paths and fetch scripts, but does not embed large source data.

## Known Limitations

- OSM roads, amenities, and building footprints are current snapshots and may contain edits after the disaster dates.
- WorldPop exposure is used at 1 km resolution and cannot resolve all within-cell variation in 500 m analysis cells.
- GHSL is scripted but not claimed because source downloads were unavailable during the recorded attempt.
- The package is a research audit artifact, not an operational emergency management data release.

## Verification

The final audit should confirm:

- The data-license note is present in the package.
- Raw satellite imagery and raw rasters are absent from the package.
- Package path privacy and secret scans pass.
- The manifest includes this file and its exported PDF.
