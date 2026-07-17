import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from '../App'

class EventSourceMock { addEventListener() {} close() {} onerror = () => {} }
globalThis.EventSource = EventSourceMock as unknown as typeof EventSource

test('submits and renders grounded answer', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      run_id: '12345678-test', request: {}, state: 'completed',
      result: { answer: '根拠付き回答', citations: ['[社内] FAQ'], groundedness: 1,
        decision: 'answer', warning: false, used_web: false, contradiction: false,
        forced_escalate: false, no_info_detected: false }, created_at: '', updated_at: '',
    }),
  }) as typeof fetch
  render(<App />)
  fireEvent.change(screen.getByPlaceholderText(/返品したい/), { target: { value: '質問です' } })
  fireEvent.click(screen.getByRole('button', { name: /実行を開始/ }))
  await waitFor(() => expect(screen.getByText('根拠付き回答')).toBeInTheDocument())
  expect(screen.getByText('[社内] FAQ')).toBeInTheDocument()
})

test('renders escalation without presenting an automatic answer', async () => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      run_id: 'escalate-test', request: {}, state: 'escalated',
      result: { answer: null, citations: [], groundedness: 0,
        groundedness_decided: 0, decision: 'escalate', warning: false,
        used_web: false, web_reused: false, contradiction: false,
        forced_escalate: true, no_info_detected: false }, created_at: '', updated_at: '',
    }),
  }) as typeof fetch
  render(<App />)
  fireEvent.change(screen.getByPlaceholderText(/返品したい/), { target: { value: '障害です' } })
  fireEvent.click(screen.getByRole('button', { name: /実行を開始/ }))

  await waitFor(() => expect(screen.getByText('有人対応へ引き継ぎます')).toBeInTheDocument())
  expect(screen.getByText(/自動回答を停止/)).toBeInTheDocument()
  expect(screen.getByText('あり')).toBeInTheDocument()
})

test('modifies a pending HITL action without executing it', async () => {
  const pending = {
    action: { action_type: 'create_ticket', args: { query: '旧内容' },
      requires_confirmation: true, action_id: 'action-1' },
    action_hash: 'old-hash', version: 1, expires_at: '2099-01-01T00:00:00Z',
  }
  const initialRun = {
    run_id: 'hitl-test', request: {}, state: 'pending_confirmation', result: undefined,
    pending_confirmation: pending, created_at: '', updated_at: '',
  }
  const replacedRun = {
    ...initialRun,
    pending_confirmation: { ...pending, action: { ...pending.action, args: { query: '新内容' } },
      action_hash: 'new-hash', version: 2 },
  }
  globalThis.fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => initialRun })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ run: replacedRun }) }) as typeof fetch

  render(<App />)
  fireEvent.change(screen.getByPlaceholderText(/返品したい/), { target: { value: 'バグです' } })
  fireEvent.click(screen.getByRole('button', { name: /実行を開始/ }))
  const editor = await screen.findByLabelText('Action引数')
  fireEvent.change(editor, { target: { value: '{"query":"新内容"}' } })
  fireEvent.click(screen.getByRole('button', { name: '修正を依頼' }))

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2))
  const [, request] = vi.mocked(globalThis.fetch).mock.calls[1]
  const body = JSON.parse(String(request?.body))
  expect(body.decision).toBe('modify')
  expect(body.action.args).toEqual({ query: '新内容' })
  expect(body.version).toBe(1)
  await waitFor(() => expect(screen.getByLabelText('Action引数')).toHaveValue(
    JSON.stringify({ query: '新内容' }, null, 2),
  ))
})

test('restores the last run after reload including pending confirmation', async () => {
  localStorage.setItem('grace-support-run-id', 'restored-run')
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      run_id: 'restored-run', request: { query: '復元対象', vertical: 'saas' },
      state: 'pending_confirmation',
      pending_confirmation: {
        action: { action_type: 'create_ticket', args: { query: '復元対象' },
          requires_confirmation: true },
        action_hash: 'restore-hash', version: 1, expires_at: '2099-01-01T00:00:00Z',
      },
      created_at: '', updated_at: '',
    }),
  }) as typeof fetch

  render(<App />)

  expect(await screen.findByText('アクションの承認が必要です')).toBeInTheDocument()
  await waitFor(() => expect(screen.getByLabelText('Action引数')).toHaveValue(
    JSON.stringify({ query: '復元対象' }, null, 2),
  ))
  expect(globalThis.fetch).toHaveBeenCalledWith(
    '/api/agent-support/runs/restored-run',
    expect.any(Object),
  )
})

test('loads run history and opens a selected run', async () => {
  const historical = {
    run_id: 'history-run', request: { query: '過去の問い合わせ', vertical: 'gov' },
    state: 'completed', result: { answer: '過去の回答', citations: [], groundedness: 1,
      groundedness_decided: 1, decision: 'answer', warning: false, used_web: false,
      web_reused: false, contradiction: false, forced_escalate: false,
      no_info_detected: false }, created_at: '', updated_at: '',
  }
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [historical] }) as typeof fetch

  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '実行履歴を表示' }))
  const historyItem = await screen.findByRole('button', { name: /gov · completed/ })
  fireEvent.click(historyItem)

  expect(await screen.findByText('過去の回答')).toBeInTheDocument()
  expect(localStorage.getItem('grace-support-run-id')).toBe('history-run')
})
