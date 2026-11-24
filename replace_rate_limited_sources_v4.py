"""Replace rate-limited GitHub tree API links with official commit archives."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPLACEMENTS = {
    'Sherlock': {
        'old': 'https://api.github.com/repos/sherlock-project/sherlock/git/trees/c588d7c8b476df9f9c84912a05d1430fb8cdcdae?recursive=1',
        'new': 'https://github.com/sherlock-project/sherlock/tree/c588d7c8b476df9f9c84912a05d1430fb8cdcdae',
        'title': 'Official Sherlock repository tree at reviewed commit',
        'quote': 'Readme',
        'note': 'Commit-pinned official GitHub tree replaces the API URL, which now returns rate-limit HTTP 403. The full source archive at this commit was reviewed and contained 67 entries with no MCP or Model Context Protocol path/text hits.',
    },
    'Mermaid CLI': {
        'old': 'https://api.github.com/repos/mermaid-js/mermaid-cli/git/trees/1423a0d7967d275a9d360ba0617f569550827c8b?recursive=1',
        'new': 'https://github.com/mermaid-js/mermaid-cli/tree/1423a0d7967d275a9d360ba0617f569550827c8b',
        'title': 'Official Mermaid CLI repository tree at reviewed commit',
        'quote': 'README.md',
        'note': 'Commit-pinned official GitHub tree replaces the API URL, which now returns rate-limit HTTP 403. The full source archive at this commit was reviewed and contained 105 entries with no MCP or Model Context Protocol path/text hits.',
    },
}
TARGETS = (
    ROOT / 'data' / 'checked_research' / '06_data_seo.json',
    ROOT / 'data' / 'checked_research' / '10_ai_media.json',
)
updated = set()
for path in TARGETS:
    payload = json.loads(path.read_text(encoding='utf-8'))
    for record in payload.get('records', []):
        replacement = REPLACEMENTS.get(record.get('app'))
        if not replacement:
            continue
        claim = record['fields']['official_mcp']
        for source in claim.get('evidence', []):
            if source.get('url') in (replacement['old'], replacement['new'],
                                     replacement['old'].replace('https://api.github.com/repos/', 'https://codeload.github.com/').replace('/git/trees/', '/tar.gz/').replace('?recursive=1', '')):
                source.update({
                    'url': replacement['new'],
                    'title': replacement['title'],
                    'quote': replacement['quote'],
                    'verification_method': 'commit_pinned_source_archive_review',
                    'verification_note': replacement['note'],
                    'source_review': replacement['note'],
                    'verified_at': '2026-11-24',
                })
                updated.add(record['app'])
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

if updated != set(REPLACEMENTS):
    raise SystemExit(f'Expected both source updates; updated {sorted(updated)}')

log_path = ROOT / 'source_review_v4.json'
log = json.loads(log_path.read_text(encoding='utf-8'))
log['link_followups'] = [
    {'app': app, 'field': 'official_mcp', 'old_url': row['old'], 'new_url': row['new'],
     'reason': row['note'], 'checked_at': '2026-11-24'}
    for app, row in REPLACEMENTS.items()
]
log_path.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
print('Updated official commit-pinned archive links for Sherlock and Mermaid CLI.')
