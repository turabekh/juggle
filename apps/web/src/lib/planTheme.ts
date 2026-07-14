// Party Planner templates (ADR-0011 party page) — pure CSS-variable skins, no assets.
// Each template maps to a hero gradient, an accent colour, a headline emoji, and a set of
// decoration emojis; the party page applies these as inline custom properties so the whole page
// re-skins with the host's choice. Keys must stay in sync with the backend THEMES allow-list.
// The template is a *style* choice only — the child's gender is never stored (INV-3).

export interface PlanTheme {
  key: string
  label: string
  emoji: string
  decorations: string[]
  vars: Record<string, string>
}

function skin(from: string, to: string, accent: string): Record<string, string> {
  return { '--pt-from': from, '--pt-to': to, '--pt-accent': accent, '--pt-on-accent': '#ffffff' }
}

const THEMES: Record<string, PlanTheme> = {
  default: {
    key: 'default',
    label: 'Party',
    emoji: '🎉',
    decorations: ['🎈', '🎊', '🎂', '🥳'],
    vars: skin('#fff4e6', '#ffe9f2', '#c2185b'),
  },
  unicorn: {
    key: 'unicorn',
    label: 'Unicorn',
    emoji: '🦄',
    decorations: ['🌈', '✨', '☁️', '🦄'],
    vars: skin('#fdeafe', '#e8e6ff', '#ab47bc'),
  },
  princess: {
    key: 'princess',
    label: 'Princess',
    emoji: '👑',
    decorations: ['👑', '🎀', '🌸', '💖'],
    vars: skin('#ffe6f0', '#ffd9ec', '#d81b60'),
  },
  superhero: {
    key: 'superhero',
    label: 'Superhero',
    emoji: '🦸',
    decorations: ['⚡', '💥', '🌟', '🦸'],
    vars: skin('#e3f2fd', '#ffebee', '#1565c0'),
  },
  dino: {
    key: 'dino',
    label: 'Dinosaur',
    emoji: '🦖',
    decorations: ['🌋', '🦕', '🌴', '🦖'],
    vars: skin('#e7f6e7', '#d3f0dd', '#2e7d32'),
  },
  space: {
    key: 'space',
    label: 'Space',
    emoji: '🚀',
    decorations: ['🪐', '⭐', '🌙', '🚀'],
    vars: skin('#e8eaf6', '#e3e0f7', '#3949ab'),
  },
  rainbow: {
    key: 'rainbow',
    label: 'Rainbow',
    emoji: '🌈',
    decorations: ['🌈', '🎈', '🎉', '🎂'],
    vars: skin('#fff3e0', '#e0f7fa', '#f4511e'),
  },
  mermaid: {
    key: 'mermaid',
    label: 'Under the Sea',
    emoji: '🧜',
    decorations: ['🐠', '🐚', '🌊', '🧜'],
    vars: skin('#e0f7fa', '#e0f2f1', '#00838f'),
  },
  jungle: {
    key: 'jungle',
    label: 'Jungle Safari',
    emoji: '🐵',
    decorations: ['🌴', '🦁', '🐘', '🐵'],
    vars: skin('#f1f8e9', '#e8f5e9', '#558b2f'),
  },
}

export const PLAN_THEMES: PlanTheme[] = Object.values(THEMES)

export function planTheme(key: string | undefined | null): PlanTheme {
  return THEMES[key ?? 'default'] ?? THEMES.default
}
