"""Check checked evidence URLs and whether direct retrieval reproduces each quote."""
import argparse
import concurrent.futures
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
uses = {}
reviews = {}


def normalize(text):
    text = unicodedata.normalize('NFKC', text or '')
    text = text.replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-').replace('\u2011', '-')
    text = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()


def tokens(text):
    return re.findall(r'[^\W_]+', normalize(text).lower(), re.UNICODE)


def contains_tokens(page_tokens, quote_tokens):
    if not quote_tokens or len(quote_tokens) > len(page_tokens):
        return False
    first = quote_tokens[0]
    width = len(quote_tokens)
    return any(page_tokens[index] == first and page_tokens[index:index + width] == quote_tokens
               for index in range(len(page_tokens) - width + 1))


def markdown_url(url):
    parts = urlsplit(url)
    if parts.path.endswith('.md'):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/') + '.md', parts.query, parts.fragment))


def visible_text(html_text):
    soup = BeautifulSoup(html_text[:3_000_000], 'html.parser')
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'template', 'noscript']):
        element.decompose()
    hidden_class = re.compile(r'(?:^|[-_\s])(?:hidden|sr-only|visually-hidden|d-none|is-hidden|js-hidden)(?:[-_\s]|$)', re.I)
    for element in soup.find_all(True):
        if element.parent is None:
            continue
        style = element.get('style', '')
        classes = ' '.join(element.get('class', []))
        if ('hidden' in element.attrs or element.get('aria-hidden', '').lower() == 'true'
                or re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', style, re.I)
                or hidden_class.search(classes)):
            element.decompose()
    return normalize(soup.get_text(' ', strip=True))


def raw_artifact_allowed(url, content_type):
    return urlsplit(url).path.endswith(('.md', '.txt')) or any(
        value in content_type.lower() for value in ('text/markdown', 'text/plain', 'application/json', 'application/xml', 'text/xml'))


def decoded_text(response):
    if 'charset=' not in response.headers.get('content-type', '').lower():
        response.encoding = response.apparent_encoding or 'utf-8'
    return response.text


def checked_http_failure(result):
    return any(use['claim_status'] == 'checked'
               and use.get('manual_review', {}).get('decision') != 'keep'
               for use in result['uses'])


def check(url):
    result = {'url': url, 'uses': uses[url]}
    for use in result['uses']:
        review = reviews.get((use['app'], use['field'], url, use.get('quote', '')))
        if review:
            use['manual_review'] = review
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'},
                                timeout=25, allow_redirects=True)
        result.update(status=response.status_code, final_url=response.url)
        if response.status_code == 200:
            response_text = decoded_text(response)
            page = visible_text(response_text)
            raw_page = normalize(response_text)
            artifact_page = raw_page if raw_artifact_allowed(response.url, response.headers.get('content-type', '')) else ''
            page_tokens = tokens(page)
            raw_tokens = tokens(artifact_page)
            for use in result['uses']:
                quote = normalize(use['quote'])
                quote_tokens = tokens(quote)
                use['quote_exact'] = bool(quote and (quote in page or quote in artifact_page))
                use['quote_token_exact'] = bool(quote_tokens and (
                    contains_tokens(page_tokens, quote_tokens) or contains_tokens(raw_tokens, quote_tokens)))
                use['raw_html_only_match'] = bool(not artifact_page and quote and (
                    quote in raw_page or contains_tokens(tokens(raw_page), quote_tokens)))
                if quote:
                    use['start_fragment_found'] = quote[:50] in page or quote[:50] in artifact_page
                    use['end_fragment_found'] = quote[-50:] in page or quote[-50:] in artifact_page
                review = reviews.get((use['app'], use['field'], url, use.get('quote', '')))
                if review:
                    use['manual_review'] = review
            unresolved = [use for use in result['uses'] if use.get('quote')
                          and not use.get('quote_exact') and not use.get('quote_token_exact')]
            alternate_url = markdown_url(url)
            if unresolved and alternate_url:
                markdown_response = requests.get(alternate_url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'},
                                                 timeout=25, allow_redirects=True)
                if markdown_response.status_code == 200:
                    alternate = normalize(decoded_text(markdown_response))
                    alternate_tokens = tokens(alternate)
                    raw_page += ' ' + alternate
                    raw_tokens = tokens(raw_page)
                    for use in unresolved:
                        quote = normalize(use['quote'])
                        quote_tokens = tokens(quote)
                        use['quote_exact'] = quote in page or quote in raw_page
                        use['quote_token_exact'] = contains_tokens(page_tokens, quote_tokens) or contains_tokens(raw_tokens, quote_tokens)
                        if use['quote_exact'] or use['quote_token_exact']:
                            use['raw_html_only_match'] = False
                        use['start_fragment_found'] = quote[:50] in page or quote[:50] in raw_page
                        use['end_fragment_found'] = quote[-50:] in page or quote[-50:] in raw_page
                markdown_response.close()
        response.close()
    except Exception as exc:
        result['error'] = str(exc)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='checked_dataset_v4.json')
    parser.add_argument('--output', default='source_checks_v4.json')
    parser.add_argument('--review', help='Optional manual source-review log for browser-verified quotations')
    args = parser.parse_args()
    if args.review:
        review_log = json.loads(Path(args.review).read_text(encoding='utf-8'))
        reviews.update({(action['app'], action['field'], action['old_url'], action['old_quote']): action
                        for action in review_log['actions'] if action.get('decision') == 'keep'})
    rows = json.loads(Path(args.input).read_text(encoding='utf-8'))
    for row in rows:
        for field, claim in row['fields'].items():
            for source in claim.get('evidence', []):
                if source.get('url'):
                    uses.setdefault(source['url'], []).append({'app': row['app'], 'field': field,
                                                              'claim_status': claim['status'],
                                                              'quote': source.get('quote', '')})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, sorted(uses)))
    Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    http_bad = [result for result in results if result.get('status') != 200]
    checked_http_bad = [result for result in http_bad if checked_http_failure(result)]
    quote_bad = [use for result in results for use in result['uses']
                 if result.get('status') == 200 and use.get('quote')
                 and not use.get('quote_exact') and not use.get('quote_token_exact')]
    checked_quote_bad = [use for use in quote_bad if use['claim_status'] == 'checked'
                         and use.get('manual_review', {}).get('decision') != 'keep']
    manual_keeps = sum(use.get('manual_review', {}).get('decision') == 'keep'
                       and not use.get('quote_exact') and not use.get('quote_token_exact')
                       for result in results for use in result['uses'])
    print(f'{len(results)} unique URLs; {len(http_bad)} non-200/errors; {len(quote_bad)} quotes not reproduced by direct fetch')
    print(f'Checked-evidence failures: {len(checked_http_bad)} URLs; {len(checked_quote_bad)} quotes; '
          f'{manual_keeps} browser-reviewed quote keeps')
    for result in checked_http_bad:
        print('checked source', result.get('status', 'error'), result['url'])
    for result in http_bad:
        if result not in checked_http_bad:
            label = 'browser-reviewed checked source' if any(use['claim_status'] == 'checked' for use in result['uses']) else 'unknown attempted lookup'
            print(label, result.get('status', 'error'), result['url'])
    for use in checked_quote_bad[:60]:
        print('quote review', use['app'], use['field'], next(result['url'] for result in results if use in result['uses']))
    if checked_http_bad or checked_quote_bad:
        raise SystemExit(1)
