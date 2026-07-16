# Data Access, Attribution, and Redistribution Notes

Team: **Auto-City-Research**  
Project website: [ireliya.github.io/auto-city-research](https://ireliya.github.io/auto-city-research/)  
Code: [github.com/Ireliya/auto-city-research](https://github.com/Ireliya/auto-city-research)  
Data: [huggingface.co/datasets/Ireliya/auto-city-research](https://huggingface.co/datasets/Ireliya/auto-city-research)

This document is a research-artifact inventory, not legal advice. It records source pages, attribution requirements, privacy handling, and the conservative redistribution boundary used by the project. No project-level license overrides the terms attached to an upstream source.

## 1. Release Policy

The competition package and public dataset include source code, fixed configurations, privacy-safe derived tables, selected derived geospatial layers, figures, reports, logs, and manifests. They do not include raw satellite imagery, raw source rasters, bulk map extracts, or individual assistance/claim records.

The Hugging Face repository must use a per-source data card rather than presenting every file under one blanket license. Code licensing is handled separately in the GitHub repository.

## 2. Source Ledger

| Source | Provider page | Applicable note | Public artifact | Not redistributed |
| --- | --- | --- | --- | --- |
| xView2/xBD | [CMU SEI xView2 project](https://www.sei.cmu.edu/projects/xview-2-challenge/) | SEI describes xBD as public-use Creative Commons data; this project conservatively treats xView-derived material as CC BY-NC-SA 4.0 and preserves attribution | Aggregated labels, grid tables, figures, and code | Raw pre/post-disaster satellite images and full source archive |
| WorldPop | [WorldPop FAQ](https://www.worldpop.org/faq/) | CC BY 4.0; attribution required; population surfaces are modeled estimates | Population-enriched grid values and audit summaries | Raw 100 m and 1 km GeoTIFFs |
| OpenStreetMap | [OSM copyright and license](https://www.openstreetmap.org/copyright) | ODbL 1.0; attribution to OpenStreetMap contributors; share-alike conditions may apply to derivative databases | Derived road, facility, and building metrics with attribution and reproducible extraction code | Bulk extracts, OSMnx caches, and tile caches |
| ohsome API | [ohsome API documentation](https://docs.ohsome.org/ohsome-api/stable/endpoints.html) | Historical extraction retains `© OpenStreetMap contributors` attribution and OSM licensing | Historical coverage summaries, grid metrics, and fetch log | Raw full-history responses beyond the study outputs |
| CDC/ATSDR SVI 2016 | [SVI documentation](https://www.atsdr.cdc.gov/place-health/php/svi/index.html) | US government public-health dataset; cite CDC/ATSDR and the release year | Harvey-intersecting tract scores and bootstrap metrics | Unused national/state source files |
| OpenFEMA NFIP Claims v2 | [NFIP claims dataset](https://www.fema.gov/openfema-data-page/fima-nfip-redacted-claims-v2) | Public redacted OpenFEMA data subject to OpenFEMA terms and citation requirements | Sums by intersecting Census tract and bootstrap metrics | Individual claim rows and statewide runtime cache |
| OpenFEMA RI-IHP v2 | [RI-IHP dataset](https://www.fema.gov/openfema-data-page/registration-intake-and-individuals-household-program-ri-ihp-v2) | Aggregated non-PII OpenFEMA data subject to OpenFEMA terms and citation requirements | One-table ZIP aggregates and bootstrap metrics | Source records outside the study aggregation |
| Census TIGER/Line | [US Census TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | US government work; Census requests source citation and supplies accuracy disclaimers | Joined geographic identifiers and result aggregates | Full downloaded geometry archives |
| CARTO basemap | [CARTO attribution](https://carto.com/attribution/) | Rendered map credits both CARTO and OpenStreetMap contributors | Attributed static case-map figure | Raster tile cache |

## 3. Source-Specific Handling

### xView2/xBD

xBD supplies post-disaster building polygons, ordinal damage labels, and event metadata. The public release uses derived annotation tables and grid aggregates, but deliberately excludes the satellite pixels. Every report cites the xBD paper and the CMU SEI project page. Any downstream user should obtain the source dataset through its official access route and follow the source terms.

Because the current official SEI summary states only “a Creative Commons license” without naming a version on that page, this project applies the more restrictive CC BY-NC-SA 4.0 treatment associated with the xView challenge family. The public data card must not relabel xBD-derived content as unrestricted or purely MIT-licensed.

### WorldPop

WorldPop states that its datasets are licensed under CC BY 4.0 and may be reused and redistributed with clear attribution. Even so, raw rasters are omitted to keep the competition package small and to make product/version selection explicit. Released tables contain only values spatially joined to the study grids, together with product identifiers and fetch manifests.

Required attribution: WorldPop, University of Southampton, with the product page and release metadata identified in the data card and paper bibliography.

### OpenStreetMap and ohsome

Current OSM features and pre-event ohsome snapshots are attributed to `OpenStreetMap contributors`. The project links to the ODbL and releases extraction code, filters, timestamps, derived tables, and manifests. Static maps carry visible OSM/CARTO attribution.

The project does not claim that an aggregated feature table escapes ODbL obligations. Public data documentation keeps OSM-derived files identifiable so downstream users can comply with attribution and share-alike requirements where applicable.

### CDC/ATSDR SVI

SVI is used as a pre-event social-vulnerability proxy for 149 Harvey-intersecting tracts. Only the fields needed for the audit and the resulting rank metrics are released. The report cites CDC/ATSDR and does not interpret SVI as realized post-disaster unmet need.

### OpenFEMA NFIP Claims

The NFIP acquisition script reads public redacted records, filters the Harvey period and Texas scope, and aggregates immediately to Census tract. The public output contains 149 intersecting tract rows covering 10,134 claims and aggregate monetary fields. It never writes or releases individual claim rows.

The output is an insured-property-loss proxy. Flood-insurance coverage, reporting, policy limits, and tenure affect interpretation.

### OpenFEMA RI-IHP

RI-IHP is drawn from one FEMA table and aggregated by ZIP to avoid combining owner/renter tables in a way that could double-count registrations. The released study output contains 41 ZIP aggregates and reports coverage thresholds and sample sizes. It remains subject to registration, eligibility, and administrative-process selection.

### Census TIGER/Line

Census boundaries provide spatial support for tract and ZIP association. US Census technical documentation states that US government works are not copyright-protected and asks users to cite the Census Bureau. The source also disclaims positional and attribute accuracy and notes that statistical boundaries are not legal land descriptions.

## 4. Included Files

- derived CSV and selected GeoJSON outputs;
- source and result manifests with checksums;
- figures in SVG, PDF, RGB PNG, and grayscale-check PNG;
- report PDFs and Markdown sources;
- scripts and fixed configurations;
- research, command, and AI collaboration logs;
- evidence index and package audit reports.

## 5. Excluded Files

- raw xBD satellite images and the full xBD archive;
- raw WorldPop GeoTIFFs;
- bulk OSM extracts, OSMnx caches, and raw ohsome response caches;
- CARTO or OSM raster tiles;
- individual NFIP claims or person/household assistance records;
- all-Texas or national intermediate caches not needed for aggregate audit;
- credentials, access tokens, IP addresses, passwords, private absolute paths, and shell history;
- temporary render directories and local environment files.

## 6. Public Dataset Card Requirements

The Hugging Face data card must state:

1. project title and team name `Auto-City-Research`;
2. exact GitHub repository and fixed code revision;
3. per-source licenses and attribution links;
4. that raw xBD imagery and raw WorldPop rasters are absent;
5. that NFIP and FEMA assistance outputs are aggregated and non-person-level;
6. that the data support an audit, not operational emergency allocation;
7. the four final candidates and the absence of historical OSM support; and
8. a machine-readable manifest with byte counts and SHA-256 hashes.

## 7. Reviewer Reproduction Route

Reviewers can reproduce the deterministic evidence without raw imagery:

```bash
git clone https://github.com/Ireliya/auto-city-research.git
cd auto-city-research
python scripts/reproduce_core.py --profile final
```

The command downloads the fixed Hugging Face revision, validates `MANIFEST.csv`, recomputes the core rankings and consensus, and checks exact candidate keys. Full source reconstruction additionally requires official source access and live public APIs.

## 8. Validity and Compliance Checks

Before public release and competition upload:

- verify every derived source is identified in the data card;
- verify OSM attribution is visible on maps and present in documentation;
- verify no source is assigned a more permissive license than its provider permits;
- scan tracked files and the ZIP for secrets, private paths, raw imagery, rasters, caches, and person-level records; and
- validate all manifest hashes and preserve the final public revisions and package SHA-256 with the upload receipt.
