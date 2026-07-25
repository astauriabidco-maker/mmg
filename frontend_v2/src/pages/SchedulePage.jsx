import React from 'react';
import { ArrowLeft, Box, LogOut, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import ScheduleDashboard from './ScheduleDashboard';
import { useAuth } from '../context/AuthContext';

export default function SchedulePage() {
    const { user, logout } = useAuth();

    return (
        <div className="min-h-screen bg-slate-50">
            <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
                <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6 xl:px-8">
                    <div className="flex min-w-0 items-center gap-3">
                        <Link
                            to="/dashboard"
                            className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-slate-900 text-white"
                            title="Retour à mon espace"
                        >
                            <Box className="h-5 w-5" />
                        </Link>
                        <div className="min-w-0">
                            <p className="truncate text-sm font-black text-slate-950">MMG Planning</p>
                            <p className="truncate text-xs font-semibold text-slate-500">Pilotage transversal des équipes</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Link
                            to="/dashboard"
                            className="flex h-9 items-center gap-2 rounded-md border border-slate-200 px-3 text-xs font-black text-slate-700 hover:bg-slate-50"
                        >
                            <ArrowLeft className="h-4 w-4" />
                            <span className="hidden sm:inline">Mon espace</span>
                        </Link>
                        <div className="hidden items-center gap-2 border-l border-slate-200 pl-3 md:flex">
                            <UserRound className="h-4 w-4 text-slate-400" />
                            <span className="max-w-40 truncate text-xs font-bold text-slate-600">{user?.username}</span>
                        </div>
                        <button
                            type="button"
                            onClick={logout}
                            className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-red-50 hover:text-red-600"
                            title="Déconnexion"
                        >
                            <LogOut className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </header>
            <ScheduleDashboard />
        </div>
    );
}
