# Assignment checklist and evidence boundaries

| Requirement | Evidence / status |
|---|---|
| 100 apps across ten categories | `apps.json`; validated by `assemble_checked_v4.py` |
| Research pipeline and saved evidence | `research.py`, immutable collector artifacts, and `data/checked_research/`; live discovery is separate from claim validation |
| Official evidence for vendor fields | `checked_dataset_v4.json`; 496/500 vendor-field answers have cited sources |
| Contextual correction and source checks | `context_pass_v4.py`, `source_review_v4.json`, link-check artifacts, and cited claim records |
| Composio catalog vs vendor MCP | 80 catalog matches (69 exact, 11 aliases), 20 scoped not-listed results; vendor MCP tiers reported independently |
| Access, blocker, buildability, next action | 64 documented candidates; 60 easy wins. Prototype and production access are separate. Production blockers: paid plan 19, admin approval 8, app review 6, partner/sales 3; counts cover 36 gated apps. |
| Four-field AI-labeled gold | `gold_ratings_v4.json`, 80 rows from 10 selected and 10 holdout apps. Model/session identity is unrecorded; blinding and exclusion of earlier chat labels are unverified. |
| Gold accuracy | Final four-field pass: 60/80 answered (75% coverage), 60/60 scoreable answered, 37/60 strict (61.7%, Wilson 95% CI 49.0–72.9%), 80.8% half-credit, zero incorrect. Gold-unscoreable: 14 not stated and 6 unresolved. |
| Six-field secondary score | `gold_ratings_v4.json`; 3×120 claims. Pass 3: 81/120 scoreable answered (67.5%), strict 71.6% [61.0–80.3], half-credit 85.8% [76.6–91.8], fixed half 57.9%. Across all passes, 232 non-correct ratings split into 107 agent-caused misses and 125 gold-unscoreable ratings. |
| Human spot-check | `human_gold_spotcheck_results_v1.json`: same-author, non-independent status check of 24 rows. 15/23 clear labels agree (65.2%); one weak case; 16/24 (66.7%) if counted as found. Not full value agreement. |
| Source conflict review | `current_source_adjudication_v1.json`: three source conflicts recorded separately; frozen labels are not silently changed. |
| Human-authored override audit | `classification_overrides_v1.json`: classification decisions include reasons and claim-level source evidence where available. |
| Runnable one-app demo | `python run_submission_demo_v4.py`; output captured in `run_submission_demo_sample_v4.json`. `run_pipeline.py` has offline and live modes; fresh discovery remains separate and requires human review. |
| Interactive single page | `index.html`; table filters, sorting, responsive layout, and filtered JSON/CSV exports. |
| Public review and source | GitHub Pages page and public repository linked in `README.md`; deployment is verified after publishing. |
| Secret handling | `.env` is ignored and excluded from the static page. `scan_secrets.py` checks commit-eligible files without printing matched values. Historical documentation examples are distinguished from secrets. |
| Tests | Python unit tests and Playwright browser tests are part of the release check. |

The gold score is descriptive of a small sample. It is not an independent model benchmark: the labeling model is unknown, the human check is same-author and status-only, and some credential-gate checks cite authentication evidence that may not demonstrate a product-access gate. See the provenance and source-adjudication JSON files for row-level details.
