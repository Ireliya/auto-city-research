# Dataset And Download Notes

Dataset repository:

<https://huggingface.co/datasets/Ireliya/auto-city-research>

## What Is In The Downloadable Dataset

The Hugging Face dataset is intended to contain lightweight reproducibility artifacts:

- `data/derived/xbd_core_v1/`: parsed xBD building label tables and event summaries
- `data/derived/xbd_damage_grid_v1/`: 500 m damage grid
- `data/derived/osm_context_v1/`: OSM road and facility context joined to the grid
- `data/derived/worldpop_context_v1/`: WorldPop population exposure joined to the grid
- `data/derived/priority_mismatch_v1/`: primary damage-only vs need-aware mismatch outputs
- `data/derived/mismatch_drivers_v1/`: driver-profile tables
- `data/derived/robustness_v1/`: threshold and scenario-consensus robustness checks
- `data/derived/strict_budget_v1/`: exact top-k budget robustness checks
- `data/derived/osm_building_form_v1/`: independent OSM building-form robustness checks
- `reports/figures/`: publication figures
- `reports/pdf/`: PDF exports of paper/report/data notes
- `records/evidence_index.csv`: claim-to-evidence ledger

## What Is Not Redistributed

The repository does not redistribute raw xBD satellite imagery or raw source rasters. Users who want to rebuild from the raw source layer must obtain the source datasets under their own permitted access and licensing terms.

## Download

From the GitHub repository root:

```bash
python scripts/download_data.py
```

The script downloads the Hugging Face dataset snapshot into the local project tree while avoiding the dataset card overwrite of the GitHub README.

## License Boundary

Code is released under the MIT License. Reports and project documentation are released under CC BY 4.0 unless a file states otherwise.

The downloadable data artifacts combine derived information from xBD/xView2, WorldPop, OpenStreetMap, and other public/open data sources. Their use remains subject to the upstream data terms. For source-specific notes, see `reports/data_access_license_notes.md`.
