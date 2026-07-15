# Reproducibility Guide

## Immutable Inputs

The public dataset revision is fixed in `configs/public_release.yaml`:

```text
0c56e1d43158e7b769316bee46a162c40a62d1d2
```

`scripts/download_data.py` downloads only the derived data, figures, reports, manifest, and final evidence records needed by the public workflow. `MANIFEST.csv` is then checked by byte count and SHA-256.

## Level 1: Released-Table Audit

```bash
python -m pip install -r requirements.txt
python scripts/download_data.py
python scripts/smoke_reproduce.py
```

The smoke test verifies:

- 99,629 building rows and 1,448 reference cells;
- legacy WorldPop 1 km checks of 67 and 109 disagreements;
- WorldPop 100 m checks of 73 and 115 disagreements;
- the four exact final candidate keys and zero temporally supported candidates;
- population-quality, historical OSM, NFIP, SVI, and RI-IHP aggregate invariants;
- finite numeric values in the released result tables.

## Level 2: Deterministic Final Recalculation

```bash
python scripts/reproduce_core.py --profile final
```

This is the reviewer-facing route. It:

1. downloads and verifies the pinned snapshot;
2. recomputes the legacy 1 km analysis;
3. recomputes the 100 m primary analysis;
4. reruns the four damage baselines and 10,000 policy-plausible weight draws;
5. reruns the prepared 250, 500, and 1,000 m analyses for both population products;
6. rebuilds the fixed-gate consensus and verifies the four released candidate keys;
7. regenerates the consensus and external-proxy figures.

Randomized analyses use seed `20260715`. The route is CPU-only and writes outputs under `data/reproduced/core_v1/` and `reports/reproduced_figures/`.

## Level 3: Source Acquisition

Source acquisition can be rerun with the relevant scripts:

```bash
python src/01_parse_xbd_labels.py --help
python src/02_build_xbd_damage_grid.py --help
python src/03_fetch_osm_context.py --help
python src/04_join_worldpop_population.py --help
python src/17_fetch_osm_building_form.py --help
python src/20_validate_harvey_nfip.py --help
python src/22_run_historical_osm_sensitivity.py --help
python src/23_validate_svi_ihp.py --help
python src/26_audit_population_resolution.py --help
```

This level is intentionally not the per-commit CI path. It depends on independently obtained xBD labels and live public services whose availability and map coverage can change. Failed source requests are recorded as failures and are never converted to zero-valued observations.

## Claim Boundary

NFIP measures insured property loss, SVI measures social vulnerability, and RI-IHP measures registrations, eligibility, and assistance. None is a direct label of true unmet rescue or recovery need. Reproduction confirms the released disagreement audit; it does not turn these proxies into ground truth.
