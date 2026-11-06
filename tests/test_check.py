import datetime as dt
import unittest

from contrib_check.check import assess

NOW = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)


BASE_ISSUE = {'state': 'open', 'assignees': [], 'labels': [{'name': 'Bounty 100 ERG'}], 'title': 'Fix x', 'comments': 2}


def fake(issue=None, prs=(), merged=3, fail=(), merged_items=(), comments=()):
    issue = issue or BASE_ISSUE

    def fetch(path, token=None, timeout=15):
        if any(f in path for f in fail):
            raise OSError('down')
        if path.startswith('/repos/') and '/comments' in path:
            return list(comments)
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


class PaidLabelTest(unittest.TestCase):
    def test_rewarded_label_means_bounty_already_paid(self):
        issue = dict(BASE_ISSUE, labels=[{'name': '💎 Bounty'}, {'name': '💰 Rewarded'}])
        r = assess('o/r', 7, fetch=fake(issue=issue), now=NOW)
        self.assertEqual(r['verdict'], 'skip')
        self.assertIn('bounty already marked as paid (💰 Rewarded)', r['reasons'])
        self.assertEqual(r['signals']['issue']['paid_labels'], ['💰 Rewarded'])

    def test_plain_bounty_label_is_not_paid(self):
        r = assess('o/r', 7, fetch=fake(issue=dict(BASE_ISSUE, labels=[{'name': '💎 Bounty'}, {'name': 'unpaid work'}])), now=NOW)
        self.assertEqual(r['signals']['issue']['paid_labels'], [])
        self.assertEqual(r['verdict'], 'worth_a_look')


class AlreadyFixedTest(unittest.TestCase):
    def test_merged_pr_with_same_title_words_flags_issue(self):
        issue = {'state': 'open', 'assignees': [], 'labels': [], 'title': 'Allow custom property names in kicadFootprintMetadata properties',
                 'created_at': '2026-11-05T18:50:36Z'}
        fix = {'html_url': 'https://github.com/o/r/pull/9', 'title': 'Allow custom KiCad metadata property names'}
        other = {'html_url': 'https://github.com/o/r/pull/8', 'title': 'Bump dependencies'}
        r = assess('o/r', 7, fetch=fake(issue=issue, merged_items=[fix, other]), now=NOW)
        self.assertEqual([p['url'] for p in r['signals']['possibly_fixed']['merged_prs']], ['https://github.com/o/r/pull/9'])
        self.assertIn('a PR merged after the issue was opened looks like the same fix', r['reasons'])


def comment(body, login='x', association='CONTRIBUTOR', at='2026-11-01T00:00:00Z'):
    return {'body': body, 'user': {'login': login}, 'author_association': association, 'created_at': at,
            'html_url': 'https://github.com/o/r/issues/7#issuecomment-1'}


class DiscussionTest(unittest.TestCase):
    def test_maintainer_saying_done_skips_the_issue(self):
        comments = [comment('This looks already done.', 'c1'), comment('yes, can be closed indeed', 'm1', 'COLLABORATOR')]
        r = assess('o/r', 7, fetch=fake(comments=comments), now=NOW)
        self.assertEqual(r['verdict'], 'skip')
        self.assertIn('a maintainer said the issue can be closed or is already done', r['reasons'])

    def test_done_remark_from_non_maintainer_is_only_a_note(self):
        comments = [comment('This should be closed, current already has the changes.', 'c1')]
        r = assess('o/r', 7, fetch=fake(comments=comments), now=NOW)
        self.assertEqual(r['verdict'], 'worth_a_look')
        self.assertIn('a commenter said the issue is already done (not confirmed by a maintainer)', r['notes'])

    def test_reporter_announcing_a_pr_is_a_recent_claim(self):
        issue = dict(BASE_ISSUE, body="Proposed fix: follow the cursor.\n\nI'll open a PR for (1) with tests.",
                     user={'login': 'rep'}, created_at='2026-11-02T18:29:31Z')
        r = assess('o/r', 7, fetch=fake(issue=issue), now=NOW)
        self.assertEqual(r['verdict'], 'skip')
        self.assertIn('claimed in the last 14 days by rep', r['reasons'])

    def test_old_quoted_and_own_claims_do_not_block(self):
        comments = [comment('Can I work on this?', 'old', at='2025-01-01T00:00:00Z'),
                    comment("> I'll open a PR\nThanks, sounds good.", 'q'),
                    comment("```\nI'm working on this\n```", 'q2'),
                    comment("I'm working on this", 'me')]
        r = assess('o/r', 7, fetch=fake(comments=comments), now=NOW, me='me')
        self.assertEqual(r['verdict'], 'worth_a_look')
        self.assertEqual([c['by'] for c in r['signals']['discussion']['claims']], ['old'])
        self.assertIn('older claims by old', r['notes'])

    def test_unreadable_comments_still_check_issue_text(self):
        issue = dict(BASE_ISSUE, body='I am working on this.', user={'login': 'rep'}, created_at='2026-11-04T00:00:00Z')
        r = assess('o/r', 7, fetch=fake(issue=issue, fail=('/comments',)), now=NOW)
        self.assertEqual(r['signals']['discussion']['status'], 'partial')
        self.assertIn('claimed in the last 14 days by rep', r['reasons'])
        self.assertIn('comments could not be read; only the issue text was checked for claims', r['notes'])


class FallbackTest(unittest.TestCase):
    def test_issue_read_falls_back_to_search(self):
        r = assess('o/r', 7, fetch=fake(fail=('repo_endpoint',)), now=NOW)
        self.assertEqual(r['signals']['issue']['status'], 'ok')
        self.assertEqual(r['verdict'], 'worth_a_look')


if __name__ == '__main__':
    unittest.main()
