import { describe, expect, it } from 'vitest'

import { decodeJwt } from '@/lib/jwt'

function makeToken(payload: Record<string, unknown>): string {
  const b64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `header.${b64}.signature`
}

describe('decodeJwt', () => {
  it('reads claims from the payload segment', () => {
    const claims = decodeJwt(makeToken({ sub: 'user-1', adm: true, imp: 'admin-9', mode: 'act_as' }))
    expect(claims?.sub).toBe('user-1')
    expect(claims?.adm).toBe(true)
    expect(claims?.imp).toBe('admin-9')
    expect(claims?.mode).toBe('act_as')
  })

  it('returns null for malformed tokens', () => {
    expect(decodeJwt('not-a-jwt')).toBeNull()
    expect(decodeJwt('')).toBeNull()
    expect(decodeJwt('a.!!!notbase64!!!.c')).toBeNull()
  })
})
