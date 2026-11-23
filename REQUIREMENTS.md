# Assignment checklist

| Requirement | Current location / status |
|---|---|
| Exact 100 apps | `apps.json`; assertion in `assess.py` |
| Agent/script across list, raw baseline | `research.py` and `data/001.json`–`data/100.json`; source discovery performed, full claim extraction not complete |
| Candidate review | `candidate_triage.json` indexes 100 apps; unreviewed candidates remain and most claims are unknown |
| Composio catalog vs vendor MCP | `reviewed_dataset.json` and page table; 77 catalog matches (61 exact + 16 alias), 23 unknown; 46 positive vendor MCP cases reviewed, one dated negative, and 53 unresolved; early-access and product scope differ |
| Six-field category sample | `pass2_review.json`, ten apps / 60 fields; new pass answered 26, with 19 correct, 7 partial, 34 abstained |
| First-pass accuracy | Baseline: 0/60 answered, accuracy 0/0 undefined. New pass: 22.5/26 weighted (86.5%); sample is deliberately selected and not population accuracy |
| Category and decision patterns | Page matrix shows 85 verdicts unknown; 15 scoped documented or inferred decisions; substantive patterns are not yet justified |
| Workflow and corrections | Page research and accuracy sections; scripts and logs in project |
| Single page and interaction | `index.html`; tested at 1440px and 390px, filters/sort/JSON/CSV/keyboard details |
| Source links | `link_checks.json`: 157 checked; 154 HTTP successes and three HTTP 403 responses to the direct checker at check time (all three opened through the web reader); this does not verify claim truth |
| Live link / repository | Repository pushed and opened at https://github.com/harshbehl67-ctrl/-composio-product-ops-research; case-study deployment remains incomplete |
| Submission readiness | Not ready: 85 app verdicts unknown, most required fields incomplete, sample and holdout incomplete |

The new targeted search and tentative extraction cover all 100 apps, but individual claim-level review remains incomplete. See `research_diagnostics.md` and `remaining_unknowns.json`.
