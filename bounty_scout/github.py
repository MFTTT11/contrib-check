"""Minimal GitHub REST/search client (stdlib only)."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

API = 'https://api.github.com'


def get_json(path: str, token: str | None = None, timeout: float = 15):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'bounty-scout/0.1',
               'X-GitHub-Api-Version': '2022-11-28'}
    token = token if token is not None else os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=timeout) as resp:
        return json.load(resp)


def search_issues(query: str, fetch=get_json, per_page: int = 50):
    return fetch('/search/issues?' + urllib.parse.urlencode({'q': query, 'per_page': per_page}))
