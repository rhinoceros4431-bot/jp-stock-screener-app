"""
将来の値動き予測と、その答え合わせによる自動改善の仕組み(試験的機能)。

既存の各シグナル(売られすぎ・ゴールデンクロス・値幅ブレイクなど)や
過去の類似パターン検索の結果を「重み付き投票」で合成し、数日後の値動きの
方向(上昇/下落)を予測する。予測した銘柄は predictions.json に記録しておき、
目標日を迎えたら実際の値動きと照合して当たり外れを記録する。
的中したシグナルの重みは上げ、外れたシグナルの重みは下げることで、
運用を続けるほど予測が(理論上は)実績に基づいて調整されていく、という
簡易な自己改善の仕組み(いわゆる重み付き多数決/オンライン学習の考え方)。

あくまで既存シグナルの組み合わせによる参考情報であり、将来の値動きを
保証するものではない。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent
PREDICTIONS_PATH = ROOT / "predictions.json"

# 各シグナルが「上昇/下落のどちらを示唆するか」の既定値。
# breakout(値幅ブレイク)は個別のhitに direction("up"/"down") が入っているのでそちらを使う。
# watched_level(注目の価格帯)は方向を示唆しないため、予測材料には使わない。
DIRECTIONAL_TYPES = {
    "oversold": "up",
    "overbought": "down",
    "golden_cross": "up",
    "dead_cross": "down",
}

DEFAULT_WEIGHT = 1.0
MIN_WEIGHT = 0.2
MAX_WEIGHT = 3.0

# ファイルサイズと処理量を抑えるための上限(無料枠のメモリ対策)
MAX_PENDING = 400
MAX_RESOLVED = 400


def _empty_state() -> dict:
    return {"weights": {}, "pending": [], "resolved": []}


def load_state() -> dict:
    if not PREDICTIONS_PATH.exists():
        return _empty_state()
    try:
        state = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8"))
        state.setdefault("weights", {})
        state.setdefault("pending", [])
        state.setdefault("resolved", [])
        return state
    except Exception:
        return _empty_state()


def save_state(state: dict) -> None:
    PREDICTIONS_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_weight(weights: dict, key: str) -> float:
    return weights.get(key, DEFAULT_WEIGHT)


def _signal_direction(hit_type: str, hits: list[dict]) -> str | None:
    if hit_type in DIRECTIONAL_TYPES:
        return DIRECTIONAL_TYPES[hit_type]
    if hit_type == "breakout":
        for h in hits:
            if h["type"] == "breakout" and h.get("direction"):
                return h["direction"]
    return None


def _pattern_match_direction(pm: dict | None) -> str | None:
    if not pm or not pm.get("available"):
        return None
    avg = pm.get("avg_forward_return_pct")
    if avg is None:
        return None
    if avg > 0:
        return "up"
    if avg < 0:
        return "down"
    return None


def build_prediction(code: str, hits: list[dict], pattern_match_result: dict | None,
                      weights: dict) -> dict | None:
    """既存シグナルを重み付き投票で合成し、方向予測を作る。
    予測材料が無い(すべて中立、または上昇・下落が拮抗)場合は None を返す。"""
    contributions = []  # 予測に使った材料の記録(答え合わせ・重み更新に使う)
    score = 0.0
    seen_types = set()

    for h in hits:
        t = h["type"]
        if t in seen_types:
            continue
        direction = _signal_direction(t, hits)
        if direction is None:
            continue
        seen_types.add(t)
        w = _get_weight(weights, t)
        score += w if direction == "up" else -w
        contributions.append({"signal": t, "direction": direction, "weight": w})

    pm_direction = _pattern_match_direction(pattern_match_result)
    if pm_direction is not None:
        w = _get_weight(weights, "pattern_match")
        score += w if pm_direction == "up" else -w
        contributions.append({"signal": "pattern_match", "direction": pm_direction, "weight": w})

    if not contributions or score == 0:
        return None

    predicted_direction = "up" if score > 0 else "down"
    total_weight = sum(c["weight"] for c in contributions)
    confidence = round(min(1.0, abs(score) / total_weight), 2) if total_weight else 0.0

    return {
        "code": code,
        "predicted_direction": predicted_direction,
        "confidence": confidence,
        "contributions": contributions,
    }


def generate_predictions(results: list[dict], price_map: dict, cfg: dict, today: dt.date) -> dict:
    """まだ予測を出していない該当銘柄について、新しい予測を作って pending に積む。
    (今回のスキャンで既に計算済みのhits/pattern_matchのみを使うため、追加の
    データ取得は発生しない)"""
    pred_cfg = cfg.get("prediction", {})
    state = load_state()
    if not pred_cfg.get("enabled"):
        return state

    weights = state["weights"]
    pending = state["pending"]
    pending_codes = {p["code"] for p in pending}

    horizon_days = pred_cfg.get("horizon_days", 7)
    max_new = pred_cfg.get("max_new_per_run", 30)
    target_date = (today + dt.timedelta(days=horizon_days)).isoformat()

    new_count = 0
    for r in results:
        if new_count >= max_new:
            break
        code = r["code"]
        if code in pending_codes:
            continue
        price = price_map.get(code)
        if price is None:
            continue
        pred = build_prediction(code, r.get("hits", []), r.get("pattern_match"), weights)
        if pred is None:
            continue
        pending.append({
            "code": code,
            "name": r.get("name", ""),
            "issued_date": today.isoformat(),
            "target_date": target_date,
            "issue_price": price,
            "predicted_direction": pred["predicted_direction"],
            "confidence": pred["confidence"],
            "contributions": pred["contributions"],
        })
        pending_codes.add(code)
        new_count += 1

    state["pending"] = pending[-MAX_PENDING:] if len(pending) > MAX_PENDING else pending
    save_state(state)
    return state


def resolve_due_predictions(price_map: dict, today: dt.date, cfg: dict) -> dict:
    """目標日を迎えた予測を答え合わせし、当たった/外れたシグナルの重みを更新する。"""
    state = load_state()
    pred_cfg = cfg.get("prediction", {})
    if not pred_cfg.get("enabled"):
        return state

    weights = state["weights"]
    learning_rate = pred_cfg.get("learning_rate", 0.1)
    still_pending = []
    newly_resolved = []

    for p in state["pending"]:
        target_date = dt.date.fromisoformat(p["target_date"])
        if target_date > today:
            still_pending.append(p)
            continue
        price = price_map.get(p["code"])
        if price is None:
            # まだ価格が取れない(取得失敗等)。しばらく保留し、1ヶ月以上
            # 遅延したら答え合わせを諦めて捨てる。
            if (today - target_date).days > 30:
                continue
            still_pending.append(p)
            continue

        issue_price = p["issue_price"]
        actual_return_pct = round((price - issue_price) / issue_price * 100, 2) if issue_price else 0.0
        actual_direction = "up" if actual_return_pct > 0 else "down" if actual_return_pct < 0 else "flat"
        hit = (
            (p["predicted_direction"] == "up" and actual_return_pct > 0)
            or (p["predicted_direction"] == "down" and actual_return_pct < 0)
        )

        # 貢献したシグナルごとに重みを更新(当たれば重みを上げ、外れれば下げる)。
        for c in p.get("contributions", []):
            key = c["signal"]
            w = _get_weight(weights, key)
            signal_correct = (
                (c["direction"] == "up" and actual_return_pct > 0)
                or (c["direction"] == "down" and actual_return_pct < 0)
            )
            w = w * (1 + learning_rate) if signal_correct else w * (1 - learning_rate)
            weights[key] = round(min(MAX_WEIGHT, max(MIN_WEIGHT, w)), 4)

        newly_resolved.append({
            **p,
            "actual_price": price,
            "actual_return_pct": actual_return_pct,
            "actual_direction": actual_direction,
            "hit": hit,
            "resolved_date": today.isoformat(),
        })

    resolved = state["resolved"] + newly_resolved
    state["pending"] = still_pending
    state["resolved"] = resolved[-MAX_RESOLVED:] if len(resolved) > MAX_RESOLVED else resolved
    state["weights"] = weights
    save_state(state)
    return state


def summarize_accuracy(state: dict) -> dict:
    """全体の的中率と、直近分だけの的中率(重みの調整が効き始めているかの目安)を集計する。"""
    resolved = state.get("resolved", [])
    if not resolved:
        return {"total": 0, "weights": state.get("weights", {})}
    total = len(resolved)
    hits = sum(1 for r in resolved if r["hit"])
    recent = resolved[-50:]
    recent_hits = sum(1 for r in recent if r["hit"])
    return {
        "total": total,
        "win_rate": round(hits / total * 100, 1),
        "recent_total": len(recent),
        "recent_win_rate": round(recent_hits / len(recent) * 100, 1) if recent else 0,
        "weights": state.get("weights", {}),
    }
