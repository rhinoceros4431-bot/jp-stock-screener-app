"""
yfinance (Yahoo!ファイナンスの非公式ライブラリ) を使った無料の日足株価取得。

- 登録・APIキー不要
- 日本株は銘柄コードに ".T" を付けて指定する (例: 7203.T = トヨタ自動車)
- 非公式ライブラリのため、Yahoo!ファイナンス側の仕様変更で動かなくなる可能性がある点に注意
- 個人利用の範囲を想定。大量・高頻度アクセスはレート制限やブロックの対象になり得るため、
  chunk_size / sleep_between で負荷を抑えている
"""
from __future__ import annotations

import ctypes
import gc
import time

import pandas as pd

try:
    import yfinance as yf
except ImportError as e:
    raise ImportError(
        "yfinance がインストールされていません。 pip install yfinance を実行してください。"
    ) from e

# gc.collect() だけでは、pandas/numpy が確保したメモリ領域がOSに返却されず
# プロセスのRSS(実メモリ使用量)が下がらないことがある(glibcのmalloc実装の都合で、
# 一度確保した領域を再利用のために保持し続けるため)。そのため、チャンク処理後に
# malloc_trim(0) を呼んで未使用領域を明示的にOSへ返却する。
# (Renderの無料枠は512MBしかなく、chunk_sizeを縮小しただけでは実行終盤にじわじわ
#  メモリ使用量が積み上がってOOM Killされる不具合が実際に起きたための対策)
try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:
    _libc = None


def _release_memory():
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass


def fetch_daily_quotes_chunks(codes: list[str], period: str = "6mo", chunk_size: int = 30,
                               sleep_between: float = 0.7):
    """複数銘柄の日足OHLCVをチャンク単位で取得し、チャンクごとに (chunk_codes, DataFrame) を
    yield するジェネレータ。呼び出し側がチャンク完了ごとに途中経過を保存できるようにするため、
    全件まとめて返す fetch_daily_quotes ではなくこちらを主に使う。
    DataFrameの列: Code, Date, Open, High, Low, Close, Volume

    chunk_size は既定150から30に縮小している。Renderの無料枠はメモリが512MBしかなく、
    150銘柄まとめてスレッド並列ダウンロードすると一時的なメモリ使用量がそれを超えて
    プロセスがOOM Killされることが実際に発生したため(結果が消える不具合の真因だった)。
    さらに、chunk_sizeを縮小した後も実行終盤(3000銘柄超)でメモリが徐々に積み上がって
    OOM Killされることが確認できたため、スレッド並列を無効化(threads=False)して
    チャンクあたりのピークメモリをさらに抑え、チャンクごとに malloc_trim でメモリを
    OSへ返却するようにしている。
    """
    for i in range(0, len(codes), chunk_size):
        chunk = codes[i:i + chunk_size]
        tickers = [f"{c}.T" for c in chunk]
        frames = []
        try:
            data = yf.download(
                tickers=tickers,
                period=period,
                interval="1d",
                group_by="ticker",
                threads=False,
                progress=False,
                auto_adjust=False,
                timeout=20,
            )
        except Exception as e:
            print(f"[WARN] チャンク {i}-{i+chunk_size} の取得に失敗: {e}")
            time.sleep(sleep_between)
            yield chunk, pd.DataFrame()
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
            frames.append(sub[["Code", "Date", "Open", "High", "Low", "Close", "Volume"]])

        print(f"[INFO] {min(i + chunk_size, len(codes))}/{len(codes)} 銘柄 取得完了")
        result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        # チャンクごとに使い終わった生データを明示的に破棄し、次のチャンクに進む前に
        # メモリを解放する(512MBしかない無料枠でのOOM Kill対策)。
        del data, frames
        _release_memory()
        yield chunk, result
        time.sleep(sleep_between)


def fetch_daily_quotes(codes: list[str], period: str = "6mo", chunk_size: int = 30,
                        sleep_between: float = 0.7) -> pd.DataFrame:
    """複数銘柄の日足OHLCVをまとめて取得し、J-Quants版と同じ列構成のDataFrameに変換する。
    列: Code, Date, Open, High, Low, Close, Volume
    (途中経過が不要な用途向けの一括版。通常のスクリーニング実行では
    fetch_daily_quotes_chunks を使う)
    """
    all_frames = [df for _, df in fetch_daily_quotes_chunks(codes, period=period,
                                                              chunk_size=chunk_size,
                                                              sleep_between=sleep_between)
                  if not df.empty]
    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


def fetch_single_quote(code: str, period: str = "6mo") -> pd.DataFrame:
    """1銘柄分の日足OHLCVを取得する(アプリのチャート表示など、都度リクエスト向け)。
    列: Date, Open, High, Low, Close, Volume
    """
    ticker = f"{code}.T"
    data = yf.download(tickers=ticker, period=period, interval="1d",
                        progress=False, auto_adjust=False, timeout=20)
    if data.empty:
        return pd.DataFrame()
    # yfinanceのバージョンによって単一銘柄でもMultiIndex列になる場合があるため平坦化する
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(how="all").reset_index()
    return data[["Date", "Open", "High", "Low", "Close", "Volume"]]
