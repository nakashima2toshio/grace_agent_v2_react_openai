import { render, screen } from '@testing-library/react'
import App from '../App'

class EventSourceMock { addEventListener() {} close() {} onerror = () => {} }
globalThis.EventSource = EventSourceMock as unknown as typeof EventSource

test('renders query form and safety controls', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: '問い合わせ' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /実行を開始/ })).toBeInTheDocument()
  expect(screen.getByLabelText('Web相互検証')).toBeChecked()
  expect(screen.getByText(/Human-approved actions/)).toBeInTheDocument()
})
