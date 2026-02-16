import React from 'react';
import { Link } from 'react-router-dom';
import { LayoutDashboard, Activity, ClipboardList, Settings, LogOut, X, Box } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function Sidebar({ activeView, setActiveView, isOpen, setIsOpen }) {
    const { logout } = useAuth();

    const menuItems = [
        { id: 'dashboard', label: 'Tableau de Bord', icon: LayoutDashboard, type: 'internal' },
        { id: 'live', label: 'Atelier Live', icon: Activity, type: 'internal' },
        { id: 'orders', label: 'Suivi Commandes', icon: ClipboardList, type: 'internal' },
        { id: 'mmg', label: 'Dossiers MMG', icon: ClipboardList, type: 'external', path: '/mmg' },
        { id: 'config', label: 'Configuration', icon: Settings, type: 'internal' },
    ];

    return (
        <>
            {/* Mobile Overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`
                fixed top-0 left-0 bottom-0 w-72 bg-slate-900 border-r border-slate-800 z-50 transform transition-transform duration-300 ease-in-out
                ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            `}>
                <div className="flex flex-col h-full">
                    {/* Header */}
                    <div className="p-6 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/20">
                                <Box className="w-6 h-6 text-white" />
                            </div>
                            <div>
                                <h2 className="text-white font-black tracking-tight leading-none uppercase">MMG</h2>
                                <p className="text-slate-500 text-[10px] font-bold tracking-widest uppercase mt-1">Atelier Connecté</p>
                            </div>
                        </div>
                        <button onClick={() => setIsOpen(false)} className="lg:hidden text-slate-400 p-2 hover:bg-slate-800 rounded-lg">
                            <X className="w-6 h-6" />
                        </button>
                    </div>

                    {/* Navigation */}
                    <nav className="flex-1 px-4 py-6 space-y-1">
                        {menuItems.map((item) => {
                            const isSelected = activeView === item.id;
                            const content = (
                                <>
                                    <item.icon className={`w-5 h-5 ${isSelected ? 'text-white' : 'text-slate-500'}`} />
                                    {item.label}
                                </>
                            );
                            const className = `
                                w-full flex items-center gap-3 px-4 py-3 rounded-xl font-bold transition-all duration-200
                                ${isSelected
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'}
                            `;

                            if (item.type === 'external') {
                                return (
                                    <Link
                                        key={item.id}
                                        to={item.path}
                                        className={className}
                                        onClick={() => { if (window.innerWidth < 1024) setIsOpen(false); }}
                                    >
                                        {content}
                                    </Link>
                                );
                            }

                            return (
                                <button
                                    key={item.id}
                                    onClick={() => {
                                        setActiveView(item.id);
                                        if (window.innerWidth < 1024) setIsOpen(false);
                                    }}
                                    className={className}
                                >
                                    {content}
                                </button>
                            );
                        })}
                    </nav>

                    {/* Footer */}
                    <div className="p-4 border-t border-slate-800 space-y-2">
                        <button
                            onClick={logout}
                            className="w-full flex items-center gap-3 px-4 py-3 text-slate-400 hover:bg-red-500/10 hover:text-red-400 rounded-xl font-bold transition-all"
                        >
                            <LogOut className="w-5 h-5" />
                            Déconnexion
                        </button>
                    </div>
                </div>
            </aside>
        </>
    );
}
