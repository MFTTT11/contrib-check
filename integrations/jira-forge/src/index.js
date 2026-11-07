import Resolver from '@forge/resolver';
import api, { route, fetch } from '@forge/api';
import { adfText, githubIssueRefs, discussion, competingPrs, similarIssues, searchTerms, verdict, issueKey } from './checks.js';

const GITHUB = 'https://api.github.com';
const resolver = new Resolver();

async function github(path) {
  const res = await fetch(GITHUB + path, { headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'work-check-forge' } });
  if (!res.ok) throw new Error(`GitHub ${res.status}`);
  return res.json();
}

async function checkGithubIssue(ref) {
  try {
    const [issue, comments, prs] = await Promise.all([
      github(`/repos/${ref.repo}/issues/${ref.number}`),
      github(`/repos/${ref.repo}/issues/${ref.number}/comments?per_page=100`),
      github(`/search/issues?q=${encodeURIComponent(`repo:${ref.repo} is:pr is:open ${ref.number}`)}&per_page=50`),
    ]);
    return {
      url: ref.url, state: issue.state, assignees: (issue.assignees || []).map((a) => a.login),
      competing: competingPrs(prs.items, ref.number), discussion: discussion(issue, comments),
    };
  } catch (err) {
    return { url: ref.url, error: err.message };
  }
}

async function similarInProject(issueKey, projectKey, summary) {
  const terms = searchTerms(summary);
  if (!terms.length) return [];
  const text = terms.join(' ').replace(/["\\]/g, '');
  const jql = `project = "${projectKey}" AND statusCategory != Done AND key != ${issueKey} AND text ~ "${text}" ORDER BY updated DESC`;
  const res = await api.asApp().requestJira(route`/rest/api/3/search/jql`, {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ jql, maxResults: 20, fields: ['summary', 'status', 'assignee'] }),
  });
  if (!res.ok) return [];
  const data = await res.json();
  const candidates = (data.issues || []).map((i) => ({
    key: i.key, summary: i.fields?.summary || '', status: i.fields?.status?.name || '', assignee: i.fields?.assignee?.displayName || null,
  }));
  return similarIssues(summary, candidates);
}

export async function buildReport(key) {
  const res = await api.asApp().requestJira(route`/rest/api/3/issue/${key}?fields=summary,description,project`, { headers: { Accept: 'application/json' } });
  if (!res.ok) return { status: 'unknown', reasons: [`Jira returned ${res.status}`], similar: [], github: [] };
  const issue = await res.json();
  const summary = issue.fields?.summary || '';
  const refs = githubIssueRefs(adfText(issue.fields?.description)).slice(0, 3);
  const [similar, gh] = await Promise.all([
    similarInProject(key, issue.fields?.project?.key, summary).catch(() => []),
    Promise.all(refs.map(checkGithubIssue)),
  ]);
  return { ...verdict({ similar, github: gh }), similar, github: gh };
}

resolver.define('getReport', async ({ context }) => buildReport(context.extension.issue.key));

export const handler = resolver.getDefinitions();

/** Rovo action: same report for an issue key given by an agent. */
export async function actionHandler(payload) {
  const key = issueKey(payload?.issueKey);
  if (!key) return { status: 'unknown', reasons: [`"${payload?.issueKey ?? ''}" is not a Jira issue key`], similar: [], github: [] };
  return buildReport(key);
}
