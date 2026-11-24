"""Build the v2 research data model (`data.json` + `data.csv`) from validated v4 evidence.

Every derived field is computed here from `checked_dataset_v4.json` (the validated
six-field research), `composio_catalog.json` (Composio's live catalog) and
`catalog_crosscheck.json`. Nothing is hand-typed: the mappings below are the whole
rule set. Where a rule cannot decide mechanically, the choice is written to
`human_log.json` instead of being guessed silently.

Run:
    python datamodel_v2.py            # write data.json, data.csv, human_log.json
    python datamodel_v2.py --check    # the same, but exit non-zero on any count mismatch
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

import catalog_crosscheck as crosscheck

ROOT = Path(__file__).resolve().parent
FETCHED_AT = '2026-11-24'

# --- Controlled vocabularies -------------------------------------------------
ACCESS_VALUES = ('self_serve_free', 'self_serve_trial', 'paid_plan', 'admin_approval',
                 'app_review', 'partner_or_sales', 'unknown')
MCP_TIERS = ('hosted_action', 'docs_readonly', 'local', 'beta', 'prelaunch', 'none', 'unresolved')
BLOCKERS = ('no_public_api', 'partner_gate', 'paid_gate', 'app_review', 'admin_gate',
            'enterprise_only', 'sparse_api', 'no_docs', 'none')
CHIPS = ('oauth2_user', 'oauth2_client_creds', 'oauth2_service_account', 'api_key_or_pat', 'basic', 'jwt_signed', 'signed_request', 'none')
IN_COMPOSIO_VALUES = ('exact', 'alias', 'none')
EFFORT_VALUES = ('S', 'M', 'L')
CONFIDENCE_VALUES = ('high', 'medium', 'low')

# --- Rules -------------------------------------------------------------------

# credential_gate gate_class -> (prototype_access, production_access) for the
# unambiguous apps. "mixed" is deliberately absent: those are split below.
ACCESS_FROM_GATE = {
    'self_serve_free': ('self_serve_free', 'self_serve_free'),
    'self_serve_trial': ('self_serve_trial', 'self_serve_trial'),
    'paid_plan': ('paid_plan', 'paid_plan'),
    'admin_approval': ('admin_approval', 'admin_approval'),
    'partner_or_sales': ('partner_or_sales', 'partner_or_sales'),
    'no_public_api': ('unknown', 'unknown'),
    'unknown': ('unknown', 'unknown'),
}

# The 17 apps the validated research labelled "mixed". Each is split into a
# prototype path and a production path from the credential_gate reason text; the
# quote in `why` is the phrase the decision rests on. All 17 are logged to
# human_log.json because a rule cannot read the intent of these pages.
MIXED_SPLIT = {
    'Twenty': ('self_serve_trial', 'paid_plan',
               'free trial without a credit card; paid Cloud plans follow'),
    'Intercom': ('self_serve_free', 'paid_plan',
                 'development workspaces are free but development-only; production requires a paid workspace'),
    'Freshdesk': ('self_serve_trial', 'paid_plan',
                  'trial users receive an API allowance, but MCP is limited to Growth/Pro/Enterprise'),
    'Lark (Larksuite)': ('admin_approval', 'paid_plan',
                         'tenant-admin approval for self-built app permissions; advanced API needs a metering pack on specified plans'),
    'WhatsApp Business': ('self_serve_free', 'paid_plan',
                          'free monthly service-message allowance plus per-message charges and business prerequisites'),
    'Google Ads': ('self_serve_free', 'app_review',
                   'Cloud project grants Test access; production requires access-level applications and a Standard audit'),
    'Meta Ads': ('self_serve_free', 'app_review',
                 'self-serve entry plus reviewed production access (App Review on permissions/features)'),
    'LinkedIn Ads': ('self_serve_free', 'app_review',
                     'starts in Development tier; Standard access requested by support ticket at LinkedIn discretion'),
    'Pinterest': ('self_serve_free', 'app_review',
                  'register an app for Trial access; Standard access requires a reviewed upgrade request'),
    'Threads (Meta)': ('self_serve_free', 'app_review',
                       'create an app and use testers; ordinary users require permission-specific App Review'),
    'SendGrid': ('self_serve_trial', 'paid_plan',
                 '60-day trial; sending stops unless an Email API plan is selected'),
    'Magento (Adobe Commerce)': ('self_serve_free', 'paid_plan',
                                 'PaaS/Open Source create an integration in Admin; Adobe Commerce as a Cloud Service requires a Commerce license'),
    'Squarespace': ('self_serve_free', 'app_review',
                    'OAuth apps generate credentials immediately for development (Demo Mode) and require Squarespace review for production'),
    'Paygent Connect': ('self_serve_free', 'paid_plan',
                        'no-cost sandbox with full API access; production carries a $15/month gateway fee plus per-transaction pricing'),
    'iPayX': ('self_serve_free', 'paid_plan',
              'no-key public MCP evaluation and free audits plus paid production API options'),
    'QuickBooks': ('self_serve_free', 'admin_approval',
                   'no-charge Builder tier and free sandbox; Production Key requires questionnaire approval'),
    'Grain': ('self_serve_free', 'paid_plan',
              'personal access tokens on every plan including Free; workspace tokens require Business/Enterprise and admin access'),
}

# mcp_mode -> tier, for apps with a documented vendor server.
MCP_MODE_TIER = {
    'remote': 'hosted_action',
    'both': 'hosted_action',
    'local': 'local',
    'early_access': 'beta',
    'unknown': 'unresolved',
}

# Named re-tiers from the saved MCP evidence. The mechanical mcp_mode map above
# mis-states these because a "remote" server can still be documentation-only or
# not yet live. Every entry is logged to human_log.json.
MCP_OVERRIDE = {
    'Twilio': ('docs_readonly', 'Vendor MCP exposes documentation/read-only lookups, not actions.'),
    'Discord': ('docs_readonly', 'Vendor MCP is documentation-oriented.'),
    'Ecwid': ('docs_readonly', 'Vendor MCP is documentation/read-only.'),
    'Vonage': ('docs_readonly', 'Vendor MCP serves reference/documentation material.'),
    'QuickBooks': ('local', 'Vendor MCP ships as a local server.'),
    'Neo4j': ('local', 'Vendor MCP ships as a local server.'),
    'Magento (Adobe Commerce)': ('local', 'Vendor MCP is a local/self-hosted server.'),
    'Copper': ('beta', 'Vendor MCP is in beta/early access.'),
    'Brex': ('beta', 'Official Brex MCP documentation labels the hosted server Beta.'),
    'NotebookLM': ('beta', 'Official product docs describe NotebookLM as Early Access Public Preview.'),
    'Pinterest': ('prelaunch', 'Official page asks readers to be first to know when the MCP launches.'),
    'Google Ads': ('local', 'Official package is locally run/self-deployed; the Cloud Run option is customer-deployed, not a vendor-hosted endpoint. Read-only is configurable; propose-and-confirm mutations are also documented.'),
    'Lark (Larksuite)': ('local', 'Gold evidence says the OpenAPI MCP runs locally with npx; the separate remote-mode guide is deprecated.'),
    'Shopify': ('local', 'Dev MCP is a locally run, read-only developer docs/schema server; the separate store-management MCP is not public.'),
    'Zendesk': ('beta', 'Vendor MCP is early access (EAP).'),
    'Gladly': ('beta', 'Vendor MCP is EAP/early access.'),
}
# Tiers where an ordinary third-party app cannot just connect today.
NOT_USABLE_TIERS = ('none', 'unresolved', 'beta', 'prelaunch')
# Apps whose MCP exists but is restricted beyond the tier (logged).
MCP_RESTRICTED = {'Slack': 'Slack MCP is limited to Marketplace / internal apps, so an ordinary third-party app cannot use it.'}

CHIP_MAP = {
    'oauth2': 'oauth2_user', 'oauth2_client_creds': 'oauth2_client_creds',
    'oauth2_service_account': 'oauth2_service_account',
    'api_key': 'api_key_or_pat', 'basic': 'basic', 'jwt_signed': 'jwt_signed', 'none': 'none',
}
AUTH_CHIP_OVERRIDES = {
    'Vercel': (['api_key_or_pat'], 'Scoped Vercel access tokens are personal access tokens, not an unknown transport.'),
    'Google Ads': (['oauth2_user', 'oauth2_service_account'], 'Official auth docs list user OAuth and service-account OAuth flows; this is not OAuth client credentials.'),
    'Binance': (['api_key_or_pat', 'signed_request'], 'Official API docs describe API keys and signed requests using HMAC, RSA, or Ed25519; the signature is not JWT.'),
    'Amazon Selling Partner': (['oauth2_user', 'oauth2_client_creds'], 'Selling Partner API uses Login with Amazon OAuth for seller-authorized operations and client credentials for grantless operations; it does not require JWT signing.'),
    'Intercom': (['oauth2_user', 'api_key_or_pat'], 'Public apps use OAuth; private workspace apps use access tokens.'),
    'GoHighLevel': (['oauth2_user', 'api_key_or_pat'], 'Public integrations use OAuth; private integrations use bearer tokens.'),
    'Ecwid': (['oauth2_user', 'api_key_or_pat'], 'Public apps use OAuth; custom store apps use access tokens.'),
    'Gumroad': (['oauth2_user', 'api_key_or_pat'], 'OAuth supports general integrations; account access tokens support own-account API use.'),
    'Snowflake': (['api_key_or_pat', 'jwt_signed', 'oauth2_user'], 'Official auth docs list programmatic access tokens, signed key-pair JWTs, and OAuth tokens.'),
}
COMPOSIO_MAP = {'listed_exact': 'exact', 'listed_alias': 'alias', 'not_listed': 'none'}
VERDICT_OK = {'documented_build_candidate', 'gated_build_candidate', 'partner_outreach',
              'wrapper_or_cli', 'no_public_api', 'unknown'}


# A few summaries open with a meta note (a scope note or a rename notice) rather
# than a description of the app, so what_it_does skips those and takes the first
# substantive sentence instead.
META_SENTENCE = re.compile(r'^(this record is scoped|note:)|became .{1,40} on \d{4}-\d{2}-\d{2}|^as of ', re.I)


def clip(text: str, limit: int = 100) -> str:
    """Trim to at most `limit` characters, cutting on a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    if ' ' in cut:
        cut = cut[:cut.rfind(' ')]
    return cut.rstrip(' ,.;:') + '\u2026'


