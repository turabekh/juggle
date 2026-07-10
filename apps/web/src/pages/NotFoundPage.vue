<template>
  <div class="jg-notfound">
    <EmptyState
      icon="explore_off"
      title="Page not found"
      subtitle="That link led nowhere. Let's get you back to the good stuff."
    >
      <q-btn unelevated color="primary" no-caps label="Back to Juggle" :to="{ name: 'discover' }" />
    </EmptyState>
  </div>
</template>

<script setup lang="ts">
import EmptyState from '@/components/EmptyState.vue'
</script>

<style scoped>
.jg-notfound {
  min-height: 100vh;
  display: grid;
  place-items: center;
}
</style>
