// Tiny self-contained confetti burst (ADR-0011 Milestone C) — no dependency, no assets, uses the
// Web Animations API. Spawns short-lived particles at a screen point and cleans them up.

const COLORS = ['#f94144', '#f3722c', '#f9c74f', '#90be6d', '#43aa8b', '#577590', '#c2185b']

export function confettiBurst(x: number, y: number, count = 28): void {
  if (typeof document === 'undefined') return
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (reduce) return
  for (let i = 0; i < count; i += 1) {
    const p = document.createElement('div')
    const size = 6 + Math.floor(Math.random() * 6)
    Object.assign(p.style, {
      position: 'fixed',
      left: `${x}px`,
      top: `${y}px`,
      width: `${size}px`,
      height: `${size}px`,
      background: COLORS[i % COLORS.length],
      borderRadius: Math.random() > 0.5 ? '50%' : '2px',
      pointerEvents: 'none',
      zIndex: '9999',
    })
    document.body.appendChild(p)
    const angle = Math.random() * Math.PI * 2
    const dist = 60 + Math.random() * 120
    const dx = Math.cos(angle) * dist
    const dy = Math.sin(angle) * dist - 40
    p.animate(
      [
        { transform: 'translate(0,0) rotate(0deg)', opacity: 1 },
        { transform: `translate(${dx}px, ${dy + 160}px) rotate(${Math.random() * 720}deg)`, opacity: 0 },
      ],
      { duration: 900 + Math.random() * 500, easing: 'cubic-bezier(.2,.6,.4,1)' },
    ).onfinish = () => p.remove()
  }
}
