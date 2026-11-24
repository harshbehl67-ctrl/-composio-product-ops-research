# Composio integration evidence

A documentation-based survey of 100 apps across ten categories for the [AI Product Ops take-home](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). The interactive case study is [`index.html`](index.html); it embeds the reviewed app data and downloads JSON or CSV for the currently filtered rows.

## Review links

- [Open the case study](https://harshbehl67-ctrl.github.io/-composio-product-ops-research/)
- [Source repository](https://github.com/harshbehl67-ctrl/-composio-product-ops-research)

The page is static and works without local files, a login, or an API key. Its browser demo cannot start Python or an MCP server. Run those locally using the commands below.

## Findings

- 100 apps across ten categories; 496 of 500 vendor-field answers have a cited source.
- 64 apps meet the documented build-candidate rule; 60 are easy wins with free or trial access for prototype and production and a broad or moderate API.
- 36 apps document a production gate: paid plan (19), admin approval (8), app review (6), or partner / sales (3). The blocker ranking counts the 39 apps with a blocker, including sparse API docs (2) and no public API docs (1).
- The access table records free or trial access for 78 prototype paths and 62 production paths. The 16-app difference is the net change; individual apps can move in either direction.
- Composio lists 80 apps (69 exact names and 11 aliases); 20 are not listed. Vendor MCP availability is classified separately.
- The six-page Firecrawl-through-Composio comparison reproduced one more stored quote than direct retrieval (5 versus 4). This is a small illustration, not a benchmark.

## Gold score and provenance

The four-field gold contains 80 rows: 10 selected apps and 10 random holdout apps, four fields each. The final pass answered 60/80 rows (75.0% sample coverage). Of those, 60 are scoreable from the frozen reference; all 60 were answered (100% scoreable coverage). Strict accuracy is 37/60 (61.7%; Wilson 95% CI 49.0–72.9%); half-credit is 80.8%; there were zero incorrect answers. The other 20 frozen references are gold-unscoreable: 14 were marked not stated and six unresolved. These are excluded from accuracy, not counted as correct or incorrect.

The six-field score is secondary and uses a different denominator. Across three passes, its 232 non-correct ratings comprise 107 agent-caused misses and 125 ratings on gold-unscoreable references. In the final four-field pass, unresolved rows rose from four in pass one to 20 because pass one abstained on 50 rows while pass three answered all 80, exposing the full set of 20 unscoreable references.

Gold labels were AI-produced from frozen excerpts. The model and session identity were not recorded; the evidence that earlier assistant answers were withheld or earlier chat labels excluded is unverified. The author later status-checked 24 rows (12 selected, 12 holdout): 15/23 clear status labels agreed (65.2%), with one weak case; counting it as found gives 16/24 (66.7%). This same-author check is not independent and does not establish full value agreement. Five credential-gate checks rely on authentication evidence whose scope may not establish a gate. Three disputed gold rows remain disclosed separately: R032 Notion and R059 YouTube Transcript await human adjudication; R072 Snowflake remains `found` despite the author's spot-check disagreement. The frozen gold was not silently rewritten. See [`gold_provenance_v1.json`](gold_provenance_v1.json), [`human_gold_spotcheck_results_v1.json`](human_gold_spotcheck_results_v1.json), and [`current_source_adjudication_v1.json`](current_source_adjudication_v1.json).

## Run the demo

Python 3.10 or newer:

```bash
python -m pip install -r requirements.txt
python run_submission_demo_v4.py
```

The deterministic offline output is captured in [`run_submission_demo_sample_v4.json`](run_submission_demo_sample_v4.json). Run one saved app through the offline pipeline with:

```bash
python run_pipeline.py --mode offline --app "Google Ads"
```

For live collection and rechecking of existing claims, create a local `.env` containing `COMPOSIO_API_KEY=...`, then run:

```bash
python run_pipeline.py --mode live --app "Google Ads"
```

Live mode stores fresh discovery separately from revalidation of the existing checked record. New discovery text is not promoted to verified claims; human review is required. Keep `.env` private; it is ignored by Git. The static review page does not contain or need the key.

## Rebuild and checks

The published `index.html` is self-contained. Rebuild it from the checked records with `python build_case_v4.py`. Python checks run with `python -m unittest discover -p "test_*.py"`; browser checks run with `npm ci`, `npx playwright install chromium`, and `npm run test:browser`.

The project is documentation research. Vendor credentials and production integrations were not tested. No model identity is asserted where the audit record does not establish one.
