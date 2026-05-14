import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';

const Login = lazy(() => import('./pages/Login'));
const OperatorDashboard = lazy(() => import('./pages/OperatorDashboard'));
const ManagerDashboard = lazy(() => import('./pages/ManagerDashboard'));
const ManualUpload = lazy(() => import('./pages/ManualUpload'));
const MMGDossiers = lazy(() => import('./pages/MMGDossiers'));
const POSDashboard = lazy(() => import('./pages/POSDashboard'));
const StockDashboard = lazy(() => import('./pages/StockDashboard'));
const ClientPortal = lazy(() => import('./pages/ClientPortal'));
const DriverDashboard = lazy(() => import('./pages/DriverDashboard'));

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
    if (!allowedRoles.includes(user.role)) return <Navigate to="/dashboard" replace />;
    return children;
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
                                element={<Navigate to="/dashboard/PVC_DEBIT" replace />}
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
                                path="/mmg"
                                element={
                                    <RoleRoute allowedRoles={['ADMIN', 'MANAGER']}>
                                        <MMGDossiers />
                                    </RoleRoute>
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
