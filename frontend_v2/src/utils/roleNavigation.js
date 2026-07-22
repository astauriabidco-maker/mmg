const STOCK_HOME_ROLES = new Set(['MAGASINIER', 'CHEF_STOCK']);
const ATELIER_HOME_ROLES = new Set(['OPERATOR', 'DEBIT_OPERATOR', 'QUALITY_CONTROLLER', 'WORKSHOP_LEAD']);

export function isAtelierRole(role) {
    return ATELIER_HOME_ROLES.has(role);
}

export function getDefaultPathForUser(user) {
    const role = user?.role;
    if (role === 'ADMIN' || role === 'MANAGER') return '/manager';
    if (STOCK_HOME_ROLES.has(role)) return '/stock';
    if (ATELIER_HOME_ROLES.has(role)) {
        const firstStation = Array.isArray(user?.stations) && user.stations.length > 0 ? user.stations[0] : null;
        const stationCode = typeof firstStation === 'string' ? firstStation : firstStation?.code;
        return `/dashboard/${stationCode || 'PVC_DEBIT'}`;
    }
    return '/dashboard/PVC_DEBIT';
}
