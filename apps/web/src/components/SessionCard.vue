<template>
  <router-link :to="{ name: 'session', params: { id: card.session_id } }" class="jg-scard-link">
    <article class="jg-card jg-card--hover jg-scard">
      <header class="jg-scard__top">
        <span class="jg-pill">
          <q-icon :name="cat.icon" size="15px" />
          {{ cat.label }}
        </span>
        <span
          class="jg-pill"
          :class="card.seats_remaining <= 3 ? 'jg-pill--warm' : 'jg-pill--muted'"
        >
          {{ card.seats_remaining > 0 ? `${card.seats_remaining} left` : 'Full' }}
        </span>
      </header>

      <h3 class="jg-scard__title">{{ card.title }}</h3>
      <div class="jg-muted jg-scard__org">{{ card.organisation_name }}</div>

      <div class="jg-scard__meta">
        <span><q-icon name="event" size="16px" /> {{ dayLabel(card.starts_at) }}</span>
        <span><q-icon name="schedule" size="16px" /> {{ timeRange(card.starts_at, card.ends_at) }}</span>
      </div>
      <div class="jg-scard__meta">
        <span class="ellipsis">
          <q-icon name="place" size="16px" />
          {{ card.venue_name }}<template v-if="card.suburb">, {{ card.suburb }}</template>
        </span>
        <span v-if="distance" class="jg-faint">· {{ distance }}</span>
      </div>

      <footer class="jg-scard__foot">
        <div>
          <span class="jg-scard__price">{{ money(card.price_cents) }}</span>
          <span class="jg-faint jg-scard__per">/ child</span>
        </div>
        <span class="jg-pill jg-pill--muted">{{ ageBand(card.age_min, card.age_max) }}</span>
      </footer>
    </article>
  </router-link>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { ageBand, categoryMeta, dayLabel, distanceLabel, money, timeRange } from '@/lib/format'
import type { SearchCard } from '@/lib/types'

const props = defineProps<{ card: SearchCard }>()

const cat = computed(() => categoryMeta(props.card.category))
const distance = computed(() => distanceLabel(props.card.distance_km))
</script>

<style scoped>
.jg-scard-link {
  text-decoration: none;
  color: inherit;
  display: block;
  height: 100%;
}
.jg-scard {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
}
.jg-scard__top {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.jg-scard__title {
  font-size: 18px;
  line-height: 1.25;
  margin: 2px 0 0;
}
.jg-scard__org { font-size: 13.5px; }
.jg-scard__meta {
  display: flex;
  gap: 14px;
  align-items: center;
  color: var(--jg-ink-soft);
  font-size: 13.5px;
  margin-top: 6px;
}
.jg-scard__meta .q-icon { color: var(--jg-ink-faint); vertical-align: -3px; margin-right: 3px; }
.jg-scard__foot {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--jg-line);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.jg-scard__price { font-weight: 700; font-size: 17px; }
.jg-scard__per { font-size: 12.5px; margin-left: 2px; }
.ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
