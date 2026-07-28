import React from 'react';
import { LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../context/AuthContext';
import CRMClientsDashboard from './CRMClientsDashboard';


export default function CRMWorkspacePage() {
    const { logout, user } = useAuth();
    const navigate = useNavigate();

    const signOut = () => {
        logout();
        navigate('/login', { replace: true });
    };

    return (
        <div className="min-h-screen bg-slate-50">
            <header className="sticky top-0 z-40 flex items-center justify-between border-b border-slate-200 bg-slate-950 px-4 py-3 text-white sm:px-6">
                <div>
                    <p className="text-[9px] font-black uppercase tracking-[0.2em] text-blue-300">MMG · Espace commercial</p>
                    <h1 className="mt-1 text-lg font-black">CRM Avant-vente</h1>
                </div>
                <div className="flex items-center gap-3">
                    <span className="hidden text-xs font-bold text-slate-300 sm:inline">{user?.username}</span>
                    <button onClick={signOut} className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-xs font-black text-slate-200 hover:bg-slate-800">
                        <LogOut className="h-4 w-4" />
                        Déconnexion
                    </button>
                </div>
            </header>
            <main className="min-h-[calc(100vh-64px)]">
                <CRMClientsDashboard />
            </main>
        </div>
    );
}
