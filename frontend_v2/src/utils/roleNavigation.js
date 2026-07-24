const STOCK_HOME_ROLES = new Set(['MAGASINIER', 'CHEF_STOCK']);
const ATELIER_HOME_ROLES = new Set(['OPERATOR', 'DEBIT_OPERATOR', 'QUALITY_CONTROLLER', 'WORKSHOP_LEAD']);

export function getUserRoles(user) {
    return Array.from(new Set([
        user?.role,
        ...(Array.isArray(user?.roles) ? user.roles : []),
    ].filter(Boolean)));
}

export function userHasRole(user, role) {
    return getUserRoles(user).includes(role);
}

export function userHasAnyRole(user, allowedRoles) {
    const roles = new Set(getUserRoles(user));
    return allowedRoles.some(role => roles.has(role));
}

export function isAtelierRole(role) {
    return ATELIER_HOME_ROLES.has(role);
}

export function isAtelierUser(user) {
    return getUserRoles(user).some(role => ATELIER_HOME_ROLES.has(role));
}

export function shouldUseStockMobile() {
    if (typeof window === 'undefined') return false;
    const standalone = window.matchMedia?.('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
    const mobileViewport = window.matchMedia?.('(max-width: 820px)').matches;
    const touchDevice = window.matchMedia?.('(pointer: coarse)').matches;
    return standalone || (mobileViewport && touchDevice);
}

export function getDefaultPathForUser(user) {
    const roles = getUserRoles(user);
    if (roles.some(role => role === 'ADMIN' || role === 'MANAGER')) return '/manager';
    if (roles.some(role => STOCK_HOME_ROLES.has(role))) return shouldUseStockMobile() ? '/stock-mobile' : '/stock';
    if (roles.some(role => ATELIER_HOME_ROLES.has(role))) {
        const firstStation = Array.isArray(user?.stations) && user.stations.length > 0 ? user.stations[0] : null;
        const stationCode = typeof firstStation === 'string' ? firstStation : firstStation?.code;
        return `/dashboard/${stationCode || 'PVC_DEBIT'}`;
    }
    return '/dashboard/PVC_DEBIT';
}
