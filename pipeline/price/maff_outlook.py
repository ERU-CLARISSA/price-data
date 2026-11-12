"""農水省 野菜の生育状況及び価格見通し（原則毎月）。

ページ（HTML）には月ごとの PDF へのリンクだけがあり、品目ごとの判定は PDF の表にある。
pdfplumber の extract_tables で「品目／主産地／今後の生育及び入荷見通し／価格見通し」の 4 列が取れる
（令和6年4月・令和8年11月で同じ形を確認）。
対象は東京都中央卸売市場に出荷される野菜の「卸売価格」の見通し（平年＝直近5か年平均）。
"""
from __future__ import annotations

import io
import re
from urllib.parse import urljoin

import pdfplumber

from . import fetch, wareki

PAGE = "https://www.maff.go.jp/j/seisan/ryutu/yasai_zyukyu/index.html"

# 見通しの言い回し → 5 段階（2=高い 1=やや高い 0=平年並み -1=やや安い -2=安い）
LEVELS = [
    ("やや平年を上回", 1), ("平年をやや上回", 1), ("平年を上回", 2),
    ("やや平年を下回", -1), ("平年をやや下回", -1), ("平年を下回", -2),
    ("平年並み", 0),
]

OUTLOOK_ITEMS = {
    "だいこん": "daikon", "にんじん": "carrot", "はくさい": "hakusai", "キャベツ": "cabbage",
    "ほうれんそう": "spinach", "ねぎ": "negi", "レタス": "lettuce", "きゅうり": "cucumber",
    "なす": "eggplant", "トマト": "tomato", "ピーマン": "green_pepper", "ばれいしょ": "potato",
    "さといも": "taro", "たまねぎ": "onion", "ブロッコリー": "broccoli",
}


def find_pdfs(html: str) -> list[tuple[tuple[int, int], str]]:
    """[(年, 月), PDF の URL] を新しい順に。"""
    out = []
    for href, label in re.findall(r'href="([^"]+\.pdf)"[^>]*>([^<]*価格見通し[^<]*)<', html):
        ym = wareki.parse_year_month(label)
        if ym:
            out.append((ym, urljoin(PAGE, href)))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def level(text: str) -> int | None:
    for word, lv in LEVELS:
        if word in text:
            return lv
    return None


def parse_judgement(cell: str) -> list[dict]:
    """「<11月前半>平年並みで推移<11月後半>平年を上回って推移」→ 前半・後半に分ける。"""
    t = wareki.norm(cell).replace("\n", "")
    parts = re.split(r"[<〈]([^>〉]*)[>〉]", t)
    if len(parts) == 1:
        lv = level(t)
        return [{"period": "month", "level": lv, "text": t.strip()}] if lv is not None else []
    out = []
    for label, body in zip(parts[1::2], parts[2::2]):
        period = "first_half" if "前半" in label else "second_half" if "後半" in label else label
        lv = level(body)
        if lv is not None:
            out.append({"period": period, "level": lv, "text": body.strip()})
    return out


def parse_pdf(data: bytes) -> dict:
    items = []
    headline = ""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text0 = pdf.pages[0].extract_text() or ""
        m = re.search(r"〇\s*(.+?)(?:\n\s*\n|東京都中央卸売市場に出荷)", text0, re.S)
        if m:
            headline = re.sub(r"\s+", "", m.group(1))
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 4:
                        continue
                    name = wareki.norm((row[0] or "").replace("\n", "")).strip()
                    key = OUTLOOK_ITEMS.get(name)
                    if key is None:
                        continue
                    judg = parse_judgement(row[3] or "")
                    if not judg:
                        continue
                    items.append({
                        "item": key,
                        "name": name,
                        "areas": wareki.norm((row[1] or "").replace("\n", "")),
                        "reason": wareki.norm((row[2] or "").replace("\n", "")),
                        "outlook": judg,
                    })
    if not items:
        raise ValueError("見通しの表から品目が 1 つも読めない（書式が変わった？）")
    return {"headline": headline, "items": items}


def build() -> dict:
    html = fetch.get_text(PAGE)
    pdfs = find_pdfs(html)
    if not pdfs:
        raise ValueError("見通しの PDF へのリンクが見つからない")
    (y, m), url = pdfs[0]
    body = parse_pdf(fetch.get(url))
    return {
        "schema": "maff-outlook/1",
        "month": f"{y:04d}-{m:02d}",
        "basis": "東京都中央卸売市場の卸売価格の見通し（平年＝直近5か年平均。平年並み＝90〜110%）",
        "levels": {"2": "平年より高い", "1": "やや高い", "0": "平年並み", "-1": "やや安い", "-2": "安い"},
        "source_url": url,
        "data_updated": f"{y:04d}-{m:02d}",
        **body,
    }


def count(doc: dict) -> int:
    return len(doc["items"])
