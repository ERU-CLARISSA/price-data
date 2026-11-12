"""総務省 小売物価統計調査「主要品目の都市別小売価格」（e-Stat API 3.0、月次）。

表 ID 0003421913：都道府県庁所在市及び人口15万以上の市（2000年1月～）。
- 品目（cat02。cat01 は「価格」1 つだけ）：5 桁（例 01401 キャベツ）。全 872、うち食料（01xxx）256。調査終了の品目は名前に【…調査終了】。
- 地域（area）：市区町村コード 5 桁（例 13100 特別区部）。95（うち掲載終了・旧市を含む）。
- 時間（time）：10 桁（例 2026000909 = 2026年9月）。
appId は環境変数 ESTAT_APP_ID（GitHub の Secrets）。コードやアプリには書かない。

取り方：前回の配信ファイルがあれば、その最後の月より後だけを取る（毎月の取り込みは小さい）。
"""
from __future__ import annotations

import json
import os
import re

from . import fetch

API = "https://api.e-stat.go.jp/rest/3.0/app/json"
STATS_ID = "0003421913"
START = (2000, 1)


class NoAppId(RuntimeError):
    pass


def app_id() -> str:
    v = os.environ.get("ESTAT_APP_ID", "").strip()
    if not v:
        raise NoAppId("ESTAT_APP_ID がない（GitHub の Secrets に登録する）")
    return v


def call(name: str, **params) -> dict:
    params = {"appId": app_id(), "lang": "J", **params}
    doc = json.loads(fetch.get(f"{API}/{name}", params=params, timeout=180))
    root = next(iter(doc.values()))
    status = int(root["RESULT"]["STATUS"])
    if status not in (0, 1):  # 1 = 該当データなし
        raise RuntimeError(f"e-Stat {name}: {root['RESULT'].get('ERROR_MSG')}")
    return root


def as_list(x):
    return x if isinstance(x, list) else [x] if x is not None else []


def meta() -> dict:
    root = call("getMetaInfo", statsDataId=STATS_ID)
    classes = {}
    for obj in as_list(root["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]):
        classes[obj["@id"]] = [
            {"code": c["@code"], "name": c["@name"], "unit": c.get("@unit"), "explanation": c.get("@explanation")}
            for c in as_list(obj.get("CLASS"))
        ]
    return classes


def time_code(y: int, m: int) -> str:
    return f"{y:04d}00{m:02d}{m:02d}"


def parse_time(code: str) -> tuple[int, int]:
    return int(code[0:4]), int(code[6:8])


def item_class(classes: dict) -> str:
    """品目の分類の id（cat01・cat02…のうち一番数が多いもの。この表では cat02）。"""
    cats = [k for k in classes if k.startswith("cat")]
    if not cats:
        raise ValueError(f"品目の分類が見つからない: {list(classes)}")
    return max(cats, key=lambda k: len(classes[k]))


def parse_values(values: list[dict], cls: str = "cat02") -> dict[str, dict[str, dict[tuple[int, int], int]]]:
    """VALUE の並び → {地域: {品目: {(年, 月): 円}}}。「-」「…」「***」などは捨てる。"""
    out: dict = {}
    for v in values:
        raw = str(v.get("$", "")).replace(",", "")
        if not re.fullmatch(r"\d+(\.\d+)?", raw):
            continue
        out.setdefault(v["@area"], {}).setdefault(v[f"@{cls}"], {})[parse_time(v["@time"])] = int(round(float(raw)))
    return out


def fetch_values(items: list[str], since: tuple[int, int], cls: str = "cat02") -> list[dict]:
    """品目を 100 ずつに分け、NEXT_KEY でページを送りながら全部取る。"""
    values = []
    for i in range(0, len(items), 100):
        start = 1
        while True:
            root = call(
                "getStatsData", statsDataId=STATS_ID, **{f"cd{cls.capitalize()}": ",".join(items[i:i + 100])},
                cdTimeFrom=time_code(*since), startPosition=start, limit=100000,
                metaGetFlg="N", cntGetFlg="N", sectionHeaderFlg="2",
            )
            data = root.get("STATISTICAL_DATA", {})
            values += as_list(data.get("DATA_INF", {}).get("VALUE"))
            print(f"e-Stat: 品目 {i + 1}〜{min(i + 100, len(items))}/{len(items)}、{start} 件目から、累計 {len(values)} 件", flush=True)
            nxt = data.get("RESULT_INF", {}).get("NEXT_KEY")
            if not nxt:
                break
            start = int(nxt)
    return values


def wanted_items(cat01: list[dict]) -> list[dict]:
    """食料（01xxx）で、調査が続いている品目。"""
    return [c for c in cat01 if c["code"].startswith("01") and "調査終了" not in c["name"]]


def merge(prev: dict | None, new: dict) -> dict:
    """前回の配信（city ファイル群の中身）に新しい月を重ねる。"""
    out = {a: {i: dict(s) for i, s in items.items()} for a, items in (prev or {}).items()}
    for a, items in new.items():
        for i, s in items.items():
            out.setdefault(a, {}).setdefault(i, {}).update(s)
    return out


def series_to_json(s: dict[tuple[int, int], int]) -> dict:
    """{(年, 月): 円} → {"start": "YYYY-MM", "values": [円 or null…]}（月の抜けは null）。"""
    keys = sorted(s)
    (y, m), (y2, m2) = keys[0], keys[-1]
    vals = []
    while (y, m) <= (y2, m2):
        vals.append(s.get((y, m)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return {"start": f"{keys[0][0]:04d}-{keys[0][1]:02d}", "values": vals}


def series_from_json(j: dict) -> dict[tuple[int, int], int]:
    y, m = int(j["start"][0:4]), int(j["start"][5:7])
    out = {}
    for v in j["values"]:
        if v is not None:
            out[(y, m)] = v
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
