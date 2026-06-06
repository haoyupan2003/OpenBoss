import { render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import App from '../App'

beforeEach(() => {
  vi.restoreAllMocks()
})

function mockAll() {
  vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
    const s = typeof url === 'string' ? url : url.toString()
    if (s.includes('/health')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'healthy', app: 'OpenBoss Agent System', version: '0.2.0' }) } as Response)
    }
    if (s.includes('/api/agents')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({
        agents: [{ task_id: 'task-001', status: 'COMPLETED', role: 'dev', started: null, finished: null, git_sha: 'abc1234', error: null }],
        summary: { total: 1, completed: 1, failed: 0, in_progress: 0, blocked: 0 },
        by_role: [],
      }) } as Response)
    }
    if (s.includes('/api/tasks')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({
        tasks: [{ id: 'task-001', title: 'Login', status: 'completed', priority: 'high', complexity: 'medium', suggested_role: 'dev', dependencies: [], progress: null }],
        summary: { total: 1, completed: 1, failed: 0, pending: 0, in_progress: 0, blocked: 0 },
      }) } as Response)
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ agents: [], summary: { total: 0 }, by_role: [] }) } as Response)
  })
}

describe('App', () => {
  it('renders header and health status', async () => {
    mockAll()
    render(<App />)
    await waitFor(() => expect(screen.getByText('OpenBoss')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('healthy')).toBeInTheDocument())
  })

  it('renders all 5 navigation tabs', async () => {
    mockAll()
    render(<App />)
    await waitFor(() => expect(screen.getByText('Home')).toBeInTheDocument())
    expect(screen.getByText('New Req')).toBeInTheDocument()
    expect(screen.getAllByText('Agents').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Tasks').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Alerts').length).toBeGreaterThanOrEqual(1)
  })

  it('renders Dashboard on home tab', async () => {
    mockAll()
    render(<App />)
    await waitFor(() => expect(screen.getByText('System Overview')).toBeInTheDocument())
  })

  it('switches to Agents tab and shows agent data', async () => {
    mockAll()
    render(<App />)
    await waitFor(() => expect(screen.getByText('System Overview')).toBeInTheDocument())
    // Click the Agents nav button (2nd button after Home)
    const btns = document.querySelectorAll('nav button')
    expect(btns.length).toBeGreaterThanOrEqual(2)
    act(() => (btns[1] as HTMLButtonElement).click())
    await waitFor(() => expect(screen.getByText('task-001')).toBeInTheDocument())
  })

  it('switches to Tasks tab and shows task data', async () => {
    mockAll()
    render(<App />)
    await waitFor(() => expect(screen.getByText('System Overview')).toBeInTheDocument())
    const btns = document.querySelectorAll('nav button')
    expect(btns.length).toBeGreaterThanOrEqual(3)
    act(() => (btns[2] as HTMLButtonElement).click())
    await waitFor(() => expect(screen.getByText('Login')).toBeInTheDocument())
  })
})
