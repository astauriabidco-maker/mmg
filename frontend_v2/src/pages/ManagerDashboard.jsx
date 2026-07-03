import React, { useState, useEffect } from 'react';
import api, { API_BASE_URL } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area, PieChart, Pie, Cell } from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, AlertTriangle, Clock, Activity, LogOut, Upload, Menu, Search, Filter, ArrowUpRight, ArrowDownRight, ChevronRight, ChevronLeft, Users, Settings, Box, Banknote, CheckCircle2, Factory, Package, BarChart3, Sparkles, X, Scissors, Download, FileText, FileSpreadsheet, ArrowUpDown } from 'lucide-react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import StationManager from '../components/StationManager';
import OperatorManager from '../components/OperatorManager';
import Sidebar from '../components/Sidebar';
import CuttingOptimizerModal from '../components/CuttingOptimizerModal';
import StockDashboard from './StockDashboard';
import PurchasesDashboard from './PurchasesDashboard';
import SalesDashboard from './SalesDashboard';
import CRMClientsDashboard from './CRMClientsDashboard';
import SaleDetailPage from './SaleDetailPage';
import ConfigDashboard from './ConfigDashboard';
import AccountingDashboard from './AccountingDashboard';
import DeliveryDashboard from './DeliveryDashboard';
import InsightDashboard from './InsightDashboard';
import RBACMatrix from '../components/RBACMatrix';
import PlatformSettings from '../components/PlatformSettings';

