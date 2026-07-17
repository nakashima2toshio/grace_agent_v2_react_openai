import { FormEvent, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowRight, BookOpen, CheckCircle2, RotateCcw, Shield, Square } from 'lucide-react'
import { agentSupportClient } from './api/agentSupportClient'
import { WorkflowTimeline } from './components/WorkflowTimeline'
import type { ActionRequest, RunEvent, RunRecord, RunRequest } from './types/agentSupport'
import './styles.css'
import './details.css'

const initial: RunRequest = { query: '', vertical: null, use_web: true, do_action: true, dry_run: true }
type PlanData = { complexity:number; success_criteria:string; steps:{step_id:number;action:string;description:string;depends_on?:number[]}[] }
export type StepData = { step_id:number; status:string; confidence?:number; sources?:unknown[]; execution_time_ms?:number; origin?:string; error?:string; error_code?:string }
const escalationLabels: Record<string, string> = {
  insufficient_grounding: '回答の根拠を十分に検証できませんでした。',
  contradiction: '情報源間の矛盾を検知しました。',
  no_information: '問い合わせに回答できる情報が見つかりませんでした。',
  forced_policy: '業務ポリシーにより自動回答を停止しました。',
  identity_required: '本人確認が必要です。',
  system_error: '処理中にシステムエラーが発生しました。',
}
const stepErrorLabels: Record<string, string> = {
  timeout: 'タイムアウト',
  tool_error: 'ツール実行エラー',
  cancelled: 'キャンセル',
  dependency_error: '依存ステップ未完了',
  validation_error: '入力・設定エラー',
}

export function formatStepError(step: StepData): string {
  if (!step.error) return ''
  return `${stepErrorLabels[step.error_code ?? ''] ?? '実行エラー'}: ${step.error}`
}

export function selectFinalSteps(events: RunEvent[]): StepData[] {
  const finalByStep = new Map<number, StepData>()
  events.filter(event => event.type === 'step_completed' && event.data.step).forEach(event => {
    const step = { ...(event.data.step as StepData) }
    if (typeof event.data.origin === 'string') step.origin = event.data.origin
    finalByStep.set(step.step_id, step)
  })
  return [...finalByStep.values()].sort((a, b) => a.step_id - b.step_id)
}

