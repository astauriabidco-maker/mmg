import React, { useState, useEffect } from 'react';
import { Plus, Trash2, ArrowUp, ArrowDown, Save, RefreshCw } from 'lucide-react';
import api from '../services/api';

export default function StationManager() {
    const [stations, setStations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newStation, setNewStation] = useState({ code: '', display_name: '', material: 'PVC', order_index: 0 });

    const fetchStations = async () => {
        setLoading(true);
        try {
            const res = await api.get('/v2/config/stations');
            setStations(res.data);
        } catch (err) {
            console.error("Error fetching stations", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStations();
    }, []);

    const handleCreate = async () => {
        if (!newStation.code || !newStation.display_name) return alert("Remplissez tous les champs");
        try {
            await api.post('/v2/config/stations', newStation);
            setNewStation({ code: '', display_name: '', material: 'PVC', order_index: 0 });
            fetchStations();
        } catch (err) {
            alert(err.response?.data?.detail || "Erreur de création");
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Supprimer ce poste ?")) return;
        try {
            await api.delete(`/v2/config/stations/${id}`);
            fetchStations();
        } catch (err) {
            console.error(err);
        }
    };

    const handleMove = async (id, direction) => {
        const materialStations = stations.filter(s => s.material === stations.find(st => st.id === id).material);
        const index = materialStations.findIndex(s => s.id === id);

        if (direction === 'up' && index === 0) return;
        if (direction === 'down' && index === materialStations.length - 1) return;

        const otherIndex = direction === 'up' ? index - 1 : index + 1;
        const otherStation = materialStations[otherIndex];
        const currentStation = materialStations[index];

        const orderMap = {
            [currentStation.id]: otherStation.order_index,
            [otherStation.id]: currentStation.order_index
        };

        try {
            await api.post('/v2/config/stations/reorder', orderMap);
            fetchStations();
        } catch (err) {
            console.error(err);
        }
    };

    const renderMaterialGroup = (material) => (
        <div className="flex-1 min-w-[300px] bg-slate-50/50 p-6 rounded-2xl border border-slate-100">
            <h3 className="text-xl font-bold text-slate-800 mb-6 flex items-center justify-between">
                Gamme {material}
                <span className="text-xs font-medium bg-blue-100 text-blue-600 px-2 py-1 rounded-full uppercase tracking-wider">
                    {stations.filter(s => s.material === material).length} Postes
                </span>
            </h3>
            <div className="space-y-3">
                {stations.filter(s => s.material === material).map((s, i, arr) => (
                    <div key={s.id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-100 flex items-center justify-between group hover:border-blue-200 transition-all">
                        <div className="flex flex-col">
                            <span className="font-bold text-slate-700">{s.display_name}</span>
                            <span className="text-[10px] text-slate-400 font-mono tracking-wider">{s.code}</span>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button onClick={() => handleMove(s.id, 'up')} disabled={i === 0} className="p-1.5 hover:bg-slate-100 rounded text-slate-400 hover:text-blue-500 disabled:opacity-20">
                                <ArrowUp className="w-4 h-4" />
                            </button>
                            <button onClick={() => handleMove(s.id, 'down')} disabled={i === arr.length - 1} className="p-1.5 hover:bg-slate-100 rounded text-slate-400 hover:text-blue-500 disabled:opacity-20">
                                <ArrowDown className="w-4 h-4" />
                            </button>
                            <button onClick={() => handleDelete(s.id)} className="p-1.5 hover:bg-red-50 rounded text-slate-400 hover:text-red-500 ml-2">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );

    return (
        <div className="mt-12 animate-fade-in-up" style={{ animationDelay: '600ms' }}>
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-2xl font-black text-slate-800 tracking-tight">Configuration des Postes</h2>
                    <p className="text-slate-400 text-sm mt-1">Personnalisez votre workflow de production par gamme.</p>
                </div>
                <button
                    onClick={fetchStations}
                    className="p-3 bg-white border border-slate-200 text-slate-400 hover:text-blue-500 hover:border-blue-200 rounded-xl transition-all shadow-sm"
                >
                    <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {/* CREATE FORM */}
            <div className="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm mb-10 flex flex-wrap gap-4 items-end">
                <div className="flex-1 min-w-[150px]">
                    <label className="block text-[10px] uppercase font-bold text-slate-400 mb-2">Code Technique</label>
                    <input
                        type="text"
                        placeholder="ex: PVC_FINITION"
                        className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 ring-blue-500/20 outline-none font-mono text-sm"
                        value={newStation.code}
                        onChange={e => setNewStation({ ...newStation, code: e.target.value })}
                    />
                </div>
                <div className="flex-1 min-w-[200px]">
                    <label className="block text-[10px] uppercase font-bold text-slate-400 mb-2">Nom Affiché</label>
                    <input
                        type="text"
                        placeholder="ex: Finition & Nettoyage"
                        className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 ring-blue-500/20 outline-none"
                        value={newStation.display_name}
                        onChange={e => setNewStation({ ...newStation, display_name: e.target.value })}
                    />
                </div>
                <div className="w-[120px]">
                    <label className="block text-[10px] uppercase font-bold text-slate-400 mb-2">Gamme</label>
                    <select
                        className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 ring-blue-500/20 outline-none font-bold text-slate-700"
                        value={newStation.material}
                        onChange={e => setNewStation({ ...newStation, material: e.target.value })}
                    >
                        <option value="PVC">PVC</option>
                        <option value="ALU">ALU</option>
                    </select>
                </div>
                <button
                    onClick={handleCreate}
                    className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl transition-all shadow-lg shadow-blue-500/20 active:scale-95 flex items-center gap-2"
                >
                    <Plus className="w-5 h-5" />
                    Ajouter
                </button>
            </div>

            {/* STATION LISTS */}
            <div className="flex flex-col lg:flex-row gap-8">
                {renderMaterialGroup('PVC')}
                {renderMaterialGroup('ALU')}
            </div>
        </div>
    );
}
