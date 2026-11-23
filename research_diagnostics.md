# Research diagnostics and final validation

## Why the baseline abstained

`research.py` did not contain an extraction prompt or model call. It searched once per app, fetched at most one hint-domain URL, and unconditionally assigned `unknown` or `unclear` to substantive fields. The 0/60 sample coverage was intentional code behavior, not measured model uncertainty. Domain discovery often selected homepages, login pages, or unrelated product pages, and developer documentation frequently lives on a separate vendor-controlled domain.

The original `data/001.json`–`data/100.json` remain unchanged. Baseline answered-claim accuracy is undefined (0/0).

## Why relevant documentation still produced blanks

The first targeted extractor was deterministic. Its domain rule required both a vendor-root match and an API/documentation-like path, discarding official pricing, credential-creation, review, and MCP pages on other paths. Candidate selection spent its six-page budget on topic labels rather than guaranteed coverage of the five required source types. JavaScript shells, redirects, 403 responses, navigation removal, and truncation further reduced usable text.

Extraction added a second bottleneck. Authentication was scanned only on authentication-looking pages. API recognition required exact “REST API” or “GraphQL API” phrases, missing “HTTP API”, “RESTful APIs”, “GraphQL Admin API”, and explicitly negated REST statements. There was no breadth classifier, access-tier implementation, or verdict implementation in pass 2. MCP matching was a positive keyword/brand-proximity test: it could not distinguish a vendor server from a client connection, handled negation incompletely, and did not retain source dates systematically.

The 100-app new pass provisionally answered authentication for 56 apps, API surface for 28, vendor MCP for 65, and Composio catalog matches for 77. These were extraction counts, not verified findings.

## Context-aware replay

`context_pass_v4.py` broadens official-source ownership, scans API evidence beyond authentication-looking pages, recognizes REST/GraphQL/HTTP/gRPC/SOAP with clause-local negation, estimates breadth from documented resource terms, and extracts free/trial/paid/admin/partner access conditions. MCP classification separates `vendor_server`, `client_only`, `no_vendor_server_documented`, and `unknown`; Composio cannot establish vendor MCP.

The corrected frozen replay is `data/pass12/`. It provisionally answered auth 77, access 31, API surface 41, vendor MCP 30, Composio toolkit 77, and verdict 15. These remain extraction counts. Earlier defective passes are preserved.

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

Abstained and unresolved claims are excluded from accuracy denominators. The baseline answered 0/60, so its accuracy is undefined (0/0); no baseline improvement is claimed. Exact ratings, corrections, and independent sources are in `independent_review_v4.json`.

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

`scan_secrets.py` stores only file, line, category, and SHA-256 fingerprint. Final scan: 1,728 files, 42 credential-shaped occurrences, all inside preserved research, zero outside. The public page payload excludes those raw passes.

## Regression and browser tests

The Python suite has 41 passing tests. Playwright passes at 1440px and 390px for 100 rows, all filters, empty search, sorting, keyboard evidence details, no horizontal overflow, parsed JSON/CSV exports, raw-research exclusion, and the 60-claim holdout view. No script errors were observed. The live GitHub Pages URL passes the same suite: https://harshbehl67-ctrl.github.io/-composio-product-ops-research/.

No live token, paid plan, admin approval, partner agreement, production connection, Composio SDK runtime, or MCP runtime was tested.
