"""Leak check for the blind labeling packets.

Guarantees the packets cannot reveal a prior answer:
  1) no run of 6+ consecutive words of AGENT-AUTHORED text appears in any
     blind_batches file;
  2) no blind file contains the banned phrases below.

Agent-authored text is every string value in data.json, verification.json and
the published page (index.html) EXCEPT verbatim first-party material that both
artifacts legitimately copy from the same public docs: evidence quotes, evidence
URLs and document titles, plus the quote spans index.html renders at runtime.
Those are source-document strings, not the agent's answer, so they are excluded
from the comparison set.

On the packet side each reviewer-visible string value is compared on its own,
and the mandated first-party locator field (docs_url), supplied verbatim by the
gold template rather than by the agent, is not part of the leakage surface.

Exits non-zero (build fails) on any hit, and lists the matches.

Run:  python leak_check_blind.py
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BATCH_DIR = ROOT / 'blind_batches'
SOURCES = {
    'data.json': ROOT / 'data.json',
    'verification.json': ROOT / 'verification.json',
    'index.html': ROOT / 'index.html',
}
NGRAM = 6
BANNED = ['Documented build candidate', 'VERIFIED', 'DRAFT', 'easy win', 'Vendor server']
# Keys whose values are verbatim first-party material, not the agent's own words.
EXCLUDE_KEYS = {'quote', 'url', 'title', 'published_at', 'published_label',
                'retrieved_at', 'evidence_url', 'source_url', 'href'}
TOKEN_RE = re.compile(r'[^\W_]+', re.UNICODE)
TAG_RE = re.compile(r'(?s)<[^>]+>')
SCRIPT_RE = re.compile(r'(?is)<script[^>]*>(.*?)</script>')
STYLE_RE = re.compile(r'(?is)<style[^>]*>.*?</style>')
EMBED_RE = re.compile(r'const\s+data\s*=')


def tokens(text):
    return TOKEN_RE.findall(text.lower())


def strings_from_json(value, key=None):
    if key in EXCLUDE_KEYS or key == 'evidence':
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child_key, child in value.items():
            yield from strings_from_json(child, child_key)
    elif isinstance(value, list):
        for item in value:
            yield from strings_from_json(item, key)


def strings_from_html(text):
    text = STYLE_RE.sub(' ', text)
    for script in SCRIPT_RE.findall(text):
        match = EMBED_RE.search(script)
        if not match:
            continue
        start = script.find('[', match.end())
        if start < 0:
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(script[start:])
        except ValueError:
            continue
        yield from strings_from_json(data)
    visible = TAG_RE.sub(' ', SCRIPT_RE.sub(' ', text))
    yield html.unescape(visible)


def ngrams_from(tokens_list, n=NGRAM):
    return {' '.join(tokens_list[index:index + n]) for index in range(len(tokens_list) - n + 1)}


def source_strings(name, path):
    raw = path.read_text(encoding='utf-8', errors='replace')
    if name.endswith('.html'):
        return list(strings_from_html(raw))
    return list(strings_from_json(json.loads(raw)))


def agent_source_grams():
    """Every 6-word run of agent-authored text (gram -> source label)."""
    source_grams = {}
    for name, path in SOURCES.items():
        for value in source_strings(name, path):
            value_tokens = tokens(value)
            if len(value_tokens) < NGRAM:
                continue
            for gram in ngrams_from(value_tokens):
                source_grams.setdefault(gram, name)
    return source_grams


def blind_packet_strings():
    """Every reviewer-visible string value in every packet.

    Yields (file, field, value). The mandated first-party locator field
    (docs_url) is skipped: the gold template supplies it verbatim, so it is not
    agent-authored text and cannot reveal an earlier answer.
    """
    for path in sorted(BATCH_DIR.glob('*.json')):
        for packet in json.loads(path.read_text(encoding='utf-8')):
            for field, value in packet.items():
                if field == 'docs_url':
                    continue
                values = value if isinstance(value, list) else [value]
                for item in values:
                    if isinstance(item, str):
                        yield path.name, field, item


def main():
    if not BATCH_DIR.exists():
        print('leak-check FAIL: blind_batches/ not found')
        return 1
    source_grams = agent_source_grams()

    matches, seen = [], set()
    for name, field, value in blind_packet_strings():
        for gram in ngrams_from(tokens(value)):
            if gram in source_grams and (gram, source_grams[gram]) not in seen:
                seen.add((gram, source_grams[gram]))
                matches.append((name, field, source_grams[gram], gram))

    banned_hits = []
    for path in sorted(BATCH_DIR.glob('*.json')):
        text = path.read_text(encoding='utf-8')
        for phrase in BANNED:
            if phrase in text:
                banned_hits.append((path.name, phrase))

    ok = not matches and not banned_hits
    print(f'leak-check {"PASS" if ok else "FAIL"}: '
          f'{len(matches)} shared 6-word runs, {len(banned_hits)} banned phrases')
    for name, field, source, gram in matches[:60]:
        print(f'  shared run: {name}:{field} <- {source}: "{gram}"')
    if len(matches) > 60:
        print(f'  ... {len(matches) - 60} more shared runs')
    for name, phrase in banned_hits:
        print(f'  banned phrase: {name}: "{phrase}"')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
