"""Minimal GitHub REST/search client (stdlib only)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
USER_AGENT = 'contrib-check/0.4'


def _rate_limit_wait(err: urllib.error.HTTPError, now: float) -> float | None:
    """Seconds to wait before retrying a rate-limited request, or None if it is another error."""
    if err.code not in (403, 429):
        return None
    headers = err.headers or {}
    retry_after = headers.get('Retry-After')
    if retry_after and str(retry_after).strip().isdigit():
        return float(retry_after)
    if headers.get('X-RateLimit-Remaining') == '0' and str(headers.get('X-RateLimit-Reset', '')).isdigit():
        return max(0.0, float(headers['X-RateLimit-Reset']) - now) + 1
    return None


def get_json(path: str, token: str | None = None, timeout: float = 15, opener=urllib.request.urlopen,
             sleep=time.sleep, clock=time.time, max_wait: float = 65):
    """GET a GitHub API path. A rate-limited request waits (at most `max_wait` seconds) and is retried once."""
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': USER_AGENT,
               'X-GitHub-Api-Version': '2022-11-28'}
    token = token if token is not None else os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    for attempt in (1, 2):
        try:
            with opener(urllib.request.Request(API + path, headers=headers), timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            wait = _rate_limit_wait(err, clock())
            if attempt == 2 or wait is None or wait > max_wait:
                raise
            sleep(wait)


def search_issues(query: str, fetch=get_json, per_page: int = 50):
    return fetch('/search/issues?' + urllib.parse.urlencode({'q': query, 'per_page': per_page}))
