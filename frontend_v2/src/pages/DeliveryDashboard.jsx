import React, { useState, useEffect } from 'react';
import { Truck, MapPin, Package, Plus, Calendar, User, Search, CheckCircle, FileText } from 'lucide-react';
import api, { API_BASE_URL } from '../services/api';

export default function DeliveryDashboard() {
    const [routes, setRoutes] = useState([]);
    const [readyNotes, setReadyNotes] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    const [showNewRouteModal, setShowNewRouteModal] = useState(false);
    const [newRouteData, setNewRouteData] = useState({
        driver_name: "", vehicle: "Camion 1 (Iveco)", planned_date: "", note_ids: []
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const resRoutes = await api.get('/v2/logistics/routes');
            setRoutes(resRoutes.data);
            
            const resNotes = await api.get('/v2/logistics/notes/ready');
            setReadyNotes(resNotes.data);
        } catch (error) {
            console.error("Error fetching logistics data", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleCreateRoute = async () => {
        if(!newRouteData.driver_name || !newRouteData.planned_date) return alert("Veuillez remplir le chauffeur et la date.");
        
        try {
            await api.post('/v2/logistics/routes', newRouteData);
            setShowNewRouteModal(false);
            setNewRouteData({ driver_name: "", vehicle: "Camion 1 (Iveco)", planned_date: "", note_ids: [] });
            fetchData();
        } catch (error) {
            alert(error.response?.data?.detail || "Erreur de création de tournée");
        }
    };

    const handleStartRoute = async (routeId) => {
        if(!window.confirm("Démarrer cette tournée ? Le statut passera à 'En Transit'.")) return;
        try {
            await api.post(`/v2/logistics/routes/${routeId}/start`);
            fetchData();
        } catch (error) {
            console.error(error);
        }
    };

    return (
        <div className="space-y-6 max-w-7xl mx-auto animate-fade-in pb-12">
            
            {/* KPI ROW */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Prêt au Quai</p>
                        <h2 className="text-3xl font-black text-slate-800">{readyNotes.length} <span className="text-lg font-bold text-slate-500">BLs</span></h2>
                    </div>
                    <div className="w-12 h-12 bg-amber-50 text-amber-500 rounded-full flex items-center justify-center">
                        <Package className="w-6 h-6" />
                    </div>
                </div>

                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Tournées Prévues</p>
                        <h2 className="text-3xl font-black text-slate-800">{routes.filter(r => r.status === "PLANNED").length}</h2>
                    </div>
                    <div className="w-12 h-12 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center">
                        <Calendar className="w-6 h-6" />
                    </div>
                </div>
                
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">En Transit</p>
                        <h2 className="text-3xl font-black text-slate-800">{routes.filter(r => r.status === "IN_TRANSIT").length}</h2>
                    </div>
                    <div className="w-12 h-12 bg-emerald-50 text-emerald-500 rounded-full flex items-center justify-center">
                        <Truck className="w-6 h-6" />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* COL 1 : Quai d'expédition (Ready Notes) */}
                <div className="lg:col-span-1 space-y-4">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-black text-slate-800 text-lg flex items-center gap-2">
                            <Package className="w-5 h-5 text-slate-400"/> Quai de Chargement
                        </h3>
                    </div>
                    <div className="bg-slate-200/50 p-4 rounded-2xl border border-slate-200 min-h-[400px]">
                        {readyNotes.length === 0 && (
                            <p className="text-center text-slate-400 font-bold mt-10">Aucune marchandise en attente.</p>
                        )}
                        {readyNotes.map(note => (
                            <div key={note.id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 mb-3 hover:border-blue-300 transition-colors cursor-pointer group">
                                <div className="flex justify-between items-start mb-2">
                                    <span className="font-mono text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded">{note.reference}</span>
                                    <span className="text-[10px] font-black uppercase text-slate-400">PROD TERMINÉE</span>
                                </div>
                                <p className="font-black text-slate-800 mb-1">{note.client_name}</p>
                                <p className="text-xs text-slate-500 flex items-center gap-1">
                                    <MapPin className="w-3 h-3"/> {note.delivery_address || "Adresse non spécifiée"}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* COL 2 : Tournées / Dispatch */}
                <div className="lg:col-span-2 space-y-4">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="font-black text-slate-800 text-lg flex items-center gap-2">
                            <Truck className="w-5 h-5 text-slate-400"/> Tournées (Routes)
                        </h3>
                        <button 
                            onClick={() => setShowNewRouteModal(true)}
                            className="bg-slate-900 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-md hover:bg-blue-600 transition-colors flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4"/> Nouvelle Tournée
                        </button>
                    </div>

                    <div className="space-y-4">
                        {routes.length === 0 && !isLoading && (
                            <div className="bg-white border border-dashed border-slate-300 rounded-2xl p-12 text-center text-slate-400">
                                <Truck className="w-12 h-12 mx-auto mb-4 opacity-20" />
                                <p className="font-bold">Aucune tournée planifiée.</p>
                            </div>
                        )}
                        {routes.map(route => (
                            <div key={route.id} className={`bg-white rounded-2xl border ${route.status === 'IN_TRANSIT' ? 'border-blue-500 ring-4 ring-blue-50' : 'border-slate-200'} shadow-sm overflow-hidden`}>
                                <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                                    <div>
                                        <div className="flex items-center gap-3 mb-1">
                                            <h4 className="font-black text-slate-800 text-lg">{route.reference}</h4>
                                            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${
                                                route.status === 'PLANNED' ? 'bg-slate-200 text-slate-600' : 
                                                route.status === 'IN_TRANSIT' ? 'bg-blue-500 text-white' : 'bg-emerald-500 text-white'
                                            }`}>
                                                {route.status === 'PLANNED' ? 'Planifiée' : route.status === 'IN_TRANSIT' ? 'En Route' : 'Terminée'}
                                            </span>
                                        </div>
                                        <p className="text-sm font-bold text-slate-500 flex items-center gap-4">
                                            <span className="flex items-center gap-1"><Calendar className="w-4 h-4"/> {new Date(route.planned_date).toLocaleDateString()}</span>
                                            <span className="flex items-center gap-1"><User className="w-4 h-4"/> {route.driver_name}</span>
                                            <span className="flex items-center gap-1"><Truck className="w-4 h-4"/> {route.vehicle}</span>
                                        </p>
                                    </div>
                                    <div className="flex gap-2">
                                        <button className="p-2 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg text-slate-600 transition-colors" title="Imprimer le Bordereau">
                                            <FileText className="w-5 h-5"/>
                                        </button>
                                        {route.status === "PLANNED" && (
                                            <button 
                                                onClick={() => handleStartRoute(route.id)}
                                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg shadow-sm transition-colors"
                                            >
                                                Démarrer
                                            </button>
                                        )}
                                    </div>
                                </div>
                                <div className="p-5 bg-white">
                                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Chargement ({route.notes?.length || 0} BLs)</p>
                                    <div className="space-y-2">
                                        {route.notes?.map(note => (
                                            <div key={note.id} className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                                                <div className="flex items-center gap-3">
                                                    <span className="font-mono text-xs font-bold text-slate-600">{note.reference}</span>
                                                    <span className="font-black text-slate-800 text-sm">{note.client_name}</span>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    <span className="text-xs text-slate-500 truncate max-w-[200px]">{note.delivery_address}</span>
                                                    {note.status === "DELIVERED" ? (
                                                        <span className="flex items-center gap-2">
                                                            {note.signature_path && (
                                                                <a
                                                                    href={`${API_BASE_URL}/${note.signature_path}`}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className="text-[10px] font-black uppercase text-emerald-600 hover:text-emerald-800 underline"
                                                                    title="Voir la signature client"
                                                                >
                                                                    Signature
                                                                </a>
                                                            )}
                                                            <CheckCircle className="w-5 h-5 text-emerald-500" />
                                                        </span>
                                                    ) : (
                                                        <span className="w-2 h-2 rounded-full bg-slate-300"></span>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* NEW ROUTE MODAL */}
            {showNewRouteModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-[2rem] max-w-xl w-full p-8 shadow-2xl animate-fade-in-up">
                        <h3 className="text-2xl font-black text-slate-800 mb-6">Planifier une Tournée</h3>
                        
                        <div className="space-y-4 mb-8">
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Chauffeur / Équipe</label>
                                    <input 
                                        type="text" 
                                        placeholder="Ex: Jean & Marc"
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-800 outline-none focus:border-blue-500"
                                        value={newRouteData.driver_name}
                                        onChange={(e) => setNewRouteData({...newRouteData, driver_name: e.target.value})}
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Véhicule</label>
                                    <select 
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700 outline-none focus:border-blue-500"
                                        value={newRouteData.vehicle}
                                        onChange={(e) => setNewRouteData({...newRouteData, vehicle: e.target.value})}
                                    >
                                        <option value="Camion 1 (Iveco)">Camion 1 (Iveco)</option>
                                        <option value="Camion 2 (Renault)">Camion 2 (Renault)</option>
                                        <option value="Fourgon (Peugeot)">Fourgon (Peugeot)</option>
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Date de livraison prévue</label>
                                <input 
                                    type="date" 
                                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 outline-none focus:border-blue-500"
                                    value={newRouteData.planned_date}
                                    onChange={(e) => setNewRouteData({...newRouteData, planned_date: e.target.value})}
                                />
                            </div>

                            <div className="pt-4">
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Sélectionner les BLs à charger</label>
                                <div className="max-h-48 overflow-y-auto space-y-2 border border-slate-200 p-2 rounded-xl bg-slate-50">
                                    {readyNotes.map(note => (
                                        <label key={note.id} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-slate-100 cursor-pointer hover:border-blue-300">
                                            <input 
                                                type="checkbox" 
                                                className="w-4 h-4 text-blue-600 rounded border-slate-300"
                                                checked={newRouteData.note_ids.includes(note.id)}
                                                onChange={(e) => {
                                                    const ids = e.target.checked 
                                                        ? [...newRouteData.note_ids, note.id]
                                                        : newRouteData.note_ids.filter(id => id !== note.id);
                                                    setNewRouteData({...newRouteData, note_ids: ids});
                                                }}
                                            />
                                            <div className="flex-1">
                                                <span className="font-black text-slate-800">{note.client_name}</span>
                                                <span className="text-xs text-slate-500 ml-2">({note.reference})</span>
                                            </div>
                                        </label>
                                    ))}
                                    {readyNotes.length === 0 && <p className="text-sm text-slate-400 text-center p-4">Aucun BL prêt.</p>}
                                </div>
                            </div>
                        </div>

                        <div className="flex gap-4">
                            <button 
                                onClick={() => setShowNewRouteModal(false)}
                                className="flex-1 py-4 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl transition-colors"
                            >
                                Annuler
                            </button>
                            <button 
                                onClick={handleCreateRoute}
                                className="flex-1 py-4 bg-slate-900 hover:bg-blue-600 text-white font-bold rounded-xl shadow-lg transition-colors"
                            >
                                Créer la Tournée
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
