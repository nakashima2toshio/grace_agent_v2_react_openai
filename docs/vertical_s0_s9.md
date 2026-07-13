## エージェント　自律型AI-エージェント・プログラミング

ChatGPT5.6solが出ましたが、まだ、まだ、claude code 一択のようですね。
ソフトウェ開発の分野では、claude Opus4.8（Fable5使わずとも）の方が、まだまだ、出来が良いですね。
では、「業界特化・自治体向け」のRAG・「自律型AIエージェント」のプログラミングの紹介です。
- **Claude API 版（本記事の実装）**: https://github.com/nakashima2toshio/anthropic_grace_agent_v2
- **ローカル LLM 版（Ollama）**: https://github.com/nakashima2toshio/ollama_grace_agent_v2
日本語 RAG の自律型エージェントを土台に、**自治体・SaaS・EC の 3 業種ををスクラッチで作りました。この記事では、その中心である「業界特化」の設計、「自治体・gov」を説明します。
##### 「業界特化」コマンド：
```bash
uv run agent_support_example.py
```

| Phase | モジュール | 説明 |
|:---|:---|:---|
| [1] | agent_support_example.py | ユーザから質問入力 |
| [2] | planner.py | 計画生成（最初に実行） |
| [4] | executor.py | 計画実行（中核エンジン） |
| [5] | confidence.py | 信頼度計算（各ステップ実行後に評価） |
| [6] | intervention.py | HITL 介入（信頼度が低い場合に発動） |
| [7] | replan.py | 動的リプラン（失敗・低信頼度時に再計画） |
| [米] | tools.py | ツール定義（Executor が呼び出す道具箱） |

### 「汎用RAG・自律型AI-Agent」→業界特化の機能の必要性
AI-Agentのコードは共通で、業界プロファイル（VerticalProfile）で制御します。
--vertical {gov|saas|ec} で 業界プロファイル（VerticalProfile） を適用し、検索スコープ・エスカレ語・回答しきい値・アクション対応・本人確認を切り替える。ご検知抑止のため、キーワード一致は候補検出（第 1 段）に留め、一致時のみ軽量 LLM で意図分類（第 2 段）する二段判定を採用する。
##### gov（自治体向け）のプロファイル
```python
"gov": VerticalProfile(
    name="自治体",
    # wikipedia_ja は専用コレクション（gov_faq/gov_laws）登録までの代替
    collections=["gov_faq_anthropic", "gov_laws_anthropic", "wikipedia_ja"],
    escalate_keywords=["法的", "訴訟", "減免", "個別", "例外", "不服"],
    action_map={"申請": "send_reply", "手続": "send_reply", "様式": "send_reply"},
    require_identity=False,
    notify_th=0.8, confirm_th=0.5,   # 正確性最優先：厳しめ
    prompt_addendum="条例・公式案内に基づき、断定を避け、該当ページ・担当課を明示。個人情報は尋ねない。",
),
```

##### SaaS（クラウド・サービス）のプロファイル
```python
"saas": VerticalProfile(
    name="SaaS",
    collections=["saas_docs_anthropic", "saas_api_anthropic"],
    escalate_keywords=["障害", "ダウン", "落ち", "課金", "請求", "情報漏", "セキュリティ"],
    action_map={"エラー": "create_ticket", "不具合": "create_ticket", "バグ": "create_ticket"},
    require_identity=False,
    prompt_addendum="製品バージョンを明示し、再現手順と公式ドキュメント URL を添える。",
),
```
##### ECのプロファイル
```python
"ec": VerticalProfile(
    name="EC",
    collections=["ec_policy_anthropic", "ec_faq_anthropic"],
    escalate_keywords=["決済", "返金", "破損", "クレーム", "不良品"],
    action_map={"返品": "create_ticket", "交換": "create_ticket",
                "キャンセル": "create_ticket", "解約": "create_ticket"},
    require_identity=True,           # 注文情報の操作は本人確認必須
    prompt_addendum="注文情報の照会・変更は本人確認必須。返品・交換は規定の版に基づいて回答。",
),
```
### agent_support_example.py を「s0 から s9」に分解・実行
| 機能 | 説明                                   | コード                                                                              |
|--|--------------------------------------|----------------------------------------------------------------------------------|
| s0_arg.py | 引数をプロファイルに書き込む         |                                                                                  |
| s1_profile.py | 共有 config(grace/config) オブジェクトへの書き込み | config.qdrant.allowed_collections = list(profile.collections) if profile else [] |
| s2_plan.py |                                      |                                                                                  |
| s3_execute.py |                                      |                                                                                  |
| s4_confidence.py |                                      |                                                                                  |
| s5_gate.py |                                      |                                                                                  |
| s6_web.py |                                      |                                                                                  |
| s7_no_info.py |                                      |                                                                                  |
| s8_action.py |                                      |                                                                                  |
| s9_render.py |                                      |                                                                                  |


