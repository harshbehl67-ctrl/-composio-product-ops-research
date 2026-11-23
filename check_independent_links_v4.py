"""Check independent-review citation links, allowing explicit browser verification."""
import argparse
import concurrent.futures
import json
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument('--input', default='independent_review_v4.json')
parser.add_argument('--output', default='independent_link_checks_v4.json')
parser.add_argument('--review', help='Optional JSON list of browser-verified URLs')
args = parser.parse_args()
review = json.loads(Path(args.review).read_text(encoding='utf-8')) if args.review else {'verified': []}
verified = {item['url']: item for item in review.get('verified', [])}
data = json.loads(Path(args.input).read_text(encoding='utf-8'))
uses = {}
for sample_name in ('selected_sample', 'random_holdout'):
    for record in data[sample_name]['records']:
        for url in record.get('independent_sources', []):
            uses.setdefault(url, []).append({'sample': sample_name, 'app': record['app'], 'field': record['field']})


def check(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'},
                                timeout=25, allow_redirects=True, stream=True)
        result = {'url': url, 'uses': uses[url], 'status': response.status_code, 'final_url': response.url}
        response.close()
    except Exception as exc:
        result = {'url': url, 'uses': uses[url], 'error': str(exc)}
    if url in verified:
        result['browser_review'] = verified[url]
    return result


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, sorted(uses)))
    Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    bad = [result for result in results if result.get('status', 0) >= 400 or 'error' in result]
    unresolved = [result for result in bad if result['url'] not in verified]
    print(f'{len(results)} unique independent-review URLs; {len(bad)} direct failures; '
          f'{len(bad) - len(unresolved)} browser-verified; {len(unresolved)} unresolved')
    for result in unresolved:
        print('independent source', result.get('status', 'error'), result['url'])
    if unresolved:
        raise SystemExit(1)
