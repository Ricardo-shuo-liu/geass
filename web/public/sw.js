const CACHE = 'geass-v1';

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.method !== 'GET' ||
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/ws')
  ) {
    return;
  }
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request);
      const fetched = fetch(event.request)
        .then((response) => {
          if (response.ok) cache.put(event.request, response.clone());
          return response;
        })
        .catch(() => cached);
      return cached || fetched;
    }),
  );
});

