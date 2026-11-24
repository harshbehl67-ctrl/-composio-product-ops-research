"""Run a one-app, offline submission demo and save a redacted sample."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    result = subprocess.run(
        [sys.executable, str(ROOT / 'run_one.py'), '--app', 'Google Ads', '--offline'],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    raw = json.loads(result.stdout)
    checks = raw['verification']
    sample = {
        'app': raw['app'],
        'mode': 'offline - saved evidence and catalog snapshot; no network requests',
        'evidence_urls': checks['urls_checked'],
        'first_party_urls': checks['first_party_urls'],
        'quote_checks': 'not run offline',
        'catalog_snapshot': {
            'in_composio': raw['composio_catalog']['in_composio'],
            'slug': raw['composio_catalog']['composio_slug'],
            'auth_schemes': raw['composio_catalog']['auth_schemes'],
            'snapshot_date': raw['composio_catalog']['fetched_at'],
        },
        'auth_crosscheck': raw['auth_crosscheck'],
    }
    output = ROOT / 'run_submission_demo_sample_v4.json'
    output.write_text(json.dumps(sample, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(sample, indent=2, ensure_ascii=False))
    print(f'Wrote {output.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
