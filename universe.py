"""
日本株全銘柄の一覧(銘柄コード・銘柄名・市場区分)を無料で取得する。

データ源: JPX(日本取引所グループ)が毎月公開している「東証上場銘柄一覧」(data_j.xls)
https://www.jpx.co.jp/markets/statistics-equities/misc/01.html
登録・APIキー不要、誰でも無料でダウンロード可能。
"""
from __future__ import annotations

import io
import re

import pandas as pd
import requests

LISTING_PAGE_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
# ページ構成が変わってリンクが取得できない場合のフォールバック(定期的にJPXが更新するURL)
FALLBACK_XLS_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

MARKET_NAME_MAP = {
    "プライム（内国株式）": "0111",
    "スタンダード（内国株式）": "0112",
    "グロース（内国株式）": "0113",
}


def _find_xls_url() -> str:
    try:
        resp = requests.get(LISTING_PAGE_URL, timeout=30)
        resp.raise_for_status()
        m = re.search(r'href="([^"]+data_j\.xls)"', resp.text)
        if m:
            url = m.group(1)
            if url.startswith("/"):
                url = "https://www.jpx.co.jp" + url
            return url
    except requests.RequestException:
        pass
    return FALLBACK_XLS_URL


def load_universe(target_markets: list[str] | None = None) -> pd.DataFrame:
    """全上場銘柄(コード・銘柄名・市場区分・業種)のDataFrameを返す。
    列: Code, CompanyName, MarketSegment, MarketCode, Industry
    """
    url = _find_xls_url()
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_excel(io.BytesIO(resp.content))

    # 実際の列名は年によって微妙に異なる場合があるため、部分一致で解決する
    col_code = next(c for c in df.columns if "コード" == str(c).strip())
    col_name = next(c for c in df.columns if "銘柄名" == str(c).strip())
    col_market = next(c for c in df.columns if "市場・商品区分" in str(c))
    # 33業種区分(JPXの無料データに含まれる業種分類)。「テーマ別」表示に使う。
    col_industry = next((c for c in df.columns if "33業種区分" in str(c)), None)

    out = pd.DataFrame({
        "Code": df[col_code].astype(str).str.strip(),
        "CompanyName": df[col_name].astype(str).str.strip(),
        "MarketSegment": df[col_market].astype(str).str.strip(),
    })
    if col_industry is not None:
        industry = df[col_industry].astype(str).str.strip()
        out["Industry"] = industry.replace({"nan": "その他", "-": "その他", "": "その他"})
    else:
        out["Industry"] = "その他"
    out["MarketCode"] = out["MarketSegment"].map(MARKET_NAME_MAP)

    # ETF/REIT/優先株など普通株以外の行を除外(市場区分が上記マップに無いものは除く)
    out = out.dropna(subset=["MarketCode"])

    if target_markets:
        out = out[out["MarketCode"].isin(target_markets)]

    return out.reset_index(drop=True)


if __name__ == "__main__":
    df = load_universe()
    print(f"取得銘柄数: {len(df)}")
    print(df.head())
