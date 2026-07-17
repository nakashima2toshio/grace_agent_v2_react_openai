# React実行結果表示・判定整合 改善TODO

**Version 1.0** | 最終更新: 2026-07-17

## 1. 目的

React版GRACE Supportで確認された次の矛盾を解消し、実行過程・最終判定・ユーザーへ提示する回答を一致させる。

- 2ステップのPlanに対して、失敗・成功・Step 3が混在して表示される
- `decision=escalate`なのに、採用されなかった回答本文と8件の出典が通常回答として表示される
- 通常質問が`escalate_to_human`のHITL承認待ちになる
- 出典8件に対してGroundedness 0%、判定可能主張0件となる
- Streamlit Agent ChatとReact GRACE Supportで実行経路と回答方針が異なる
- タイムラインが一部の実行状態を扱っていない

## 2. 改善方針

1. **最終結果と途中経過を分離する**: リトライ、フォールバック、リプランを最終ステップ結果と同列に表示しない。
2. **判定と表示を一致させる**: `answer`だけを回答として表示し、`escalate`時は不採用回答を通常表示しない。
3. **エスカレーションと副作用Actionを分離する**: 有人引継ぎ状態と、外部システムへの起票・返信実行を別契約にする。
4. **根拠本文を検証する**: URL文字列ではなく検索本文・スニペットに対してGroundednessを計算する。
5. **初期Planと現在Planを区別する**: リプランをAPIイベントとして公開する。
6. **比較可能な受入基準を作る**: 「住民票を取得したい。」を代表ケースにしてStreamlit版との期待差を明文化する。

## 3. 優先度別TODO一覧

| ID | 優先度 | 状態 | TODO | 主対象 | 完了条件 |
|---|:---:|:---:|---|---|---|
| RO-00 | P0 | DONE | React版の正解となる実行経路と回答方針を確定する | 仕様、Streamlit、GRACE Support | 業界特化Supportを維持し、一般FAQはAction承認へ変換しない方針に決定 |
| RO-01 | P0 | DONE | Executeの最終結果と試行履歴を分離する | `App.tsx::selectFinalSteps` | 最終結果には各論理ステップの最終状態が1件だけ表示される |
| RO-02 | P0 | DONE | `step_completed`を最終結果の一次情報にする | backend events、React | `executor_state`の重複yieldで結果行が増えない |
| RO-03 | P0 | DONE | `escalate`時に不採用回答を通常回答として表示しない | `App.tsx` | HUMAN ESCALATION領域に回答本文が通常表示されない |
| RO-04 | P0 | DONE | エスカレーション理由を構造化する | `SupportResult.escalation_reason`、API、UI | 根拠不足／矛盾／No-info／強制エスカレを区別して表示できる |
| RO-05 | P0 | DONE | `escalate_to_human`とHITL Actionを分離する | `AgentSupportService` | 単なる回答不能では承認待ちにならず、有人引継ぎ状態へ遷移する |
| RO-06 | P0 | DONE | `intent=None`でActionを作成しない | `AgentSupportService._proposed_action` | 意図不明の通常質問がAction承認待ちにならない |
| RO-07 | P0 | DONE | Groundednessへ根拠本文を渡す | `_collect_evidence_texts`、Verifier | URLではなく検索payloadのanswer/content/textで主張を検証する |
| RO-08 | P0 | DONE | Groundedness判定不能を0%と区別する | React metrics | `decided=0`は「判定不能」と表示される |
| RO-09 | P1 | DONE | リプランイベントを追加する | `forward_executor_event`、SSE | `replan_completed`で旧Plan、新Plan、理由、版を送信する |
| RO-10 | P1 | DONE | Reactに現在Planと版を表示する | `App.tsx` | 最新の`replan_completed.data.plan`をPLAN vNとして表示する |
| RO-11 | P1 | DONE | 動的Web・ask_userステップを識別可能にする | `step_completed.data.origin`、UI | planned／dynamic_web／dynamic_ask_user／replanを表示する |
| RO-12 | P1 | DONE | タイムラインの全状態を扱う | `WorkflowTimeline.tsx` | No-infoと全終端状態を表示し、未知状態でindex=-1を進捗判定に使わない |
| RO-13 | P1 | DONE | 使用業界プロファイルを常時表示する | result metrics | `run.request.vertical`を結果指標に表示する |
| RO-14 | P1 | DONE | デフォルト業界を未選択へ変更する | `App.tsx` | required selectで明示選択しない限り実行できない |
| RO-15 | P1 | DONE | 出典取得数と検証済み出典数を分離する | `SupportResult`、UI | `retrieved_source_count/verified_source_count`を表示する |
| RO-16 | P1 | DONE | 完了RunでもSSEイベントを復元する | React SSE effect、既存SSE API | terminal stateでも保存イベントを再購読してPlan／Stepを復元する |
| RO-17 | P1 | DONE | 実行中／確定済みの表示境界を明確にする | React | 確定結果は`step_completed`、確認待ちはHITL領域に限定する |
| RO-18 | P1 | DONE | backend回帰テストを追加する | pytest | escalate非Action、明示request Action、intent不明非Action、根拠本文抽出を検証する |
| RO-19 | P1 | DONE | Execute集計・escalate表示のReactテストを追加する | Vitest | 確定結果重複排除、回答非表示、判定不能表示を検証する |
| RO-20 | P1 | TODO | Streamlit／React比較試験を追加する | 実Qdrant、LLM、Web | 同一入力・同一設定で許容差を満たす |
| RO-21 | P2 | DONE | ステップ詳細を展開式で表示する | React UI | 途中の試行状態、エラー、実行時間をdetails内で確認できる |
| RO-22 | P2 | DONE | 長文回答の改行を保持する | React CSS | `white-space: pre-wrap`で段落・箇条書きの改行を保持する |
| RO-23 | P2 | TODO | 実行時間とタイムアウト理由を可視化する | event schema、UI | 30秒失敗がtimeout等の理由付きで表示される |
| RO-24 | P2 | DONE | 運用メトリクスを追加する | service、logging | decision、replan_count、判定不能、Action候補を構造化ログへ記録する |

