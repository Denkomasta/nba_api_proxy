// Types and calls for the backend (backend/app/main.py)

export type Dataset = 'games' | 'playbyplay'
export type Format = 'csv' | 'json'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Team {
  id: number
  name: string
  abbreviation: string
}

export interface Options {
  seasons: string[]
  season_types: string[]
  teams: Team[]
  first_live_season: string
  max_games: number
}

export interface Filters {
  season?: string
  season_type?: string
  team_id?: number
  opponent_team_id?: number
  date_from?: string
  date_to?: string
  location?: 'Home' | 'Road'
  outcome?: 'W' | 'L'
}

export interface ExportRequest {
  dataset: Dataset
  format: Format
  filters: Filters
}

export interface Job {
  id: string
  request: ExportRequest
  status: JobStatus
  created_at: number
  finished_at: number | null
  done: number
  total: number | null
  rows: number | null
  message: string | null
  error: string | null
  filename: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(errorMessage(body) ?? `${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<T>
}

// FastAPI returns { detail: string } or { detail: [{ msg }] } for validation errors
function errorMessage(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg?.replace(/^Value error, /, '')).join('; ')
  return null
}

export const api = {
  options: () => request<Options>('/options'),
  exports: () => request<Job[]>('/exports'),
  create: (body: ExportRequest) => request<Job>('/exports', { method: 'POST', body: JSON.stringify(body) }),
  cancel: (id: string) => request<Job>(`/exports/${id}/cancel`, { method: 'POST' }),
  downloadUrl: (id: string) => `/api/exports/${id}/download`,
}
