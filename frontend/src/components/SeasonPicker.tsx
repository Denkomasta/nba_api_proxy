import { Button } from 'denval-ui'
import type { ReactNode } from 'react'

/** "2004-05" -> "2000s" */
function decade(season: string): string {
  return `${season.slice(0, 3)}0s`
}

/** Toggle any number of seasons, laid out one decade per row. `seasons` comes newest first. */
export function SeasonPicker({
  seasons,
  value,
  onChange,
  hint,
}: {
  seasons: string[]
  value: string[]
  onChange: (value: string[]) => void
  hint?: ReactNode
}) {
  const selected = new Set(value)
  const decades = new Map<string, string[]>()
  for (const season of seasons) {
    decades.set(decade(season), [...(decades.get(decade(season)) ?? []), season])
  }

  function toggle(season: string) {
    onChange(selected.has(season) ? value.filter((s) => s !== season) : [...value, season].sort())
  }

  return (
    <fieldset className="relative">
      <legend className="mb-1.5 text-label font-medium text-secondary">
        Seasons{' '}
        <span className="font-normal text-subtle">
          ({value.length ? `${value.length} selected` : 'any, use the dates'})
        </span>
      </legend>
      {value.length > 0 && (
        <Button variant="ghost" size="sm" onClick={() => onChange([])} className="absolute -top-1 right-0 py-0.5">
          Clear
        </Button>
      )}
      <div className="space-y-1.5 rounded-lg border border-border bg-surface p-2">
        {[...decades].map(([name, list]) => (
          <div key={name} className="flex items-start gap-2">
            <span className="w-12 shrink-0 pt-1.5 text-caption text-subtle">{name}</span>
            <div className="flex flex-wrap gap-1">
              {[...list].reverse().map((season) => (
                <Button
                  key={season}
                  size="sm"
                  variant={selected.has(season) ? 'solid' : 'ghost'}
                  aria-pressed={selected.has(season)}
                  onClick={() => toggle(season)}
                  className="px-2 tabular-nums"
                >
                  {season}
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {hint && <p className="mt-1.5 text-caption text-subtle">{hint}</p>}
    </fieldset>
  )
}