##### s0:引数の処理：
```bash
uv run python grace/step_trace/s0_arg.py --vertical gov "住民票の写しの取り方は？"
```
##### s0:実行結果：
```aiignore
============================================================
S0. 起動・引数解釈（argparse → args / identity）
============================================================
IN     : argv=['--vertical', 'gov', '住民票の写しの取り方は？']
Process: build_parser() で main() と同一の引数体系を構築 → parser.parse_args()
         --identity KEY=VALUE（append）を dict へ変換（'=' を含まない指定は無視）
         この args / identity が run_support_agent(query, verbose, use_web, ...) の入力になる
OUT    : vars(args) と identity（下記に pprint 表示）

parser=:
ArgumentParser(prog='s0_arg.py', usage=None, description='GRACE-Support: 内部RAG＋出典／Web裏取り・相互検証／アクション＋HITL／業界特化(--vertical)', formatter_class=<class 'argparse.HelpFormatter'>, conflict_handler='error', add_help=True)
args=:
{'do_action': True,
 'dry_run': True,
 'identity': None,
 'query': '住民票の写しの取り方は？',
 'use_web': True,
 'verbose': False,
 'vertical': 'gov'}
identity=:
None
```
##### (s0)プロファイルの影響：
- 引数がプロファイルに設定される。

##### s1:：共有 config オブジェクトへの書き込み
```bash
uv run python grace/step_trace/s1_profile.py --vertical gov "住民票の写しの取り方は？"
```
##### s1の説明：
```python
# コアへの配線: 検索スコープ（rag_search の許可リスト）と業界方針（reasoning へ注入）。
# tools は config への参照を保持しているため、ここでの設定が実行時に効く。
config.qdrant.allowed_collections = list(profile.collections) if profile else []
config.llm.prompt_addendum = profile.prompt_addendum if profile else ""
```
```aiignore
============================================================
S1. 業界プロファイル適用（--vertical gov）
============================================================
IN     : vertical='gov'
Process: get_config() で共通設定を取得（planner/executor/verifier/intervention もここで生成）
         PROFILES.get(vertical) で VerticalProfile を解決
         config.qdrant.allowed_collections / config.llm.prompt_addendum へ配線
         notify_th / confirm_th をプロファイル値（無ければ config 既定）で解決
         create_intent_classifier / create_no_info_judge は用意のみ（この時点では未発火）
OUT    : profile = VerticalProfile(name='自治体', collections=['gov_faq_anthropic', 'gov_laws_anthropic', 'wikipedia_ja'], escalate_keywords=['法的', '訴訟', '減免', '個別', '例外', '不服'], action_map={'申請': 'send_reply', '手続': 'send_reply', '様式': 'send_reply'}, require_identity=False, notify_th=0.8, confirm_th=0.5, prompt_addendum='条例・公式案内に基づき、断定を避け、該当ページ・担当課を明示。個人情報は尋ねない。')
         config.qdrant.allowed_collections = ['gov_faq_anthropic', 'gov_laws_anthropic', 'wikipedia_ja']
         config.llm.prompt_addendum        = '条例・公式案内に基づき、断定を避け、該当ページ・担当課を明示。個人情報は尋ねない。'
         notify_th=0.8 / confirm_th=0.5

============================================================
業界プロファイル: 自治体（--vertical gov）
============================================================
  検索スコープ: gov_faq_anthropic, gov_laws_anthropic, wikipedia_ja（未登録コレクションは自動的に無視）
  しきい値: notify=0.8 / confirm=0.5 / 本人確認=False
  方針(reasoningへ注入): 条例・公式案内に基づき、断定を避け、該当ページ・担当課を明示。個人情報は尋ねない。
```
##### (s1) 設定された「プロファイル」のプログラム実行への影響


##### s2:
```bash
uv run python grace/step_trace/s2_plan.py --vertical gov "住民票の写しの取り方は？"
```
##### s2の説明

