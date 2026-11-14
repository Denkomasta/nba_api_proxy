import { Button, ButtonSize, ButtonVariant, Card, LinkButton, Progress, StatusBadge, StatusTone } from 'denval-ui'
import { api, type Job, type JobStatus, type Team } from '../api'

const statusTone: Record<JobStatus, StatusTone> = {
  queued: StatusTone.NEUTRAL,
  running: StatusTone.WARNING,
  done: StatusTone.SUCCESS,
  failed: StatusTone.ERROR,
  cancelled: StatusTone.NEUTRAL,
}

/** "Play-by-play · 2024-25 Regular Season + Playoffs · GSW vs LAL · Home" */
function describe(job: Job, teams: Map<number, Team>): string {
  const f = job.request.filters
  const team = (id?: number) => (id ? (teams.get(id)?.abbreviation ?? String(id)) : null)
  const dates = f.date_from || f.date_to ? `${f.date_from ?? '…'} → ${f.date_to ?? '…'}` : null
  return [
    job.request.dataset === 'games' ? 'Games' : 'Play-by-play',
    [f.seasons?.join(', '), f.season_types?.join(' + ')].filter(Boolean).join(' ') || null,
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
        return (
          <Card as="li" key={job.id} className="p-4">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-label font-medium text-heading">{describe(job, byId)}</p>
                <p className="mt-0.5 text-caption text-subtle">
                  {new Date(job.created_at * 1000).toLocaleString()} · {job.request.format.toUpperCase()}
                </p>
              </div>
              <StatusBadge tone={statusTone[job.status]}>{job.status}</StatusBadge>
            </div>

            {job.status === 'running' && (
              // Moves back and forth until the total is known
              <Progress
                aria-label={`Progress of ${describe(job, byId)}`}
                value={job.total ? job.done : null}
                max={job.total || undefined}
                className="mt-3"
              />
            )}

            {(job.message || job.error) && (
              <p
                className={`mt-2 text-label wrap-break-word ${job.error ? 'text-error' : 'text-muted'}`}
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
                    variant={ButtonVariant.SOLID}
                    size={ButtonSize.SM}
                  >
                    Download
                  </LinkButton>
                )}
                {active && (
                  <Button size={ButtonSize.SM} onClick={() => api.cancel(job.id).then(onChanged)}>
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
