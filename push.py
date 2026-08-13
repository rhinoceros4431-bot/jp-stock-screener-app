"""Web Push (VAPID) 通知の送信。"""
from __future__ import annotations

import json
import os

from pywebpush import WebPushException, webpush

import db

VAPID_PRIVATE_KEY = os.environ["VAPID_PRIVATE_KEY"]
VAPID_CLAIMS_SUB = os.environ.get("VAPID_CONTACT_EMAIL", "mailto:example@example.com")


def send_to_all(title: str, body: str, url: str = "/"):
    """登録されている全端末にプッシュ通知を送る。無効になった購読は自動的に削除する。"""
    subs = db.list_subscriptions()
    payload = json.dumps({"title": title, "body": body, "url": url})
    sent, failed = 0, 0
    for sub in subs:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_SUB},
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                # 購読が失効(アプリのアンインストール等) → 削除
                db.remove_subscription(sub["endpoint"])
            print(f"[WARN] プッシュ通知送信失敗: {e}")
    print(f"[INFO] プッシュ通知: 成功{sent}件 / 失敗{failed}件")
    return sent, failed
