# Bilingual Event Atlas And Figure Boundary Audit

Record ID: `20260715-2104-bilingual-event-atlas`

## Goal

Resolve three reviewer-facing defects without changing any scientific result:

1. Keep every label inside the fixed-gate overview boxes.
2. Make the four event tabs display four genuinely different event footprints.
3. Provide a complete English/Chinese website experience.

## Implementation

- Added render-time text measurement and font reduction to the overview flowchart.
- Regenerated four event-specific 500 m maps from each event's independently rebuilt grid.
- Added event-map paths to the frozen website data and study-overview manifest.
- Added a persistent language control covering headings, body copy, event content, evidence states, map captions, scale states, metadata, and accessibility labels.
- Added keyboard navigation for event and scale tabs.
- Added stable event-map dimensions and image-swap transitions to prevent layout movement.
- Extended package checks to require four distinct event maps and bilingual website markers.
- Flattened publication figures to RGB when embedding them in PDFs, removing a Poppler soft-mask compatibility defect while retaining transparent brand icons.

## Verification

- Browser QA passed at 1,440 x 1,000 and 390 x 844.
- English and Chinese layouts have no horizontal overflow or hero-text overlap.
- All four event tabs load different image paths and decoded images.
- Event text, evidence status, map caption, scale verdict, menu label, and figure-dialog label change with language.
- The overview flowchart contains all text inside its boxes.
- English paper: 14 pages rendered and inspected.
- Chinese report: 9 pages rendered and inspected with both Poppler and macOS Quick Look.
- Headline evidence remains 99,629 buildings, 1,448 cells, 73 percentile disagreements, 115 exact Top-20 disagreements, four non-temporal candidates, and zero temporally supported candidates.

## Evidence

- `docs/index.html`
- `docs/styles.css`
- `docs/script.js`
- `docs/data/study.json`
- `docs/assets/event_hurricane-harvey.png`
- `docs/assets/event_mexico-earthquake.png`
- `docs/assets/event_palu-tsunami.png`
- `docs/assets/event_santa-rosa-wildfire.png`
- `scripts/verify_website.mjs`
- `src/09_export_report_pdfs.py`
- `src/12_run_final_submission_audit.py`
- `src/27_make_study_overview.py`
- `reports/figures/study_overview_global_multiscale.png`
- `reports/pdf/paper_en.pdf`
- `reports/pdf/competition_report_cn.pdf`

## External Gate Status

GitHub Pages was activated by the repository owner. Deployment job `87522688191` completed successfully, and `https://ireliya.github.io/auto-city-research/` returned HTTP 200. A fresh public Playwright run passed English and Chinese interaction checks on desktop and mobile, while all four event maps returned HTTP 200 with distinct hashes. The official competition upload and receipt remain the only owner-authorized external actions.
