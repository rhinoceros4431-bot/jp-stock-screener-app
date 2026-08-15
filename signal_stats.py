"""
過去に出たシグナルが、その後の値動きとして「当たっていたか」を簡易集計するモジュール。

注意点(利用者向けに/api/resultsのレスポンスやUIにも表示している):
- 本格的なバックテストではなく、あくまで参考値。
- Renderの無料枠はディスクが一時的なもののため、プロセスが再起動(スリープ復帰・再デプロイ等)
  すると記録はリセットされる。長期間ノーリスタートで動き続けるほど、集計件数が増えて参考になる。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent
HISTORY_PATH = ROOT / "signal_history.json"

# シグナルが出てから何営業日相当(≒暦日)後の値動きで判定するか
HOLD_DAYS = 5

# シグナルごとに「期待する値動きの向き」("up"=上昇を期待 / "down"=下落を期待)
# breakout(値幅ブレイク)は高値ブレイクか安値ブレイクかで向きが変わるため、
# ヒットのlabel/directionから個別に判定する(下のrecord_new_signals参照)。
CATEGORY_DIRECTION = {
    "oversold": "up",
    "overbought": "down",
    "golden_cross": "up",
    "dead_cross": "down",
}


def _load() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(records: list[dict]) -> None:
    HISTORY_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def record_new_signals(new_matches: list[dict], price_map: dict[str, float], today: str) -> None:
    """新規該当した銘柄を、後で答え合わせするための記録として追加する。
    同じ(銘柄, カテゴリ, 日付)はすでにあれば追加しない(1日に何度実行しても重複登録しない)。
    """
    records = _load()
    existing_keys = {(r["code"], r["category"], r["entry_date"]) for r in records}
    changed = False
    for r in new_matches:
        price = price_map.get(r["code"])
        if price is None:
            continue
        direction = r.get("direction") or CATEGORY_DIRECTION.get(r["category"])
        if not direction:
            continue  # 出来高急増など、値動きの向きを定義できないシグナルは記録しない
        key = (r["code"], r["category"], today)
        if key in existing_keys:
            continue
        records.append({
            "code": r["code"],
            "name": r.get("name", ""),
            "category": r["category"],
            "direction": direction,
            "entry_date": today,
            "entry_price": price,
            "resolved": False,
            "outcome_date": None,
            "outcome_price": None,
            "return_pct": None,
            "win": None,
        })
        existing_keys.add(key)
        changed = True
    if changed:
        _save(records)


def resolve_pending(price_map: dict[str, float], today_date: dt.date) -> list[dict]:
    """HOLD_DAYS以上前に記録された未解決のシグナルについて、現在値との比較で結果を確定する。"""
    records = _load()
    changed = False
    for r in records:
        if r["resolved"]:
            continue
        try:
            entry_dt = dt.date.fromisoformat(r["entry_date"])
        except Exception:
            continue
        if (today_date - entry_dt).days < HOLD_DAYS:
            continue
        price = price_map.get(r["code"])
        if price is None:
            continue
        entry_price = r["entry_price"]
        if not entry_price:
            continue
        return_pct = (price - entry_price) / entry_price * 100
        win = (return_pct > 0) if r["direction"] == "up" else (return_pct < 0)
        r.update({
            "resolved": True,
            "outcome_date": today_date.isoformat(),
            "outcome_price": price,
            "return_pct": round(return_pct, 2),
            "win": win,
        })
        changed = True
    if changed:
        _save(records)
    return records


def summarize(records: list[dict]) -> dict:
    """カテゴリ別に、答え合わせ済みシグナルの的中率・平均リターンを集計する。"""
    by_cat: dict[str, dict] = {}
    for r in records:
        if not r.get("resolved"):
            continue
        cat = r["category"]
        s = by_cat.setdefault(cat, {"wins": 0, "total": 0, "_sum": 0.0})
        s["total"] += 1
        if r.get("win"):
            s["wins"] += 1
        s["_sum"] += r.get("return_pct") or 0.0

    out = {}
    for cat, s in by_cat.items():
        if not s["total"]:
            continue
        out[cat] = {
            "total": s["total"],
            "win_rate": round(s["wins"] / s["total"] * 100, 1),
            "avg_return_pct": round(s["_sum"] / s["total"], 2),
        }
    return out
