"""市区町村の代表点（アプリの assets に入れる一覧）を作る。年 1 回くらい手で動かす。

元：国土交通省「大字・町丁目レベル位置参照情報」（都道府県ごとの zip の CSV、cp932）。
代表点＝その市区町村の大字・町丁目の点の平均（緯度経度）。
e-Stat の調査市のうち、政令市（01100 札幌市など）・特別区部（13100）は区の点の平均にする。

  python tools/make_municipalities.py --out ../09_price_app/assets/municipalities.json [--ver 19.0b]

出典の表示：「大字・町丁目位置参照情報 国土交通省」（整備年・加工した旨も併記する）
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

URL = "https://nlftp.mlit.go.jp/isj/dls/data/{ver}/{pref:02d}000-{ver}.zip"
CITIES = "https://eru-clarissa.github.io/price-data/v1/estat/cities.json"


def load_pref(pref: int, ver: str) -> list[dict]:
    for i in range(3):
        try:
            r = requests.get(URL.format(pref=pref, ver=ver), timeout=120)
            r.raise_for_status()
            break
        except Exception:  # noqa: BLE001
            if i == 2:
                raise
            time.sleep(3)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in z.namelist() if n.endswith(".csv"))
    text = z.read(name).decode("cp932")
    return list(csv.DictReader(io.StringIO(text)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ver", default="19.0b")
    a = ap.parse_args()

    pts: dict[str, list[tuple[float, float]]] = defaultdict(list)
    names: dict[str, tuple[str, str]] = {}
    for pref in range(1, 48):
        rows = load_pref(pref, a.ver)
        for r in rows:
            code = r["市区町村コード"]
            pts[code].append((float(r["緯度"]), float(r["経度"])))
            names[code] = (r["都道府県名"], r["市区町村名"])
        print(f"{pref:02d} {len(rows)} 件", file=sys.stderr)

    def center(codes: list[str]) -> tuple[float, float] | None:
        ps = [p for c in codes for p in pts.get(c, [])]
        if not ps:
            return None
        return round(sum(p[0] for p in ps) / len(ps), 4), round(sum(p[1] for p in ps) / len(ps), 4)

    munis = []
    for code in sorted(pts):
        lat, lon = center([code])
        pref_name, name = names[code]
        munis.append({"code": code, "pref": int(code[:2]), "name": name, "lat": lat, "lon": lon})

    # 調査市の代表点（その市そのもの、なければ区の平均：コードの +1〜+29）
    survey = {}
    for c in requests.get(CITIES, timeout=60).json()["cities"]:
        code = c["code"]
        if code in pts:
            p = center([code])
        else:
            base = int(code)
            p = center([f"{base + i:05d}" for i in range(1, 30) if f"{base + i:05d}" in pts and names[f"{base + i:05d}"][1].startswith(c["name"].split("【")[0].replace("特別区部", ""))])
            if p is None and code == "13100":
                p = center([f"{13100 + i:05d}" for i in range(1, 24)])
        if p:
            survey[code] = {"lat": p[0], "lon": p[1]}
        else:
            print(f"代表点なし: {code} {c['name']}", file=sys.stderr)

    prefs = sorted({(int(c[:2]), names[c][0]) for c in names})
    doc = {
        "source": f"大字・町丁目位置参照情報 国土交通省（{a.ver}）を加工して作成（町丁目の点の平均）",
        "prefs": [{"code": p, "name": n} for p, n in prefs],
        "municipalities": munis,
        "survey_cities": survey,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"市区町村 {len(munis)}、調査市 {len(survey)} → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
