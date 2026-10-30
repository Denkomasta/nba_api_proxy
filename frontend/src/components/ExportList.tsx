import { Button, Card, LinkButton, StatusBadge, type StatusBadgeProps } from 'denval-ui'
import { api, type Job, type JobStatus, type Team } from '../api'

// denval-ui has no error tone, so "failed" recolours the neutral badge and its dot
const statusBadge: Record<JobStatus, Pick<StatusBadgeProps, 'tone' | 'className'>> = {
  queued: { tone: 'neutral' },
  running: { tone: 'warning' },
  done: { tone: 'success' },
  failed: { className: 'text-red-700 dark:text-red-300 [&>span]:bg-red-500' },
  cancelled: { tone: 'neutral' },
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
    return <p className="text-label text-subtle">No exports yet. Finished exports stay downloadable for 24 hours.</p>
  }

  return (
    <ul className="space-y-3">
      {jobs.map((job) => {
        const active = job.status === 'queued' || job.status === 'running'
        const percent = job.total ? Math.round((job.done / job.total) * 100) : null
        return (
          <Card as="li" key={job.id} className="p-4">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-label font-medium text-heading">{describe(job, byId)}</p>
                <p className="mt-0.5 text-caption text-subtle">
                  {new Date(job.created_at * 1000).toLocaleString()} · {job.request.format.toUpperCase()}
                </p>
              </div>
              <StatusBadge {...statusBadge[job.status]}>{job.status}</StatusBadge>
            </div>

            {job.status === 'running' && percent !== null && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-fill">
                <div className="h-full bg-accent transition-[width]" style={{ width: `${percent}%` }} />
              </div>
            )}

            {(job.message || job.error) && (
              <p
                className={`mt-2 text-label wrap-break-word ${job.error ? 'text-red-700 dark:text-red-300' : 'text-muted'}`}
              >
                {job.error ?? job.message}
              </p>
            )}

            {(job.status === 'done' || active) && (
              <div className="mt-3 flex gap-2">
                {job.status === 'done' && (
                  <LinkButton
                    href={api.downloadUrl(job.id)}
                    download={job.filename ?? undefined}
                    variant="solid"
                    size="sm"
                  >
                    Download
                  </LinkButton>
                )}
                {active && (
                  <Button size="sm" onClick={() => api.cancel(job.id).then(onChanged)}>
                    Cancel
                  </Button>
                )}
              </div>
            )}
          </Card>
        )
      })}
    </ul>
  )
}