##### s2実行結果：
```aiignore
============================================================
S2. ① Plan（planner.create_plan）
============================================================
❓ 問い合わせ: 住民票の写しの取り方は？
IN     : query='住民票の写しの取り方は？', allowed_collections=['gov_faq_anthropic', 'gov_laws_anthropic', 'wikipedia_ja']
Process: Planner.create_plan(query) … LLM が複雑度を推定し rag_search/reasoning 計画を生成
OUT    : plan = ExecutionPlan(
           original_query='住民票の写しの取り方は？',
           complexity=0.50, estimated_steps=2,
           steps=[
             PlanStep(step_id=1, action='rag_search', collection='gov_faq_anthropic', depends_on=[])
             PlanStep(step_id=2, action='reasoning', collection=None, depends_on=[1])
           ])

  [plan] 2 ステップ (complexity=0.50)
```

##### s3:
```bash
uv run python grace/step_trace/s3_execute.py --vertical gov "住民票の写しの取り方は？"
```

```aiignore
============================================================
S3. ② Execute（executor + tools: 内部RAG）
============================================================
2026-07-12 18:42:48,383 - regex_mecab - INFO - ✅ MeCabが利用可能です（複合名詞抽出モード）
🔍 Searching collection: gov_faq_anthropic
2026-07-12 18:42:48,530 - agent_tools - INFO - ツールアクション(Structured): RAG検索を実行: query='住民票の写しの取り方は？', collection='gov_faq_anthropic', hybrid=有効
2026-07-12 18:42:48,548 - helper.helper_embedding - INFO - GeminiEmbedding initialized: model=gemini-embedding-001, dims=3072
2026-07-12 18:42:49,825 - helper.helper_embedding_sparse - INFO - Initializing SparseEmbedding with model: prithivida/Splade_PP_en_v1
2026-07-12 18:42:50,386 - qdrant_client_wrapper - WARNING - ⚠️ 【Stage 1→2】Sparse Vector未設定 (gov_faq_anthropic): Denseのみに切替
2026-07-12 18:42:50,400 - agent_tools - INFO - コサイン類似度フィルタ: 10 -> 1件 (Top: 0.8011, 閾値: 0.7)

==================== [RAG SEARCH IPO: OUTPUT] ====================
Collection: gov_faq_anthropic
[
  {
    "score": 0.8010899,
    "id": 3463679292697501101,
    "payload": {
      "domain": "gov_faq_anthropic",
      "question": "住民票の写しの取り方を教えてください",
      "answer": "住民票の写しは市役所本庁舎・各区役所の窓口、郵送、コンビニ交付（マイナンバーカードが必要）で取得できます。窓口・コンビニは1通300円、郵送は定額小為替でのお支 払いです。本人確認書類をお持ちください。",
      "source": "gov_faq.csv",
      "created_at": "2026-07-11T00:43:23.917385+00:00",
      "schema": "qa:v1",
      "topic": "住民票",
      "embedding_provider": "gemini",
      "embedding_model": "gemini-embedding-001"
    }
  }
]
============================================================
IN     : plan（②の計画）, config.qdrant.allowed_collections, config.llm.prompt_addendum
Process: executor.execute(plan) → RAG 限定検索 →（不足なら web_search 動的挿入）→ reasoning 生成
OUT    : result.overall_confidence=0.84
             step1: success (sources=1)
             step2: success (sources=0)
         internal_answer[:60]='## 住民票の写しの取得方法について\n\n社内ナレッジ（出典：`gov_faq.csv`）によると、住民票の写しは以下の方'
         internal_citations=['[社内] gov_faq.csv']
         used_dynamic_web=False
  step1: success (sources=1)
  step2: success (sources=0)
```

##### s4:
```bash
uv run python grace/step_trace/s4_confidence.py --vertical gov "住民票の写しの取り方は？"
```

```aiignore
============================================================
S4. ③ Confidence（GroundednessVerifier: 内部回答の裏付け）
============================================================
IN     : query='住民票の写しの取り方は？', answer=SAMPLE_ANSWER, sources=1 件
Process: GroundednessVerifier.verify(...) が主張分解→3値判定→支持率を集計
OUT    : gres = GroundednessResult(
             support_rate=1.0, supported=4, contradicted=0, total=4,
             has_contradiction=False, verified=True)

  [groundedness] 支持率=1.00（判定可能 4/4 主張） / 出典数=1
```

##### s5:
```bash
uv run python grace/step_trace/s5_gate.py --vertical gov "固定資産税の減免を個別に判断してほしい"
```

