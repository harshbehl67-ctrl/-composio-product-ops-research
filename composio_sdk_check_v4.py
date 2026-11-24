"""Cross-check the Composio toolkit findings with Composio's own Python SDK.

The rest of the pipeline verifies the Composio catalog from its published docs
(https://docs.composio.dev/toolkits). This step does the same check the way the
role expects: it asks the Composio SDK directly which toolkits exist and
compares that with the composio_toolkit claim we recorded for each of the 100
apps (listed_exact / listed_alias / not_listed).

The SDK needs an API key. The step reads it from the environment (loaded from the
git-ignored .env via python-dotenv). Without a key the step is skipped with a
note, so the rest of the build still works.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
OUT = ROOT / 'composio_sdk_check_v4.json'

APPS = json.loads((ROOT / 'checked_dataset_v4.json').read_text(encoding='utf-8'))

SLUG_IN_TEXT = re.compile(r'slug[:\s]*`?([A-Za-z0-9_]+)`?', re.IGNORECASE)
TOOLS_IN_QUOTE = re.compile(r'Tools:\**\s*(\d+)', re.IGNORECASE)


def api_key() -> str | None:
    return os.environ.get('COMPOSIO_API_KEY', '').strip() or None


def normalise(name: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', name.upper())


def slug_from_url(url: str) -> str | None:
    """docs.composio.dev/toolkits/<slug> -> <slug>; the full-catalog page has no slug."""
    if not url:
        return None
    path = urlparse(url).path
    if not path.startswith('/toolkits/'):
        return None
    slug = path[len('/toolkits/'):].strip('/')
    if slug.endswith('.md'):
        slug = slug[:-3]
    if not slug or slug == 'toolkits':
        return None
    return slug.upper()


def candidate_slugs(app: dict) -> list[str]:
    """Every slug this app's evidence points at, most specific first."""
    field = app['fields']['composio_toolkit']
    candidates: list[str] = []
    for ev in field.get('evidence') or []:
        url_slug = slug_from_url(ev.get('url', ''))
        if url_slug:
            candidates.append(url_slug)
        for match in SLUG_IN_TEXT.finditer(f"{ev.get('quote') or ''} {field.get('reason') or ''}"):
            candidates.append(match.group(1).upper())
    candidates.append(normalise(app['app']))
    seen: list[str] = []
    for slug in candidates:
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def docs_tools(app: dict) -> int | None:
    for ev in (app['fields']['composio_toolkit'].get('evidence') or []):
        match = TOOLS_IN_QUOTE.search(ev.get('quote') or '')
        if match:
            return int(match.group(1))
    return None


def fetch_sdk_catalog(client) -> dict:
    catalog: dict[str, dict] = {}
    cursor = None
    while True:
        page = client.toolkits.list(limit=100, cursor=cursor)
        for item in page.items:
            catalog[item.slug.upper()] = {
                'name': item.name,
                'slug': item.slug,
                'tools': int(item.meta.tools_count),
                'triggers': int(item.meta.triggers_count),
                'auth_schemes': list(item.auth_schemes or []),
                'toolkit_type': item.toolkit_type,
            }
        cursor = page.next_cursor
        if not cursor:
            break
    return catalog


def main() -> int:
    key = api_key()
    if not key:
        print('No COMPOSIO_API_KEY in the environment; skipping Composio SDK cross-check.')
        return 0

    from composio import Composio

    client = Composio(api_key=key)
    sdk = fetch_sdk_catalog(client)
    print(f'Composio SDK returned {len(sdk)} toolkits')

    records = []
    listed_claims = listed_confirmed = not_listed_claims = not_listed_confirmed = 0
    tools_compared = tools_match = 0
    for app in APPS:
        claim = app['fields']['composio_toolkit']['value']
        wanted_listed = claim in ('listed_exact', 'listed_alias')
        candidates = candidate_slugs(app)
        hit = next((slug for slug in candidates if slug in sdk), None)
        sdk_present = hit is not None
        agree = wanted_listed == sdk_present
        if wanted_listed:
            listed_claims += 1
            listed_confirmed += 1 if agree else 0
        else:
            not_listed_claims += 1
            not_listed_confirmed += 1 if agree else 0
        dt = docs_tools(app)
        sdk_tools = sdk[hit]['tools'] if hit else None
        tmatch = None
        if sdk_present and dt is not None and sdk_tools is not None:
            tools_compared += 1
            tmatch = (dt == sdk_tools)
            tools_match += 1 if tmatch else 0
        records.append({
            'app': app['app'], 'claim': claim, 'candidates': candidates, 'matched_slug': hit,
            'sdk_present': sdk_present, 'docs_tools': dt, 'sdk_tools': sdk_tools,
            'tools_match': tmatch, 'sdk_auth_schemes': sdk[hit]['auth_schemes'] if hit else None,
            'agree': agree,
        })

    total = len(records)
    agree = listed_confirmed + not_listed_confirmed
    payload = {
        'checked_at': '2026-11-24',
        'sdk': 'composio',
        'sdk_catalog_count': len(sdk),
        'apps_checked': total,
        'listed_claims': listed_claims,
        'listed_confirmed': listed_confirmed,
        'listed_mismatch': listed_claims - listed_confirmed,
        'not_listed_claims': not_listed_claims,
        'not_listed_confirmed': not_listed_confirmed,
        'not_listed_mismatch': not_listed_claims - not_listed_confirmed,
        'listing_agreement': agree,
        'listing_agreement_pct': round(100.0 * agree / total, 1) if total else 0.0,
        'tools_compared': tools_compared,
        'tools_match': tools_match,
        'method': ('The SDK lists every toolkit (paginated). For each app the recorded composio_toolkit claim is '
                   'compared with the SDK: listed_exact/listed_alias should be present under one of the slugs its '
                   'evidence points at, and not_listed should be absent from all of them. Where the docs page quotes a '
                   'Tools count, it is compared with the SDK tools_count.'),
        'records': records,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Listing agreement {agree}/{total} ({payload["listing_agreement_pct"]}%): '
          f'listed confirmed {listed_confirmed}/{listed_claims}, '
          f'not-listed confirmed {not_listed_confirmed}/{not_listed_claims}')
    print(f'Tool counts: {tools_match}/{tools_compared} exact matches where both sides report a number')
    print(f'Wrote {OUT.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
