"""
テクニカル指標の計算ロジック。
入力は 1銘柄分の日次OHLCVを日付昇順に並べた pandas.DataFrame
(列: Date, Open, High, Low, Close, Volume)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    out = out.where(avg_loss != 0, 100.0)  # 平均下落がゼロなら100(極端な買われすぎ)
    return out


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3):
    lowest_low = low.rolling(window=k_period, min_periods=k_period).min()
    highest_high = high.rolling(window=k_period, min_periods=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(window=d_period, min_periods=d_period).mean()
    return k, d


def bollinger_bands(close: pd.Series, window: int = 20, sigma: float = 3.0):
    mid = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std()
    upper = mid + sigma * std
    lower = mid - sigma * std
    return upper, mid, lower


def golden_dead_cross(close: pd.Series, short_window: int, long_window: int) -> pd.Series:
    """直近1本で 'golden' / 'dead' / None を返す(直近足でクロスが発生したか)。"""
    short_ma = sma(close, short_window)
    long_ma = sma(close, long_window)
    diff = short_ma - long_ma
    if len(diff) < 2 or pd.isna(diff.iloc[-1]) or pd.isna(diff.iloc[-2]):
        return None
    prev, cur = diff.iloc[-2], diff.iloc[-1]
    if prev <= 0 and cur > 0:
        return "golden"
    if prev >= 0 and cur < 0:
        return "dead"
    return None


def volume_surge(volume: pd.Series, lookback_days: int, surge_multiple: float) -> bool:
    if len(volume) < lookback_days + 1:
        return False
    avg = volume.iloc[-(lookback_days + 1):-1].mean()
    if avg == 0 or pd.isna(avg):
        return False
    return volume.iloc[-1] >= avg * surge_multiple


def price_breakout(high: pd.Series, low: pd.Series, close: pd.Series, lookback_days: int, breakout_type: str = "both"):
    """直近終値が過去lookback_days(当日を除く)の高値・安値を更新したか判定する。"""
    if len(close) < lookback_days + 1:
        return None
    past_high = high.iloc[-(lookback_days + 1):-1].max()
    past_low = low.iloc[-(lookback_days + 1):-1].min()
    cur_close = close.iloc[-1]
    if breakout_type in ("high", "both") and cur_close > past_high:
        return "high"
    if breakout_type in ("low", "both") and cur_close < past_low:
        return "low"
    return None


# ------------------------------------------------------------
# 「多くの投資家が節目として意識しやすい価格帯」に接近しているかどうかの判定。
# こうした水準の近くでは売買が入りやすく、反発・反落のきっかけになりやすいとされる
# (あくまで経験則であり、必ずそうなることを保証するものではない)。
# ------------------------------------------------------------

def _round_level_step(price: float) -> float:
    """株価水準に応じた「キリの良い」価格の刻み幅を返す(例: 800円台なら100円刻み)。"""
    if price < 500:
        return 50
    if price < 1000:
        return 100
    if price < 3000:
        return 500
    if price < 10000:
        return 1000
    if price < 30000:
        return 5000
    return 10000


def nearby_round_number(close: pd.Series, threshold_pct: float = 1.5):
    """直近終値が「キリの良い株価」(例: 1,000円、5,000円)に近いか判定する。
    戻り値: {"level": 節目の株価, "distance_pct": 乖離率} または None"""
    if close.empty:
        return None
    price = float(close.iloc[-1])
    if price <= 0 or pd.isna(price):
        return None
    step = _round_level_step(price)
    nearest = round(price / step) * step
    if nearest <= 0:
        return None
    dist_pct = abs(price - nearest) / price * 100
    if dist_pct <= threshold_pct:
        return {"level": nearest, "distance_pct": round(dist_pct, 2)}
    return None


def nearby_recent_extreme(high: pd.Series, low: pd.Series, close: pd.Series,
                           lookback_days: int = 60, threshold_pct: float = 2.0):
    """直近終値が、過去lookback_days(当日を除く)の高値・安値(サポート/レジスタンスとして
    意識されやすい水準)に近いか判定する。
    戻り値: [{"type": "high"|"low", "level": 価格, "distance_pct": 乖離率}, ...] または None"""
    if len(close) < lookback_days + 1:
        return None
    past_high = high.iloc[-(lookback_days + 1):-1].max()
    past_low = low.iloc[-(lookback_days + 1):-1].min()
    cur = float(close.iloc[-1])
    if cur <= 0 or pd.isna(cur):
        return None
    results = []
    if past_high and not pd.isna(past_high):
        dist = abs(cur - past_high) / cur * 100
        if dist <= threshold_pct:
            results.append({"type": "high", "level": round(float(past_high), 2), "distance_pct": round(dist, 2)})
    if past_low and not pd.isna(past_low):
        dist = abs(cur - past_low) / cur * 100
        if dist <= threshold_pct:
            results.append({"type": "low", "level": round(float(past_low), 2), "distance_pct": round(dist, 2)})
    return results or None


def nearby_moving_average(close: pd.Series, windows=(25, 75, 200), threshold_pct: float = 1.5):
    """直近終値が、多くの投資家が節目として意識しやすい主要な移動平均線
    (25日線・75日線・200日線など)に近いか判定する。
    戻り値: [{"window": 日数, "level": 移動平均値, "distance_pct": 乖離率}, ...] または None"""
    if close.empty:
        return None
    cur = float(close.iloc[-1])
    if cur <= 0 or pd.isna(cur):
        return None
    results = []
    for w in windows:
        if len(close) < w:
            continue
        ma = close.rolling(window=w, min_periods=w).mean().iloc[-1]
        if pd.isna(ma) or ma <= 0:
            continue
        dist_pct = abs(cur - ma) / cur * 100
        if dist_pct <= threshold_pct:
            results.append({"window": int(w), "level": round(float(ma), 2), "distance_pct": round(dist_pct, 2)})
    return results or None
