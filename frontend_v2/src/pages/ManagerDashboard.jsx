import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertTriangle, Clock, Activity, LogOut, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';
import StationManager from '../components/StationManager';

export default function ManagerDashboard() {
    const { logout } = useAuth();
    const [stats, setStats] = useState({ total: 0, avg_time: 0, delay_rate: 0, active: 0 });
    const [chartData, setChartData] = useState([]);
    const [recentOrders, setRecentOrders] = useState([]);
    const [activeTab, setActiveTab] = useState('analytics'); // 'analytics' or 'config'

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
        const interval = setInterval(fetchData, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="min-h-screen bg-slate-50 p-8 font-sans">
            <div className="max-w-7xl mx-auto">
                <header className="mb-10 flex items-center justify-between">
                    <div>
                        <h1 className="text-4xl font-bold text-slate-900 tracking-tight">Tableau de Bord Atelier</h1>
                        <p className="text-slate-500 mt-2">Vue d'ensemble de la production en temps réel</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <Link
                            to="/upload"
                            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-blue-500/20 active:scale-95"
                        >
                            <Upload className="w-5 h-5" />
                            Upload Commande
                        </Link>
                        <div className="text-right">
                            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-100 text-green-700 text-xs font-bold uppercase tracking-widest">
                                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                                Live
                            </span>
                            <button onClick={logout} className="ml-4 p-2 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-full transition-colors" title="Déconnexion">
                                <LogOut className="w-5 h-5" />
                            </button>
                        </div>
                    </div>
                </header>

                {/* TAB SWITCHER */}
                <div className="flex gap-4 mb-8">
                    <button
                        onClick={() => setActiveTab('analytics')}
                        className={`px-6 py-2 rounded-full font-bold transition-all ${activeTab === 'analytics' ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-white text-slate-400 hover:text-slate-600 border border-slate-100'}`}
                    >
                        Analyse Production
                    </button>
                    <button
                        onClick={() => setActiveTab('config')}
                        className={`px-6 py-2 rounded-full font-bold transition-all ${activeTab === 'config' ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' : 'bg-white text-slate-400 hover:text-slate-600 border border-slate-100'}`}
                    >
                        Configuration Atelier
                    </button>
                </div>

                {activeTab === 'analytics' ? (
                    <>
                        {/* KPI GRID */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
                            <KpiCard icon={Activity} title="Production Totale" value={stats.total} color="blue" delay={0} />
                            <KpiCard icon={AlertTriangle} title="Défauts / Alertes" value={stats.defects} color={stats.defects > 0 ? "red" : "green"} delay={200} />
                            <KpiCard icon={TrendingUp} title="En Cours" value={stats.active} color="indigo" delay={300} />
                            <KpiCard icon={Clock} title="Temps Moyen" value={stats.avg_time} color="emerald" delay={100} />
                        </div>

                        {/* CHARTS */}
                        <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-100 h-[500px] animate-fade-in-up" style={{ animationDelay: '400ms' }}>
                            <h2 className="text-xl font-bold text-slate-800 mb-6 flex items-center gap-2">
                                <div className="w-1 h-6 bg-blue-500 rounded-full"></div>
                                Production Horaire
                            </h2>
                            <ResponsiveContainer width="100%" height="90%">
                                <BarChart data={chartData}>
                                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                    <XAxis
                                        dataKey="name"
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#64748b', fontSize: 12 }}
                                        dy={10}
                                    />
                                    <YAxis
                                        axisLine={false}
                                        tickLine={false}
                                        tick={{ fill: '#64748b', fontSize: 12 }}
                                        dx={-10}
                                    />
                                    <Tooltip
                                        cursor={{ fill: '#f8fafc' }}
                                        contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)' }}
                                    />
                                    <Bar
                                        dataKey="count"
                                        fill="#3b82f6"
                                        radius={[6, 6, 0, 0]}
                                        barSize={40}
                                    />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>

                        {/* RECENT ORDERS TABLE */}
                        <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-100 mt-10 animate-fade-in-up" style={{ animationDelay: '500ms' }}>
                            <h2 className="text-xl font-bold text-slate-800 mb-6 flex items-center gap-2">
                                <div className="w-1 h-6 bg-emerald-500 rounded-full"></div>
                                Dernières Ingestions (Flux Réel)
                            </h2>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                    <thead>
                                        <tr className="text-slate-400 text-xs font-bold uppercase tracking-wider border-b border-slate-50">
                                            <th className="pb-4 px-2">Référence</th>
                                            <th className="pb-4 px-2">Client</th>
                                            <th className="pb-4 px-2">Dimensions</th>
                                            <th className="pb-4 px-2">Couleur</th>
                                            <th className="pb-4 px-2 text-center">Qté</th>
                                            <th className="pb-4 px-2 text-right">Statut</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {recentOrders.map((order) => (
                                            <tr key={order.id} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors group">
                                                <td className="py-4 px-2 font-bold text-slate-700">{order.reference}</td>
                                                <td className="py-4 px-2 text-slate-500 font-medium truncate max-w-[120px]" title={order.client_name}>{order.client_name || "-"}</td>
                                                <td className="py-4 px-2 text-slate-500">{order.width} x {order.height} mm</td>
                                                <td className="py-4 px-2">
                                                    <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-1 rounded border border-slate-200 uppercase">
                                                        {order.color || "Standard"}
                                                    </span>
                                                </td>
                                                <td className="py-4 px-2 text-center font-bold text-blue-600">{order.quantity}</td>
                                                <td className="py-4 px-2 text-right">
                                                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold">
                                                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                                                        Ingéré
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                        {recentOrders.length === 0 && (
                                            <tr>
                                                <td colSpan="6" className="py-12 text-center text-slate-400 italic">Aucune commande récemment ingérée</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </>
                ) : (
                    <StationManager />
                )}
            </div>
        </div>
    );
}

function KpiCard({ icon: Icon, title, value, color, delay }) {
    const styles = {
        blue: "bg-blue-50 text-blue-600 ring-blue-100",
        emerald: "bg-emerald-50 text-emerald-600 ring-emerald-100",
        red: "bg-red-50 text-red-600 ring-red-100",
        indigo: "bg-indigo-50 text-indigo-600 ring-indigo-100"
    };

    return (
        <div
            className={`bg-white p-6 rounded-2xl border border-slate-100 shadow-sm flex items-center justify-between group hover:shadow-lg hover:-translate-y-1 transition-all duration-300 animate-fade-in-up`}
            style={{ animationDelay: `${delay}ms` }}
        >
            <div>
                <p className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">{title}</p>
                <p className="text-4xl font-black text-slate-800 tracking-tight group-hover:scale-105 transition-transform origin-left">{value}</p>
            </div>
            <div className={`p-4 rounded-xl ${styles[color]} ring-1 group-hover:rotate-12 transition-transform duration-300`}>
                <Icon className="w-8 h-8" strokeWidth={2.5} />
            </div>
        </div>
    );
}