def what_it_does(row: dict) -> str:
    purposes = json.loads((ROOT / 'app_purposes_v4.json').read_text(encoding='utf-8'))
    try:
        return purposes[row['app']]
    except KeyError as exc:
        raise ValueError(f"Missing concise purpose for {row['app']}") from exc


def override_evidence(row: dict, field: str) -> list[dict]:
    """Attach the cited evidence for the exact field affected by an override."""
    return [
        {key: claim[key] for key in ('url', 'quote', 'retrieved_at', 'published_at') if key in claim}
        for claim in row['fields'][field].get('evidence', [])
        if claim.get('url') and claim.get('quote')
    ]


def auth_chips(row: dict) -> tuple[list[str], list[str]]:
    if row['app'] in AUTH_CHIP_OVERRIDES:
        chips, _reason = AUTH_CHIP_OVERRIDES[row['app']]
        return sorted(chips), list(row['fields']['auth']['value'] if isinstance(row['fields']['auth']['value'], list)
                                  else [row['fields']['auth']['value']])
    methods, _transport = crosscheck.researched_methods(row['fields']['auth']['value'])
    chips = sorted({CHIP_MAP[m] for m in methods if m in CHIP_MAP})
    return (chips or ['unknown']), list(row['fields']['auth']['value'] if isinstance(row['fields']['auth']['value'], list)
                                        else [row['fields']['auth']['value']])


