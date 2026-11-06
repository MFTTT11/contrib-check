// Pure checks shared by the resolver; no Forge imports, so they run under `node --test`.

export const CLAIM = new RegExp(
  "\\b(?:I(?:'ll| will|'m going to| am going to)\\s+(?:open|submit|send|raise|create|file|make)\\s+" +
  "(?:a\\s+|the\\s+|my\\s+)?(?:PR|pull request|fix)" +
  "|I(?:'m| am)\\s+(?:currently\\s+|already\\s+)?working on (?:this|it|a fix)" +
  "|(?:can|could|may) I (?:work on|take|pick up) (?:this|it)" +
  "|I(?:'d| would) like to (?:work on|take|pick up) (?:this|it)" +
  "|assign (?:this |it )?to me)|(?<!\\w)/attempt\\b", 'i');

export const DONE = new RegExp(
  "\\b(?:(?:can|should|could) be closed" +
  "|already (?:done|fixed|implemented|resolved|merged|has the changes)" +
  "|(?:fixed|resolved|addressed|implemented) (?:in|by|via) (?:#\\d+|https://github\\.com/\\S+/pull/\\d+)" +
  "|(?:is|looks|seems) (?:obsolete|outdated|no longer (?:relevant|needed|valid)))", 'i');

const MAINTAINER = new Set(['OWNER', 'MEMBER', 'COLLABORATOR']);
const STOP = new Set('a an the and or of to in on for with from by is are be not when only can into as at it its this that'.split(' '));
const DAY = 24 * 3600 * 1000;

/** Plain text of an Atlassian Document Format node (or a plain string). */
export function adfText(node) {
  if (node == null) return '';
  if (typeof node === 'string') return node;
  if (Array.isArray(node)) return node.map(adfText).join(' ');
  const own = typeof node.text === 'string' ? node.text : '';
  const href = node.marks?.find?.((m) => m?.type === 'link')?.attrs?.href || node.attrs?.url || '';
  return [own, href, adfText(node.content)].filter(Boolean).join(' ');
}

/** GitHub issue references in free text: [{repo, number, url}] (deduplicated). */
export function githubIssueRefs(text) {
  const out = new Map();
  for (const m of String(text).matchAll(/https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/issues\/(\d+)/g)) {
    const url = `https://github.com/${m[1]}/issues/${m[2]}`;
    out.set(url, { repo: m[1], number: Number(m[2]), url });
  }
  return [...out.values()];
}

/** Body text without fenced code blocks and quoted lines. */
export function ownWords(body) {
  return String(body || '').replace(/```[\s\S]*?```/g, ' ')
    .split('\n').filter((l) => !l.trimStart().startsWith('>')).join('\n');
}

/** Claims and "already done" remarks from an issue and its comments. */
export function discussion(issue, comments, now = new Date(), recentDays = 14) {
  const cutoff = now.getTime() - recentDays * DAY;
  const claims = [];
  const done = [];
  const entries = [['issue', issue], ...(comments || []).map((c) => ['comment', c])];
  for (const [where, item] of entries) {
    if (!item || typeof item !== 'object') continue;
    const by = item.user?.login || '';
    const text = ownWords(item.body);
    const at = Date.parse(item.created_at || '');
    const claim = text.match(CLAIM);
    if (claim) claims.push({ by, where, quote: claim[0], recent: Number.isFinite(at) && at >= cutoff });
    const remark = where === 'comment' ? text.match(DONE) : null;
    if (remark) done.push({ by, quote: remark[0], maintainer: MAINTAINER.has(item.author_association || '') });
  }
  return { claims, done };
}

/** Open PRs (from a search result) that mention #number. */
export function competingPrs(items, number) {
  const ref = new RegExp(`(?<![\\w/])#${number}\\b`);
  return (items || []).filter((it) => it?.pull_request && it.state === 'open'
    && ref.test(`${it.title || ''}\n${it.body || ''}`)).map((it) => ({ url: it.html_url, by: it.user?.login || '' }));
}

export function words(text) {
  return new Set((String(text).toLowerCase().match(/[a-z0-9_]{3,}/g) || []).filter((w) => !STOP.has(w)));
}

/** Other open Jira issues whose summaries share most significant words with this one. */
export function similarIssues(summary, candidates, minOverlap = 2, minRatio = 0.5) {
  const want = words(summary);
  if (!want.size) return [];
  return (candidates || []).map((c) => {
    const shared = [...want].filter((w) => words(c.summary).has(w));
    return { ...c, shared, ratio: shared.length / want.size };
  }).filter((c) => c.shared.length >= minOverlap && c.ratio >= minRatio)
    .sort((a, b) => b.ratio - a.ratio).slice(0, 5);
}

/** Search words for a JQL text query (longest first, at most four). */
export function searchTerms(summary) {
  return [...words(summary)].sort((a, b) => b.length - a.length).slice(0, 4);
}

/** Overall verdict from the collected signals. Unknown lookups never count as "clear". */
export function verdict({ similar = [], github = [] }) {
  const reasons = [];
  if (similar.length) reasons.push(`${similar.length} similar open issue(s) in this project`);
  for (const g of github) {
    if (g.error) { reasons.push(`${g.url}: could not be checked (${g.error})`); continue; }
    if (g.state && g.state !== 'open') reasons.push(`${g.url} is ${g.state}`);
    if (g.assignees?.length) reasons.push(`${g.url} is assigned to ${g.assignees.join(', ')}`);
    if (g.competing?.length) reasons.push(`${g.url}: ${g.competing.length} open PR(s) already reference it`);
    if (g.discussion?.done.some((d) => d.maintainer)) reasons.push(`${g.url}: a maintainer said it is already done`);
    const recent = [...new Set((g.discussion?.claims || []).filter((c) => c.recent).map((c) => c.by))];
    if (recent.length) reasons.push(`${g.url}: claimed in the last 14 days by ${recent.join(', ')}`);
  }
  const unknown = github.some((g) => g.error);
  return { status: reasons.length ? (unknown && reasons.every((r) => r.includes('could not be checked')) ? 'unknown' : 'check') : 'clear', reasons };
}
