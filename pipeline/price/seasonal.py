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


def monthly_from_points(points: list[tuple[str, float]]) -> dict[tuple[int, int], float]:
    """[('YYYY-MM-DD', 値)…]（週次など）→ {(年, 月): 月の平均}。"""
    acc: dict[tuple[int, int], list[float]] = defaultdict(list)
    for d, v in points:
        acc[(int(d[0:4]), int(d[5:7]))].append(v)
    return {k: mean(v) for k, v in acc.items()}


def index(monthly: dict[tuple[int, int], float]) -> dict | None:
    by_year: dict[int, dict[int, float]] = defaultdict(dict)
    for (y, m), v in monthly.items():
        if v and v > 0:
            by_year[y][m] = v
    years = sorted(y for y, ms in by_year.items() if len(ms) >= MIN_MONTHS)
    if len(years) < MIN_YEARS:
        return None
    per_month: dict[int, list[float]] = defaultdict(list)
    for y in years:
        avg = mean(by_year[y].values())
        for m, v in by_year[y].items():
            per_month[m].append(v / avg)
    idx = [round(mean(per_month[m]), 3) if per_month[m] else None for m in range(1, 13)]
    vals = [v for v in idx if v is not None]
    cheap = [m for m, v in enumerate(idx, 1) if v is not None and v <= CHEAP]
    if not cheap:  # 差が小さい品目は一番低い月だけ
        cheap = [idx.index(min(vals)) + 1]
    return {
        "index": idx,
        "cheap_months": cheap,
        "years": [years[0], years[-1]],
        "n_years": len(years),
        "amplitude": round(max(vals) - min(vals), 3),
    }