def access_split(row: dict, log: list) -> tuple[str, str]:
    gate = row['fields']['credential_gate'].get('gate_class')
    if gate == 'mixed':
        split = MIXED_SPLIT[row['app']]
        prototype, production, why = split
        log.append({'app': row['app'], 'field': 'prototype_access/production_access',
                    'actor_type': 'authored classification override',
                    'reason': f'Validated research classified access as "mixed": {why}.',
                    'evidence': override_evidence(row, 'credential_gate'),
                    'decision': f'prototype={prototype}, production={production}'})
        return prototype, production
    if gate == 'no_public_api':
        log.append({'app': row['app'], 'field': 'prototype_access/production_access',
                    'reason': 'No public API documented, so no credential path exists.',
                    'decision': 'prototype=unknown, production=unknown'})
        return 'unknown', 'unknown'
    return ACCESS_FROM_GATE.get(gate, ('unknown', 'unknown'))


def mcp_tier(row: dict, log: list) -> str:
    mcp = row['fields']['official_mcp']
    if mcp['value'] == 'no_vendor_server_documented':
        return 'none'
    if row['app'] in MCP_OVERRIDE:
        tier, why = MCP_OVERRIDE[row['app']]
        log.append({'app': row['app'], 'field': 'mcp_tier',
                    'actor_type': 'authored classification override',
                    'reason': f'Named re-tier from saved MCP evidence: {why}',
                    'evidence': override_evidence(row, 'official_mcp'),
                    'decision': f'mcp_tier={tier}'})
        return tier
    return MCP_MODE_TIER.get(mcp.get('mcp_mode'), 'unresolved')


