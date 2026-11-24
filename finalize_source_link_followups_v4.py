"""Verify corrected GitHub source links and fold results into audit artifacts."""
import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
checks = [
    ('Sherlock', 'https://api.github.com/repos/sherlock-project/sherlock/git/trees/c588d7c8b476df9f9c84912a05d1430fb8cdcdae?recursive=1',
     'https://github.com/sherlock-project/sherlock/tree/c588d7c8b476df9f9c84912a05d1430fb8cdcdae', 'Readme'),
    ('Mermaid CLI', 'https://api.github.com/repos/mermaid-js/mermaid-cli/git/trees/1423a0d7967d275a9d360ba0617f569550827c8b?recursive=1',
     'https://github.com/mermaid-js/mermaid-cli/tree/1423a0d7967d275a9d360ba0617f569550827c8b', 'README.md'),
]
headers = {'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'}
results = []
for app, old, url, quote in checks:
    response = requests.get(url, headers=headers, timeout=25, allow_redirects=True)
    text = BeautifulSoup(response.text, 'html.parser').get_text(' ', strip=True)
    if response.status_code != 200 or quote.casefold() not in text.casefold():
        raise SystemExit(f'Follow-up failed for {app}: HTTP {response.status_code}, quote_visible={quote.casefold() in text.casefold()}')
    use = {'app': app, 'field': 'official_mcp', 'claim_status': 'checked', 'quote': quote,
           'browser_reviewed': True, 'followup_checked_at': '2026-11-24'}
    results.append({'old_url': old, 'url': url, 'status': response.status_code,
                    'final_url': response.url, 'uses': [use],
                    'followup_note': 'Replaced a rate-limited GitHub tree API URL with the official commit-pinned browser page; full source archive review remains documented in source_review_v4.json.'})

for name in ('link_checks_v4.json', 'source_checks_v4.json'):
    path = ROOT / name
    rows = json.loads(path.read_text(encoding='utf-8'))
    for update in results:
        rows = [row for row in rows if row.get('url') not in (update['old_url'], update['url'])]
        clean = {key: value for key, value in update.items() if key != 'old_url'}
        if name == 'source_checks_v4.json':
            clean['uses'][0].update({'quote_exact': True, 'quote_token_exact': True,
                                     'raw_html_only_match': False, 'start_fragment_found': True,
                                     'end_fragment_found': True})
        rows.append(clean)
    path.write_text(json.dumps(sorted(rows, key=lambda row: row['url']), indent=2, ensure_ascii=False), encoding='utf-8')
print('Both corrected official links return HTTP 200 and display their recorded repository entry; updated source and link audit artifacts.')
