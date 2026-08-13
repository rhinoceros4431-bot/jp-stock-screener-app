#!/usr/bin/env bash
# ngrok(無料の公開用トンネル)をインストールするスクリプト(WSL/Ubuntu用)。
#   bash setup_ngrok.sh
set -e

if command -v ngrok >/dev/null 2>&1; then
  echo "ngrok は既にインストールされています。"
else
  echo "ngrok をインストールします(パスワードを聞かれたら入力してください)..."
  curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
    | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
  echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
    | sudo tee /etc/apt/sources.list.d/ngrok.list
  sudo apt update
  sudo apt install -y ngrok
fi

echo ""
echo "インストール完了。次に以下を行ってください:"
echo "  1. https://dashboard.ngrok.com/signup で無料アカウントを作成"
echo "  2. https://dashboard.ngrok.com/get-started/your-authtoken でトークンをコピー"
echo "  3. 以下のコマンドを実行(<トークン>を貼り付けて):"
echo "     ngrok config add-authtoken <トークン>"
echo "  4. https://dashboard.ngrok.com/domains で「+ Create Domain」を押し、発行されたドメインをコピー"
echo "  5. 以下のコマンドでトンネルを起動(アプリ(start.sh)を別のターミナルで起動した状態で):"
echo "     ngrok http --domain=発行されたドメイン 5000"
