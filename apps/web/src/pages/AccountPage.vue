<template>
  <q-page class="jg-page" style="max-width: 640px">
    <h1 class="text-h4 q-mb-xs">My kids</h1>
    <p class="jg-muted q-mb-lg">
      We keep this minimal — first name and date of birth only. No surnames, no photos.
    </p>

    <div v-if="loading" class="q-gutter-sm">
      <q-skeleton v-for="n in 2" :key="n" type="rect" height="64px" style="border-radius: 14px" />
    </div>

    <div v-else class="jg-kids">
      <div v-for="child in children" :key="child.id" class="jg-card jg-kidrow">
        <q-avatar color="primary" text-color="white" size="42px">
          {{ child.first_name.slice(0, 1).toUpperCase() }}
        </q-avatar>
        <div>
          <div class="text-weight-600">{{ child.first_name }}</div>
          <div class="jg-faint text-caption">
            {{ ageAt(child.date_of_birth, nowIso) }} years old
          </div>
        </div>
      </div>

      <button class="jg-card jg-addkid" @click="showAddChild = true">
        <q-icon name="add" size="22px" color="primary" />
        <span>Add a child</span>
      </button>
    </div>

    <!-- Co-guardians (PRD §7.3) -->
    <section class="q-mt-xl">
      <h2 class="text-h5 q-mb-xs">Family</h2>
      <p class="jg-muted q-mb-md">
        Add another parent or carer — once they accept, you'll share your kids and bookings.
      </p>

      <div v-if="coGuardians.length" class="jg-kids q-mb-md">
        <div v-for="cg in coGuardians" :key="cg.id" class="jg-card jg-kidrow">
          <q-avatar :color="cg.accepted ? 'positive' : 'grey-5'" text-color="white" size="42px">
            {{ (cg.other_name || cg.other_email).slice(0, 1).toUpperCase() }}
          </q-avatar>
          <div class="col">
            <div class="text-weight-600">{{ cg.other_name || cg.other_email }}</div>
            <div class="jg-faint text-caption">
              <template v-if="cg.accepted">Sharing family</template>
              <template v-else-if="cg.direction === 'received'">Invited you</template>
              <template v-else>Invite sent — awaiting acceptance</template>
            </div>
          </div>
          <q-btn
            v-if="!cg.accepted && cg.direction === 'received'"
            unelevated dense no-caps size="sm" color="primary" label="Accept"
            @click="accept(cg)"
          />
          <q-btn flat round dense icon="close" color="grey-7" @click="remove(cg)" />
        </div>
      </div>

      <button class="jg-card jg-addkid" @click="showInvite = true">
        <q-icon name="group_add" size="22px" color="primary" />
        <span>Add a co-guardian</span>
      </button>
    </section>

    <!-- Data & privacy (PRD §10.2 — APP data-deletion) -->
    <section class="q-mt-xl">
      <h2 class="text-h6 q-mb-xs">Data &amp; privacy</h2>
      <p class="jg-muted q-mb-sm">
        You can delete your account and your kids' details at any time.
      </p>
      <q-btn
        flat no-caps color="negative" icon="delete_forever" label="Delete my account"
        @click="confirmDelete"
      />
    </section>

    <q-dialog v-model="showInvite">
      <q-card style="min-width: 360px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Add a co-guardian</div>
          <div class="jg-faint text-caption">They need a Juggle account with this email.</div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="inviteEmail" outlined dense type="email" label="Their email" autofocus
            @keyup.enter="invite"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated color="primary" no-caps label="Send invite"
            :loading="inviting" :disable="!inviteEmail" @click="invite"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="showAddChild">
      <q-card style="min-width: 340px; border-radius: 18px">
        <q-card-section>
          <div class="text-h6">Add a child</div>
        </q-card-section>
        <q-card-section class="q-gutter-md">
          <q-input v-model="newChild.first_name" outlined dense label="First name" autofocus />
          <q-input v-model="newChild.date_of_birth" outlined dense type="date" label="Date of birth" stack-label />
          <q-input
            v-model="newChild.medical_notes"
            outlined
            dense
            type="textarea"
            autogrow
            label="Allergies / medical notes (optional)"
          />
        </q-card-section>
        <q-card-actions align="right" class="q-pb-md q-pr-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            no-caps
            label="Add child"
            :loading="saving"
            :disable="!newChild.first_name || !newChild.date_of_birth"
            @click="saveChild"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import { useRouter } from 'vue-router'

import { api, apiError } from '@/lib/api'
import { ageAt } from '@/lib/format'
import type { Child, CoGuardian } from '@/lib/types'
import { useAuthStore } from '@/stores/auth'

const $q = useQuasar()
const router = useRouter()
const auth = useAuthStore()

function confirmDelete(): void {
  $q.dialog({
    title: 'Delete your account?',
    message:
      "This permanently removes your profile and your kids' details. Bookings you've " +
      'made stay on record with providers but no longer carry your data. This cannot be undone.',
    cancel: true,
    persistent: true,
    ok: { label: 'Delete everything', color: 'negative', unelevated: true, noCaps: true },
  }).onOk(async () => {
    try {
      await api.auth.deleteAccount()
      auth.logout()
      $q.notify({ type: 'info', message: 'Your account has been deleted.' })
      router.push({ name: 'discover' })
    } catch (err) {
      $q.notify({ type: 'negative', message: apiError(err, 'Could not delete your account') })
    }
  })
}
const children = ref<Child[]>([])
const coGuardians = ref<CoGuardian[]>([])
const loading = ref(true)
const showAddChild = ref(false)
const saving = ref(false)
const showInvite = ref(false)
const inviting = ref(false)
const inviteEmail = ref('')
const nowIso = new Date().toISOString()
const newChild = reactive({ first_name: '', date_of_birth: '', medical_notes: '' })

async function load(): Promise<void> {
  loading.value = true
  try {
    children.value = await api.children.list()
    coGuardians.value = await api.coGuardians.list()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not load your kids') })
  } finally {
    loading.value = false
  }
}

async function invite(): Promise<void> {
  if (!inviteEmail.value) return
  inviting.value = true
  try {
    await api.coGuardians.invite(inviteEmail.value.trim())
    showInvite.value = false
    inviteEmail.value = ''
    coGuardians.value = await api.coGuardians.list()
    $q.notify({ type: 'positive', message: 'Invite sent.' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not send invite') })
  } finally {
    inviting.value = false
  }
}

async function accept(cg: CoGuardian): Promise<void> {
  try {
    await api.coGuardians.accept(cg.id)
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function remove(cg: CoGuardian): Promise<void> {
  try {
    await api.coGuardians.remove(cg.id)
    await load()
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err) })
  }
}

async function saveChild(): Promise<void> {
  saving.value = true
  try {
    const created = await api.children.create({
      first_name: newChild.first_name,
      date_of_birth: newChild.date_of_birth,
      medical_notes: newChild.medical_notes || null,
    })
    children.value.push(created)
    showAddChild.value = false
    newChild.first_name = ''
    newChild.date_of_birth = ''
    newChild.medical_notes = ''
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not add child') })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.jg-kids { display: flex; flex-direction: column; gap: 12px; }
.jg-kidrow { display: flex; align-items: center; gap: 14px; padding: 14px 18px; }
.jg-addkid {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 18px;
  border-style: dashed;
  color: var(--jg-primary);
  font-weight: 600;
  cursor: pointer;
  background: transparent;
}
</style>
