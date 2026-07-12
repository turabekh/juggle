// Party Planner theme skins (ADR-0011 Milestone C) — pure CSS-variable variants, no assets.
// Each theme maps to a hero gradient, an accent colour, and a headline emoji; the invitee page
// applies these as inline custom properties so the whole page re-skins with the host's choice.

export interface PlanTheme {
  key: string
  label: string
  emoji: string
  vars: Record<string, string>
}

const THEMES: Record<string, PlanTheme> = {
  default: {
    key: 'default',
    label: 'Party',
    emoji: '🎉',
    vars: {
      '--pt-from': '#fff4e6',
      '--pt-to': '#ffe9f2',
      '--pt-accent': '#c2185b',
      '--pt-on-accent': '#ffffff',
    },
  },
  dino: {
    key: 'dino',
    label: 'Dinosaur',
    emoji: '🦖',
    vars: {
      '--pt-from': '#e7f6e7',
      '--pt-to': '#d3f0dd',
      '--pt-accent': '#2e7d32',
      '--pt-on-accent': '#ffffff',
    },
  },
  space: {
    key: 'space',
    label: 'Space',
    emoji: '🚀',
    vars: {
      '--pt-from': '#e8eaf6',
      '--pt-to': '#e3e0f7',
      '--pt-accent': '#3949ab',
      '--pt-on-accent': '#ffffff',
    },
  },
  unicorn: {
    key: 'unicorn',
    label: 'Unicorn',
    emoji: '🦄',
    vars: {
      '--pt-from': '#fdeafe',
      '--pt-to': '#e8e6ff',
      '--pt-accent': '#ab47bc',
      '--pt-on-accent': '#ffffff',
    },
  },
}

export const PLAN_THEMES: PlanTheme[] = Object.values(THEMES)

export function planTheme(key: string | undefined | null): PlanTheme {
  return THEMES[key ?? 'default'] ?? THEMES.default
}
