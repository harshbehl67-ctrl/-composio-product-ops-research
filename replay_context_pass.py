"""Rerun revised context extraction over frozen pass-2/pass-4 pages."""
import argparse
import collections
import datetime
import json
import re
from pathlib import Path
import context_pass

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', default='pass6')
args = parser.parse_args()
if not re.fullmatch(r'pass[0-9]+', args.output_dir):
    raise SystemExit('Output directory must be a new pass number, e.g. pass6')
out = root / 'data' / args.output_dir
out.mkdir(exist_ok=True)
counts = collections.Counter()
for app in context_pass.prior.APPS:
    n = app['number']
    output = out / f'{n:03}.json'
    if output.exists():
        raise SystemExit(f'Refusing to overwrite frozen replay: {output}')
    old = json.loads((root / 'data' / 'pass2' / f'{n:03}.json').read_text(encoding='utf-8'))
    newer = json.loads((root / 'data' / 'pass4' / f'{n:03}.json').read_text(encoding='utf-8'))
    search = json.loads((root / 'data' / 'new_search' / f'{n:03}.json').read_text(encoding='utf-8'))
    search_text = '\n'.join(c.get('text', '') for c in search.get('search_response', {}).get('content', []) if c.get('type') == 'text')
    dates = {}
    for block in re.split(r'\n-{20,}\n', search_text):
        title = block.splitlines()[0] if block.splitlines() else ''
        url = re.search(r'\((https?://[^\s)]+)\)', title)
        label = re.search(r'Published:\s*([^;\n]+)', block)
        if url and label:
            dates[url.group(1)] = label.group(1).strip()
    pages = old['pages'] + newer['new_pages']
    for page in pages:
        page.setdefault('published_label', dates.get(page.get('requested_url', page.get('url', ''))))
    claims = context_pass.extract(app, pages)
    counts.update(k for k, v in claims.items() if v['value'] != 'unknown')
    data = {'app': app, 'replayed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_passes': [f'data/pass2/{n:03}.json', f'data/pass4/{n:03}.json'],
            'source_search': f'data/new_search/{n:03}.json',
            'publication_date_note': 'Published labels are retained exactly as supplied by search; missing labels are null. Relative labels must not be treated as exact publication dates.',
            'claims': claims, 'validation': ['Automatic extraction is provisional and not a verified final claim',
                'Unknown is not evidence of absence', 'No Composio-to-vendor-MCP inference',
                'Basic authentication may be endpoint-specific', 'Client-only and negated statements are not positive MCP evidence']}
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(args.output_dir, 'frozen for', len(context_pass.prior.APPS), 'apps; provisional field counts:', dict(counts))
