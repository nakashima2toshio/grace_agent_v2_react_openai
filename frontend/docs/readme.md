# GRACE Agent Support React Frontend ドキュメント

## このアプリの実行方法

### 1. Dockerを起動する

QdrantとRedisは、アプリとは別にリポジトリのルートディレクトリで起動します。

```bash
docker compose -f docker-compose/docker-compose.yml up -d
```

起動確認:

```bash
docker compose -f docker-compose/docker-compose.yml ps
```

### 2. アプリを起動する

QdrantとRedisの起動後、リポジトリのルートディレクトリで次の1コマンドを実行します。

```bash
./start_react_app.sh
```

起動済みのQdrant・Redisへの接続を確認した後、FastAPIとReactが順番に起動し、
完了すると`http://localhost:5173`が表示されます。FastAPIとReactを終了するには
同じターミナルで`Ctrl+C`を押してください。Dockerの起動・停止はこのスクリプトでは行いません。

初回だけ`frontend/node_modules`が存在しない場合に`npm ci`も自動実行します。

### 3. 画面を開く

ブラウザで[http://localhost:5173](http://localhost:5173)を開きます。

### 4. 終了する

`start_react_app.sh`を実行したターミナルで`Ctrl+C`を押すと、FastAPIとReactが終了します。
Dockerは停止しません。QdrantとRedisも停止する場合だけ、別途次を実行します。

```bash
docker compose -f docker-compose/docker-compose.yml down
```

> 📝 **注意**: `down -v`はQdrantとRedisの永続ボリュームを削除するため、通常の終了では使用しないでください。

### 前提条件

- Docker / Docker Compose
- Python環境と`uv`
- Node.js / npm
- リポジトリ直下の`.env`または環境変数に`OPENAI_API_KEY`を設定済み
- 検索対象のQdrantコレクションを登録済み（コレクションは本アプリから自動作成しません）

> **対象**: `frontend/`<br>
> **バージョン**: 1.5<br>
> **最終更新日**: 2026-07-17

## 目次

1. [概要](#1-概要)
2. [アーキテクチャ構成図](#2-アーキテクチャ構成図)
3. [モジュール構成図](#3-モジュール構成図)
4. [モジュール一覧](#4-モジュール一覧)
5. [処理 IPO詳細](#5-処理-ipo詳細)
6. [設定・定数](#6-設定定数)
7. [使用例](#7-使用例)
8. [エクスポート](#8-エクスポート)
9. [変更履歴](#9-変更履歴)
10. [付録: 依存関係図](#付録-依存関係図)

## 1. 概要

`agent_support_example.py`相当の自律エージェント処理を、ブラウザから実行・監視・承認するReactフロントエンドです。Plan、Execute、Groundedness、回答ゲート、情報なし検知、Web相互検証、HITL Actionの状態をFastAPIとSSE経由で表示します。業務ロジックとAction実行はバックエンドに置き、フロントエンドは入力、可視化、明示的な人の判断を担当します。

### 1.1 主な責務

- 問い合わせ、業界、Web検証、Action、dry-runの入力
- 実行作成・中止・履歴取得・再表示
- SSEによる進捗イベントの受信と重複排除
- 計画、各実行ステップ、検証指標、回答・エスカレーションの表示
- Actionの承認・却下・JSON引数修正
- 最後に開いた実行の`localStorage`復元

### 1.2 各責務対応のモジュール

| 責務 | モジュール |
|---|---|
| 画面・状態・操作 | [`App.md`](./App.md) |
| REST/SSE通信 | [`agentSupportClient.md`](./agentSupportClient.md) |
| 進捗表示 | [`WorkflowTimeline.md`](./WorkflowTimeline.md) |
| API/UI型境界 | [`agentSupportTypes.md`](./agentSupportTypes.md) |
| エントリーポイント | `src/main.tsx` |
| スタイル | `src/styles.css`, `src/details.css` |

### 1.3 主要機能一覧

| 機能 | 内容 |
|---|---|
| Run作成 | `POST /api/agent-support/runs` |
| 進捗監視 | `EventSource`で実行イベントを購読 |
| 状態同期 | イベント受信時にRunを再取得 |
| HITL | 版番号・Actionハッシュ付きで承認、却下、修正 |
| 再接続 | 保存済みRun IDを初期表示時に取得 |
| 型同期 | OpenAPIからTypeScript型を生成 |
| 実行結果の正規化 | リプラン後の最新Planと、各Stepの確定結果を表示 |
| 安全な回答表示 | `answer`だけ本文を表示し、`escalate`は理由のみ表示 |
| エラー可視化 | timeout等の構造化理由を日本語で表示 |

### 1.4 Streamlit／React比較試験

代表問い合わせを同一条件で比較する場合は、Qdrant起動後にリポジトリ直下で実行します。

```bash
uv run python scripts/compare_agent_support_surfaces.py \
  --output frontend/docs/streamlit_react_comparison_result.json
```

2026-07-17の実比較では「住民票を取得したい。」に対し、React経路は`decision=answer`、Web出典8件、Actionなしとなり、窓口・コンビニ・マイナンバーカード・自治体の主要項目が両経路で一致しました。保存結果は[`streamlit_react_comparison_result.json`](./streamlit_react_comparison_result.json)を参照してください。

## 2. アーキテクチャ構成図

```mermaid
flowchart TB
    subgraph Presentation["プレゼンテーション層"]
        App["App.tsx"]
        Timeline["WorkflowTimeline.tsx"]
        Styles["CSS"]
    end
    subgraph Client["クライアント・型境界層"]
        Api["agentSupportClient.ts"]
        Types["agentSupport.ts / generated.ts"]
    end
    subgraph Backend["バックエンド層"]
        FastAPI["FastAPI REST / SSE"]
        Grace["GRACE orchestration"]
        Hitl["HITL Action"]
    end
    App --> Timeline
    App --> Api
    App --> Types
    Api --> FastAPI --> Grace --> Hitl
    Types --> Api
    Styles --> App
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class App,Timeline,Styles,Api,Types,FastAPI,Grace,Hitl default
style Presentation fill:#1a1a1a,stroke:#fff,color:#fff
style Client fill:#1a1a1a,stroke:#fff,color:#fff
style Backend fill:#1a1a1a,stroke:#fff,color:#fff
```

## 3. モジュール構成図

```mermaid
flowchart LR
    Main["main.tsx"] --> App["App.tsx"]
    App --> Client["api/agentSupportClient.ts"]
    App --> Timeline["components/WorkflowTimeline.tsx"]
    App --> Types["types/agentSupport.ts"]
    Client --> Types
    Timeline --> Types
    Types --> Generated["types/generated.ts"]
    OpenAPI["openapi.json"] --> Generated
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class Main,App,Client,Timeline,Types,Generated,OpenAPI default
```

## 4. モジュール一覧

| モジュール | クラス・関数・公開要素 | 詳細 |
|---|---|---|
| `App.tsx` | `App`, `Title`, `Metric` | [`App.md`](./App.md) |
| `agentSupportClient.ts` | `json`, `confirmation`, `agentSupportClient` | [`agentSupportClient.md`](./agentSupportClient.md) |
| `WorkflowTimeline.tsx` | `WorkflowTimeline`, `steps`, `order` | [`WorkflowTimeline.md`](./WorkflowTimeline.md) |
| `agentSupport.ts` | 実行・結果・イベント・確認応答型 | [`agentSupportTypes.md`](./agentSupportTypes.md) |

## 5. 処理 IPO詳細

### 5.1 エージェント実行ワークフロー

**概要**: UI入力から結果表示または有人エスカレーションまでを非同期に追跡します。各関数の完全なIPOは上記モジュール文書を参照してください。

```typescript
createRun(request: RunRequest): Promise<RunRecord>
events(id: string, onEvent: (event: RunEvent) => void, onError: () => void): () => void
```

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `request` | `RunRequest` | - | 問い合わせと実行オプション |
| `onEvent` | `(RunEvent) => void` | - | 進捗イベント処理 |
| `onError` | `() => void` | - | SSE障害時の再取得処理 |

| 項目 | 内容 |
|---|---|
| **Input** | 問い合わせ、業界、`use_web`、`do_action`、`dry_run`、任意の本人確認情報 |
| **Process** | 1. Run作成<br>2. SSE購読<br>3. Plan → Execute → Groundedness → Gate → No-info/Web検証を表示<br>4. 必要時にHITL判断<br>5. 回答またはエスカレーションを表示 |
| **Output** | `RunRecord`と`RunEvent[]`に基づく画面表示 |

**戻り値例**:

```typescript
{ run_id: 'run-1', state: 'queued', request: { query: '質問', use_web: true, do_action: true, dry_run: true } }
```

```typescript
// 使用例
const run = await agentSupportClient.createRun(request)
const close = agentSupportClient.events(run.run_id, console.log, console.error)
// 出力: 進捗イベントを受信。不要になったら close()
```

### 5.2 HITL確認ワークフロー

**概要**: `pending_confirmation`が存在する場合だけ、現在の版番号とActionハッシュを添えて人の判断を送ります。

```typescript
confirm(run: RunRecord, decision: 'approve' | 'reject' | 'modify', action?: ActionRequest): Promise<ConfirmationResponse>
```

| パラメータ | 型 | デフォルト | 説明 |
|---|---|---|---|
| `run` | `RunRecord` | - | 最新の確認待ち実行 |
| `decision` | `'approve' \| 'reject' \| 'modify'` | - | 人の判断 |
| `action` | `ActionRequest` | optional | 修正後のAction |

| 項目 | 内容 |
|---|---|
| **Input** | 判断、版番号、Actionハッシュ、任意の修正Action |
| **Process** | 1. 確認待ち情報を取得<br>2. JSONをPOST<br>3. 最新Runへ画面状態を更新 |
| **Output** | `ConfirmationResponse` |

**戻り値例**:

```typescript
{ run: { ...run, state: 'action_executing', pending_confirmation: undefined } }
```

```typescript
// 使用例
const response = await agentSupportClient.confirm(run, 'approve')
// 出力: 判断反映後のRunRecord
```

## 6. 設定・定数

| 項目 | 値・コマンド | 用途 |
|---|---|---|
| `VITE_API_BASE` | 未設定時は空文字 | APIのベースURL |
| Vite proxy | `/api` → `http://localhost:8000` | 開発時バックエンド接続 |
| `grace-support-run-id` | localStorageキー | 最後のRun復元 |
| `npm run types:generate` | OpenAPI型生成 | `generated.ts`更新 |

## 7. 使用例

```bash
# Dockerは別起動
docker compose -f docker-compose/docker-compose.yml up -d

# FastAPIとReactを1コマンドで起動
./start_react_app.sh
# 出力: 起動完了: http://localhost:5173
```

検証コマンド:

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

## 8. エクスポート

- `App.tsx`: default export `App`
- `WorkflowTimeline.tsx`: named export `WorkflowTimeline`
- `agentSupportClient.ts`: named export `agentSupportClient`
- `agentSupport.ts`: named type exports

## 9. 変更履歴

| バージョン | 変更内容 |
|---|---|
| 1.0 | 初版作成。構成、実行フロー、HITL、設定、モジュール文書索引を追加 |
| 1.1 | 文書先頭に、前提条件、Qdrant/Redis、FastAPI、Reactの起動確認・終了手順を追加 |
| 1.2 | 実行結果正規化、構造化エラー表示、Streamlit／React比較試験の実行方法と検証結果を追加 |
| 1.3 | `start_react_app.sh`によるQdrant、Redis、FastAPI、Reactの1コマンド起動手順を追加 |
| 1.4 | Docker操作を起動スクリプトから分離。Qdrant・Redisは接続確認のみ行い、FastAPIとReactだけを起動する仕様へ変更 |
| 1.5 | 起動手順と使用例を`start_react_app.sh`へ統一し、手動の`uvicorn`／`npm run dev`手順を削除 |

## 付録: 依存関係図

```mermaid
flowchart LR
    Browser["Browser"] --> React["React 19 / Vite"]
    React --> Icons["lucide-react"]
    React --> REST["FastAPI REST"]
    React --> SSE["FastAPI SSE"]
    REST --> Orchestrator["GRACE Agent Support"]
    SSE --> Orchestrator
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class Browser,React,Icons,REST,SSE,Orchestrator default
```