export default function App() {
  const [form, setForm] = useState(initial)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [history, setHistory] = useState<RunRecord[]>([])
  const [events, setEvents] = useState<RunEvent[]>([])
  const [error, setError] = useState('')
  const [editedArgs, setEditedArgs] = useState('')
  const busy = !!run && !['completed','escalated','cancelled','failed'].includes(run.state)
  const plan = useMemo(() => {
    const plans = events.filter(e => ['plan_completed', 'replan_completed'].includes(e.type))
    return plans.at(-1)?.data.plan as PlanData | undefined
  }, [events])
  const planRevision = useMemo(() => events.filter(e => e.type === 'replan_completed').length + 1, [events])
  const executed = useMemo(() => selectFinalSteps(events), [events])
  const executionAttempts = useMemo(
    () => events.filter(e => e.type === 'executor_state' && e.data.step).map(e => e.data.step as StepData),
    [events],
  )

  useEffect(() => {
    const runId = localStorage.getItem('grace-support-run-id')
    if (!runId) return
    agentSupportClient.getRun(runId).then(setRun).catch(() => {
      localStorage.removeItem('grace-support-run-id')
    })
  }, [])

  useEffect(() => {
    if (!run?.run_id) return
    return agentSupportClient.events(run.run_id, event => {
      setEvents(old => old.some(item => item.id === event.id) ? old : [...old, event])
      agentSupportClient.getRun(run.run_id).then(setRun).catch(() => undefined)
    }, () => agentSupportClient.getRun(run.run_id).then(setRun).catch(() => setError('接続を復元できませんでした。')))
  }, [run?.run_id])

  useEffect(() => {
    if (run?.pending_confirmation) {
      setEditedArgs(JSON.stringify(run.pending_confirmation.action.args, null, 2))
    }
  }, [run?.pending_confirmation])

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setEvents([])
    try {
      const created = await agentSupportClient.createRun(form)
      localStorage.setItem('grace-support-run-id', created.run_id)
      setRun(created)
    } catch (cause) { setError((cause as Error).message) }
  }
  async function loadHistory() {
    try { setHistory(await agentSupportClient.listRuns()) }
    catch (cause) { setError((cause as Error).message) }
  }
  async function decide(decision: 'approve' | 'reject') {
    if (!run) return
    try { setRun((await agentSupportClient.confirm(run, decision)).run) }
    catch (cause) { setError((cause as Error).message) }
  }
  async function modify() {
    if (!run?.pending_confirmation) return
    try {
      const action: ActionRequest = {
        ...run.pending_confirmation.action,
        args: JSON.parse(editedArgs) as Record<string, unknown>,
      }
      setRun((await agentSupportClient.confirm(run, 'modify', action)).run)
    } catch (cause) {
      setError(cause instanceof SyntaxError ? 'Action引数は正しいJSONで入力してください。' : (cause as Error).message)
    }
  }

  return <main>
    <header><a className="brand" href="#top"><b>G</b> GRACE <span>SUPPORT</span></a><div className="trust"><Shield/> Anthropic LLM ・ Gemini Embedding ・ Human-approved actions</div></header>
    <section className="hero" id="top"><div><p className="kicker">KNOWLEDGE-GROUNDED SUPPORT COPILOT</p><h1>答えるだけでなく、<br/><em>根拠まで見せる。</em></h1><p>社内ナレッジ、Web検証、有人承認をひとつの安全なワークフローへ。</p></div><aside><strong>7</strong><span>段階の検証フロー<br/><small>PLAN → HUMAN ACTION</small></span></aside></section>
    <section className="workspace">
      <form className="card" onSubmit={submit}><Title n="01" title="問い合わせ" sub="内容と業界プロファイルを指定してください"/><label>問い合わせ内容<textarea required maxLength={10000} value={form.query} placeholder="例：返品したいのですが、手続きを教えてください" onChange={e=>setForm({...form,query:e.target.value})}/></label><div className="form-row"><label>業界プロファイル<select required value={form.vertical??''} onChange={e=>setForm({...form,vertical:(e.target.value || null) as RunRequest['vertical']})}><option value="" disabled>選択してください</option><option value="gov">自治体</option><option value="saas">SaaS</option><option value="ec">EC</option></select></label><div className="toggles">{[['use_web','Web相互検証'],['do_action','Action候補'],['dry_run','Dry run']].map(([key,label])=><label key={key}><input type="checkbox" checked={!!form[key as keyof RunRequest]} onChange={e=>setForm({...form,[key]:e.target.checked})}/>{label}</label>)}</div></div>{form.vertical==='ec'&&<div className="identity"><input aria-label="注文番号" placeholder="注文番号" onChange={e=>setForm({...form,identity:{...form.identity,order_id:e.target.value}})}/><input aria-label="メール" type="email" placeholder="メール" onChange={e=>setForm({...form,identity:{...form.identity,email:e.target.value}})}/></div>}<button className="primary" disabled={busy}>実行を開始 <ArrowRight/></button></form>
      <aside className="card"><Title n="02" title="実行ステータス" sub={run?`RUN ${run.run_id.slice(0,8).toUpperCase()}`:'実行待ち'}/><WorkflowTimeline state={run?.state??'queued'}/>{busy&&<button className="secondary" onClick={()=>run&&agentSupportClient.cancel(run.run_id).then(setRun)}><Square/>実行を中止</button>}<button className="secondary" onClick={loadHistory}>実行履歴を表示</button>{history.length>0&&<ul className="history">{history.map(item=><li key={item.run_id}><button onClick={()=>{localStorage.setItem('grace-support-run-id',item.run_id);setRun(item);setEvents([])}}><b>{item.request.vertical??'general'} · {item.state}</b><span>{item.request.query}</span></button></li>)}</ul>}</aside>
    </section>
    {error&&<div className="toast"><AlertTriangle/>{error}<button onClick={()=>setError('')}>×</button></div>}
    {run&&<section className="results"><Title n="03" title="検証と回答" sub="処理結果はイベントとともに更新されます"/>
      <div className="metrics"><Metric k="状態" v={run.state}/><Metric k="業界" v={run.request.vertical??'未指定'}/><Metric k="Groundedness" v={run.result&&run.result.groundedness_decided>0?`${Math.round(run.result.groundedness*100)}%`:'判定不能'}/><Metric k="取得／検証出典" v={run.result?`${run.result.retrieved_source_count}/${run.result.verified_source_count}`:'0/0'}/><Metric k="イベント" v={String(events.length)}/></div>
      <div className="detail-grid">{plan&&<article className="detail-panel"><small>PLAN v{planRevision}</small><h3>{planRevision>1?'現在の実行計画':'実行計画'}</h3><p>複雑度 {plan.complexity.toFixed(2)} ・ {plan.steps.length} steps</p><ol>{plan.steps.map(step=><li key={step.step_id}><b>{step.step_id}. {step.description}</b><span>{step.action}{step.depends_on?.length?` / depends on ${step.depends_on.join(', ')}`:''}</span></li>)}</ol><p className="criteria">成功条件: {plan.success_criteria}</p></article>}{executed.length>0&&<article className="detail-panel"><small>EXECUTE</small><h3>確定ステップ結果</h3><p>{executionAttempts.length}件の途中状態から、各ステップの確定結果だけを表示しています。</p><ol>{executed.map(step=><li key={step.step_id}><b>Step {step.step_id} — {step.status}</b><span>{step.origin??'planned'} / confidence {Number(step.confidence??0).toFixed(2)} / sources {step.sources?.length??0} / {step.execution_time_ms??0}ms{step.error?` / ${formatStepError(step)}`:''}</span></li>)}</ol>{executionAttempts.length>0&&<details><summary>途中の試行履歴を表示</summary><ol>{executionAttempts.map((step,index)=><li key={`${step.step_id}-${index}`}><b>Attempt {index+1}: Step {step.step_id} — {step.status}</b><span>{step.execution_time_ms??0}ms{step.error?` / ${formatStepError(step)}`:''}</span></li>)}</ol></details>}</article>}</div>
      {run.result&&<div className="verification"><span>判定可能主張 <b>{run.result.groundedness_decided}</b></span><span>Web <b>{run.result.used_web?'使用':'不使用'}</b></span><span>再利用 <b>{run.result.web_reused?'あり':'なし'}</b></span><span>一致度 <b>{run.result.source_agreement==null?'—':run.result.source_agreement.toFixed(2)}</b></span><span>矛盾 <b>{run.result.contradiction?'検知':'なし'}</b></span><span>強制エスカレ <b>{run.result.forced_escalate?'あり':'なし'}</b></span><span>No-info <b>{run.result.no_info_detected?'検知':'なし'}</b></span></div>}
      {run.pending_confirmation&&<div className="confirmation"><div><p className="kicker">HUMAN IN THE LOOP</p><h3>アクションの承認が必要です</h3><p><b>{run.pending_confirmation.action.action_type}</b> — 承認されるまで処理は行われません。</p><label>Action引数<textarea aria-label="Action引数" value={editedArgs} onChange={e=>setEditedArgs(e.target.value)}/></label></div><div><button className="danger" onClick={()=>decide('reject')}>却下</button><button className="secondary" onClick={modify}>修正を依頼</button><button className="primary" onClick={()=>decide('approve')}><CheckCircle2/>承認して実行</button></div></div>}
      {run.result&&<article className={`answer ${run.result.decision}`}><div className="answer-title">{run.result.decision==='answer'?<CheckCircle2/>:<AlertTriangle/>}<div><small>{run.result.decision==='answer'?'GROUNDED ANSWER':'HUMAN ESCALATION'}</small><h3>{run.result.decision==='answer'?'回答':'有人対応へ引き継ぎます'}</h3></div></div><p>{run.result.decision==='answer'?(run.result.answer??'回答を生成できませんでした。'):(escalationLabels[run.result.escalation_reason??'']??'十分な根拠が得られなかったため、自動回答を停止しました。')}</p>{run.result.warning&&<div className="warning">この回答は出典による裏付けが十分ではありません。</div>}{run.result.citations.length>0&&<div className="citations"><h4><BookOpen/>参照した出典</h4>{run.result.citations.map((citation,index)=>{const url=citation.match(/https?:\/\/\S+/)?.[0];return <p key={citation}><b>{index+1}</b>{url?<a href={url} target="_blank" rel="noreferrer">{citation}</a>:citation}</p>})}</div>}</article>}
      {['completed','escalated','cancelled','failed'].includes(run.state)&&<button className="secondary" onClick={()=>{localStorage.removeItem('grace-support-run-id');setRun(null);setEvents([])}}><RotateCcw/>新しい問い合わせ</button>}
    </section>}
  </main>
}

function Title({n,title,sub}:{n:string;title:string;sub:string}) { return <div className="section-title"><b>{n}</b><div><h2>{title}</h2><p>{sub}</p></div></div> }
function Metric({k,v}:{k:string;v:string}) { return <article><small>{k}</small><strong>{v}</strong></article> }
