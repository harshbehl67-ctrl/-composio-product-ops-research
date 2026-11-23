# Assignment checklist

| Requirement | Current location / status |
|---|---|
| Exact 100 apps | `apps.json`; assertion in `assess.py` |
| Agent/script across list, raw baseline | `research.py` and `data/001.json`–`data/100.json`; source discovery performed, full claim extraction not complete |
| Candidate review | `candidate_triage.json` indexes 100 apps; unreviewed candidates remain and most claims are unknown |
| Composio catalog vs vendor MCP | `assessed_dataset.json` and page table; 77 catalog matches (61 exact + 16 alias), 23 unknown, 5 vendor MCPs individually established |
| Six-field category sample | `six_field_review.json`, ten apps / 60 fields; 60 abstentions, 0 answered, 25 with at least partial reference evidence, 35 unresolved |
| First-pass accuracy | 0/60 answered; accuracy 0/0 undefined; no claim of improvement |
| Category and decision patterns | Page matrix shows 97 verdicts unknown, the Google Ads production gate, and two CLI-wrapper judgments; substantive patterns are not yet justified |
| Workflow and corrections | Page research and accuracy sections; scripts and logs in project |
| Single page and interaction | `index.html`; tested at 1440px and 390px, filters/sort/JSON/CSV/keyboard details |
| Source links | `link_checks.json`: 94 checked, zero HTTP errors at check time; this does not verify claim truth |
| Live link / repository | Sites creation failed: `sites_access_disabled`; no remotely hosted source repository verified |
| Submission readiness | Not ready: 97 app verdicts unknown, most required fields incomplete, sample and holdout incomplete |
