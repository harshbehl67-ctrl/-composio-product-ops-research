"""Check direct evidence links from a checked dataset."""
import argparse
import concurrent.futures
import json
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument('--input', default='checked_dataset_v4.json')
parser.add_argument('--output', default='link_checks_v4.json')
parser.add_argument('--review', help='Optional manual source-review log for browser-verified links')
args = parser.parse_args()
reviews = {}
if args.review:
    review_log = json.loads(Path(args.review).read_text(encoding='utf-8'))
    reviews.update({(action['app'], action['field'], action['old_url'], action['old_quote']): action
                    for action in review_log['actions'] if action.get('decision') == 'keep'})
rows = json.loads(Path(args.input).read_text(encoding='utf-8'))
uses = {}
for row in rows:
    for field, claim in row['fields'].items():
        for source in claim.get('evidence', []):
            if source.get('url'):
                use = {'app': row['app'], 'field': field, 'claim_status': claim['status'],
                       'quote': source.get('quote', '')}
                use['browser_reviewed'] = (row['app'], field, source['url'], use['quote']) in reviews
                uses.setdefault(source['url'], []).append(use)
urls = sorted(uses)


def checked_link_failure(result):
    return any(use['claim_status'] == 'checked' and not use.get('browser_reviewed')
               for use in result['uses'])


def check(url):
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; ProductOpsResearch/4.0)'},
                                timeout=25, allow_redirects=True, stream=True)
        result = {'url': url, 'uses': uses[url], 'status': response.status_code, 'final_url': response.url}
        response.close()
        return result
    except Exception as exc:
        return {'url': url, 'uses': uses[url], 'error': str(exc)}


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, urls))
    Path(args.output).write_text(json.dumps(results, indent=2), encoding='utf-8')
    bad = [result for result in results if result.get('status', 0) >= 400 or 'error' in result]
    checked_bad = [result for result in bad if checked_link_failure(result)]
    attempted_bad = [result for result in bad if not any(use['claim_status'] == 'checked' for use in result['uses'])]
    print(f'{len(results)} URLs checked; {len(checked_bad)} broken checked-evidence links; '
          f'{len(attempted_bad)} failed attempted lookups retained for unknown claims')
    for result in checked_bad:
        print('checked evidence', result)
    for result in bad:
        if result not in checked_bad and any(use['claim_status'] == 'checked' for use in result['uses']):
            print('browser-reviewed checked source', result.get('status', 'error'), result['url'])
    for result in attempted_bad:
        print('unknown attempted lookup', result['url'])
    if checked_bad:
        raise SystemExit(1)
