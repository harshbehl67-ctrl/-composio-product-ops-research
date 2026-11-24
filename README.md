# Composio integration evidence

A documentation-based survey of 100 apps across 10 categories for the [AI Product Ops take-home assignment](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). The single-file case study is `index.html`; it embeds the app data and exports filtered JSON and CSV from the page.

## Live page

[Open the current GitHub Pages URL](https://harshbehl67-ctrl.github.io/-composio-product-ops-research/)

The hosted URL must be opened after the reviewed update is published; the existing deployment may still serve an older version.

## Findings

- 100 apps across 10 categories; 496 of 500 vendor-field answers have a cited source.
- 64 apps meet the documented build-candidate rule; 60 are easy wins: documented candidates with free or trial access for both prototype and production plus a broad or moderate API.
- 36 apps document a production gate: paid plan (19), admin approval (8), app review (6), or partner/sales (3).
- The normalized access table shows free/trial prototype access for 78 apps and free/trial production access for 62; 16 apps move into a production gate.
- Composio lists 80 of the 100 apps; 20 are not listed. Auth-scheme comparison is reported separately from vendor auth.
- Vendor MCP research distinguishes hosted actions, docs/read-only, local/self-hosted, beta/EAP, prelaunch, none, and unresolved cases.
- The Firecrawl-through-Composio result is a small six-page illustration, not a benchmark: direct retrieval reproduced 4 stored quotes and Firecrawl reproduced 5.

## Gold validation and limits

The 80-row gold covers four fields across 10 selected apps and 10 random holdout apps. The saved record says labels came from a separate AI session using frozen page excerpts; the model/session identity was not recorded. The author has since checked 24 rows, sampled 12 selected and 12 holdout from 47 eligible rows after exclusions; see [`human_gold_spotcheck_queue_v1.json`](human_gold_spotcheck_queue_v1.json): 15/23 clear status labels matched (65.2%), one row was marked weak, and the status-only rate is 16/24 (66.7%) if that weak row is counted as found. This is not full field-value agreement; five credential-gate entries cite authentication evidence. The author had previously seen assistant answers, so this is not an independent or blind check. See the [`row-level results`](human_gold_spotcheck_results_v1.json). The workspace merge procedure copies a separate returned-label CSV by row ID and does not mechanically merge the author-review log. However, that log records earlier Google Ads auth/access decisions for an app also in the gold set, and the saved audit trail does not establish whether those earlier chat labels were excluded from the separate labeling session. [`gold_source_recheck_v1.json`](gold_source_recheck_v1.json) records a separate AI source re-check of 24 rows, with 16 supported, 2 current-source conflicts, and 6 partial or inconclusive. Some conflicts may reflect source changes since the excerpts were frozen.

The final pass scored 60/74 scoreable gold rows answered (75.0% coverage), 61.7% strict precision (37/60), 80.8% half-credit (37 correct plus half of 23 partial), and zero incorrect answers. The remaining 6 gold rows are unresolved and 14 are not stated in the frozen evidence. Selected and holdout results are split on the page. These figures are descriptive of this small sample.

This is documentation research. Vendor credentials and production integrations were not tested. A Composio-hosted MCP session was used for the research workflow. The first session probe found no active Firecrawl account connection; a later Composio MCP → Firecrawl scrape completed a small six-page comparison, as reported above.

## Run the demo

```bash
python run_submission_demo_v4.py
```

The deterministic offline output is captured in `run_submission_demo_sample_v4.json`. For a live single-app research run, configure `COMPOSIO_API_KEY` in a local `.env` file and use `python run_one.py --app "Stripe"`. Do not commit `.env`; it is ignored by Git.

## Reproduce the offline demo

Python 3.10+ is required. Install dependencies with `python -m pip install -r requirements.txt`, then run:

```bash
python run_submission_demo_v4.py
```

This runs the Google Ads example against saved evidence and the saved Composio catalog snapshot, with no network requests or credentials. The captured output is in `run_submission_demo_sample_v4.json`. The published `index.html` is self-contained. Rebuilding the research page requires the full local audit inputs and is not needed to run this demo.
