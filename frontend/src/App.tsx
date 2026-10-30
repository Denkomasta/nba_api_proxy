import { Alert, AlertVariant, Card, Container, Heading, Section } from 'denval-ui'
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
    <Container className="py-10">
      <header className="mb-10">
        <Heading as="h1" variant="display">
          NBA data export
        </Heading>
        <p className="mt-3 max-w-2xl text-muted">
          Pick filters, start an export, download it as CSV or JSON. Data comes from stats.nba.com and the NBA live feed
          via <code className="text-label">nba_api</code>.
        </p>
      </header>

      {error && <Alert role="alert" variant={AlertVariant.Error} text={error} className="mb-6" />}

      <div className="grid gap-10 lg:grid-cols-[3fr_2fr]">
        <Section id="new" title="New export" className="py-0">
          <Card>
            {options ? (
              <ExportForm options={options} onCreated={(job) => setJobs((all) => [job, ...all])} />
            ) : (
              <p className="text-label text-subtle">Loading…</p>
            )}
          </Card>
        </Section>

        <Section id="exports" title="Exports" className="py-0">
          <ExportList jobs={jobs} teams={options?.teams ?? []} onChanged={refresh} />
        </Section>
      </div>
    </Container>
  )
}
