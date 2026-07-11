<template>
  <div class="jg-stars" :class="{ 'jg-stars--input': editable }" role="img" :aria-label="ariaLabel">
    <q-icon
      v-for="n in 5"
      :key="n"
      :name="n <= displayValue ? 'star' : 'star_border'"
      :size="size"
      :color="n <= displayValue ? 'amber-7' : 'grey-5'"
      :class="{ 'jg-stars__hit': editable }"
      @click="editable && emit('update:modelValue', n)"
      @mouseenter="editable && (hover = n)"
      @mouseleave="editable && (hover = 0)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{ modelValue: number; editable?: boolean; size?: string }>(),
  { editable: false, size: '18px' },
)
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()

const hover = ref(0)
const displayValue = computed(() => (props.editable && hover.value ? hover.value : props.modelValue))
const ariaLabel = computed(() => `${props.modelValue} out of 5 stars`)
</script>

<style scoped>
.jg-stars {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}
.jg-stars--input .jg-stars__hit {
  cursor: pointer;
}
</style>