export default function ManagerDashboard() {
    const { logout } = useAuth();
    const location = useLocation();
    const [searchParams, setSearchParams] = useSearchParams();

    const [activeView, setActiveView] = useState(() => location.state?.view || searchParams.get('view') || 'dashboard'); // 'dashboard', 'live', 'orders', 'stock', 'config'
    const [configTab, setConfigTab] = useState('stations');
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [materialFilter, setMaterialFilter] = useState('ALL');
    const [insightModalOpen, setInsightModalOpen] = useState(false);
    const [cuttingModalOpen, setCuttingModalOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState('ALL');
    const [selectedOrder, setSelectedOrder] = useState(null);
    const [selectedStation, setSelectedStation] = useState(null);
    const [sortConfig, setSortConfig] = useState({ key: 'id', direction: 'desc' });
    const [currentPage, setCurrentPage] = useState(1);
    const ITEMS_PER_PAGE = 10;
    const sidebarActiveView = activeView === 'sale-detail' ? 'sales' : activeView;
    const headerTitle = activeView === 'dashboard' ? 'Vue d\'Ensemble' :
        activeView === 'live' ? 'Atelier Live' :
            activeView === 'orders' ? 'Suivi Commandes' :
                activeView === 'stock' ? 'Gestion de Stock' :
                    activeView === 'purchases' ? 'Achats & Appro' :
                        activeView === 'sales' || activeView === 'sale-detail' ? 'Commandes & Exécution Ventes' :
                            activeView === 'crm' ? 'CRM Clients - Avant-vente' :
                                activeView === 'accounting' ? 'Facturation (NF525)' :
                                    activeView === 'logistics' ? 'Logistique & Expéditions' :
                                        activeView === 'analytics_atelier' ? 'Performance Atelier' :
                                            activeView === 'insight' ? 'Insight Engine (IA)' : 'Configuration';
    const handleViewChange = (view) => {
        setActiveView(view);
        setSearchParams(view === 'dashboard' ? {} : { view });
    };

    useEffect(() => {
        const requestedView = location.state?.view || searchParams.get('view');
        if (requestedView && requestedView !== activeView) {
            setActiveView(requestedView);
        }
    }, [activeView, location.state, searchParams]);

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

    const { data: kpi = { ca_mensuel: 0, ca_delta_pct: 0, inventory_value: 0, yield_rate: 100, active_dossiers: 0, chart_data: [] } } = useQuery({
        queryKey: ['dashboard-kpi'],
        queryFn: async () => {
            const { data } = await api.get('/v2/analytics/kpi');
            return data;
        },
        refetchInterval: 30000,
    });

    const { data: recentOrders = [] } = useQuery({
        queryKey: ['manager-recent-orders'],
        queryFn: async () => {
            const { data } = await api.get('/v2/ingest/recent');
            return data;
        },
        refetchInterval: 10000,
    });

    const { data: stations = [] } = useQuery({
        queryKey: ['manager-stations'],
        queryFn: async () => {
            const { data } = await api.get('/v2/config/stations');
            return data;
        }
    });

    const { data: trackingOrders = [], isLoading: trackingLoading } = useQuery({
        queryKey: ['orders-tracking'],
        queryFn: async () => {
            const { data } = await api.get('/v2/ingest/orders/tracking');
            return data;
        },
        refetchInterval: 5000,
    });

    const { data: workshopAnalytics, isLoading: analyticsLoading } = useQuery({
        queryKey: ['workshop-analytics'],
        queryFn: async () => {
            const res = await api.get('/v2/analytics/workshop');
            return res.data;
        },
        refetchInterval: 60000 // refresh every minute
    });


    const filteredOrders = recentOrders.filter(o =>
        (searchTerm === '' || o.reference.toLowerCase().includes(searchTerm.toLowerCase()) || o.client_name?.toLowerCase().includes(searchTerm.toLowerCase())) &&
        (materialFilter === 'ALL' || o.material === materialFilter)
    );

    return (
        <div className="min-h-screen bg-slate-50 flex">
            {/* Sidebar Component */}
            <Sidebar
                activeView={sidebarActiveView}
                setActiveView={handleViewChange}
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
                            {headerTitle}
                        </h1>
                    </div>

                    {/* AI Search Bar - Global */}
                    <div 
                        onClick={() => setInsightModalOpen(true)}
                        className="hidden md:flex flex-1 max-w-lg mx-6 bg-slate-100 hover:bg-slate-200 cursor-pointer transition-colors rounded-full items-center px-5 py-2 border border-transparent hover:border-indigo-300 hover:shadow-sm"
                    >
                        <Sparkles className="w-4 h-4 text-indigo-500 mr-2 shrink-0" />
                        <span className="text-sm font-medium text-slate-400 truncate">Demander à l'IA...</span>
                        <div className="flex items-center gap-1 ml-auto">
                            <kbd className="bg-white border border-slate-300 rounded px-1.5 py-0.5 text-[10px] font-bold text-slate-400">⌘</kbd>
                            <kbd className="bg-white border border-slate-300 rounded px-1.5 py-0.5 text-[10px] font-bold text-slate-400">K</kbd>
                        </div>
                    </div>

                    <div className="flex items-center gap-4">
                        {/* Mobile AI button */}
                        <button onClick={() => setInsightModalOpen(true)} className="md:hidden p-2 text-indigo-500 hover:bg-indigo-50 rounded-lg">
                            <Sparkles className="w-5 h-5" />
                        </button>
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
                    {activeView === 'stock' && <StockDashboard />}
                    {activeView === 'purchases' && <PurchasesDashboard />}
                    {activeView === 'sales' && <SalesDashboard />}
                    {activeView === 'crm' && <CRMClientsDashboard />}
                    {activeView === 'sale-detail' && <SaleDetailPage saleId={searchParams.get('id')} embedded />}
                    {activeView === 'accounting' && <AccountingDashboard />}
                    {activeView === 'logistics' && <DeliveryDashboard />}
                    {activeView === 'analytics_atelier' && renderAtelierAnalyticsView()}
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
        const formatMoney = (v) => {
            if (v >= 1000) return `${(v / 1000).toFixed(1)}`;
            return v.toFixed(0);
        };
        const moneyUnit = (v) => v >= 1000 ? 'K €' : '€';
        const caUp = kpi.ca_delta_pct >= 0;
        const defectCount = Number(stats.defects || 0);

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
                                {formatMoney(kpi.ca_mensuel)} <span className="text-xl text-slate-500 font-bold">{moneyUnit(kpi.ca_mensuel)}</span>
                            </h2>
                            <p className={`${caUp ? 'text-emerald-400' : 'text-rose-400'} text-sm font-bold flex items-center gap-1 mt-3`}>
                                {caUp ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />} {caUp ? '+' : ''}{kpi.ca_delta_pct}% vs M-1
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><Factory className="w-4 h-4 text-blue-400"/> EN PRODUCTION</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                {kpi.active_dossiers || stats.active || 0} <span className="text-xl text-slate-500 font-bold">dossiers</span>
                            </h2>
                            <p className="text-blue-400 text-sm font-bold flex items-center gap-1 mt-3">
                                <Activity className="w-4 h-4" /> Flux tendu opérationnel
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><Package className="w-4 h-4 text-purple-400"/> VALEUR INVENTAIRE</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                {formatMoney(kpi.inventory_value)} <span className="text-xl text-slate-500 font-bold">{moneyUnit(kpi.inventory_value)}</span>
                            </h2>
                            <p className="text-slate-300 text-sm font-bold flex items-center gap-1 mt-3">
                                <Package className="w-4 h-4 text-purple-400" /> Valorisation temps réel
                            </p>
                        </div>
                        <div className="border-l border-white/10 pl-8">
                            <p className="text-slate-400 font-bold uppercase tracking-widest text-xs mb-2 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-amber-400"/> TAUX DE RENDEMENT</p>
                            <h2 className="text-4xl lg:text-5xl font-black tracking-tight mt-1 flex items-baseline gap-2">
                                {kpi.yield_rate} <span className="text-xl text-slate-500 font-bold">%</span>
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
                                <AreaChart data={kpi.chart_data.length > 0 ? kpi.chart_data : [{name:'—',sales:0,prod:0}]}>
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
                                        <div><p className="text-xs text-blue-200 font-bold uppercase uppercase tracking-wider">Tâches Réalisées</p><p className="text-2xl font-black leading-none">{stats.total ?? 0}</p></div>
                                    </div>
                                </div>
                                <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-4 border border-white/10 flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-emerald-500/20 rounded-xl"><Clock className="w-5 h-5 text-emerald-300" /></div>
                                        <div><p className="text-xs text-blue-200 font-bold uppercase uppercase tracking-wider">Temps Moyen</p><p className="text-xl font-black leading-none text-emerald-300">{stats.avg_time || "0m 0s"}</p></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Recent Alerts Container */}
                        <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm h-[calc(100%-250px)]">
                            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                                <AlertTriangle className="w-5 h-5 text-amber-500" /> Aléas & Alertes
                            </h3>
                            {defectCount === 0 ? (
                                <div className="flex flex-col items-center justify-center py-8 text-slate-400">
                                    <CheckCircle2 className="w-12 h-12 text-emerald-400 opacity-50 mb-2" />
                                    <p className="font-bold">Zéro incident remonté</p>
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    <div className="p-3 bg-red-50 border border-red-100 rounded-xl flex gap-3 text-red-700">
                                        <AlertTriangle className="w-5 h-5 shrink-0" />
                                        <p className="text-sm font-bold">{defectCount} incident{defectCount > 1 ? 's' : ''} atelier à traiter</p>
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

                <div className="flex gap-6">
                    {/* STATIONS GRID */}
                    <div className={`grid grid-cols-1 md:grid-cols-2 ${selectedStation ? 'xl:grid-cols-2 flex-1' : 'xl:grid-cols-3 w-full'} gap-6 transition-all`}>
                        {stations.map(station => (
                            <StationLiveCard 
                                key={station.code} 
                                name={station.code} 
                                displayName={station.display_name} 
                                isSelected={selectedStation === station.code}
                                onSelect={(name) => setSelectedStation(selectedStation === name ? null : name)}
                            />
                        ))}
                        {stations.length === 0 && (
                            <div className="col-span-full py-12 text-center text-slate-400">
                                Aucune station configurée
                            </div>
                        )}
                    </div>

                    {/* STATION DETAIL PANEL */}
                    {selectedStation && (
                        <StationDetailPanel stationCode={selectedStation} onClose={() => setSelectedStation(null)} />
                    )}
                </div>
            </div>
        );
    }

    function renderOrdersView() {
        const STATUS_MAP = {
            'NEW': { label: 'Nouveau', color: 'bg-slate-100 text-slate-600 ring-slate-200', dot: 'bg-slate-400' },
            'PENDING': { label: 'En attente', color: 'bg-amber-50 text-amber-700 ring-amber-200', dot: 'bg-amber-500' },
            'IN_PROGRESS': { label: 'En cours', color: 'bg-blue-50 text-blue-700 ring-blue-200', dot: 'bg-blue-500 animate-pulse' },
            'PAUSED': { label: 'En pause', color: 'bg-orange-50 text-orange-700 ring-orange-200', dot: 'bg-orange-500' },
            'DONE': { label: 'Terminé', color: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-500' },
            'READY': { label: 'Prêt à livrer', color: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-500' },
            'DELIVERED': { label: 'Livré', color: 'bg-green-50 text-green-800 ring-green-300', dot: 'bg-green-600' },
            'ISSUE': { label: 'Incident', color: 'bg-red-50 text-red-700 ring-red-200', dot: 'bg-red-500 animate-pulse' },
            'DEFECT': { label: 'Défaut', color: 'bg-red-50 text-red-700 ring-red-200', dot: 'bg-red-500' },
        };



        let filtered = trackingOrders.filter(o =>
            (searchTerm === '' || o.reference?.toLowerCase().includes(searchTerm.toLowerCase()) || o.client_name?.toLowerCase().includes(searchTerm.toLowerCase())) &&
            (materialFilter === 'ALL' || o.material === materialFilter) &&
            (statusFilter === 'ALL' || o.status === statusFilter)
        );

        // Sorting
        filtered.sort((a, b) => {
            let valA = a[sortConfig.key];
            let valB = b[sortConfig.key];
            
            if (valA === null || valA === undefined) valA = '';
            if (valB === null || valB === undefined) valB = '';

            if (valA < valB) return sortConfig.direction === 'asc' ? -1 : 1;
            if (valA > valB) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });

        // Pagination
        const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE) || 1;
        const currentData = filtered.slice((currentPage - 1) * ITEMS_PER_PAGE, currentPage * ITEMS_PER_PAGE);

        const handleSort = (key) => {
            let direction = 'asc';
            if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
            setSortConfig({ key, direction });
            setCurrentPage(1);
        };

        const handleExportCSV = () => window.open(`${API_BASE_URL}/v2/ingest/orders/export/csv`, '_blank');
        const handleExportPDF = () => window.open(`${API_BASE_URL}/v2/ingest/orders/export/pdf`, '_blank');

        // KPI summary
        const kpiInProgress = trackingOrders.filter(o => o.status === 'IN_PROGRESS').length;
        const kpiPending = trackingOrders.filter(o => o.status === 'PENDING' || o.status === 'NEW').length;
        const kpiReady = trackingOrders.filter(o => o.status === 'READY' || o.status === 'DELIVERED').length;
        const kpiIssue = trackingOrders.filter(o => o.status === 'ISSUE').length;

        return (
            <div className="max-w-7xl mx-auto space-y-6">
                {/* KPI STRIP */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">En cours</p>
                        <p className="text-3xl font-black text-blue-600">{kpiInProgress}</p>
                    </div>
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">En attente</p>
                        <p className="text-3xl font-black text-amber-600">{kpiPending}</p>
                    </div>
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Prêts / Livrés</p>
                        <p className="text-3xl font-black text-emerald-600">{kpiReady}</p>
                    </div>
                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Incidents</p>
                        <p className="text-3xl font-black text-red-600">{kpiIssue}</p>
                    </div>
                </div>

                {/* FILTERS BAR */}
                <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-[250px] relative">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Rechercher une commande, un client..."
                            className="w-full pl-12 pr-4 py-3 bg-slate-50 border-none rounded-xl outline-none ring-1 ring-slate-100 focus:ring-2 focus:ring-blue-500 transition-all font-medium text-slate-700"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>

                    {/* Material Filter */}
                    <div className="flex items-center gap-1 bg-slate-50 p-1 rounded-xl ring-1 ring-slate-100">
                        {['ALL', 'PVC', 'ALU'].map(mat => (
                            <button key={mat} onClick={() => setMaterialFilter(mat)}
                                className={`px-3 py-2 rounded-lg text-xs font-bold transition-all ${materialFilter === mat ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                            >{mat === 'ALL' ? 'Tout' : mat}</button>
                        ))}
                    </div>

                    {/* Status Filter */}
                    <div className="flex items-center gap-1 bg-slate-50 p-1 rounded-xl ring-1 ring-slate-100 flex-wrap">
                        {['ALL', 'IN_PROGRESS', 'PENDING', 'READY', 'ISSUE'].map(st => (
                            <button key={st} onClick={() => setStatusFilter(st)}
                                className={`px-3 py-2 rounded-lg text-xs font-bold transition-all ${statusFilter === st ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
                            >{st === 'ALL' ? 'Tous' : (STATUS_MAP[st]?.label || st)}</button>
                        ))}
                    </div>

                    <div className="text-xs font-bold text-slate-400 ml-auto mr-4">{filtered.length} commande{filtered.length > 1 ? 's' : ''}</div>

                    {/* Export Buttons */}
                    <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
                        <button onClick={handleExportCSV} className="p-2 hover:bg-slate-100 text-slate-500 rounded-lg transition-colors group relative" title="Export CSV">
                            <FileSpreadsheet className="w-5 h-5 group-hover:text-emerald-600 transition-colors" />
                        </button>
                        <button onClick={handleExportPDF} className="p-2 hover:bg-slate-100 text-slate-500 rounded-lg transition-colors group relative" title="Export PDF">
                            <FileText className="w-5 h-5 group-hover:text-red-500 transition-colors" />
                        </button>
                    </div>
                </div>

                <div className="flex gap-6">
                    {/* TABLE */}
                    <div className={`bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden ${selectedOrder ? 'flex-1' : 'w-full'} transition-all`}>
                        {trackingLoading ? (
                            <div className="py-20 text-center"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto"></div></div>
                        ) : (
                        <table className="w-full text-left border-collapse">
                            <thead>
                                <tr className="bg-slate-50/50 border-b border-slate-100">
                                    <th onClick={() => handleSort('reference')} className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center gap-2">Réf. <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('client_name')} className="py-4 px-4 text-xs font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center gap-2">Client <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('material')} className="py-4 px-4 text-xs font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center gap-2">Matériau <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('station_display')} className="py-4 px-4 text-xs font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center gap-2">Station <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('progress')} className="py-4 px-4 text-xs font-black text-slate-400 uppercase tracking-widest cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center gap-2">Progression <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('quantity')} className="py-4 px-4 text-xs font-black text-slate-400 uppercase tracking-widest text-center cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center justify-center gap-2">Qté <ArrowUpDown className="w-3 h-3" /></div>
                                    </th>
                                    <th onClick={() => handleSort('status')} className="py-4 px-6 text-xs font-black text-slate-400 uppercase tracking-widest text-right cursor-pointer hover:bg-slate-100/50 transition-colors">
                                        <div className="flex items-center justify-end gap-2"><ArrowUpDown className="w-3 h-3" /> Statut</div>
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50">
                                {currentData.map((order) => {
                                    const st = STATUS_MAP[order.status] || STATUS_MAP['NEW'];
                                    return (
                                    <tr key={order.id} onClick={() => setSelectedOrder(selectedOrder?.id === order.id ? null : order)} className={`group hover:bg-blue-50/30 transition-colors cursor-pointer ${selectedOrder?.id === order.id ? 'bg-blue-50/50' : ''}`}>
                                        <td className="py-4 px-6">
                                            <div className="flex items-center gap-3">
                                                <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center text-slate-400 group-hover:bg-blue-100 group-hover:text-blue-600 transition-colors">
                                                    <Box className="w-4 h-4" />
                                                </div>
                                                <span className="font-bold text-slate-700 text-sm">{order.reference}</span>
                                            </div>
                                        </td>
                                        <td className="py-4 px-4">
                                            <p className="font-semibold text-slate-600 truncate max-w-[130px] text-sm">{order.client_name || "—"}</p>
                                        </td>
                                        <td className="py-4 px-4">
                                            <span className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-wider ${order.material === 'PVC' ? 'bg-indigo-50 text-indigo-600' : 'bg-amber-50 text-amber-700'}`}>
                                                {order.material}
                                            </span>
                                        </td>
                                        <td className="py-4 px-4">
                                            {order.station_display ? (
                                                <span className="text-xs font-bold text-slate-500 bg-slate-100 px-2 py-1 rounded-lg">{order.station_display}</span>
                                            ) : (
                                                <span className="text-xs text-slate-300">—</span>
                                            )}
                                        </td>
                                        <td className="py-4 px-4">
                                            <div className="flex items-center gap-2">
                                                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden max-w-[80px]">
                                                    <div className={`h-full rounded-full transition-all ${order.progress >= 100 ? 'bg-emerald-500' : order.progress > 0 ? 'bg-blue-500' : 'bg-slate-200'}`} style={{width: `${order.progress}%`}}></div>
                                                </div>
                                                <span className="text-xs font-bold text-slate-500">{order.progress}%</span>
                                            </div>
                                        </td>
                                        <td className="py-4 px-4 text-center font-bold text-slate-700 text-sm">{order.quantity}</td>
                                        <td className="py-4 px-6 text-right">
                                            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold ring-1 ${st.color}`}>
                                                <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`}></span>
                                                {st.label}
                                            </span>
                                        </td>
                                    </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        )}

                        {/* Pagination */}
                        {!trackingLoading && filtered.length > 0 && (
                            <div className="p-4 border-t border-slate-100 flex items-center justify-between bg-slate-50/30">
                                <span className="text-xs font-medium text-slate-500">
                                    Affichage de {(currentPage - 1) * ITEMS_PER_PAGE + 1} à {Math.min(currentPage * ITEMS_PER_PAGE, filtered.length)} sur {filtered.length} commandes
                                </span>
                                <div className="flex items-center gap-1">
                                    <button 
                                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                        disabled={currentPage === 1}
                                        className="p-1.5 rounded-lg text-slate-500 hover:bg-white hover:shadow-sm disabled:opacity-50 disabled:hover:bg-transparent disabled:cursor-not-allowed transition-all"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                    </button>
                                    <span className="px-3 py-1 text-xs font-bold text-slate-700 bg-white rounded-lg shadow-sm border border-slate-200">
                                        Page {currentPage} / {totalPages}
                                    </span>
                                    <button 
                                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                        disabled={currentPage === totalPages}
                                        className="p-1.5 rounded-lg text-slate-500 hover:bg-white hover:shadow-sm disabled:opacity-50 disabled:hover:bg-transparent disabled:cursor-not-allowed transition-all"
                                    >
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        )}

                        {!trackingLoading && filtered.length === 0 && (
                            <div className="py-20 text-center space-y-4">
                                <Search className="w-12 h-12 text-slate-200 mx-auto" />
                                <p className="text-slate-400 font-medium italic">Aucune commande ne correspond à votre recherche.</p>
                            </div>
                        )}
                    </div>

                    {/* DETAIL PANEL */}
                    {selectedOrder && (
                        <div className="w-96 bg-white rounded-3xl border border-slate-200 shadow-sm p-6 space-y-6 shrink-0 animate-fade-in">
                            <div className="flex items-center justify-between">
                                <h3 className="font-black text-lg text-slate-800">{selectedOrder.reference}</h3>
                                <button onClick={() => setSelectedOrder(null)} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors">✕</button>
                            </div>

                            <div className="space-y-3">
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Client</span><span className="font-semibold text-slate-700">{selectedOrder.client_name || "—"}</span></div>
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Dimensions</span><span className="font-semibold text-slate-700">{selectedOrder.width} × {selectedOrder.height} mm</span></div>
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Matériau</span><span className="font-semibold text-slate-700">{selectedOrder.material}</span></div>
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Couleur</span><span className="font-semibold text-slate-700">{selectedOrder.color || "—"}</span></div>
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Système</span><span className="font-semibold text-slate-700">{selectedOrder.system_type || "—"}</span></div>
                                <div className="flex justify-between text-sm"><span className="text-slate-400 font-bold">Opérateur</span><span className="font-semibold text-slate-700">{selectedOrder.assigned_to || "Non assigné"}</span></div>
                            </div>

                            {/* Progress */}
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-black text-slate-400 uppercase tracking-widest">Progression</span>
                                    <span className="text-sm font-black text-blue-600">{selectedOrder.progress}%</span>
                                </div>
                                <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                                    <div className={`h-full rounded-full transition-all duration-500 ${selectedOrder.progress >= 100 ? 'bg-emerald-500' : 'bg-blue-500'}`} style={{width: `${selectedOrder.progress}%`}}></div>
                                </div>
                            </div>

                            {/* Steps Timeline */}
                            <div>
                                <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-3">Étapes de fabrication</p>
                                <div className="space-y-0">
                                    {selectedOrder.steps && selectedOrder.steps.map((step, i) => {
                                        const stepColor = step.status === 'DONE' ? 'bg-emerald-500' : step.status === 'IN_PROGRESS' ? 'bg-blue-500 animate-pulse' : step.status === 'ISSUE' ? 'bg-red-500' : 'bg-slate-300';
                                        const lineColor = step.status === 'DONE' ? 'bg-emerald-300' : 'bg-slate-200';
                                        return (
                                            <div key={i} className="flex items-start gap-3">
                                                <div className="flex flex-col items-center">
                                                    <div className={`w-3 h-3 rounded-full ${stepColor} shrink-0 mt-0.5`}></div>
                                                    {i < selectedOrder.steps.length - 1 && <div className={`w-0.5 h-8 ${lineColor}`}></div>}
                                                </div>
                                                <div className="pb-4">
                                                    <p className="text-sm font-bold text-slate-700">{step.station.replace(/_/g, ' ')}</p>
                                                    <p className="text-xs text-slate-400 font-medium">{STATUS_MAP[step.status]?.label || step.status}</p>
                                                </div>
                                            </div>
                                        );
                                    })}
                                    {(!selectedOrder.steps || selectedOrder.steps.length === 0) && (
                                        <p className="text-sm text-slate-400 italic">Aucune étape planifiée</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    function renderAtelierAnalyticsView() {
        if (analyticsLoading || !workshopAnalytics) {
            return <div className="py-20 text-center"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto"></div></div>;
        }

        const analytics = workshopAnalytics;

        return (
            <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h2 className="text-2xl font-bold text-slate-900">Analyse & Performance Atelier</h2>
                        <p className="text-slate-500">Métriques de production sur les 7 derniers jours.</p>
                    </div>
                </div>

                {/* KPIs */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Lead Time Moyen (Global)</p>
                        <p className="text-3xl font-black text-slate-800">{analytics.global.avg_lead_time_min} <span className="text-lg text-slate-400">min</span></p>
                    </div>
                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Tâches Réalisées</p>
                        <p className="text-3xl font-black text-blue-600">{analytics.global.tasks_completed_7d}</p>
                    </div>
                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Taux de Défauts</p>
                        <p className="text-3xl font-black text-amber-600">{analytics.global.defect_rate_pct}%</p>
                    </div>
                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Incidents & Aléas (7J)</p>
                        <p className="text-3xl font-black text-red-600">{analytics.global.issues_7d}</p>
                    </div>
                </div>

                {/* CHARTS */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <h3 className="text-lg font-bold text-slate-900 mb-6 flex items-center gap-2">
                            <Clock className="w-5 h-5 text-blue-500" /> Temps Moyen par Station (Min)
                        </h3>
                        <div className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={analytics.station_avg_time} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E2E8F0" />
                                    <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} />
                                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} width={120} />
                                    <Tooltip cursor={{fill: '#f1f5f9'}} contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }} />
                                    <Bar dataKey="avg_time" fill="#3b82f6" radius={[0, 4, 4, 0]} barSize={20} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                        <h3 className="text-lg font-bold text-slate-900 mb-6 flex items-center gap-2">
                            <Users className="w-5 h-5 text-emerald-500" /> Top Productivité (Opérateurs)
                        </h3>
                        <div className="h-[300px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={analytics.operator_productivity} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E2E8F0" />
                                    <XAxis type="number" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} />
                                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12, fontWeight: 700 }} width={100} />
                                    <Tooltip cursor={{fill: '#f1f5f9'}} contentStyle={{ borderRadius: '16px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }} />
                                    <Bar dataKey="tasks" fill="#10b981" radius={[0, 4, 4, 0]} barSize={20} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
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

function StationLiveCard({ name, displayName, isSelected, onSelect }) {
    const { data: queueData = [], isLoading } = useQuery({
        queryKey: ['station-queue', name],
        queryFn: async () => {
            const res = await api.get(`/v2/planning/${name}`);
            return res.data;
        },
        refetchInterval: 5000,
    });

    const pendingTasks = queueData.filter(item => item.status === 'PENDING');
    const inProgressTasks = queueData.filter(item => item.status === 'IN_PROGRESS');
    
    const stats = {
        queue: pendingTasks.length,
        in_progress: inProgressTasks.length
    };

    const hasIssue = stats.queue > 8 || queueData.some(item => item.status === 'ISSUE');
    const activeTask = inProgressTasks[0]; // Take the first active task if any

    return (
        <div 
            onClick={() => onSelect(name)}
            className={`bg-white p-6 rounded-3xl border shadow-sm transition-all cursor-pointer group flex flex-col h-full
                ${isSelected ? 'border-blue-500 ring-4 ring-blue-50' : 'border-slate-200 hover:border-blue-300'}`}
        >
            <div className="flex items-center justify-between mb-6 shrink-0">
                <h4 className="font-black text-slate-800 tracking-tight">{displayName || name.replace('_', ' ')}</h4>
                <div className={`w-3 h-3 rounded-full ${hasIssue ? 'bg-red-500 animate-pulse' : 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]'}`} />
            </div>

            {/* Active Task Highlight */}
            {activeTask ? (
                <div className="mb-6 bg-blue-50/50 rounded-2xl p-4 border border-blue-100 flex-1">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-black text-blue-500 uppercase tracking-widest flex items-center gap-1">
                            <Activity className="w-3 h-3" /> Production en cours
                        </span>
                    </div>
                    <p className="text-lg font-black text-slate-800 mb-1">{activeTask.order_reference}</p>
                    <p className="text-sm font-semibold text-slate-600 truncate">Opérateur : <span className="text-blue-700">{activeTask.operator?.name || 'Inconnu'}</span></p>
                </div>
            ) : (
                <div className="mb-6 bg-slate-50 rounded-2xl p-4 border border-slate-100 flex-1 flex flex-col items-center justify-center text-center">
                    <Clock className="w-6 h-6 text-slate-300 mb-2" />
                    <p className="text-sm font-bold text-slate-400">Station en attente</p>
                    <p className="text-xs font-medium text-slate-400">Aucune production active</p>
                </div>
            )}

            <div className="grid grid-cols-2 gap-4 shrink-0">
                <div className="bg-slate-50 p-4 rounded-2xl">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">En attente</p>
                    <p className="text-2xl font-black text-slate-800">{stats.queue}</p>
                </div>
                <div className="bg-blue-50 p-4 rounded-2xl">
                    <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">En cours</p>
                    <p className="text-2xl font-black text-blue-600">{stats.in_progress}</p>
                </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-50 flex items-center justify-between shrink-0">
                <span className={`text-xs font-black flex items-center gap-1 transition-colors ${isSelected ? 'text-blue-600' : 'text-slate-400 group-hover:text-blue-500'}`}>
                    Voir la file détaillée
                    <ChevronRight className={`w-4 h-4 transition-transform ${isSelected ? 'translate-x-1' : 'group-hover:translate-x-1'}`} />
                </span>
                {hasIssue && <span className="text-[10px] font-black text-red-500 uppercase tracking-widest bg-red-50 px-2 py-1 rounded-md">Surcharge</span>}
            </div>
        </div>
    );
}

function StationDetailPanel({ stationCode, onClose }) {
    const { data: queueData = [], refetch } = useQuery({
        queryKey: ['station-queue', stationCode],
        queryFn: async () => {
            const res = await api.get(`/v2/planning/${stationCode}`);
            return res.data;
        },
        refetchInterval: 5000,
    });

    const [draggedItem, setDraggedItem] = useState(null);

    const handleDragStart = (e, task) => {
        setDraggedItem(task);
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(() => {
            e.target.style.opacity = '0.5';
        }, 0);
    };

    const handleDragEnd = (e) => {
        e.target.style.opacity = '1';
        setDraggedItem(null);
    };

    const handleDragOver = (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    };

    const handleDrop = async (e, targetTask) => {
        e.preventDefault();
        if (!draggedItem || draggedItem.id === targetTask.id) return;
        
        const newPriority = targetTask.priority + 1;
        try {
            await api.put(`/v2/planning/${draggedItem.id}`, { priority: newPriority });
            refetch();
        } catch(err) {
            console.error("Erreur réorganisation", err);
        }
    };

    const pending = queueData.filter(item => item.status === 'PENDING');
    const inProgress = queueData.filter(item => item.status === 'IN_PROGRESS');

    return (
        <div className="w-96 bg-white rounded-3xl border border-slate-200 shadow-sm p-6 shrink-0 animate-fade-in flex flex-col h-[calc(100vh-200px)] sticky top-8">
            <div className="flex items-center justify-between mb-6 shrink-0">
                <h3 className="font-black text-xl text-slate-800 tracking-tight">{stationCode.replace('_', ' ')}</h3>
                <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors">✕</button>
            </div>

            <div className="flex items-center justify-between mb-4 shrink-0 bg-slate-50 p-4 rounded-2xl border border-slate-100">
                <div className="text-center">
                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">En attente</p>
                    <p className="text-xl font-black text-slate-800">{pending.length}</p>
                </div>
                <div className="w-px h-8 bg-slate-200"></div>
                <div className="text-center">
                    <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">En cours</p>
                    <p className="text-xl font-black text-blue-600">{inProgress.length}</p>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto pr-2 space-y-3">
                <h4 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-3 sticky top-0 bg-white py-2 z-10">File d'attente détaillée (Glisser pour prioriser)</h4>
                {queueData.length === 0 ? (
                    <p className="text-slate-400 text-sm italic text-center py-8">Aucun dossier planifié</p>
                ) : (
                    queueData.sort((a, b) => {
                        if (a.status === 'IN_PROGRESS' && b.status !== 'IN_PROGRESS') return -1;
                        if (b.status === 'IN_PROGRESS' && a.status !== 'IN_PROGRESS') return 1;
                        return b.priority - a.priority;
                    }).map((task) => (
                        <div 
                            key={task.id} 
                            draggable={task.status === 'PENDING'}
                            onDragStart={(e) => handleDragStart(e, task)}
                            onDragEnd={handleDragEnd}
                            onDragOver={handleDragOver}
                            onDrop={(e) => handleDrop(e, task)}
                            className={`p-4 rounded-2xl border ${task.status === 'IN_PROGRESS' ? 'bg-blue-50/50 border-blue-200 shadow-sm' : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-md cursor-grab active:cursor-grabbing'} transition-all relative group`}
                        >
                            <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    {task.status === 'IN_PROGRESS' ? (
                                        <span className="relative flex h-2 w-2">
                                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                                            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                                        </span>
                                    ) : (
                                        <div className="w-2 h-2 rounded-full bg-slate-300"></div>
                                    )}
                                    <span className="font-bold text-slate-800">{task.order_reference}</span>
                                </div>
                                <span className={`text-[10px] font-black px-2 py-0.5 rounded-lg uppercase tracking-wider ${task.status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-500'}`}>
                                    {task.status === 'IN_PROGRESS' ? 'Actif' : 'Attente'}
                                </span>
                            </div>
                            <div className="text-xs font-medium text-slate-500 flex justify-between items-center mt-2">
                                <div className="flex items-center gap-1">
                                    <span>Assigné : </span>
                                    <select 
                                        className="font-bold text-slate-700 bg-transparent outline-none hover:bg-slate-100 rounded px-1 py-0.5 cursor-pointer"
                                        value={task.assigned_to || ""}
                                        onChange={async (e) => {
                                            await api.put(`/v2/planning/${task.id}`, { assigned_to: e.target.value || null });
                                            refetch();
                                        }}
                                    >
                                        <option value="">Automatique</option>
                                        <option value="john">John (Opérateur)</option>
                                        <option value="admin">Admin</option>
                                    </select>
                                </div>
                                <span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600 font-bold">Prio: {task.priority}</span>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
