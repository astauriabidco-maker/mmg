import React, { useState, useEffect } from 'react';
import api from '../services/api';
import { Save, AlertCircle, RefreshCw, PlusCircle, Factory, CalendarClock, Briefcase, Truck, Settings } from 'lucide-react';

const CATEGORY_ICONS = {
    'PRODUCTION': Factory,
    'PLANNING': CalendarClock,
    'COMMERCIAL': Briefcase,
    'LOGISTIQUE': Truck
};

export default function BusinessRulesManager() {
    const [rules, setRules] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState({});
    const [message, setMessage] = useState(null);

    const fetchRules = async () => {
        setLoading(true);
        try {
            const res = await api.get('/v2/config/rules');
            setRules(res.data);
        } catch (e) {
            setMessage({ type: 'error', text: 'Erreur lors du chargement des règles métier.' });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRules();
    }, []);

    const handleUpdateRule = async (rule_key, value) => {
        setSaving({ ...saving, [rule_key]: true });
        try {
            await api.put(`/v2/config/rules/${rule_key}`, { value: value.toString() });
            setMessage({ type: 'success', text: 'Règle mise à jour avec succès.' });
            setTimeout(() => setMessage(null), 3000);
        } catch (e) {
            setMessage({ type: 'error', text: 'Erreur lors de la sauvegarde.' });
        } finally {
            setSaving({ ...saving, [rule_key]: false });
        }
    };

    const handleChange = (id, newValue) => {
        setRules(rules.map(r => r.id === id ? { ...r, value: newValue } : r));
    };

    if (loading) {
        return <div className="p-8 text-center text-slate-400 font-bold animate-pulse">Chargement des règles...</div>;
    }

    // Group rules by category
    const groupedRules = rules.reduce((acc, rule) => {
        if (!acc[rule.category]) acc[rule.category] = [];
        acc[rule.category].push(rule);
        return acc;
    }, {});

    return (
        <div className="space-y-8 animate-fade-in">
            {message && (
                <div className={`p-4 rounded-xl font-bold flex items-center gap-2 ${message.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-emerald-50 text-emerald-600'}`}>
                    <AlertCircle className="w-5 h-5" />
                    {message.text}
                </div>
            )}

            {Object.entries(groupedRules).map(([category, categoryRules]) => {
                const Icon = CATEGORY_ICONS[category] || Settings;
                return (
                    <section key={category} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="w-10 h-10 rounded-xl bg-slate-50 flex items-center justify-center text-slate-600">
                                <Icon className="w-5 h-5" />
                            </div>
                            <h3 className="text-sm font-black text-slate-800 uppercase tracking-widest">{category}</h3>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {categoryRules.map((rule) => (
                                <div key={rule.id} className="bg-slate-50 p-4 rounded-xl border border-slate-100 flex flex-col justify-between">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-500 mb-1">{rule.description || rule.rule_key}</label>
                                        <div className="text-[10px] text-slate-400 font-mono mb-3">{rule.rule_key}</div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <input 
                                            type={rule.value_type === 'number' ? 'number' : 'text'}
                                            step={rule.value_type === 'number' ? 'any' : undefined}
                                            value={rule.value}
                                            onChange={(e) => handleChange(rule.id, e.target.value)}
                                            className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500" 
                                        />
                                        <button 
                                            onClick={() => handleUpdateRule(rule.rule_key, rule.value)}
                                            disabled={saving[rule.rule_key]}
                                            className="p-2 bg-blue-100 text-blue-600 hover:bg-blue-200 rounded-lg transition-colors disabled:opacity-50"
                                            title="Sauvegarder cette règle"
                                        >
                                            {saving[rule.rule_key] ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>
                );
            })}
        </div>
    );
}
