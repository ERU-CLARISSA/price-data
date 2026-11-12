"""和暦の日付（「令和8年11月2日の週」など）を西暦に直す。"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

ERA = {"明治": 1867, "大正": 1911, "昭和": 1925, "平成": 1988, "令和": 2018}

_RE = re.compile(r"(明治|大正|昭和|平成|令和)\s*(元|\d+)\s*年\s*(\d+)\s*月(?:\s*(\d+)\s*日)?")


def norm(s: str) -> str:
    """全角数字・全角空白などを半角にそろえる。"""
    return unicodedata.normalize("NFKC", s)


def parse(s: str) -> date | None:
    """最初に出てくる和暦の年月日を返す（日がなければ 1 日）。"""
    m = _RE.search(norm(s))
    if not m:
        return None
    era, y, mo, d = m.groups()
    year = ERA[era] + (1 if y == "元" else int(y))
    return date(year, int(mo), int(d) if d else 1)


def parse_year_month(s: str) -> tuple[int, int] | None:
    d = parse(s)
    return (d.year, d.month) if d else None
