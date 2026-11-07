# Work check — Jira issue panel (Atlassian Forge)

Before someone starts on a Jira issue, **Work check** answers two questions in the issue panel:

1. **Is this already being done here?** It searches the same project for open issues whose summaries
   overlap with this one (shared significant words) and lists them with status and assignee.
2. **Is the upstream issue still free?** If the description links a GitHub issue
   (`https://github.com/owner/repo/issues/123`), it checks it the way
   [contrib-check](../../README.md) does: open or closed, assigned, open pull requests that already
   reference it, people who claimed it in the last 14 days, and maintainers saying it can be closed or
   is already fixed. Quoted lines and code blocks are ignored.

The same check is a **Rovo action** (`check-work-overlap`) used by the **Work check** Rovo agent, so
you can ask in Rovo chat: *"Is anyone already working on ENG-42?"*

The panel shows **No overlap found**, **Check before starting** (with the reasons) or **Could not
check**. A failed lookup is never reported as clear.

## Layout

| Path | What |
| --- | --- |
| `manifest.yml` | `jira:issuePanel` (UI Kit), Rovo `action` + `rovo:agent`; scope `read:jira-work`; egress only to `api.github.com` |
| `src/index.js` | Resolver: reads the issue, runs a JQL text search in the project, checks linked GitHub issues |
| `src/checks.js` | Pure logic (ADF text, link extraction, claims, done remarks, competing PRs, similarity, verdict) |
| `src/frontend/index.jsx` | UI Kit panel |
| `test/` | `npm test`: logic tests and validation of `manifest.yml` against the official `@forge/manifest` schema |

## Run it on your Jira site

1. Create a free Atlassian developer site and an API token, install the Forge CLI
   (`npm install -g @forge/cli`) and run `forge login`.
2. In this folder: `npm install`, then `forge register "Work check"` (writes your app id into
   `manifest.yml`), `forge deploy` and `forge install --product jira --site <your-site>.atlassian.net`.
3. Open any issue: the **Work check** panel appears under the issue actions.

Or use the `forge-deploy` workflow in this repository: add the repository secrets `FORGE_EMAIL`,
`FORGE_API_TOKEN` and `FORGE_APP_ID` (from the developer console), then run the workflow with your
site name.

## Limits

- GitHub requests are unauthenticated (60 per hour per IP for the REST API); a busy site may hit the
  limit and the panel then says **Could not check**.
- Similarity is word overlap on summaries, not semantic search.
