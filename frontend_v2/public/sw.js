const CACHE_NAME = 'mmg-pwa-shell-v2';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/manifest.webmanifest',
    '/icons/mmg-icon.svg',
    '/icons/mmg-icon-192.png',
    '/icons/mmg-icon-512.png',
    '/icons/mmg-icon-maskable-512.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()),
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
            .then(() => self.clients.claim()),
    );
});

const isStaticAsset = (url) => {
    return /\.(?:js|css|png|svg|ico|webmanifest|woff2?)$/i.test(url.pathname);
};

self.addEventListener('fetch', (event) => {
    const { request } = event;
    if (request.method !== 'GET') return;

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws') || url.pathname === '/health') return;

    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put('/index.html', copy));
                    return response;
                })
                .catch(() => caches.match('/index.html')),
        );
        return;
    }

    if (isStaticAsset(url)) {
        event.respondWith(
            caches.match(request).then(async (cached) => {
                const fresh = fetch(request)
                    .then((response) => {
                        if (response.ok) {
                            const copy = response.clone();
                            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                        }
                        return response;
                    })
                    .catch(() => null);
                if (cached) {
                    fresh.catch(() => null);
                    return cached;
                }
                return (await fresh) || new Response('', { status: 504, statusText: 'Offline' });
            }),
        );
    }
});
