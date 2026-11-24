# Research diagnostics and final validation

## Why the baseline abstained

My first script, `research.py`, had no extraction prompt and no model call. It searched once per app, fetched at most one hint-domain URL, and then just labelled every real field `unknown` or `unclear`. That empty discovery run is not used as an accuracy baseline; it measured a pipeline limitation, not research accuracy. My domain search often landed on homepages, login pages or unrelated product pages, and developer docs usually live on a separate vendor domain.

I left the original `data/001.json`–`data/100.json` untouched. Accuracy comparisons begin with the first pass that produced claims.

## Why relevant documentation still produced blanks

My first targeted extractor was deterministic. Its domain rule needed both a vendor-root match and an API/documentation-like path, so it threw away official pricing, credential, review and MCP pages sitting on other paths. It spent its six-page budget on topic labels instead of guaranteeing the five source types I needed. JavaScript shells, redirects, 403 responses, stripped navigation and truncation cut the usable text down further.

Extraction added a second bottleneck. I only scanned authentication on authentication-looking pages. My API check wanted the exact phrases “REST API” or “GraphQL API”, so it missed “HTTP API”, “RESTful APIs”, “GraphQL Admin API” and explicit statements that REST was not used. Pass 2 had no breadth classifier, no access-tier handling and no verdict logic at all, and my MCP check was just keyword and brand proximity: it could not tell a vendor server from a client connection, handled negation badly and did not keep source dates properly.

The new 100-app pass provisionally answered authentication for 56 apps, API surface for 28, vendor MCP for 65 and Composio catalog matches for 77. Those were extraction counts, not verified findings.

## Context-aware replay

I then wrote `context_pass_v4.py` to widen source ownership, scan API evidence beyond authentication-looking pages, recognise REST/GraphQL/HTTP/gRPC/SOAP with clause-local negation, estimate breadth from documented resource terms, and pull out free/trial/paid/admin/partner access conditions. It also splits MCP into `vendor_server`, `client_only`, `no_vendor_server_documented` and `unknown` — a Composio listing can never establish a vendor MCP.

My corrected frozen replay is `data/pass12/`. It provisionally answered auth 77, access 31, API surface 41, vendor MCP 30, Composio toolkit 77 and verdict 15. These are still extraction counts, and I kept all the earlier defective passes.

## Final checked dataset

All ten category files are complete and strictly validated:

- 100 unique apps across ten categories.
- 496/500 vendor-field claims checked.
- 100/100 Composio toolkit claims checked.
- 64 documented build candidates, 30 gated candidates, 3 partner/sales, 2 wrapper/CLI, 1 unresolved.
- 92 vendor-operated MCP servers and 8 scoped no-vendor-server documentation findings.
- 69 exact Composio listings, 11 alias listings, 20 point-in-time no-listing findings.

The only unresolved core fields are Fanbasis authentication, credential gate, API surface, and verdict. Fanbasis became Commas on 2026-07-14. Current first-party pages document APIs/SDKs and an MCP beta, but omit API authentication, credential issuance, protocol, and endpoint breadth. The legacy Fanbasis API Docs site is password-protected. The MCP finding is checked; the remaining unknowns are specific to inaccessible API details.

## Source and link verification

`verify_checked_sources.py` validates only visible HTML text or explicit Markdown/plain-text/JSON/XML artifacts. Scripts, navigation, hidden elements, and raw HTML do not validate quotations. It normalizes Markdown links, Unicode hyphens, punctuation spacing, and missing server charsets.

Final results:

- 592 unique dataset evidence URLs.
- 10 direct non-200/error results: nine checked Salesforce/PitchBook URLs with exact rendered-browser keeps, plus one unknown Fanbasis `/api` attempt retained as a 404.
- 96 quotations not reproduced by direct fetch; all are covered by 120 exact rendered-browser keeps.
- Zero unreviewed checked HTTP failures and zero unreviewed checked quotation failures.
- `link_checks_v4.json`: zero broken checked-evidence links; one failed attempted lookup retained for an unknown claim.
- `independent_link_checks_v4.json`: 123 unique independent-review URLs; four direct Salesforce 403 responses are rendered-browser verified; zero unresolved.

A 200 response alone never establishes truth, and a browser-rendered quote does not establish live account access.

## Independent six-field review

The deliberately selected ten-category sample remains separate from the seeded random holdout (`20261124`), drawn after pass 12 froze.

| Cohort | Answered | Correct | Partial | Incorrect | Abstained | Strict | Half-credit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Selected sample | 33/60 | 19 | 12 | 2 | 27 | 19/33 (57.6%) | 25/33 (75.8%) |
| Random holdout | 26/60 | 14 | 8 | 4 | 34 | 14/26 (53.8%) | 18/26 (69.2%) |

