import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StarRating from '@/components/StarRating.vue'

function iconNames(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper.findAllComponents({ name: 'QIcon' }).map((i) => i.props('name') as string)
}

describe('StarRating', () => {
  it('renders exactly modelValue filled stars out of five', () => {
    const wrapper = mount(StarRating, { props: { modelValue: 3 } })
    const names = iconNames(wrapper)
    expect(names).toHaveLength(5)
    expect(names.filter((n) => n === 'star')).toHaveLength(3)
    expect(names.filter((n) => n === 'star_border')).toHaveLength(2)
  })

  it('does not emit when not editable', async () => {
    const wrapper = mount(StarRating, { props: { modelValue: 2 } })
    await wrapper.findAllComponents({ name: 'QIcon' })[4].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('emits the clicked rating when editable', async () => {
    const wrapper = mount(StarRating, { props: { modelValue: 2, editable: true } })
    await wrapper.findAllComponents({ name: 'QIcon' })[3].trigger('click') // 4th star
    expect(wrapper.emitted('update:modelValue')).toEqual([[4]])
  })
})
