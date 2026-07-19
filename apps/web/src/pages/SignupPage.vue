<template>
  <div class="jg-auth">
    <div class="jg-auth__card jg-card">
      <router-link :to="{ name: 'discover' }" class="jg-auth__brand">
        <span style="font-size: 24px">🤹</span>
        <span>Juggle</span>
      </router-link>
      <h1 class="text-h5 q-mt-md q-mb-xs">{{ heading }}</h1>
      <p class="jg-muted q-mb-md">{{ blurb }}</p>

      <q-btn-toggle
        v-model="audience"
        spread
        no-caps
        unelevated
        class="jg-audience q-mb-lg"
        toggle-color="primary"
        color="white"
        text-color="grey-8"
        :options="[
          { value: 'parent', label: 'I\'m a parent', icon: 'family_restroom' },
          { value: 'provider', label: 'I run activities', icon: 'storefront' },
        ]"
      />

      <q-form @submit="submit" class="q-gutter-md">
        <q-input v-model="fullName" outlined label="Your name" autofocus />
        <q-input v-model="email" outlined type="email" label="Email" :rules="[req]" />
        <q-input
          v-model="password"
          outlined
          :type="showPw ? 'text' : 'password'"
          label="Password"
          hint="At least 8 characters"
          :rules="[req, min8]"
        >
          <template #append>
            <q-icon
              :name="showPw ? 'visibility_off' : 'visibility'"
              class="cursor-pointer"
              @click="showPw = !showPw"
            />
          </template>
        </q-input>
        <q-btn
          unelevated
          color="primary"
          no-caps
          size="lg"
          class="full-width"
          type="submit"
          label="Create account"
          :loading="loading"
        />
      </q-form>

      <div class="jg-auth__foot">
        Already have an account?
        <router-link :to="{ name: 'login', query: { ...route.query, as: audience } }" class="jg-link">
          Sign in
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import { apiError } from '@/lib/api'
import { audienceFromQuery, landingFor, type Audience } from '@/lib/authAudience'
import { useAuthStore } from '@/stores/auth'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const audience = ref<Audience>(audienceFromQuery(route.query.as))
const heading = computed(() =>
  audience.value === 'provider' ? 'Create a provider account' : 'Create your account',
)
const blurb = computed(() =>
  audience.value === 'provider'
    ? "One account to list activities and manage bookings. You'll set up your organisation next."
    : "One account for all your kids' holiday plans.",
)

const fullName = ref('')
const email = ref('')
const password = ref('')
const showPw = ref(false)
const loading = ref(false)

const req = (v: string): boolean | string => !!v || 'Required'
const min8 = (v: string): boolean | string => v.length >= 8 || 'At least 8 characters'

async function submit(): Promise<void> {
  loading.value = true
  try {
    await auth.signup(email.value, password.value, fullName.value || undefined)
    router.push(landingFor(audience.value, route.query.redirect as string | undefined))
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not create account') })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.jg-auth {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: radial-gradient(120% 120% at 50% 0%, #eef3fe 0%, var(--jg-canvas) 55%);
}
.jg-auth__card { width: 100%; max-width: 400px; padding: 30px 28px; }
.jg-auth__brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--jg-ink);
  font-family: 'Fraunces', serif;
  font-weight: 700;
  font-size: 20px;
}
.jg-auth__foot { margin-top: 20px; font-size: 14px; color: var(--jg-ink-soft); }
.jg-link { color: var(--jg-primary); font-weight: 600; text-decoration: none; }
.jg-audience {
  border: 1px solid var(--jg-line);
  border-radius: 12px;
  overflow: hidden;
}
</style>
