import { SegmentedControl, type ToggleOption } from 'denval-ui'
import type { ReactNode } from 'react'
import { type Control, type FieldPath, type FieldPathValue, type FieldValues, useController } from 'react-hook-form'

/** denval-ui's `SegmentedControl` connected to a field of a react-hook-form form */
export function SegmentedField<T extends FieldValues, N extends FieldPath<T>>({
  control,
  name,
  label,
  hint,
  options,
}: {
  control: Control<T>
  name: N
  label: string
  hint?: ReactNode
  options: ToggleOption<FieldPathValue<T, N> & string>[]
}) {
  const { field } = useController({ control, name })
  return <SegmentedControl label={label} hint={hint} value={field.value} options={options} onChange={field.onChange} />
}
