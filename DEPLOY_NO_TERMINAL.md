# ターミナルを使わない方法(推奨)

あなたのPCには何もインストールしません。ブラウザの画面操作だけで完結します。ビルドや実行はすべてクラウド上(Render.com)で行われます。無料です。

**この版はファイル構成をシンプルにしました**: フォルダ分けを一切せず、全ファイルを1つの階層にまとめています。GitHubのアップロード画面でフォルダ構造が崩れてしまう問題を避けるためです。

---

## 1. GitHubに無料登録する(まだの場合)

https://github.com/signup にアクセスし、メールアドレスで無料アカウントを作成してください。

## 2. GitHubに新しいリポジトリを作る

1. https://github.com/new を開く
2. Repository name に `jp-stock-screener-app` と入力
3. 「Public」のまま(Privateにできる場合はPrivateの方が安心です)
4. 「Create repository」をクリック

## 3. ファイルをアップロードする

1. リポジトリのページで「uploading an existing file」をクリック(見当たらなければ「Add file」→「Upload files」)
2. お渡ししたzipを解凍し、`backend`フォルダの**中にあるファイルを全部**(サブフォルダは無く、20数個のファイルが並んでいるはずです)選択してドラッグ&ドロップ
   - **注意**: `vapid_keys.txt` だけはアップロードしないでください(次のステップでRenderの環境変数に直接入力するので、GitHub上に置く必要がなく、公開リポジトリだと第三者に見えてしまいます)
3. 画面を一番下までスクロールして「Commit changes」をクリック

## 4. Render.comに無料登録する

1. https://render.com/ にアクセスし、「Get Started」→ GitHubアカウントでサインアップ
2. GitHubとの連携を許可する

## 5. Web Serviceを作成する

1. Renderのダッシュボードで「New +」→「Web Service」
2. 先ほど作った `jp-stock-screener-app` リポジトリを選択して「Connect」
3. 以下を設定:
   - **Name**: 好きな名前(例: `jp-stock-screener`)
   - **Root Directory**: 空欄のまま(何も入力しない)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
   - **Instance Type**: `Free`
4. 「Advanced」を開き、「Add Environment Variable」で以下を1つずつ追加:

   | Key | Value |
   |---|---|
   | `VAPID_PUBLIC_KEY` | `BHLjH-8PQU1oFrJ15rmu5VTYCsxfP-xtRWT6QD6gy1d1nbMEtlyShhL7rzn9ceWk_mX-uUt-cbxwDe91ks3nlnI` |
   | `VAPID_PRIVATE_KEY` | `sH-CIxfoaPY37SClrrB6U2q1cC2rcWqfy_K4jwA6PVs` |
   | `VAPID_CONTACT_EMAIL` | `mailto:rhinoceros4431@gmail.com` |
   | `ADMIN_TOKEN` | `mytoken12345` |
   | `RUN_INTERVAL_MINUTES` | `60` |

5. 一番下の「Create Web Service」をクリック

数分待つとビルドが完了し、`https://jp-stock-screener-xxxx.onrender.com` のようなURLが発行されます。

## 6. スマホでアクセスしてホーム画面に追加

1. スマホのブラウザで発行されたURLを開く
2. iPhone: 共有ボタン→「ホーム画面に追加」/ Android: メニュー→「アプリをインストール」
3. アプリを開き、「通知を有効にする」をタップ

---

## 7. スリープさせないための設定(無料・推奨)

Renderの無料プランは15分アクセスがないとスリープします。

1. https://uptimerobot.com/ で無料アカウントを作成
2. 「+ Add New Monitor」
   - Monitor Type: `HTTP(s)`
   - URL: `https://あなたのRenderのURL/api/ping`
   - Monitoring Interval: `5 minutes`
3. 保存

---

## 設定を変更したいとき

`config.yaml`(通知条件)を変えたい場合は、GitHub上でそのファイルを開いて鉛筆マーク(Edit)で編集し、「Commit changes」を押せば、Renderが自動で再デプロイします。
