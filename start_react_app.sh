#!/usr/bin/env bash
# GRACE SupportのFastAPIとReactをまとめて起動する。

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

usage() {
  printf '%s\n' \
    "Usage: ./start_react_app.sh" \
    "" \
    "起動済みのQdrant/Redisを確認し、FastAPIとReactを起動します。" \
    "終了するには Ctrl+C を押してください。"
}

cleanup() {
  trap - INT TERM EXIT
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  printf '\nFastAPIとReactを終了しました。Dockerの状態は変更していません。\n'
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'エラー: 必須コマンドが見つかりません: %s\n' "$1" >&2
    exit 1
  fi
}

port_must_be_free() {
  if lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'エラー: ポート%sは既に使用されています。既存プロセスを終了してから再実行してください。\n' "$1" >&2
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >&2 || true
    exit 1
  fi
}

wait_for_url() {
  local url="$1"
  local name="$2"
  local attempts=60
  while (( attempts > 0 )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 1
  done
  printf 'エラー: %sの起動を確認できませんでした: %s\n' "$name" "$url" >&2
  return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 0 ]]; then
  usage >&2
  exit 2
fi

require_command uv
require_command npm
require_command curl
require_command lsof
require_command nc
port_must_be_free 8000
port_must_be_free 5173

cd "$ROOT_DIR"
printf 'QdrantとRedisの接続を確認します...\n'
if ! curl -fsS "http://localhost:6333/healthz" >/dev/null 2>&1; then
  printf 'エラー: Qdrantへ接続できません。先にDocker側でQdrantを起動してください。\n' >&2
  exit 1
fi
if ! nc -z -w 1 127.0.0.1 6379 >/dev/null 2>&1; then
  printf 'エラー: Redisへ接続できません。先にDocker側でRedisを起動してください。\n' >&2
  exit 1
fi

printf '1/3 FastAPIを起動します...\n'
AGENT_SUPPORT_STORE="${AGENT_SUPPORT_STORE:-redis}" \
  uv run uvicorn api.app:app --reload --port 8000 &
BACKEND_PID=$!
trap cleanup INT TERM EXIT
wait_for_url "http://localhost:8000/health" "FastAPI"

printf '2/3 React依存関係を確認します...\n'
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci)
fi

printf '3/3 Reactを起動します...\n'
(cd frontend && npm run dev -- --host 127.0.0.1) &
FRONTEND_PID=$!
wait_for_url "http://localhost:5173" "React"

printf '\n起動完了: http://localhost:5173\n'
printf '終了するには Ctrl+C を押してください。\n'

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

printf 'エラー: FastAPIまたはReactが予期せず終了しました。\n' >&2
exit 1
