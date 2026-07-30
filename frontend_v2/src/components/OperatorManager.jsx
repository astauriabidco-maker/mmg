import React, { useState, useEffect } from 'react';
import { UserPlus, Trash2, Shield, Link2, RefreshCw, Edit2, X, Check } from 'lucide-react';
import api from '../services/api';

const ROLE_DISPLAY = {
    SUPER_ADMIN: { label: 'Super admin', family: 'Bureau' },
    ADMIN: { label: 'Administrateur', family: 'Bureau' },
    MANAGER: { label: 'Manager opérationnel', family: 'Bureau' },
    SALES: { label: 'Commercial CRM', family: 'Bureau' },
    TECHNICO_COMMERCIAL: { label: 'Technico-commercial', family: 'Bureau d’études' },
    FINANCE: { label: 'Comptable / Finance', family: 'Bureau' },
    ACHATS: { label: 'Achats', family: 'Bureau' },
    MAGASINIER: { label: 'Magasinier', family: 'Stock' },
    CHEF_STOCK: { label: 'Chef stock', family: 'Stock' },
    OPERATOR: { label: 'Opérateur atelier', family: 'Atelier' },
    DEBIT_OPERATOR: { label: 'Débit atelier', family: 'Atelier' },
    QUALITY_CONTROLLER: { label: 'Contrôle qualité', family: 'Atelier' },
    WORKSHOP_LEAD: { label: 'Chef atelier', family: 'Atelier' },
};

