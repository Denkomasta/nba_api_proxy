import type { ReactNode } from 'react'

export const inputClass =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm shadow-xs focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900'

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>}
    </label>
  )
}

export interface Choice<T extends string> {
  value: T
  label: string
}

/** A row of mutually exclusive buttons, like a radio group. */
export function Segmented<T extends string>({
  label,
  value,
  choices,
  onChange,
}: {
  label: string
  value: T
  choices: Choice<T>[]
  onChange: (value: T) => void
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-zinc-700 dark:text-zinc-300">{label}</legend>
      <div className="flex rounded-lg border border-zinc-300 bg-white p-0.5 dark:border-zinc-700 dark:bg-zinc-900">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            aria-pressed={choice.value === value}
            onClick={() => onChange(choice.value)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm transition-colors ${
              choice.value === value
                ? 'bg-accent font-medium text-white dark:text-zinc-950'
                : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800'
            }`}
          >
            {choice.label}
          </button>
        ))}
      </div>
    </fieldset>
  )
}
