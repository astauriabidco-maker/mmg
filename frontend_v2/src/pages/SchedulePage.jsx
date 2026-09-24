import React, { useCallback, useState } from 'react';
import { Menu } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import ScheduleDashboard from './ScheduleDashboard';

export default function SchedulePage() {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [searchParams, setSearchParams] = useSearchParams();
    const settingsTab = searchParams.get('settings');

    const closeSettings = useCallback(() => {
        const next = new URLSearchParams(searchParams);
        next.delete('settings');
        setSearchParams(next, { replace: true });
    }, [searchParams, setSearchParams]);

    return (
        <div className="flex min-h-screen overflow-x-hidden bg-slate-50">
            <Sidebar
                activeView={settingsTab ? 'planning_resources' : 'schedule'}
                isOpen={isSidebarOpen}
                setIsOpen={setIsSidebarOpen}
            />

            <main className="min-w-0 flex-1 transition-all duration-300 lg:ml-72">
                <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur-md sm:px-6 sm:py-4 lg:px-8">
                    <div className="flex min-w-0 items-center gap-3 sm:gap-4">
                        <button
                            type="button"
                            onClick={() => setIsSidebarOpen(true)}
                            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
                            title="Ouvrir la navigation"
                        >
                            <Menu className="h-6 w-6" />
                        </button>
                        <h1 className="truncate text-lg font-bold text-slate-900 sm:text-xl">
                            Planning & Agenda
                        </h1>
                    </div>

                    <div className="flex items-center gap-3">
                        <span className="relative flex h-3 w-3">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                            <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
                        </span>
                        <span className="hidden text-xs font-bold uppercase tracking-wider text-slate-500 md:block">
                            Système Live
                        </span>
                    </div>
                </header>

                <div className="manager-view-shell p-0 sm:p-4 xl:p-8">
                    <ScheduleDashboard
                        initialSettingsTab={settingsTab}
                        onSettingsClosed={closeSettings}
                    />
                </div>
            </main>
        </div>
    );
}
