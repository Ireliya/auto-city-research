# Study Overview Figure Contract

## Purpose

Create one graphical overview shared by the English paper, Chinese competition
report, and public project website. The visual must explain geographic scope,
spatial-scale rebuilding, and the fixed evidence funnel without expanding the
scientific claim.

## Evidence Contract

- Geographic scope: four selected xBD event footprints, not global coverage.
- Spatial example: the same real Mexico candidate area at independently rebuilt
  250 m, 500 m, and 1,000 m grids.
- Audit universe: 99,629 buildings and 1,448 reference 500 m cells.
- Diagnostic counts: 73 percentile-rule and 115 exact top-20% disagreements.
- Final cross-definition result: four non-temporal candidates, all in Mexico.
- Historical OSM result: zero candidates have temporal support.
- External proxies: mixed and construct-specific; they remain outside the
  candidate-selection funnel.

## Visual Contract

- Panel a: Natural Earth world map with exact event-footprint centroids and
  direct labels.
- Panel b: common geographic crop with building points and grid boundaries at
  all three analysis scales. The focus cell is retained at 500 m and 1,000 m,
  but not at 250 m.
- Panel c: fixed-gate audit from all cells to diagnostic disagreements, robust
  non-temporal candidates, and temporal support.
- White publication background, editable SVG text, color-blind-conscious event
  colors, direct labels, and grayscale export.
- Website hero uses the same event locations on a dark bitmap map and leaves
  unframed space for the title and research question.

## Claim Boundary

The figure visualizes disagreement among rankings. It must not state or imply
that the workflow estimates true unmet need, identifies an ethically correct
allocation, provides global disaster coverage, or constitutes an operational
dispatch model.

## Reproduction

Run `python src/27_make_study_overview.py` in the server `city` environment.
The script writes publication files, website map assets, compact website data,
and a SHA-256 manifest from frozen project outputs.
