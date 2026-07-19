<template>
  <div class="jg-preview" :style="theme.vars">
    <div class="jg-preview__frame">
      <PartyHero :template="page.template" :title="page.title" :hero-avatar="page.hero_avatar"
                 subtitle="Help pick the party — vote for your favourite!" />

      <div v-if="showWelcome" class="jg-preview__card jg-preview__welcome">
        <q-icon name="waving_hand" size="16px" class="q-mr-xs" :style="{ color: 'var(--pt-accent)' }" />
        {{ page.message }}
      </div>

      <div v-if="on('countdown')" class="jg-preview__count">
        <div class="jg-preview__deco"><span v-for="(d, i) in theme.decorations" :key="i">{{ d }}</span></div>
        <div class="jg-preview__time">2d 6h left</div>
      </div>

      <div class="jg-preview__card">
        <div class="jg-preview__label">Vote for the party</div>
        <div v-for="o in sampleOptions" :key="o.id" class="jg-preview__opt">
          <span class="ellipsis">{{ optionLabel(o) }}</span>
          <span class="jg-preview__votes">{{ o.votes }}</span>
        </div>
        <div v-if="!sampleOptions.length" class="jg-preview__muted">Add party options to see them here</div>
      </div>

      <div v-if="on('board')" class="jg-preview__card">
        <div class="jg-preview__label">Who's coming</div>
        <div class="jg-preview__avatars">
          <span v-for="(a, i) in sampleAvatars" :key="i">{{ a }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import PartyHero from '@/components/PartyHero.vue'
import { widgetOn } from '@/lib/partyPage'
import { planTheme } from '@/lib/planTheme'
import type { PartyPagePatch, PlanOptionView } from '@/lib/types'

const props = defineProps<{ page: PartyPagePatch; options: PlanOptionView[] }>()

const theme = computed(() => planTheme(props.page.template))
const showWelcome = computed(() => widgetOn(props.page.widgets, 'welcome') && !!props.page.message)
const on = (key: 'countdown' | 'board'): boolean => widgetOn(props.page.widgets, key)
const sampleOptions = computed(() => props.options.filter((o) => !o.voided).slice(0, 3))
const sampleAvatars = ['🦖', '🦄', '🚀', '🐼']

function optionLabel(o: PlanOptionView): string {
  return o.kind === 'custom' ? o.custom_text || 'Custom idea' : o.package_name || 'Party package'
}
</script>

<style scoped>
.jg-preview__frame {
  border: 8px solid #1a1a2e;
  border-radius: 26px;
  padding: 10px;
  background: linear-gradient(180deg, var(--pt-from, #fff4e6) 0%, #ffffff 42%);
  max-width: 320px;
  margin: 0 auto;
}
.jg-preview__card {
  background: #fff;
  border: 1px solid var(--jg-line, #e6e6ef);
  border-radius: 12px;
  padding: 10px 12px;
  margin-top: 10px;
  font-size: 13px;
}
.jg-preview__welcome { white-space: pre-wrap; line-height: 1.4; }
.jg-preview__label { font-weight: 600; margin-bottom: 6px; }
.jg-preview__opt {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--jg-line, #f0f0f5);
}
.jg-preview__opt:last-child { border-bottom: 0; }
.jg-preview__votes { font-weight: 700; color: var(--pt-accent, var(--jg-primary)); }
.jg-preview__muted { color: var(--jg-ink-soft, #8a8a9e); font-size: 12px; }
.jg-preview__count {
  text-align: center;
  margin-top: 10px;
  padding: 10px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--pt-accent, #7b1fa2) 8%, #fff);
  border: 1px solid color-mix(in srgb, var(--pt-accent, #7b1fa2) 22%, transparent);
}
.jg-preview__deco { font-size: 18px; letter-spacing: 5px; }
.jg-preview__time { font-weight: 700; color: var(--pt-accent, var(--jg-primary)); font-size: 15px; }
.jg-preview__avatars { font-size: 22px; letter-spacing: 4px; }
</style>
