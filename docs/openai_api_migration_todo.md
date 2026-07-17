# OpenAI API 全面移行 TODO

**Version 1.3** | 最終更新: 2026-07-17

## 1. 目的と対象

現在の `agent_support_example.py` と関連処理には、Anthropic LLM、Gemini Embedding、SerpAPI／DuckDuckGo Web検索が混在している。これを `OPENAI_API_KEY` とOpenAI APIへ統一する。既存のGRACEコア、React、FastAPI、HITL、Redis、ローカルQdrantは再利用する。

| 領域 | 現状 | 移行後 |
|---|---|---|
| 通常生成 | Anthropic Messages API | OpenAI Responses API `responses.create()` |
| 構造化出力 | 手動JSON化／旧Chat Completions | `responses.parse()`＋Pydantic |
| ReAct／Tool Use | Anthropic tool block | Responses API function calling |
| Embedding | Gemini `gemini-embedding-001` | OpenAI `text-embedding-3-large`、3072次元 |
| Web検索 | SerpAPI／DuckDuckGo／Google CSE | Responses API `web_search` tool |
| AI認証 | Anthropic／Google等 | `OPENAI_API_KEY`のみ |

Qdrant、Redis、FastAPI、React、Action webhookはOpenAIの代替対象ではないため維持する。OpenWeather等、GRACE Supportと無関係なAPIは対象外とする。

## 2. 調査結果

- `agent_support_example.py` は `ANTHROPIC_API_KEY`、Claude軽量モデル、`*_anthropic` collectionを固定している。
- `grace/config.py` はLLM=`anthropic`、Embedding=`gemini`を既定とする。
- `grace/llm_compat.py` はAnthropic adapterへフォールバックする。
- `qa_generation/` の生成・EmbeddingはOpenAIへ移行済み。
- `chunking/` とCeleryのQ/A生成経路はOpenAIへ移行済み。
- `qa_qdrant/make_qa*.py` と登録用EmbeddingはOpenAIへ移行済み。
- `agent_main.py`、`services/agent_service.py`、`services/qa_service.py`、`chunking/async_api_client.py`、`eval/run_eval.py`、Streamlit UIにもAnthropic固定呼び出しが残る。
- 既存 `OpenAIClient` はChat Completions中心で、GRACE用Responses API互換とfunction callingが不足する。

## 3. 重要な移行判断

### Qdrantデータは既存OpenAI collectionを利用する

Qdrantのコレクションとデータはユーザーが手動管理する。Codexおよびアプリケーションによるコレクションの作成・再作成・登録・追加登録・更新・削除は**絶対禁止**とする。データが存在しない場合も自動作成・自動登録せず、処理を安全に停止して「手動作成が必要」と通知する。

OpenAI APIでEmbedding済みの手動管理collectionを参照専用で利用する。業種別の参照先は `gov_faq_ollama`、`saas_api_ollama`、`saas_docs_ollama`、`ec_faq_ollama` とし、汎用データでは `cc_news_2per_ollama` 等を利用できる。名前に旧provider名が含まれていても、実ベクトルはOpenAI `text-embedding-3-large`・3072次元であることを検索前に確認する。移行対象は、アプリ側のquery embedding、collection選択、存在・件数・次元の読み取り確認、検索処理に限定する。`create_collection`、`recreate_collection`、`upsert`、`delete`、登録CLIの実行は行わない。

2026-07-17 に `uv run python -m qa_qdrant.command.list_collections --detail` で確認した時点では、`cc_news_2per_openai` は3072次元・Cosine・greenだが `points=0` だった。コード移行はこのcollection名を前提に進めるが、実検索スモークテストはユーザーによる手動登録後に行う。0件の場合、Codex側では変更せず、手動対応待ちとして報告する。

### モデル文字列を一元化する

通常LLMは `config.ModelConfig.DEFAULT_MODEL`、軽量処理は新設する `ModelConfig.LIGHT_MODEL` を参照し、各ファイルへ直書きしない。モデル名の変換表は作らない。

初期案は通常モデル `gpt-5-mini`、軽量分類 `gpt-5-nano`、Embedding `text-embedding-3-large` 3072次元とする。実装時にAPIで利用可能性を確認し、失敗時に別モデルへ勝手に置換しない。

