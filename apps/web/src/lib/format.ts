// Display helpers — currency (AUD), dates, ages, categories.

import type { ConnectStatus } from '@/lib/types'

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

// Stripe Connect payout-setup state → chip + copy + CTA (PRD §8.4 · F-PAY-1).
export interface PayoutSetupDisplay {
  color: string
  label: string
  hint: string
  needsSetup: boolean
  ctaLabel: string
}

export function payoutSetupDisplay(status: ConnectStatus | null): PayoutSetupDisplay {
  if (status?.payouts_enabled) {
    return {
      color: 'positive',
      label: 'Active',
      hint: "Payouts are active — you're paid a few days after each session.",
      needsSetup: false,
      ctaLabel: 'Set up payouts',
    }
  }
  if (status?.onboarded) {
    return {
      color: 'warning',
      label: 'In review',
      hint: 'Stripe is verifying your details. This usually takes a few minutes.',
      needsSetup: true,
      ctaLabel: 'Finish Stripe setup',
    }
  }
  return {
    color: 'grey-6',
    label: 'Not set up',
    hint: 'Connect a Stripe account to receive payouts from your bookings.',
    needsSetup: true,
    ctaLabel: 'Set up payouts',
  }
}
