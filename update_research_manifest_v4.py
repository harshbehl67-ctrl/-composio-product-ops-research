"""Verify preserved research hashes and append newly preserved artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'research_pass_manifest.json'
LOG_FILES = (
    'pass2_review.json', 'pass6_review.json', 'pass7_review.json',
    'security_example_review.json', 'redaction_log.json', 'manual_facts_v3.json',
    'holdout_selection_v4.json', 'independent_review_v4.json', 'source_review_v4.json',
    'first_pass_review_v4.json', 'composio_sdk_check_v4.json',
    'replace_rate_limited_sources_v4.py', 'finalize_source_link_followups_v4.py',
)
FINAL_FILES = (
    'checked_dataset_v4.json', 'research_summary_v4.json', 'remaining_unknowns_v4.json',
    'validation_report_v4.json', 'source_checks_v4.json', 'link_checks_v4.json',
    'independent_link_checks_v4.json', 'secret_scan_v4.json', 'gold_ratings_v4.json',
    'verification.json', 'first_pass_review_v4.json', 'independent_review_v4.json',
    'README.md', 'REQUIREMENTS.md', 'research_diagnostics.md', 'index.html',
)
MUTABLE_FILES = set(FINAL_FILES) | {
    'source_review_v4.json', 'independent_review_v4.json', 'redaction_log.json',
    'composio_sdk_check_v4.json',
    'first_pass_review_v4.json',
    'data/pass4/022.json', 'data/pass4_search/062.json',
}
MUTABLE_PATTERNS = ('data/checked_research/[0-9][0-9]_*.json', 'data/checked_research/review_*.json')


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': digest.hexdigest()}


manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
entries = {entry['path']: entry for entry in manifest['files']}
verified = 0
updated = 0
for relative, entry in entries.items():
    current = fingerprint(ROOT / relative)
    if relative in MUTABLE_FILES or any((ROOT / relative).match(pattern) for pattern in MUTABLE_PATTERNS):
        if current != entry:
            entries[relative] = current
            updated += 1
        else:
            verified += 1
        continue
    if current['bytes'] != entry['bytes'] or current['sha256'] != entry['sha256']:
        raise ValueError(f'Preserved file changed: {relative}')
    verified += 1

candidates = set()
for pattern in ('data/pass*/*.json', 'data/checked_research_raw/*.json',
                'data/checked_research/review_*.json', 'data/checked_research/[0-9][0-9]_*.json'):
    candidates.update(path for path in ROOT.glob(pattern) if path.is_file())
candidates.update(ROOT / name for name in LOG_FILES + FINAL_FILES if (ROOT / name).is_file())
added = 0
for path in sorted(candidates):
    relative = path.relative_to(ROOT).as_posix()
    if relative not in entries:
        entries[relative] = fingerprint(path)
        added += 1

manifest['updated_at'] = '2026-11-24'
manifest['files'] = [entries[relative] for relative in sorted(entries)]
MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Verified {verified} existing hashes; refreshed {updated} final artifacts; added {added}; manifest contains {len(entries)} files')
