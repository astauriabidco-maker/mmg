const canNotify = () => (
    typeof window !== 'undefined'
    && 'Notification' in window
    && Notification.permission === 'granted'
);

const emitOnce = ({ key, title, body, url }) => {
    if (!canNotify() || window.localStorage.getItem(key)) return;
    const notification = new Notification(title, {
        body,
        tag: key,
        icon: '/icons/icon-192.png',
    });
    notification.onclick = () => {
        window.focus();
        if (url) window.location.assign(url);
    };
    window.localStorage.setItem(key, new Date().toISOString());
};

export const requestPlanningNotificationPermission = async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
    return Notification.requestPermission();
};

export const notifyPlanningIncidents = (incidents = []) => {
    incidents
        .filter((incident) => (
            incident.notify_pwa !== false
            && incident.status !== 'RESOLVED'
            && (incident.severity === 'CRITICAL' || incident.escalation_level > 0)
        ))
        .forEach((incident) => emitOnce({
            key: `mmg-planning-incident-${incident.id}-${incident.escalation_level}`,
            title: incident.escalation_level > 0
                ? 'Incident planning non traité'
                : 'Incident planning critique',
            body: `${incident.title} · ${incident.message || incident.reference}`,
            url: incident.source_url,
        }));
};

export const notifyPlanningInbox = (notifications = []) => {
    notifications
        .filter((item) => ['INCIDENT_CRITICAL', 'INCIDENT_ESCALATED'].includes(
            item.notification_type,
        ))
        .forEach((item) => emitOnce({
            key: `mmg-planning-notification-${item.id}`,
            title: item.title,
            body: item.message,
            url: null,
        }));
};