## 4. TODO

状態は `TODO`／`DOING`／`BLOCKED`／`DONE` を使用する。

### Phase O0: 契約・基準

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O0-01 | P0 | DONE | Support／QA／Qdrant／composeを調査 | provider、key、model、データ経路を特定 |
| O0-02 | P0 | DONE | 移行前テスト基準を固定 | pytest=`631 passed, 19 skipped`、React 6 tests／lint／typecheck／build成功 |
| O0-03 | P0 | DOING | OpenAI認証・モデル利用可否を確認 | 値を出さず`OPENAI_API_KEY=configured`を確認済み。実API確認は未実施 |

### Phase O1: 設定・認証

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O1-01 | P0 | DONE | `ModelConfig`をOpenAIへ変更 | DEFAULT／LIGHT／料金／limitをOpenAI化 |
| O1-02 | P0 | DONE | `grace.config`のLLM／EmbeddingをOpenAI化 | provider、model、dimensionsが統一 |
| O1-03 | P0 | DOING | APIキーガードを変更 | Support／API readinessは変更済み。残る実行経路を順次変更 |
| O1-04 | P1 | TODO | readiness、README、env例を更新 | Anthropic／Googleを必須表示しない |
| O1-05 | P0 | DONE | `config.py`／`config.yml`をOpenAI化 | LLM／Embedding／provider／fallback既定をOpenAIへ統一 |

### Phase O2: OpenAIクライアント

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O2-01 | P0 | DONE | `OpenAIClient.generate_content`をResponsesへ移行 | `responses.create()`を使用 |
| O2-02 | P0 | DONE | 構造化出力をResponses parseへ移行 | Pydantic結果とusageを返す |
| O2-03 | P0 | DONE | OpenAI function callingを実装 | ReAct tool call／output／継続応答をResponses形式へ変換 |
| O2-04 | P0 | DONE | `grace.llm_compat`にOpenAI adapterを実装 | GRACE呼び出し形を保ちOpenAIへ接続 |
| O2-05 | P0 | DONE | token上限／temperatureを正規化 | `max_tokens`を`max_output_tokens`へ変換し、GPT-5へtemperatureを送らない |
| O2-06 | P1 | TODO | Anthropic専用変換を実行経路から除去 | Anthropic tool block参照がゼロ |

### Phase O3: GRACE・サービス呼び出し元

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O3-01 | P0 | TODO | `agent_support_example.py`をOpenAI化 | Plan〜ActionがOpenAIだけで動く |
| O3-02 | P0 | TODO | intent／no-infoモデルを一元化 | Claude文字列を除去 |
| O3-03 | P0 | TODO | planner／executor／confidence／toolsを検証 | 全LLM生成がOpenAI adapterを通る |
| O3-04 | P0 | TODO | agent／service／UIの固定factoryを移行 | `create_llm_client("anthropic")`が実行コードからゼロ |
| O3-05 | P1 | TODO | eval judgeをOpenAI化 | 評価も同じproviderを使用 |

### Phase O4: `qa_generation/`

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O4-01 | P0 | DONE | `SmartQAGenerator`をResponses parseへ変更 | SmartQAResultをOpenAI Responses parseで型付き生成 |
| O4-02 | P0 | DONE | pipeline／semanticをOpenAI化 | LLM／Embedding既定をOpenAIへ変更 |
| O4-03 | P0 | DONE | async／Celery経路をOpenAI化 | workerもOPENAI_API_KEYだけで起動 |
| O4-04 | P1 | TODO | usage・失敗契約を回帰確認 | token集計、空結果、successを維持 |

