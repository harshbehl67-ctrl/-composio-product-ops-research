"""Second-stage access-condition extraction from frozen pass-2 pages.

Outputs a separate provisional pass. Matches quote a context window and require
independent review; they are not categorical statements about every API scope.
"""
import json
import re
from pathlib import Path

apps = json.loads(Path('apps.json').read_text(encoding='utf-8'))
out = Path('data/pass3')
out.mkdir(exist_ok=True)
patterns = [
    ('self-serve / free or trial mentioned', r'\b(?:free plan|free tier|free trial|developer account|developer sandbox|development store)\b.{0,140}\b(?:api|token|credential|developer|app)\b|\b(?:api|token|credential)\b.{0,140}\b(?:free plan|free tier|free trial|developer account|developer sandbox)\b'),
    ('paid-plan condition mentioned', r'\b(?:api|api access)\b.{0,100}\b(?:requires?|only available|available only)\b.{0,90}\b(?:paid|subscription|plan)\b'),
    ('approval condition mentioned', r'\b(?:app|api|integration)\b.{0,100}\b(?:requires?|must|need(?:s)?)\b.{0,60}\b(?:approval|review|approved)\b'),
    ('administrator-controlled credential mentioned', r'\b(?:admin|administrator|owner)\b.{0,100}\b(?:create|generate|manage)\b.{0,100}\b(?:api key|token|credential)\b'),
]
answered = 0
for app in apps:
    source = Path(f"data/pass2/{app['number']:03}.json")
    data = json.loads(source.read_text(encoding='utf-8'))
    matches = []
    for page in data['pages']:
        if page.get('status') != 200:
            continue
        text = page.get('text', '')
        for label, pattern in patterns:
            for match in list(re.finditer(pattern, text, re.I))[:2]:
                excerpt = text[max(0, match.start()-100):min(len(text), match.end()+150)]
                matches.append({'value': label, 'url': page['url'], 'excerpt': excerpt,
                                'status': 'provisional; check scope, negation and plan details'})
    answered += bool(matches)
    result = {'app': app['name'], 'source_pass': str(source), 'access_candidates': matches,
              'reason_if_unknown': '' if matches else 'No access-condition phrase matched the retrieved candidate pages; targeted results require human-style review.',
              'warning': 'A phrase match is not a verified credential gate or a buildability verdict.'}
    (out / f"{app['number']:03}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Access-condition candidate excerpts: {answered}/100 apps; none promoted automatically to verified.')
