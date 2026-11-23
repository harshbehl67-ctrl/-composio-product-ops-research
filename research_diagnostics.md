# Diagnosis and second experiment

## Why the baseline abstained

`research.py` did not contain an extraction prompt or a model call. It searched once per app, fetched at most one hint-domain URL, and then unconditionally assigned `unknown` (or `unclear`) to every substantive field. A validation rule also marked every row as needing review. Thus the 0/60 sample coverage was intentional code behavior, not measured model uncertainty. In addition, the domain-discovery pass often selected a vendor homepage, login page, or unrelated product page; a matching domain alone did not establish a claim. Developer documentation may also live on a separate vendor-controlled domain.

The original `data/001.json` through `data/100.json` remain unchanged. The baseline sample had 0/60 answered claims, so accuracy among answered claims has denominator zero and is undefined.

## New pass

The new discovery run saved three targeted queries per app (authentication and credentials; API access and pricing; official MCP) and the web-search response under `data/new_search/`. `improved_pass.py` selects candidate vendor domains and documentation-like paths, fetches up to six pages per app, saves retrieved text and errors, and extracts positive authentication, API-surface and MCP matches with source excerpts. It independently checks the saved Composio catalog. It does not infer absence from a failed search. The original saved new pass is `data/pass2/`; forced reruns use timestamped files under `data/pass2_reruns/`.

The extractor is deterministic and has **no LLM extraction prompt**. Its claims are tentative, not individually verified. It did not implement access-tier or verdict classification, so those fields remain unknown in the saved pass even if the targeted search surfaced useful evidence. Its domain and text rules can misclassify scope or product identity. `refine_access.py` separately indexes access-related phrases for 26/100 apps, but the examples include false matches and are not automatically promoted to facts.

The 100-app new pass produced provisional answers for authentication on 56/100, API surface on 28/100, vendor MCP on 65/100, and Composio catalog matches on 77/100. Its 476 HTTP attempts returned 457 HTTP 200 responses, 18 HTTP 403 responses, and one network error. Eleven apps had no candidate that passed the selection rule. These figures measure extraction and retrieval coverage, not claim accuracy or verified vendor capabilities. A 200 response does not establish that the page supports a claim.

## Independent AI-assisted review

`pass2_review.json` records a deliberately chosen sample of ten apps, one from each category, with six fields each. The new pass answered 26/60 and abstained on 34/60. Of the 26 answered claims, the independent review rated 19 correct, seven partial, zero incorrect and zero unresolved. Strict full-credit accuracy is 19/26 (73.1%). With partial answers assigned 0.5, the weighted result is (19 + 7×0.5)/26 = 22.5/26 (86.5%). This is a targeted sample, not a random holdout or population estimate; the original baseline has no calculable answered-claim accuracy to compare against it.

Examples: Zendesk's extracted MCP answer was positive, but its citation described Zendesk as a **client** of external servers. Independent vendor documentation establishes Zendesk's own MCP server through Zendesk Bridge in early access, so the answer received partial credit with the correct source. Notion had a similar client/server citation error. Slack's extraction included Basic authentication for an OAuth token endpoint as though it were a general API method, and omitted the scope of that detail. GitHub's extracted Basic-only answer missed personal access tokens and app tokens. Exact original new-pass answers, citations, ratings, corrections, and review sources are in `pass2_review.json`.

## What is still incomplete

`manual_facts.json` records independently reviewed, scoped access findings and product-ops inferences. `reviewed_dataset.json` combines these with prior checked evidence without changing either frozen pass. It has 15 scoped buildability decisions and 85 unknown verdicts; `remaining_unknowns.json` records the reason for each unresolved field. The new pass's 65 provisional MCP matches and 56 provisional auth matches have not been verified across all 100 apps, so they must not be presented as population findings. No paid account, real credential, production integration, random holdout or full accessibility audit was used.

The targeted searches were performed with the connected web-search service, which is not a standalone command supplied in this repository. The logged queries and outputs are saved, and the extractor can be rerun against those saved results. Credential-shaped strings found in several files of retrieved public material were redacted before pushing; `redaction_log.json` records the affected files and match counts without retaining the strings.

Aircall provides an out-of-sample negation error: its current FAQ says it did not offer an MCP server at the time of writing, whereas the new extractor returned yes after matching the words MCP server. The corrected, dated vendor statement is in `manual_facts.json`; this out-of-sample finding is not included in the 26-claim sample score.

One bearer-shaped example from the public Zendesk authentication documentation was already present in `data/review_sources/73874c42bbc1e9a0.json` in commit `3fe2521`, which was pushed before the broader bearer-pattern check. It has been redacted in the current working tree; the earlier commit remains in Git history. It was drawn from public documentation and has not been established to be a live credential.
