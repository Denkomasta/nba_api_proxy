import { Alert, AlertVariant, Button } from 'denval-ui'
import { useController, useForm, useWatch } from 'react-hook-form'
import { api, type Dataset, type Format, type Job, type Options } from '../api'
import { Field, inputClass, MultiToggle, SegmentedField } from './controls'
import { SeasonPicker } from './SeasonPicker'

const datasets: Record<Dataset, { label: string; description: string }> = {
  games: {
    label: 'Games',
    description: 'One row per team per game with box score totals. A single request, ready in seconds.',
  },
  playbyplay: {
    label: 'Play-by-play',
    description:
      'An event log of every matching game, with one case per possession (case_id, activity, timestamp). One request per game ' +
      '(about 1–3 s each), cached games are instant.',
  },
}

const seasonTypeLabels: Record<string, string> = {
  PlayIn: 'Play-In',
  'Pre Season': 'Preseason',
  'All Star': 'All-Star',
}

// What the inputs hold: an empty string means "no filter"
interface FormValues {
  dataset: Dataset
  format: Format
  seasons: string[]
  seasonTypes: string[]
  teamId: string
  opponentId: string
  dateFrom: string
  dateTo: string
  location: '' | 'Home' | 'Road'
  outcome: '' | 'W' | 'L'
}

export function ExportForm({ options, onCreated }: { options: Options; onCreated: (job: Job) => void }) {
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    defaultValues: {
      dataset: 'playbyplay',
      format: 'csv',
      // Default to the last complete season
      seasons: options.seasons[1] ? [options.seasons[1]] : [],
      seasonTypes: ['Regular Season'],
      teamId: '',
      opponentId: '',
      dateFrom: '',
      dateTo: '',
      location: '',
      outcome: '',
    },
  })
  const dataset = useWatch({ control, name: 'dataset' })
  const { field: seasonsField } = useController({ control, name: 'seasons' })
  const seasons = seasonsField.value
  const { field: seasonTypesField } = useController({ control, name: 'seasonTypes' })

  // Before the live feed, timestamps come from the game clock, so they leave out stoppages
  const older = seasons.filter((s) => s < options.first_live_season).length
  const seasonHint =
    dataset !== 'playbyplay' || older === 0
      ? undefined
      : older === seasons.length
        ? `Before ${options.first_live_season} events have no wall-clock time, so timestamps are built from the game clock.`
        : `Seasons before ${options.first_live_season} have timestamps built from the game clock, later ones the real time. ` +
          'To compare durations across eras, use game_seconds. Group by the season column.'

  async function submit(values: FormValues) {
    const filters = {
      seasons: values.seasons.length ? values.seasons : undefined,
      season_types: values.seasonTypes.length ? values.seasonTypes : undefined,
      team_id: values.teamId ? Number(values.teamId) : undefined,
      opponent_team_id: values.opponentId ? Number(values.opponentId) : undefined,
      date_from: values.dateFrom || undefined,
      date_to: values.dateTo || undefined,
      location: values.location || undefined,
      outcome: values.outcome || undefined,
    }
    try {
      onCreated(await api.create({ dataset: values.dataset, format: values.format, filters }))
    } catch (e) {
      setError('root.server', { message: e instanceof Error ? e.message : String(e) })
    }
  }

  const teamOptions = options.teams.map((team) => (
    <option key={team.id} value={team.id}>
      {team.name}
    </option>
  ))
  const serverError = errors.root?.server?.message

  return (
    <form onSubmit={handleSubmit(submit)} className="space-y-6">
      <div>
        <SegmentedField
          control={control}
          name="dataset"
          label="Data"
          choices={(Object.keys(datasets) as Dataset[]).map((value) => ({ value, label: datasets[value].label }))}
        />
        <p className="mt-2 text-label text-muted">{datasets[dataset].description}</p>
      </div>

      <SeasonPicker seasons={options.seasons} value={seasons} onChange={seasonsField.onChange} hint={seasonHint} />

      <MultiToggle
        label={
          <>
            Season types{' '}
            <span className="font-normal text-subtle">
              ({seasonTypesField.value.length ? `${seasonTypesField.value.length} selected` : 'all'})
            </span>
          </>
        }
        value={seasonTypesField.value}
        choices={options.season_types.map((t) => ({ value: t, label: seasonTypeLabels[t] ?? t }))}
        onChange={seasonTypesField.onChange}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="From date">
          <input type="date" className={inputClass} {...register('dateFrom')} />
        </Field>
        <Field label="To date">
          <input type="date" className={inputClass} {...register('dateTo')} />
        </Field>
        <Field label="Team">
          <select className={inputClass} {...register('teamId')}>
            <option value="">All teams</option>
            {teamOptions}
          </select>
        </Field>
        <Field label="Opponent">
          <select className={inputClass} {...register('opponentId')}>
            <option value="">Any opponent</option>
            {teamOptions}
          </select>
        </Field>
        <SegmentedField
          control={control}
          name="location"
          label="Location (of the team)"
          choices={[
            { value: '', label: 'Any' },
            { value: 'Home', label: 'Home' },
            { value: 'Road', label: 'Away' },
          ]}
        />
        <SegmentedField
          control={control}
          name="outcome"
          label="Outcome (of the team)"
          choices={[
            { value: '', label: 'Any' },
            { value: 'W', label: 'Win' },
            { value: 'L', label: 'Loss' },
          ]}
        />
      </div>

      <div className="flex flex-wrap items-end gap-4 border-t border-divider pt-6">
        <div className="w-40">
          <SegmentedField
            control={control}
            name="format"
            label="File format"
            choices={[
              { value: 'csv', label: 'CSV' },
              { value: 'json', label: 'JSON' },
            ]}
          />
        </div>
        <Button type="submit" variant="solid" disabled={isSubmitting} className="ml-auto">
          {isSubmitting ? 'Starting…' : 'Start export'}
        </Button>
      </div>

      {serverError && <Alert role="alert" variant={AlertVariant.Error} text={serverError} />}
    </form>
  )
}
