import { Check, Circle, LoaderCircle, ShieldCheck } from 'lucide-react'
import type { ExecutionState } from '../types/agentSupport'

const steps: [ExecutionState, string][] = [
  ['planning', 'Plan'],
  ['executing', 'Execute'],
  ['verifying', 'Groundedness'],
  ['gating', 'Answer gate'],
  ['web_verifying', 'Web verify'],
  ['no_info_check', 'No-info'],
  ['pending_confirmation', 'Action'],
]
const progressOrder: ExecutionState[] = [
  'queued', ...steps.map(step => step[0]), 'action_executing', 'completed',
]
const terminalStates: ExecutionState[] = ['completed', 'escalated', 'cancelled', 'failed']

export function WorkflowTimeline({ state }: { state: ExecutionState }) {
  const active = progressOrder.indexOf(state)
  const terminal = terminalStates.includes(state)
  return <ol className="timeline" aria-label="処理の進捗">
    {steps.map(([key, label], index) => {
      const position = progressOrder.indexOf(key)
      const complete = (active > position && active >= 0) || state === 'completed'
      const current = state === key || (key === 'pending_confirmation' && state === 'action_executing')
      return <li key={key} className={complete ? 'complete' : current ? 'current' : ''}>
        <span>{complete ? <Check /> : current ? <LoaderCircle /> : <Circle />}</span>
        <small>{String(index + 1).padStart(2, '0')}</small>{label}
      </li>
    })}
    <li className={terminal ? 'complete' : ''}>
      <span><ShieldCheck /></span><small>08</small>{terminal ? `Result: ${state}` : 'Result'}
    </li>
  </ol>
}
