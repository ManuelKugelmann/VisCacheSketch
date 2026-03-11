# Paper Sketch — Multilevel Visibility Hash Filter

This is the markdown-based paper sketch for the VisCacheSketch project. Each section is maintained as a separate file for easier editing.

> **CI auto-combines** all `sections/*.md` files (sorted by filename) into `paper-combined.md` via `.github/workflows/paper.yml`, then deploys an HTML preview to GitHub Pages. Edit individual section files — the combined output is generated automatically.

## Sections

| # | Section | File |
|---|---------|------|
| — | [Front Matter (title, abstract, keywords)](sections/00-front-matter.md) | `sections/00-front-matter.md` |
| 1 | [Introduction](sections/01-introduction.md) | `sections/01-introduction.md` |
| 2 | [Related Work](sections/02-related-work.md) | `sections/02-related-work.md` |
| 3 | [Data Structure](sections/03-data-structure.md) | `sections/03-data-structure.md` |
| 4 | [Addressing](sections/04-addressing.md) | `sections/04-addressing.md` |
| 5 | [Insert](sections/05-insert.md) | `sections/05-insert.md` |
| 6 | [Eviction and Temporal Decay](sections/06-eviction-and-temporal-decay.md) | `sections/06-eviction-and-temporal-decay.md` |
| 7 | [Lookup](sections/07-lookup.md) | `sections/07-lookup.md` |
| 8 | [Control Variate with Russian Roulette](sections/08-control-variate-with-russian-roulette.md) | `sections/08-control-variate-with-russian-roulette.md` |
| 9 | [ReSTIR Integration](sections/09-restir-integration.md) | `sections/09-restir-integration.md` |
| 10 | [Contribution-Weighted Revalidation](sections/10-contribution-weighted-revalidation.md) | `sections/10-contribution-weighted-revalidation.md` |
| 11 | [Cache-Free Alternatives](sections/11-cache-free-alternatives.md) | `sections/11-cache-free-alternatives.md` |
| 12 | [Runtime Statistics](sections/12-runtime-statistics.md) | `sections/12-runtime-statistics.md` |
| 13 | [Results](sections/13-results.md) | `sections/13-results.md` |
| 14 | [Conclusion](sections/14-conclusion.md) | `sections/14-conclusion.md` |
| — | [References](sections/references.md) | `sections/references.md` |

## PDF generation

Moving to LaTeX. The old reportlab-based `generate_paper.py` has been removed.
