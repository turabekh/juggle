import { describe, expect, it } from 'vitest'

import { payoutSetupDisplay } from '@/lib/format'
import type { ConnectStatus } from '@/lib/types'

function status(over: Partial<ConnectStatus> = {}): ConnectStatus {
  return { onboarded: false, charges_enabled: false, payouts_enabled: false, ...over }
}

describe('payoutSetupDisplay', () => {
  it('prompts setup when no Stripe account exists yet', () => {
    const d = payoutSetupDisplay(null)
    expect(d.label).toBe('Not set up')
    expect(d.needsSetup).toBe(true)
    expect(d.ctaLabel).toBe('Set up payouts')
  })

  it('treats an un-onboarded status the same as no account', () => {
    const d = payoutSetupDisplay(status())
    expect(d.label).toBe('Not set up')
    expect(d.needsSetup).toBe(true)
  })

  it('shows "in review" while Stripe verifies an onboarded-but-not-enabled account', () => {
    const d = payoutSetupDisplay(status({ onboarded: true }))
    expect(d.color).toBe('warning')
    expect(d.label).toBe('In review')
    expect(d.needsSetup).toBe(true)
    expect(d.ctaLabel).toBe('Finish Stripe setup')
  })

  it('shows active and hides the CTA once payouts are enabled', () => {
    const d = payoutSetupDisplay(status({ onboarded: true, charges_enabled: true, payouts_enabled: true }))
    expect(d.color).toBe('positive')
    expect(d.label).toBe('Active')
    expect(d.needsSetup).toBe(false)
  })

  it('payouts_enabled wins even if onboarded were somehow false', () => {
    const d = payoutSetupDisplay(status({ payouts_enabled: true }))
    expect(d.label).toBe('Active')
    expect(d.needsSetup).toBe(false)
  })
})
