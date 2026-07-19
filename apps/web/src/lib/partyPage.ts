// Shared party-page assets: the avatar sticker set + widget metadata. Used by the public invitee
// page, the host editor, and the live preview so they stay in sync. Avatar/widget keys mirror the
// backend allow-lists (AVATAR_KEYS / WIDGET_KEYS_ORDER).

import { dayLabel } from '@/lib/format'
import { planTheme } from '@/lib/planTheme'
import type { PartyWidgetKey, PlanView } from '@/lib/types'

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

// --- Plan list presentation (shared by the parties page, plans list, manage header) ---------

// Prefer the host's party title; else name it after the first package option; else a placeholder.
export function planDisplayTitle(p: PlanView): string {
  if (p.page.title) return p.page.title
  const first = p.options.find((o) => o.kind === 'package' && o.package_name)
  return first?.package_name ? `${first.package_name} + more` : 'Untitled party vote'
}

// The plan's hero glyph for compact cards: the host's chosen avatar, else the template emoji.
export function planGlyph(p: PlanView): string {
  return p.page.hero_avatar ? avatarEmoji(p.page.hero_avatar) : planTheme(p.page.template).emoji
}

// One-line summary: options · invited · deadline.
export function planSummary(p: PlanView): string {
  const opts = p.options.filter((o) => !o.voided).length
  const base = `${opts} option${opts === 1 ? '' : 's'} · ${p.invites.length} invited`
  return p.deadline_at ? `${base} · votes close ${dayLabel(p.deadline_at)}` : base
}

export const PLAN_STATUS: Record<string, { label: string; color: string }> = {
  draft: { label: 'Draft', color: 'grey-6' },
  open: { label: 'Voting open', color: 'primary' },
  resolved: { label: 'Ready to book', color: 'deep-orange' },
  booked: { label: 'Booked', color: 'positive' },
  expired_unbooked: { label: 'Closed', color: 'grey-5' },
}
export const planStatusLabel = (s: string): string => PLAN_STATUS[s]?.label ?? s
export const planStatusColor = (s: string): string => PLAN_STATUS[s]?.color ?? 'grey'
