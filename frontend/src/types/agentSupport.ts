import type { components } from './generated'

export type ExecutionState = components['schemas']['ExecutionState']
export type ActionRequest = components['schemas']['ActionRequest']
export type PendingConfirmation = components['schemas']['PendingConfirmation']
export type RunRequest = components['schemas']['RunRequest']

type ApiSupportResult = components['schemas']['SupportResult']
export type SupportResult = Omit<ApiSupportResult, 'citations'> & {
  citations: string[]
}

type ApiRunRecord = components['schemas']['RunRecord']
export type RunRecord = Omit<ApiRunRecord, 'result' | 'pending_confirmation'> & {
  result?: SupportResult
  pending_confirmation?: PendingConfirmation
}

export interface RunEvent {
  id: number
  type: string
  state: ExecutionState
  data: Record<string, unknown>
  created_at: string
}

export interface ConfirmationResponse {
  run: RunRecord
  outcome?: SupportResult['action_outcome']
}
