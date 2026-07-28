import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import { getDefaultPathForUser, userHasAnyRole } from './utils/roleNavigation';

const Login = lazy(() => import('./pages/Login'));
const OperatorDashboard = lazy(() => import('./pages/OperatorDashboard'));
const ManagerDashboard = lazy(() => import('./pages/ManagerDashboard'));
const CRMWorkspacePage = lazy(() => import('./pages/CRMWorkspacePage'));
const SaleDetailPage = lazy(() => import('./pages/SaleDetailPage'));
const ManualUpload = lazy(() => import('./pages/ManualUpload'));
const MMGDossiers = lazy(() => import('./pages/MMGDossiers'));
const MeasureMissionPage = lazy(() => import('./pages/MeasureMissionPage'));
const POSDashboard = lazy(() => import('./pages/POSDashboard'));
const StockDashboard = lazy(() => import('./pages/StockDashboard'));
const StockMobileDashboard = lazy(() => import('./pages/StockMobileDashboard'));
const ClientPortal = lazy(() => import('./pages/ClientPortal'));
const DriverDashboard = lazy(() => import('./pages/DriverDashboard'));
const SchedulePage = lazy(() => import('./pages/SchedulePage'));

const PageLoader = () => (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center text-sm font-bold text-slate-500">
        Chargement...
    </div>
);

const ProtectedRoute = ({ children }) => {
    const { user } = useAuth();
    if (!user) return <Navigate to="/login" replace />;
    return children;
};

const RoleRoute = ({ children, allowedRoles }) => {
    const { user } = useAuth();
    if (!user) return <Navigate to="/login" replace />;
    if (!userHasAnyRole(user, allowedRoles)) return <Navigate to="/dashboard" replace />;
    return children;
};

const PermissionRoute = ({ children, permission }) => {
    const { user } = useAuth();
    if (!user) return <Navigate to="/login" replace />;
    const permissions = user.permissions || [];
    if (!permissions.includes('*') && !permissions.includes(permission)) {
        return <Navigate to="/dashboard" replace />;
    }
    return children;
};

const SaleDetailRedirect = () => {
    const { saleId } = useParams();
    return <SaleDetailPage saleId={saleId} />;
};

const DefaultDashboardRedirect = () => {
    const { user } = useAuth();
    if (!user) return <Navigate to="/login" replace />;
    return <Navigate to={getDefaultPathForUser(user)} replace />;
};

const queryClient = new QueryClient();

export default function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <AuthProvider>
                <BrowserRouter>
                    <Suspense fallback={<PageLoader />}>
                        <Routes>
                            <Route path="/login" element={<Login />} />
                            {/* PUBLIC PORTAL ROUTE (NO AUTH REQUIRED) */}
                            <Route path="/portal/sign/:token" element={<ClientPortal />} />

                            <Route
                                path="/dashboard"
                                element={<DefaultDashboardRedirect />}
                            />
                            <Route
                                path="/dashboard/:stationId"
                                element={
                                    <ProtectedRoute>
                                        <OperatorDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/manager"
                                element={
                                    <RoleRoute allowedRoles={['ADMIN', 'MANAGER']}>
                                        <ManagerDashboard />
                                    </RoleRoute>
                                }
                            />
                            <Route
                                path="/sales/:saleId"
                                element={
                                    <RoleRoute allowedRoles={['ADMIN', 'MANAGER', 'SALES']}>
                                        <SaleDetailRedirect />
                                    </RoleRoute>
                                }
                            />
                            <Route
                                path="/crm"
                                element={
                                    <PermissionRoute permission="SALES_VIEW">
                                        <CRMWorkspacePage />
                                    </PermissionRoute>
                                }
                            />
                            <Route
                                path="/mmg"
                                element={
                                    <RoleRoute allowedRoles={['ADMIN', 'MANAGER']}>
                                        <MMGDossiers />
                                    </RoleRoute>
                                }
                            />
                            <Route
                                path="/measure-missions/new"
                                element={
                                    <ProtectedRoute>
                                        <MeasureMissionPage />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/measure-missions/:missionId"
                                element={
                                    <ProtectedRoute>
                                        <MeasureMissionPage />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/upload"
                                element={
                                    <RoleRoute allowedRoles={['ADMIN', 'MANAGER']}>
                                        <ManualUpload />
                                    </RoleRoute>
                                }
                            />
                            <Route
                                path="/pos"
                                element={
                                    <ProtectedRoute>
                                        <POSDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/stock"
                                element={
                                    <ProtectedRoute>
                                        <StockDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/stock-mobile"
                                element={
                                    <ProtectedRoute>
                                        <StockMobileDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route
                                path="/planning"
                                element={
                                    <PermissionRoute permission="PLANNING_VIEW">
                                        <SchedulePage />
                                    </PermissionRoute>
                                }
                            />
                            <Route
                                path="/driver"
                                element={
                                    <ProtectedRoute>
                                        <DriverDashboard />
                                    </ProtectedRoute>
                                }
                            />
                            <Route path="*" element={<Navigate to="/dashboard" replace />} />
                        </Routes>
                    </Suspense>
                </BrowserRouter>
            </AuthProvider>
        </QueryClientProvider>
    );
}
