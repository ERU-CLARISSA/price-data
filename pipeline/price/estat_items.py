"""総務省統計局 小売物価統計調査「調査品目及び基本銘柄」（年 1 回、PDF）。

e-Stat のメタ情報には単位・銘柄が入っていないので、ここから取る。
表は「符号／品目／銘柄〔細部指定〕〔調査月〕／単位／区分／掲載表」の 6 列（2025年版で確認）。
- 単位：1kg・100g・1個・1袋・1パック・1本 など（価格はこの単位あたり）
- 調査月：季節品だけ銘柄の後ろに「５月～８月」「１月～５月，１２月」のように入る（ない品目は通年）
"""
from __future__ import annotations

import io
import re
from datetime import date
from urllib.parse import urljoin

import pdfplumber

from . import fetch, wareki

PAGE = "https://www.stat.go.jp/data/kouri/doukou/{year}np.html"


def find_pdf(today: date | None = None) -> str:
    """今年 → 去年 → … の年報のページから「調査品目及び基本銘柄」の PDF を探す。"""
    y = (today or date.today()).year
    for year in range(y, y - 4, -1):
        url = PAGE.format(year=year)
        try:
            html = fetch.get(url, tries=1).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        m = re.search(r'href="([^"]*hinmoku\d{4}\.pdf)"', html)
        if m:
            return urljoin(url, m.group(1))
    raise ValueError("調査品目及び基本銘柄の PDF が見つからない")


def months_of(text: str) -> list[int] | None:
    """「１月～５月，１２月」→ [1,2,3,4,5,12]。月の指定がなければ None（通年）。"""
    t = wareki.norm(text).replace("\n", "")
    out: set[int] = set()
    for a, b in re.findall(r"(\d{1,2})月[～~〜-](\d{1,2})月", t):
        a, b = int(a), int(b)
        out.update(range(a, b + 1) if a <= b else [*range(a, 13), *range(1, b + 1)])
    t2 = re.sub(r"\d{1,2}月[～~〜-]\d{1,2}月", "", t)
    for a in re.findall(r"(?<![\d～~〜-])(\d{1,2})月(?![～~〜-])", t2):
        out.add(int(a))
    out = {m for m in out if 1 <= m <= 12}
    return sorted(out) or None


def parse_pdf(data: bytes) -> dict[str, dict]:
    """{e-Stat の品目コード(5 桁): {unit, brand, months}}"""
    out: dict[str, dict] = {}
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 4 or not row[0] or not re.fullmatch(r"\d{4}", row[0].strip()):
                        continue
                    code = "0" + row[0].strip()
                    brand_raw = row[2] or ""
                    months = months_of(brand_raw)
                    brand = wareki.norm(brand_raw).replace("\n", "")
                    brand = re.sub(r"\d{1,2}月[～~〜-]\d{1,2}月,?|\d{1,2}月,?", "", brand)
                    brand = re.sub(r"●\S*指定", "", brand).strip(" ,，")
                    out[code] = {
                        "unit": wareki.norm(row[3] or "").strip(),
                        "brand": brand,
                        "months": months,
                    }
    if len(out) < 100:
        raise ValueError(f"品目が {len(out)} しか読めない（書式が変わった？）")
    return out


def build() -> tuple[str, dict[str, dict]]:
    url = find_pdf()
    return url, parse_pdf(fetch.get(url))
