import { useCallback, useEffect, useState } from 'react'
import { api, type Job, type Options } from './api'
import { ExportForm } from './components/ExportForm'
import { ExportList } from './components/ExportList'

const POLL_MS = 1500

export default function App() {
  const [options, setOptions] = useState<Options | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    api.exports().then(setJobs, (e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    api.options().then(setOptions, (e: Error) => setError(`Backend not reachable: ${e.message}`))
    refresh()
  }, [refresh])

  // Poll while an export is queued or running
  const active = jobs.some((job) => job.status === 'queued' || job.status === 'running')
  useEffect(() => {
    if (!active) return
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [active, refresh])

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <header className="mb-10">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">NBA data export</h1>
        <p className="mt-2 max-w-2xl text-zinc-600 dark:text-zinc-400">
          Pick filters, start an export, download it as CSV or JSON. Data comes from stats.nba.com and the NBA live feed
          via <code className="text-sm">nba_api</code>.
        </p>
      </header>

      {error && (
        <p role="alert" className="mb-6 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/50 dark:text-red-300">
          {error}
        </p>
      )}

      <div className="grid gap-10 lg:grid-cols-[3fr_2fr]">
        <section aria-labelledby="new-title">
          <h2 id="new-title" className="mb-4 text-sm font-semibold tracking-wide text-zinc-500 uppercase">
            New export
          </h2>
          <div className="rounded-xl border border-zinc-200 bg-white p-5 sm:p-6 dark:border-zinc-800 dark:bg-zinc-900">
            {options ? (
              <ExportForm options={options} onCreated={(job) => setJobs((all) => [job, ...all])} />
            ) : (
              <p className="text-sm text-zinc-500">Loading…</p>
            )}
          </div>
        </section>

        <section aria-labelledby="exports-title">
          <h2 id="exports-title" className="mb-4 text-sm font-semibold tracking-wide text-zinc-500 uppercase">
            Exports
          </h2>
          <ExportList jobs={jobs} teams={options?.teams ?? []} onChanged={refresh} />
        </section>
      </div>
    </div>
  )
}
