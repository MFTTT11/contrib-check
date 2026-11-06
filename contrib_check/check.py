"""Assess one GitHub bounty issue: is it open, claimed, crowded, already done, and is the repo merging?

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


CLAIM = re.compile(
    r"(?i)\b(?:I(?:'ll| will|'m going to| am going to)\s+(?:open|submit|send|raise|create|file|make)\s+"
    r"(?:a\s+|the\s+|my\s+)?(?:PR|pull request|fix)"
    r"|I(?:'m| am)\s+(?:currently\s+|already\s+)?working on (?:this|it|a fix)"
    r"|(?:can|could|may) I (?:work on|take|pick up) (?:this|it)"
    r"|I(?:'d| would) like to (?:work on|take|pick up) (?:this|it)"
    r"|assign (?:this |it )?to me)|(?<!\w)/attempt\b")
DONE = re.compile(
    r"(?i)\b(?:(?:can|should|could) be closed"
    r"|already (?:done|fixed|implemented|resolved|merged|has the changes)"
    r"|(?:fixed|resolved|addressed|implemented) (?:in|by|via) (?:#\d+|https://github\.com/\S+/pull/\d+)"
    r"|(?:is|looks|seems) (?:obsolete|outdated|no longer (?:relevant|needed|valid)))")
MAINTAINER = frozenset({'OWNER', 'MEMBER', 'COLLABORATOR'})


def _own_words(body: str) -> str:
    """Body text without fenced code blocks and quoted lines (quotes repeat other people)."""
    body = re.sub(r'(?s)```.*?```', ' ', str(body or ''))
    return '\n'.join(line for line in body.splitlines() if not line.lstrip().startswith('>'))


def _when(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def discussion(issue_data, comments, now, me: str | None = None, recent_days: int = 14):
    """Claims to work on the issue and remarks that it is already done.

    The issue text is checked for claims (a reporter announcing their own PR);
    comments are checked for claims and for 'can be closed' / 'already fixed'.
    A remark counts as authoritative only from an OWNER, MEMBER or COLLABORATOR.
    """
    cutoff = now - dt.timedelta(days=recent_days)
    entries = []
    if isinstance(issue_data, dict):
        entries.append(('issue', issue_data))
    entries += [('comment', c) for c in comments or [] if isinstance(c, dict)]
    claims, done = [], []
    for where, item in entries:
        login = (item.get('user') or {}).get('login', '')
        if me and login.casefold() == me.casefold():
            continue
        text = _own_words(item.get('body'))
        when = _when(item.get('created_at'))
        base = {'by': login, 'where': where, 'at': item.get('created_at'), 'url': item.get('html_url')}
        m = CLAIM.search(text)
        if m:
            claims.append(dict(base, quote=m.group(0), recent=bool(when and when >= cutoff)))
        m = DONE.search(text) if where == 'comment' else None
        if m:
            association = item.get('author_association') or ''
            done.append(dict(base, quote=m.group(0), association=association, maintainer=association in MAINTAINER))
    return {'claims': claims, 'done_remarks': done}


def assess(repo: str, issue: int, fetch=get_json, now=None, me: str | None = None, max_competing: int = 1,
           cache: dict | None = None):
    """Assess one issue. `cache` (optional dict) reuses per-repository lookups across calls."""
    now = now or dt.datetime.now(UTC)
    cache = {} if cache is None else cache
    report = {'repo': repo, 'issue': issue, 'checked_at': now.isoformat(), 'signals': {}, 'verdict': 'unknown',
              'reasons': [], 'notes': []}
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

    if sig['issue'].get('status') == 'ok' and isinstance(data, dict):
        comments, err = _safe(fetch, f'/repos/{repo}/issues/{issue}/comments?per_page=100')
        if err or not isinstance(comments, list):
            # The issue text is still checked; unread comments are reported, not assumed empty.
            sig['discussion'] = dict(discussion(data, [], now, me), status='partial', error=err or 'unexpected response')
        else:
            sig['discussion'] = dict(discussion(data, comments, now, me), status='ok', comments_read=len(comments))

    since = (now - dt.timedelta(days=14)).date().isoformat()
    key = ('activity', repo, since)
    if key not in cache:
        merged, err = _safe(search_issues, f'repo:{repo} is:pr is:merged merged:>={since}', fetch=fetch, per_page=5)
        if err or not isinstance(merged, dict):
            cache[key] = {'status': 'unknown', 'error': err}
        else:
            cache[key] = {'status': 'ok', 'merged_prs_14d': merged.get('total_count'),
                          'examples': [i.get('html_url') for i in merged.get('items', [])[:3]]}
    sig['activity'] = dict(cache[key])

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
    disc = sig.get('discussion') or {}
    if any(d['maintainer'] for d in disc.get('done_remarks', [])):
        reasons.append('a maintainer said the issue can be closed or is already done')
    elif disc.get('done_remarks'):
        report['notes'].append('a commenter said the issue is already done (not confirmed by a maintainer)')
    recent = sorted({c['by'] for c in disc.get('claims', []) if c['recent']})
    if recent:
        reasons.append('claimed in the last 14 days by ' + ', '.join(recent))
    older = sorted({c['by'] for c in disc.get('claims', []) if not c['recent']} - set(recent))
    if older:
        report['notes'].append('older claims by ' + ', '.join(older))
    if disc.get('status') == 'partial':
        report['notes'].append('comments could not be read; only the issue text was checked for claims')
    report['verdict'] = 'skip' if reasons else 'worth_a_look'
    return report
