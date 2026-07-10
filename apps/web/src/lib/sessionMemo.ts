// Lightweight client-side memo of session display info (title/org/time), keyed
// by session id. The bookings API returns ids, not titles; this fills the gap
// for sessions the user has viewed or booked, with a graceful fallback.

export interface SessionMemo {
  title: string
  orgName: string
  startsAt: string
  endsAt: string
}

const KEY = 'juggle.sessionMemo'

function readAll(): Record<string, SessionMemo> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, SessionMemo>
  } catch {
    return {}
  }
}

export function rememberSession(id: string, memo: SessionMemo): void {
  const all = readAll()
  all[id] = memo
  localStorage.setItem(KEY, JSON.stringify(all))
}

export function recallSession(id: string): SessionMemo | null {
  return readAll()[id] ?? null
}
