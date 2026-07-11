import { describe, expect, it } from 'vitest'

import { ageAt, ageBand, categoryMeta, distanceLabel, money } from '@/lib/format'

describe('money', () => {
  it('formats cents as AUD', () => {
    expect(money(5000)).toBe('$50.00')
    expect(money(0)).toBe('$0.00')
    expect(money(4599)).toBe('$45.99')
  })
})

describe('ageAt', () => {
  it('computes whole years, respecting the month/day', () => {
    expect(ageAt('2018-06-01', '2026-06-01')).toBe(8)
    // Birthday not yet reached in the target year → one year younger.
    expect(ageAt('2018-06-02', '2026-06-01')).toBe(7)
  })
})

describe('ageBand', () => {
  it('renders an inclusive band', () => {
    expect(ageBand(4, 12)).toBe('Ages 4–12')
  })
})

describe('distanceLabel', () => {
  it('uses metres under 1km and one-dp km otherwise', () => {
    expect(distanceLabel(null)).toBeNull()
    expect(distanceLabel(0.4)).toBe('400 m away')
    expect(distanceLabel(3.25)).toBe('3.3 km away')
  })
})

describe('categoryMeta', () => {
  it('maps known categories to a label + icon', () => {
    expect(categoryMeta('art')).toMatchObject({ label: 'Art', icon: 'palette' })
    expect(categoryMeta('stem').label).toBe('STEM')
  })
  it('falls back for unknown categories', () => {
    expect(categoryMeta('mystery')).toEqual({ label: 'mystery', icon: 'category' })
  })
})