The per-pass numbers above leave out claims I abstained on or could not resolve. For the blind gold comparison, the first answer-producing extraction and final pass use the same fixed 120 claims: half-credit across all claims rises from 31.7% (pass 1) through 33.3% (pass 2) to 57.9% (pass 3), while scoreable coverage rises from 35% to 67.5%. Strict precision is conditional on answered claims and therefore falls from 81.0% to 71.6% as harder claims are added. In the separate 60-claim self-review, fixed-denominator half-credit rises from 35.8% to 41.7% on the selected sample and 28.3% to 30.0% on the random holdout. These metrics answer different questions and are kept separate. Exact ratings, corrections, and independent sources are in `independent_review_v4.json`; fixed-sample movement is in `first_pass_review_v4.json`.

## Blind gold set

A separate session labelled 80 app × judgment-field rows from frozen excerpts only, never seeing an agent answer. Of the 80 rows, 60 are `found`, 14 `not_stated_in_docs`, and 6 `unresolved`; one row was FETCH_FAILED (Gladly `credential_gate`, HTTP 404) and one was off-topic (Discord `credential_gate`, a `PAGE_OFF_TOPIC` marker with no usable text), both retained and reported. Scored over all 120 claims, the final pass has 81 scoreable (67.5%) with 71.6% strict [61.0–80.3] and 85.8% half-credit [76.6–91.8] at n=81; on a fixed denominator that counts unresolved and abstained claims as zero, half-credit moves from 31.7% (pass 1) through 33.3% (pass 2) to 57.9% (pass 3). All 232 non-correct rows carry a cause category, and 39 partial/ambiguous rows are queued for adjudication. Scoring audits fixed verdict defaults so missing evidence or missing API breadth cannot imply an access gate; API grading also honors explicit protocol negations in blind label notes. The four hand-labelled fields are `auth`, `credential_gate`, `api_surface`, `official_mcp`; `composio_toolkit` is scored against the catalog snapshot and `verdict` is derived by a written rule. The agent records vendor-MCP presence rather than the gold tier, so presence is scored and the tier stays visible; gold rows marked not stated or unresolved cannot score an answer either way. Credential-gate labels still have weak granularity (1/7 strict correct, six partial); many API-surface partials reflect missing SDK/breadth detail. See `gold_ratings_v4.json` and `gold_template.csv`.

## Publication safeguards

- Exact owner/repository allowlisting on GitHub and shared code hosts; arbitrary `github.io` sites are rejected.
- Unknown claims cannot retain positive gate, API, MCP, or listing metadata.
- Checked `not_listed` requires complete-catalog evidence and a scoped search note.
- `no_vendor_server_documented` requires an explicit review basis: scoped documentation review or explicit negation.
- The public page payload uses an allowlist and excludes raw passes, search responses, page text, and auth config.
- JSON/CSV exports are parsed and checked for 100 unique apps, required fields, raw-key exclusion, and formula-shaped cells.
- Source-review application is idempotent, including chained replacements and reclassifications.
- All final category files and generated artifacts are eligible for the hash manifest.

## Security review

The bearer-shaped value in the first Git commit exactly matches a publicly labeled Zendesk documentation example. It was not established as a user-owned credential, so no history rewrite or revocation was performed. `security_example_review.json` records the finding. GitHub push protection later flagged two additional public documentation examples in preserved raw passes (Vercel access token and Twilio Conversations JWT); both were redacted in a replacement local commit before the first successful push. Published history was not rewritten, and no real credential was established.

`scan_secrets.py` stores only file, line, category, and SHA-256 fingerprint. Final commit-eligible scan: 1,760 files, 42 credential-shaped occurrences, all inside preserved research, zero outside. Local blind-label packets, runtime caches, and `.env` are excluded from Git. The public page payload excludes raw passes and auth configuration.

## Regression and browser tests

The full local Python regression suite passes (84 tests). Playwright checks pass at 1440px and 390px for 100 rows, all filters, empty search, sorting, keyboard evidence details, no horizontal overflow, parsed JSON/CSV exports, raw-research exclusion, and the 60-claim holdout view. The local generated page has no script errors. The currently published GitHub Pages URL is an older build and must be updated before submission.

No vendor live token, paid plan, admin approval, partner agreement, or production connection was tested. The Composio Python SDK catalog check and hosted MCP Streamable HTTP smoke test did run; the read-only search tool succeeded. Firecrawl actions were discoverable, but this project had no active Firecrawl account connection, so Firecrawl retrieval was not tested.