def mcp_usable(tier: str, row: dict, log: list) -> bool:
    app = row['app']
    if app in MCP_RESTRICTED:
        log.append({'app': app, 'field': 'mcp_usable_by_ordinary_app',
                    'actor_type': 'authored classification override',
                    'reason': MCP_RESTRICTED[app],
                    'evidence': override_evidence(row, 'official_mcp'),
                    'decision': 'mcp_usable_by_ordinary_app=false'})
        return False
    return tier not in NOT_USABLE_TIERS


def blocker_for(row: dict, production: str) -> str:
    klass = row['blocker_class']
    if klass == 'none_documented_for_prototype':
        return 'none'
    if klass == 'partnership_or_sales':
        return 'partner_gate'
    if klass == 'no_documented_public_api':
        return 'no_public_api'
    if klass == 'wrapper_required':
        return 'sparse_api'
    if klass == 'unresolved_official_evidence':
        return 'no_docs'
    if klass == 'credential_access_gate':
        if production in ('self_serve_free', 'self_serve_trial'):
            return 'none'
        return {'paid_plan': 'paid_gate', 'app_review': 'app_review', 'admin_approval': 'admin_gate',
                'partner_or_sales': 'partner_gate'}.get(production, 'no_docs')
    return 'no_docs'


def effort_tier(rec: dict) -> str:
    easy = (rec['verdict'] == 'documented_build_candidate'
            and rec['production_access'] in ('self_serve_free', 'self_serve_trial')
            and rec['api_breadth'] in ('broad', 'moderate')
            and rec['mcp_tier'] == 'hosted_action'
            and rec['in_composio'] in ('exact', 'alias'))
    hard = (rec['blocker'] in ('no_public_api', 'partner_gate', 'enterprise_only')
            or rec['mcp_tier'] in ('none', 'unresolved', 'local'))
    return 'S' if easy else ('L' if hard else 'M')


def confidence_of(row: dict) -> str:
    checked = sum(claim['status'] == 'checked' for claim in row['fields'].values())
    return {6: 'high', 5: 'medium'}.get(checked, 'low')


