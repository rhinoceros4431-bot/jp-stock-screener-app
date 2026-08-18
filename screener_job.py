"""
スクリーニングジョブ本体。
全銘柄データを取得 → config.yaml の条件で評価 → results_latest.json に保存 →
前回になかった新規該当銘柄があればプッシュ通知を送る。
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
import yaml

import indicators as ind
import pattern_match
import predictor
import signal_stats
import universe as univ
from yfinance_client import fetch_daily_quotes_chunks, fetch_single_quote

import push

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.yaml"
RESULTS_PATH = ROOT / "results_latest.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_stock(hist: pd.DataFrame, cfg: dict) -> list[dict]:
    """該当した条件を [{"type": ..., "label": ...}, ...] の形で返す。
    type はアプリ側でシグナル別ブロック(買われすぎ/売られすぎ等)に振り分けるための分類キー。
    """
    hist = hist.sort_values("Date")
    close = hist["Close"].astype(float)
    high = hist["High"].astype(float)
    low = hist["Low"].astype(float)
    volume = hist["Volume"].astype(float)

    hits: list[dict] = []

    min_avg_vol = cfg.get("min_avg_volume", 0)
    if len(volume) >= 20 and volume.tail(20).mean() < min_avg_vol:
        return []

    gc_cfg = cfg["golden_dead_cross"]
    if gc_cfg.get("enabled"):
        cross = ind.golden_dead_cross(close, gc_cfg["short_window"], gc_cfg["long_window"])
        if cross == "golden" and gc_cfg.get("notify_golden", True):
            hits.append({"type": "golden_cross", "label": f"ゴールデンクロス ({gc_cfg['short_window']}日線が{gc_cfg['long_window']}日線を上抜け)"})
        if cross == "dead" and gc_cfg.get("notify_dead", True):
            hits.append({"type": "dead_cross", "label": f"デッドクロス ({gc_cfg['short_window']}日線が{gc_cfg['long_window']}日線を下抜け)"})

    ov_cfg = cfg["overheat_indicators"]
    if ov_cfg.get("enabled"):
        if ov_cfg["rsi"].get("enabled"):
            r = ind.rsi(close, ov_cfg["rsi"]["period"])
            if not r.empty and not pd.isna(r.iloc[-1]):
                val = r.iloc[-1]
                if val <= ov_cfg["rsi"]["oversold"]:
                    hits.append({"type": "oversold", "label": f"RSI売られすぎ (RSI={val:.1f})"})
                elif val >= ov_cfg["rsi"]["overbought"]:
                    hits.append({"type": "overbought", "label": f"RSI買われすぎ (RSI={val:.1f})"})
        if ov_cfg["stochastic"].get("enabled"):
            k, d = ind.stochastic(high, low, close, ov_cfg["stochastic"]["k_period"], ov_cfg["stochastic"]["d_period"])
            if not k.empty and not pd.isna(k.iloc[-1]):
                val = k.iloc[-1]
                if val <= ov_cfg["stochastic"]["oversold"]:
                    hits.append({"type": "oversold", "label": f"ストキャスティクス売られすぎ (%K={val:.1f})"})
                elif val >= ov_cfg["stochastic"]["overbought"]:
                    hits.append({"type": "overbought", "label": f"ストキャスティクス買われすぎ (%K={val:.1f})"})

    vb_cfg = cfg["volume_breakout"]
    if vb_cfg.get("enabled"):
        vs_cfg = vb_cfg["volume_surge"]
        if vs_cfg.get("enabled") and ind.volume_surge(volume, vs_cfg["lookback_days"], vs_cfg["surge_multiple"]):
            hits.append({"type": "volume_surge", "label": f"出来高急増 (直近{vs_cfg['lookback_days']}日平均の{vs_cfg['surge_multiple']}倍以上)"})
        pb_cfg = vb_cfg["price_breakout"]
        if pb_cfg.get("enabled"):
            b = ind.price_breakout(high, low, close, pb_cfg["lookback_days"], pb_cfg["breakout_type"])
            if b == "high":
                hits.append({"type": "breakout", "label": f"{pb_cfg['lookback_days']}日ぶり高値ブレイク", "direction": "up"})
            elif b == "low":
                hits.append({"type": "breakout", "label": f"{pb_cfg['lookback_days']}日ぶり安値ブレイク", "direction": "down"})

    bb_cfg = cfg["bollinger_band"]
    if bb_cfg.get("enabled"):
        upper, mid, lower = ind.bollinger_bands(close, bb_cfg["window"], bb_cfg["sigma"])
        if not upper.empty and not pd.isna(upper.iloc[-1]):
            if close.iloc[-1] > upper.iloc[-1]:
                hits.append({"type": "overbought", "label": f"ボリンジャーバンド+{bb_cfg['sigma']}σ突破"})
            elif close.iloc[-1] < lower.iloc[-1]:
                hits.append({"type": "oversold", "label": f"ボリンジャーバンド-{bb_cfg['sigma']}σ突破"})

    wl_cfg = cfg.get("watched_levels", {})
    if wl_cfg.get("enabled"):
        ma_cfg = wl_cfg.get("moving_average", {})
        if ma_cfg.get("enabled"):
            ma_hits = ind.nearby_moving_average(close, tuple(ma_cfg.get("windows", (25, 75, 200))),
                                                 ma_cfg.get("threshold_pct", 1.5))
            if ma_hits:
                for m in ma_hits:
                    hits.append({"type": "watched_level",
                                 "label": f"{m['window']}日移動平均線が近い ({m['level']:.1f}円、乖離{m['distance_pct']}%)"})

        re_cfg = wl_cfg.get("recent_extreme", {})
        if re_cfg.get("enabled"):
            re_hits = ind.nearby_recent_extreme(high, low, close, re_cfg.get("lookback_days", 60),
                                                 re_cfg.get("threshold_pct", 2.0))
            if re_hits:
                for r in re_hits:
                    kind_label = "直近高値" if r["type"] == "high" else "直近安値"
                    hits.append({"type": "watched_level",
                                 "label": f"{kind_label}が近い ({r['level']:.1f}円、乖離{r['distance_pct']}%)"})

        rn_cfg = wl_cfg.get("round_number", {})
        if rn_cfg.get("enabled"):
            rn_hit = ind.nearby_round_number(close, rn_cfg.get("threshold_pct", 1.5))
            if rn_hit:
                hits.append({"type": "watched_level",
                             "label": f"キリの良い株価が近い ({rn_hit['level']:.0f}円、乖離{rn_hit['distance_pct']}%)"})

    return hits


# シグナル別ブロックの表示優先順(複数シグナルに該当する銘柄は、この順で最初に一致した
# カテゴリのブロックに表示する)。
CATEGORY_PRIORITY = ["oversold", "overbought", "golden_cross", "dead_cross", "breakout", "volume_surge", "watched_level"]


def _pick_category(hits: list[dict]) -> str:
    types = {h["type"] for h in hits}
    for c in CATEGORY_PRIORITY:
        if c in types:
            return c
    return "other"


def _pick_direction(hits: list[dict], category: str) -> str | None:
    """シグナル的中率の答え合わせ用に、そのカテゴリで「期待する値動きの向き」を1つ選ぶ。
    breakout(値幅ブレイク)は高値/安値どちらのブレイクかでhit側にdirectionを持たせている。"""
    if category in signal_stats.CATEGORY_DIRECTION:
        return signal_stats.CATEGORY_DIRECTION[category]
    for h in hits:
        if h["type"] == category and h.get("direction"):
            return h["direction"]
    return None


def run_screening() -> dict:
    cfg = load_config()

    lookback_candidates = [
        cfg["golden_dead_cross"]["long_window"],
        cfg["overheat_indicators"]["rsi"]["period"],
        cfg["overheat_indicators"]["stochastic"]["k_period"],
        cfg["volume_breakout"]["volume_surge"]["lookback_days"],
        cfg["volume_breakout"]["price_breakout"]["lookback_days"],
        cfg["bollinger_band"]["window"],
    ]
    lookback_days = max(lookback_candidates) + 10
    calendar_days = int(lookback_days * 1.6) + 15
    period = "1mo" if calendar_days <= 35 else "3mo" if calendar_days <= 95 else "6mo" if calendar_days <= 185 else "1y"

    print("[INFO] 上場銘柄一覧を取得中(JPX 無料データ)...")
    listed = univ.load_universe(cfg.get("target_markets") or None)
    code_to_name = dict(zip(listed["Code"], listed["CompanyName"]))
    code_to_industry = dict(zip(listed["Code"], listed["Industry"])) if "Industry" in listed.columns else {}
    codes = listed["Code"].tolist()
    total = len(codes)

    print(f"[INFO] {total}銘柄の日足データを取得中(yfinance)...")

    # 通知の新規判定用に、前回「完了済み」の結果を保持しておく
    prev_codes = set()
    if RESULTS_PATH.exists():
        try:
            prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
            prev_codes = {r["code"] for r in prev.get("results", [])}
        except Exception:
            pass

    results = []
    done_count = 0
    # シグナル的中率の答え合わせ(signal_stats)用に、該当有無にかかわらず全銘柄の最新終値を集める
    price_map: dict[str, float] = {}
    # 全銘柄の取得完了(15-30分程度かかる)を待たず、チャンク(150銘柄)ごとに
    # 途中経過をresults_latest.jsonへ書き出す。これによりアプリ側は実行中も
    # 「何も表示されない」状態にならず、その時点までの該当銘柄と進捗を表示できる。
    for chunk_codes, panel in fetch_daily_quotes_chunks(codes, period=period):
        if not panel.empty:
            grouped = panel.groupby("Code")
            for code, hist in grouped:
                if code not in code_to_name:
                    continue
                hist_sorted = hist.sort_values("Date")
                close_series = hist_sorted["Close"].astype(float).dropna()
                if not close_series.empty:
                    price_map[code] = float(close_series.iloc[-1])
                try:
                    hits = evaluate_stock(hist, cfg)
                except Exception as e:
                    print(f"[WARN] {code} の評価中にエラー: {e}")
                    continue
                if hits:
                    category = _pick_category(hits)
                    results.append({
                        "code": code,
                        "name": code_to_name[code],
                        "industry": code_to_industry.get(code, "その他"),
                        "category": category,
                        "direction": _pick_direction(hits, category),
                        "score": len(hits),
                        "hits": hits,
                    })
        done_count += len(chunk_codes)
        # より注目すべき(該当条件が多い)銘柄が上位に来るよう並び替えておく
        results.sort(key=lambda r: -r["score"])

        partial_new = [r for r in results if r["code"] not in prev_codes]
        partial_output = {
            "updated_at": None,  # 完了前はNoneにして「実行中」と区別する(完了時刻ではないため)
            "results": results,
            "new_match_codes": [r["code"] for r in partial_new],
            "status": "running",
            "progress": {"done": done_count, "total": total},
        }
        RESULTS_PATH.write_text(json.dumps(partial_output, ensure_ascii=False, indent=2), encoding="utf-8")

    now_dt = dt.datetime.now()
    now = now_dt.isoformat(timespec="seconds")
    results.sort(key=lambda r: -r["score"])
    new_matches = [r for r in results if r["code"] not in prev_codes]

    # 過去の類似パターン検索(該当銘柄のうちスコア上位のみ。2年分のデータを別途取得するため
    # 全銘柄には行わず、件数を絞って追加の負荷・実行時間・メモリ使用を抑える)
    pm_cfg = cfg.get("pattern_match", {})
    if pm_cfg.get("enabled") and results:
        max_stocks = pm_cfg.get("max_stocks", 150)
        sleep_between = pm_cfg.get("sleep_between", 0.3)
        target_results = results[:max_stocks]
        print(f"[INFO] 過去の類似パターン検索を実行中 ({len(target_results)}銘柄)...")
        for r in target_results:
            try:
                hist2y = fetch_single_quote(r["code"], period="2y")
                if hist2y.empty:
                    r["pattern_match"] = {"available": False, "reason": "no_data"}
                else:
                    hist2y = hist2y.sort_values("Date").reset_index(drop=True)
                    close_full = hist2y["Close"].astype(float)
                    dates_full = hist2y["Date"].dt.strftime("%Y-%m-%d").tolist()
                    r["pattern_match"] = pattern_match.find_similar_patterns(close_full, dates_full)
            except Exception as e:
                print(f"[WARN] {r['code']} の類似パターン検索でエラー: {e}")
                r["pattern_match"] = {"available": False, "reason": f"error: {e}"}
            time.sleep(sleep_between)

    # シグナル的中率の記録・答え合わせ(サーバー再起動でリセットされる簡易集計。詳細はsignal_stats.py参照)
    try:
        signal_stats.record_new_signals(new_matches, price_map, now_dt.date().isoformat())
        history = signal_stats.resolve_pending(price_map, now_dt.date())
        stats = signal_stats.summarize(history)
    except Exception as e:
        print(f"[WARN] シグナル的中率の集計に失敗しました: {e}")
        stats = {}

    # 将来の値動き予測(試験的機能)。今回のスキャンで既に計算済みのhits/pattern_matchのみを
    # 使って予測を作るため、追加のデータ取得は発生しない。まず目標日を迎えた過去の予測を
    # 答え合わせして重みを更新し、そのあと新しい予測を積む。
    prediction_stats = {}
    try:
        today_date = now_dt.date()
        predictor.resolve_due_predictions(price_map, today_date, cfg)
        pred_state = predictor.generate_predictions(results, price_map, cfg, today_date)
        prediction_stats = predictor.summarize_accuracy(pred_state)
        pending_by_code = {p["code"]: p for p in pred_state.get("pending", [])}
        for r in results:
            p = pending_by_code.get(r["code"])
            if p:
                r["prediction"] = {
                    "direction": p["predicted_direction"],
                    "confidence": p["confidence"],
                    "target_date": p["target_date"],
                }
    except Exception as e:
        print(f"[WARN] 将来予測の生成・答え合わせに失敗しました: {e}")

    output = {
        "updated_at": now,
        "results": results,
        "new_match_codes": [r["code"] for r in new_matches],
        "status": "done",
        "progress": {"done": total, "total": total},
        "signal_stats": stats,
        "prediction_stats": prediction_stats,
    }
    RESULTS_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] スクリーニング完了: {len(results)}銘柄該当 (うち新規{len(new_matches)}銘柄)")

    # 通知するシグナルカテゴリを設定で絞り込む(一覧画面には全カテゴリ表示されるが、
    # 通知が来るのはここで有効になっているカテゴリのみ)
    notify_categories = set(
        cfg.get("notification", {}).get("notify_categories")
        or (CATEGORY_PRIORITY + ["other"])
    )
    notify_matches = [r for r in new_matches if r["category"] in notify_categories]

    if notify_matches:
        names = "、".join(f"{r['name']}({r['code']})" for r in notify_matches[:10])
        more = f" 他{len(notify_matches) - 10}銘柄" if len(notify_matches) > 10 else ""
        push.send_to_all(
            title=f"株スクリーニング: {len(notify_matches)}銘柄が新たに該当",
            body=f"{names}{more}",
            url="/",
        )

    return output


if __name__ == "__main__":
    run_screening()