### Phase O5: `qa_qdrant/`・Qdrant

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O5-01 | P0 | DONE | OpenAI Embeddingを3072次元へ統一 | `text-embedding-3-large`を使用 |
| O5-02 | P0 | DONE | collection model判定をOpenAIへ修正 | 3072次元を`text-embedding-3-large`として解決 |
| O5-03 | P0 | DONE | 検索query EmbeddingをOpenAIへ変更 | OpenAI 3072次元で検索し、Qdrantへ書き込まない |
| O5-04 | P0 | DONE | Qdrant参照専用ガードを実装 | Support実行経路からcreate／recreate／upsert／deleteを呼び出せない |
| O5-05 | P0 | DONE | collection不足時の安全停止を実装 | 未作成・0件・次元不一致を通知し、自動作成・自動登録しない |
| O5-06 | P0 | DONE | 利用対象collectionを確定 | 手動管理する業種別collectionと汎用collectionを確定 |
| O5-07 | P0 | DONE | Supportの検索スコープを既存OpenAI collectionへ切替 | 業種別collectionを選択し、存在しないcollectionへフォールバックしない |
| O5-08 | P1 | TODO | 実データ件数を読み取り確認 | 0件なら手動作成待ちを報告するだけで、Qdrantを変更しない |
| O5-09 | P0 | DONE | Q/A作成・登録CLIをOpenAI化 | LLMと登録EmbeddingをOpenAIへ固定し、旧providerを拒否 |

### Phase O6: Web検索

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O6-01 | P0 | TODO | OpenAI Web Search adapterを追加 | Responses APIから結果とURLを取得 |
| O6-02 | P0 | TODO | GRACE WebSearchToolを接続 | SerpAPI／Google CSEキー不要 |
| O6-03 | P1 | TODO | citation・失敗分岐を維持 | URL、agreement、no-info／escalateを保持 |

### Phase O7: テスト・実移行

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O7-01 | P0 | DONE | OpenAI create／parse／function calling単体テスト | Responses create／parse／function call／function outputをmock検証 |
| O7-02 | P0 | TODO | provider禁止回帰テスト | 実行コードのAnthropic／Gemini生成を検出 |
| O7-03 | P0 | DONE | Qdrant参照専用・model解決テスト | provider／model／dimsを検証し、書き込みAPIが呼ばれないことを確認 |
| O7-04 | P0 | TODO | Support全分岐とReact／FastAPI回帰 | answer、Web、no-info、Action、HITLが成功 |
| O7-05 | P0 | DOING | 全pytest／ruff／frontend品質確認 | pytest=`637 passed, 19 skipped`、frontend成功。全体ruffは最終段階で実施 |
| O7-06 | P1 | TODO | 実OpenAIスモークテスト | 送信承認後、代表結果をJSON保存 |
| O7-07 | P1 | TODO | CLIとReactを比較 | decision、action、citationsが一致 |

### Phase O8: 文書・依存整理

| ID | 優先度 | 状態 | TODO | 完了条件 |
|---|---|---|---|---|
| O8-01 | P1 | TODO | README／GRACE／QA／Qdrant文書を更新 | OpenAIを現行仕様として記載 |
| O8-02 | P1 | TODO | React provider表示を更新 | OpenAI LLM／Embedding／Webを表示 |
| O8-03 | P1 | TODO | 未使用SDKを確認後に整理 | 実行参照ゼロをテストしてから削除 |
| O8-04 | P1 | TODO | 最終grep監査 | Claudeモデル、Anthropic／Gemini固定値が実行コードに残らない |

## 5. 実装順序と完了条件

推奨順序は `O0 → O1 → O2 → O3 → O4 → O5-01〜O5-05・O5-07 → O7単体テスト → O6 → O5-08 → O7実試験 → O8` とする。Qdrantの作成・再作成・登録・追加登録・更新・削除は一切実施しない。

完了条件は、GRACE Support、QA生成、Embedding、Web検索が `OPENAI_API_KEY` だけで動き、`*_openai` collectionをOpenAI query vectorで検索でき、React／FastAPI／HITLを含む全品質チェックが成功することである。

## 6. 参照

- [OpenAI Models](https://developers.openai.com/api/docs/models)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [OpenAI Embeddings API](https://platform.openai.com/docs/api-reference/embeddings)

## 7. 変更履歴

| Version | 日付 | 内容 |
|---|---|---|
| 1.2 | 2026-07-17 | Qdrantを完全な手動管理・参照専用とし、作成／登録／更新／削除を絶対禁止。0件時は自動処理せず手動対応待ちとする方針へ修正 |
| 1.1 | 2026-07-17 | Qdrantデータ再生成を対象外化し、既存`cc_news_2per_openai`を利用する方針へ変更。実確認時の0件状態を記録 |
| 1.0 | 2026-07-17 | Anthropic／Gemini混在実装からOpenAI APIへ全面統一するTODOを作成 |
