import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { TrendingUp, AlertTriangle, Clock, Activity, LogOut, Upload, Menu, Search, Filter, ArrowUpRight, ArrowDownRight, ChevronRight, Users, Settings, Box } from 'lucide-react';
import { Link } from 'react-router-dom';
import StationManager from '../components/StationManager';
import OperatorManager from '../components/OperatorManager';
import Sidebar from '../components/Sidebar';

export default function ManagerDashboard() {
    const { logout } = useAuth();
    const [stats, setStats] = useState({ total: 0, avg_time: 0, delay_rate: 0, active: 0, defects: 0 });
    const [chartData, setChartData] = useState([]);
    const [recentOrders, setRecentOrders] = useState([]);
    const [activeView, setActiveView] = useState('dashboard'); // 'dashboard', 'live', 'orders', 'config'
    const [configTab, setConfigTab] = useState('stations');
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [materialFilter, setMaterialFilter] = useState('ALL');

    const fetchData = async () => {
        try {
            const kpi = await api.get('/v2/analytics/daily');
            setStats(kpi.data);
            const chart = await api.get('/v2/analytics/hourly');
            setChartData(chart.data);
            const recent = await api.get('/v2/ingest/recent');
            setRecentOrders(recent.data);
        } catch (e) {
            console.error(e);
            setStats({ total: 0, avg_time: "Err", delay_rate: 0, active: 0, defects: 0 });
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

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
                                    activeView === 'orders' ? 'Suivi Commandes' : 'Configuration'}
                        </h1>
                    </div>

                    <div className="flex items-center gap-4">
                        <Link
                            to="/upload"
                            className="hidden sm:inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-xl transition-all shadow-lg shadow-blue-500/20 active:scale-95"
                        >
                            <Upload className="w-4 h-4" />
                            Nouvel Import
                        </Link>
                        <div className="h-8 w-[1px] bg-slate-200 mx-2 hidden sm:block"></div>
                        <div className="flex items-center gap-3">
                            <span className="relative flex h-3 w-3">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                            </span>
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider hidden md:block">Système Live</span>
                        </div>
                    </div>
                </header>

                {/* View Container */}
                <div className="p-8">
                    {activeView === 'dashboard' && renderDashboardView()}
                    {activeView === 'live' && renderLiveView()}
                    {activeView === 'orders' && renderOrdersView()}
                    {activeView === 'config' && renderConfigView()}
                </div>
            </main>
        </div>
    );

    function renderDashboardView() {
        return (
            <div className="space-y-8 max-w-7xl mx-auto">
                {/* KPI Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
                    <KpiCard
                        icon={Activity}
                        title="Tâches Réalisées"
                        value={stats.total}
                        trend="+12%"
                        isUp={true}
                        color="blue"
                    />
                    <KpiCard
                        icon={AlertTriangle}
                        title="Incidents"
                        value={stats.defects}
                        trend={stats.defects > 0 ? "Attention" : "Sain"}
                        isUp={false}
                        color={stats.defects > 0 ? "red" : "emerald"}
                    />
                    <KpiCard
                        icon={TrendingUp}
                        title="Charge Atelier"
                        value={stats.active}
                        trend="En direct"
                        isUp={true}
                        color="indigo"
                    />
                    <KpiCard
                        icon={Clock}
                        title="Temps Moyen / Poste"
                        value={stats.avg_time}
                        trend="-5 min"
                        isUp={true}
                        color="emerald"
                    />
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Main Chart */}
                    <div className="lg:col-span-2 bg-white p-8 rounded-3xl border border-slate-200 shadow-sm shrink-0">
                        <div className="flex items-center justify-between mb-8">
                            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                                <div className="w-1.5 h-6 bg-blue-600 rounded-full"></div>
                                Rythme de Production (24h)
                            </h2>
                            <select className="bg-slate-50 border-none text-xs font-bold text-slate-500 rounded-lg px-3 py-1 outline-none ring-1 ring-slate-200">
                                <option>Aujourd'hui</option>
                                <option>Hier</option>
                            </select>
                        </div>
                        <div className="h-[350px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={chartData}>
                                    <defs>
                                        <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1} />
                                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                    <XAxis
                                        dataKey="name"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#94a3b8', fontSize: 11 }}
                                        dy={10}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#94a3b8', fontSize: 11 }}
                                    />
                                    <Tooltip
                                        contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1)' }}
                                    />
                                    <Area
                                        type="monotone"
                                        dataKey="count"
                                        stroke="#3b82f6"
                                        strokeWidth={3}
                                        fillOpacity={1}
                                        fill="url(#colorCount)"
                                    />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Quick Stats side panel */}
                    <div className="bg-slate-900 rounded-3xl p-8 text-white shadow-xl flex flex-col justify-between">
                        <div>
                            <h3 className="text-xl font-bold mb-2">Performateur Flash</h3>
                            <p className="text-slate-400 text-sm mb-6">Résumé rapide des performances de l'équipe.</p>

                            <div className="space-y-6">
                                <div className="flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/10">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-emerald-500/20 rounded-xl flex items-center justify-center">
                                            <Users className="w-5 h-5 text-emerald-400" />
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 font-bold uppercase">Opérateurs Actifs</p>
                                            <p className="text-lg font-bold">12 / 15</p>
                                        </div>
                                    </div>
                                    <ArrowUpRight className="w-5 h-5 text-emerald-400" />
                                </div>

                                <div className="flex items-center justify-between p-4 bg-white/5 rounded-2xl border border-white/10">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 bg-amber-500/20 rounded-xl flex items-center justify-center">
                                            <Settings className="w-5 h-5 text-amber-400" />
                                        </div>
                                        <div>
                                            <p className="text-xs text-slate-400 font-bold uppercase">Postes Tournants</p>
                                            <p className="text-lg font-bold">5 Stations</p>
                                        </div>
                                    </div>
                                    <ChevronRight className="w-5 h-5 text-slate-500" />
                                </div>
                            </div>
                        </div>

                        <div className="mt-8 pt-6 border-t border-white/10">
                            <p className="text-xs text-slate-500 font-bold uppercase mb-4 tracking-widest text-center">Objectif du Jour</p>
                            <div className="w-full bg-white/5 h-2 rounded-full overflow-hidden">
                                <div className="bg-blue-500 h-full w-[70%]" />
                            </div>
                            <p className="text-right text-xs mt-2 font-bold text-blue-400">70% atteint</p>
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

    function renderConfigView() {
        return (
            <div className="max-w-4xl mx-auto space-y-8">
                <div className="flex gap-4 p-1.5 bg-slate-100 rounded-2xl w-fit">
                    <button
                        onClick={() => setConfigTab('stations')}
                        className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${configTab === 'stations' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                        Postes de Travail
                    </button>
                    <button
                        onClick={() => setConfigTab('operators')}
                        className={`px-6 py-2.5 rounded-xl text-sm font-bold transition-all ${configTab === 'operators' ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                    >
                        Opérateurs
                    </button>
                </div>

                <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-sm animate-fade-in">
                    {configTab === 'stations' ? <StationManager /> : <OperatorManager />}
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
    const [stats, setStats] = useState({ queue: 0, in_progress: 0 });

    // In a real app, this would fetch from a per-station stats endpoint
    useEffect(() => {
        setStats({
            queue: Math.floor(Math.random() * 10),
            in_progress: Math.floor(Math.random() * 3)
        });
    }, []);

    const hasIssue = stats.queue > 8;

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
