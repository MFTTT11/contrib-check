"""Find open bounty issues in an organization or repository and assess each one.

Search queries cover the common conventions: the `bounty` label (any case), the
`💎 Bounty` label used by bounty platforms, free-text "bounty", plus any labels
passed with --label. For a single repository, its bounty-like labels are also
discovered from the labels endpoint. Every candidate then goes through
`assess`, and results are ranked: worth a look first, then by fewer reasons to
skip, then most recently updated.
"""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse

from .check import AMOUNT, _safe, assess
from .github import get_json, search_issues

BOUNTY_LABEL = re.compile(r'(?i)bount|reward|💎|\bB-\d')
REPO_URL = re.compile(r'https://github\.com/([^/]+/[^/]+)/issues/(\d+)\Z')


def _scope(target: str) -> str:
    return f'repo:{target}' if '/' in target else f'org:{target}'


def queries(target: str, labels=()) -> list[str]:
    scope = _scope(target)
    out = [f'{scope} is:issue is:open label:bounty', f'{scope} is:issue is:open label:"💎 Bounty"',
           f'{scope} is:issue is:open bounty']
    out += [f'{scope} is:issue is:open label:"{name}"' for name in labels if name and '"' not in name]
    return list(dict.fromkeys(out))


def repo_bounty_labels(repo: str, fetch=get_json) -> list[str]:
    """Bounty-like label names defined in one repository ([] if the endpoint is unavailable)."""
    data, err = _safe(fetch, f'/repos/{repo}/labels?per_page=100')
    if err or not isinstance(data, list):
        return []
    return [l['name'] for l in data if isinstance(l, dict) and BOUNTY_LABEL.search(str(l.get('name', '')))]


def candidates(target: str, fetch=get_json, labels=(), per_page: int = 50):
    """Open issues (not PRs) that carry a bounty-like label or an amount in the title. Returns (items, errors)."""
    labels = list(labels)
    if '/' in target:
        labels += repo_bounty_labels(target, fetch)
    found, errors = {}, []
    for q in queries(target, labels):
        res, err = _safe(search_issues, q, fetch=fetch, per_page=per_page)
        if err or not isinstance(res, dict):
            errors.append({'query': q, 'error': err or 'unexpected response'})
            continue
        for it in res.get('items') or []:
            url = str(it.get('html_url') or '')
            if 'pull_request' in it or not REPO_URL.fullmatch(url) or it.get('state') != 'open':
                continue
            names = [l.get('name', '') for l in it.get('labels') or [] if isinstance(l, dict)]
            if any(BOUNTY_LABEL.search(n) for n in names) or AMOUNT.search(str(it.get('title') or '')):
                found.setdefault(url, it)
    return list(found.values()), errors


def _rank(row):
    return (row['verdict'] != 'worth_a_look', row['verdict'] == 'unknown', len(row['reasons']),
            -dt.datetime.fromisoformat(str(row.get('updated_at') or '1970-01-01T00:00:00+00:00').replace('Z', '+00:00')).timestamp())


def scan(target: str, fetch=get_json, now=None, me: str | None = None, labels=(), limit: int = 15,
         max_competing: int = 1):
    """Assess up to `limit` bounty issues (most recently updated first) and rank them."""
    now = now or dt.datetime.now(dt.timezone.utc)
    items, errors = candidates(target, fetch, labels)
    items.sort(key=lambda it: str(it.get('updated_at') or ''), reverse=True)
    cache, rows = {}, []
    for it in items[:max(0, limit)]:
        repo, number = REPO_URL.fullmatch(it['html_url']).groups()
        report = assess(repo, int(number), fetch=fetch, now=now, me=me, max_competing=max_competing, cache=cache)
        issue = report['signals'].get('issue', {})
        rows.append({'url': it['html_url'], 'title': str(it.get('title') or '')[:120], 'updated_at': it.get('updated_at'),
                     'verdict': report['verdict'], 'reasons': report['reasons'], 'notes': report['notes'],
                     'bounty_labels': issue.get('bounty_labels', []), 'amounts': issue.get('amount_mentions', []),
                     'competing_prs': len((report['signals'].get('competition') or {}).get('open_prs') or [])})
    rows.sort(key=_rank)
    return {'target': target, 'checked_at': now.isoformat(), 'found': len(items), 'assessed': len(rows),
            'errors': errors, 'results': rows}


def table(result) -> str:
    lines = [f"{result['target']}: {result['found']} bounty issues found, {result['assessed']} assessed"]
    for r in result['results']:
        tag = {'worth_a_look': 'LOOK', 'skip': 'skip', 'unknown': '????'}.get(r['verdict'], r['verdict'])
        money = ', '.join(r['amounts'] or r['bounty_labels'])[:30]
        why = '; '.join(r['reasons'])[:90]
        lines.append(f"{tag:4}  {r['url']}  [{money}]  {why}")
    for e in result['errors']:
        lines.append(f"error: {e['error']} for {urllib.parse.unquote(e['query'])}")
    return '\n'.join(lines)
