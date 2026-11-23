# Composio integration evidence — work in progress

This repository contains a candid partial response to the [assignment](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). `index.html` is a self-contained static page, explicitly marked incomplete. It is not a submission-ready research result.

## What is saved

- `apps.json`, `assignment_blocks.json`: exact 100-app list and assignment snapshot. `assess.py` asserts 100 unique apps and ten category coverage in the sample.
- `data/001.json` … `data/100.json`: immutable initial source-discovery pass, including original first-pass abstentions and validation errors. `research.py --force` writes timestamped reruns, preserving the baseline.
- `data/discovery/` and `candidate_triage.json`: second search and evidence candidates. Keyword snippets are triage, not verified vendor claims.
- `catalog_snapshot.json` and `catalog_aliases.json`: public Composio catalog and 16 product-name alias matches. The original snapshot remains untouched; alias matches require scope review. `data/catalog/` saves catalog pages. Composio catalog entries are separate from vendor MCP servers.
- `review.json`, `extra_review.json`, `data/review_sources/`, `six_field_review.json`: independent AI-assisted documentation review and source text. The deliberate ten-app sample spans ten categories. The original baseline answered 0/60, so its answered-claim accuracy is undefined (0/0). The separate new pass answered 26/60; independent AI-assisted review rated 19 correct and 7 partial. With half-credit for partial answers, this is 22.5/26 (86.5%), or 19/26 (73.1%) with strict full credit. This selected sample is not a random holdout or a population accuracy estimate. See `pass2_review.json`.
- `reviewed_dataset.json`: current partially reviewed structured dataset, with each field's sources/status and explicit unknowns. `build_case.py` produces `index.html` from it. `remaining_unknowns.json` records an app-by-app reason for unresolved fields. `link_checks.json` saves HTTP availability checks; an HTTP response does not establish that a claim is true.

## Reproduce

Python 3.10 or later: `python -m pip install -r requirements.txt` (requests and BeautifulSoup). No API key is required for the saved workflow.

- Small run: `python research.py --app "Slack"` (resumes saved baseline). Use `--force` for a timestamped rerun.
- Full initial search: `python research.py --workers 8`. Existing records are preserved.
- Additional domain discovery: `python discover.py`; candidate indexing: `python triage.py`.
- Refresh public catalog: first back up `catalog_snapshot.json`, then `python catalog_check.py`. Resolve selected aliases with `python aliases.py`; retrieve matched toolkit pages using `python catalog_details.py`.
- `python review_sources.py` captures the original reviewed docs. `review.json` preserves the prior review; `extra_review.json` records the later vendor MCP and CLI source checks.
- Regenerate the reviewed dataset and page: `python review_pass2.py`, `python assemble_reviewed.py`, `python summarize_pass2.py`, then `python build_case.py`. `python assess.py` regenerates the earlier baseline assessment.
- HTTP link check: `python check_links.py`.
- Browser smoke tests: `npm install --no-save --no-package-lock playwright`, then `node test_page.cjs` (requires Chrome at the path in that file). These test 1440px/390px table interaction, keyboard details, and JSON/CSV export; they are not a complete accessibility audit.

## Remaining work and deployment

Candidate pages still need source-specific review across all 100 apps. 85 of 100 build verdicts remain unknown; most auth, access, API, and vendor MCP fields remain unknown. The six-field sample is not fully resolved, the 16 alias matches need scope confirmation, and no credentials or live integrations were tested. These limitations prevent a defensible build-now/gated breakdown or an accuracy-improvement claim.

The Sites deployment attempt returned `sites_access_disabled`: Sites is not enabled for this workspace. The source repository has been pushed to https://github.com/harshbehl67-ctrl/-composio-product-ops-research. No verified live case-study page exists. `index.html` can be served by any static host, but publishing it does not make its incomplete research submission-ready.

## New targeted research pass

`data/new_search/NNN.json` contains three targeted query strings and search output for each of the 100 apps. Those searches were executed using the connected web-search service; no standalone API key or portable search client was available, so live discovery itself is not reproducible from this repository alone. The exact saved output is the input to the reproducible extractor. `python improved_pass.py --workers 12` resumes the saved new pass. `python improved_pass.py --app "Slack" --force` fetches new material into a timestamped rerun without overwriting the baseline or frozen pass 2.

`data/pass2/NNN.json` preserves candidates, up to six fetched pages, text, tentative answers, and per-field source excerpts. Across 100 apps it extracted provisional auth claims for 56, API-surface claims for 28, vendor-MCP claims for 65, and catalog matches for 77. These are extraction coverage, not verified findings: source-context errors exist, and access-gate and verdict extraction were not implemented in that pass. `python refine_access.py` scans the frozen pages for 26/100 possible access-condition excerpts in `data/pass3/`, but these remain candidates, not verified claims.

`python review_pass2.py`, `python assemble_reviewed.py`, and `python summarize_pass2.py` build the sampled review, independently corrected partial dataset, and app-by-app unknown reasons. The corrected dataset has 15 scoped buildability decisions and 85 unknown verdicts. `python build_case.py` regenerates the incomplete self-contained case study. `redaction_log.json` records credential-shaped strings removed from newly retrieved public material before publication.
