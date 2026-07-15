# Dataset And Download Notes

Dataset repository: [huggingface.co/datasets/Ireliya/auto-city-research](https://huggingface.co/datasets/Ireliya/auto-city-research)

Pinned revision: `0c56e1d43158e7b769316bee46a162c40a62d1d2`

## Included

- parsed xBD/xView2 building-label tables and reference grids;
- WorldPop 100 m primary and 1 km comparison joins;
- four-baseline and weight-uncertainty outputs;
- independently rebuilt 250, 500, and 1,000 m analyses;
- current and pre-event OSM aggregate evidence;
- privacy-safe NFIP, CDC SVI, and FEMA RI-IHP aggregate tables;
- fixed-gate consensus candidates and manifests;
- 12 figures in SVG, vector PDF, 600 dpi PNG, and grayscale-check PNG;
- English and Chinese report PDFs and final evidence ledgers.

## Excluded

- raw xBD satellite imagery and the full xBD archive;
- raw WorldPop GeoTIFFs;
- bulk OSM extracts, tile caches, and raw service-response caches;
- individual NFIP claims or person/household assistance records;
- credentials, private paths, and temporary files.

## Download

From the GitHub repository root:

```bash
python scripts/download_data.py
```

The script preserves the GitHub README while restoring the pinned evidence files into their expected relative paths. The root `MANIFEST.csv` records SHA-256 and byte counts for every dataset-repository file except itself.

## Source Terms

The code is MIT licensed. No blanket license is asserted over combined derived data. xBD/xView2, WorldPop, OpenStreetMap/ohsome, CDC SVI, OpenFEMA, and Census-derived artifacts remain subject to their upstream terms and attribution requirements.

See `reports/data_access_license_notes.md` and `data/manifests/auxiliary_data_sources.csv` for the source-by-source ledger.
