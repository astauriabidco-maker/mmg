import React, { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, Check, Plus, Trash2, X, Users, Eye, Settings2 } from 'lucide-react';
import api from '../services/api';

const ROLE_PRESETS = [
    {
        name: 'MAGASINIER',
        label: 'Magasinier',
        description: 'Réceptionne, range, transfère et compte le stock.',
        scope: 'Stock',
        permissions: ['STOCK_VIEW', 'stock.receive', 'stock.transfer', 'inventory.count', 'purchases.receive'],
    },
    {
        name: 'CHEF_STOCK',
        label: 'Chef stock',
        description: 'Pilote le stock, les inventaires, les corrections et le catalogue.',
        scope: 'Stock',
        permissions: ['STOCK_VIEW', 'STOCK_EDIT', 'stock.receive', 'stock.transfer', 'stock.adjust', 'catalog.qualify', 'workshop.reserve_stock', 'workshop.consume_stock', 'inventory.count', 'inventory.validate', 'purchases.receive'],
    },
    {
        name: 'DEBIT_OPERATOR',
        label: 'Débit atelier',
        description: 'Confirme le débit réel depuis les réservations atelier.',
        scope: 'Atelier',
        permissions: ['PROD_VIEW', 'planning:start', 'planning:pause', 'planning:stop', 'planning:consume_stock', 'workshop.consume_stock', 'planning:report_issue'],
    },
    {
        name: 'WORKSHOP_LEAD',
        label: 'Chef atelier',
        description: 'Pilote les postes, priorités, blocages et débits atelier.',
        scope: 'Atelier',
        permissions: ['PROD_VIEW', 'PROD_EDIT', 'planning:start', 'planning:pause', 'planning:stop', 'planning:consume_stock', 'planning:reprioritize', 'planning:assign', 'planning:unblock', 'planning:report_issue', 'quality:reject', 'STOCK_VIEW', 'stock.receive', 'stock.transfer', 'workshop.reserve_stock', 'workshop.consume_stock', 'inventory.count'],
    },
    {
        name: 'ACHATS',
        label: 'Achats',
        description: 'Suit les commandes fournisseurs et les réceptions attendues.',
        scope: 'Achats',
        permissions: ['STOCK_VIEW', 'purchases.receive'],
    },
    {
        name: 'SALES',
        label: 'Commercial CRM',
        description: 'Gère les clients, propositions, devis et avant-vente.',
        scope: 'Ventes',
        permissions: ['SALES_VIEW', 'SALES_EDIT'],
    },
];

const ROLE_FALLBACKS = {
    SUPER_ADMIN: { label: 'Super admin', scope: 'Système', description: 'Accès complet à toute la plateforme.', permissions: ['*'] },
    ADMIN: { label: 'Administrateur', scope: 'Système', description: 'Administration complète des modules, profils et données.', permissions: ['*'] },
    MANAGER: { label: 'Manager opérationnel', scope: 'Pilotage', description: 'Pilote ventes, atelier, stock et production.', permissions: [] },
    OPERATOR: { label: 'Opérateur atelier', scope: 'Atelier', description: 'Exécute les tâches atelier assignées.', permissions: [] },
    QUALITY_CONTROLLER: { label: 'Contrôle qualité', scope: 'Atelier', description: 'Contrôle et signale les défauts qualité.', permissions: [] },
};

const MODULE_PURPOSES = {
    'Comptabilité': 'Factures, paiements, avoirs et export comptable.',
    'Ventes (CRM)': 'Clients, propositions, devis et cycle commercial.',
    'Stocks & Logistique': 'Consultation et pilotage global du stock.',
    'Stock - Actions': 'Réception, transfert et correction physique.',
    'Stock - Catalogue': 'Création et qualification des fiches articles.',
    'Stock - Atelier': 'Réservation et consommation du stock atelier.',
    'Stock - Inventaire physique': 'Comptage, recompte et validation des écarts.',
    'Achats': 'Réceptions fournisseur et suivi achats.',
    'Atelier': 'Vue atelier et production.',
    'Atelier - Actions': 'Actions opérateur sur les tâches atelier.',
    'Atelier - Pilotage': 'Priorités, affectations et déblocages atelier.',
    'Atelier - Qualité': 'Contrôle et rejet qualité.',
    'Configuration': 'Paramètres de la plateforme.',
};

