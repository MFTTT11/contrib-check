"""Assess one GitHub bounty issue: is it open, claimed, crowded, and is the repo merging?

Every signal is reported with its source. A failed lookup is 'unknown', never
treated as a positive signal.
"""
from __future__ import annotations

import datetime as dt
import re

from .github import get_json, search_issues

UTC = dt.timezone.utc
AMOUNT = re.compile(r'(?i)(?:\$\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?(?:USD[CT]?|ERG|SigUSD|SOL|ETH))')


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs), None
    except Exception as exc:  # noqa: BLE001 - network/provider errors vary
        return None, type(exc).__name__


def competing_prs(repo: str, issue: int, items, exclude_author: str | None = None):
    ref = re.compile(rf'(?<![\w/])#{issue}\b')
    out = []
    for it in items or []:
        if 'pull_request' not in it or it.get('state') != 'open':
            continue
        author = (it.get('user') or {}).get('login', '')
        if exclude_author and author.casefold() == exclude_author.casefold():
            continue
        if ref.search(f"{it.get('title') or ''}\n{it.get('body') or ''}"):
            out.append({'url': it.get('html_url'), 'author': author, 'created_at': it.get('created_at')})
    return out


STOP = frozenset('a an the and or of to in on for with from by is are be not when only can into as at it its this that'.split())


def _words(text):
    return {w for w in re.findall(r'[a-z0-9_]{3,}', str(text).lower()) if w not in STOP}


def likely_fixed(issue_title: str, merged_items, min_overlap: int = 3, min_ratio: float = 0.5):
    """Merged PRs whose titles share most significant words with the issue title.

    Catches fixes that never mention the issue number. A heuristic signal only.
    """
    want = _words(issue_title)
    out = []
    for it in merged_items or []:
        have = _words(it.get('title'))
        shared = want & have
        if want and len(shared) >= min_overlap and len(shared) / len(want) >= min_ratio:
            out.append({'url': it.get('html_url'), 'title': it.get('title'), 'shared_words': sorted(shared)})
    return out


def assess(repo: str, issue: int, fetch=get_json, now=None, me: str | None = None, max_competing: int = 1):
    now = now or dt.datetime.now(UTC)
    report = {'repo': repo, 'issue': issue, 'checked_at': now.isoformat(), 'signals': {}, 'verdict': 'unknown', 'reasons': []}
    sig = report['signals']

    data, err = _safe(fetch, f'/repos/{repo}/issues/{issue}')
    if err or not isinstance(data, dict):
        # Some environments deny the repository endpoint; issue search returns the same fields.
        found, err2 = _safe(search_issues, f'repo:{repo} is:issue {issue}', fetch=fetch, per_page=20)
        url = f'https://github.com/{repo}/issues/{issue}'
        match = [i for i in (found or {}).get('items', []) if i.get('html_url') == url] if not err2 else []
        if match:
            data, err = match[0], None
    if err or not isinstance(data, dict):
        sig['issue'] = {'status': 'unknown', 'error': err}
    else:
        labels = [l.get('name', '') for l in data.get('labels') or [] if isinstance(l, dict)]
        text = f"{data.get('title') or ''} {' '.join(labels)}"
        sig['issue'] = {'status': 'ok', 'state': data.get('state'), 'assignees': [a.get('login') for a in data.get('assignees') or []],
                        'bounty_labels': [l for l in labels if re.search(r'(?i)bount|reward|\$|💎', l)],
                        'amount_mentions': AMOUNT.findall(text)[:5], 'comments': data.get('comments'),
                        'is_pull_request': 'pull_request' in data}

    found, err = _safe(search_issues, f'repo:{repo} is:pr is:open {issue}', fetch=fetch)
    if err or not isinstance(found, dict):
        sig['competition'] = {'status': 'unknown', 'error': err}
    else:
        prs = competing_prs(repo, issue, found.get('items'), me)
        sig['competition'] = {'status': 'ok', 'open_prs': prs}

    created = None
    if sig['issue'].get('status') == 'ok' and isinstance(data, dict):
        created = str(data.get('created_at') or '')[:10] or None
    if created:
        recent, err = _safe(search_issues, f'repo:{repo} is:pr is:merged merged:>={created}', fetch=fetch, per_page=50)
        if err or not isinstance(recent, dict):
            sig['possibly_fixed'] = {'status': 'unknown', 'error': err}
        else:
            sig['possibly_fixed'] = {'status': 'ok', 'merged_prs': likely_fixed(data.get('title', ''), recent.get('items'))}

    since = (now - dt.timedelta(days=14)).date().isoformat()
    merged, err = _safe(search_issues, f'repo:{repo} is:pr is:merged merged:>={since}', fetch=fetch, per_page=5)
    if err or not isinstance(merged, dict):
        sig['activity'] = {'status': 'unknown', 'error': err}
    else:
        sig['activity'] = {'status': 'ok', 'merged_prs_14d': merged.get('total_count'),
                           'examples': [i.get('html_url') for i in merged.get('items', [])[:3]]}

    reasons = report['reasons']
    issue_sig, comp, act = sig['issue'], sig['competition'], sig['activity']
    if issue_sig.get('status') != 'ok' or comp.get('status') != 'ok' or act.get('status') != 'ok':
        reasons.append('some signals could not be read')
        return report
    if issue_sig['is_pull_request'] or issue_sig['state'] != 'open':
        reasons.append('issue is not open')
    if issue_sig['assignees']:
        reasons.append('issue is assigned')
    if not issue_sig['bounty_labels'] and not issue_sig['amount_mentions']:
        reasons.append('no bounty label or amount on the issue')
    if len(comp['open_prs']) > max_competing:
        reasons.append(f"{len(comp['open_prs'])} open competing PRs")
    if (sig.get('possibly_fixed') or {}).get('merged_prs'):
        reasons.append('a PR merged after the issue was opened looks like the same fix')
    if not act['merged_prs_14d']:
        reasons.append('no merged PRs in the last 14 days')
    report['verdict'] = 'skip' if reasons else 'worth_a_look'
    return report
