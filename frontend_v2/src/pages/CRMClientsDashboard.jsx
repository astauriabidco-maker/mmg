import React from 'react';
import { ClipboardList, FileClock, Users } from 'lucide-react';
import PartnerDirectory from '../components/PartnerDirectory';

export default function CRMClientsDashboard() {
    return (
        <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
            <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-6">
                    <div className="max-w-3xl">
                        <div className="flex items-center gap-3 mb-3">
                            <div className="w-11 h-11 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                                <Users className="w-6 h-6" />
                            </div>
                            <div>
                                <p className="text-xs font-black text-indigo-500 uppercase tracking-widest">CRM</p>
                                <h2 className="text-2xl font-black text-slate-900 tracking-tight">Clients</h2>
                            </div>
                        </div>
                        <p className="text-sm font-medium text-slate-500 leading-6">
                            Centralisez les clients, contacts, coordonnées et informations légales utiles au suivi commercial.
                            Cette vue sert de base CRM dédiée avant de relier les historiques de devis, ventes et relances.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 lg:w-[28rem]">
                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                            <div className="flex items-center gap-2 text-slate-500 mb-2">
                                <FileClock className="w-4 h-4" />
                                <span className="text-[10px] font-black uppercase tracking-widest">Historique</span>
                            </div>
                            <p className="text-sm font-bold text-slate-800">Timeline client</p>
                            <p className="text-xs font-medium text-slate-500 mt-1">Espace prêt pour les interactions et relances.</p>
                        </div>
                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                            <div className="flex items-center gap-2 text-slate-500 mb-2">
                                <ClipboardList className="w-4 h-4" />
                                <span className="text-[10px] font-black uppercase tracking-widest">Devis</span>
                            </div>
                            <p className="text-sm font-bold text-slate-800">Suivi commercial</p>
                            <p className="text-xs font-medium text-slate-500 mt-1">Zone réservée aux devis et ventes associés.</p>
                        </div>
                    </div>
                </div>
            </section>

            <section className="h-[720px] min-h-[560px] overflow-hidden border border-slate-200 rounded-2xl bg-white shadow-sm">
                <PartnerDirectory type="CLIENT" />
            </section>
        </div>
    );
}
