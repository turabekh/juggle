// Shared party-page assets: the avatar sticker set + widget metadata. Used by the public invitee
// page, the host editor, and the live preview so they stay in sync. Avatar/widget keys mirror the
// backend allow-lists (AVATAR_KEYS / WIDGET_KEYS_ORDER).

import type { PartyWidgetKey } from '@/lib/types'

export interface Avatar {
  key: string
  emoji: string
}

export const AVATARS: Avatar[] = [
  { key: 'dino', emoji: '🦖' },
  { key: 'rocket', emoji: '🚀' },
  { key: 'unicorn', emoji: '🦄' },
  { key: 'star', emoji: '⭐' },
  { key: 'cat', emoji: '🐱' },
  { key: 'dog', emoji: '🐶' },
  { key: 'robot', emoji: '🤖' },
  { key: 'fox', emoji: '🦊' },
  { key: 'panda', emoji: '🐼' },
  { key: 'owl', emoji: '🦉' },
  { key: 'dragon', emoji: '🐲' },
  { key: 'balloon', emoji: '🎈' },
]

export function avatarEmoji(key: string | null | undefined): string {
  return AVATARS.find((a) => a.key === key)?.emoji ?? '🎈'
}

export interface WidgetMeta {
  key: PartyWidgetKey
  label: string
  hint: string
  icon: string
}

export const WIDGETS: WidgetMeta[] = [
  { key: 'welcome', label: 'Welcome note', hint: 'A short message from you', icon: 'waving_hand' },
  {
    key: 'countdown',
    label: 'Countdown & decorations',
    hint: 'Ticking timer + theme confetti',
    icon: 'timer',
  },
  {
    key: 'board',
    label: "Who's coming & reactions",
    hint: 'Guest avatars + emoji reactions',
    icon: 'groups',
  },
  {
    key: 'reveal_venue',
    label: 'Winning venue & map',
    hint: 'Shown once voting closes',
    icon: 'place',
  },
]

// The resolved page.widgets is always the full enabled list from the server; fall back to
// "all on" defensively if it is ever empty.
export function widgetOn(widgets: PartyWidgetKey[], key: PartyWidgetKey): boolean {
  return widgets.length === 0 || widgets.includes(key)
}
