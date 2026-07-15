export function registerServiceWorker() {
    if (!import.meta.env.PROD) return;
    if (!('serviceWorker' in navigator)) return;

    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch((error) => {
            console.info('PWA service worker registration skipped:', error);
        });
    });
}
