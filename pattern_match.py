"""
「今の値動きが、過去のどの局面に似ているか」を簡易的に探すモヸュール。

やり方(かなりシンプルな近似手法です):
- 直近 WINDOW 日分の終値を「前日比%の並び」に変換したものを「現在のパターン」とする
  (価格そのものではなく変化率で比べることで、値がさ(株価水準)の違いを無視して
  値動きの「形」だけを比較できるようにしている)
- 過去の期間を1日ずつずらしながら同じ長さの窓を切り出し、現在のパターンとの相関係数を
  類似度(-1〜1、1に近いほど形が似ている)として計算する
- 類似度が高い順に、なるべく時期が重ならないように上位数件を採用する
- 採用した過去の各局面について、そこから FORWARD_DAYS 日後までの騰落率を計算し、
  勝率(上昇した割合)・平均騰落率をまとめて返す

注意:
- あくまで過去の値動きの形の類似性に基づく参考情報であり、将来の値動きを保証するものではない
- 上場して間もない銘柄など、過去データが少ない場合は結果を返さない(available: False)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = 20          # 「現在のパターン」として使う直近の日数
FORWARD_DAYS = 5      # 類似局面の「その後」を見る日数
MIN_HISTORY = WINDOW * 3  # これより過去データが短い銘柄は対象外
GAP_DAYS = 5           # 直近ウィンドウに近すぎる(実質同じ動きの)期間は候補から除外する
TOP_N = 3              # 採用する類似局面の最大件数
MIN_SIMILARITY = 0.5   # これ未満の類似度は「似ている」とみなさない
DEDUP_GAP = WINDOW // 2  # 採用済みの局面と時期が近すぎる候補は除外する(同じ局面の重複採用を防ぐ)


def _pct_change_seq(close: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.diff(close) / close[:-1]


def find_similar_patterns(close: pd.Series, dates: list[str]) -> dict:
    """終値の時系列(古い→新しい順、closeとdatesは同じ長さ・同じ並び順)から、
    直近パターンと似た過去局面を探し、その後の値動きを集計して返す。"""
    close = close.dropna()
    n = len(close)
    if n < WINDOW + MIN_HISTORY:
        return {"available": False, "reason": "insufficient_history"}

    close_arr = close.to_numpy(dtype=float)
    pct_all = _pct_change_seq(close_arr)  # 長さ n-1。pct_all[i] は close[i]→close[i+1] の変化率

    current = pct_all[-WINDOW:]
    current_std = current.std()
    if current_std == 0 or np.isnan(current_std):
        return {"available": False, "reason": "flat_recent"}

    current_start = len(pct_all) - WINDOW
    search_end = current_start - GAP_DAYS

    candidates = []
    for start in range(0, max(search_end, 0)):
        window = pct_all[start:start + WINDOW]
        if window.std() == 0 or np.isnan(window.std()):
            continue
        corr = np.corrcoef(current, window)[0, 1]
        if np.isnan(corr):
            continue
        end_close_idx = start + WINDOW  # このパターンが終わった時点のcloseのインデックス
        future_idx = end_close_idx + FORWARD_DAYS
        if future_idx >= n:
            continue
        base_price = close.iloc[end_close_idx]
        if not base_price:
            continue
        future_price = close.iloc[future_idx]
        forward_return = (future_price - base_price) / base_price * 100
        candidates.append({
            "similarity": float(corr),
            "end_index": end_close_idx,
            "forward_return_pct": float(forward_return),
        })

    if not candidates:
        return {"available": False, "reason": "no_candidates"}

    candidates.sort(key=lambda c: -c["similarity"])

    picked = []
    for c in candidates:
        if c["similarity"] < MIN_SIMILARITY:
            break
        if any(abs(c["end_index"] - p["end_index"]) < DEDUP_GAP for p in picked):
            continue
        picked.append(c)
        if len(picked) >= TOP_N:
            break

    if not picked:
        return {
            "available": False,
            "reason": "no_similar_enough",
            "best_similarity_pct": round(candidates[0]["similarity"] * 100, 1),
        }

    wins = sum(1 for c in picked if c["forward_return_pct"] > 0)
    avg_similarity = sum(c["similarity"] for c in picked) / len(picked)
    avg_forward_return = sum(c["forward_return_pct"] for c in picked) / len(picked)

    cases = []
    for c in picked:
        idx = c["end_index"]
        cases.append({
            "date": dates[idx] if 0 <= idx < len(dates) else None,
            "similarity_pct": round(c["similarity"] * 100, 1),
            "forward_return_pct": round(c["forward_return_pct"], 2),
        })

    return {
        "available": True,
        "window_days": WINDOW,
        "forward_days": FORWARD_DAYS,
        "sample_count": len(picked),
        "avg_similarity_pct": round(avg_similarity * 100, 1),
        "win_rate_pct": round(wins / len(picked) * 100, 1),
        "avg_forward_return_pct": round(avg_forward_return, 2),
        "cases": cases,
    }
