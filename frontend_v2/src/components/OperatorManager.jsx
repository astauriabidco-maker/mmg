import React, { useState, useEffect } from 'react';
import { UserPlus, Trash2, Shield, Link2, RefreshCw, Edit2, X, Check } from 'lucide-react';
import api from '../services/api';

export default function OperatorManager() {
    const [users, setUsers] = useState([]);
    const [stations, setStations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newUser, setNewUser] = useState({ username: '', pin: '', station_codes: [] });
    const [editingUser, setEditingUser] = useState(null);
    const [message, setMessage] = useState({ type: '', text: '' });

    const fetchData = async () => {
        setLoading(true);
        try {
            const [usersRes, stationsRes] = await Promise.all([
                api.get('/v2/config/users'),
                api.get('/v2/config/stations')
            ]);
            setUsers(usersRes.data);
            setStations(stationsRes.data);
        } catch (e) {
            console.error(e);
            setMessage({ type: 'error', text: 'Erreur lors du chargement des données' });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleCreate = async (e) => {
        e.preventDefault();
        try {
            await api.post('/v2/config/users', {
                ...newUser,
                role: 'OPERATOR'
            });
            setMessage({ type: 'success', text: `Opérateur ${newUser.username} créé !` });
            setNewUser({ username: '', pin: '', station_codes: [] });
            fetchData();
        } catch (e) {
            setMessage({ type: 'error', text: e.response?.data?.detail || 'Erreur de création' });
        }
    };

    const handleUpdate = async (e) => {
        e.preventDefault();
        try {
            const payload = {
                username: editingUser.username,
                station_codes: editingUser.station_codes
            };
            if (editingUser.pin) payload.pin = editingUser.pin;

            await api.put(`/v2/config/users/${editingUser.id}`, payload);
            setMessage({ type: 'success', text: `Opérateur ${editingUser.username} mis à jour !` });
            setEditingUser(null);
            fetchData();
        } catch (e) {
            setMessage({ type: 'error', text: e.response?.data?.detail || 'Erreur de mise à jour' });
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Supprimer cet opérateur ?')) return;
        try {
            await api.delete(`/v2/config/users/${id}`);
            fetchData();
        } catch (e) {
            setMessage({ type: 'error', text: 'Erreur de suppression' });
        }
    };

    const toggleStation = (userState, setUserState, code) => {
        const current = userState.station_codes || [];
        if (current.includes(code)) {
            setUserState({ ...userState, station_codes: current.filter(c => c !== code) });
        } else {
            setUserState({ ...userState, station_codes: [...current, code] });
        }
    };

    return (
        <div className="space-y-8 animate-fade-in-up" style={{ animationDelay: '200ms' }}>
            {/* CREATION / EDIT FORM */}
            <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-100">
                <h3 className="text-xl font-bold text-slate-800 mb-6 flex items-center gap-2">
                    {editingUser ? <Edit2 className="text-indigo-500" /> : <UserPlus className="text-blue-500" />}
                    {editingUser ? `Modifier ${editingUser.username}` : 'Nouvel Opérateur'}
                </h3>

                <form onSubmit={editingUser ? handleUpdate : handleCreate} className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Nom Utilisateur</label>
                            <input
                                type="text"
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                placeholder="ex: Jean_Debit"
                                value={editingUser ? editingUser.username : newUser.username}
                                onChange={e => editingUser ? setEditingUser({ ...editingUser, username: e.target.value }) : setNewUser({ ...newUser, username: e.target.value })}
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">
                                {editingUser ? 'Nouveau PIN (laisser vide pour inchangé)' : 'Code PIN (4 chiffres)'}
                            </label>
                            <input
                                type="text"
                                maxLength="4"
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                placeholder="1234"
                                value={editingUser ? (editingUser.pin || '') : newUser.pin}
                                onChange={e => editingUser ? setEditingUser({ ...editingUser, pin: e.target.value }) : setNewUser({ ...newUser, pin: e.target.value })}
                                required={!editingUser}
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase mb-4">Affectation aux Postes (Plusieurs choix possibles)</label>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            {stations.map(s => {
                                const isSelected = editingUser
                                    ? editingUser.station_codes?.includes(s.code)
                                    : newUser.station_codes?.includes(s.code);
                                return (
                                    <button
                                        key={s.id}
                                        type="button"
                                        onClick={() => editingUser
                                            ? toggleStation(editingUser, setEditingUser, s.code)
                                            : toggleStation(newUser, setNewUser, s.code)
                                        }
                                        className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition-all ${isSelected ? 'bg-blue-50 border-blue-500 text-blue-700 shadow-sm' : 'bg-white border-slate-100 text-slate-500 hover:border-slate-300'}`}
                                    >
                                        <div className={`w-4 h-4 rounded-md flex items-center justify-center border ${isSelected ? 'bg-blue-500 border-blue-500 text-white' : 'bg-slate-50 border-slate-200'}`}>
                                            {isSelected && <Check className="w-3 h-3" />}
                                        </div>
                                        <span className="truncate">{s.material} - {s.display_name}</span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div className="flex gap-4 pt-4">
                        <button
                            type="submit"
                            className={`${editingUser ? 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-500/20' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-500/20'} text-white font-bold py-3 px-8 rounded-xl transition-all shadow-lg active:scale-95`}
                        >
                            {editingUser ? 'Mettre à jour' : 'Ajouter'}
                        </button>
                        {editingUser && (
                            <button
                                type="button"
                                onClick={() => setEditingUser(null)}
                                className="bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold py-3 px-8 rounded-xl transition-all active:scale-95"
                            >
                                Annuler
                            </button>
                        )}
                    </div>
                </form>

                {message.text && (
                    <div className={`mt-6 p-4 rounded-xl text-sm font-medium flex items-center justify-between ${message.type === 'error' ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}`}>
                        {message.text}
                        <button onClick={() => setMessage({ text: '', type: '' })}><X className="w-4 h-4" /></button>
                    </div>
                )}
            </div>

            {/* USERS LIST */}
            <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-100">
                <div className="flex justify-between items-center mb-6">
                    <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Shield className="text-emerald-500" />
                        Liste des Opérateurs
                    </h3>
                    <button onClick={fetchData} className="p-2 text-slate-400 hover:text-blue-500 transition-colors">
                        <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="text-slate-400 text-xs font-bold uppercase tracking-wider border-b border-slate-50">
                                <th className="pb-4">Utilisateur</th>
                                <th className="pb-4">Postes Assignés</th>
                                <th className="pb-4 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map((user) => (
                                <tr key={user.id} className="border-b border-slate-50 group hover:bg-slate-50/50 transition-colors">
                                    <td className="py-4 font-bold text-slate-700 flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-black">
                                            {user.username.slice(0, 2).toUpperCase()}
                                        </div>
                                        <div>
                                            <p>{user.username}</p>
                                            <p className="text-[10px] text-slate-400 font-medium uppercase tracking-widest">{user.role}</p>
                                        </div>
                                    </td>
                                    <td className="py-4">
                                        <div className="flex flex-wrap gap-1.5">
                                            {user.stations?.length > 0 ? user.stations.map(s => (
                                                <span key={s.id} className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-[10px] font-bold border border-slate-200">
                                                    {s.display_name}
                                                </span>
                                            )) : (
                                                <span className="text-slate-400 italic text-xs">Aucun poste</span>
                                            )}
                                        </div>
                                    </td>
                                    <td className="py-4 text-right">
                                        <div className="flex justify-end gap-2">
                                            <button
                                                onClick={() => setEditingUser({
                                                    ...user,
                                                    station_codes: user.stations.map(s => s.code),
                                                    pin: ''
                                                })}
                                                className="p-2 text-slate-400 hover:text-indigo-600 transition-colors hover:bg-indigo-50 rounded-lg"
                                                title="Modifier"
                                            >
                                                <Edit2 className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(user.id)}
                                                className="p-2 text-slate-400 hover:text-red-500 transition-colors hover:bg-red-50 rounded-lg"
                                                title="Supprimer"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
