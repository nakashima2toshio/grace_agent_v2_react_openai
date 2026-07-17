# App.tsx - GRACE Support メイン画面 ドキュメント

**Version 1.0** | 最終更新: 2026-07-17

---

## 目次

1. [概要](#概要)
2. [アーキテクチャ構成図](#1-アーキテクチャ構成図)
3. [モジュール構成図](#2-モジュール構成図)
4. [クラス・関数一覧表](#3-クラス関数一覧表)
5. [クラス・関数 IPO詳細](#4-クラス関数-ipo詳細)
6. [設定・定数](#5-設定定数)
7. [使用例](#6-使用例)
8. [エクスポート](#7-エクスポート)
9. [変更履歴](#8-変更履歴)
10. [付録: 依存関係図](#付録-依存関係図)

---

## 概要

`App.tsx` は、GRACE Support の問い合わせ入力、非同期実行の監視、検証結果の表示、実行履歴の再表示、および Human-in-the-Loop（HITL）承認を一画面にまとめる React モジュールです。バックエンドとの通信は `agentSupportClient` に委譲し、Server-Sent Events（SSE）で実行イベントを受信します。

### 主な責務

- 問い合わせ、業界プロファイル、実行オプションを入力する
- エージェント実行を作成し、SSEイベントと最新状態を同期する
- Plan、Execute、Groundedness、回答ゲート、Web検証、Actionの進捗と結果を表示する
- HITLの承認、却下、Action引数修正を受け付ける
- 実行IDをブラウザに保存し、画面再読み込み後に実行を復元する
- 過去の実行を取得し、選択した実行を再表示する

### 各責務対応のモジュール

| # | 責務 | 対応モジュール | 説明 |
|---|------|--------------|------|
| 1 | 問い合わせ条件の入力 | `App.tsx` | 制御されたフォームとEC向け本人確認入力を描画 |
| 2 | 実行作成と状態同期 | `App.tsx`, `api/agentSupportClient.ts` | REST APIとSSE購読を組み合わせて同期 |
| 3 | 進捗と結果の表示 | `App.tsx`, `components/WorkflowTimeline.tsx` | 段階表示、指標、計画、実行結果、回答を描画 |
| 4 | HITL判断 | `App.tsx`, `api/agentSupportClient.ts` | approve/reject/modifyを確認APIへ送信 |
| 5 | 実行復元 | `App.tsx` | `localStorage` の実行IDを利用 |
| 6 | 実行履歴の再表示 | `App.tsx`, `api/agentSupportClient.ts` | 履歴取得と選択時の状態切替を実行 |

### 主要機能一覧

| 機能 | 説明 |
|------|------|
| `App()` | メイン画面全体と状態管理を提供する既定エクスポートコンポーネント |
| `submit()` | フォーム入力から新規実行を作成 |
| `loadHistory()` | 実行履歴を取得 |
| `decide()` | 承認または却下を送信 |
| `modify()` | 編集したAction引数をJSONとして検証し、修正判断を送信 |
| `Title()` | 番号、見出し、補足文を表示 |
| `Metric()` | 結果指標のラベルと値を表示 |

---

## 1. アーキテクチャ構成図

### 1.1 システム全体構成

```mermaid
flowchart TB
    subgraph CLIENT["ブラウザ・利用者層"]
        USER["サポート担当者"]
        STORAGE["localStorage"]
    end
    subgraph UI["React UI層"]
        APP["App"]
        TITLE["Title"]
        METRIC["Metric"]
        TIMELINE["WorkflowTimeline"]
    end
    subgraph SERVICE["通信・バックエンド層"]
        CLIENT_API["agentSupportClient"]
        REST["Agent Support REST API"]
        SSE["Agent Support SSE"]
    end
    USER --> APP
    APP <--> STORAGE
    APP --> TITLE
    APP --> METRIC
    APP --> TIMELINE
    APP --> CLIENT_API
    CLIENT_API --> REST
    CLIENT_API --> SSE
    SSE --> APP
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class USER,STORAGE,APP,TITLE,METRIC,TIMELINE,CLIENT_API,REST,SSE default
style CLIENT fill:#1a1a1a,stroke:#fff,color:#fff
style UI fill:#1a1a1a,stroke:#fff,color:#fff
style SERVICE fill:#1a1a1a,stroke:#fff,color:#fff
```

### 1.2 データフロー

1. 利用者が問い合わせと業界プロファイル、Web検証・Action・Dry runの設定を入力します。
2. `submit()` が実行を作成し、返された `run_id` を `localStorage` とReact stateへ保存します。
3. 実行中はSSEを購読し、重複しないイベントを `events` に追加します。
4. イベント受信ごとに最新の `RunRecord` を取得し、進捗・Plan・Execute結果を再描画します。
5. 確認待ちでは利用者の approve/reject/modify をバックエンドへ送ります。
6. 完了後は検証指標、回答または有人エスカレーション、出典を表示します。

### 1.3 画面操作シーケンス

```mermaid
%%{ init: { "theme": "base", "themeVariables": {
  "background": "#000000", "mainBkg": "#000000",
  "textColor": "#ffffff", "lineColor": "#ffffff",
  "actorBkg": "#000000", "actorTextColor": "#ffffff",
  "actorLineColor": "#ffffff", "noteBkgColor": "#000000",
  "noteTextColor": "#ffffff", "noteBorderColor": "#ffffff" } } }%%
sequenceDiagram
    actor User as 利用者
    participant App as App
    participant Client as agentSupportClient
    participant API as Backend API
    User->>App: 問い合わせを送信
    App->>Client: createRun(form)
    Client->>API: POST runs
    API-->>App: RunRecord
    App->>Client: events(run_id)
    Client->>API: SSE接続
    API-->>App: RunEvent
    App->>Client: getRun(run_id)
    Client->>API: GET run
    API-->>App: 最新RunRecord
    opt 確認が必要
        User->>App: 承認・却下・修正
        App->>Client: confirm(run, decision, action)
        Client->>API: POST confirmations
        API-->>App: ConfirmationResponse
    end
```

---

## 2. モジュール構成図

### 2.1 内部モジュール構成

```mermaid
flowchart LR
    subgraph STATE["状態・派生値"]
        FORM["form"]
        RUN["run"]
        EVENTS["events"]
        HISTORY["history"]
        VIEW["busy・plan・executed"]
    end
    subgraph EFFECTS["副作用"]
        RESTORE["保存実行の復元"]
        STREAM["SSE購読"]
        ARGS["Action引数同期"]
    end
    subgraph HANDLERS["イベントハンドラ"]
        SUBMIT["submit"]
        LOAD["loadHistory"]
        DECIDE["decide"]
        MODIFY["modify"]
    end
    subgraph RENDER["表示関数"]
        APP["App"]
        TITLE["Title"]
        METRIC["Metric"]
    end
    STATE --> APP
    EFFECTS --> STATE
    HANDLERS --> STATE
    APP --> HANDLERS
    APP --> TITLE
    APP --> METRIC
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class FORM,RUN,EVENTS,HISTORY,VIEW,RESTORE,STREAM,ARGS,SUBMIT,LOAD,DECIDE,MODIFY,APP,TITLE,METRIC default
style STATE fill:#1a1a1a,stroke:#fff,color:#fff
style EFFECTS fill:#1a1a1a,stroke:#fff,color:#fff
style HANDLERS fill:#1a1a1a,stroke:#fff,color:#fff
style RENDER fill:#1a1a1a,stroke:#fff,color:#fff
```

### 2.2 外部依存関係

| ライブラリ | 用途 |
|-----------|------|
| `react` | state、effect、memo化、フォームイベント、JSX描画 |
| `lucide-react` | 状態、操作、警告、出典を表すSVGアイコン |
| Web `localStorage` | 最後に表示した実行IDの永続化 |

### 2.3 内部依存モジュール

| モジュール | 用途 |
|-----------|------|
| `./api/agentSupportClient` | REST通信、確認送信、SSE購読 |
| `./components/WorkflowTimeline` | 実行段階のタイムライン表示 |
| `./types/agentSupport` | APIデータ型の提供 |
| `./styles.css`, `./details.css` | 画面全体と詳細領域のスタイル |

---

## 3. クラス・関数一覧表

### 3.1 クラス一覧

クラス定義はありません。React関数コンポーネントと、その内部ハンドラで構成されます。

### 3.2 関数一覧（カテゴリ別）

#### Reactコンポーネント

| 関数名 | 概要 |
|-------|------|
| `App()` | 画面、状態、副作用、操作を統括 |
| `Title({ n, title, sub })` | セクション見出しを描画 |
| `Metric({ k, v })` | 指標カードを描画 |

#### `App` 内部ハンドラ

| 関数名 | 概要 |
|-------|------|
| `submit(event)` | 実行作成と実行ID保存 |
| `loadHistory()` | 実行履歴の読込み |
| `decide(decision)` | approve/reject判断の送信 |
| `modify()` | 編集済みAction引数によるmodify判断の送信 |

### 3.3 state・派生値・effect一覧

| 種別 | 名前 | 型・依存 | 役割 |
|------|------|----------|------|
| state | `form` | `RunRequest` | 入力フォームの値 |
| state | `run` | `RunRecord \| null` | 現在表示中の実行 |
| state | `history` | `RunRecord[]` | 読み込んだ実行履歴 |
| state | `events` | `RunEvent[]` | SSEで受信した実行イベント |
| state | `error` | `string` | トーストに表示するエラー |
| state | `editedArgs` | `string` | 編集中のAction引数JSON |
| 派生値 | `busy` | `run` | 終端状態以外なら `true` |
| memo | `plan` | `events` | 最新配列内の最初の `plan_completed` の計画 |
| memo | `executed` | `events` | `executor_state` のステップ一覧 |
| effect | 実行復元 | 初回のみ | 保存済み `run_id` の実行を取得 |
| effect | SSE同期 | `run?.run_id`, `busy` | 実行中だけイベントを購読 |
| effect | Action引数同期 | `run?.pending_confirmation` | 確認対象の引数を整形JSONへ変換 |

---

## 4. クラス・関数 IPO詳細

### 4.1 Reactコンポーネント

#### `App`

**概要**: GRACE Support画面の全状態を保持し、入力、実行監視、検証結果、HITL操作を統括します。

```typescript
export default function App(): JSX.Element
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| なし | - | - | propsは受け取りません |

| 項目 | 内容 |
|------|------|
| **Input** | 利用者のフォーム操作、SSEイベント、REST API応答、`localStorage` の実行ID |
| **Process** | 1. stateと派生値を構成<br>2. 保存実行とSSEを同期<br>3. ハンドラでAPI操作<br>4. 実行状態に応じて入力・進捗・確認・回答を条件描画 |
| **Output** | `JSX.Element`: GRACE Supportメイン画面 |

**戻り値例**:

```tsx
<main>
  <header>...</header>
  <section className="workspace">...</section>
  <section className="results">...</section>
</main>
```

```tsx
// 使用例
import App from './App'

root.render(<App />)
// 出力: 問い合わせ入力と実行結果を含むメイン画面
```

#### `Title`

**概要**: セクション番号、タイトル、補足文を共通レイアウトで描画します。

```typescript
function Title(props: { n: string; title: string; sub: string }): JSX.Element
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `n` | `string` | - | セクション番号 |
| `title` | `string` | - | 見出し |
| `sub` | `string` | - | 補足文 |

| 項目 | 内容 |
|------|------|
| **Input** | `n`, `title`, `sub` |
| **Process** | 値を `.section-title` 内の番号、`h2`、`p` に割り当てる |
| **Output** | `JSX.Element`: セクション見出し |

**戻り値例**:

```tsx
<div className="section-title"><b>01</b><div><h2>問い合わせ</h2><p>内容を指定</p></div></div>
```

```tsx
// 使用例
<Title n="01" title="問い合わせ" sub="内容と業界プロファイルを指定してください" />
// 出力: 番号付きセクション見出し
```

#### `Metric`

**概要**: 検証結果の単一指標をラベルと値の組で描画します。

```typescript
function Metric(props: { k: string; v: string }): JSX.Element
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `k` | `string` | - | 指標ラベル |
| `v` | `string` | - | 表示値 |

| 項目 | 内容 |
|------|------|
| **Input** | `k`, `v` |
| **Process** | ラベルを `small`、値を `strong` としてカードへ配置 |
| **Output** | `JSX.Element`: 指標カード |

**戻り値例**:

```tsx
<article><small>Groundedness</small><strong>92%</strong></article>
```

```tsx
// 使用例
<Metric k="Groundedness" v="92%" />
// 出力: Groundedness指標カード
```

### 4.2 イベントハンドラ

#### `submit`

**概要**: フォーム送信を止めて表示状態を初期化し、新規実行を作成します。

```typescript
async function submit(event: FormEvent): Promise<void>
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `event` | `FormEvent` | - | フォーム送信イベント |

| 項目 | 内容 |
|------|------|
| **Input** | `event`, 現在の `form` |
| **Process** | 1. 既定送信を抑止<br>2. エラーとイベントを消去<br>3. `createRun(form)` を実行<br>4. `run_id` を保存して `run` を更新<br>5. 失敗時は例外メッセージを設定 |
| **Output** | `Promise<void>`: state更新のみ |

**戻り値例**:

```typescript
undefined
```

```tsx
// 使用例
<form onSubmit={submit}>...</form>
// 出力: 実行作成後にrun stateが更新される
```

#### `loadHistory`

**概要**: 全実行履歴を取得して履歴stateへ格納します。

```typescript
async function loadHistory(): Promise<void>
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| なし | - | - | 入力パラメータなし |

| 項目 | 内容 |
|------|------|
| **Input** | なし |
| **Process** | `listRuns()` を呼び、成功時は `history`、失敗時は `error` を更新 |
| **Output** | `Promise<void>`: state更新のみ |

**戻り値例**:

```typescript
undefined
```

```tsx
// 使用例
<button onClick={loadHistory}>実行履歴を表示</button>
// 出力: 履歴リストが表示される
```

#### `decide`

**概要**: 現在の確認待ち実行に対し、承認または却下を送信します。

```typescript
async function decide(decision: 'approve' | 'reject'): Promise<void>
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `decision` | `'approve' \| 'reject'` | - | HITL判断 |

| 項目 | 内容 |
|------|------|
| **Input** | `decision`, 現在の `run` |
| **Process** | 1. `run` がなければ終了<br>2. `confirm(run, decision)` を実行<br>3. 応答内の実行を `run` に設定<br>4. 失敗時はエラーを設定 |
| **Output** | `Promise<void>`: state更新のみ |

**戻り値例**:

```typescript
undefined
```

```tsx
// 使用例
<button onClick={() => decide('approve')}>承認して実行</button>
// 出力: 承認結果を反映したrunへ更新
```

#### `modify`

**概要**: テキストエリアのJSONをAction引数として解析し、修正済みActionを確認APIへ送信します。

```typescript
async function modify(): Promise<void>
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| なし | - | - | `run.pending_confirmation` と `editedArgs` を参照 |

| 項目 | 内容 |
|------|------|
| **Input** | 確認待ちAction、`editedArgs` のJSON文字列 |
| **Process** | 1. 確認待ちでなければ終了<br>2. JSONを `Record<string, unknown>` に解析<br>3. 元Actionを複製し引数を置換<br>4. modify判断を送信<br>5. JSON構文エラーは専用の日本語メッセージへ変換 |
| **Output** | `Promise<void>`: state更新のみ |

**戻り値例**:

```typescript
undefined
```

```tsx
// 使用例
<button onClick={modify}>修正を依頼</button>
// 出力: 編集済みActionを含む確認結果がrunへ反映される
```

### 4.3 副作用（`useEffect`）

#### 保存済み実行の復元effect

**概要**: 初回マウント時に保存済み実行IDを読み、該当実行を復元します。取得失敗時は無効なIDを削除します。

```typescript
useEffect((): void => { /* restore run */ }, [])
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| 依存配列 | `[]` | - | 初回マウント時のみ実行 |

| 項目 | 内容 |
|------|------|
| **Input** | `localStorage['grace-support-run-id']` |
| **Process** | IDがあれば `getRun()` を実行し、失敗時は保存値を削除 |
| **Output** | `void`: 非同期処理により `run` を更新 |

**戻り値例**:

```typescript
undefined
```

```typescript
// 使用例: Appの初回マウント時にReactが自動実行
// 出力: 保存済み実行が画面へ復元される
```

#### SSE同期effect

**概要**: 実行中だけSSEを購読し、イベントをIDで重複排除しながら追加し、実行状態も再取得します。

```typescript
useEffect((): void | (() => void) => { /* subscribe events */ }, [run?.run_id, busy])
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `run?.run_id` | `string \| undefined` | - | 購読対象実行 |
| `busy` | `boolean` | - | 購読可否 |

| 項目 | 内容 |
|------|------|
| **Input** | 実行ID、実行中フラグ、SSEイベント |
| **Process** | 1. 実行中でなければ終了<br>2. `events()` で購読<br>3. イベントIDを重複排除<br>4. イベント・エラー時に最新実行を取得<br>5. cleanupでSSEを閉じる |
| **Output** | `void \| (() => void)`: 未購読または購読解除関数 |

**戻り値例**:

```typescript
() => source.close()
```

```typescript
// 使用例: run_idまたはbusyの変更時にReactが自動実行
// 出力: eventsとrunが継続的に同期される
```

#### Action引数同期effect

**概要**: 確認待ちActionが更新されたとき、その引数を2スペースインデントのJSON文字列へ変換します。

```typescript
useEffect((): void => { /* format action args */ }, [run?.pending_confirmation])
```

| パラメータ | 型 | デフォルト | 説明 |
|------------|----|-----------|------|
| `run?.pending_confirmation` | `PendingConfirmation \| undefined` | - | 現在の確認要求 |

| 項目 | 内容 |
|------|------|
| **Input** | `pending_confirmation.action.args` |
| **Process** | 確認要求があれば `JSON.stringify(args, null, 2)` を実行 |
| **Output** | `void`: `editedArgs` を更新 |

**戻り値例**:

```json
{
  "ticket_id": "T-001"
}
```

```typescript
// 使用例: pending_confirmationの受信時にReactが自動実行
// 出力: Action引数テキストエリアへ整形JSONを設定
```

---

## 5. 設定・定数

### 5.1 `initial`

初期フォーム値です。

```typescript
const initial: RunRequest = {
  query: '',
  vertical: 'saas',
  use_web: true,
  do_action: true,
  dry_run: true,
}
```

| キー | デフォルト値 | 説明 |
|-----|-------------|------|
| `query` | `''` | 問い合わせ本文 |
| `vertical` | `'saas'` | 初期業界プロファイル |
| `use_web` | `true` | Web相互検証を有効化 |
| `do_action` | `true` | Action候補生成を有効化 |
| `dry_run` | `true` | Dry runを有効化 |

### 5.2 画面内ローカル型

| 型 | 用途 |
|----|------|
| `PlanData` | `plan_completed` イベント内の計画表示 |
| `StepData` | `executor_state` イベント内のステップ表示 |

### 5.3 終端状態

`completed`、`escalated`、`cancelled`、`failed` を終端状態として扱います。いずれかに達すると `busy` は `false` となり、SSE購読を停止し、「新しい問い合わせ」を表示します。

---

## 6. 使用例

### 6.1 基本的なワークフロー

```tsx
// 使用例
// 1. 問い合わせと業界を入力
// 2. 必要な実行オプションを選択
// 3. 「実行を開始」を押す
// 4. タイムラインとPlan・Execute結果を確認
// 5. 確認要求があればAction引数を確認して承認・却下・修正
// 6. 回答、検証指標、出典を確認
```

### 6.2 実行復元と履歴切替

```typescript
// 使用例
// ブラウザ再読込み時は保存されたrun_idから実行を復元する。
// 「実行履歴を表示」で履歴を取得し、項目を選ぶとrunを切り替える。
// 履歴選択時にはeventsを空にするため、過去イベント詳細は自動再取得されない。
```

> 📝 **注意**: 実装上、SSE購読の `events` は実行中に受け取ったイベントだけを保持します。履歴から終端済み実行を選択した場合、`RunRecord` の結果は表示されますが、過去のPlan/Executeイベントは再取得しません。

---

## 7. エクスポート

本モジュールに `__all__` 相当の明示的エクスポート一覧はありません。

```typescript
export default App
```

`Title`、`Metric`、内部ハンドラ、ローカル型はモジュール外へエクスポートされません。

---

## 8. 変更履歴

| バージョン | 変更内容 |
|-----------|---------|
| 1.0 | `App.tsx` の画面、state、effect、ハンドラ、HITL操作を実コードに基づき初版文書化 |

---

## 付録: 依存関係図

```mermaid
flowchart LR
    APP["App.tsx"]
    subgraph EXTERNAL["外部ライブラリ・ブラウザAPI"]
        REACT["react"]
        ICONS["lucide-react"]
        LOCAL["localStorage"]
    end
    subgraph INTERNAL["内部モジュール"]
        CLIENT["api/agentSupportClient"]
        TIMELINE["components/WorkflowTimeline"]
        TYPES["types/agentSupport"]
        CSS1["styles.css"]
        CSS2["details.css"]
    end
    APP --> REACT
    APP --> ICONS
    APP --> LOCAL
    APP --> CLIENT
    APP --> TIMELINE
    APP --> TYPES
    APP --> CSS1
    APP --> CSS2
classDef default fill:#000,stroke:#fff,color:#fff
classDef subgraphStyle fill:#1a1a1a,stroke:#fff,color:#fff
class APP,REACT,ICONS,LOCAL,CLIENT,TIMELINE,TYPES,CSS1,CSS2 default
style EXTERNAL fill:#1a1a1a,stroke:#fff,color:#fff
style INTERNAL fill:#1a1a1a,stroke:#fff,color:#fff
```
