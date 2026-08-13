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
