<template>
  <div class="jg-hero" :style="theme.vars">
    <div class="jg-hero__deco jg-hero__deco--l">{{ theme.decorations[0] }}</div>
    <div class="jg-hero__deco jg-hero__deco--r">{{ theme.decorations[1] }}</div>
    <div class="jg-hero__avatar">{{ heroGlyph }}</div>
    <h1 class="jg-hero__title">{{ title || "You're invited!" }}</h1>
    <p v-if="subtitle" class="jg-hero__sub">{{ subtitle }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { avatarEmoji } from '@/lib/partyPage'
import { planTheme } from '@/lib/planTheme'

const props = defineProps<{
  template: string | null | undefined
  title?: string | null
  heroAvatar?: string | null
  subtitle?: string | null
}>()

const theme = computed(() => planTheme(props.template))
// The host-picked sticker if set, else the template's headline emoji.
const heroGlyph = computed(() => (props.heroAvatar ? avatarEmoji(props.heroAvatar) : theme.value.emoji))
</script>

<style scoped>
.jg-hero {
  position: relative;
  text-align: center;
  padding: 28px 20px 24px;
  background: linear-gradient(120% 140% at 15% 0%, var(--pt-from, #fff4e6) 0%, var(--pt-to, #ffe9f2) 100%);
  border-radius: 18px;
  overflow: hidden;
}
.jg-hero__avatar {
  font-size: 52px;
  line-height: 1;
  animation: jg-bob 2.4s ease-in-out infinite;
}
.jg-hero__title {
  font-size: 26px;
  line-height: 1.15;
  margin: 8px 0 2px;
  color: var(--jg-ink, #1a1a2e);
  word-break: break-word;
}
.jg-hero__sub {
  color: var(--jg-ink-soft, #5a5a6e);
  margin: 0;
  font-size: 14px;
}
.jg-hero__deco {
  position: absolute;
  top: 14px;
  font-size: 26px;
  opacity: 0.55;
}
.jg-hero__deco--l {
  left: 16px;
  transform: rotate(-12deg);
}
.jg-hero__deco--r {
  right: 16px;
  transform: rotate(12deg);
}
@keyframes jg-bob {
  0%, 100% { transform: translateY(0) rotate(-3deg); }
  50% { transform: translateY(-6px) rotate(3deg); }
}
</style>
