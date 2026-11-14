const minus = '−'

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const rounded = Number.isInteger(value) ? value : Math.round(value * 10) / 10
  return `${rounded < 0 ? minus : ''}${Math.abs(rounded)} s`
}

export function signedSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value > 0 ? `+${seconds(value)}` : seconds(value)
}

export const percent = (fraction: number) => `${Math.round(fraction * 1000) / 10} %`
export const metres = (value: number | null | undefined) => value === null || value === undefined ? 'Unset' : `${value} m`

const reasonText: Record<string, string> = {
  native_spacing_too_coarse: 'Native posting is coarser than required',
  effective_scale_too_coarse: 'Effective scale is coarser than required',
  no_usable_product_meets_requirements: 'No usable product meets the requirements',
  requirements_unsatisfied: 'Requirements not satisfied',
}
export const describeReason = (code: string) => reasonText[code] ?? code.replaceAll('_', ' ')

export const statusText: Record<string, string> = {
  OK: 'Return within reserve',
  RETURN_OVER_RESERVE: 'Direct return exceeds the reserve',
  NO_RETURN_ROUTE: 'No return route with these closures',
}
