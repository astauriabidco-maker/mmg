import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Plus, Trash2, Settings, ListPlus } from 'lucide-react';

export default function ConfigDashboard() {
    const [configs, setConfigs] = useState([]);
    const [newCat, setNewCat] = useState('material');
    const [newVal, setNewVal] = useState('');

    const fetchData = async () => {
        try {
            const { data } = await api.get('/v2/config/app_configs');
            setConfigs(data);
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleAdd = async (e) => {
        e.preventDefault();
        if (!newVal.trim()) return;
        try {
            await api.post('/v2/config/app_configs', { category: newCat, value: newVal.toUpperCase() });
            setNewVal('');
            fetchData();
        } catch (e) {
            alert('Cannot add config');
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm("Supprimer ce référentiel ? Cela n'impactera pas les produits existants, mais l'ôtera des choix futurs.")) return;
        try {
            await api.delete(`/v2/config/app_configs/${id}`);
            fetchData();
        } catch (e) {
            alert('Error deleting');
        }
    };

    const grouped = configs.reduce((acc, curr) => {
        if (!acc[curr.category]) acc[curr.category] = [];
        acc[curr.category].push(curr);
        return acc;
    }, {});

    const renderTable = (catName, title) => (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[400px]">
            <div className="p-4 bg-slate-50 border-b border-slate-200">
                <h3 className="font-black text-lg text-slate-800 flex items-center gap-2">
                    <ListPlus className="w-5 h-5 text-blue-500" /> {title}
                </h3>
            </div>
            <div className="flex-1 overflow-auto p-4 space-y-2">
                {(grouped[catName] || []).length === 0 && <p className="text-slate-400 text-sm font-bold italic">Aucune donnée</p>}
                {(grouped[catName] || []).map(c => (
                    <div key={c.id} className="flex justify-between items-center bg-slate-50 p-3 rounded-lg group border border-slate-100">
                        <span className="font-bold text-slate-700">{c.value}</span>
                        <button onClick={() => handleDelete(c.id)} className="text-slate-300 hover:text-red-500 p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Trash2 className="w-4 h-4" />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );

    return (
        <div className="p-6 w-full h-[calc(100vh-80px)] overflow-y-auto animate-fade-in relative font-sans bg-white border-y border-slate-200/80">
            <h1 className="text-3xl font-black text-slate-800 mb-2 flex items-center gap-3">
                <Settings className="w-8 h-8 text-blue-600" /> Options & Référentiels
            </h1>
            <p className="text-slate-500 font-medium mb-8">Administrez vos listes personnalisées pour harmoniser la création de produits et les sélections dans tout l'ERP.</p>

            <form onSubmit={handleAdd} className="bg-white p-6 rounded-2xl border border-blue-200 shadow-sm flex items-end gap-4 mb-8 bg-gradient-to-r from-blue-50 to-white">
                <div className="flex-1">
                    <label className="block text-xs font-black text-blue-800 uppercase tracking-widest mb-2">Ajouter à la liste :</label>
                    <select value={newCat} onChange={e=>setNewCat(e.target.value)} className="w-full p-3 bg-white border border-blue-200 rounded-xl font-bold text-slate-700 focus:ring-2 outline-none">
                        <option value="product_category">Familles / catégories articles</option>
                        <option value="material">Matières</option>
                        <option value="unit">Unités de Mesure</option>
                        <option value="supplier">Fournisseurs</option>
                        <option value="specs">Spécificités (Couleur, Sens, Finition...)</option>
                        <option value="bank_rib">Coordonnées Bancaires (RIB / IBAN)</option>
                    </select>
                </div>
                <div className="flex-1">
                    <label className="block text-xs font-black text-blue-800 uppercase tracking-widest mb-2">Valeur :</label>
                    <input autoFocus value={newVal} onChange={e=>setNewVal(e.target.value)} className="w-full p-3 bg-white border border-blue-200 rounded-xl font-bold uppercase text-slate-700 focus:ring-2 outline-none" placeholder="Ex: IBAN FR76..., NOIR MAT..." />
                </div>
                <button type="submit" className="bg-blue-600 hover:bg-blue-500 text-white font-black px-6 py-3 rounded-xl shadow border-b-4 border-blue-700 active:border-b-0 active:translate-y-1 transition-all flex items-center gap-2">
                    <Plus className="w-5 h-5"/> Sauvegarder
                </button>
            </form>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
                {renderTable('product_category', 'Familles / catégories')}
                {renderTable('material', 'Matières')}
                {renderTable('unit', 'Unités')}
                {renderTable('supplier', 'Fournisseurs')}
                {renderTable('specs', 'Spécificités Variantes')}
                {renderTable('bank_rib', 'Coordonnées Bancaires')}
            </div>
        </div>
    );
}
