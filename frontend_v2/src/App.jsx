import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import OperatorDashboard from './pages/OperatorDashboard';
import ManagerDashboard from './pages/ManagerDashboard';
import ManualUpload from './pages/ManualUpload';
import MMGDossiers from './pages/MMGDossiers';
import POSDashboard from './pages/POSDashboard';
import StockDashboard from './pages/StockDashboard';
import ClientPortal from './pages/ClientPortal';
import DriverDashboard from './pages/DriverDashboard';

const ProtectedRoute = ({ children }) => {
    const { user } = useAuth();
    if (!user) return <Navigate to="/login" replace />;
    return children;
};

const queryClient = new QueryClient();

export default function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <AuthProvider>
                <BrowserRouter>
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
                            <ProtectedRoute>
                                <ManagerDashboard />
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/mmg"
                        element={
                            <ProtectedRoute>
                                <MMGDossiers />
                            </ProtectedRoute>
                        }
                    />
                    <Route
                        path="/upload"
                        element={
                            <ProtectedRoute>
                                <ManualUpload />
                            </ProtectedRoute>
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
            </BrowserRouter>
        </AuthProvider>
    </QueryClientProvider>
    );
}
