import type {
  ActionRequest,
  ConfirmationResponse,
  RunEvent,
  RunRecord,
  RunRequest,
} from '../types/agentSupport'

const API = import.meta.env.VITE_API_BASE ?? ''

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body?.detail?.message ?? `APIエラー (${response.status})`)
  }
  return response.json() as Promise<T>
}

function confirmation(
  run: RunRecord,
  decision: 'approve' | 'reject' | 'modify',
  action?: ActionRequest,
) {
  return json<ConfirmationResponse>(
    `/api/agent-support/runs/${run.run_id}/confirmations`,
    {
      method: 'POST',
      body: JSON.stringify({
        decision,
        version: run.pending_confirmation!.version,
        action_hash: run.pending_confirmation!.action_hash,
        action,
      }),
    },
  )
}

export const agentSupportClient = {
  listRuns: () => json<RunRecord[]>('/api/agent-support/runs'),
  createRun: (request: RunRequest) =>
    json<RunRecord>('/api/agent-support/runs', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
  getRun: (id: string) => json<RunRecord>(`/api/agent-support/runs/${id}`),
  cancel: (id: string) =>
    json<RunRecord>(`/api/agent-support/runs/${id}/cancel`, { method: 'POST' }),
  confirm: confirmation,
  events: (id: string, onEvent: (event: RunEvent) => void, onError: () => void) => {
    const source = new EventSource(`${API}/api/agent-support/runs/${id}/events`)
    const eventTypes = [
      'plan_started', 'plan_completed', 'replan_completed', 'execution_started', 'executor_state',
      'tool_event', 'step_completed', 'groundedness_completed', 'gate_completed',
      'web_started', 'web_completed', 'no_info_completed', 'confirmation_required',
      'confirmation_resolved', 'action_started', 'action_completed', 'run_completed',
      'run_failed', 'run_cancelled',
    ]
    eventTypes.forEach(type => source.addEventListener(type, raw => {
      onEvent(JSON.parse((raw as MessageEvent).data))
    }))
    source.onerror = onError
    return () => source.close()
  },
}
