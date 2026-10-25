import { api, type Job, type JobStatus, type Team } from '../api'

const statusStyle: Record<JobStatus, string> = {
  queued: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
  running: 'bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300',
  done: 'bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300',
  cancelled: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400',
}

/** "Play-by-play · 2024-25 Regular Season · GSW vs LAL · Home" */
function describe(job: Job, teams: Map<number, Team>): string {
  const f = job.request.filters
  const team = (id?: number) => (id ? (teams.get(id)?.abbreviation ?? String(id)) : null)
  const dates = f.date_from || f.date_to ? `${f.date_from ?? '…'} → ${f.date_to ?? '…'}` : null
  return [
    job.request.dataset === 'games' ? 'Games' : 'Play-by-play',
    [f.season, f.season_type].filter(Boolean).join(' ') || null,
    dates,
    [team(f.team_id), f.opponent_team_id ? `vs ${team(f.opponent_team_id)}` : null].filter(Boolean).join(' ') || null,
    f.location === 'Road' ? 'Away' : f.location,
    f.outcome && (f.outcome === 'W' ? 'Wins' : 'Losses'),
  ]
    .filter(Boolean)
    .join(' · ')
}

export function ExportList({ jobs, teams, onChanged }: { jobs: Job[]; teams: Team[]; onChanged: () => void }) {
  const byId = new Map(teams.map((t) => [t.id, t]))

  if (jobs.length === 0) {
    return <p className="text-sm text-zinc-500">No exports yet. Finished exports stay downloadable for 24 hours.</p>
  }

  return (
    <ul className="space-y-3">
      {jobs.map((job) => {
        const active = job.status === 'queued' || job.status === 'running'
        const percent = job.total ? Math.round((job.done / job.total) * 100) : null
        return (
          <li
            key={job.id}
            className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{describe(job, byId)}</p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {new Date(job.created_at * 1000).toLocaleString()} · {job.request.format.toUpperCase()}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${statusStyle[job.status]}`}>
                {job.status}
              </span>
            </div>

            {job.status === 'running' && percent !== null && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div className="h-full bg-accent transition-[width]" style={{ width: `${percent}%` }} />
              </div>
            )}

            {(job.message || job.error) && (
              <p
                className={`mt-2 text-sm break-words ${job.error ? 'text-red-700 dark:text-red-300' : 'text-zinc-600 dark:text-zinc-400'}`}
              >
                {job.error ?? job.message}
              </p>
            )}

            {(job.status === 'done' || active) && (
              <div className="mt-3 flex gap-2">
                {job.status === 'done' && (
                  <a
                    href={api.downloadUrl(job.id)}
                    download={job.filename ?? undefined}
                    className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 dark:text-zinc-950"
                  >
                    Download
                  </a>
                )}
                {active && (
                  <button
                    type="button"
                    onClick={() => api.cancel(job.id).then(onChanged)}
                    className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
                  >
                    Cancel
                  </button>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
