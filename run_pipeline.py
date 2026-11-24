"""Run one app through evidence collection and saved-claim verification.

Offline mode reads the collector artifact already in data/ and checks the saved
validated record without network requests. Live mode runs the discovery
collector into the selected output directory, then independently re-fetches the
existing checked record. Freshly collected text is never silently promoted to a
claim; it remains an explicit manual-review input.

Examples:
    python run_pipeline.py --mode offline --app "Google Ads"
    python run_pipeline.py --mode live --app "Google Ads" --output-dir .local_runs/live
    python run_pipeline.py --mode offline --limit 5 --resume
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS = json.loads((ROOT / 'apps.json').read_text(encoding='utf-8'))
FIELDS = ('auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict')


def safe_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-') or 'app'


def select_apps(app: str | None, limit: int | None) -> list[dict]:
    if limit is not None and not 1 <= limit <= len(APPS):
        raise ValueError(f'--limit must be between 1 and {len(APPS)}')
    if app:
        matches = [item for item in APPS if item['name'].casefold() == app.casefold()]
        if not matches:
            raise ValueError(f'No assigned app named {app!r}')
        if limit not in (None, 1):
            raise ValueError('--app selects one app; omit --limit or use --limit 1')
        return matches
    return APPS[:(limit or 1)]


def summarize_discovery(path: Path, app: dict, source: str) -> dict:
    if not path.exists():
        return {'source': source, 'status': 'missing', 'manual_review_required': True}
    raw = json.loads(path.read_text(encoding='utf-8'))
    retrievals = raw.get('retrievals') or []
    return {
        'source': source,
        'status': 'collected',
        'artifact': path.name,
        'search_results': len(raw.get('search_results') or []),
        'documents_fetched': len(retrievals),
        'fetch_errors': len(raw.get('errors') or []),
        'first_pass_claims': raw.get('first_pass', {}),
        'claims_require_manual_review': bool(raw.get('validation_errors')),
        'manual_review_required': True,
        'note': 'Discovery text is not promoted to checked claims by this runner.',
    }


def summarize_checked_claims(payload: dict, mode: str) -> dict:
    verification = payload.get('verification') or {}
    return {
        'basis': 'existing checked_dataset_v4.json record',
        'mode': mode,
        'urls_checked': verification.get('urls_checked', 0),
        'urls_live_200': verification.get('urls_live', 0),
        'first_party_urls': verification.get('first_party_urls', 0),
        'quotes_checked': verification.get('quotes_checked', 0),
        'quotes_reproduced': verification.get('quotes_reproduced', 0),
        'catalog_listed': (payload.get('composio_catalog') or {}).get('in_composio'),
        'auth_crosscheck': (payload.get('auth_crosscheck') or {}).get('comparison'),
        'interpretation': 'This revalidates saved claims; it does not validate the fresh discovery text.',
    }


def command_output(command: list[str]) -> dict:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def run_app(app: dict, mode: str, output_dir: Path, resume: bool) -> tuple[dict, int]:
    slug = safe_slug(app['name'])
    result_path = output_dir / f'{slug}.json'
    if resume and result_path.exists():
        return {'app': app['name'], 'status': 'resumed', 'result': result_path.name}, 0

    if mode == 'live':
        discovery_dir = output_dir / 'discovery'
        discovery_dir.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(ROOT / 'research.py'), '--app', app['name'],
                   '--output-dir', str(discovery_dir), '--workers', '1']
        try:
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            failure = {'app': app['name'], 'mode': mode, 'status': 'failed',
                       'stage': 'fresh_discovery', 'error_type': type(exc).__name__}
            result_path.write_text(json.dumps(failure, indent=2), encoding='utf-8')
            return failure, 1
        discovery = summarize_discovery(discovery_dir / f"{app['number']:03}.json", app,
                                        'fresh live collection')
        checked_mode = 'live'
    else:
        discovery_path = ROOT / 'data' / f"{app['number']:03}.json"
        discovery = summarize_discovery(discovery_path, app, 'saved collector artifact')
        checked_mode = 'offline'

    command = [sys.executable, str(ROOT / 'run_one.py'), '--app', app['name'], f'--{checked_mode}']
    try:
        checked = command_output(command)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        failure = {'app': app['name'], 'mode': mode, 'status': 'failed',
                   'stage': 'saved_claim_verification', 'error_type': type(exc).__name__,
                   'discovery': discovery}
        result_path.write_text(json.dumps(failure, indent=2), encoding='utf-8')
        return failure, 1

    result = {
        'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'app': app['name'],
        'mode': mode,
        'status': 'completed',
        'discovery': discovery,
        'checked_claim_verification': summarize_checked_claims(checked, checked_mode),
        'human_review_required': True,
        'manual_review_boundary': 'Fresh discovery output and verification of existing claims are separate stages.',
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Collect evidence and verify saved claims without conflating them.')
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--app', help='Exact app name from the assigned 100-app list')
    parser.add_argument('--limit', type=int, help='Process the first N apps; defaults to one')
    parser.add_argument('--output-dir', type=Path, default=Path('.local_runs/submission'))
    parser.add_argument('--resume', action='store_true', help='skip apps with an existing result file')
    args = parser.parse_args(argv)
    try:
        apps = select_apps(args.app, args.limit)
    except ValueError as exc:
        parser.error(str(exc))

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for app in apps:
        result, exit_code = run_app(app, args.mode, output_dir, args.resume)
        failed |= exit_code != 0
        print(f"{app['number']:03} {app['name']}: {result['status']}", flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
