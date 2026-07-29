import React, { useState, useEffect } from 'react';
import { ShieldCheck, ShieldAlert, Check, Plus, Trash2, X, Users, Eye, Settings2, Mail, KeyRound } from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import { userHasAnyRole } from '../utils/roleNavigation';

const ROLE_PRESETS = [
    {
        name: 'MAGASINIER',
        label: 'Magasinier',
        description: 'Réceptionne, range, transfère et compte le stock.',
        scope: 'Stock',
        permissions: ['STOCK_VIEW', 'stock.receive', 'stock.transfer', 'inventory.count', 'purchases.request', 'purchases.receive', 'PLANNING_VIEW'],
    },
    {
        name: 'CHEF_STOCK',
        label: 'Chef stock',
        description: 'Pilote le stock, les inventaires, les corrections et le catalogue.',
        scope: 'Stock',
        permissions: ['STOCK_VIEW', 'STOCK_EDIT', 'stock.receive', 'stock.transfer', 'stock.adjust', 'stock.locations.manage', 'catalog.qualify', 'workshop.reserve_stock', 'workshop.consume_stock', 'inventory.count', 'inventory.validate', 'purchases.request', 'purchases.approve', 'purchases.order', 'purchases.receive', 'PLANNING_VIEW', 'PLANNING_EDIT'],
    },
    {
        name: 'DEBIT_OPERATOR',
        label: 'Débit atelier',
        description: 'Confirme le débit réel depuis les réservations atelier.',
        scope: 'Atelier',
        permissions: ['PROD_VIEW', 'planning:start', 'planning:pause', 'planning:stop', 'planning:consume_stock', 'workshop.consume_stock', 'planning:report_issue', 'PLANNING_VIEW'],
    },
    {
        name: 'WORKSHOP_LEAD',
        label: 'Chef atelier',
        description: 'Pilote les postes, priorités, blocages et débits atelier.',
        scope: 'Atelier',
        permissions: ['PROD_VIEW', 'PROD_EDIT', 'planning:start', 'planning:pause', 'planning:stop', 'planning:consume_stock', 'planning:reprioritize', 'planning:assign', 'planning:unblock', 'planning:report_issue', 'quality:reject', 'STOCK_VIEW', 'stock.receive', 'stock.transfer', 'workshop.reserve_stock', 'workshop.consume_stock', 'inventory.count', 'PLANNING_VIEW', 'PLANNING_EDIT', 'PLANNING_AVAILABILITY_MANAGE', 'PLANNING_ABSENCE_APPROVE', 'PLANNING_RESOURCE_MANAGE'],
    },
    {
        name: 'ACHATS',
        label: 'Achats',
        description: 'Suit les commandes fournisseurs et les réceptions attendues.',
        scope: 'Achats',
        permissions: ['STOCK_VIEW', 'PURCHASES_VIEW', 'purchases.request', 'purchases.approve', 'purchases.order', 'purchases.receive', 'purchases.invoice.manage', 'purchases.payments.manage', 'PLANNING_VIEW'],
    },
    {
        name: 'SALES',
        label: 'Commercial CRM',
        description: 'Gère les clients, propositions, devis et avant-vente.',
        scope: 'Ventes',
        permissions: ['SALES_VIEW', 'SALES_EDIT', 'PLANNING_VIEW', 'PLANNING_EDIT'],
    },
    {
        name: 'TECHNICO_COMMERCIAL',
        label: 'Technico-commercial',
        description: 'Pilote le cycle commercial et les dossiers du bureau d’études, avec consultation et réservation du stock.',
        scope: 'Commerce + BE',
        permissions: ['SALES_VIEW', 'SALES_EDIT', 'STOCK_VIEW', 'workshop.reserve_stock', 'PLANNING_VIEW', 'PLANNING_EDIT'],
    },
    {
        name: 'FINANCE',
        label: 'Comptable / Finance',
        description: 'Suit les factures clients et fournisseurs, encaissements, paiements, avoirs et exports comptables.',
        scope: 'Finance',
        permissions: ['ACC_VIEW', 'ACC_EDIT', 'SALES_VIEW', 'PURCHASES_VIEW', 'purchases.invoice.manage', 'purchases.payments.manage', 'PLANNING_VIEW'],
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
    'Planning & Agenda': 'Agenda transverse, affectations, métrés, atelier et livraisons.',
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
    const { user } = useAuth();
    const canManagePermissions = userHasAnyRole(user, ['ADMIN', 'SUPER_ADMIN']);
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [users, setUsers] = useState([]);
    const [stations, setStations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showRoleModal, setShowRoleModal] = useState(false);
    const [newRoleForm, setNewRoleForm] = useState({ name: '', description: '' });
    const emptyUserForm = {
        accessType: 'ATELIER',
        username: '',
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        job_title: '',
        team: '',
        role: 'MAGASINIER',
        additional_roles: [],
        access_mode: 'PIN',
        pin: '',
        station_codes: [],
        send_invite: false,
    };
    const [newUserForm, setNewUserForm] = useState(emptyUserForm);
    const [createdAccess, setCreatedAccess] = useState(null);
    const [applyingPreset, setApplyingPreset] = useState(null);
    const [selectedRoleName, setSelectedRoleName] = useState('MAGASINIER');
    const [rbacView, setRbacView] = useState('overview');

    const fetchData = async () => {
        try {
            const [rolesRes, permsRes, usersRes, stationsRes] = await Promise.all([
                api.get('/v2/config/roles'),
                api.get('/v2/config/permissions'),
                api.get('/v2/config/users'),
                api.get('/v2/config/stations')
            ]);
            setRoles(rolesRes.data);
            setPermissions(permsRes.data);
            setUsers(usersRes.data);
            setStations(stationsRes.data);
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

    const setAccessType = (accessType) => {
        const isAtelier = accessType === 'ATELIER';
        setNewUserForm({
            ...newUserForm,
            accessType,
            role: isAtelier ? 'MAGASINIER' : 'SALES',
            additional_roles: [],
            access_mode: isAtelier ? 'PIN' : 'EMAIL',
            send_invite: !isAtelier,
            station_codes: isAtelier ? newUserForm.station_codes : [],
        });
    };

    const toggleStation = (code) => {
        const current = new Set(newUserForm.station_codes || []);
        if (current.has(code)) current.delete(code);
        else current.add(code);
        setNewUserForm({...newUserForm, station_codes: Array.from(current)});
    };

    const toggleAdditionalRole = (roleName) => {
        const current = new Set(newUserForm.additional_roles || []);
        if (current.has(roleName)) current.delete(roleName);
        else current.add(roleName);
        current.delete(newUserForm.role);
        setNewUserForm({...newUserForm, additional_roles: Array.from(current)});
    };

    const submitNewUser = async () => {
        if (!newUserForm.username || !newUserForm.role) return;
        try {
            const payload = {
                username: newUserForm.username.trim(),
                first_name: newUserForm.first_name.trim() || null,
                last_name: newUserForm.last_name.trim() || null,
                email: newUserForm.email.trim() || null,
                phone: newUserForm.phone.trim() || null,
                job_title: newUserForm.job_title.trim() || null,
                team: newUserForm.team.trim() || null,
                role: newUserForm.role,
                additional_roles: (newUserForm.additional_roles || []).filter(roleName => roleName !== newUserForm.role),
                access_mode: newUserForm.access_mode,
                pin: newUserForm.pin.trim() || null,
                station_codes: newUserForm.station_codes || [],
                send_invite: Boolean(newUserForm.send_invite),
            };
            const res = await api.post('/v2/config/users', payload);
            setCreatedAccess(res.data);
            setNewUserForm(emptyUserForm);
            await fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Impossible de créer l'utilisateur.");
        }
    };

    const resendInvite = async (userId) => {
        try {
            const res = await api.post(`/v2/config/users/${userId}/invite`);
            setCreatedAccess(res.data);
            await fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Impossible d'envoyer l'invitation.");
        }
    };

    const updateUserAdditionalRoles = async (user, additionalRoles) => {
        try {
            await api.put(`/v2/config/users/${user.id}`, {
                additional_roles: Array.from(new Set(additionalRoles)).filter(roleName => roleName && roleName !== user.role),
            });
            await fetchData();
        } catch (e) {
            alert(e.response?.data?.detail || "Impossible de mettre à jour les rôles de l'utilisateur.");
        }
    };

    const addRoleToUser = (user, roleName) => {
        if (!roleName || user.role === roleName || (user.additional_roles || []).includes(roleName)) return;
        updateUserAdditionalRoles(user, [...(user.additional_roles || []), roleName]);
    };

    const removeRoleFromUser = (user, roleName) => {
        if (user.role === roleName) {
            alert("Ce profil est le rôle principal de l'utilisateur. Changez d'abord son rôle principal pour le retirer.");
            return;
        }
        updateUserAdditionalRoles(user, (user.additional_roles || []).filter(item => item !== roleName));
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
    const userHasRole = (user, roleName) => user?.role === roleName || (user?.additional_roles || []).includes(roleName);
    const selectedUsers = users.filter(user => userHasRole(user, selectedRole?.name));
    const assignableUsers = users.filter(user => selectedRole?.name && !userHasRole(user, selectedRole.name));
    const selectedGroupedPermissions = selectedPermissions.reduce((acc, permission) => {
        if (!acc[permission.module]) acc[permission.module] = [];
        acc[permission.module].push(permission);
        return acc;
    }, {});
    const isBuiltinFullAccess = ['ADMIN', 'SUPER_ADMIN'].includes(selectedRole?.name);
    const inputClass = "w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500";
    const pendingInvitations = users.filter(user => ['PENDING', 'INVITED'].includes(user.invitation_status)).length;
    const atelierUsers = users.filter(user => ['PIN', 'HYBRID'].includes(user.access_mode)).length;
    const rbacViews = [
        { id: 'overview', label: "Vue d'ensemble", helper: 'Modèles et état global', icon: Eye },
        { id: 'users', label: 'Utilisateurs', helper: 'Comptes, PIN, invitations', icon: Users },
        { id: 'profiles', label: 'Profils métier', helper: 'Qui peut faire quoi', icon: ShieldCheck },
        { id: 'matrix', label: 'Matrice avancée des droits', helper: 'Voir et modifier les permissions fines', icon: Settings2 },
    ];

    return (
        <div className="min-w-0 space-y-5 font-sans">
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                <div className="flex flex-col gap-4 border-b border-slate-100 p-4 sm:p-5 2xl:flex-row 2xl:items-center 2xl:justify-between">
                    <div>
                        <p className="text-[11px] font-black uppercase tracking-widest text-blue-500">Accès plateforme</p>
                        <h2 className="mt-1 text-xl font-black text-slate-900">Gestion des accès</h2>
                    </div>
                    <div className="grid w-full grid-cols-3 gap-2 2xl:w-auto 2xl:min-w-[390px]">
                        <RoleMetric icon={Users} label="Utilisateurs" value={users.length} />
                        <RoleMetric icon={ShieldCheck} label="Profils" value={roles.length} />
                        <RoleMetric icon={Mail} label="Invitations" value={pendingInvitations} />
                    </div>
                </div>
                <div className="border-b border-slate-200 bg-slate-50 p-2">
                    <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
                        {rbacViews.map(view => {
                            const Icon = view.icon;
                            const active = rbacView === view.id;
                            return (
                                <button
                                    key={view.id}
                                    type="button"
                                    onClick={() => setRbacView(view.id)}
                                    className={`flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2.5 text-left transition-colors ${active ? 'bg-slate-900 border-slate-900 text-white' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-200 hover:text-blue-700'}`}
                                >
                                    <Icon className="h-4 w-4 shrink-0" />
                                    <span className="min-w-0">
                                        <span className="block text-sm font-black">{view.label}</span>
                                        <span className={`hidden truncate text-[11px] font-bold 2xl:block ${active ? 'text-white/60' : 'text-slate-400'}`}>
                                            {view.helper}
                                        </span>
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>

            {rbacView === 'overview' && (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                        <RoleMetric icon={KeyRound} label="Accès atelier" value={atelierUsers} />
                        <RoleMetric icon={Mail} label="Invitations en attente" value={pendingInvitations} />
                        <RoleMetric icon={ShieldAlert} label="Rôles personnalisés" value={roles.filter(role => !ROLE_PRESETS.some(preset => preset.name === role.name) && !ROLE_FALLBACKS[role.name]).length} />
                        <RoleMetric icon={Settings2} label="Permissions" value={permissions.length} />
                    </div>

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
                                disabled={!canManagePermissions || applyingPreset === preset.name}
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
                </>
            )}

            {rbacView === 'users' && (
            <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-6 border-b border-slate-100 flex flex-col xl:flex-row xl:items-end xl:justify-between gap-4">
                    <div>
                        <p className="text-[11px] font-black uppercase tracking-widest text-emerald-500">Création utilisateur</p>
                        <h2 className="text-2xl font-black text-slate-900 mt-1">Créer un accès exploitable</h2>
                        <p className="text-sm font-semibold text-slate-500 mt-1">
                            Choisissez d'abord le contexte d'usage, puis le profil métier. Les permissions viennent du rôle.
                        </p>
                    </div>
                    <div className="flex rounded-2xl border border-slate-200 bg-slate-50 p-1">
                        {[
                            ['ATELIER', 'Rapide atelier'],
                            ['BUREAU', 'Bureau / email'],
                        ].map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                onClick={() => setAccessType(value)}
                                className={`px-4 py-2 rounded-xl text-sm font-black ${newUserForm.accessType === value ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-white'}`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="p-6 grid grid-cols-1 2xl:grid-cols-[1fr_360px] gap-6">
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                        <Field label="Identifiant">
                            <input value={newUserForm.username} onChange={e => setNewUserForm({...newUserForm, username: e.target.value})} className={inputClass} placeholder="ex: jdupont" />
                        </Field>
                        <Field label="Prénom">
                            <input value={newUserForm.first_name} onChange={e => setNewUserForm({...newUserForm, first_name: e.target.value})} className={inputClass} placeholder="Jean" />
                        </Field>
                        <Field label="Nom">
                            <input value={newUserForm.last_name} onChange={e => setNewUserForm({...newUserForm, last_name: e.target.value})} className={inputClass} placeholder="Dupont" />
                        </Field>
                        <Field label="Profil métier">
                            <select value={newUserForm.role} onChange={e => setNewUserForm({...newUserForm, role: e.target.value, additional_roles: (newUserForm.additional_roles || []).filter(roleName => roleName !== e.target.value)})} className={inputClass}>
                                {roles.map(role => {
                                    const preset = ROLE_PRESETS.find(item => item.name === role.name) || ROLE_FALLBACKS[role.name];
                                    return <option key={role.id} value={role.name}>{preset?.label || role.name}</option>;
                                })}
                            </select>
                        </Field>
                        <Field label="Mode d'accès">
                            <select value={newUserForm.access_mode} onChange={e => setNewUserForm({...newUserForm, access_mode: e.target.value})} className={inputClass}>
                                <option value="PIN">PIN atelier</option>
                                <option value="EMAIL">Email / invitation</option>
                                <option value="HYBRID">PIN + email</option>
                            </select>
                        </Field>
                        <Field label={newUserForm.access_mode === 'PIN' ? 'PIN temporaire' : 'Mot de passe temporaire'}>
                            <input value={newUserForm.pin} onChange={e => setNewUserForm({...newUserForm, pin: e.target.value})} className={inputClass} placeholder={newUserForm.access_mode === 'PIN' ? 'Auto si vide' : 'Auto si vide'} />
                        </Field>
                        <Field label="Email">
                            <input value={newUserForm.email} onChange={e => setNewUserForm({...newUserForm, email: e.target.value})} className={inputClass} placeholder="nom@entreprise.com" />
                        </Field>
                        <Field label="Téléphone">
                            <input value={newUserForm.phone} onChange={e => setNewUserForm({...newUserForm, phone: e.target.value})} className={inputClass} placeholder="+33..." />
                        </Field>
                        <Field label="Poste / équipe">
                            <input value={newUserForm.job_title} onChange={e => setNewUserForm({...newUserForm, job_title: e.target.value})} className={inputClass} placeholder="Magasinier, achats..." />
                        </Field>
                        <div className="lg:col-span-3 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mb-3">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Rôles complémentaires</p>
                                    <h3 className="font-black text-slate-900">Ajouter des casquettes métier</h3>
                                </div>
                                <p className="text-xs font-bold text-slate-500">Le rôle principal garde l’écran d’accueil.</p>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
                                {roles.filter(role => role.name !== newUserForm.role).map(role => {
                                    const preset = ROLE_PRESETS.find(item => item.name === role.name) || ROLE_FALLBACKS[role.name];
                                    const checked = (newUserForm.additional_roles || []).includes(role.name);
                                    return (
                                        <label
                                            key={role.id}
                                            className={`rounded-xl border px-3 py-2 flex items-start gap-3 cursor-pointer ${checked ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-100'}`}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={checked}
                                                onChange={() => toggleAdditionalRole(role.name)}
                                                className="mt-1"
                                            />
                                            <span>
                                                <span className="block text-sm font-black">{preset?.label || role.name}</span>
                                                <span className="block text-[11px] font-bold text-slate-400">{preset?.scope || 'Custom'}</span>
                                            </span>
                                        </label>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    <aside className="rounded-2xl border border-slate-200 bg-slate-50 p-5 space-y-4">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Accès atelier</p>
                            <h3 className="font-black text-slate-900">Stations autorisées</h3>
                        </div>
                        <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto pr-1">
                            {stations.map(station => (
                                <label key={station.code} className={`rounded-xl border px-3 py-2 flex items-center gap-3 cursor-pointer ${newUserForm.station_codes.includes(station.code) ? 'bg-blue-50 border-blue-200 text-blue-700' : 'bg-white border-slate-200 text-slate-600'}`}>
                                    <input
                                        type="checkbox"
                                        checked={newUserForm.station_codes.includes(station.code)}
                                        onChange={() => toggleStation(station.code)}
                                    />
                                    <span className="text-sm font-black">{station.display_name}</span>
                                </label>
                            ))}
                            {stations.length === 0 && <p className="text-sm font-bold text-slate-400">Aucune station configurée.</p>}
                        </div>
                        <label className="rounded-xl border border-slate-200 bg-white p-3 flex items-start gap-3 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={newUserForm.send_invite}
                                onChange={e => setNewUserForm({...newUserForm, send_invite: e.target.checked, access_mode: e.target.checked && newUserForm.access_mode === 'PIN' ? 'HYBRID' : newUserForm.access_mode})}
                            />
                            <span>
                                <span className="block text-sm font-black text-slate-900">Envoyer une invitation email</span>
                                <span className="block text-xs font-semibold text-slate-500 mt-1">Best-effort : la création réussit même si SMTP n'est pas configuré.</span>
                            </span>
                        </label>
                        <button onClick={submitNewUser} disabled={!newUserForm.username || !newUserForm.role} className="w-full py-4 rounded-xl bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-500 text-white font-black shadow-sm inline-flex justify-center items-center gap-2">
                            <Plus className="w-4 h-4" /> Créer l'utilisateur
                        </button>
                    </aside>
                </div>

                {createdAccess && (
                    <div className="mx-6 mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5 grid grid-cols-1 xl:grid-cols-[1fr_auto] gap-4">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Accès créé</p>
                            <h3 className="text-xl font-black text-emerald-950">{createdAccess.user?.username}</h3>
                            <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                                {createdAccess.temporary_pin && (
                                    <InfoPill icon={KeyRound} label="PIN / secret temporaire" value={createdAccess.temporary_pin} />
                                )}
                                {createdAccess.invitation_link && (
                                    <InfoPill icon={Mail} label="Lien invitation" value={createdAccess.invitation_link} />
                                )}
                                <InfoPill icon={ShieldCheck} label="Statut invitation" value={createdAccess.user?.invitation_status || 'ACTIVE'} />
                            </div>
                            <p className="text-sm font-bold text-emerald-800 mt-3">{createdAccess.message}</p>
                        </div>
                        <button onClick={() => setCreatedAccess(null)} className="self-start px-4 py-3 rounded-xl border border-emerald-200 bg-white text-emerald-700 font-black">
                            Masquer
                        </button>
                    </div>
                )}
            </div>
            )}

            {rbacView === 'profiles' && selectedRole && (
                <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
                    <div className="grid min-h-[520px] grid-cols-1 2xl:grid-cols-[280px_minmax(0,1fr)]">
                        <aside className="border-b border-slate-200 bg-slate-50 p-4 2xl:border-b-0 2xl:border-r">
                            <div className="flex items-center justify-between mb-4">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Fiches profils</p>
                                    <h3 className="font-black text-slate-900">Rôles actifs</h3>
                                </div>
                                <span className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-[10px] font-black text-slate-500">{roles.length}</span>
                            </div>
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 2xl:max-h-[620px] 2xl:grid-cols-1 2xl:overflow-y-auto 2xl:pr-1">
                                {roles.map(role => {
                                    const preset = ROLE_PRESETS.find(item => item.name === role.name) || ROLE_FALLBACKS[role.name];
                                    const roleUsers = users.filter(user => userHasRole(user, role.name)).length;
                                    return (
                                        <button
                                            key={role.id}
                                            type="button"
                                            onClick={() => setSelectedRoleName(role.name)}
                                            className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedRole.name === role.name ? 'bg-slate-900 border-slate-900 text-white' : 'bg-white border-slate-200 text-slate-700 hover:border-blue-200 hover:text-blue-700'}`}
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

                        <section className="min-w-0 space-y-5 p-4 sm:p-6 xl:p-7">
                            <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                                <div>
                                    <p className="text-[11px] font-black uppercase tracking-widest text-blue-500">Fiche rôle</p>
                                    <h2 className="text-3xl font-black text-slate-900 mt-1">{selectedPreset?.label || selectedRole.name}</h2>
                                    <p className="text-sm font-semibold text-slate-500 mt-2 max-w-2xl">
                                        {selectedPreset?.description || selectedRole.description || 'Profil personnalisé. Vérifiez les permissions avant de l’affecter à un utilisateur.'}
                                    </p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {canManagePermissions && selectedPreset && !['ADMIN', 'SUPER_ADMIN'].includes(selectedRole.name) && (
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
                                    {canManagePermissions && !['ADMIN', 'SUPER_ADMIN'].includes(selectedRole.name) && (
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

                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                                <RoleMetric icon={ShieldCheck} label="Permissions actives" value={isBuiltinFullAccess ? 'Toutes' : selectedPermissions.length} />
                                <RoleMetric icon={Users} label="Utilisateurs rattachés" value={selectedUsers.length} />
                                <RoleMetric icon={Eye} label="Périmètre métier" value={selectedPreset?.scope || 'Custom'} />
                            </div>

                            <div className="grid min-w-0 grid-cols-1 gap-5 2xl:grid-cols-[minmax(0,1fr)_340px]">
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
                                    {assignableUsers.length > 0 && (
                                        <div className="p-4 border-b border-slate-100 bg-white">
                                            <select
                                                value=""
                                                onChange={e => {
                                                    const user = users.find(item => item.id === Number(e.target.value));
                                                    if (user) addRoleToUser(user, selectedRole.name);
                                                }}
                                                className="w-full px-3 py-3 rounded-xl border border-slate-200 bg-slate-50 text-sm font-bold text-slate-700"
                                            >
                                                <option value="">Ajouter ce profil à un utilisateur...</option>
                                                {assignableUsers.map(user => (
                                                    <option key={user.id} value={user.id}>
                                                        {`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username} - rôle principal {user.role}
                                                    </option>
                                                ))}
                                            </select>
                                            <p className="text-[11px] font-semibold text-slate-400 mt-2">
                                                Ajoute ce profil comme rôle complémentaire. Le rôle principal garde l'écran d'accueil.
                                            </p>
                                        </div>
                                    )}
                                    <div className="divide-y divide-slate-100">
                                        {selectedUsers.length > 0 ? selectedUsers.map(user => (
                                            <div key={user.id} className="p-4 flex items-center gap-3">
                                                <div className="w-9 h-9 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-black">
                                                    {(user.first_name || user.username || '?').charAt(0).toUpperCase()}
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <p className="font-black text-sm text-slate-900 truncate">{`${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username}</p>
                                                    <p className="text-xs font-semibold text-slate-400 truncate">
                                                        {user.username} · {user.access_mode || 'PIN'} · {user.invitation_status || 'ACTIVE'}
                                                    </p>
                                                    {user.additional_roles?.length > 0 && (
                                                        <p className="mt-1 text-[11px] font-bold text-blue-600 truncate">
                                                            + {user.additional_roles.join(', ')}
                                                        </p>
                                                    )}
                                                    <p className="mt-1">
                                                        <span className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase ${user.role === selectedRole.name ? 'bg-slate-900 text-white' : 'bg-blue-50 text-blue-700'}`}>
                                                            {user.role === selectedRole.name ? 'Principal' : 'Complémentaire'}
                                                        </span>
                                                    </p>
                                                </div>
                                                <div className="flex flex-col gap-2">
                                                    {user.email && (
                                                        <button
                                                            type="button"
                                                            onClick={() => resendInvite(user.id)}
                                                            className="px-3 py-2 rounded-xl border border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-100 text-xs font-black inline-flex items-center gap-1"
                                                        >
                                                            <Mail className="w-3.5 h-3.5" />
                                                            Inviter
                                                        </button>
                                                    )}
                                                    {user.role !== selectedRole.name && (
                                                        <button
                                                            type="button"
                                                            onClick={() => removeRoleFromUser(user, selectedRole.name)}
                                                            className="px-3 py-2 rounded-xl border border-red-100 bg-red-50 text-red-700 hover:bg-red-100 text-xs font-black"
                                                        >
                                                            Retirer
                                                        </button>
                                                    )}
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

            {rbacView === 'matrix' && (
            <div className="bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden">
            {!canManagePermissions && (
                <div className="px-6 py-4 border-b border-amber-200 bg-amber-50 text-amber-800 text-sm font-bold flex items-center gap-3">
                    <ShieldAlert className="w-5 h-5 shrink-0" />
                    Lecture seule : seul un administrateur peut modifier les profils et les permissions.
                </div>
            )}
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
                    <button disabled={!canManagePermissions} onClick={() => setShowRoleModal(true)} className="w-12 h-12 rounded-full border-4 border-slate-900 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed transition-colors flex items-center justify-center text-white" style={{zIndex: 0}}>
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
                                    {canManagePermissions && !['ADMIN', 'SUPER_ADMIN'].includes(role.name) && (
                                        <button onClick={() => deleteRole(role.id)} className="absolute top-2 right-2 text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    )}
                                </th>
                            ))}
                            <th className="p-4 text-center w-[120px]">
                                <button disabled={!canManagePermissions} onClick={() => setShowRoleModal(true)} className="text-xs font-bold bg-slate-800 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 mx-auto hover:bg-emerald-600 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors">
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
                                                        disabled={isAdmin || !canManagePermissions}
                                                        onClick={() => togglePermission(role.id, perm.id, hasPerm)}
                                                        className={`w-8 h-8 rounded-lg flex items-center justify-center mx-auto transition-all ${
                                                            hasPerm 
                                                                ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20' 
                                                                : 'bg-slate-100 text-slate-300 hover:bg-slate-200'
                                                        } ${isAdmin || !canManagePermissions ? 'opacity-50 cursor-not-allowed grayscale' : ''}`}
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
            )}
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

function Field({ label, children }) {
    return (
        <label className="block">
            <span className="block text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">{label}</span>
            {children}
        </label>
    );
}

function InfoPill({ icon: Icon, label, value }) {
    return (
        <div className="rounded-xl border border-emerald-200 bg-white p-3 min-w-0">
            <div className="flex items-center gap-2 text-emerald-700">
                <Icon className="w-4 h-4 shrink-0" />
                <p className="text-[10px] font-black uppercase tracking-widest truncate">{label}</p>
            </div>
            <p className="mt-1 text-sm font-black text-slate-900 break-all">{value}</p>
        </div>
    );
}
