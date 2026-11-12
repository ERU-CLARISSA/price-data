"""農水省 食品価格動向調査（野菜）：週 1 回・全国平均の店頭価格（円/kg）。

取り込むのは公開ページにある Excel（価格推移データのバックアップ）だけ。PDF は読まない。
- 今の Excel：令和3年4月5日の週〜（ページの「価格推移データのバックアップ」）
- 過去の Excel：平成29年11月6日の週〜令和3年3月29日の週（過去の調査結果のページの先頭）
それより前（平成22年4月〜平成29年10月）は PDF だけなので使わない（品目が 4〜5 しかない時期が長い）。
"""
from __future__ import annotations

import io
import re
from urllib.parse import urljoin

import openpyxl

from . import fetch, wareki

PAGE = "https://www.maff.go.jp/j/zyukyu/anpo/kouri/k_yasai/h22index.html"
PAST_PAGE = "https://www.maff.go.jp/j/zyukyu/anpo/kouri/k_yasai/y_past.html"

# 表の品目名 → このデータでの品目キー（vegetables.json と共通）
ITEMS = {
    "キャベツ": "cabbage", "ねぎ": "negi", "レタス": "lettuce", "ばれいしょ": "potato",
    "たまねぎ": "onion", "きゅうり": "cucumber", "トマト": "tomato", "にんじん": "carrot",
    "はくさい": "hakusai", "だいこん": "daikon", "ほうれんそう": "spinach",
}


def find_xlsx_links(html: str, base: str) -> list[str]:
    return [urljoin(base, h) for h in re.findall(r'href="([^"]+\.xlsx)"', html)]


def parse_xlsx(data: bytes) -> dict[str, dict[str, int]]:
    """「価格」シートを読む。戻り値：{品目キー: {'YYYY-MM-DD'(週の月曜): 円/kg}}。"""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb["価格"] if "価格" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = None
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if header is None:
            names = [str(c).strip() if c else "" for c in r]
            if "キャベツ" in names:
                header = names
            continue
        label = r[0]
        if not isinstance(label, str) or "週" not in label:
            continue
        d = wareki.parse(label)
        if d is None:
            continue
        for col, name in enumerate(header):
            key = ITEMS.get(name)
            if key is None or col >= len(r):
                continue
            v = r[col]
            if isinstance(v, (int, float)) and v > 0:
                out.setdefault(key, {})[d.isoformat()] = int(round(v))
    if header is None:
        raise ValueError("Excel に見出し（キャベツ…）が見つからない（書式が変わった？）")
    return out


def build() -> dict:
    page = fetch.get_text(PAGE)
    links = find_xlsx_links(page, PAGE)
    if not links:
        raise ValueError("今の Excel へのリンクが見つからない")
    series: dict[str, dict[str, int]] = {}
    past = fetch.get_text(PAST_PAGE)
    past_links = find_xlsx_links(past, PAST_PAGE)
    # 古い順に重ね、同じ週は新しいファイルを優先
    for url in past_links[:1] + links[:1]:
        for k, s in parse_xlsx(fetch.get(url)).items():
            series.setdefault(k, {}).update(s)
    return to_json(series)


def to_json(series: dict[str, dict[str, int]]) -> dict:
    items = {}
    for k in sorted(series):
        pts = sorted(series[k].items())
        items[k] = {"points": [[d, p] for d, p in pts]}
    latest = max((pts["points"][-1][0] for pts in items.values()), default=None)
    return {
        "schema": "maff-weekly/1",
        "unit": "yen_per_kg",
        "area": "全国平均（各都道府県10店舗の量販店）",
        "note": "特売価格等を含まない消費税込み価格。調査のない週（表の「-」）は点がない。",
        "data_updated": latest,
        "items": items,
    }


def count(doc: dict) -> int:
    return sum(len(v["points"]) for v in doc["items"].values())
