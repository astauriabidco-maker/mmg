import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell } from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, AlertTriangle, Clock, Activity, LogOut, Upload, Menu, Search, Filter, ArrowUpRight, ArrowDownRight, ChevronRight, Users, Settings, Box, Banknote, CheckCircle2, Factory, Package, BarChart3, Sparkles, X, Scissors } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import StationManager from '../components/StationManager';
import OperatorManager from '../components/OperatorManager';
import Sidebar from '../components/Sidebar';
import CuttingOptimizerModal from '../components/CuttingOptimizerModal';
import StockDashboard from './StockDashboard';
import PurchasesDashboard from './PurchasesDashboard';
import SalesDashboard from './SalesDashboard';
import ConfigDashboard from './ConfigDashboard';
import AccountingDashboard from './AccountingDashboard';
import DeliveryDashboard from './DeliveryDashboard';
import InsightDashboard from './InsightDashboard';
import RBACMatrix from '../components/RBACMatrix';
import PlatformSettings from '../components/PlatformSettings';

export default function ManagerDashboard() {
    const { logout } = useAuth();

    const [activeView, setActiveView] = useState('dashboard'); // 'dashboard', 'live', 'orders', 'stock', 'config'
    const [configTab, setConfigTab] = useState('stations');
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [materialFilter, setMaterialFilter] = useState('ALL');
    const [insightModalOpen, setInsightModalOpen] = useState(false);
    const [cuttingModalOpen, setCuttingModalOpen] = useState(false);
    const location = useLocation();

    useEffect(() => {
        if (location.state && location.state.view) {
            setActiveView(location.state.view);
            // Replace state to avoid loop on reload
            window.history.replaceState({}, document.title)
        }
    }, [location.state]);

    const { data: stats = { total: 0, avg_time: "...", delay_rate: 0, active: 0, defects: 0 } } = useQuery({
        queryKey: ['manager-stats'],
        queryFn: async () => {
            const { data } = await api.get('/v2/analytics/daily');
            return data;
        },
        refetchInterval: 10000,
    });

    const { data: chartData = [] } = useQuery({
        queryKey: ['manager-chart'],
        queryFn: async () => {
            const { data } = await api.get('/v2/analytics/hourly');
            return data;
        },
        refetchInterval: 10000,
    });

    const { data: recentOrders = [] } = useQuery({
        queryKey: ['manager-recent-orders'],
        queryFn: async () => {
            const { data } = await api.get('/v2/ingest/recent');
            return data;
        },
        refetchInterval: 10000,
    });

    const filteredOrders = recentOrders.filter(o =>
        (searchTerm === '' || o.reference.toLowerCase().includes(searchTerm.toLowerCase()) || o.client_name?.toLowerCase().includes(searchTerm.toLowerCase())) &&
        (materialFilter === 'ALL' || o.material === materialFilter)
    );

    return (
        <div className="min-h-screen bg-slate-50 flex">
            {/* Sidebar Component */}
            <Sidebar
                activeView={activeView}
                setActiveView={setActiveView}
                isOpen={isSidebarOpen}
                setIsOpen={setIsSidebarOpen}
            />

            {/* Main Content */}
            <main className="flex-1 lg:ml-72 transition-all duration-300">
                {/* Header / Top Bar */}
                <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-200 px-8 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={() => setIsSidebarOpen(true)}
                            className="lg:hidden p-2 text-slate-600 hover:bg-slate-100 rounded-lg"
                        >
                            <Menu className="w-6 h-6" />
                        </button>
                        <h1 className="text-xl font-bold text-slate-900 capitalize">
                            {activeView === 'dashboard' ? 'Vue d\'Ensemble' :
                                activeView === 'live' ? 'Atelier Live' :
                                    activeView === 'orders' ? 'Suivi Commandes' :
                                        activeView === 'stock' ? 'Gestion de Stock' : 
                                            activeView === 'purchases' ? 'Achats & Approvisionnement' :
                                                activeView === 'sales' ? 'CRM & Devis (Ventes)' : 
                                                        activeView === 'logistics' ? 'Logistique & Expéditions' : 
                                                            activeView === 'insight' ? 'Insight Engine (IA)' : 'Configuration'}
                        </h1>
                    </div>

                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-3">
                            <span className="relative flex h-3 w-3">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                            </span>
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider hidden md:block">Système Live</span>
                        </div>
                    </div>
                </header>

                {/* AI Search Bar directly below header */}
                {activeView === 'dashboard' && (
                    <div className="bg-white border-b border-slate-200 p-4 shadow-sm relative z-20">
                        <div 
                            onClick={() => setInsightModalOpen(true)}
                            className="max-w-3xl mx-auto bg-slate-100 hover:bg-slate-200 cursor-text transition-colors rounded-full flex items-center px-6 py-3 border border-transparent focus-within:border-indigo-400 focus-within:bg-white focus-within:shadow-lg focus-within:shadow-indigo-500/10"
                        >
                            <Sparkles className="w-5 h-5 text-indigo-500 mr-3 shrink-0" />
                            <input 
                                type="text"
                                placeholder="Demander à l'IA... (Ex: Quel est le CA ? Quels sont les produits les plus vendus ?)"
                                className="bg-transparent border-none outline-none w-full font-medium text-slate-700 pointer-events-none"
                                readOnly
                            />
                            <div className="flex items-center gap-1">
                                <kbd className="hidden sm:inline-block bg-white border border-slate-300 rounded px-2 py-0.5 text-xs font-bold text-slate-500">⌘</kbd>
                                <kbd className="hidden sm:inline-block bg-white border border-slate-300 rounded px-2 py-0.5 text-xs font-bold text-slate-500">K</kbd>
                            </div>
                        </div>
                    </div>
                )}

                {/* View Container */}
                <div className="p-8">
                    {activeView === 'dashboard' && renderDashboardView()}
                    {activeView === 'live' && renderLiveView()}
                    {activeView === 'orders' && renderOrdersView()}
                    {activeView === 'stock' && <StockDashboard />}
                    {activeView === 'purchases' && <PurchasesDashboard />}
                    {activeView === 'sales' && <SalesDashboard />}
                    {activeView === 'accounting' && <AccountingDashboard />}
                    {activeView === 'logistics' && <DeliveryDashboard />}
                    {activeView === 'insight' && <InsightDashboard />}
                    {activeView === 'config' && <PlatformSettings />}
                </div>

                {/* CUTTING OPTIMIZER MODAL */}
                {cuttingModalOpen && <CuttingOptimizerModal onClose={() => setCuttingModalOpen(false)} />}

                {/* FLOATING INSIGHT MODAL */}
                {insightModalOpen && (
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
                        <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-5xl overflow-hidden flex flex-col relative animate-fade-in border border-slate-200">
                            <button 
                                onClick={() => setInsightModalOpen(false)}
                                className="absolute top-4 right-4 z-10 w-10 h-10 bg-white/80 backdrop-blur-md rounded-full flex items-center justify-center text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors shadow-sm"
                            >
                                <X className="w-6 h-6" />
                            </button>
                            <div className="h-[80vh]">
                                <InsightDashboard />
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );

    function renderDashboardView() {
        const presentationData = [
            { name: 'Lun', sales: 4000, prod: 2400 },
            { name: 'Mar', sales: 3000, prod: 1398 },
            { name: 'Mer', sales: 2000, prod: 9800 },
            { name: 'Jeu', sales: 2780, prod: 3908 },
            { name: 'Ven', sales: 1890, prod: 4800 },
            { name: 'Sam', sales: 2390, prod: 3800 },
            { name: 'Dim', sales: 3490, prod: 4300 },
        ];

        return (
            <div className="space-y-6 max-w-7xl mx-auto font-sans animate-fade-in pb-12">
                
                {/* HERO EXECUTIVE SUMMARY */}
                <div className="bg-slate-900 rounded-[2rem] p-8 md:p-10 text-white shadow-2xl relative overflow-hidden mb-8">
                    {/* Background decorations */}
                    <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
                    <div className="absolute bottom-0 left-0 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2"></div>
                    
                    <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
                        <div>
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><Banknote className="w-4 h-4 text-emerald-400"/> CA MENSUEL</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                42.8 <span className="text-xl text-slate-500 font-bold">K €</span>
                            </h2>
                            <p className="text-emerald-400 text-sm font-bold flex items-center gap-1 mt-3">
                                <ArrowUpRight className="w-4 h-4" /> +15.2% vs M-1
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><Factory className="w-4 h-4 text-blue-400"/> EN PRODUCTION</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                {stats.active || 24} <span className="text-xl text-slate-500 font-bold">dossiers</span>
                            </h2>
                            <p className="text-blue-400 text-sm font-bold flex items-center gap-1 mt-3">
                                <Activity className="w-4 h-4" /> Flux tendu opérationnel
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><Package className="w-4 h-4 text-purple-400"/> VALEUR INVENTAIRE</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                115.3 <span className="text-xl text-slate-500 font-bold">K €</span>
                            </h2>
                            <p className="text-slate-300 text-sm font-bold flex items-center gap-1 mt-3">
                                <ArrowDownRight className="w-4 h-4 text-rose-400" /> -4.1% rotation (Sain)
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-amber-400"/> TAUX DE RENDEMENT</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                98.2 <span className="text-xl text-slate-500 font-bold">%</span>
                            </h2>
                            <p className="text-amber-400 text-sm font-bold flex items-center gap-1 mt-3">
                                Objectif: 99.0%
                            </p>
                        </div>
                    </div>
                </div>

                {/* CHARTS CONTAINER */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Main Analytics: CA vs Prod */}
                    <div className="lg:col-span-2 bg-white p-8 rounded-3xl border border-slate-200 shadow-sm shadow-slate-200/50">
                        <div className="flex items-center justify-between mb-8">
                            <div>
                                <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                                    <BarChart3 className="w-6 h-6 text-blue-500" />
                                    Dynamique des Revenus
                                </h2>
                                <p className="text-slate-500 text-sm font-medium mt-1">Comparatif des encaissements VS Production valorisée</p>
                            </div>
                            <div className="flex gap-2 bg-slate-100 p-1 rounded-xl">
                                <button className="px-4 py-2 text-xs font-bold bg-white shadow-sm rounded-lg text-slate-800">Semaine</button>
                                <button className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-800 rounded-lg transition-colors">Mois</button>
                            </div>
                        </div>
                        <div className="h-[350px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={presentationData}>
                                    <defs>
                                        <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="colorProd" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                                    <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} dy={10} />
                                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} />
                                    <Tooltip contentStyle={{ borderRadius: '16px', border: '1px solid #e2e8f0', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)', fontWeight: 'bold' }} />
                                    <Area type="monotone" dataKey="sales" name="C.A Encaissé" stroke="#10b981" strokeWidth={4} fillOpacity={1} fill="url(#colorSales)" />
                                    <Area type="monotone" dataKey="prod" name="Prod Valorisée" stroke="#3b82f6" strokeWidth={4} fillOpacity={1} fill="url(#colorProd)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Operational Highlights */}
                    <div className="space-y-6">
                        {/* Atelier Live Minified */}
                        <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-3xl p-8 text-white shadow-xl shadow-blue-500/20 relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-32 h-32 bg-white/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2"></div>
                            <h3 className="text-xl font-bold mb-1">Pulsations Atelier</h3>
                            <p className="text-blue-200 text-sm font-medium mb-6">En temps réel sur les chaînes</p>
                            
                            <div className="space-y-3 relative z-10">
                                <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-4 border border-white/10 flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-white/10 rounded-xl"><Activity className="w-5 h-5 text-white" /></div>
                                        <div><p className="text-xs text-blue-200 font-bold uppercase uppercase tracking-wider">Tâches Réalisées</p><p className="text-2xl font-black leading-none">{stats.total || 142}</p></div>
                                    </div>
                                </div>
                                <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-4 border border-white/10 flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-emerald-500/20 rounded-xl"><Clock className="w-5 h-5 text-emerald-300" /></div>
                                        <div><p className="text-xs text-blue-200 font-bold uppercase uppercase tracking-wider">Temps Moyen</p><p className="text-xl font-black leading-none text-emerald-300">{stats.avg_time || "12 min"}</p></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Recent Alerts Container */}
                        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm h-[calc(100%-250px)]">
                            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                                <AlertTriangle className="w-5 h-5 text-amber-500" /> Aléas & Alertes
                            </h3>
                            {stats.defects === 0 ? (
                                <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                                    <CheckCircle2 className="w-12 h-12 text-emerald-400 opacity-50 mb-2" />
                                    <p className="font-bold">Zéro incident remonté</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <div className="p-3 bg-red-50 border border-red-100 rounded-xl flex gap-3 text-red-700">
                                        <AlertTriangle className="w-5 h-5 shrink-0" />
                                        <p className="text-sm font-bold">Unité de Sciage ALU: Lame H.S, requête maintenance urgente (Il y a 15 min)</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    function renderLiveView() {
        return (
            <div className="max-w-7xl mx-auto space-y-6">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h2 className="text-2xl font-bold text-slate-900">Vue au Sol - Live</h2>
                        <p className="text-slate-500">État de charge en temps réel par poste de travail.</p>
                    </div>
                    <button 
                        onClick={() => setCuttingModalOpen(true)}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-lg flex items-center gap-2 font-bold transition-all"
                    >
                        <Scissors className="w-5 h-5" />
                        IA : Optimisation Découpe
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                    {['PVC_DEBIT', 'PVC_SOUDURE', 'PVC_MOULES', 'ALU_DEBIT', 'ALU_ASSEMBLAGE'].map(station => (
                        <StationLiveCard key={station} name={station} />
                    ))}
                </div>
            </div>
        );
    }

    function renderOrdersView() {
        return (
            <div className="max-w-7xl mx-auto space-y-6">
                {/* FILTERS BAR */}
                <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-4">
                    <div className="flex-1 min-w-[300px] relative">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Rechercher une commande, un client..."
                            className="w-full pl-12 pr-4 py-3 bg-slate-50 border-none rounded-xl outline-none ring-1 ring-slate-100 focus:ring-2 focus:ring-blue-500 transition-all font-medium text-slate-700"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>

                    <div className="flex items-center gap-2 bg-slate-50 p-1.5 rounded-xl ring-1 ring-slate-100">
                        <button
                            onClick={() => setMaterialFilter('ALL')}
                            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${materialFilter === 'ALL' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            Tout
                        </button>
                        <button
                            onClick={() => setMaterialFilter('PVC')}
                            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${materialFilter === 'PVC' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            PVC
                        </button>
                        <button
                            onClick={() => setMaterialFilter('ALU')}
                            className={`px-4 py-2 rounded-lg text-xs font-bold transition-all ${materialFilter === 'ALU' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                        >
                            ALU
                        </button>
                    </div>

                    <button className="p-3 bg-slate-50 hover:bg-slate-100 text-slate-500 rounded-xl ring-1 ring-slate-100 transition-colors">
                        <Filter className="w-5 h-5" />
                    </button>
                </div>

                {/* TABLE */}
                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-50/50 border-b border-slate-100">
                                <th className="py-5 px-8 text-xs font-black text-slate-400 uppercase tracking-widest">Référence</th>
                                <th className="py-5 px-4 text-xs font-black text-slate-400 uppercase tracking-widest">Client</th>
                                <th className="py-5 px-4 text-xs font-black text-slate-400 uppercase tracking-widest">Produit</th>
                                <th className="py-5 px-4 text-xs font-black text-slate-400 uppercase tracking-widest">Matériau</th>
                                <th className="py-5 px-4 text-xs font-black text-slate-400 uppercase tracking-widest text-center">Qté</th>
                                <th className="py-5 px-8 text-xs font-black text-slate-400 uppercase tracking-widest text-right">Statut</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                            {filteredOrders.map((order) => (
                                <tr key={order.id} className="group hover:bg-blue-50/30 transition-colors">
                                    <td className="py-5 px-8">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                                                <Box className="w-4 h-4" />
                                            </div>
                                            <span className="font-bold text-slate-700">{order.reference}</span>
                                        </div>
                                    </td>
                                    <td className="py-5 px-4">
                                        <p className="font-semibold text-slate-600 truncate max-w-[150px]">{order.client_name || "N/A"}</p>
                                    </td>
                                    <td className="py-5 px-4">
                                        <p className="text-sm text-slate-500">{order.width} x {order.height} mm</p>
                                    </td>
                                    <td className="py-5 px-4">
                                        <span className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider ${order.material === 'PVC' ? 'bg-indigo-50 text-indigo-600' : 'bg-amber-50 text-amber-700'}`}>
                                            {order.material}
                                        </span>
                                    </td>
                                    <td className="py-5 px-4 text-center font-bold text-slate-700">{order.quantity}</td>
                                    <td className="py-5 px-8 text-right">
                                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-50 text-emerald-600 text-xs font-bold ring-1 ring-emerald-100">
                                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                            Validé
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {filteredOrders.length === 0 && (
                        <div className="py-20 text-center space-y-4">
                            <Search className="w-12 h-12 text-slate-200 mx-auto" />
                            <p className="text-slate-400 font-medium italic">Aucune commande ne correspond à votre recherche.</p>
                        </div>
                    )}
                </div>
            </div>
        );
    }
}

// Sub-components

function KpiCard({ icon: Icon, title, value, trend, isUp, color }) {
    const colors = {
        blue: "bg-blue-600 text-white shadow-blue-200",
        emerald: "bg-emerald-500 text-white shadow-emerald-200",
        red: "bg-red-500 text-white shadow-red-200",
        indigo: "bg-indigo-600 text-white shadow-indigo-200"
    };

    return (
        <div className="bg-white p-8 rounded-[32px] border border-slate-200 shadow-sm relative overflow-hidden group hover:shadow-xl transition-all duration-500">
            <div className="relative z-10 flex flex-col h-full justify-between">
                <div>
                    <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-6 shadow-lg ${colors[color]}`}>
                        <Icon className="w-6 h-6" strokeWidth={2.5} />
                    </div>
                    <p className="text-slate-400 text-xs font-black uppercase tracking-widest mb-1">{title}</p>
                    <h3 className="text-4xl font-black text-slate-900 tracking-tighter">{value}</h3>
                </div>

                <div className="mt-6 flex items-center gap-2">
                    <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black ${isUp ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'}`}>
                        {isUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {trend}
                    </div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">vs hier</span>
                </div>
            </div>

            {/* Subtle background decoration */}
            <div className="absolute -right-4 -bottom-4 opacity-[0.03] group-hover:scale-110 transition-transform duration-700 origin-center pointer-events-none">
                <Icon className="w-40 h-40" />
            </div>
        </div>
    );
}

function StationLiveCard({ name }) {
    const { data: queueData = [], isLoading } = useQuery({
        queryKey: ['station-queue', name],
        queryFn: async () => {
            const res = await api.get(`/v2/planning/${name}`);
            return res.data;
        },
        refetchInterval: 5000, // Auto-refresh every 5s
    });

    const stats = {
        queue: queueData.filter(item => item.status === 'PENDING').length,
        in_progress: queueData.filter(item => item.status === 'IN_PROGRESS').length
    };

    const hasIssue = stats.queue > 8 || queueData.some(item => item.status === 'ISSUE');

    return (
        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm hover:border-blue-300 transition-all group">
            <div className="flex items-center justify-between mb-6">
                <h4 className="font-black text-slate-800 tracking-tight">{name.replace('_', ' ')}</h4>
                <div className={`w-3 h-3 rounded-full ${hasIssue ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`} />
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-50 p-4 rounded-2xl">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">En attente</p>
                    <p className="text-2xl font-black text-slate-800">{stats.queue}</p>
                </div>
                <div className="bg-blue-50 p-4 rounded-2xl">
                    <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">En cours</p>
                    <p className="text-2xl font-black text-blue-600">{stats.in_progress}</p>
                </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-50 flex items-center justify-between">
                <Link
                    to={`/dashboard/${name}`}
                    className="text-xs font-black text-blue-500 hover:text-blue-600 flex items-center gap-1 group/btn"
                >
                    Voir File
                    <ChevronRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" />
                </Link>
                {hasIssue && <span className="text-[10px] font-black text-red-500 uppercase tracking-widest">Surcharge</span>}
            </div>
        </div>
    );
}
