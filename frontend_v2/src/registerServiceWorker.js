export function registerServiceWorker() {
    if (!import.meta.env.PROD) return;
    if (!('serviceWorker' in navigator)) return;

    window.addEventListener('load', () => {
        let reloading = false;
        navigator.serviceWorker.addEventListener('controllerchange', () => {
            if (reloading) return;
            reloading = true;
            window.location.reload();
        });

        navigator.serviceWorker
            .register('/sw.js', { updateViaCache: 'none' })
            .then((registration) => registration.update())
            .catch((error) => {
                console.info('PWA service worker registration skipped:', error);
            });
    });
}
