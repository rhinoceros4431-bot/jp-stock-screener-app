# 日本株スクリーニング PWA(スマホアプリ風・プッシュ通知対応)

日本株全銘柄(東証約4,000銘柄)を無料データ(JPX公式データ + yfinance)でスクリーニングし、結果をスマホアプリのような画面(PWA)で確認しつつ、条件に合致した銘柄が出たらブラウザ/スマホにプッシュ通知するアプリです。

## これは何か(PWAについて)

「ネイティブアプリ」を厳密に作る場合、iOSはApple Developer Program(年$99)への登録とMac環境でのビルド・審査提出、AndroidはGoogle Play開発者登録($25)と審査が必要で、このクラウド上のセッションだけでは配布まで完結できません。

代わりに **PWA(Progressive Web App)** として作りました。スマホでURLを開き「ホーム画面に追加」するだけで、アイコンが並び、全画面表示で、プッシュ通知も受け取れる、ネイティブアプリとほぼ同じ体験になります。審査不要・費用ゼロで今すぐ使えます。

- iPhoneの場合: Safariで開く →共有ボタン→「ホーム画面に追加」(iOS 16.4以降でプッシュ通知に対応)
- Androidの場合: Chromeで開く → メニュー→「アプリをインストール」

---

## 全体構成

```
jp-stock-screener-app/
├── README.md / DEPLOY_FREE.md / DEPLOY_NO_TERMINAL.md
└── backend/                    このフォルダの中身を丸ごとGitHubにアップロードします(サブフォルダ無し)
    ├── app.py                   メインアプリ(Flask)
    ├── screener_job.py          スクリーニング処理
    ├── indicators.py / universe.py / yfinance_client.py   データ取得・指標計算
    ├── push.py                  Web Push送信
    ├── db.py                    購読情報の保存(SQLite)
    ├── config.yaml              通知条件の設定
    ├── index.html / app.js / style.css   PWAの画面
    ├── manifest.json            ホーム画面追加用の設定
    ├── service-worker.js        プッシュ通知受信・オフライン対応
    ├── icon-192.png / icon-512.png       アプリアイコン
    ├── generate_vapid_keys.py   プッシュ通知用の鍵を再生成するスクリプト
    ├── vapid_keys.txt           あらかじめ生成した鍵(GitHubにはアップロードしないこと。下記参照)
    ├── requirements.txt / Procfile / setup.sh / start.sh / setup_ngrok.sh
    └── env.example
```

すべてのファイルを1つの階層(`backend`直下)にまとめています。フォルダ分けをすると、GitHubのブラウザアップロードで構造が崩れることがあるためです。`app.py`側では、`index.html`や`app.js`などフロントエンド用のファイル名だけを配信するようホワイトリストで制限しているので、`config.yaml`や`vapid_keys.txt`など他のファイルが誤って外部から見えることはありません。

---

## 1. 事前に用意したもの

**VAPID鍵**(プッシュ通知に必須の鍵ペア)をあらかじめ生成しました。`backend/vapid_keys.txt` に入っています。このまま使っても構いませんが、第三者に知られている前提の鍵なので、本格運用する場合は `python generate_vapid_keys.py` で再生成することをおすすめします。

---

## 2. ローカルで動かす(まずは動作確認)

```bash
cd jp-stock-screener-app/backend
pip install -r requirements.txt

cp env.example .env
# .env を開き、vapid_keys.txt の内容をコピーして VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY に設定
# ADMIN_TOKEN は好きな文字列でOK

# .env を読み込んで起動(direnvやpython-dotenvを使わない場合は export で読み込むか、以下のように起動時に読み込みます)
set -a; source .env; set +a
python app.py
```

`http://localhost:5000` にアクセスすると画面が表示されます。「今すぐ更新」ボタンでスクリーニングを試せます(全銘柄分なので初回は数分〜十数分かかります)。

**注意**: プッシュ通知(Push API)はブラウザの仕様上、`https://` または `localhost` でしか動作しません。ローカルでの通知テストは `localhost` なら可能ですが、スマホの実機で試すには次項のデプロイが必要です。

---

## 3. インターネットに公開する(スマホから使うために必須)

スマホから使う・プッシュ通知を受け取るには、常時起動していてHTTPSでアクセスできるサーバーにデプロイする必要があります。ここは重要なトレードオフがあるので整理します。

| 選択肢 | 費用 | 常時起動 | 備考 |
|---|---|---|---|
| Render.com (Free Web Service) | 無料 | ✕ 15分アクセスがないとスリープし、次のアクセス時に遅延して起動 | スケジュール実行(市場時間中の自動スクリーニング)がスリープ中は動きません。外部の無料稼働監視サービス(UptimeRobot等)で定期的にpingすれば起こし続けることは可能ですが、Render公式には推奨されていない使い方です |
| Render.com / Railway 等の有料プラン | 月500円〜1,000円程度 | ○ | 常時起動でき、スケジュール実行が確実に動きます。実用するならこちらを推奨 |
| 自宅PC + 常時起動 + Cloudflare Tunnel(無料) | 無料 | PCが起動している間のみ | 電気代はかかりますが金銭コストはゼロ。PCを付けっぱなしにできる場合の選択肢 |

**おすすめは [DEPLOY_NO_TERMINAL.md](./DEPLOY_NO_TERMINAL.md) です**(あなたのPCには何もインストールせず、ブラウザの画面操作だけでGitHub + Render.comの無料枠にデプロイする方法)。自宅PCを常時起動できる場合は [DEPLOY_FREE.md](./DEPLOY_FREE.md)(ngrokを使う方法)も選べます。

---

## 4. 通知の仕組み

- バックエンドが平日9:00〜15:30(JST)の間、`RUN_INTERVAL_MINUTES`(既定60分)おきにスクリーニングを自動実行します
- 前回実行時になかった新規該当銘柄がある場合のみ、購読している全端末にプッシュ通知を送ります(同じ銘柄で毎回通知が来ることはありません)
- アプリを開くと `/api/results` から最新の全該当銘柄一覧を確認できます(NEWバッジ付きで新規分もわかります)

---

## 5. 通知条件のカスタマイズ

`backend/config.yaml` を編集してください(内容は既存のスクリーニングツールと同じ形式です)。デプロイ後に条件を変えたい場合は、アプリの `/api/config` にJSONをPOSTすることでも変更できます(将来的に設定画面のUIも追加できます。ご要望があれば作ります)。

---

## 6. 注意事項・免責

- yfinance・JPX公開データは無料・非公式または個人利用前提のものです。大量・高頻度なアクセスは避けてください。
- 本アプリの通知は機械的なテクニカル条件判定であり、投資助言ではありません。投資判断はご自身の責任で行ってください。
- VAPID秘密鍵・ADMIN_TOKENなどは第三者に共有しないでください。
