"""Fetch Composio's own catalog entry for each of the 100 researched apps.

For every app we call GET https://backend.composio.dev/api/v3/toolkits/{slug}
with the x-api-key header (read from the git-ignored .env) and save the fields
that describe the toolkit's authentication and availability. A 404, or an alias
that resolves to nothing, is recorded as "not in Composio catalog" - a finding,
not an error.

The slug to probe comes from the app's saved evidence (see catalog_lookup.py), so
aliases such as Zoho CRM -> ZOHO, Monday.com -> MONDAY and WhatsApp Business ->
WHATSAPP are handled. Raw responses are cached under data/composio_catalog_cache/
so reruns are cheap and every number stays reproducible.

Output: composio_catalog.json
"""
from __future__ import annotations

import concurrent.futures
import datetime
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

import catalog_lookup as lookup

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
BASE = 'https://backend.composio.dev/api/v3/toolkits'
CACHE = ROOT / 'data' / 'composio_catalog_cache'
OUT = ROOT / 'composio_catalog.json'
FETCHED_AT = '2026-11-24'


def api_key() -> str:
    key = os.environ.get('COMPOSIO_API_KEY', '').strip()
    if not key:
        raise SystemExit('COMPOSIO_API_KEY is not set; add it to .env before fetching the catalog.')
    return key


def fetch_slug(slug: str) -> dict:
    """Return {"status": int, "body": dict|None} for one slug, using the cache."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f'{slug}.json'
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding='utf-8'))
    response = requests.get(f'{BASE}/{slug}', headers={'x-api-key': api_key()}, timeout=30)
    result = {'status': response.status_code,
              'body': response.json() if response.status_code == 200 else None,
              'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if response.status_code not in (200, 404):
        raise SystemExit(f'Composio catalog returned {response.status_code} for {slug}: check the API key.')
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def schemes_of(body: dict) -> list[str]:
    """Union of managed schemes and the modes documented in auth_config_details."""
    schemes = set(body.get('composio_managed_auth_schemes') or [])
    for detail in body.get('auth_config_details') or []:
        if detail.get('mode'):
            schemes.add(detail['mode'])
    return sorted(schemes)


def probe(app: dict) -> dict:
    claim = app['fields']['composio_toolkit']['value']
    candidates = lookup.candidate_slugs(app)
    record = {'app': app['app'], 'category': app['category'], 'claim': claim,
              'slug_candidates': candidates, 'slug_tried': None, 'http_status': None,
              'in_composio': False, 'composio_slug': None, 'auth_schemes': [],
              'composio_managed_auth_schemes': [], 'no_auth': None, 'auth_guide_url': None,
              'base_url': None, 'enabled': None, 'toolkit_type': None,
              'tools_count': None, 'triggers_count': None, 'fetched_at': FETCHED_AT}
    for slug in candidates:
        result = fetch_slug(slug)
        record['slug_tried'] = slug
        record['http_status'] = result['status']
        if result['status'] == 200 and result['body']:
            body = result['body']
            record.update({
                'in_composio': True,
                'composio_slug': body.get('slug'),
                'auth_schemes': schemes_of(body),
                'composio_managed_auth_schemes': body.get('composio_managed_auth_schemes') or [],
                'auth_guide_url': body.get('auth_guide_url'),
                'base_url': body.get('base_url'),
                'enabled': body.get('enabled'),
                'toolkit_type': body.get('toolkit_type'),
                'tools_count': (body.get('meta') or {}).get('tools_count'),
                'triggers_count': (body.get('meta') or {}).get('triggers_count'),
            })
            record['no_auth'] = not record['auth_schemes']
            return record
    record['no_auth'] = None
    return record


def main() -> int:
    apps = lookup.load_dataset()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(probe, apps))
    listed = sum(1 for r in records if r['in_composio'])
    payload = {'source': BASE, 'fetched_at': FETCHED_AT, 'apps': len(records),
               'in_composio': listed, 'not_in_composio': len(records) - listed,
               'records': records}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Catalog fetch: {listed}/{len(records)} apps found in Composio; '
          f'{len(records) - listed} not in the catalog')
    mismatch = [r['app'] for r in records
                if (r['claim'] in ('listed_exact', 'listed_alias')) != r['in_composio']]
    print(f'Claim vs catalog disagreements: {len(mismatch)}' + (f' -> {mismatch}' if mismatch else ''))
    print(f'Wrote {OUT.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
