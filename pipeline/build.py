"""price-data のビルド：取得 → 変換 → チェック → site/v1/ に書き出す。

  python build.py --out ../site [--previous <前回の配信の URL かフォルダ>] [--require-estat]

- 取り込み元ごとに独立。失敗した元・中身が 2 割以上減った元は、前回の配信のファイルをそのまま使う。
- 書き出すファイルにはビルド日時を入れない（中身が同じならハッシュも同じ）。
- 終了コード：0 = 全部成功、2 = 一部の失敗（前回分で補って配信してよい）、1 = 配信しない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path

import requests

from price import estat, maff_otoku, maff_outlook, maff_weekly, seasonal

SHRINK = 0.8  # 前回のこの割合より少なければ配信しない（その元は前回分を使う）


def dump(doc) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


class Previous:
    """前回の配信（URL またはフォルダ）から v1/ のファイルを読む。なければ None。"""

    def __init__(self, where: str | None):
        self.where = where

    def get(self, rel: str):
        if not self.where:
            return None
        try:
            if self.where.startswith("http"):
                r = requests.get(f"{self.where.rstrip('/')}/v1/{rel}", timeout=60)
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            p = Path(self.where) / "v1" / rel
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except Exception:  # noqa: BLE001
            return None


class Builder:
    def __init__(self, out: Path, prev: Previous):
        self.out = out
        self.prev = prev
        self.files: dict[str, bytes] = {}
        self.report: list[str] = []
        self.failed: list[str] = []

    def put(self, rel: str, doc) -> None:
        self.files[rel] = dump(doc)

    def single(self, name: str, rel: str, build, count) -> dict | None:
        """1 ファイルの取り込み元。失敗・大きく減ったら前回のファイルを使う。"""
        prev = self.prev.get(rel)
        try:
            doc = build()
            n, pn = count(doc), (count(prev) if prev else 0)
            if prev and n < pn * SHRINK:
                raise ValueError(f"件数が {pn} → {n} に減った")
            self.put(rel, doc)
            self.report.append(f"- OK {name}: {n} 件（前回 {pn}）、データ {doc.get('data_updated')}")
            return doc
        except Exception as e:  # noqa: BLE001
            self.failed.append(name)
            self.report.append(f"- **失敗** {name}: {e}")
            traceback.print_exc()
            if prev:
                self.put(rel, prev)
                self.report.append(f"  - 前回のファイルを使う（データ {prev.get('data_updated')}）")
            return prev

    def estat(self, require: bool) -> dict | None:
        """都市別小売価格。cities.json・items.json・city/<市のコード>.json。"""
        prev_items = self.prev.get("estat/items.json")
        prev_cities = self.prev.get("estat/cities.json")
        prev_data = {}
        if prev_cities:
            for c in prev_cities["cities"]:
                j = self.prev.get(f"estat/city/{c['code']}.json")
                if j:
                    prev_data[c["code"]] = {k: estat.series_from_json(v) for k, v in j["items"].items()}
        try:
            classes = estat.meta()
            cls = estat.item_class(classes)
            items = estat.wanted_items(classes[cls])
            last = max((max(s) for a in prev_data.values() for s in a.values() if s), default=None)
            since = estat.START if last is None else ((last[0], last[1] + 1) if last[1] < 12 else (last[0] + 1, 1))
            self.report.append(f"  - 品目（{cls}）{len(items)}、地域 {len(classes.get('area', []))}、{since[0]}-{since[1]:02d} から取る")
            values = estat.fetch_values([i["code"] for i in items], since, cls)
            self.report.append(f"  - API の値 {len(values)} 件")
            new = estat.parse_values(values, cls)
            data = estat.merge(prev_data, new)
            n = sum(len(s) for a in data.values() for s in a.values())
            pn = sum(len(s) for a in prev_data.values() for s in a.values())
            if n == 0:
                raise ValueError("e-Stat から価格が 1 件も取れない")
            if pn and n < pn * SHRINK:
                raise ValueError(f"件数が {pn} → {n} に減った")
            names = {c["code"]: c for c in classes.get("area", [])}
            latest = max(max(s) for a in data.values() for s in a.values() if s)
        except Exception as e:  # noqa: BLE001
            skipped = isinstance(e, estat.NoAppId) and not require
            if not skipped:
                self.failed.append("e-Stat 都市別小売価格")
            self.report.append(f"- {'スキップ' if skipped else '**失敗**'} e-Stat 都市別小売価格: {type(e).__name__}: {e}")
            if not skipped:
                self.report.append("```\n" + traceback.format_exc()[-1500:] + "```")
            if prev_cities and prev_items:
                self.put("estat/items.json", prev_items)
                self.put("estat/cities.json", prev_cities)
                for code in prev_data:
                    self.put(f"estat/city/{code}.json", self.prev.get(f"estat/city/{code}.json"))
                self.report.append("  - 前回のファイルを使う")
            return None

        self.put("estat/items.json", {
            "schema": "estat-items/1",
            "items": [{"code": i["code"], "name": i["name"], "unit": i.get("unit"), "explanation": i.get("explanation")} for i in items],
        })
        self.put("estat/cities.json", {
            "schema": "estat-cities/1",
            "cities": [{"code": a, "name": names.get(a, {}).get("name", a)} for a in sorted(data)],
        })
        for a in sorted(data):
            self.put(f"estat/city/{a}.json", {
                "schema": "estat-city/1",
                "code": a,
                "data_updated": f"{latest[0]:04d}-{latest[1]:02d}",
                "items": {i: estat.series_to_json(s) for i, s in sorted(data[a].items()) if s},
            })
        self.report.append(f"- OK e-Stat 都市別小売価格: {len(data)} 市、{n} 件（前回 {pn}）、{latest[0]}-{latest[1]:02d} まで")
        return data

    def seasonal(self, weekly: dict | None, estat_data: dict | None) -> None:
        doc = {"schema": "seasonal/1", "method": "各年の価格をその年の平均で割った指数を月ごとに平均。"
               f"値のある月が{seasonal.MIN_MONTHS}未満の年は除く。指数{seasonal.CHEAP}以下＝安くなりやすい月。",
               "maff_weekly": {}, "estat_national": {}}
        if weekly:
            for k, v in weekly["items"].items():
                r = seasonal.index(seasonal.monthly_from_points(v["points"]))
                if r:
                    doc["maff_weekly"][k] = r
        if estat_data:
            # 全国の傾向：品目ごとに、各市の指数ではなく「各月の市の平均」から作る
            acc: dict[str, dict[tuple[int, int], list[int]]] = {}
            for items in estat_data.values():
                for i, s in items.items():
                    for ym, v in s.items():
                        acc.setdefault(i, {}).setdefault(ym, []).append(v)
            for i in sorted(acc):
                r = seasonal.index({ym: sum(v) / len(v) for ym, v in acc[i].items()})
                if r:
                    doc["estat_national"][i] = r
        elif (p := self.prev.get("seasonal.json")):
            doc["estat_national"] = p.get("estat_national", {})
        self.put("seasonal.json", doc)

    def write(self) -> None:
        v1 = self.out / "v1"
        if v1.exists():
            shutil.rmtree(v1)
        index = {"schema": "price-index/1", "files": {}}
        for rel in sorted(self.files):
            p = v1 / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(self.files[rel])
            doc = json.loads(self.files[rel])
            index["files"][rel] = {
                "sha256": hashlib.sha256(self.files[rel]).hexdigest(),
                "bytes": len(self.files[rel]),
                "data_updated": doc.get("data_updated"),
            }
        (v1 / "index.json").write_bytes(dump(index))
        (self.out / "report.md").write_text("## price-data\n\n" + "\n".join(self.report) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../site")
    ap.add_argument("--previous")
    ap.add_argument("--require-estat", action="store_true", help="appId がないのも失敗にする（Actions 用）")
    a = ap.parse_args()

    b = Builder(Path(a.out), Previous(a.previous))
    try:
        weekly = b.single("農水省 食品価格動向調査（野菜）", "maff_weekly.json", maff_weekly.build, maff_weekly.count)
        b.single("農水省 野菜の生育状況及び価格見通し", "outlook.json", maff_outlook.build, maff_outlook.count)
        b.single("農水省 今週のお手頃野菜", "otoku.json", maff_otoku.build, maff_otoku.count)
        estat_data = b.estat(a.require_estat)
        b.seasonal(weekly, estat_data)
    except Exception:  # noqa: BLE001  想定外のエラーも Summary に出してから止める
        b.report.append("- **想定外のエラー（配信しない）**\n```\n" + traceback.format_exc() + "```")
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / "report.md").write_text("## price-data\n\n" + "\n".join(b.report) + "\n", encoding="utf-8")
        print("\n".join(b.report), file=sys.stderr)
        return 1

    if not b.files:
        print("配信できるファイルがない", file=sys.stderr)
        return 1
    b.write()
    print("\n".join(b.report))
    return 2 if b.failed else 0


if __name__ == "__main__":
    sys.exit(main())
