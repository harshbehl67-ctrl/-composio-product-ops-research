# Assignment checklist

| Requirement | Final location / status |
|---|---|
| Exact 100 apps across ten categories | `apps.json`; `assemble_checked_v4.py` validates 100 unique assigned apps |
| Agent/script across the list with raw baseline | `research.py`; immutable `data/001.json`–`data/100.json`; later frozen passes under `data/pass*` |
| Candidate review and claim-specific sources | All 100 records in `data/checked_research/`; 496/500 vendor claims checked |
| API reference, authentication, credentials, access/pricing, MCP | Official first-party evidence per field in `checked_dataset_v4.json`; exact quotes and dates retained |
| Context corrections | `context_pass_v4.py`; client/server direction, clause-local negation, publication labels, ownership checks, and Composio separation |
| Composio catalog vs vendor MCP | 69 exact, 11 alias, 20 scoped not-listed findings; 92 vendor servers and 8 scoped no-server findings reported separately |
| Buildability, blocker, next action | 64 documented, 30 gated, 3 partner, 2 wrapper/CLI, 1 unresolved; every record has blocker and next action |
| Six-field category sample | `review_selected_v4.json`; 33/60 answered, strict 19/33, half-credit 25/33 |
| Random holdout | `review_holdout_v4.json`; seed 20261124, 26/60 answered, strict 14/26, half-credit 18/26 |
| Baseline accuracy | 0/60 answered; accuracy undefined (0/0); no improvement claim |
| Category and decision patterns | `research_summary_v4.json` and generated category matrix in `index.html` |
| Workflow and corrections | Runnable commands in `README.md`; exact actions in `source_review_v4.json` and group logs |
| Single page and interaction | `index.html`; 1440px/390px Playwright tests pass for filters, sort, empty search, keyboard details, exports, and overflow |
| Source links | `link_checks_v4.json`: 592 URLs, zero broken checked links; `independent_link_checks_v4.json`: 123 URLs, zero unresolved |
| Historical bearer-shaped string | `security_example_review.json`: exact public Zendesk documentation example; no evidence of a user-owned credential, so history was not rewritten |
| GitHub push protection | Two additional public documentation token examples in raw passes were redacted before the first successful push; `redaction_log.json` records them |
| Secret scan | `secret_scan_v4.json`: 1,728 files, 42 preserved-research occurrences, zero outside preserved research |
| Live link / repository | Live and tested: https://harshbehl67-ctrl.github.io/-composio-product-ops-research/; source: https://github.com/harshbehl67-ctrl/-composio-product-ops-research |
| Submission readiness | Complete and published; the live URL passes the same 1440px/390px Playwright suite with no script errors |

The only unresolved core fields are Fanbasis authentication, credential gate, API surface, and verdict. Current first-party Commas pages document the Fanbasis rebrand, APIs/SDKs, and an MCP beta, but do not publish those API details; the legacy Fanbasis API Docs site remains password-protected. This is a specific evidence boundary, not a generic incomplete-research label.
