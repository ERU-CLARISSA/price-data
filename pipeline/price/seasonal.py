"""季節の傾向（月別の指数）。

インフレで最近の年ほど高く出ないよう、各年の価格をその年の平均で割った「指数」にしてから、
月ごとに年をまたいで平均する。指数が低い月＝安くなりやすい月（アプリでは「価格から見た旬」）。
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean

MIN_MONTHS = 10      # 1 年のうち値のある月がこれ未満の年は使わない（欠けの多い年）
MIN_YEARS = 3        # 使える年がこれ未満なら傾向を出さない
CHEAP = 0.95         # 指数がこれ以下の月を「安くなりやすい月」とする
MAX_CHEAP = 4        # 通年の品目の「安くなりやすい月」は、低い順にこの数まで


def monthly_from_points(points: list[tuple[str, float]]) -> dict[tuple[int, int], float]:
    """[('YYYY-MM-DD', 値)…]（週次など）→ {(年, 月): 月の平均}。"""
    acc: dict[tuple[int, int], list[float]] = defaultdict(list)
    for d, v in points:
        acc[(int(d[0:4]), int(d[5:7]))].append(v)
    return {k: mean(v) for k, v in acc.items()}


def index(monthly: dict[tuple[int, int], float], months: list[int] | None = None) -> dict | None:
    """months：季節品の調査月（例 すいか [5,6,7,8]）。その月だけで指数を作る（指数はその季節の平均との比）。"""
    season = set(months) if months else None
    need = max(2, len(season) - 1) if season else MIN_MONTHS
    by_year: dict[int, dict[int, float]] = defaultdict(dict)
    for (y, m), v in monthly.items():
        if v and v > 0 and (season is None or m in season):
            by_year[y][m] = v
    years = sorted(y for y, ms in by_year.items() if len(ms) >= need)
    # 終わっていない最後の年（例 2026 年の 1〜10 月）は、いつも最後の何か月かが欠けて傾向がずれるので使わない
    if by_year:
        last_y = max(by_year)
        last_expected = max(season) if season else 12
        if max(by_year[last_y]) < last_expected and last_y in years:
            years.remove(last_y)
    if len(years) < MIN_YEARS:
        return None
    per_month: dict[int, list[float]] = defaultdict(list)
    for y in years:
        avg = mean(by_year[y].values())
        for m, v in by_year[y].items():
            per_month[m].append(v / avg)
    idx = [round(mean(per_month[m]), 3) if per_month[m] else None for m in range(1, 13)]
    vals = [v for v in idx if v is not None]
    limit = max(1, round(len(vals) / 3)) if season else MAX_CHEAP
    low = sorted((v, m) for m, v in enumerate(idx, 1) if v is not None)
    cheap = sorted(m for v, m in low[:limit] if v <= CHEAP)
    if not cheap:  # 差が小さい品目は一番低い月だけ
        cheap = [low[0][1]]
    return {
        "index": idx,
        "cheap_months": cheap,
        "years": [years[0], years[-1]],
        "n_years": len(years),
        "amplitude": round(max(vals) - min(vals), 3),
        **({"season": sorted(season)} if season else {}),
    }