def last_verified(row: dict, fallback: str) -> str:
    dates = [ev.get('retrieved_at') for claim in row['fields'].values() for ev in claim.get('evidence', [])]
    dates = [d for d in dates if d]
    return max(dates) if dates else fallback


def primary_evidence(row: dict) -> str:
    for claim in row['fields'].values():
        for ev in claim.get('evidence', []):
            if ev.get('url'):
                return ev['url']
    return ''


def public_claim(claim: dict) -> dict:
    keys = ('value', 'status', 'reason', 'evidence', 'gate_class', 'api_types', 'breadth', 'mcp_mode',
            'slug', 'tools', 'triggers', 'server_url', 'server_urls', 'transport', 'authentication')
    result = {key: claim[key] for key in keys if key in claim}
    if 'evidence' in result:
        ev_keys = ('url', 'title', 'quote', 'retrieved_at', 'published_at', 'published_label',
                   'original_url', 'verification_method')
        result['evidence'] = [{k: ev[k] for k in ev_keys if k in ev} for ev in result['evidence']]
    return result


def build() -> tuple[list[dict], list[dict]]:
    rows = json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))
    catalog = {rec['app']: rec for rec in json.loads((ROOT / 'composio_catalog.json').read_text(encoding='utf-8'))['records']}
    log: list[dict] = []
    records = []
    for row in rows:
        prototype, production = access_split(row, log)
        tier = mcp_tier(row, log)
        chips, detail = auth_chips(row)
        if row['app'] in AUTH_CHIP_OVERRIDES:
            log.append({'app': row['app'], 'field': 'auth_chips',
                        'actor_type': 'authored classification override',
                        'reason': AUTH_CHIP_OVERRIDES[row['app']][1],
                        'evidence': override_evidence(row, 'auth'),
                        'decision': ','.join(chips)})
        catalog_rec = catalog.get(row['app'], {})
        record = {
            'number': row['number'], 'app': row['app'], 'category': row['category'],
            'what_it_does': what_it_does(row),
            'auth_chips': chips, 'auth_detail': detail,
            'prototype_access': prototype, 'production_access': production,
            'api_types': row['fields']['api_surface'].get('api_types', []),
            'api_breadth': row['fields']['api_surface'].get('breadth', 'unknown'),
            'api_surface': row['fields']['api_surface']['value'],
            'mcp_tier': tier, 'mcp_usable_by_ordinary_app': mcp_usable(tier, row, log),
            'official_mcp': row['fields']['official_mcp']['value'],
            'in_composio': COMPOSIO_MAP[row['fields']['composio_toolkit']['value']],
            'composio_slug': catalog_rec.get('composio_slug'),
            'effort_tier': None, 'needs_outreach': False, 'blocker': None,
            'confidence': confidence_of(row), 'last_verified': last_verified(row, FETCHED_AT),
            'verdict': row['fields']['verdict']['value'],
            'blocker_detail': row['blocker'], 'next_action': row['next_action'],
            'evidence_url': primary_evidence(row),
            'fields': {field: public_claim(claim) for field, claim in row['fields'].items()},
        }
        record['blocker'] = blocker_for(row, production)
        record['needs_outreach'] = record['blocker'] == 'partner_gate' or production == 'partner_or_sales'
        record['effort_tier'] = effort_tier(record)
        records.append(record)
    log.extend([
        {
            'app': 'gold set (all sampled apps)',
            'field': 'gold_status',
            'actor_type': 'recorded process provenance',
            'reason': 'The saved project record attributes filled gold rows to a separate AI session using frozen excerpts. Model/session identity is missing; blinding and exclusion of earlier chat labels are not independently verified.',
            'decision': 'compare saved AI-labeled truth values after labeling; preserve provenance and author spot-check results as separate records.',
            'provenance_file': 'gold_provenance_v1.json',
        },
        {
            'app': 'gold set (composio_toolkit, verdict)',
            'field': 'composio_toolkit', 'reason': 'Grading the Composio-toolkit and buildability claims by hand '
                      'would be opinion against opinion. Only auth, credential_gate, api_surface and official_mcp '
                      'are judgment calls.',
            'decision': 'composio_toolkit is scored against the Composio catalog snapshot (composio_catalog.json, '
                        'with its fetched_at), and verdict (buildability) is derived from the four gold fields by '
                        'the written rule in gold_score_v4.derive_verdict.',
        },
        {
            'app': 'Zendesk',
            'field': 'official_mcp',
            'reason': 'Surprise re-check: the EAP article is JS-rendered, so a plain HTTP fetch returns no '
                      'readable body and the cited quote cannot be reproduced without a browser.',
            'decision': 'keep the claim (originally captured with headless Chromium); mark the live re-check '
                        'as needing the browser-fallback loop, not as a wrong claim.',
        },
        {
            'app': 'Pinterest',
            'field': 'official_mcp',
            'reason': 'Surprise re-check: developers.pinterest.com/about-pinterest-mcp/ is a JS single-page app; '
                      'a plain HTTP fetch returns ~20 characters ("Pinterest Developers"), so the quote cannot '
                      'be reproduced without rendering.',
            'decision': 'keep the "prelaunch / not live" claim; mark the live re-check as needing the '
                        'browser-fallback loop, not as a wrong claim.',
        },
    ])
    return records, log


