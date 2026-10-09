#!/usr/bin/env python3
"""Weighted length of a post on X: CJK and full-width characters count 2, links 23.

Usage: python3 x_weight.py <file>   (or pipe text on stdin)
Exits 1 when the text is over the 280 limit.
"""

from __future__ import annotations

import re
import sys
import unicodedata

LIMIT = 280
URL_WEIGHT = 23
URL_RE = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?", re.IGNORECASE)


def weight(text: str) -> int:
    urls = URL_RE.findall(text)
    rest = URL_RE.sub("", text)
    chars = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in rest)
    return chars + URL_WEIGHT * len(urls)


def main() -> int:
    text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    text = text.strip()
    total = weight(text)
    print(f"{total}/{LIMIT}")
    return 0 if total <= LIMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
