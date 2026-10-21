export function routePayload(data) {
    if (!data.driver_name.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(data.planned_date) || !data.note_ids.length) {
        throw new Error('Renseignez le chauffeur, la date et au moins un BL.');
    }
    return { ...data, driver_name: data.driver_name.trim(), planned_date: `${data.planned_date}T00:00:00` };
}

export function logisticsError(error) {
    const detail = error.response?.data?.detail;
    if (Array.isArray(detail)) return detail.map(item => item.msg).join(' · ');
    return typeof detail === 'string' ? detail : error.message || 'Opération impossible. Réessayez.';
}
