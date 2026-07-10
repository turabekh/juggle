<template>
  <q-page class="jg-page" style="max-width: 780px">
    <h1 class="text-h4 q-mb-lg">Your cart</h1>

    <div v-if="cart.items.length" class="jg-cart">
      <div v-for="item in cart.items" :key="item.holdId" class="jg-card jg-cartrow">
        <div class="jg-cartrow__main">
          <div class="text-weight-600">{{ item.title }}</div>
          <div class="jg-muted text-caption">{{ item.orgName }} · {{ item.venueName }}</div>
          <div class="jg-muted text-caption q-mt-xs">
            <q-icon name="event" size="14px" /> {{ dayLabel(item.startsAt) }} ·
            {{ timeRange(item.startsAt, item.endsAt) }}
          </div>
          <span class="jg-pill jg-pill--muted q-mt-sm">
            {{ item.childIds.length }} {{ item.childIds.length === 1 ? 'child' : 'children' }}
          </span>
        </div>
        <div class="jg-cartrow__side">
          <div class="text-weight-700">{{ money(item.priceCents * item.childIds.length) }}</div>
          <q-btn
            flat
            dense
            round
            icon="close"
            size="sm"
            class="jg-faint"
            aria-label="Remove"
            @click="remove(item.holdId)"
          />
        </div>
      </div>

      <div class="jg-card jg-cart__summary">
        <div class="row items-center justify-between">
          <span class="text-subtitle1 text-weight-600">Total</span>
          <span class="text-h6">{{ money(cart.totalCents) }}</span>
        </div>
        <div class="jg-faint text-caption q-mb-md">
          {{ cart.seatCount }} seat(s) across {{ cart.count }} session(s)
        </div>
        <q-btn
          unelevated
          color="primary"
          no-caps
          size="lg"
          class="full-width"
          label="Proceed to checkout"
          @click="goCheckout"
        />
      </div>
    </div>

    <EmptyState
      v-else
      icon="shopping_bag"
      title="Your cart is empty"
      subtitle="Find something fun and add your kids to hold their spot."
    >
      <q-btn unelevated color="primary" no-caps label="Browse activities" :to="{ name: 'discover' }" />
    </EmptyState>
  </q-page>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { dayLabel, money, timeRange } from '@/lib/format'
import { useCartStore } from '@/stores/cart'

const cart = useCartStore()
const router = useRouter()

async function remove(holdId: string): Promise<void> {
  await cart.removeItem(holdId)
}

function goCheckout(): void {
  router.push({ name: 'checkout' })
}
</script>

<style scoped>
.jg-cart { display: flex; flex-direction: column; gap: 14px; }
.jg-cartrow {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 18px;
}
.jg-cartrow__side { display: flex; align-items: center; gap: 8px; }
.jg-cart__summary { padding: 20px; margin-top: 6px; }
</style>
