import { Button } from 'denval-ui'
import { type SubmitEvent, useState } from 'react'
import { api, type Dataset, type Filters, type Format, type Job, type Options } from '../api'
import { Field, inputClass, Segmented } from './controls'

const datasets: Record<Dataset, { label: string; description: string }> = {
  games: {
    label: 'Games',
    description: 'One row per team per game with box score totals. A single request, ready in seconds.',
  },
  playbyplay: {
    label: 'Play-by-play',
    description:
      'Every event of every matching game: the event log, with game_id or possession_id as the case. One request per game ' +
      '(about 1–3 s each), cached games are instant.',
  },
}

export function ExportForm({ options, onCreated }: { options: Options; onCreated: (job: Job) => void }) {
  const [dataset, setDataset] = useState<Dataset>('playbyplay')
  const [format, setFormat] = useState<Format>('csv')
  // Default to the last complete season
  const [season, setSeason] = useState(options.seasons[1] ?? '')
  const [seasonType, setSeasonType] = useState('Regular Season')
  const [teamId, setTeamId] = useState('')
  const [opponentId, setOpponentId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [location, setLocation] = useState<'' | 'Home' | 'Road'>('')
  const [outcome, setOutcome] = useState<'' | 'W' | 'L'>('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const noTimestamps = dataset === 'playbyplay' && season !== '' && season < options.first_live_season

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    const filters: Filters = {
      season: season || undefined,
      season_type: seasonType || undefined,
      team_id: teamId ? Number(teamId) : undefined,
      opponent_team_id: opponentId ? Number(opponentId) : undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      location: location || undefined,
      outcome: outcome || undefined,
    }
    setSubmitting(true)
    setError(null)
    try {
      onCreated(await api.create({ dataset, format, filters }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const teamOptions = options.teams.map((team) => (
    <option key={team.id} value={team.id}>
      {team.name}
    </option>
  ))

  return (
    <form onSubmit={submit} className="space-y-6">
      <div>
        <Segmented
          label="Data"
          value={dataset}
          onChange={setDataset}
          choices={(Object.keys(datasets) as Dataset[]).map((value) => ({ value, label: datasets[value].label }))}
        />
        <p className="mt-2 text-label text-muted">{datasets[dataset].description}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Season"
          hint={
            noTimestamps
              ? `Before ${options.first_live_season} events have no wall-clock time (timeActual). Order by game_seconds.`
              : undefined
          }
        >
          <select className={inputClass} value={season} onChange={(e) => setSeason(e.target.value)}>
            <option value="">Any (use the dates)</option>
            {options.seasons.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Field>
        <Field label="Season type">
          <select className={inputClass} value={seasonType} onChange={(e) => setSeasonType(e.target.value)}>
            <option value="">All</option>
            {options.season_types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </Field>
        <Field label="From date">
          <input type="date" className={inputClass} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </Field>
        <Field label="To date">
          <input type="date" className={inputClass} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </Field>
        <Field label="Team">
          <select className={inputClass} value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">All teams</option>
            {teamOptions}
          </select>
        </Field>
        <Field label="Opponent">
          <select className={inputClass} value={opponentId} onChange={(e) => setOpponentId(e.target.value)}>
            <option value="">Any opponent</option>
            {teamOptions}
          </select>
        </Field>
        <Segmented
          label="Location (of the team)"
          value={location}
          onChange={setLocation}
          choices={[
            { value: '', label: 'Any' },
            { value: 'Home', label: 'Home' },
            { value: 'Road', label: 'Away' },
          ]}
        />
        <Segmented
          label="Outcome (of the team)"
          value={outcome}
          onChange={setOutcome}
          choices={[
            { value: '', label: 'Any' },
            { value: 'W', label: 'Win' },
            { value: 'L', label: 'Loss' },
          ]}
        />
      </div>

      <div className="flex flex-wrap items-end gap-4 border-t border-divider pt-6">
        <div className="w-40">
          <Segmented
            label="File format"
            value={format}
            onChange={setFormat}
            choices={[
              { value: 'csv', label: 'CSV' },
              { value: 'json', label: 'JSON' },
            ]}
          />
        </div>
        <Button type="submit" variant="solid" disabled={submitting} className="ml-auto">
          {submitting ? 'Starting…' : 'Start export'}
        </Button>
      </div>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-label text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </p>
      )}
    </form>
  )
}
