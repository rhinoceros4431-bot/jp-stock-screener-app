# ターミナルを使わない方法(推奨・こちらに切り替えましょう)

WSLでのセットアップが上手くいかないので、方針を変えます。この方法は**あなたのPCに何もインストールしません**。ブラウザの画面操作だけで完結します。ビルドや実行はすべてクラウド上(Render.com)で行われるので、pipやvenvのエラーとは無縁です。

無料です。唯一の制約は「15分アクセスがないと一時的にスリープする」ことですが、後述の設定でほぼ気にならなくなります。

---

## 1. GitHubに無料登録する(まだの場合)

https://github.com/signup にアクセスし、メールアドレスで無料アカウントを作成してください。

## 2. GitHubに新しいリポジトリを作る

1. https://github.com/new を開く
2. Repository name に `jp-stock-screener-app` と入力
3. 「Public」のまま(Privateでも構いません)
4. 「Create repository」をクリック

## 3. ファイルをアップロードする(ドラッグ&ドロップでOK)

1. 作成されたリポジトリのページで「uploading an existing file」というリンクをクリック
   (見当たらない場合は「Add file」→「Upload files」)
2. お渡ししたzipを解凍し、`jp-stock-screener-app`フォルダの**中身(backend, frontend, README.md など)**をまとめてドラッグ&ドロップ
3. 下の方にある「Commit changes」をクリック

これでコードがGitHub上に置かれました。

## 4. Render.comに無料登録する

1. https://render.com/ にアクセスし、「Get Started」→ GitHubアカウントでサインアップ(連携がスムーズです)
2. GitHubとの連携を許可する画面が出たら許可してください

## 5. Web Serviceを作成する

1. Renderのダッシュボードで「New +」→「Web Service」
2. 先ほど作った `jp-stock-screener-app` リポジトリを選択して「Connect」
3. 以下を設定:
   - **Name**: 好きな名前(例: `jp-stock-screener`)
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
   - **Instance Type**: `Free`
4. 「Advanced」を開き、「Add Environment Variable」で以下を1つずつ追加:

   | Key | Value |
   |---|---|
   | `VAPID_PUBLIC_KEY` | (お渡しした `vapid_keys.txt` の該当行の値) |
   | `VAPID_PRIVATE_KEY` | (同上) |
   | `VAPID_CONTACT_EMAIL` | `mailto:あなたのメールアドレス` |
   | `ADMIN_TOKEN` | 好きな文字列(例: `mytoken12345`) |
   | `RUN_INTERVAL_MINUTES` | `60` |

5. 一番下の「Create Web Service」をクリック

数分待つとビルドが完了し、`https://jp-stock-screener-xxxx.onrender.com` のようなURLが発行されます。これがあなたのアプリのURLです。

## 6. スマホでアクセスしてホーム画面に追加

1. スマホのブラウザで発行されたURLを開く
2. iPhone: 共有ボタン→「ホーム画面に追加」/ Android: メニュー→「アプリをインストール」
3. アプリを開き、「通知を有効にする」をタップ

---

## 7. スリープさせないための設定(無料・任意だが推奨)

Renderの無料プランは15分アクセスがないとスリープします。これを防ぐため、無料の外部監視サービスで定期的にアプリへアクセスさせます。

1. https://uptimerobot.com/ で無料アカウントを作成
2. 「+ Add New Monitor」
   - Monitor Type: `HTTP(s)`
   - Friendly Name: 好きな名前
   - URL: `https://あなたのRenderのURL/api/ping`
   - Monitoring Interval: `5 minutes`(無料プランで選べる最短)
3. 保存

これで5分おきにアクセスが発生し、市場時間中はスリープしなくなります。またこの `/api/ping` へのアクセスは「前回の実行から時間が経っていればスクリーニングを自動実行する」役割も兼ねているので、多少アプリがスリープしても次にアクセスが来たときに自動で追いつきます。

---

## この方法のまとめ

- あなたのPCには何もインストールしない(ブラウザだけ)
- コードの実行はRender.com上で行われる(WSLやPython環境の問題と無関係)
- 費用は無料(GitHub無料アカウント + Renderの無料Web Service + UptimeRobotの無料監視)
- 設定を変更したいとき(config.yamlの条件変更など)は、GitHub上でファイルを編集して保存すれば、Renderが自動的に再デプロイします