export default function OperatorManager() {
    const pinRoles = ['OPERATOR', 'DEBIT_OPERATOR', 'QUALITY_CONTROLLER', 'WORKSHOP_LEAD', 'MAGASINIER'];
    const [users, setUsers] = useState([]);
    const [stations, setStations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [roles, setRoles] = useState([]);
    const [newUser, setNewUser] = useState({ 
        username: '', 
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        pin: '', 
        role: 'OPERATOR', 
        station_codes: [] 
    });
    const [editingUser, setEditingUser] = useState(null);
    const [message, setMessage] = useState({ type: '', text: '' });

    const fetchData = async () => {
        setLoading(true);
        try {
            const [usersRes, stationsRes, rolesRes] = await Promise.all([
                api.get('/v2/config/users'),
                api.get('/v2/config/stations'),
                api.get('/v2/config/roles')
            ]);
            setUsers(usersRes.data);
            setStations(stationsRes.data);
            setRoles(rolesRes.data);
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
            await api.post('/v2/config/users', { ...newUser });
            setMessage({ type: 'success', text: `Utilisateur ${newUser.username} créé !` });
            setNewUser({ 
                username: '', 
                first_name: '',
                last_name: '',
                email: '',
                phone: '',
                pin: '', 
                role: 'OPERATOR', 
                station_codes: [] 
            });
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
                first_name: editingUser.first_name,
                last_name: editingUser.last_name,
                email: editingUser.email,
                phone: editingUser.phone,
                role: editingUser.role,
                station_codes: editingUser.station_codes
            };
            if (editingUser.pin) payload.pin = editingUser.pin;

            await api.put(`/v2/config/users/${editingUser.id}`, payload);
            setMessage({ type: 'success', text: `Utilisateur ${editingUser.username} mis à jour !` });
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
                    {editingUser ? `Modifier ${editingUser.username}` : 'Nouvel utilisateur'}
                </h3>

                <form onSubmit={editingUser ? handleUpdate : handleCreate} className="space-y-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        <div className="col-span-1 md:col-span-2 lg:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Prénom</label>
                                <input
                                    type="text"
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                    placeholder="ex: Jean"
                                    value={editingUser ? (editingUser.first_name || '') : newUser.first_name}
                                    onChange={e => editingUser ? setEditingUser({ ...editingUser, first_name: e.target.value }) : setNewUser({ ...newUser, first_name: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Nom de famille</label>
                                <input
                                    type="text"
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                    placeholder="ex: Dupont"
                                    value={editingUser ? (editingUser.last_name || '') : newUser.last_name}
                                    onChange={e => editingUser ? setEditingUser({ ...editingUser, last_name: e.target.value }) : setNewUser({ ...newUser, last_name: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Email</label>
                                <input
                                    type="email"
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                    placeholder="ex: jean.dupont@mmg.com"
                                    value={editingUser ? (editingUser.email || '') : newUser.email}
                                    onChange={e => editingUser ? setEditingUser({ ...editingUser, email: e.target.value }) : setNewUser({ ...newUser, email: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Téléphone</label>
                                <input
                                    type="tel"
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                    placeholder="ex: 06 12 34 56 78"
                                    value={editingUser ? (editingUser.phone || '') : newUser.phone}
                                    onChange={e => editingUser ? setEditingUser({ ...editingUser, phone: e.target.value }) : setNewUser({ ...newUser, phone: e.target.value })}
                                />
                            </div>
                        </div>

                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Identifiant (Login)</label>
                            <input
                                type="text"
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                placeholder="ex: j.dupont"
                                value={editingUser ? editingUser.username : newUser.username}
                                onChange={e => editingUser ? setEditingUser({ ...editingUser, username: e.target.value }) : setNewUser({ ...newUser, username: e.target.value })}
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Rôle / Accès</label>
                            <select
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20 font-bold"
                                value={editingUser ? editingUser.role : newUser.role}
                                onChange={e => editingUser ? setEditingUser({ ...editingUser, role: e.target.value }) : setNewUser({ ...newUser, role: e.target.value })}
                            >
                                {roles.map(r => {
                                    const meta = ROLE_DISPLAY[r.name] || { label: r.name, family: 'Personnalisé' };
                                    return (
                                        <option key={r.id} value={r.name}>{meta.label} · {meta.family} - {r.description}</option>
                                    );
                                })}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-slate-400 uppercase mb-2">
                                {editingUser ? 'Nouveau Code/Mot de Passe (vide = inchangé)' : (pinRoles.includes(editingUser ? editingUser.role : newUser.role) ? 'Code PIN (4 chiffres)' : 'Mot de passe')}
                            </label>
                            <input
                                type={pinRoles.includes(editingUser ? editingUser.role : newUser.role) ? 'text' : 'password'}
                                maxLength={pinRoles.includes(editingUser ? editingUser.role : newUser.role) ? "4" : "100"}
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-slate-700 outline-none focus:ring-2 focus:ring-blue-500/20"
                                placeholder={pinRoles.includes(editingUser ? editingUser.role : newUser.role) ? "1234" : "Mot de passe sécurisé..."}
                                value={editingUser ? (editingUser.pin || '') : newUser.pin}
                                onChange={e => editingUser ? setEditingUser({ ...editingUser, pin: e.target.value }) : setNewUser({ ...newUser, pin: e.target.value })}
                                required={!editingUser}
                            />
                            <p className="mt-2 text-[11px] font-bold text-slate-400">
                                Les profils atelier utilisent un PIN court sur tablette. Les profils bureau utilisent un mot de passe.
                            </p>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase mb-4">Affectation aux postes PVC/ALU</label>
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
                            {editingUser ? 'Mettre à jour' : 'Créer l’utilisateur'}
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
                        Utilisateurs existants
                    </h3>
                    <button onClick={fetchData} className="p-2 text-slate-400 hover:text-blue-500 transition-colors">
                        <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left">
                        <thead>
                            <tr className="bg-slate-50 border-b border-slate-200">
                                <th className="p-4 text-left font-black text-slate-800">Employé</th>
                                <th className="p-4 text-left font-black text-slate-800">Identifiant (Login)</th>
                                <th className="p-4 text-left font-black text-slate-800">Contact</th>
                                <th className="p-4 text-left font-black text-slate-800">Rôle / Accès</th>
                                <th className="p-4 text-left font-black text-slate-800">Postes Assignés</th>
                                <th className="p-4 text-center font-black text-slate-800">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map((user) => (
                                <tr key={user.id} className="border-b border-slate-50 group hover:bg-slate-50/50 transition-colors">
                                    <td className="p-4 font-bold text-slate-800">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-black shadow-inner">
                                                {user.first_name ? user.first_name.charAt(0).toUpperCase() : user.username.charAt(0).toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="text-sm font-black">{user.first_name} {user.last_name}</div>
                                                <div className="text-xs text-slate-400 font-medium">{ROLE_DISPLAY[user.role]?.family || (pinRoles.includes(user.role) ? 'Atelier' : 'Bureau')}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="p-4 text-slate-600 font-mono text-sm font-medium">{user.username}</td>
                                    <td className="p-4 text-slate-600 text-sm">
                                        {user.email && <div className="text-xs">{user.email}</div>}
                                        {user.phone && <div className="text-xs">{user.phone}</div>}
                                        {(!user.email && !user.phone) && <span className="text-slate-300 italic">Non renseigné</span>}
                                    </td>
                                    <td className="p-4">
                                        <div className="text-xs font-black text-slate-700">{ROLE_DISPLAY[user.role]?.label || user.role}</div>
                                        <div className="text-[10px] text-slate-400 font-medium uppercase tracking-widest">{user.role}</div>
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