### 3.1 実装契約一覧

各TODOの「改善する」を、次のコード変更へ固定する。

| ID | 変更ファイル | 変更シンボル | 変更前 | 変更後 | 検証テスト |
|---|---|---|---|---|---|
| RO-01/02 | `frontend/src/App.tsx` | `selectFinalSteps()` | 全`executor_state.data.step`を表示 | `step_completed`をstep_idで集約し最新1件を表示 | `selects only the latest completed result...` |
| RO-03 | `frontend/src/App.tsx` | 最終回答パネル | `decision`に関係なく`answer`を表示 | `decision=answer`だけ本文表示、escalateでは理由表示 | `renders escalation without presenting...` |
| RO-04 | `services/agent_support_schemas.py` | `EscalationReason`、`SupportResult.escalation_reason` | 理由フィールドなし | 6種類の理由コードをAPIで返す | service escalation test、React escalation test |
| RO-05/06 | `services/agent_support_service.py` | `_proposed_action()` | escalateまたはintent不明でもAction生成 | `decision=answer`かつintent=request/incidentだけAction候補化 | service 3分岐テスト |
| RO-07 | `agent_support_example.py` | `_collect_evidence_texts()` | URL・ファイル名をVerifierへ渡す | 検索payloadの本文だけをVerifierへ渡す | evidence抽出2テスト |
| RO-08 | `frontend/src/App.tsx` | Groundedness Metric | decided=0を0%表示 | decided=0を「判定不能」表示 | React escalation test |
| RO-09 | `agent_support_example.py` | `forward_executor_event()` | リプラン通知なし | Plan変化時に`replan_completed`を発行 | 追加するworkflow event test |
| RO-10 | `frontend/src/App.tsx` | `plan`、`planRevision` | 最初のplanだけ表示 | 最新planとPLAN vNを表示 | 追加するreplan component test |
| RO-12 | `WorkflowTimeline.tsx` | `steps`、`terminalStates` | 4状態が欠落 | No-infoと全終端状態を表示 | 追加する全状態parametrize test |
| RO-13/14 | `frontend/src/App.tsx` | `initial`、vertical select、metrics | SaaS固定、結果に非表示 | 未選択required、実行vertical表示 | form test、result test |

### 3.2 未完了TODOの具体的作業

