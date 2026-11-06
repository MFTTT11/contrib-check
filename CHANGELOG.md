# Changelog

## Unreleased

- Composite GitHub Action (`action.yml`): runs `scan` and writes the ranked table to the job summary.
- Weekly example workflow (`radar.yml`).

## 0.4.0 — 2026-11-06

- New `scan` command: find the open bounty issues of an organization or repository and rank them.
  Searches the `bounty` and `💎 Bounty` labels, free-text "bounty" and any `--label` you pass; for a
  single repository, its bounty-like labels are discovered automatically. Each candidate goes
  through the same checks as a single-issue assessment.
- Rate-limited GitHub requests wait for `Retry-After` / `X-RateLimit-Reset` (at most 65 s) and are
  retried once.
- Repository activity is looked up once per repository during a scan.

## 0.3.0 — 2026-11-06

- Discussion signals: a reporter announcing their own PR, recent claims in comments
  ("I'm working on this", "/attempt"), and maintainers saying an issue "can be closed" or is
  "already fixed". Non-maintainer remarks and older claims are reported as `notes`.

## 0.2.0 — 2026-11-06

- Flag issues that a recently merged PR already fixed (title-overlap heuristic).

## 0.1.0 — 2026-11-05

- First release (as bounty-scout, renamed to contrib-check): open/assigned state, bounty labels and
  amounts, competing open PRs, repository merge activity.
