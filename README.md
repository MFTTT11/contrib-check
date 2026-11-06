# contrib-check

[![tests](https://github.com/MFTTT11/contrib-check/actions/workflows/tests.yml/badge.svg)](https://github.com/MFTTT11/contrib-check/actions/workflows/tests.yml)

Check whether an open-source issue is still worth your time **before** you start contributing.

Issues — especially ones with a bounty — often look open while several pull requests are already
competing for them, or while the repository has stopped merging. `contrib-check` reads public GitHub data and tells you, with sources:

- is the issue open and unassigned?
- does it carry a bounty label or a stated amount (USD, USDC, ERG, SigUSD, SOL, ETH)?
- how many **open pull requests already reference it** (your own PRs are excluded with `--me`)?
- was a PR **already merged for it** without mentioning the issue number (title-overlap heuristic)?
- has the repository **merged anything in the last 14 days**?
- did someone **claim it recently** — the reporter announcing their own PR ("I'll open a PR"), or a
  commenter in the last 14 days ("I'm working on this", "/attempt")?
- did a **maintainer say it is already done** ("can be closed", "already fixed", "fixed in #123")?
  The same remark from a non-maintainer is reported as a note, not a reason to skip.

A lookup that fails is reported as `unknown` — never as a positive signal.

## Usage

Check one issue:

```sh
python -m contrib_check ergoplatform/ergo#1905 --me your-login
```

```json
{
  "verdict": "skip",
  "reasons": ["3 open competing PRs", "claimed in the last 14 days by someone"],
  "notes": ["older claims by another-user"],
  "signals": { "issue": { "bounty_labels": ["B-500 SigUSD"] }, "competition": { "open_prs": [ ... ] },
               "activity": { "merged_prs_14d": 61 } }
}
```

Exit code: `0` worth a look, `3` skip, `2` unknown. Set `GITHUB_TOKEN` for higher rate limits (optional).
When the repository endpoint is not reachable, issue data is read through the search API instead.

### Scan an organization or a repository

```sh
python -m contrib_check scan tscircuit --me your-login
python -m contrib_check scan ergoplatform/sigmastate-interpreter --label "Bounty - 100 SigUSD"
```

```text
tscircuit: 12 bounty issues found, 10 assessed
LOOK  https://github.com/owner/repo/issues/101  [💎 Bounty]
skip  https://github.com/owner/repo/issues/87   [$150]  2 open competing PRs; claimed in the last 14 days by someone
```

`scan` searches the `bounty` and `💎 Bounty` labels, free-text "bounty" and every `--label` you pass.
For a single repository it also reads the repository's own bounty-like labels (for example
`Bounty - 100 SigUSD` or `B-200 Erg`); for an organization, pass such labels with `--label`.
The most recently updated issues are assessed first (`--limit`, default 15) and the results are ranked:
worth a look first, then fewer reasons to skip. Add `--json` for machine-readable output.

GitHub's search API allows few requests per minute without a token, so a scan of 15 issues can take a
few minutes. Rate-limited requests wait for the reset (at most 65 s) and are retried once.

## Install

No dependencies beyond the Python 3.10+ standard library.

```sh
pip install .
contrib-check owner/repo#123
```

## Tests

```sh
python -m unittest discover -s tests -t .
```

## Limits

- A scan only sees issues that GitHub search returns for the queries above (at most 50 per query).
- Competition is detected from open PRs that mention `#<issue>` in the title or body; PRs that link the
  issue only through the UI sidebar may be missed.
- A bounty label is a signal, not proof of funding. Check the sponsor's own terms before working.
- Claims and "already done" remarks are matched with simple English phrases. Quoted lines and code
  blocks are ignored; other wordings, other languages and claims made elsewhere (chat, a bounty
  platform) are missed. If the comments cannot be read, only the issue text is checked and the
  report says so in `notes`.

## License

MIT
