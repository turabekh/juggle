import { describe, expect, it } from 'vitest'

import { PLAN_THEMES, planTheme } from './planTheme'

describe('planTheme', () => {
  it('exposes the four launch themes', () => {
    expect(PLAN_THEMES.map((t) => t.key)).toEqual(['default', 'dino', 'space', 'unicorn'])
  })

  it('resolves a known theme with its emoji + CSS vars', () => {
    const dino = planTheme('dino')
    expect(dino.emoji).toBe('🦖')
    expect(dino.vars['--pt-accent']).toBeTruthy()
  })

  it('falls back to default for unknown or nullish keys', () => {
    expect(planTheme('hacker').key).toBe('default')
    expect(planTheme(null).key).toBe('default')
    expect(planTheme(undefined).key).toBe('default')
  })
})
