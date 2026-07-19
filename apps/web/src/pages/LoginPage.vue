<template>
  <div class="jg-auth">
    <div class="jg-auth__card jg-card">
      <router-link :to="{ name: 'discover' }" class="jg-auth__brand">
        <span style="font-size: 24px">🤹</span>
        <span>Juggle</span>
      </router-link>
      <h1 class="text-h5 q-mt-md q-mb-xs">Welcome back</h1>
      <p class="jg-muted q-mb-md">{{ audienceBlurb }}</p>

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

      <q-tabs
        v-if="smsEnabled"
        v-model="tab"
        no-caps
        dense
        active-color="primary"
        indicator-color="primary"
        align="justify"
        class="q-mb-md jg-auth__tabs"
      >
        <q-tab name="email" icon="mail" label="Email" />
        <q-tab name="sms" icon="sms" label="Phone" />
      </q-tabs>

      <!-- Email + password -->
      <q-form v-if="tab === 'email'" @submit="submit" class="q-gutter-md">
        <q-input v-model="email" outlined type="email" label="Email" autofocus :rules="[req]" />
        <q-input
          v-model="password"
          outlined
          :type="showPw ? 'text' : 'password'"
          label="Password"
          :rules="[req]"
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
          label="Sign in"
          :loading="loading"
        />
      </q-form>

      <!-- SMS one-time code -->
      <q-form v-else @submit="codeSent ? verifyCode() : sendCode()" class="q-gutter-md">
        <q-input
          v-model="phone"
          outlined
          type="tel"
          label="Mobile number"
          hint="e.g. 0412 345 678"
          stack-label
          :readonly="codeSent"
          :rules="[req]"
        >
          <template #prepend><q-icon name="phone_iphone" /></template>
        </q-input>

        <q-input
          v-if="codeSent"
          v-model="code"
          outlined
          type="tel"
          inputmode="numeric"
          maxlength="6"
          label="6-digit code"
          autofocus
          :rules="[req]"
          hint="We texted you a code. It expires in 10 minutes."
        />

        <q-btn
          unelevated
          color="primary"
          no-caps
          size="lg"
          class="full-width"
          type="submit"
          :label="codeSent ? 'Verify & sign in' : 'Text me a code'"
          :loading="loading"
        />
        <q-btn
          v-if="codeSent"
          flat
          no-caps
          dense
          class="full-width jg-muted"
          label="Use a different number"
          @click="resetSms"
        />
      </q-form>

      <div class="jg-auth__foot">
        New here?
        <router-link :to="{ name: 'signup', query: { ...route.query, as: audience } }" class="jg-link">
          Create an account
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import { api, apiError } from '@/lib/api'
import { audienceFromQuery, landingFor, type Audience } from '@/lib/authAudience'
import { useAuthStore } from '@/stores/auth'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// One login page, two destinations (parent marketplace vs provider console).
const audience = ref<Audience>(audienceFromQuery(route.query.as))
const audienceBlurb = computed(() =>
  audience.value === 'provider'
    ? 'Sign in to manage your listings, roster and payouts.'
    : 'Sign in to book and manage your holiday plans.',
)

const tab = ref<'email' | 'sms'>('email')
// SMS sign-in only shows when the server has an SMS provider configured.
const smsEnabled = ref(false)
onMounted(async () => {
  try {
    smsEnabled.value = (await api.auth.config()).sms_enabled
  } catch {
    smsEnabled.value = false
  }
})
const email = ref('')
const password = ref('')
const showPw = ref(false)
const loading = ref(false)

// SMS one-time-code state
const phone = ref('')
const code = ref('')
const codeSent = ref(false)

const req = (v: string): boolean | string => !!v || 'Required'

function goNext(): void {
  router.push(landingFor(audience.value, route.query.redirect as string | undefined))
}

async function submit(): Promise<void> {
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    goNext()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not sign in') })
  } finally {
    loading.value = false
  }
}

async function sendCode(): Promise<void> {
  loading.value = true
  try {
    await auth.requestOtp(phone.value)
    codeSent.value = true
    $q.notify({ type: 'positive', message: 'Code sent — check your messages' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not send a code') })
  } finally {
    loading.value = false
  }
}

async function verifyCode(): Promise<void> {
  loading.value = true
  try {
    await auth.verifyOtp(phone.value, code.value)
    goNext()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'That code did not match') })
  } finally {
    loading.value = false
  }
}

function resetSms(): void {
  codeSent.value = false
  code.value = ''
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
