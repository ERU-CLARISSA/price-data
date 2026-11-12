"""HTTP の取得（再試行つき）。"""
from __future__ import annotations

import time

import requests

UA = "price-data-pipeline/1.0 (+https://github.com/ERU-CLARISSA/price-data)"


def get(url: str, *, params: dict | None = None, tries: int = 3, timeout: int = 60) -> bytes:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"取得に失敗: {url}: {last}")


def get_text(url: str, **kw) -> str:
    return get(url, **kw).decode("utf-8", errors="replace")
