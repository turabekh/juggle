/* Juggle service worker (dependency-free).
 *
 * Strategy:
 *   - navigations: network-first, cache a copy of the app shell, fall back to
 *     the cached shell when offline;
 *   - hashed static assets (js/css/fonts/images): cache-first (immutable);
 *   - /api and non-GET / cross-origin: always straight to the network (never
 *     cache live availability or mutations).
 */
const CACHE = 'juggle-v1'
const SHELL = '/index.html'
const ASSET_RE = /\.(?:js|css|woff2?|ttf|png|svg|ico|webmanifest)$/

self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api')) return // live data + mutations — never cache

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put(SHELL, copy))
          return res
        })
        .catch(() => caches.match(SHELL).then((hit) => hit || caches.match(request))),
    )
    return
  }

  if (ASSET_RE.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((res) => {
            const copy = res.clone()
            caches.open(CACHE).then((c) => c.put(request, copy))
            return res
          }),
      ),
    )
  }
})
