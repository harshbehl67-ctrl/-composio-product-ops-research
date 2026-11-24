# Composio integration evidence

A documentation-based survey of 100 apps across 10 categories for the [AI Product Ops take-home assignment](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). The single-file case study is `index.html`; it embeds the app data and exports filtered JSON and CSV from the page.

## Live page

[Open the current GitHub Pages URL](https://harshbehl67-ctrl.github.io/-composio-product-ops-research/)

The hosted URL must be opened after the reviewed update is published; the existing deployment may still serve an older version.

## Findings

- 100 apps across 10 categories; 496 of 500 vendor-field answers have a cited source.
- 64 apps meet the documented build-candidate rule; 60 are easy wins with free or trial prototype access and a broad or moderate API.
- 36 apps document a production gate: paid plan (19), admin approval (8), app review (6), or partner/sales (3).
- The normalized access table shows free/trial prototype access for 78 apps and free/trial production access for 62; 16 apps move into a production gate.
- Composio lists 80 of the 100 apps; 20 are not listed. Auth-scheme comparison is reported separately from vendor auth.
- Vendor MCP research distinguishes hosted actions, docs/read-only, local/self-hosted, beta/EAP, prelaunch, none, and unresolved cases.
- The Firecrawl-through-Composio result is a small six-page illustration, not a benchmark: direct retrieval reproduced 4 stored quotes and Firecrawl reproduced 5.

## Gold validation and limits

The 80-row gold covers four fields across 10 selected apps and 10 random holdout apps. The saved record says labels came from a separate AI session using frozen page excerpts; the model/session identity was not recorded. No independent human check of the gold is recorded. The merge script reads only `private/labels_returned.csv`, not `human_log.json`, so there is no direct mechanical import of that log. However, `human_log.json` contains earlier Google Ads auth/access decisions for an app also in the gold set, and the saved files do not establish whether those earlier chat labels were excluded from the separate labeling session. `gold_source_recheck_v1.json` records an AI source re-check of 24 seeded rows; it is neither a human agreement measure nor blind to the saved labels. It found 16 directly supported rows, 2 current-source conflicts, and 6 partial or inconclusive cases. Some conflicts may reflect source changes since the excerpts were frozen.

The final pass scored 60/74 scoreable gold rows answered (75.0% coverage), 61.7% strict precision (37/60), 80.8% half-credit (37 correct plus half of 23 partial), and zero incorrect answers. The remaining 6 gold rows are unresolved and 14 are not stated in the frozen evidence. Selected and holdout results are split on the page. These figures are descriptive of this small sample.

This is documentation research. Vendor credentials and production integrations were not tested. A Composio-hosted MCP session was used for the research workflow; its search tool discovered Firecrawl tools, but the project did not have an active Firecrawl account connection during that recorded run.

## Run the demo

```bash
python run_submission_demo_v4.py
```

The deterministic offline output is captured in `run_submission_demo_sample_v4.json`. For a live single-app research run, configure `COMPOSIO_API_KEY` in a local `.env` file and use `python run_one.py --app "Stripe"`. Do not commit `.env`; it is ignored by Git.

## Reproduce

Python 3.10+ and Node.js 18+ are required. Install Python dependencies with `python -m pip install -r requirements.txt`.

```bash
python build_case_v4.py
python -m unittest discover -v
node test_page_v4.cjs
python scan_secrets.py
```

The page generator derives counts from `checked_dataset_v4.json`, the access labels, and saved gold-scoring outputs. Source excerpts and detailed research files are retained in the repository; review the staged file list before publishing.
