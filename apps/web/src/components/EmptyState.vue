<template>
  <div class="jg-empty">
    <div class="jg-empty__icon">
      <q-icon :name="icon" size="30px" color="primary" />
    </div>
    <div class="text-h6 q-mt-md">{{ title }}</div>
    <div class="jg-muted q-mt-xs" v-if="subtitle">{{ subtitle }}</div>
    <div class="q-mt-lg"><slot /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ icon: string; title: string; subtitle?: string }>()
</script>

<style scoped>
.jg-empty {
  text-align: center;
  padding: 56px 20px;
  max-width: 440px;
  margin: 0 auto;
}
.jg-empty__icon {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  border-radius: 20px;
  display: grid;
  place-items: center;
  background: var(--jg-primary-tint);
}
</style>