```aiignore
============================================================
S5. ④ 回答ゲート＋強制エスカレ（二段判定）
============================================================
IN     : support_rate=0.86, verified=True, citation_count=3, notify_th=0.8, confirm_th=0.5
         query='固定資産税の減免を個別に判断してほしい', profile=gov
Process: _answer_gate(...) が 支持率≥notify かつ 出典≥1 → answer を判定
         _should_force_escalate(query, profile, classify): 第1段 _match_keyword で候補検出、
           一致時のみ classify（意図分類）。question は誤検知抑止、request/incident は強制エスカレ
         _should_rescue_unaffirmed は decision!='escalate' のため今回は不発（救済不要）
OUT    : (decision, warning) = ('escalate', False)
         forced_escalate=True, matched_kw='減免', intent='request'

  [profile] エスカレ語 '減免'（意図=request）を検知 → 有人対応へ

```

##### s6:
```bash
uv run python grace/step_trace/s6_web.py --vertical gov "住民票の写しの取り方は？"
```

```aiignore
============================================================
S6. ⑤ Web フォールバック（tools.web_search → reasoning → 相互検証）
============================================================
IN     : decision='answer', use_web=True, forced_escalate=False
Process: `if decision == "escalate" and use_web and not forced_escalate:` を評価。
         True なら: executor が Web 使用済み→内部回答を本文スニペットで再検証のみ（web_reused=True）、
                  未使用→web_search → reasoning → 相互検証（SourceAgreementCalculator）
                  → _answer_gate 再判定 / _pick_groundedness / _merge_citations で SupportResult 再構築
OUT    : 分岐に入らない（support は S5 のまま）   # gov 代表例は decision='answer'

  ⑤ はスキップ（decision='answer' か --no-web か forced_escalate のため）
```

##### s7:
```bash
uv run python grace/step_trace/s7_no_info.py --vertical gov "住民票の写しの取り方は？"
```

```aiignore
============================================================
S7. ④' 情報なし回答検知（_detect_no_info_answer）
============================================================
IN     : query='住民票の写しの取り方は？', answer[:40]='住民票の写しは、市区町村の窓口（市民課等）・コンビニ交付・郵送で請求できます。本',
         force_judge(web_only)=False, judge=あり
Process: 第1段: _match_keyword(answer, NO_INFO_MARKERS) で候補句を検出
           → 候補なし かつ not force_judge なら (False, None)（LLM 未実行）
           → 候補あり でも judge=None（鍵なし）なら (False, marker)（従来どおり回答を通す）
         第2段: judge(query, answer) で answered/no_info を判定
           → answered なら (False, marker)、no_info/判定失敗なら (True, marker)（安全側 escalate）
OUT    : 第1段の候補句 marker=None
         (no_info, matched_marker) = (False, None)

  [gate] 実質回答（answered）→ decision='answer' を維持
```

##### s8:
```bash
uv run python grace/step_trace/s8_action.py --vertical gov "保育園の申請様式がほしい"
```

```aiignore
============================================================
S8. ⑥ Action（本人確認 → intervention CONFIRM → ActionTool[dry-run]）
============================================================
IN     : query='保育園の申請様式がほしい', decision='answer', profile=gov
Process: _decide_action(): escalate→escalate_to_human。answer なら第1段 _match_keyword
           (profile.action_map / 既定マッピング)、候補あり かつ 意図=question は起票せず None
         action があれば _perform_action(): 本人確認 → CONFIRM 承認 → backend.execute（dry-run）
OUT    : action = ActionRequest(action_type='send_reply', args={'query': '保育園の申請様式がほしい', 'matched': '申請'}, requires_confirmation=True)

  [action] 種別=send_reply（要承認=True）
  [action] [DRY-RUN] 'send_reply' を実行（ログのみ・args={'query': '保育園の申請様式がほしい', 'matched': '申請'}）
  [action] identity_checked=False / backend=dry-run
```

##### s9:
```bash
uv run python grace/step_trace/s9_render.py --vertical gov "住民票の写しの取り方は？"
```

```aiignore
============================================================
S9. ⑦ 応答整形（_render → SupportResult 返却）
============================================================
❓ 問い合わせ: 住民票の写しの取り方は？（--vertical gov の代表例）
IN     : support（S3〜S8 で確定した SupportResult）
Process: support.forced_escalate / support.intent を確定した後、
         _render(support) が回答本文＋出典一覧＋根拠メタ行を整形表示し、
         run_support_agent() が support を return
OUT    : decision='answer', groundedness=0.86, vertical='gov', intent=None
         端末表示（下記）＋ 呼び出し元へ SupportResult を返却

============================================================
応答
============================================================
住民票の写しは、お住まいの市区町村の窓口（市民課等）またはコンビニ交付・郵送で請求できます。本人確認書類が必要です。詳しくは担当課の案内ページをご確認ください。

【出典】
  [1] [社内] gov_faq_anthropic/住民票.md
  [2] [社内] gov_faq_anthropic/窓口案内.md
```