export default function RBACMatrix() {
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showRoleModal, setShowRoleModal] = useState(false);
    const [newRoleForm, setNewRoleForm] = useState({ name: '', description: '' });
    const [applyingPreset, setApplyingPreset] = useState(null);
    const [selectedRoleName, setSelectedRoleName] = useState('MAGASINIER');

    const fetchData = async () => {
        try {
            const [rolesRes, permsRes, usersRes] = await Promise.all([
                api.get('/v2/config/roles'),
                api.get('/v2/config/permissions'),
                api.get('/v2/config/users')
            ]);
            setRoles(rolesRes.data);
            setPermissions(permsRes.data);
            setUsers(usersRes.data);
            if (!rolesRes.data.some(role => role.name === selectedRoleName) && rolesRes.data[0]) {
                setSelectedRoleName(rolesRes.data[0].name);
            }
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

    const applyPreset = async (preset) => {
        const missingCodes = preset.permissions.filter(code => !permissions.some(permission => permission.code === code));
        if (missingCodes.length > 0) {
            alert(`Permissions manquantes côté serveur : ${missingCodes.join(', ')}. Redémarrez le backend pour relancer le seed.`);
            return;
        }
        const message = roles.some(role => role.name === preset.name)
            ? `Appliquer le modèle "${preset.label}" et remplacer ses permissions actuelles ?`
            : `Créer le rôle "${preset.label}" avec ses permissions métier ?`;
        if (!window.confirm(message)) return;
        setApplyingPreset(preset.name);
        try {
            let role = roles.find(r => r.name === preset.name);
            if (!role) {
                const roleRes = await api.post('/v2/config/roles', {
                    name: preset.name,
                    description: preset.description,
                });
                role = roleRes.data;
            }
            const permissionIds = permissions
                .filter(permission => preset.permissions.includes(permission.code))
                .map(permission => permission.id);
            await api.post(`/v2/config/roles/${role.id}/permissions`, permissionIds);
            await fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Impossible d'appliquer ce profil métier.");
        } finally {
            setApplyingPreset(null);
        }
    };

    if (loading) return <div className="p-8 text-center animate-pulse font-bold text-slate-400">Chargement Matrice RBAC...</div>;

    // Group permissions by module
    const groupedPerms = permissions.reduce((acc, curr) => {
        if (!acc[curr.module]) acc[curr.module] = [];
        acc[curr.module].push(curr);
        return acc;
    }, {});
    const selectedRole = roles.find(role => role.name === selectedRoleName) || roles[0];
    const selectedPreset = ROLE_PRESETS.find(preset => preset.name === selectedRole?.name) || ROLE_FALLBACKS[selectedRole?.name];
    const selectedPermissions = selectedRole ? selectedRole.permissions || [] : [];
    const selectedPermissionCodes = new Set(selectedPermissions.map(permission => permission.code));
    const selectedUsers = users.filter(user => user.role === selectedRole?.name);
    const selectedGroupedPermissions = selectedPermissions.reduce((acc, permission) => {
        if (!acc[permission.module]) acc[permission.module] = [];
        acc[permission.module].push(permission);
        return acc;
    }, {});
    const isBuiltinFullAccess = ['ADMIN', 'SUPER_ADMIN'].includes(selectedRole?.name);

    return (
        <div className="mt-12 space-y-6 font-sans">
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-6 border-b border-slate-100 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
                    <div>
                        <p className="text-[11px] font-black uppercase tracking-widest text-blue-500">Profils prêts à l'emploi</p>
                        <h2 className="text-2xl font-black text-slate-900 mt-1">Choisir un rôle métier, pas une matrice</h2>
                        <p className="text-sm font-semibold text-slate-500 mt-1">
                            Ces modèles créent ou remettent à niveau les permissions d'un profil standard MMG.
                        </p>
                    </div>
                    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-800">
                        La matrice avancée reste disponible plus bas pour les exceptions.
                    </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-6">
                    {ROLE_PRESETS.map(preset => {
                        const roleExists = roles.some(role => role.name === preset.name);
                        return (
                            <button
                                key={preset.name}
                                type="button"
                                onClick={() => applyPreset(preset)}
                                disabled={applyingPreset === preset.name}
                                className="text-left rounded-2xl border border-slate-200 bg-slate-50 hover:bg-white hover:border-blue-200 hover:shadow-md transition-all p-5 disabled:opacity-60 disabled:cursor-wait"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <span className="inline-flex px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                            {preset.scope}
                                        </span>
                                        <h3 className="text-lg font-black text-slate-900 mt-3">{preset.label}</h3>
                                    </div>
                                    <span className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase ${roleExists ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'}`}>
                                        {roleExists ? 'Existe' : 'À créer'}
                                    </span>
                                </div>
                                <p className="text-sm font-semibold text-slate-600 mt-3 min-h-[2.5rem]">{preset.description}</p>
                                <div className="flex items-center justify-between mt-4">
                                    <span className="text-xs font-black text-slate-400">{preset.permissions.length} permission(s)</span>
                                    <span className="text-xs font-black text-blue-600">
                                        {applyingPreset === preset.name ? 'Application...' : roleExists ? 'Remettre à niveau' : 'Créer le profil'}
                                    </span>
                                </div>
                            </button>
                        );
                    })}
                </div>
            </div>

            {selectedRole && (
                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] min-h-[520px]">
                        <aside className="border-r border-slate-200 bg-slate-50 p-5">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Fiches profils</p>
                                    <h3 className="font-black text-slate-900">Rôles actifs</h3>
                                </div>
                                <span className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-[10px] font-black text-slate-500">{roles.length}</span>
                            </div>
                            <div className="space-y-2 max-h-[430px] overflow-y-auto pr-1">
                                {roles.map(role => {
                                    const preset = ROLE_PRESETS.find(item => item.name === role.name) || ROLE_FALLBACKS[role.name];
                                    const roleUsers = users.filter(user => user.role === role.name).length;
                                    return (
                                        <button
                                            key={role.id}
                                            type="button"
                                            onClick={() => setSelectedRoleName(role.name)}
                                            className={`w-full text-left rounded-2xl border p-4 transition-all ${selectedRole.name === role.name ? 'bg-slate-900 border-slate-900 text-white shadow-md' : 'bg-white border-slate-200 text-slate-700 hover:border-blue-200 hover:text-blue-700'}`}
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    <p className="font-black">{preset?.label || role.name}</p>
                                                    <p className={`text-[10px] font-black uppercase tracking-widest mt-1 ${selectedRole.name === role.name ? 'text-white/50' : 'text-slate-400'}`}>{preset?.scope || 'Personnalisé'}</p>
                                                </div>
                                                <span className={`px-2 py-1 rounded-lg text-[10px] font-black ${selectedRole.name === role.name ? 'bg-white/10 text-white' : 'bg-slate-100 text-slate-500'}`}>
                                                    {roleUsers} user
                                                </span>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </aside>

                        <section className="p-6 lg:p-8 space-y-6">
                            <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                                <div>
                                    <p className="text-[11px] font-black uppercase tracking-widest text-blue-500">Fiche rôle</p>
                                    <h2 className="text-3xl font-black text-slate-900 mt-1">{selectedPreset?.label || selectedRole.name}</h2>
                                    <p className="text-sm font-semibold text-slate-500 mt-2 max-w-2xl">
                                        {selectedPreset?.description || selectedRole.description || 'Profil personnalisé. Vérifiez les permissions avant de l’affecter à un utilisateur.'}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {selectedPreset && !['ADMIN', 'SUPER_ADMIN'].includes(selectedRole.name) && (
                                        <button
                                            type="button"
                                            onClick={() => applyPreset(selectedPreset)}
                                            disabled={applyingPreset === selectedPreset.name}
                                            className="px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 text-white text-sm font-black inline-flex items-center gap-2"
                                        >
                                            <Settings2 className="w-4 h-4" />
                                            Remettre à niveau
                                        </button>
                                    )}
                                    {!['ADMIN', 'SUPER_ADMIN'].includes(selectedRole.name) && (
                                        <button
                                            type="button"
                                            onClick={() => deleteRole(selectedRole.id)}
                                            className="px-4 py-3 rounded-xl border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-sm font-black inline-flex items-center gap-2"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                            Supprimer
                                        </button>
                                    )}
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <RoleMetric icon={ShieldCheck} label="Permissions actives" value={isBuiltinFullAccess ? 'Toutes' : selectedPermissions.length} />
                                <RoleMetric icon={Users} label="Utilisateurs rattachés" value={selectedUsers.length} />
                                <RoleMetric icon={Eye} label="Périmètre métier" value={selectedPreset?.scope || 'Custom'} />
                            </div>

                            <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5">
                                <div className="rounded-2xl border border-slate-200 overflow-hidden">
                                    <div className="px-5 py-4 bg-slate-50 border-b border-slate-200">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Ce profil peut faire</p>
                                        <h3 className="font-black text-slate-900">Droits par domaine</h3>
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {isBuiltinFullAccess ? (
                                            <div className="p-5 bg-emerald-50 text-emerald-800 font-bold">
                                                Ce profil dispose d’un accès complet automatiquement. La matrice ne limite pas ce rôle.
                                            </div>
                                        ) : Object.keys(selectedGroupedPermissions).length > 0 ? (
                                            Object.entries(selectedGroupedPermissions).map(([moduleName, modulePermissions]) => (
                                                <div key={moduleName} className="p-5">
                                                    <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-2 mb-3">
                                                        <div>
                                                            <h4 className="font-black text-slate-900">{moduleName}</h4>
                                                            <p className="text-xs font-semibold text-slate-500">{MODULE_PURPOSES[moduleName] || 'Actions autorisées sur ce domaine.'}</p>
                                                        </div>
                                                        <span className="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-500 text-[10px] font-black uppercase">{modulePermissions.length} droit(s)</span>
                                                    </div>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                        {modulePermissions.map(permission => (
                                                            <div key={permission.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                                <p className="text-sm font-black text-slate-800">{permission.description}</p>
                                                                <p className="text-[11px] font-mono text-slate-400 mt-1">{permission.code}</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            ))
                                        ) : (
                                            <div className="p-8 text-center text-slate-400 font-bold">Aucune permission affectée à ce profil.</div>
                                        )}
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-slate-200 overflow-hidden self-start">
                                    <div className="px-5 py-4 bg-slate-50 border-b border-slate-200">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Utilisateurs</p>
                                        <h3 className="font-black text-slate-900">Qui utilise ce profil</h3>
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {selectedUsers.length > 0 ? selectedUsers.map(user => (
                                            <div key={user.id} className="p-4 flex items-center gap-3">
                                                <div className="w-9 h-9 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-black">
                                                    {(user.first_name || user.username || '?').charAt(0).toUpperCase()}
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="font-black text-sm text-slate-900 truncate">{`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username}</p>
                                                    <p className="text-xs font-semibold text-slate-400 truncate">{user.username}</p>
                                                </div>
                                            </div>
                                        )) : (
                                            <div className="p-6 text-sm font-bold text-slate-400 text-center">
                                                Aucun utilisateur n’utilise encore ce profil.
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {!isBuiltinFullAccess && selectedPreset && (
                                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-bold text-amber-800">
                                    Modèle recommandé : {selectedPreset.permissions.length} permission(s). Permissions actuellement actives : {selectedPermissions.length}.
                                    {selectedPreset.permissions.some(code => !selectedPermissionCodes.has(code)) && ' Ce profil diffère du modèle recommandé.'}
                                </div>
                            )}
                        </section>
                    </div>
                </div>
            )}

            <div className="bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden">
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
                                    {!['ADMIN', 'SUPER_ADMIN'].includes(role.name) && (
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
                                            const isAdmin = ['ADMIN', 'SUPER_ADMIN'].includes(role.name);
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
                <p>Attention : Les utilisateurs "ADMIN" et "SUPER_ADMIN" reçoivent techniquement toutes les permissions par défaut. Cette matrice s'applique immédiatement aux autres rôles dès qu'ils se reconnectent.</p>
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
        </div>
    );
}

function RoleMetric({ icon: Icon, label, value }) {
    return (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
                    <p className="text-2xl font-black text-slate-900 mt-1">{value}</p>
                </div>
                <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 text-blue-600 flex items-center justify-center">
                    <Icon className="w-5 h-5" />
                </div>
            </div>
        </div>
    );
}
