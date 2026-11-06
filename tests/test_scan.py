import datetime as dt
import email.message
import io
import unittest
import urllib.error

from contrib_check import github
from contrib_check.scan import candidates, queries, scan, table

NOW = dt.datetime(2026, 11, 6, tzinfo=dt.timezone.utc)


def item(n, title='Fix x', labels=('bounty',), pr=False, updated='2026-11-01T00:00:00Z', repo='o/r'):
    it = {'html_url': f'https://github.com/{repo}/issues/{n}', 'number': n, 'title': title, 'state': 'open',
          'labels': [{'name': l} for l in labels], 'updated_at': updated, 'assignees': [], 'comments': 0,
          'user': {'login': 'reporter'}, 'body': '', 'created_at': '2026-10-01T00:00:00Z'}
    if pr:
        it['pull_request'] = {}
    return it


class FakeGitHub:
    def __init__(self, by_query, issues, labels=None, competing=None):
        self.by_query, self.issues, self.labels, self.competing = by_query, issues, labels, competing or {}
        self.calls = []

    def __call__(self, path, token=None, timeout=15):
        self.calls.append(path)
        if path.startswith('/repos/') and path.endswith('/labels?per_page=100'):
            if self.labels is None:
                raise OSError('denied')
            return [{'name': n} for n in self.labels]
        if path.startswith('/repos/') and '/comments' in path:
            return []
        if path.startswith('/repos/'):
            n = int(path.rsplit('/', 1)[1])
            return self.issues[n]
        q = github.urllib.parse.parse_qs(github.urllib.parse.urlsplit(path).query)['q'][0]
        if 'is:pr is:open' in q:
            n = int(q.rsplit(' ', 1)[1])
            return {'items': self.competing.get(n, [])}
        if 'is:merged' in q:
            return {'total_count': 4, 'items': []}
        return {'items': self.by_query.get(q, [])}


class QueryTest(unittest.TestCase):
    def test_org_and_repo_scopes_and_extra_labels(self):
        self.assertIn('org:tscircuit is:issue is:open label:"💎 Bounty"', queries('tscircuit'))
        q = queries('o/r', ['Bounty - 100 SigUSD', 'bad"label'])
        self.assertIn('repo:o/r is:issue is:open label:"Bounty - 100 SigUSD"', q)
        self.assertFalse(any('bad' in x for x in q))


class CandidateTest(unittest.TestCase):
    def test_dedupes_drops_prs_and_non_bounty_items_and_discovers_repo_labels(self):
        a, b = item(1), item(2, labels=('Bounty - 100 SigUSD',))
        by_query = {
            'repo:o/r is:issue is:open label:bounty': [a, item(3, pr=True)],
            'repo:o/r is:issue is:open bounty': [a, item(4, title='Docs typo', labels=('docs',))],
            'repo:o/r is:issue is:open label:"Bounty - 100 SigUSD"': [b],
        }
        fake = FakeGitHub(by_query, {}, labels=['Bounty - 100 SigUSD', 'bug'])
        found, errors = candidates('o/r', fake)
        self.assertEqual(sorted(i['number'] for i in found), [1, 2])
        self.assertEqual(errors, [])

    def test_label_discovery_failure_is_not_fatal(self):
        fake = FakeGitHub({'repo:o/r is:issue is:open label:bounty': [item(1)]}, {}, labels=None)
        found, _ = candidates('o/r', fake)
        self.assertEqual([i['number'] for i in found], [1])


class ScanTest(unittest.TestCase):
    def test_ranks_worth_a_look_first_and_caches_repo_activity(self):
        crowded, clean = item(1, updated='2026-11-05T00:00:00Z'), item(2, title='Add 50 USDC export', updated='2026-11-01T00:00:00Z')
        pr = {'pull_request': {}, 'state': 'open', 'title': 'Fix #1', 'body': '', 'user': {'login': 'x'},
              'html_url': 'https://github.com/o/r/pull/9', 'created_at': '2026-11-02T00:00:00Z'}
        competing = {1: [pr, dict(pr, html_url='https://github.com/o/r/pull/10', user={'login': 'y'})]}
        fake = FakeGitHub({'repo:o/r is:issue is:open label:bounty': [crowded, clean]},
                          {1: crowded, 2: clean}, labels=[], competing=competing)
        result = scan('o/r', fetch=fake, now=NOW)
        self.assertEqual([r['url'][-1] for r in result['results']], ['2', '1'])
        self.assertEqual(result['results'][0]['verdict'], 'worth_a_look')
        self.assertIn('2 open competing PRs', result['results'][1]['reasons'])
        activity_calls = [c for c in fake.calls if c.endswith('per_page=5')]
        self.assertEqual(len(activity_calls), 1)
        text = table(result)
        self.assertIn('LOOK  https://github.com/o/r/issues/2', text)
        self.assertIn('skip  https://github.com/o/r/issues/1', text)

    def test_limit_and_search_errors_are_reported(self):
        def failing(path, token=None, timeout=15):
            raise OSError('down')
        result = scan('tscircuit', fetch=failing, now=NOW)
        self.assertEqual(result['results'], [])
        self.assertEqual(len(result['errors']), 3)
        self.assertIn('error: OSError for org:tscircuit is:issue is:open label:bounty', table(result))


def http_error(code, **headers):
    msg = email.message.Message()
    for k, v in headers.items():
        msg[k.replace('_', '-')] = v
    return urllib.error.HTTPError('https://api.github.com/x', code, 'err', msg, io.BytesIO(b''))


class RateLimitTest(unittest.TestCase):
    def opener(self, *outcomes):
        outcomes = list(outcomes)

        def open_(req, timeout=15):
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return io.BytesIO(out)
        return open_

    def test_waits_for_retry_after_then_retries_once(self):
        waits = []
        data = github.get_json('/x', token='', opener=self.opener(http_error(403, Retry_After='2'), b'{"ok": 1}'),
                               sleep=waits.append)
        self.assertEqual(data, {'ok': 1})
        self.assertEqual(waits, [2.0])

    def test_uses_reset_header_and_gives_up_on_long_waits_or_other_errors(self):
        waits = []
        err = http_error(403, X_RateLimit_Remaining='0', X_RateLimit_Reset='1030')
        github.get_json('/x', token='', opener=self.opener(err, b'[]'), sleep=waits.append, clock=lambda: 1000.0)
        self.assertEqual(waits, [31.0])
        with self.assertRaises(urllib.error.HTTPError):
            github.get_json('/x', token='', opener=self.opener(http_error(429, Retry_After='600')), sleep=waits.append)
        with self.assertRaises(urllib.error.HTTPError):
            github.get_json('/x', token='', opener=self.opener(http_error(404)), sleep=waits.append)
        self.assertEqual(waits, [31.0])


if __name__ == '__main__':
    unittest.main()