| ID | 実施するコード変更 | 完了を証明する検証 |
|---|---|---|
| RO-20 | gov固定、Web ON、Action ON、dry-run ON、同一Qdrantデータで「住民票を取得したい。」を両UI実行する比較スクリプトを追加する | decision、主要回答項目、出典、Action有無の比較結果を保存 |
| RO-23 | Stepイベントへ`error_code`を追加し、timeout/tool_error/cancelledを分類する | 30秒timeout fixtureで理由が「タイムアウト」と表示される |

## 4. Phase別実施内容

### Phase 0: 正解仕様の固定

#### RO-00 React版の正解となる処理を確定する

現状のStreamlit「Agent Chat」とReact「GRACE Support」は同じ画面移植ではなく、異なる実行経路である。先に次のどちらを正解とするかを明文化する。

- **案A: 共通サービス化** — StreamlitとReactが同じAgent実行サービスを呼び、回答内容も原則一致させる。
- **案B: 用途分離** — Streamlitは一般Agent Chat、Reactは厳格な業界特化Supportとし、異なる判定を仕様として認める。

ユーザー提示のStreamlit結果を正解とする場合は、案Aを基本方針とする。ただし、Thoughtなど内部推論の逐語表示は行わず、Tool Call、検索結果、Reflection結果など公開可能な構造化イベントだけを扱う。

**受入条件**:

- 「住民票を取得したい。」の期待decision、回答方針、Web利用、Action有無が決まっている
- Streamlit／Reactで一致させる項目と、画面固有項目が表になっている
- 使用するverticalとQdrantコレクションが固定されている

### Phase 1: 誤表示と誤Actionの修正

#### RO-01／RO-02 Execute結果の正規化

`executor_state`は進捗用、`step_completed`は確定結果用と役割を分ける。確定結果は`logical_step_id`単位で最新1件を表示する。

必要なデータ:

| フィールド | 説明 |
|---|---|
| `logical_step_id` | ユーザーへ見せる論理ステップID |
| `attempt` | 試行回数 |
| `plan_revision` | Planの版番号 |
| `origin` | `planned`／`dynamic_web`／`fallback`／`replan` |
| `final` | この論理ステップの確定結果か |
| `error_code` | timeout、tool_error等の構造化理由 |

**受入条件**:

- Step 1が失敗後に成功した場合、最終結果は`Step 1 — success`の1行
- 試行履歴を開くと初回failedと再試行successを確認できる
- 同一SSEイベントの再送で行が重複しない

#### RO-03／RO-04 判定と回答表示の一致

`decision=escalate`では`answer`を通常回答として表示しない。バックエンドは`escalation_reason`を返す。

候補値:

- `insufficient_grounding`
- `contradiction`
- `no_information`
- `forced_policy`
- `identity_required`
- `system_error`

**受入条件**:

- `answer`判定だけが「回答」領域に表示される
- `escalate`では理由、次の行動、参照可能な出典だけが表示される
- 不採用の生成文を残す場合は管理者向け折り畳み領域とし、通常回答と明確に区別する

#### RO-05／RO-06 エスカレーションとActionの分離

有人引継ぎは判定結果であり、必ずしも副作用Actionではない。`create_ticket`、`send_reply`等の実行だけをHITL対象とする。

**受入条件**:

- FAQ質問が根拠不足になった場合、状態は`escalated`となり、承認画面を出さない
- ユーザーが起票・返信等を依頼し、意図が確認できた場合だけ`pending_confirmation`になる
- `intent=None`ではActionを作らない

### Phase 2: Groundednessの正当化

#### RO-07／RO-08／RO-15 根拠本文と表示指標の再設計

GroundednessVerifierへ、URLではなく回答生成に実際に使った本文を渡す。検証不能と不支持を区別する。

推奨表示:

```text
取得した出典        8件
本文検証可能な出典  8件
検証対象主張        12件
判定済み主張        10件
支持された主張       9件
Groundedness        90%
```

`groundedness_decided == 0`の場合:

```text
Groundedness: 判定不能
```

**受入条件**:

- 出典数だけで回答ゲートを通過しない
- 判定不能を0%として扱わない
- 各主要主張から根拠本文または出典へ辿れる

### Phase 3: Replan・動的ステップの可視化

#### RO-09／RO-10／RO-11

イベントを追加する。

```text
replan_started
replan_completed
dynamic_step_started
dynamic_step_completed
```

Reactでは次のように表示する。

