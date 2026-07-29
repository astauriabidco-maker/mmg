const STOCK_HOME_ROLES = new Set(['MAGASINIER', 'CHEF_STOCK']);
const ATELIER_HOME_ROLES = new Set(['OPERATOR', 'DEBIT_OPERATOR', 'QUALITY_CONTROLLER', 'WORKSHOP_LEAD']);
const MANAGER_ROLES = new Set(['ADMIN', 'MANAGER', 'SUPER_ADMIN']);

const MANAGER_VIEW_PERMISSIONS = {
    schedule: 'PLANNING_VIEW',
    planning_resources: 'PLANNING_RESOURCE_MANAGE',
    crm: 'SALES_VIEW',
    sales: 'SALES_VIEW',
    'sale-detail': 'SALES_VIEW',
    pos: 'SALES_EDIT',
    accounting: 'ACC_VIEW',
    stock: 'STOCK_VIEW',
    purchases: 'PURCHASES_VIEW',
};

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

export function userHasPermission(user, permission) {
    const permissions = user?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
}

export function canAccessManagerView(user, view) {
    if (getUserRoles(user).some(role => MANAGER_ROLES.has(role))) return true;
    const permission = MANAGER_VIEW_PERMISSIONS[view];
    if (permission) return userHasPermission(user, permission);
    return false;
}

export function getDefaultManagerView(user) {
    const roles = getUserRoles(user);
    if (roles.some(role => MANAGER_ROLES.has(role))) return 'dashboard';
    if (roles.includes('FINANCE') && userHasPermission(user, 'ACC_VIEW')) return 'accounting';
    if (roles.includes('TECHNICO_COMMERCIAL') && userHasPermission(user, 'SALES_VIEW')) return 'crm';
    if (userHasPermission(user, 'SALES_VIEW')) return 'crm';
    if (userHasPermission(user, 'ACC_VIEW')) return 'accounting';
    if (userHasPermission(user, 'PURCHASES_VIEW')) return 'purchases';
    if (userHasPermission(user, 'STOCK_VIEW')) return 'stock';
    return null;
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
    if (roles.some(role => MANAGER_ROLES.has(role))) return '/manager';
    if (
        roles.includes('TECHNICO_COMMERCIAL')
        || roles.includes('FINANCE')
        || (userHasPermission(user, 'SALES_VIEW') && userHasPermission(user, 'STOCK_VIEW'))
    ) {
        const view = getDefaultManagerView(user);
        if (view) return `/manager?view=${view}`;
    }
    if (roles.includes('SALES')) return '/crm';
    if (userHasPermission(user, 'ACC_VIEW')) return '/manager?view=accounting';
    if (userHasPermission(user, 'PURCHASES_VIEW')) return '/manager?view=purchases';
    if (roles.some(role => STOCK_HOME_ROLES.has(role))) return shouldUseStockMobile() ? '/stock-mobile' : '/stock';
    if (roles.some(role => ATELIER_HOME_ROLES.has(role))) {
        const firstStation = Array.isArray(user?.stations) && user.stations.length > 0 ? user.stations[0] : null;
        const stationCode = typeof firstStation === 'string' ? firstStation : firstStation?.code;
        return `/dashboard/${stationCode || 'PVC_DEBIT'}`;
    }
    return '/dashboard/PVC_DEBIT';
}
