import React, { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, Check, Plus, Trash2, X } from 'lucide-react';
import api from '../services/api';

export default function RBACMatrix() {
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showRoleModal, setShowRoleModal] = useState(false);
    const [newRoleForm, setNewRoleForm] = useState({ name: '', description: '' });

    const fetchData = async () => {
        try {
            const [rolesRes, permsRes] = await Promise.all([
                api.get('/v2/config/roles'),
                api.get('/v2/config/permissions')
            ]);
            setRoles(rolesRes.data);
            setPermissions(permsRes.data);
        } catch (e) {
            console.error("Error fetching RBAC", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const togglePermission = async (roleId, permissionId, currentStatus) => {
        const role = roles.find(r => r.id === roleId);
        if (!role) return;
        
        let newPermIds = role.permissions.map(p => p.id);
        if (currentStatus) {
            newPermIds = newPermIds.filter(id => id !== permissionId);
        } else {
            newPermIds.push(permissionId);
        }

        try {
            await api.post(`/v2/config/roles/${roleId}/permissions`, newPermIds);
            fetchData();
        } catch (e) {
            alert('Cannot update permissions');
        }
    };

    const submitNewRole = async () => {
        if (!newRoleForm.name) return;
        try {
            await api.post('/v2/config/roles', newRoleForm);
            setShowRoleModal(false);
            setNewRoleForm({ name: '', description: '' });
            fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur lors de la création du rôle");
        }
    };

    const deleteRole = async (roleId) => {
        if (!window.confirm("Supprimer ce profil d'accès ?")) return;
        try {
            await api.delete(`/v2/config/roles/${roleId}`);
            fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur de suppression");
        }
    };

    if (loading) return <div className="p-8 text-center animate-pulse font-bold text-slate-400">Chargement Matrice RBAC...</div>;

    // Group permissions by module
    const groupedPerms = permissions.reduce((acc, curr) => {
        if (!acc[curr.module]) acc[curr.module] = [];
        acc[curr.module].push(curr);
        return acc;
    }, {});

    return (
        <div className="mt-12 bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden font-sans">
            <div className="p-8 bg-slate-900 text-white flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-black flex items-center gap-3">
                        <ShieldCheck className="w-8 h-8 text-emerald-400" /> Matrice des Rôles & Sécurité
                    </h2>
                    <p className="text-slate-400 font-medium mt-1">Cochez ou décochez pour lier un module à un rôle utilisateur.</p>
                </div>
                <div className="flex -space-x-3">
                    {roles.map((r, i) => (
                        <div key={r.id} className="w-12 h-12 rounded-full border-4 border-slate-900 bg-slate-800 flex items-center justify-center font-black text-xs" style={{zIndex: roles.length - i}}>
                            {r.name.substring(0, 2)}
                        </div>
                    ))}
                    <button onClick={() => setShowRoleModal(true)} className="w-12 h-12 rounded-full border-4 border-slate-900 bg-emerald-600 hover:bg-emerald-500 transition-colors flex items-center justify-center text-white" style={{zIndex: 0}}>
                        <Plus className="w-5 h-5" />
                    </button>
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                            <th className="p-4 font-black w-64 border-r border-slate-200 text-slate-800">Modules & Accès</th>
                            {roles.map(role => (
                                <th key={role.id} className="p-4 text-center font-black text-sm text-slate-700 min-w-[120px] relative group">
                                    {role.name}
                                    {role.name !== 'ADMIN' && (
                                        <button onClick={() => deleteRole(role.id)} className="absolute top-2 right-2 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    )}
                                </th>
                            ))}
                            <th className="p-4 text-center w-[120px]">
                                <button onClick={() => setShowRoleModal(true)} className="text-xs font-bold bg-slate-800 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 mx-auto hover:bg-emerald-600 transition-colors">
                                    <Plus className="w-3 h-3"/> Profil
                                </button>
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {Object.entries(groupedPerms).map(([moduleName, perms]) => (
                            <React.Fragment key={moduleName}>
                                <tr className="bg-slate-100/50">
                                    <td colSpan={roles.length + 1} className="p-3 font-black text-xs uppercase tracking-widest text-slate-500 border-b border-slate-200 border-t">
                                        {moduleName}
                                    </td>
                                </tr>
                                {perms.map(perm => (
                                    <tr key={perm.id} className="border-b border-slate-100 hover:bg-slate-50">
                                        <td className="p-4 border-r border-slate-200">
                                            <div className="font-bold text-slate-800 text-sm">{perm.description}</div>
                                            <div className="text-xs font-mono text-slate-400">{perm.code}</div>
                                        </td>
                                        {roles.map(role => {
                                            const hasPerm = role.permissions.some(p => p.id === perm.id);
                                            const isAdmin = role.name === 'ADMIN';
                                            return (
                                                <td key={role.id} className="p-4 text-center border-r border-slate-100">
                                                    <button 
                                                        disabled={isAdmin}
                                                        onClick={() => togglePermission(role.id, perm.id, hasPerm)}
                                                        className={`w-8 h-8 rounded-lg flex items-center justify-center mx-auto transition-all ${
                                                            hasPerm 
                                                                ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20' 
                                                                : 'bg-slate-100 text-slate-300 hover:bg-slate-200'
                                                        } ${isAdmin ? 'opacity-50 cursor-not-allowed grayscale' : ''}`}
                                                    >
                                                        {hasPerm && <Check className="w-5 h-5" />}
                                                    </button>
                                                </td>
                                            );
                                        })}
                                        <td className="p-4 bg-slate-50 border-l border-slate-200"></td>
                                    </tr>
                                ))}
                            </React.Fragment>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="p-4 bg-amber-50 text-amber-800 text-sm font-bold flex flex-col sm:flex-row items-center gap-3 border-t border-amber-200">
                <ShieldAlert className="w-5 h-5" /> 
                <p>Attention : Les utilisateurs "ADMIN" reçoivent techniquement toutes les permissions par défaut. Cette matrice s'applique immédiatement aux autres rôles dès qu'ils se reconnectent.</p>
            </div>

            {showRoleModal && (
                <div className="fixed inset-0 z-[100] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl p-8 max-w-sm w-full shadow-2xl relative">
                        <button onClick={() => setShowRoleModal(false)} className="absolute top-4 right-4 p-2 bg-slate-100 rounded-full text-slate-500 hover:bg-slate-200">
                            <X className="w-5 h-5" />
                        </button>
                        <h3 className="font-black text-xl text-slate-800 mb-6 flex items-center gap-2">
                            <ShieldCheck className="w-6 h-6 text-emerald-500" />
                            Nouveau Profil
                        </h3>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Nom du Rôle Court</label>
                                <input 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-black text-slate-800 uppercase focus:ring-2 focus:ring-emerald-500 outline-none" 
                                    placeholder="EX: COMPTABLE" 
                                    value={newRoleForm.name} 
                                    onChange={e => setNewRoleForm({...newRoleForm, name: e.target.value.toUpperCase()})}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Description</label>
                                <input 
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-medium text-slate-700 focus:ring-2 focus:ring-emerald-500 outline-none" 
                                    placeholder="Accès à la trésorerie..." 
                                    value={newRoleForm.description} 
                                    onChange={e => setNewRoleForm({...newRoleForm, description: e.target.value})}
                                />
                            </div>
                            <button onClick={submitNewRole} className="w-full py-4 mt-2 bg-emerald-600 hover:bg-emerald-500 text-white font-black rounded-xl shadow-lg transition-transform active:scale-95">
                                Créer et paramétrer
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
