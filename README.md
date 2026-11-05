# bounty-scout

Check whether an open-source bounty is still worth your time **before** you start coding.

Bounty issues often look open while several pull requests are already competing for them, or while the
repository has stopped merging. `bounty-scout` reads public GitHub data and tells you, with sources:

- is the issue open and unassigned?
- does it carry a bounty label or a stated amount (USD, USDC, ERG, SigUSD, SOL, ETH)?
- how many **open pull requests already reference it** (your own PRs are excluded with `--me`)?
- has the repository **merged anything in the last 14 days**?

A lookup that fails is reported as `unknown` — never as a positive signal.

## Usage

```sh
python -m bounty_scout ergoplatform/ergo#1905 --me your-login
```

```json
{
  "verdict": "skip",
  "reasons": ["3 open competing PRs"],
  "signals": { "issue": { "bounty_labels": ["B-500 SigUSD"] }, "competition": { "open_prs": [ ... ] },
               "activity": { "merged_prs_14d": 61 } }
}
```

Exit code: `0` worth a look, `3` skip, `2` unknown. Set `GITHUB_TOKEN` for higher rate limits (optional).
When the repository endpoint is not reachable, issue data is read through the search API instead.

## Install

No dependencies beyond the Python 3.10+ standard library.

```sh
pip install .
bounty-scout owner/repo#123
```

## Tests

```sh
python -m unittest discover -s tests -t .
```

## Limits

- Competition is detected from open PRs that mention `#<issue>` in the title or body; PRs that link the
  issue only through the UI sidebar may be missed.
- A bounty label is a signal, not proof of funding. Check the sponsor's own terms before working.

## License

MIT
