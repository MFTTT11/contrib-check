import datetime as dt
import unittest

from contrib_check.check import assess

NOW = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)


def fake(issue=None, prs=(), merged=3, fail=(), merged_items=()):
    issue = issue or {'state': 'open', 'assignees': [], 'labels': [{'name': 'Bounty 100 ERG'}], 'title': 'Fix x', 'comments': 2}

    def fetch(path, token=None, timeout=15):
        if any(f in path for f in fail):
            raise OSError('down')
        if path.startswith('/repos/'):
            if 'repo_endpoint' in fail:
                raise OSError('denied')
            return issue
        if 'is%3Aissue' in path:
            return {'items': [dict(issue, html_url='https://github.com/o/r/issues/7')]}
        if 'is%3Amerged' in path:
            return {'total_count': merged, 'items': list(merged_items)}
        return {'items': list(prs)}
    return fetch


def pr(n, title, author='x', state='open'):
    return {'pull_request': {}, 'state': state, 'title': title, 'body': '', 'user': {'login': author},
            'html_url': f'https://github.com/o/r/pull/{n}', 'created_at': '2026-11-01T00:00:00Z'}


class AssessTest(unittest.TestCase):
    def test_clean_bounty_is_worth_a_look(self):
        r = assess('o/r', 7, fetch=fake(), now=NOW)
        self.assertEqual(r['verdict'], 'worth_a_look')
        self.assertEqual(r['signals']['issue']['amount_mentions'], ['100 ERG'])

    def test_crowded_assigned_or_inactive_is_skipped(self):
        r = assess('o/r', 7, fetch=fake(prs=[pr(1, 'Fix #7'), pr(2, 'Closes #7')]), now=NOW)
        self.assertIn('2 open competing PRs', r['reasons'])
        r = assess('o/r', 7, fetch=fake(issue={'state': 'open', 'assignees': [{'login': 'a'}], 'labels': [], 'title': 't'}), now=NOW)
        self.assertEqual(r['verdict'], 'skip')
        self.assertIn('issue is assigned', r['reasons'])
        self.assertIn('no merged PRs in the last 14 days', assess('o/r', 7, fetch=fake(merged=0), now=NOW)['reasons'])

    def test_own_pr_and_unrelated_numbers_not_counted(self):
        prs = [pr(1, 'Fix #7', author='me'), pr(2, 'bump 70 deps'), pr(3, 'Fix #70')]
        r = assess('o/r', 7, fetch=fake(prs=prs), now=NOW, me='me')
        self.assertEqual(r['signals']['competition']['open_prs'], [])

    def test_failed_lookup_is_unknown_not_positive(self):
        r = assess('o/r', 7, fetch=fake(fail=('is%3Aopen',)), now=NOW)
        self.assertEqual(r['verdict'], 'unknown')
        self.assertEqual(r['signals']['competition']['status'], 'unknown')


class AlreadyFixedTest(unittest.TestCase):
    def test_merged_pr_with_same_title_words_flags_issue(self):
        issue = {'state': 'open', 'assignees': [], 'labels': [], 'title': 'Allow custom property names in kicadFootprintMetadata properties',
                 'created_at': '2026-11-05T18:50:36Z'}
        fix = {'html_url': 'https://github.com/o/r/pull/9', 'title': 'Allow custom KiCad metadata property names'}
        other = {'html_url': 'https://github.com/o/r/pull/8', 'title': 'Bump dependencies'}
        r = assess('o/r', 7, fetch=fake(issue=issue, merged_items=[fix, other]), now=NOW)
        self.assertEqual([p['url'] for p in r['signals']['possibly_fixed']['merged_prs']], ['https://github.com/o/r/pull/9'])
        self.assertIn('a PR merged after the issue was opened looks like the same fix', r['reasons'])


class FallbackTest(unittest.TestCase):
    def test_issue_read_falls_back_to_search(self):
        r = assess('o/r', 7, fetch=fake(fail=('repo_endpoint',)), now=NOW)
        self.assertEqual(r['signals']['issue']['status'], 'ok')
        self.assertEqual(r['verdict'], 'worth_a_look')


if __name__ == '__main__':
    unittest.main()
