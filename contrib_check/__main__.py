"""CLI.

  contrib-check owner/repo#123 [--me LOGIN]          assess one issue
  contrib-check scan ORG | OWNER/REPO [--label NAME]  find and rank open bounty issues
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from .check import assess
from .scan import scan, table


def _scan(argv):
    p = argparse.ArgumentParser(prog='contrib-check scan', description='Find and rank open bounty issues.')
    p.add_argument('target', help='organization (e.g. tscircuit) or owner/repo')
    p.add_argument('--label', action='append', default=[], help='extra bounty label to search for (repeatable)')
    p.add_argument('--limit', type=int, default=15, help='assess at most this many issues (default 15)')
    p.add_argument('--me', help='your GitHub login (your own PRs and claims are not counted)')
    p.add_argument('--max-competing', type=int, default=1)
    p.add_argument('--json', action='store_true', help='print JSON instead of a table')
    a = p.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?', a.target):
        p.error('target must be an organization or owner/repo')
    result = scan(a.target, me=a.me, labels=a.label, limit=a.limit, max_competing=a.max_competing)
    print(json.dumps(result, indent=2, ensure_ascii=False) if a.json else table(result))
    return 0 if not result['errors'] or result['results'] else 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == 'scan':
        return _scan(argv[1:])
    p = argparse.ArgumentParser(prog='contrib-check', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('target', help='owner/repo#issue')
    p.add_argument('--me', help='your GitHub login (your own PRs are not counted as competition)')
    p.add_argument('--max-competing', type=int, default=1)
    a = p.parse_args(argv)
    m = re.fullmatch(r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)', a.target)
    if not m:
        p.error('target must look like owner/repo#123')
    report = assess(m.group(1), int(m.group(2)), me=a.me, max_competing=a.max_competing)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return {'worth_a_look': 0, 'skip': 3}.get(report['verdict'], 2)


if __name__ == '__main__':
    sys.exit(main())
