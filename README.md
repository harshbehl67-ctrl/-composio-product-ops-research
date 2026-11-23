# Composio integration evidence — work in progress

This repository contains a candid partial response to the [assignment](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). `index.html` is a self-contained static page, explicitly marked incomplete. It is not a submission-ready research result.

## What is saved

- `apps.json`, `assignment_blocks.json`: exact 100-app list and assignment snapshot. `assess.py` asserts 100 unique apps and ten category coverage in the sample.
- `data/001.json` … `data/100.json`: immutable initial source-discovery pass, including original first-pass abstentions and validation errors. `research.py --force` writes timestamped reruns, preserving the baseline.
- `data/discovery/` and `candidate_triage.json`: second search and evidence candidates. Keyword snippets are triage, not verified vendor claims.
- `catalog_snapshot.json` and `catalog_aliases.json`: public Composio catalog and 16 product-name alias matches. The original snapshot remains untouched; alias matches require scope review. `data/catalog/` saves catalog pages. Composio catalog entries are separate from vendor MCP servers.
- `review.json`, `extra_review.json`, `data/review_sources/`, `six_field_review.json`: independent AI-assisted documentation review and source text. The ten-app sample spans ten categories and logs six baseline fields per app; 25 of 60 have at least partial supporting evidence, 35 remain unresolved. Original answers: 60 abstained, 0 answered. Accuracy on answered claims is undefined (0/0). There is no holdout experiment or claimed improvement.
- `assessed_dataset.json`: current partial structured dataset, with each field's sources/status and explicit unknowns. `build_case.py` produces `index.html` from it. `link_checks.json` saves HTTP availability checks; an HTTP response does not establish that a claim is true.

## Reproduce

Python 3.10 or later: `python -m pip install -r requirements.txt` (requests and BeautifulSoup). No API key is required for the saved workflow.

- Small run: `python research.py --app "Slack"` (resumes saved baseline). Use `--force` for a timestamped rerun.
- Full initial search: `python research.py --workers 8`. Existing records are preserved.
- Additional domain discovery: `python discover.py`; candidate indexing: `python triage.py`.
- Refresh public catalog: first back up `catalog_snapshot.json`, then `python catalog_check.py`. Resolve selected aliases with `python aliases.py`; retrieve matched toolkit pages using `python catalog_details.py`.
- `python review_sources.py` captures the original reviewed docs. `review.json` preserves the prior review; `extra_review.json` records the later vendor MCP and CLI source checks.
- Regenerate partial data and the one-page case study: `python assess.py` followed by `python build_case.py`.
- HTTP link check: `python check_links.py`.
- Browser smoke tests: `npm install --no-save --no-package-lock playwright`, then `node test_page.cjs` (requires Chrome at the path in that file). These test 1440px/390px table interaction, keyboard details, and JSON/CSV export; they are not a complete accessibility audit.

## Remaining work and deployment

Candidate pages still need source-specific review across all 100 apps. 97 of 100 build verdicts remain unknown; most auth, access, API, and vendor MCP fields remain unknown. The six-field sample is not fully resolved, the 16 alias matches need scope confirmation, and no credentials or live integrations were tested. These limitations prevent a defensible build-now/gated breakdown or an accuracy-improvement claim.

The Sites deployment attempt returned `sites_access_disabled`: Sites is not enabled for this workspace. No hosted source repository or verified live page exists. `index.html` can be served by any static host, but publishing it does not make its incomplete research submission-ready.