```text
初期計画 v1: 2 steps
計画変更 v2: timeoutのためStep 2を再構成
現在計画 v2: 3 steps
```

**受入条件**:

- Plan表示とExecute結果のステップ集合が一致する
- Step 3が追加された理由を確認できる
- 動的Web検索を通常のPlan Stepと誤認しない

### Phase 4: 画面状態と入力改善

#### RO-12／RO-13／RO-14／RO-17

- タイムラインへ`no_info_check`、`action_executing`、`escalated`、`cancelled`、`failed`を追加する
- 実行中、確認待ち、最終結果を別表示にする
- 使用verticalをRunヘッダーと結果に表示する
- vertical初期値を未選択にするか、自動推定結果をユーザーに確認させる

**受入条件**:

- すべての`ExecutionState`で現在位置と終了状態が正しい
- `pending_confirmation`時に「処理完了」と表示しない
- 自治体質問をSaaS設定のまま無警告で実行しない

### Phase 5: SSE再接続

#### RO-16

ブラウザ標準EventSourceはSSEの`id:`を再接続時に利用できるが、現在のクライアントはイベント配列を画面内だけで保持し、Run履歴選択時には空にする。復元契約を明確にする。

**受入条件**:

- 再読込後もPlan、確定Step、リプラン履歴を復元できる
- イベントIDによる重複排除が維持される
- 確定済みRunのイベントも取得・表示できる

### Phase 6: テストと実比較

#### RO-18 Backend回帰テスト

最低限、次を固定する。

| ケース | 期待結果 |
|---|---|
| 自治体FAQ＋十分な根拠 | `answer`、Actionなし、出典あり |
| 自治体FAQ＋根拠不足 | `escalate`、承認待ちなし |
| 起票依頼＋確認済み意図 | `pending_confirmation` |
| `intent=None` | Actionなし |
| 判定可能主張0 | Groundedness判定不能 |

#### RO-19 Reactテスト

- 複数`executor_state`から確定結果が重複しない
- `step_completed`再送が重複しない
- リプラン後の現在Planを表示する
- `decision=escalate`で回答本文を通常表示しない
- `groundedness_decided=0`で「判定不能」を表示する
- 全`ExecutionState`のタイムライン表示を検証する

#### RO-20 Streamlit／React比較試験

同じ入力だけでなく、次の条件を固定する。

- LLMモデル
- vertical
- Qdrantコレクションとデータ版
- Web検索ON/OFF
- Action ON/OFF
- dry-run
- プロンプト
- 実行日時

比較項目:

- 最終decision
- 回答の主要項目
- 使用した検索経路
- 出典URL
- Action有無
- エスカレーション理由

## 5. 推奨実装順序

```text
RO-00
  → RO-03, RO-04, RO-05, RO-06
  → RO-01, RO-02
  → RO-07, RO-08, RO-15
  → RO-09, RO-10, RO-11
  → RO-12, RO-13, RO-14, RO-17
  → RO-16
  → RO-18, RO-19
  → RO-20
  → RO-21〜RO-24
```

最初に表示とActionの安全上の矛盾を直し、その後にGroundedness、リプラン表示、比較試験へ進む。

## 6. 完了判定

以下をすべて満たした場合に本改善を完了とする。

- [ ] 最終ステップ結果に同じ論理Stepが重複しない
- [ ] 途中のfailedと最終successを区別できる
- [ ] 表示Planと実行された現在Planが一致する
- [ ] `escalate`時に不採用回答を通常回答として表示しない
- [ ] 通常FAQが`escalate_to_human`承認待ちにならない
- [ ] Groundednessが根拠本文を使って計算される
- [ ] 判定不能と0%を区別する
- [ ] 全実行状態をタイムラインで正しく表現する
- [ ] verticalを実行結果から確認できる
- [ ] 代表ケースのbackend／Reactテストが成功する
- [ ] 同一条件のStreamlit／React比較結果が仕様の許容範囲内である

## 7. 変更履歴

| バージョン | 日付 | 変更内容 |
|---|---|---|
| 1.0 | 2026-07-17 | React実行結果の調査結果をP0〜P2の改善TODO、受入条件、テスト計画へ整理 |
| 1.1 | 2026-07-17 | TODOをファイル・関数・データ契約・検証テスト単位へ具体化。RO-00〜RO-19、RO-21、RO-22、RO-24を実装済みに更新 |
