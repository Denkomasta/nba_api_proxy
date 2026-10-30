import { Button } from 'denval-ui'
import type { ReactNode } from 'react'
import { type Control, type FieldPath, type FieldPathValue, type FieldValues, useController } from 'react-hook-form'

// Form controls denval-ui doesn't have yet, built on its colour tokens

export const inputClass =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-label text-foreground shadow-xs focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none'

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-label font-medium text-secondary">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-caption text-subtle">{hint}</span>}
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
      <legend className="mb-1.5 text-label font-medium text-secondary">{label}</legend>
      <div className="flex rounded-control border border-border bg-surface p-0.5">
        {choices.map((choice) => (
          <Button
            key={choice.value}
            variant={choice.value === value ? 'solid' : 'ghost'}
            aria-pressed={choice.value === value}
            onClick={() => onChange(choice.value)}
            className="flex-1 px-3 py-1.5"
          >
            {choice.label}
          </Button>
        ))}
      </div>
    </fieldset>
  )
}

/** `Segmented` connected to a field of a react-hook-form form. */
export function SegmentedField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  choices,
}: {
  control: Control<T>
  name: N
  label: string
  choices: Choice<FieldPathValue<T, N> & string>[]
}) {
  const { field } = useController({ control, name })
  return <Segmented label={label} value={field.value} choices={choices} onChange={field.onChange} />
}