def easy_wins(records: list[dict]) -> list[str]:
    return [rec['app'] for rec in records
            if rec['verdict'] == 'documented_build_candidate'
            and rec['production_access'] in ('self_serve_free', 'self_serve_trial')
            and rec['api_breadth'] in ('broad', 'moderate')]


def build_next(records: list[dict]) -> list[dict]:
    return [{'app': rec['app'], 'category': rec['category'], 'catalog_fetched_at': FETCHED_AT}
            for rec in records if rec['in_composio'] == 'none' and rec['verdict'] == 'documented_build_candidate'
            and rec['production_access'] in ('self_serve_free', 'self_serve_trial')]


def csv_rows(records: list[dict]) -> list[dict]:
    out = []
    for rec in records:
        out.append({
            'app': rec['app'], 'category': rec['category'], 'what_it_does': rec['what_it_does'],
            'auth_chips': '|'.join(rec['auth_chips']), 'prototype_access': rec['prototype_access'],
            'production_access': rec['production_access'], 'api_types': '|'.join(rec['api_types']),
            'api_breadth': rec['api_breadth'], 'mcp_tier': rec['mcp_tier'],
            'mcp_usable_by_ordinary_app': rec['mcp_usable_by_ordinary_app'], 'in_composio': rec['in_composio'],
            'composio_slug': rec['composio_slug'] or '', 'effort_tier': rec['effort_tier'],
            'needs_outreach': rec['needs_outreach'], 'blocker': rec['blocker'], 'confidence': rec['confidence'],
            'last_verified': rec['last_verified'], 'verdict': rec['verdict'],
            'evidence_url': rec['evidence_url'],
        })
    return out


