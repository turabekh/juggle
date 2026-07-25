<template>
  <section class="jg-card q-pa-lg q-mb-md">
    <div class="row items-center justify-between q-mb-sm">
      <div class="text-weight-600">Party page</div>
      <q-btn v-if="plan.share_path" flat dense no-caps size="sm" icon="open_in_new"
             label="View guest page" :href="plan.share_path" target="_blank" rel="noopener" />
    </div>
    <div class="jg-faint text-caption q-mb-md">
      Customise the page your guests see. Keep it fun — use a nickname, not real names or surnames.
    </div>

    <div class="row q-col-gutter-md">
      <!-- Editor -->
      <div class="col-12 col-sm-7">
        <div class="jg-faint text-caption q-mb-xs">Template</div>
        <div class="row q-gutter-xs q-mb-md">
          <q-btn v-for="t in PLAN_THEMES" :key="t.key" no-caps unelevated dense size="sm"
                 :color="form.template === t.key ? 'primary' : 'grey-3'"
                 :text-color="form.template === t.key ? 'white' : 'dark'"
                 :label="`${t.emoji} ${t.label}`" @click="form.template = t.key" />
        </div>

        <q-input v-model="form.title" outlined dense label="Party title"
                 hint="A fun nickname or theme — no surnames" class="q-mb-sm"
                 :maxlength="TITLE_MAX" counter />

        <div class="jg-faint text-caption q-mb-xs">Big avatar</div>
        <div class="row q-gutter-xs q-mb-sm">
          <q-btn round dense size="sm" :color="!form.hero_avatar ? 'primary' : 'grey-3'"
                 :text-color="!form.hero_avatar ? 'white' : 'dark'"
                 :label="templateEmoji" @click="form.hero_avatar = null" />
          <q-btn v-for="a in AVATARS" :key="a.key" round dense size="sm"
                 :color="form.hero_avatar === a.key ? 'primary' : 'grey-3'"
                 :text-color="form.hero_avatar === a.key ? 'white' : 'dark'"
                 :label="a.emoji" @click="form.hero_avatar = a.key" />
        </div>

        <q-input v-model="form.message" outlined dense type="textarea" autogrow
                 label="Welcome message (optional)" class="q-mb-sm"
                 :maxlength="MESSAGE_MAX" counter />

        <div class="jg-faint text-caption q-mb-xs">Widgets</div>
        <q-toggle v-for="w in WIDGETS" :key="w.key" v-model="enabled[w.key]" color="primary"
                  dense class="block q-mb-xs">
          <span class="text-body2">{{ w.label }}</span>
          <span class="jg-faint text-caption q-ml-xs">· {{ w.hint }}</span>
        </q-toggle>

        <q-btn unelevated color="primary" no-caps class="q-mt-md" label="Save page"
               :loading="saving" @click="save" />
      </div>

      <!-- Live preview -->
      <div class="col-12 col-sm-5">
        <div class="jg-faint text-caption q-mb-xs text-center">Preview</div>
        <PartyPagePreview :page="patch" :options="plan.options" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useQuasar } from 'quasar'

import PartyPagePreview from '@/components/PartyPagePreview.vue'
import { api, apiError } from '@/lib/api'
import { AVATARS, WIDGETS } from '@/lib/partyPage'
import { PLAN_THEMES, planTheme } from '@/lib/planTheme'
import type { PartyPagePatch, PartyWidgetKey, PlanView } from '@/lib/types'

const props = defineProps<{ plan: PlanView }>()
const emit = defineEmits<{ saved: [plan: PlanView] }>()
const $q = useQuasar()

// The caps are runtime config (INV-11) — the server sends the live values on the plan, so
// the counters follow an admin's change instead of drifting from a duplicated constant.
// The fallbacks match the config defaults and only apply to a plan fetched before this shipped.
const TITLE_MAX = computed(() => props.plan.limits?.page_title_maxlen ?? 60)
const MESSAGE_MAX = computed(() => props.plan.limits?.page_message_maxlen ?? 280)
const WIDGET_KEYS: PartyWidgetKey[] = ['welcome', 'countdown', 'board', 'reveal_venue']

const saving = ref(false)
const form = reactive({
  template: props.plan.page.template,
  title: props.plan.page.title ?? '',
  message: props.plan.page.message ?? '',
  hero_avatar: props.plan.page.hero_avatar,
})
const enabled = reactive(
  Object.fromEntries(
    WIDGET_KEYS.map((k) => [k, props.plan.page.widgets.includes(k)]),
  ) as Record<PartyWidgetKey, boolean>,
)

const templateEmoji = computed(() => planTheme(form.template).emoji)
const patch = computed<PartyPagePatch>(() => ({
  template: form.template,
  title: form.title,
  message: form.message,
  hero_avatar: form.hero_avatar,
  widgets: WIDGET_KEYS.filter((k) => enabled[k]),
}))

async function save(): Promise<void> {
  saving.value = true
  try {
    const updated = await api.partyPlanner.updatePage(props.plan.id, patch.value)
    emit('saved', updated)
    $q.notify({ type: 'positive', message: 'Party page saved ✓' })
  } catch (err) {
    $q.notify({ type: 'negative', message: apiError(err, 'Could not save the page') })
  } finally {
    saving.value = false
  }
}
</script>
