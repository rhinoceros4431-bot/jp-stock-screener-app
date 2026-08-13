#!/usr/bin/env bash
# アプリを起動するスクリプト。setup.sh を先に一度実行しておいてください。
#   bash start.sh
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "先に 'bash setup.sh' を実行してください。"
  exit 1
fi

set -a
source .env
set +a

echo "アプリを起動します。 http://localhost:5000 で確認できます。"
echo "終了するには Ctrl+C を押してください。"
./venv/bin/python app.py