def validate(records: list[dict]) -> dict:
    """Schema + count validation. Every check raises SystemExit on failure."""
    errors = []
    if len(records) != 100:
        errors.append(f'expected 100 records, found {len(records)}')
    if len({r['app'] for r in records}) != len(records):
        errors.append('duplicate app names')
    validators = {
        'prototype_access': ACCESS_VALUES, 'production_access': ACCESS_VALUES, 'mcp_tier': MCP_TIERS,
        'in_composio': IN_COMPOSIO_VALUES, 'effort_tier': EFFORT_VALUES, 'blocker': BLOCKERS,
        'confidence': CONFIDENCE_VALUES, 'verdict': tuple(VERDICT_OK),
    }
    for rec in records:
        for field, allowed in validators.items():
            if rec[field] not in allowed:
                errors.append(f"{rec['app']}: {field}={rec[field]!r} not in {allowed}")
        if not rec['auth_chips'] or not set(rec['auth_chips']) <= set(CHIPS + ('unknown',)):
            errors.append(f"{rec['app']}: bad auth_chips {rec['auth_chips']}")
        if not rec['what_it_does'] or len(rec['what_it_does'].split()) > 10:
            errors.append(f"{rec['app']}: what_it_does length {len(rec['what_it_does'])}")
        if not isinstance(rec['mcp_usable_by_ordinary_app'], bool) or not isinstance(rec['needs_outreach'], bool):
            errors.append(f"{rec['app']}: flag fields must be boolean")
    counts = {}
    for field in ('prototype_access', 'production_access', 'mcp_tier', 'in_composio', 'effort_tier',
                  'blocker', 'confidence', 'verdict'):
        counter = collections.Counter(rec[field] for rec in records)
        counts[field] = dict(counter)
        if sum(counter.values()) != 100:
            errors.append(f'{field} counts sum to {sum(counter.values())}, not 100')
    documented = counts['verdict'].get('documented_build_candidate', 0)
    wins = easy_wins(records)
    counts['documented_build_candidate'] = documented
    counts['easy_wins'] = len(wins)
    excluded = sorted(set(r['app'] for r in records if r['verdict'] == 'documented_build_candidate') - set(wins))
    counts['easy_win_excluded'] = excluded
    if documented != 64:
        errors.append(f'documented build candidates = {documented}, expected 64')
    if len(wins) != 60:
        errors.append(f'easy wins = {len(wins)}, expected 60')
    if excluded != ['NotebookLM', 'SendGrid', 'Twenty', 'Grain'] and excluded != sorted(['Twenty', 'Grain', 'SendGrid', 'NotebookLM']):
        errors.append(f'unexpected easy-win exclusions: {excluded}')
    if errors:
        raise SystemExit('data model validation failed:\n  - ' + '\n  - '.join(errors))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description='Build the v2 data model from validated v4 evidence.')
    parser.add_argument('--check', action='store_true', help='exit non-zero on any count mismatch')
    args = parser.parse_args()

    records, log = build()
    counts = validate(records)

    (ROOT / 'data.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / 'data.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows(records)[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows(records))
    (ROOT / 'human_log.json').write_text(
        json.dumps({'generated_at': FETCHED_AT, 'entries': log}, ensure_ascii=False, indent=2), encoding='utf-8')
    override_fields = {'auth_chips', 'prototype_access/production_access', 'mcp_tier',
                       'mcp_usable_by_ordinary_app'}
    overrides = [entry for entry in log
                 if entry.get('actor_type') == 'authored classification override'
                 and entry.get('field') in override_fields]
    missing_override_evidence = [f"{entry['app']} / {entry['field']}" for entry in overrides
                                 if not entry.get('evidence')]
    if missing_override_evidence:
        raise SystemExit('classification override missing claim-specific source evidence: '
                         + ', '.join(missing_override_evidence))
    (ROOT / 'classification_overrides_v1.json').write_text(
        json.dumps({'generated_at': FETCHED_AT,
                    'source': 'checked_dataset_v4.json field evidence plus datamodel_v2.py mappings',
                    'records': overrides}, ensure_ascii=False, indent=2), encoding='utf-8')

    print('data model v2 built from checked_dataset_v4.json')
    for field in ('prototype_access', 'production_access', 'mcp_tier', 'in_composio', 'effort_tier',
                  'blocker', 'confidence', 'verdict'):
        print(f'  {field}: {counts[field]}')
    print(f"  documented candidates: {counts['documented_build_candidate']} (easy wins {counts['easy_wins']}, "
          f"excluded {counts['easy_win_excluded']})")
    print(f'  human_log entries: {len(log)}')
    print(f'  claim-specific overrides: {len(overrides)}')
    print(f"  build-next (easy wins missing from Composio): {[r['app'] for r in build_next(records)]}")
    if args.check:
        print('validation: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
