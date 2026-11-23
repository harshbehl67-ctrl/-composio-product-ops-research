"""Replay v4 extraction over frozen pass-2 and pass-4 pages into a new pass."""
import argparse
import collections
import datetime
import json
import re
from pathlib import Path

import context_pass_v4 as pipeline

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', default='pass8')
args = parser.parse_args()
if not re.fullmatch(r'pass[0-9]+', args.output_dir):
    raise SystemExit('Output directory must be a new pass number, e.g. pass8')
out = ROOT / 'data' / args.output_dir
out.mkdir(exist_ok=True)
counts = collections.Counter()
for app in pipeline.prior.APPS:
    number = app['number']
    output = out / f'{number:03}.json'
    if output.exists():
        raise SystemExit(f'Refusing to overwrite frozen replay: {output}')
    old = json.loads((ROOT / 'data' / 'pass2' / f'{number:03}.json').read_text(encoding='utf-8'))
    newer = json.loads((ROOT / 'data' / 'pass4' / f'{number:03}.json').read_text(encoding='utf-8'))
    dates = {}
    for search_dir in ('new_search', 'pass4_search'):
        search = json.loads((ROOT / 'data' / search_dir / f'{number:03}.json').read_text(encoding='utf-8'))
        content = search.get('search_response', search.get('response', {}))
        search_text = '\n'.join(item.get('text', '') for item in content.get('content', []) if item.get('type') == 'text')
        for block in re.split(r'\n-{20,}\n', search_text):
            title = block.splitlines()[0] if block.splitlines() else ''
            url = re.search(r'\((https?://[^\s)]+)\)', title)
            label = re.search(r'Published:\s*([^;\n]+)', block)
            if url and label:
                dates[url.group(1)] = label.group(1).strip()
    pages = old['pages'] + newer['new_pages']
    for page in pages:
        page.setdefault('published_label', dates.get(page.get('requested_url', page.get('url', ''))))
    claims = pipeline.extract(app, pages)
    counts.update(field for field, claim in claims.items() if claim['value'] != 'unknown')
    record = {
        'app': app,
        'replayed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source_passes': [f'data/pass2/{number:03}.json', f'data/pass4/{number:03}.json'],
        'source_searches': [f'data/new_search/{number:03}.json', f'data/pass4_search/{number:03}.json'],
        'publication_date_note': 'Search publication labels are retained exactly; null means no label was available. Relative labels are not exact dates.',
        'claims': claims,
        'validation': [
            'Automatic extraction is provisional until independently reviewed',
            'Unknown is not evidence of absence',
            'Composio evidence cannot establish vendor MCP',
            'Client-only and negated MCP statements are not vendor-server proof',
            'API breadth is a text-coverage heuristic, not an endpoint census',
        ],
    }
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(args.output_dir, 'frozen for', len(pipeline.prior.APPS), 'apps; provisional field counts:', dict(counts))
