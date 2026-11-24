"""Build excerpt packets from gold_template.csv for a separate label review.

Each packet is designed to provide first-party documentation text without
agent-authored answers. A packet build does not prove that a later labeler had no
prior exposure to chat labels; see gold_provenance_v1.json for the saved record.

Outputs
-------
blind_batches/batch_NN.json   packets, 5 rows per file (packet fields only)
blind_batches/calibration_batch.json   the already-labeled rows, gold columns removed
blind_index.csv               row_id, app, field, docs_url
private/mapping.csv           row_id -> original gold_template.csv row (never shared)
private/full/R###.txt         full cleaned page text (never shared)
private/raw/R###.json         cleaned-blocks fetch cache (never shared)

Run:  python build_blind_packets.py [--refresh] [--limit N]
"""
import argparse
import csv
import json
import re
import subprocess
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from leak_check_blind import agent_source_grams

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'gold_template.csv'
BATCH_DIR = ROOT / 'blind_batches'
PRIVATE = ROOT / 'private'
FULL_DIR = PRIVATE / 'full'
RAW_DIR = PRIVATE / 'raw'

UA = 'Mozilla/5.0 (compatible; BlindLabelingPacket/1.0)'
TIMEOUT = 30
PER_BATCH = 5
EXCERPT_CAP = 2500
HEAD_WORDS = 300
CONTEXT_WORDS = 150

# Field keyword lists exactly as specified for the excerpt builder.
KEYWORDS = {
    'auth': ['oauth', 'api key', 'token', 'bearer', 'basic auth', 'jwt',
             'client credentials', 'service account', 'authenticat', 'authoriz'],
    'credential_gate': ['free', 'trial', 'pricing', 'plan', 'paid', 'approval',
                        'review', 'partner', 'contact sales', 'sandbox', 'production',
                        'access level', 'sign up', 'verification'],
    'api_surface': ['rest', 'graphql', 'soap', 'websocket', 'openapi', 'endpoint',
                    'reference', 'sdk', 'resource', 'webhook'],
    'official_mcp': ['mcp', 'model context protocol', 'remote', 'hosted', 'local',
                     'stdio', 'beta', 'early access', 'coming soon', 'read-only', 'oauth'],
}

# Controlled answer vocabulary per judgment field, plus the truth statuses.
ALLOWED = {
    'auth': ['oauth2 user', 'oauth2 client credentials', 'api key / PAT', 'basic',
             'JWT-signed', 'none'],
    'credential_gate': ['self_serve_free', 'self_serve_trial', 'paid_plan',
                        'admin_approval', 'app_review', 'partner_or_sales', 'unknown'],
    'api_surface': ['REST', 'GraphQL', 'SOAP', 'WebSocket', 'SDK', 'narrow',
                    'moderate', 'broad'],
    'official_mcp': ['hosted with actions', 'read-only/docs', 'local only',
                     'beta/EAP/closed', 'prelaunch', 'none'],
}
STATUS_LABELS = ['found', 'not_stated_in_docs', 'unresolved']

BLOCK_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'pre', 'blockquote',
              'td', 'th', 'dt', 'dd', 'figcaption', 'caption']
DROP_CLASS = re.compile(r'(cookie|consent|nav|menu|footer|header|sidebar|breadcrumb|'
                        r'banner|toc|promo|social|share|related|pagination|announce|'
                        r'search|skip)', re.I)
COOKIE_LINE = re.compile(r'\b(cookie|accept all|by clicking|manage preferences|'
                         r'we use cookies)\b', re.I)
ERROR_PAGE = re.compile(r'(404|page not found|access denied|just a moment|'
                        r'enable javascript|checking your browser|are you a robot)', re.I)
TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.S | re.I)


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def words(text):
    return re.findall(r'[^\W_]+', text)


def norm(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text or '')).strip()


def html_visible_words(html):
    """Cheap visible-text word count, used to decide whether a page needs JS rendering."""
    text = re.sub(r'(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>', ' ', html[:2_000_000])
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return len(words(text))


def md_front_matter(text):
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    return match.group(1) if match else ''


def md_title(text):
    front = md_front_matter(text)
    if front:
        match = re.search(r'^title:\s*(.+)$', front, re.M)
        if match:
            return norm(match.group(1))
    match = re.search(r'^#\s+(.+)$', text, re.M)
    return norm(match.group(1)) if match else ''


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def plain_fetch(url):
    """Best-effort direct fetch. Returns a meta dict (never raises)."""
    try:
        response = requests.get(
            url,
            headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,'
                     'text/plain,text/markdown,*/*'},
            timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:  # network error / timeout / TLS
        return {'status': None, 'error': f'{type(exc).__name__}: {exc}'.strip()[:200]}
    charset = response.headers.get('content-type', '').lower()
    if 'charset=' not in charset:
        response.encoding = response.apparent_encoding or 'utf-8'
    meta = {'status': response.status_code, 'final_url': response.url,
            'content_type': response.headers.get('content-type', ''),
            'method': 'requests'}
    if response.status_code == 200:
        body = response.text
        meta['body'] = body
        match = TITLE_RE.search(body[:200_000])
        if match:
            meta['title'] = norm(re.sub(r'<[^>]+>', ' ', match.group(1)))
    response.close()
    return meta


