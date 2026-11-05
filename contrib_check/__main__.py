"""CLI: python -m contrib_check owner/repo#123 [--me LOGIN]"""
from __future__ import annotations

import argparse
import json
import re
import sys

from .check import assess


def main(argv=None):
    p = argparse.ArgumentParser(prog='contrib-check', description=__doc__)
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
