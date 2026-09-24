import React, { useEffect, useState } from 'react';
import { Bot, MessageCircle, Sparkles, X } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import InsightDashboard from '../pages/InsightDashboard';

export default function FloatingInsightAssistant() {
    const { user } = useAuth();
    const location = useLocation();
    const [isOpen, setIsOpen] = useState(false);

    const hiddenOnPublicPage = location.pathname === '/login' || location.pathname.startsWith('/portal/');

    useEffect(() => {
        if (!user || hiddenOnPublicPage) return undefined;

        const onKeyDown = (event) => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                setIsOpen(true);
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [hiddenOnPublicPage, user]);

    if (!user || hiddenOnPublicPage) return null;

    return (
        <>
            <button
                type="button"
                onClick={() => setIsOpen(true)}
                className="fixed bottom-5 right-5 z-[90] flex h-16 w-16 items-center justify-center rounded-full border border-indigo-200 bg-slate-950 text-white shadow-2xl shadow-indigo-500/30 transition duration-200 hover:-translate-y-0.5 hover:bg-indigo-600 focus:outline-none focus:ring-4 focus:ring-indigo-200 sm:bottom-7 sm:right-7"
                aria-label="Ouvrir le copilote IA"
                title="Copilote IA"
            >
                <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-white bg-emerald-500">
                    <span className="h-2 w-2 rounded-full bg-white" />
                </span>
                <MessageCircle className="h-7 w-7" />
            </button>

            {isOpen && (
                <div className="fixed inset-0 z-[100]">
                    <button
                        type="button"
                        aria-label="Fermer le copilote IA"
                        onClick={() => setIsOpen(false)}
                        className="absolute inset-0 bg-slate-950/30 backdrop-blur-[2px]"
                    />
                    <aside className="absolute bottom-0 right-0 top-auto flex h-[min(760px,calc(100vh-2rem))] w-full max-w-xl flex-col rounded-t-3xl border border-slate-200 bg-white shadow-2xl animate-fade-in sm:bottom-6 sm:right-6 sm:w-[520px] sm:rounded-3xl xl:w-[560px]">
                        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                            <div className="flex min-w-0 items-center gap-3">
                                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-300">
                                    <Bot className="h-5 w-5" />
                                </div>
                                <div className="min-w-0">
                                    <p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.26em] text-indigo-500">
                                        <Sparkles className="h-3.5 w-3.5" />
                                        Copilote IA
                                    </p>
                                    <h2 className="truncate text-lg font-black text-slate-950">Insight Engine</h2>
                                </div>
                            </div>
                            <button
                                type="button"
                                onClick={() => setIsOpen(false)}
                                className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="min-h-0 flex-1">
                            <InsightDashboard mode="drawer" />
                        </div>
                    </aside>
                </div>
            )}
        </>
    );
}