def render_js(items):
    """Render JavaScript pages with headless Chromium. items: [{id,url}] -> {id: meta}."""
    if not items:
        return {}
    queue = PRIVATE / '_render_queue.json'
    out = PRIVATE / '_render_out.json'
    queue.write_text(json.dumps(items), encoding='utf-8')
    result = subprocess.run(['node', str(ROOT / 'render_pages.cjs'), str(queue), str(out)],
                            capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise SystemExit(f'playwright render failed: {result.stderr[:500]}')
    return json.loads(out.read_text(encoding='utf-8'))


# --------------------------------------------------------------------------- #
# Clean -> ordered blocks
# --------------------------------------------------------------------------- #
def clean_blocks(blocks):
    counts = {}
    for block in blocks:
        counts[block['text'].lower()] = counts.get(block['text'].lower(), 0) + 1
    out, prev = [], None
    for block in blocks:
        key = block['text'].lower()
        if key == prev:
            continue
        prev = key
        if not block['heading'] and len(block['text']) < 60 and counts[key] > 3:
            continue                                  # repeated menu / nav item
        if not block['heading'] and len(block['text']) < 200 and COOKIE_LINE.search(block['text']):
            continue                                  # cookie / consent banner
        out.append(block)
    return out


def html_blocks(html):
    soup = BeautifulSoup(html[:4_000_000], 'html.parser')
    for element in soup(['script', 'style', 'noscript', 'template', 'svg', 'iframe']):
        element.decompose()
    root = soup.find('main') or soup.find('article') or soup.body or soup
    for element in root.find_all(['nav', 'footer', 'aside', 'form']):
        element.decompose()
    for element in root.find_all(True):
        if element.parent is None:
            continue
        ident = ' '.join(element.get('class', [])) + ' ' + (element.get('id') or '')
        # only strip small chrome; never a container that happens to hold the article
        if DROP_CLASS.search(ident) and len(words(element.get_text(' ', strip=True))) < 40:
            element.decompose()
    blocks = []
    for element in root.find_all(BLOCK_TAGS):
        if element.find(BLOCK_TAGS):          # keep leaf blocks only, avoid nesting dupes
            continue
        text = norm(element.get_text(' ', strip=True))
        if len(text) < 3:
            continue
        blocks.append({'text': text, 'heading': element.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')})
    if sum(len(words(b['text'])) for b in blocks) < 80:
        fallback = root.get_text('\n', strip=True).split('\n')
        blocks = [{'text': norm(line), 'heading': False} for line in fallback if len(norm(line)) > 2]
    return clean_blocks(blocks)


def rendered_blocks(text):
    chunks = [c.strip() for c in re.split(r'\n\s*\n', text) if c.strip()]
    if len(chunks) < 5:
        chunks = [line.strip() for line in text.split('\n') if line.strip()]
    blocks = []
    for chunk in chunks:
        flat = norm(chunk)
        if len(flat) < 3:
            continue
        heading = len(words(flat)) <= 12 and not flat.endswith('.')
        blocks.append({'text': flat, 'heading': heading})
    return clean_blocks(blocks)


def markdown_blocks(text):
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.S)   # drop YAML front matter
    blocks = []
    for chunk in re.split(r'\n\s*\n', text):
        chunk = chunk.strip()
        if len(chunk) < 3:
            continue
        blocks.append({'text': norm(chunk), 'heading': chunk.startswith('#')})
    return clean_blocks(blocks)


def is_markdown(meta):
    url_path = (meta.get('final_url') or '').split('?')[0]
    content_type = (meta.get('content_type') or '').lower()
    return url_path.endswith(('.md', '.txt')) or 'text/markdown' in content_type \
        or 'text/plain' in content_type


def blocks_for(meta):
    if 'body' in meta:
        return markdown_blocks(meta['body']) if is_markdown(meta) else html_blocks(meta['body'])
    if 'text' in meta:
        return rendered_blocks(meta['text'])
    return []


def needs_render(meta):
    """A 200 response with almost no visible text is a JavaScript-only shell."""
    if meta.get('status') != 200:
        return False
    if 'body' not in meta:
        return False
    if is_markdown(meta):
        return html_visible_words(meta['body']) < 60
    return html_visible_words(meta['body']) < 120


def derive_title(meta, blocks):
    if meta.get('title'):
        return meta['title']
    if 'body' in meta and is_markdown(meta):
        title = md_title(meta['body'])
        if title:
            return title
    for block in blocks:
        if block['heading']:
            return block['text'][:120]
    return blocks[0]['text'][:120] if blocks else ''


# --------------------------------------------------------------------------- #
# Excerpt
# --------------------------------------------------------------------------- #
def build_excerpt(blocks, field):
    counts = [len(words(b['text'])) for b in blocks]
    selected, acc = set(), 0
    for index, count in enumerate(counts):            # first 300 words
        if acc >= HEAD_WORDS:
            break
        selected.add(index)
        acc += count
    lowered = [b['text'].lower() for b in blocks]
    for index, text in enumerate(lowered):            # keyword paragraphs +/- context
        if not any(keyword in text for keyword in KEYWORDS[field]):
            continue
        selected.add(index)
        run, cursor = 0, index - 1
        while cursor >= 0 and run < CONTEXT_WORDS:
            selected.add(cursor)
            run += counts[cursor]
            cursor -= 1
        run, cursor = 0, index + 1
        while cursor < len(blocks) and run < CONTEXT_WORDS:
            selected.add(cursor)
            run += counts[cursor]
            cursor += 1
    if not selected:
        selected = set(range(len(blocks)))
    out, acc = [], 0
    for index, block in enumerate(blocks):
        if index not in selected or acc >= EXCERPT_CAP:
            continue
        text = block['text']
        block_words = words(text)
        if len(block_words) > EXCERPT_CAP - acc:            # hard cap at 2,500 words
            text = ' '.join(block_words[:EXCERPT_CAP - acc])
        out.append(text)
        acc += len(block_words)
    return '\n\n'.join(out)


# --------------------------------------------------------------------------- #
# Redaction: drop any 6-word run that an earlier agent pass already wrote
# --------------------------------------------------------------------------- #
REDACT_RE = re.compile(r'[^\W_]+', re.UNICODE)


def pick_marker(source_grams):
    """A stand-in word absent from the source vocabulary, so it cannot itself
    complete a matching run and always breaks adjacency across a deletion."""
    source_tokens = set()
    for gram in source_grams:
        source_tokens.update(gram.split())
    for candidate in ('redacted', 'omitted', 'withheld', 'zzredact'):
        if candidate not in source_tokens:
            return candidate
    return 'zzredact'


def redact_text(text, source_grams, marker):
    """Replace every covered 6-word run with a single marker word.

    Any run fully inside the kept tokens was, by construction, consecutive in the
    original text too, so it would already have been covered; runs that touch a
    deletion contain the marker word and therefore cannot match. One pass suffices.
    """
    matches = list(REDACT_RE.finditer(text))
    if len(matches) < 6:
        return text
    spans = [(m.start(), m.end()) for m in matches]
    toks = [m.group().lower() for m in matches]
    covered = [False] * len(toks)
    hit = False
    for index in range(len(toks) - 5):
        if ' '.join(toks[index:index + 6]) in source_grams:
            covered[index:index + 6] = [True] * 6
            hit = True
    if not hit:
        return text
    runs, index = [], 0
    while index < len(toks):
        if not covered[index]:
            index += 1
            continue
        end = index
        while end < len(toks) and covered[end]:
            end += 1
        runs.append((spans[index][0], spans[end - 1][1]))
        index = end
    out, last = [], 0
    for start, stop in runs:
        out.append(text[last:start])
        out.append(f' {marker} ')
        last = stop
    out.append(text[last:])
    return ''.join(out)


def trim_to_words(text, limit):
    """Cut text after `limit` whitespace-separated words, keeping all original
    spacing/newlines. Counts punctuation-only tokens too, so that a plain
    `len(excerpt.split())` never exceeds the cap."""
    for count, match in enumerate(re.finditer(r'\S+', text), start=1):
        if count == limit:
            return text[:match.end()].rstrip()
    return text


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def load_rows():
    with INPUT.open(encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def prepare(rows, refresh):
    """Fetch (or reuse) each docs URL and cache its cleaned blocks."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    metas = {}
    todo = []
    for index, row in enumerate(rows, start=1):
        row_id = f'R{index:03d}'
        cache = RAW_DIR / f'{row_id}.json'
        if cache.exists() and not refresh:
            metas[row_id] = json.loads(cache.read_text(encoding='utf-8'))
        else:
            todo.append((row_id, row['docs_url']))
    if not todo:
        return metas
    urls = dict(todo)
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = dict(pool.map(lambda item: (item[0], plain_fetch(item[1])), todo))
    needs_js = []
    for row_id, meta in fetched.items():
        if needs_render(meta):
            needs_js.append({'id': row_id, 'url': meta.get('final_url') or urls[row_id]})
    if needs_js:
        for row_id, meta in render_js(needs_js).items():
            if 'text' in meta and len(words(meta['text'])) >= 80:
                fetched[row_id] = meta
    for row_id, meta in fetched.items():
        blocks = blocks_for(meta)
        entry = {'status': meta.get('status'), 'title': derive_title(meta, blocks), 'method': meta.get('method'),
                 'final_url': meta.get('final_url'), 'error': meta.get('error'), 'blocks': blocks}
        (RAW_DIR / f'{row_id}.json').write_text(json.dumps(entry, ensure_ascii=False), encoding='utf-8')
        metas[row_id] = entry
    return metas


def classify(meta, field, full_text):
    if meta.get('error'):
        return f"FETCH_FAILED: {meta['error']}"
    if meta.get('status') != 200:
        return f"FETCH_FAILED: HTTP {meta.get('status')}"
    if not full_text.strip():
        return 'FETCH_FAILED: empty page'
    if len(words(full_text)) < 80:
        return 'FETCH_FAILED: empty or JavaScript-only page'
    if ERROR_PAGE.search((meta.get('title') or '') + ' ' + full_text[:300].lower()):
        return 'PAGE_OFF_TOPIC'
    lowered = full_text.lower()
    if not any(keyword in lowered for keyword in KEYWORDS[field]):
        return 'PAGE_OFF_TOPIC'
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true', help='ignore raw cache and re-fetch')
    parser.add_argument('--limit', type=int, help='only build the first N rows (smoke test)')
    args = parser.parse_args()

    rows = load_rows()
    if args.limit:
        rows = rows[:args.limit]
    BATCH_DIR.mkdir(exist_ok=True)
    FULL_DIR.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(exist_ok=True)

    metas = prepare(rows, args.refresh)

    source_grams = agent_source_grams()
    marker = pick_marker(source_grams)

    packets, mapping, index_rows = [], [], []
    fetch_failed = off_topic = 0
    for index, row in enumerate(rows, start=1):
        row_id = f'R{index:03d}'
        field = row['field']
        meta = metas.get(row_id, {})
        blocks = meta.get('blocks', [])
        full_text = '\n\n'.join(b['text'] for b in blocks)
        (FULL_DIR / f'{row_id}.txt').write_text(full_text, encoding='utf-8')
        failure = classify(meta, field, full_text)
        if failure:
            excerpt = failure
            if failure.startswith('FETCH_FAILED'):
                fetch_failed += 1
            else:
                off_topic += 1
        else:
            excerpt = build_excerpt(blocks, field)
        excerpt = redact_text(excerpt, source_grams, marker)
        excerpt = trim_to_words(excerpt, EXCERPT_CAP)
        packet = {
            'row_id': row_id,
            'app': row['app'],
            'field': field,
            'question': row['question'],
            'allowed_labels': ALLOWED[field] + STATUS_LABELS,
            'docs_url': row['docs_url'],
            'fetched_at': now(),
            'page_title': redact_text(meta.get('title') or '', source_grams, marker),
            'page_excerpt': excerpt,
        }
        packets.append(packet)
        index_rows.append({'row_id': row_id, 'app': row['app'], 'field': field,
                           'docs_url': row['docs_url']})
        mapping.append({'row_id': row_id, 'csv_row': index, **row})

    for batch_index in range(0, len(packets), PER_BATCH):
        chunk = packets[batch_index:batch_index + PER_BATCH]
        (BATCH_DIR / f'batch_{batch_index // PER_BATCH + 1:02d}.json').write_text(
            json.dumps(chunk, indent=2, ensure_ascii=False), encoding='utf-8')
    # already-labeled rows would go here; gold_template.csv is unlabeled, so this is empty
    (BATCH_DIR / 'calibration_batch.json').write_text('[]', encoding='utf-8')

    with (ROOT / 'blind_index.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['row_id', 'app', 'field', 'docs_url'])
        writer.writeheader()
        writer.writerows(index_rows)
    # Review table: same packets, one row per packet, labels joined.
    with (ROOT / 'blind_packets.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = ['row_id', 'app', 'field', 'question', 'allowed_labels', 'docs_url',
                  'fetched_at', 'page_title', 'page_excerpt']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for packet in packets:
            writer.writerow({**packet, 'allowed_labels': ' | '.join(packet['allowed_labels'])})
    with (PRIVATE / 'mapping.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping[0].keys()))
        writer.writeheader()
        writer.writerows(mapping)
    for scratch in (PRIVATE / '_render_queue.json', PRIVATE / '_render_out.json'):
        if scratch.exists():
            scratch.unlink()

    print(f'packets {len(packets)}')
    print(f'FETCH_FAILED {fetch_failed}')
    print(f'PAGE_OFF_TOPIC {off_topic}')


if __name__ == '__main__':
    main()
