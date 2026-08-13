#!/usr/bin/env bash
# 初回セットアップ用スクリプト。このファイルがある場所(backendフォルダ)で実行してください。
#   bash setup.sh
set -e

cd "$(dirname "$0")"

echo "[1/5] 必要なシステムパッケージを確認しています(パスワードを聞かれたら入力してください)..."
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3が見つかりません。'sudo apt install -y python3' を実行してから、このスクリプトを再実行してください。"
  exit 1
fi
# venvの中にpipが同梱されない環境があるため、python3-venv と python3-pip の両方を確実に入れておく
# (関係ないPPA等でapt updateが一部失敗しても、必要なパッケージのインストールは続行する)
sudo apt update || echo "  (一部のリポジトリ更新に失敗しましたが、続行します)"
sudo apt install -y python3-venv python3-pip

echo "[2/5] 仮想環境(venv)を作成しています..."
if [ -d "venv" ] && [ ! -f "venv/bin/pip" ]; then
  echo "  以前作成した壊れたvenvを削除して作り直します..."
  rm -rf venv
fi
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# それでもpipが同梱されていない場合の保険(ensurepip→get-pip.pyの順で試す)
if [ ! -f "venv/bin/pip" ]; then
  echo "  venvにpipが含まれていないため、追加でセットアップします..."
  ./venv/bin/python -m ensurepip --upgrade || {
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    ./venv/bin/python /tmp/get-pip.py
  }
fi

if [ ! -f "venv/bin/pip" ]; then
  echo "pipのセットアップに失敗しました。上に表示されたエラーメッセージをそのまま貼ってください。"
  exit 1
fi

echo "[3/5] 必要なライブラリをインストールしています(数分かかります)..."
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

echo "[4/5] .env ファイルを作成しています..."
if [ ! -f ".env" ]; then
  VAPID_PUBLIC_KEY=$(grep VAPID_PUBLIC_KEY vapid_keys.txt | cut -d= -f2)
  VAPID_PRIVATE_KEY=$(grep VAPID_PRIVATE_KEY vapid_keys.txt | cut -d= -f2)
  ADMIN_TOKEN=$(./venv/bin/python -c "import secrets; print(secrets.token_hex(16))")
  cat > .env <<EOF
VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
VAPID_CONTACT_EMAIL=mailto:example@example.com
ADMIN_TOKEN=${ADMIN_TOKEN}
RUN_INTERVAL_MINUTES=60
EOF
  echo "  .env を自動生成しました(vapid_keys.txtの鍵を使用)"
else
  echo "  .env は既に存在するのでそのままにします"
fi

echo "[5/5] セットアップ完了!"
echo ""
echo "次は以下のコマンドでアプリを起動してください:"
echo "  bash start.sh"
