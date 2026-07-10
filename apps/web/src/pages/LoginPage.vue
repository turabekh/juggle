<template>
  <div class="jg-auth">
    <div class="jg-auth__card jg-card">
      <router-link :to="{ name: 'discover' }" class="jg-auth__brand">
        <span style="font-size: 24px">🤹</span>
        <span>Juggle</span>
      </router-link>
      <h1 class="text-h5 q-mt-md q-mb-xs">Welcome back</h1>
      <p class="jg-muted q-mb-lg">Sign in to book and manage your holiday plans.</p>

      <q-form @submit="submit" class="q-gutter-md">
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

      <div class="jg-auth__foot">
        New here?
        <router-link :to="{ name: 'signup', query: route.query }" class="jg-link">Create an account</router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'

import { apiError } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const showPw = ref(false)
const loading = ref(false)

const req = (v: string): boolean | string => !!v || 'Required'

async function submit(): Promise<void> {
  loading.value = true
  try {
    await auth.login(email.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not sign in') })
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
</style>
