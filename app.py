"""
日本株スクリーニング PWA バックエンド (Flask)

エンドポイント:
  GET  /                      フロントエンド(index.html)
  GET  /api/results           最新のスクリーニング結果
  GET  /api/vapid-public-key  プッシュ購読に必要な公開鍵
  POST /api/subscribe         ブラウザのプッシュ購読情報を登録
  POST /api/unsubscribe       プッシュ購読を解除
  POST /api/run-now           手動でスクリーニングを即時実行(要ADMIN_TOKEN)
  GET  /api/config            現在の条件設定を取得
  POST /api/config            条件設定を更新
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from flask import Flask, jsonify, request, send_from_directory

import db
import push
from screener_job import CONFIG_PATH, RESULTS_PATH, run_screening

BASE_DIR = Path(__file__).parent
# フロントエンドのファイルもbackendと同じフォルダに置く構成(サブフォルダ構造を保ったまま
# GitHubにアップロードするのが難しいケースがあるため、あえて全部同じ階層に統一している)。
# app.py・config.yaml・vapid_keys.txt など公開してはいけないファイルと同じ場所にあるため、
# 以下のホワイトリストに載っているファイル名だけを配信し、それ以外は404にする。
FRONTEND_DIR = BASE_DIR
FRONTEND_FILES = {
    "index.html", "app.js", "style.css", "manifest.json", "service-worker.js",
    "icon-192.png", "icon-512.png", "settings.html", "settings.js",
}

app = Flask(__name__, static_folder=None)

VAPID_PUBLIC_KEY = os.environ["VAPID_PUBLIC_KEY"]
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
# 実行間隔(分)。市場が開いている平日日中を想定し、環境変数で調整可能。既定は60分。
RUN_INTERVAL_MINUTES = int(os.environ.get("RUN_INTERVAL_MINUTES", "60"))


# ---------------- フロントエンド配信 ----------------
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    # ホワイトリスト外(app.py, config.yaml, vapid_keys.txt, .env等)は絶対に配信しない
    if filename not in FRONTEND_FILES:
        return jsonify({"error": "not found"}), 404
    return send_from_directory(FRONTEND_DIR, filename)


_run_lock = threading.Lock()
_run_in_progress = False


def _maybe_trigger_run():
    """前回実行から十分な時間が経っていれば、バックグラウンドでスクリーニングを実行する。
    Render等の無料枠でプロセスがスリープ/再起動してもここでリカバリできるよう、
    アクセス(/api/results, /api/ping)のたびにこのチェックを行う。"""
    global _run_in_progress
    now = dt.datetime.now(JST)
    if not (_is_market_hours(now) or os.environ.get("IGNORE_MARKET_HOURS") == "1"):
        return
    with _run_lock:
        if _run_in_progress:
            return
        stale = True
        if RESULTS_PATH.exists():
            try:
                data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
                last = dt.datetime.fromisoformat(data["updated_at"])
                if last.tzinfo is None:
                    last = last.replace(tzinfo=JST)
                stale = (now - last) >= dt.timedelta(minutes=RUN_INTERVAL_MINUTES)
            except Exception:
                stale = True
        if not stale:
            return
        _run_in_progress = True

    def _job():
        global _run_in_progress
        try:
            print("[REQUEST-TRIGGERED] スクリーニングを実行します")
            run_screening()
        except Exception as e:
            print(f"[REQUEST-TRIGGERED] エラー: {e}")
        finally:
            _run_in_progress = False

    threading.Thread(target=_job, daemon=True).start()


# ---------------- API ----------------
@app.route("/api/ping")
def api_ping():
    """外部の無料稼働監視サービス(UptimeRobot等)からの定期アクセス用。
    アプリをスリープさせない目的と、遅延実行のトリガーを兼ねる。"""
    _maybe_trigger_run()
    return jsonify({"ok": True})


@app.route("/api/results")
def api_results():
    _maybe_trigger_run()
    if not RESULTS_PATH.exists():
        return jsonify({"updated_at": None, "results": [], "new_match_codes": []})
    return jsonify(json.loads(RESULTS_PATH.read_text(encoding="utf-8")))


@app.route("/api/vapid-public-key")
def api_vapid_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    sub = request.get_json(force=True)
    endpoint = sub["endpoint"]
    keys = sub["keys"]
    db.add_subscription(endpoint, keys["p256dh"], keys["auth"])
    return jsonify({"ok": True})


@app.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    sub = request.get_json(force=True)
    db.remove_subscription(sub["endpoint"])
    return jsonify({"ok": True})


@app.route("/api/config", methods=["GET"])
def api_get_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return jsonify(yaml.safe_load(f))


@app.route("/api/config", methods=["POST"])
def api_set_config():
    new_cfg = request.get_json(force=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(new_cfg, f, allow_unicode=True, sort_keys=False)
    return jsonify({"ok": True})


@app.route("/api/run-now", methods=["POST"])
def api_run_now():
    # アプリ内の「今すぐ更新」ボタンから呼ばれる。個人利用の無料アプリのため
    # 管理者トークンは要求しない(以前はADMIN_TOKENを要求していたが、フロント側が
    # トークンを送っていなかったため常に401になり、更新ボタンが機能しないバグになっていた)。
    global _run_in_progress
    with _run_lock:
        if _run_in_progress:
            return jsonify({"ok": True, "message": "スクリーニングは既に実行中です"})
        _run_in_progress = True

    def _job():
        global _run_in_progress
        try:
            run_screening()
        except Exception as e:
            print(f"[MANUAL-TRIGGER] エラー: {e}")
        finally:
            _run_in_progress = False

    threading.Thread(target=_job, daemon=True).start()
    return jsonify({"ok": True, "message": "スクリーニングを開始しました"})


JST = ZoneInfo("Asia/Tokyo")


def _is_market_hours(now: dt.datetime) -> bool:
    """平日 9:00-15:30 (JST) の間だけ True。土日祝や時間外は無駄な実行をしない。
    ※日本の祝日判定は行っていない簡易版(祝日にも1回無駄に実行される程度で実害は小さい)。"""
    if now.weekday() >= 5:  # 5=土, 6=日
        return False
    t = now.time()
    return dt.time(9, 0) <= t <= dt.time(15, 30)


# ---------------- バックグラウンドスケジューラ ----------------
def _scheduler_loop():
    while True:
        now = dt.datetime.now(JST)
        if _is_market_hours(now) or os.environ.get("IGNORE_MARKET_HOURS") == "1":
            try:
                print("[SCHEDULER] スクリーニングを実行します")
                run_screening()
            except Exception as e:
                print(f"[SCHEDULER] エラー: {e}")
        else:
            print("[SCHEDULER] 市場時間外のためスキップ")
        time.sleep(RUN_INTERVAL_MINUTES * 60)


def start_scheduler():
    # 注意: このスケジューラはアプリプロセス内のスレッドとして動きます。
    # gunicorn等でワーカー数を2以上にすると、その数だけスクリーニング/通知が重複実行されます。
    # Procfileではワーカー数を1に固定しています(スケール時は外部cronに切り出してください)。
    if os.environ.get("DISABLE_SCHEDULER") == "1":
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


db.init_db()
start_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
