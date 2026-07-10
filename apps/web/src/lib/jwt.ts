// Read (not verify) JWT claims client-side — enough to know whether the active
// token is an impersonation token and in which mode. Verification is the API's job.

export interface JwtClaims {
  sub: string
  adm?: boolean
  imp?: string
  mode?: string
  isid?: string
  exp?: number
}

export function decodeJwt(token: string): JwtClaims | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json) as JwtClaims
  } catch {
    return null
  }
}
