import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adfText, githubIssueRefs, discussion, competingPrs, similarIssues, searchTerms, verdict } from '../src/checks.js';

const NOW = new Date('2026-11-06T00:00:00Z');

test('adfText reads text and link targets from an ADF document', () => {
  const doc = { type: 'doc', content: [{ type: 'paragraph', content: [
    { type: 'text', text: 'Upstream:' },
    { type: 'text', text: 'link', marks: [{ type: 'link', attrs: { href: 'https://github.com/o/r/issues/7' } }] },
    { type: 'inlineCard', attrs: { url: 'https://github.com/o/r/issues/8' } }] }] };
  const text = adfText(doc);
  assert.match(text, /Upstream:/);
  assert.deepEqual(githubIssueRefs(text).map((r) => r.number), [7, 8]);
});

test('githubIssueRefs deduplicates and ignores pull request links', () => {
  const refs = githubIssueRefs('https://github.com/o/r/issues/7 https://github.com/o/r/issues/7 https://github.com/o/r/pull/9');
  assert.deepEqual(refs, [{ repo: 'o/r', number: 7, url: 'https://github.com/o/r/issues/7' }]);
});

test('discussion finds recent claims and maintainer done remarks, ignoring quotes', () => {
  const issue = { body: "I'll open a PR for this.", user: { login: 'rep' }, created_at: '2026-11-02T00:00:00Z' };
  const comments = [
    { body: '> I am working on this\nsounds good', user: { login: 'q' }, created_at: '2026-11-03T00:00:00Z' },
    { body: 'yes, can be closed indeed', user: { login: 'm' }, author_association: 'COLLABORATOR', created_at: '2026-11-04T00:00:00Z' },
    { body: 'Can I work on this?', user: { login: 'old' }, created_at: '2025-01-01T00:00:00Z' },
  ];
  const d = discussion(issue, comments, NOW);
  assert.deepEqual(d.claims.map((c) => [c.by, c.recent]), [['rep', true], ['old', false]]);
  assert.deepEqual(d.done.map((x) => [x.by, x.maintainer]), [['m', true]]);
});

test('competingPrs counts open PRs that mention the issue number only', () => {
  const pr = (n, title, state = 'open') => ({ pull_request: {}, state, title, body: '', html_url: `u${n}`, user: { login: 'x' } });
  assert.deepEqual(competingPrs([pr(1, 'Fix #7'), pr(2, 'Fix #70'), pr(3, 'Fix #7', 'closed')], 7).map((p) => p.url), ['u1']);
});

test('similarIssues ranks overlapping summaries', () => {
  const found = similarIssues('Export invoices as CSV from billing page', [
    { key: 'A-2', summary: 'CSV export for invoices' }, { key: 'A-3', summary: 'Fix login button colour' }]);
  assert.deepEqual(found.map((f) => f.key), ['A-2']);
  assert.ok(searchTerms('Export invoices as CSV from billing page').length <= 4);
});

test('verdict is clear only when every signal is clean', () => {
  assert.equal(verdict({ similar: [], github: [{ url: 'g', state: 'open', assignees: [], competing: [], discussion: { claims: [], done: [] } }] }).status, 'clear');
  const v = verdict({ similar: [{ key: 'A-2' }], github: [{ url: 'g', state: 'open', assignees: [], competing: [{}], discussion: { claims: [], done: [] } }] });
  assert.equal(v.status, 'check');
  assert.equal(v.reasons.length, 2);
  assert.equal(verdict({ github: [{ url: 'g', error: 'GitHub 403' }] }).status, 'unknown');
});
