"""農水省 今週のお手頃野菜（原則毎週）。

価格の表は画像（PNG）なので読まない。ページの文（HTML）にある
「今週は ○○、△△ が大変お買い得…」「○○ も平年を下回る価格…」の品目名と更新日だけを取る。
数字は東京都中央卸売市場の卸売価格（平年比は過去5か年の旬別価格平均との比）。
"""
from __future__ import annotations

import html as htmllib
import re

from . import fetch, wareki
from .maff_outlook import OUTLOOK_ITEMS

PAGE = "https://www.maff.go.jp/j/seisan/ryutu/yasai/otokuyasai.html"

NAMES = dict(OUTLOOK_ITEMS)
NAMES.update({"トマト(大玉)": "tomato", "じゃがいも": "potato"})


def page_text(html: str) -> str:
    m = re.search(r'id="main_content".*', html, re.S)
    t = m.group(0) if m else html
    t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", wareki.norm(htmllib.unescape(t)))


def items_in(s: str) -> list[str]:
    """文に出てくる品目を、出てくる順に（長い名前から探して重なりを除く）。"""
    found: list[tuple[int, str]] = []
    for name in sorted(NAMES, key=len, reverse=True):
        i = s.find(name)
        if i >= 0 and NAMES[name] not in (k for _, k in found):
            found.append((i, NAMES[name]))
            s = s.replace(name, " " * len(name))
    return [k for _, k in sorted(found)]


def parse(html: str) -> dict:
    t = page_text(html)
    m = re.search(r"今週のお手頃野菜\s*\(([^)]*)更新\)", t)
    if not m:
        raise ValueError("更新日が見つからない（書式が変わった？）")
    d = wareki.parse(m.group(1))
    if d is None:
        raise ValueError(f"更新日が読めない: {m.group(1)}")
    best, good = [], []
    # 文は「…が大変お買い得…！」「…も平年を下回る価格…！」「…もお買い得…！」の順に並ぶ
    for sentence in re.split(r"[!！]", t[m.end():m.end() + 600]):
        if "大変お買い得" in sentence:
            best += items_in(sentence.split("大変お買い得")[0])
        elif "お買い得" in sentence or "平年を下回る" in sentence:
            good += items_in(re.split(r"お買い得|平年を下回る", sentence)[0])
    good = [g for g in good if g not in best]
    if not best and not good:
        raise ValueError("お手頃の品目が 1 つも読めない（書式が変わった？）")
    return {"date": d.isoformat(), "best": best, "good": good}


def build() -> dict:
    body = parse(fetch.get_text(PAGE))
    return {
        "schema": "maff-otoku/1",
        "basis": "東京都中央卸売市場の卸売価格の傾向（平年比は過去5か年の旬別価格平均との比率）",
        "source_url": PAGE,
        "data_updated": body["date"],
        **body,
    }


def count(doc: dict) -> int:
    return len(doc["best"]) + len(doc["good"])
