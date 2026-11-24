"""Emit credential-shaped findings without retaining or printing the matched values."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

patterns = {
    'bearer': re.compile(r'(?i)\bbearer\s+(?!\[redacted)[A-Za-z0-9._~+/-]{20,}'),
    'jwt': re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b'),
    'openai_key': re.compile(r'\bsk-[A-Za-z0-9_-]{24,}\b'),
    'github_token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b'),
    'aws_access_key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
tracked = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard'], text=True).splitlines()
paths = sorted({Path(name) for name in tracked if Path(name).is_file() and '.git' not in Path(name).parts})
findings = []
for path in paths:
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in patterns.items():
            for match in pattern.finditer(line):
                value = match.group(0)
                preserved = (path.as_posix() == 'checked_dataset_v4.json' or
                             (path.parts[0] == 'data' and (len(path.parts) < 2 or path.parts[1] != 'checked_research')) or
                             path.parts[0] == 'private' or
                             path.parts[0] == 'blind_batches' or
                             path.name in ('blind_packets.csv', 'blind_index.csv'))
                findings.append({'file': path.as_posix(), 'line': number, 'kind': kind,
                                 'sha256': hashlib.sha256(value.encode()).hexdigest(),
                                 'preserved_research': preserved})
unpreserved = [finding for finding in findings if not finding['preserved_research']]

# Fail if the live Composio API key value appears in any commit-eligible file.
# .env is git-ignored, so it is excluded from the scanned paths; only a real leak is flagged.
key_value = os.environ.get('COMPOSIO_API_KEY', '').strip()
env_path = Path('.env')
if not key_value and env_path.exists():
    for line in env_path.read_text(encoding='utf-8').splitlines():
        if line.startswith('COMPOSIO_API_KEY='):
            key_value = line.split('=', 1)[1].strip()
if key_value:
    for path in paths:
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        if key_value in text:
            findings.append({'file': path.as_posix(), 'line': 0, 'kind': 'composio_api_key',
                             'sha256': hashlib.sha256(key_value.encode()).hexdigest(),
                             'preserved_research': False})
    unpreserved = [finding for finding in findings if not finding['preserved_research']]
report = {'files_scanned': len(paths), 'findings': findings,
          'preserved_occurrences': len(findings) - len(unpreserved),
          'unpreserved_occurrences': len(unpreserved)}
Path('secret_scan_v4.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'{len(paths)} files scanned; {len(findings)} credential-shaped occurrences; '
      f'{len(unpreserved)} outside preserved research; values not retained')
if unpreserved:
    raise SystemExit(1)
