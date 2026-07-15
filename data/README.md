# Data Directory

This directory contains manifests and privacy-safe derived evidence for **Damage Is Not Need**. It does not contain raw xBD satellite imagery, raw WorldPop rasters, bulk OSM extracts, or person-level claim/assistance records.

## Main Derived Groups

- `derived/xbd_core_v1/`: parsed xBD building labels and event inventory.
- `derived/xbd_damage_grid_v1/`: reference 500 m physical-damage grid.
- `derived/worldpop_context_100m_v1/`: primary 100 m WorldPop join.
- `derived/worldpop_context_v1/`: 1 km WorldPop resolution comparison.
- `derived/priority_mismatch_100m_v1/`: primary multi-source priority-disagreement analysis.
- `derived/evidence_hardening_100m_v1/`: four damage baselines and weight uncertainty.
- `derived/multiscale_100m_v1/`: 250/500/1,000 m reconstruction.
- `derived/population_resolution_audit_v1/`: 100 m versus 1 km quality and rank audit.
- `derived/historical_osm_v1/`: pre-event OSM coverage and temporal sensitivity.
- `derived/harvey_external_validation_v1/`: privacy-safe NFIP tract evidence.
- `derived/external_proxies_v1/`: CDC SVI and FEMA assistance evidence.
- `derived/final_consensus_v1/`: fixed-gate final flags, four candidates, event summary, and manifest.

Directories without `_100m_` retain the earlier 1 km population analysis for reproducibility and resolution sensitivity. Earlier internal filenames containing `mismatch` remain stable for hash and schema compatibility; public interpretation is governed by `records/final_terminology_ledger.md`.

## Public Release

The Hugging Face repository contains the derived inputs required by:

```bash
python scripts/reproduce_core.py --profile final
```

Every public file is listed in `MANIFEST.csv` with byte count and SHA-256. Source-specific access and redistribution notes are in `reports/data_access_license_notes.md`.
