# Project Website

This directory is the standalone GitHub Pages site for **Damage Is Not Need**.
It is intentionally built with static HTML, CSS, and JavaScript so the public
research explanation remains inspectable without a frontend build tool.

## Local preview

```bash
python3 -m http.server 4173 --directory docs
```

Open `http://127.0.0.1:4173/`.

## Generated assets

Run the following command in the server `city` environment to regenerate the
world map, cross-scale views, compact study JSON, brand copies, and scientific
figure copies used by this site:

```bash
python src/27_make_study_overview.py
```

The website must preserve the paper's claim boundary: it visualizes ranking
disagreement and does not claim to estimate true unmet need.
