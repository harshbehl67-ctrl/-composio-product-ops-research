# Composio integration evidence

Final official-documentation audit for the [AI Product Ops take-home assignment](https://composio.notion.site/AI-Product-Ops-Intern-The-take-home-assignment-391f261a6dfe80e9946bee899d3a3762). The self-contained case study is `index.html`; every displayed count is generated from `checked_dataset_v4.json`.

## Live page

https://harshbehl67-ctrl.github.io/-composio-product-ops-research/

## Results

| Measure | Result |
|---|---:|
| Apps / categories | 100 / 10 |
| Checked vendor-field claims | 496 / 500 |
| Checked Composio toolkit claims | 100 / 100 |
| Documented build candidates | 64 |
| Gated build candidates | 30 |
| Partner / sales outreach | 3 |
| Wrapper or CLI path | 2 |
| Unresolved verdict | 1 |
| Vendor-operated MCP servers documented | 92 |
| Scoped no-vendor-server documentation findings | 8 |
| Composio exact / alias / not listed | 69 / 11 / 20 |

Coverage is 99/100 for authentication, credential access, API surface, and buildability; 100/100 for vendor MCP and Composio toolkit status. The remaining unresolved app is Fanbasis, now Commas: current public pages document APIs and an MCP beta but omit API authentication, credential issuance, protocol, and endpoint breadth, while the legacy API Docs site is password-protected.

These are documentation findings, not live credential tests. No paid account, production token, admin approval, partner agreement, SDK runtime, or MCP runtime was tested.

## Evidence model

Each checked field contains:

- a controlled value and scoped reason;
- exact official URL, quotation, title, and retrieval date;
- publication/update date or an explicit undated label;
- source-review metadata when direct retrieval required rendered-browser verification.

Vendor MCP is classified separately from Composio listings. `no_vendor_server_documented` is a scoped documentation finding, not universal absence. Unknown is retained only where targeted first-party research could not resolve the field.

## Preserved research

- `data/001.json`–`data/100.json`: immutable baseline discovery pass.
- `data/pass2/`, `data/pass8/`–`data/pass12/`: frozen extraction/replay passes and reruns.
- `data/checked_research_raw/`: raw snapshots of all ten final category files before review edits.
- `data/checked_research/`: reviewed category records and independent selected/holdout review logs.
- `source_review_v4.json` and `data/source_review_group_*_v4.json`: exact replacements, reclassifications, record updates, and rendered-page keeps.
- `research_pass_manifest.json`: hash manifest for preserved research artifacts.
- `security_example_review.json`: first-commit Zendesk bearer-example audit.
- `redaction_log.json`: public documentation token examples redacted before publication, including two GitHub push-protection findings.

## Independent six-field review

The deliberately selected ten-category sample and seeded random holdout are reported separately.

| Cohort | Answered | Correct | Partial | Incorrect | Abstained | Strict | Half-credit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Selected sample | 33/60 | 19 | 12 | 2 | 27 | 19/33 (57.6%) | 25/33 (75.8%) |
| Random holdout | 26/60 | 14 | 8 | 4 | 34 | 14/26 (53.8%) | 18/26 (69.2%) |

Abstained and unresolved claims are excluded from accuracy denominators. The original baseline answered 0/60, so its answered-claim accuracy is undefined (0/0); no baseline accuracy-improvement claim is made.

## Reproduce

Python 3.10+ and Node.js 18+ are sufficient. Install Python dependencies with `python -m pip install -r requirements.txt`.

```bash
python -m unittest discover -v
python normalize_checked_research_v4.py
python apply_research_followups_v4.py
python merge_source_review_v4.py
python apply_source_review_v4.py
python assemble_checked_v4.py
python verify_checked_sources.py --review source_review_v4.json
python check_links_v4.py --review source_review_v4.json
python check_independent_links_v4.py --review independent_link_review_v4.json
python score_review_v4.py
python scan_secrets.py
python build_case_v4.py
```

The source verifier uses visible HTML text and explicit Markdown/plain-text/JSON/XML artifacts. Raw HTML, scripts, navigation, and hidden elements do not validate quotations. Direct 403/404 results pass only when every checked use has an exact rendered-browser keep.

## Browser tests

The page tests use installed Chrome at the path configured in `test_page_v4.cjs`.

```bash
python -m http.server 8765 --bind 127.0.0.1
CASE_URL=http://127.0.0.1:8765 node test_page_v4.cjs
```

The suite checks 1440px and 390px layouts, all filters, empty search, sorting, keyboard evidence details, no horizontal overflow, parsed JSON/CSV exports, formula-injection neutralization, raw-research exclusion, 100 unique apps, and the 60-claim holdout view.

## Validation summary

- 41 Python regression tests pass.
- 592 unique dataset evidence URLs: zero broken checked links and zero unreviewed checked quote failures.
- 123 independent-review URLs: zero unresolved; four Salesforce 403 responses are rendered-browser verified.
- 1,728 files scanned: 42 credential-shaped occurrences, all inside preserved research; zero outside.
- Desktop and mobile Playwright tests pass locally and on the live GitHub Pages URL with no script errors.

See `research_diagnostics.md` for the full diagnosis, final counts, and limitations.
