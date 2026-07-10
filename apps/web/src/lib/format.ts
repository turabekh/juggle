// Display helpers — currency (AUD), dates, ages, categories.

const AUD = new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' })

export function money(cents: number): string {
  return AUD.format(cents / 100)
}

export function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString('en-AU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

export function timeRange(startIso: string, endIso: string): string {
  const opts: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }
  const start = new Date(startIso).toLocaleTimeString('en-AU', opts)
  const end = new Date(endIso).toLocaleTimeString('en-AU', opts)
  return `${start} – ${end}`
}

export function ageAt(dob: string, at: string): number {
  const d = new Date(dob)
  const on = new Date(at)
  let age = on.getFullYear() - d.getFullYear()
  const m = on.getMonth() - d.getMonth()
  if (m < 0 || (m === 0 && on.getDate() < d.getDate())) age -= 1
  return age
}

export function ageBand(min: number, max: number): string {
  return `Ages ${min}–${max}`
}

export function distanceLabel(km: number | null): string | null {
  if (km === null) return null
  return km < 1 ? `${Math.round(km * 1000)} m away` : `${km.toFixed(1)} km away`
}

export const CATEGORIES = [
  { value: 'sport', label: 'Sport', icon: 'sports_soccer' },
  { value: 'art', label: 'Art', icon: 'palette' },
  { value: 'stem', label: 'STEM', icon: 'science' },
  { value: 'drama', label: 'Drama', icon: 'theater_comedy' },
  { value: 'outdoor', label: 'Outdoor', icon: 'forest' },
  { value: 'other', label: 'Other', icon: 'category' },
] as const

export function categoryMeta(value: string): { label: string; icon: string } {
  return CATEGORIES.find((c) => c.value === value) ?? { label: value, icon: 'category' }
}
