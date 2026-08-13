"""
yfinance (Yahoo!ファイナンスの非公式ライブラリ) を使った無料の日足株価取得。

- 登録・APIキー不要
- 日本株は銘柄コードに ".T" を付けて指定する (例: 7203.T = トヨタ自動車)
- 非公式ライブラリのため、Yahoo!ファイナンス側の仕様変更で動かなくなる可能性がある点に注意
- 個人利用の範囲を想定。大量・高頻度アクセスはレート制限やブロックの対象になり得るため、
  chunk_size / sleep_between で負荷を抑えている
"""
from __future__ import annotations

import time

import pandas as pd

try:
    import yfinance as yf
except ImportError as e:
    raise ImportError(
        "yfinance がインストールされていません。 pip install yfinance を実行してください。"
    ) from e


def fetch_daily_quotes(codes: list[str], period: str = "6mo", chunk_size: int = 100,
                        sleep_between: float = 1.0) -> pd.DataFrame:
    """複数銘柄の日足OHLCVをまとめて取得し、J-Quants版と同じ列構成のDataFrameに変換する。
    列: Code, Date, Open, High, Low, Close, Volume
    """
    all_frames = []
    for i in range(0, len(codes), chunk_size):
        chunk = codes[i:i + chunk_size]
        tickers = [f"{c}.T" for c in chunk]
        try:
            data = yf.download(
                tickers=tickers,
                period=period,
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
        except Exception as e:
            print(f"[WARN] チャンク {i}-{i+chunk_size} の取得に失敗: {e}")
            time.sleep(sleep_between)
            continue

        for code, ticker in zip(chunk, tickers):
            try:
                if len(tickers) == 1:
                    sub = data
                else:
                    sub = data[ticker]
            except (KeyError, TypeError):
                continue
            sub = sub.dropna(how="all")
            if sub.empty:
                continue
            sub = sub.reset_index()
            sub["Code"] = code
            sub = sub.rename(columns={"Date": "Date", "Open": "Open", "High": "High",
                                        "Low": "Low", "Close": "Close", "Volume": "Volume"})
            all_frames.append(sub[["Code", "Date", "Open", "High", "Low", "Close", "Volume"]])

        print(f"[INFO] {min(i + chunk_size, len(codes))}/{len(codes)} 銘柄 取得完了")
        time.sleep(sleep_between)

    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)
