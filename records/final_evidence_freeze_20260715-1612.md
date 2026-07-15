# Final Evidence Freeze

Record ID: `20260715-1612-final-evidence-freeze`

Status: scientific evidence and reviewer-facing documents complete. Delivery operations are tracked separately from this frozen scientific record.

## Claim Boundary

The project audits disagreement between damage-only rankings and transparent multi-source priority scenarios. It does not observe true unmet rescue or recovery need, infer a uniquely correct allocation, or provide an autonomous dispatch rule.

## Evidence Funnel

| Gate | Result |
| --- | ---: |
| xBD buildings parsed | 99,629 |
| Reference 500 m cells | 1,448 |
| WorldPop 100 m percentile-consensus disagreements | 73 |
| WorldPop 100 m exact Top-20% disagreements | 115 |
| Cells passing fixed non-temporal consensus gates | 4 |
| Cells with supportive historical OSM persistence | 0 |

The four retained cells are all in the Mexico earthquake footprint:

- `mexico-earthquake_500m_3_38`
- `mexico-earthquake_500m_17_2`
- `mexico-earthquake_500m_17_3`
- `mexico-earthquake_500m_18_3`

Each cell is supported by both population products, at least three of four damage baselines, policy-plausible disagreement probability of at least 0.80, and overlap at two or more spatial scales. Thresholds were fixed before candidate inspection and were not lowered to increase the candidate count.

## Population And Scale Evidence

- WorldPop 100 m covers all four event footprints with finite non-negative values and is the primary population surface.
- The 1 km product remains a separate resolution-sensitivity check; legacy invariants remain 67 percentile-consensus and 109 exact Top-20% disagreements.
- The analysis was rebuilt independently at 250 m, 500 m, and 1,000 m from building-level inputs for both population products.
- The population-resolution audit records event-level total differences, rank correlations, and Top-20% overlap rather than assuming the products are interchangeable.

## Historical OSM Evidence

Pre-event roads, facilities, and buildings were obtained through the ohsome API with explicit completeness and coverage gates. Failed or insufficient comparisons are never encoded as zero.

| Event | Evidence status |
| --- | --- |
| Hurricane Harvey | `not_assessable` |
| Mexico earthquake | `does_not_support` |
| Palu tsunami | `does_not_support` |
| Santa Rosa wildfire | `support` |

The four non-temporal candidates are in Mexico, so none is labeled temporally supported.

## External Construct Proxies

- CDC SVI covers 149 Harvey-intersecting tracts and measures pre-event social vulnerability.
- NFIP contains 10,134 privacy-safe aggregated claims across the same 149 tracts and measures insured property loss.
- FEMA RI-IHP uses one table and 41 ZIP aggregates to avoid owner/renter double counting; the principal 10% coverage analysis contains 14 units.
- Bootstrap intervals, coverage, and sample sizes are retained for every proxy comparison.
- The proxy results are mixed. No proxy is promoted to a ground-truth ranking and no negative comparison is removed.

## Compute And Environment

- All completed evidence generation is CPU-only.
- The reference conda environment is `city` with Python 3.11.
- Pandas, GeoPandas, Rasterio, PyProj, OSM/network, statistics, plotting, and serialization imports passed.
- The environment reads the 99,629-row xBD building table and has a valid PROJ data path.

## Figures And Documents

- Figures 1-12 are exported as editable SVG, vector PDF, 600 dpi RGB PNG, and RGB grayscale-check PNG.
- Grayscale exports were composited on white before conversion; all four corners are white and no black transparency bands remain.
- Final PDFs contain 13 pages for each English paper copy, 8 pages for the Chinese report, 4 pages for the reproducibility guide, 3 pages for the data-access note, 3 pages for the AI collaboration summary, and 4 pages for the presentation script.
- Every PDF was rendered to PNG and inspected for blank pages, clipping, overlap, broken glyphs, and opaque icon backgrounds.
- Branded reports contain clickable GitHub and Hugging Face annotations and use transparent PNG assets.

## Evidence Locations

- `data/derived/population_resolution_audit_v1/`
- `data/derived/evidence_hardening_100m_v1/`
- `data/derived/multiscale_100m_v1/`
- `data/derived/historical_osm_v1/`
- `data/derived/external_proxies_v1/`
- `data/derived/final_consensus_v1/`
- `reports/figures/fig11_consensus_audit.*`
- `reports/figures/fig12_external_proxy_divergence.*`
- `reports/paper_draft_en.md`
- `reports/competition_report_cn.md`

## Freeze Scope

This record freezes the scientific results and claim boundary. Public revision identifiers, clean-clone checks, CI runs, archive hashes, and the official upload receipt are recorded in the release and submission audits so delivery metadata can be updated without changing the evidence reported here.
