import { describe, expect, it } from 'vitest'

import { PLAN_THEMES, planTheme } from './planTheme'

describe('planTheme', () => {
  it('exposes the party page templates (must match the backend THEMES allow-list)', () => {
    expect(PLAN_THEMES.map((t) => t.key)).toEqual([
      'default', 'unicorn', 'princess', 'superhero', 'dino', 'space', 'rainbow', 'mermaid', 'jungle',
    ])
  })

  it('resolves a known template with its emoji, decorations + CSS vars', () => {
    const dino = planTheme('dino')
    expect(dino.emoji).toBe('🦖')
    expect(dino.decorations.length).toBeGreaterThan(0)
    expect(dino.vars['--pt-accent']).toBeTruthy()
  })

  it('falls back to default for unknown or nullish keys', () => {
    expect(planTheme('hacker').key).toBe('default')
    expect(planTheme(null).key).toBe('default')
    expect(planTheme(undefined).key).toBe('default')
  })
})
