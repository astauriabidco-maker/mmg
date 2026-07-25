import React, { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    CalendarOff,
    Check,
    Plus,
    Save,
    Settings2,
    Truck,
    UserRoundCheck,
    X,
} from 'lucide-react';
import api from '../services/api';

const toInputDateTime = (value) => {
    const date = new Date(value);
    const pad = (part) => String(part).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const initialResource = {
    code: '',
    name: '',
    resource_type: 'VEHICLE',
    capacity: 1,
    status: 'ACTIVE',
    timezone: 'Europe/Paris',
    is_active: true,
};

const initialClosure = () => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return {
        name: '',
        closure_type: 'PUBLIC_HOLIDAY',
        start_at: toInputDateTime(start),
        end_at: toInputDateTime(end),
        all_day: true,
        country_code: 'FR',
        scope_type: 'GLOBAL',
        affects_capacity: true,
    };
};

const initialUnavailability = () => {
    const start = new Date();
    start.setMinutes(0, 0, 0);
    const end = new Date(start);
    end.setHours(end.getHours() + 2);
    return {
        start_at: toInputDateTime(start),
        end_at: toInputDateTime(end),
        reason: '',
        unavailability_type: 'UNAVAILABLE',
    };
};

function FieldLabel({ children }) {
    return <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">{children}</span>;
}

export default function PlanningSettingsModal({ users = [], onClose, onChanged }) {
    const queryClient = useQueryClient();
    const [tab, setTab] = useState('skills');
    const [selectedUserId, setSelectedUserId] = useState(users[0]?.id ? String(users[0].id) : '');
    const [selectedSkills, setSelectedSkills] = useState({});
    const [resourceForm, setResourceForm] = useState(initialResource);
    const [selectedResourceId, setSelectedResourceId] = useState('');
    const [selectedResourceMembers, setSelectedResourceMembers] = useState({});
    const [unavailabilityForm, setUnavailabilityForm] = useState(initialUnavailability);
    const [closureForm, setClosureForm] = useState(initialClosure);

    const skillsQuery = useQuery({
        queryKey: ['planning-skills'],
        queryFn: async () => (await api.get('/v2/schedule/skills')).data,
    });
    const resourcesQuery = useQuery({
        queryKey: ['planning-resources'],
        queryFn: async () => (await api.get('/v2/schedule/resources')).data,
    });
    const closuresQuery = useQuery({
        queryKey: ['planning-closures'],
        queryFn: async () => (await api.get('/v2/schedule/closures')).data,
    });
    const resourceUnavailabilitiesQuery = useQuery({
        queryKey: ['planning-resource-unavailabilities', selectedResourceId],
        queryFn: async () => (
            await api.get(`/v2/schedule/resources/${selectedResourceId}/unavailabilities`)
        ).data,
        enabled: Boolean(selectedResourceId),
    });
    const userSkillsQuery = useQuery({
        queryKey: ['planning-user-skills', selectedUserId],
        queryFn: async () => (await api.get(`/v2/schedule/users/${selectedUserId}/skills`)).data,
        enabled: Boolean(selectedUserId),
    });

    useEffect(() => {
        const next = {};
        (userSkillsQuery.data || []).forEach((row) => {
            next[row.skill_id] = {
                enabled: true,
                level: row.level || 1,
                is_certified: Boolean(row.is_certified),
                valid_until: row.valid_until ? row.valid_until.slice(0, 10) : '',
            };
        });
        setSelectedSkills(next);
    }, [userSkillsQuery.data, selectedUserId]);
    useEffect(() => {
        if (!selectedResourceId && resourcesQuery.data?.length) {
            setSelectedResourceId(String(resourcesQuery.data[0].id));
        }
    }, [resourcesQuery.data, selectedResourceId]);
    useEffect(() => {
        const resource = (resourcesQuery.data || []).find(
            (item) => String(item.id) === String(selectedResourceId),
        );
        setSelectedResourceMembers(Object.fromEntries(
            (resource?.members || []).map((member) => [member.user_id, {
                enabled: true,
                is_lead: Boolean(member.is_lead),
            }]),
        ));
    }, [resourcesQuery.data, selectedResourceId]);

    const refresh = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['planning-skills'] }),
            queryClient.invalidateQueries({ queryKey: ['planning-resources'] }),
            queryClient.invalidateQueries({ queryKey: ['planning-closures'] }),
            queryClient.invalidateQueries({ queryKey: ['schedule-meta'] }),
        ]);
        onChanged?.();
    };
    const skillsMutation = useMutation({
        mutationFn: async () => api.put(`/v2/schedule/users/${selectedUserId}/skills`, {
            skills: Object.entries(selectedSkills)
                .filter(([, value]) => value.enabled)
                .map(([skillId, value]) => ({
                    skill_id: Number(skillId),
                    level: Number(value.level || 1),
                    is_certified: Boolean(value.is_certified),
                    valid_until: value.valid_until ? new Date(`${value.valid_until}T23:59:59`).toISOString() : null,
                })),
        }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ['planning-user-skills', selectedUserId] });
            onChanged?.();
        },
    });
    const resourceMutation = useMutation({
        mutationFn: async () => api.post('/v2/schedule/resources', {
            ...resourceForm,
            code: resourceForm.code.trim(),
            name: resourceForm.name.trim(),
            capacity: Number(resourceForm.capacity),
        }),
        onSuccess: async () => {
            setResourceForm(initialResource);
            await refresh();
        },
    });
    const resourceMembersMutation = useMutation({
        mutationFn: async () => api.put(`/v2/schedule/resources/${selectedResourceId}/members`, {
            members: Object.entries(selectedResourceMembers)
                .filter(([, value]) => value.enabled)
                .map(([userId, value]) => ({
                    user_id: Number(userId),
                    member_role: value.is_lead ? 'RESPONSABLE' : 'MEMBRE',
                    is_lead: Boolean(value.is_lead),
                })),
        }),
        onSuccess: refresh,
    });
    const unavailabilityMutation = useMutation({
        mutationFn: async () => api.post(
            `/v2/schedule/resources/${selectedResourceId}/unavailabilities`,
            {
                resource_id: Number(selectedResourceId),
                start_at: new Date(unavailabilityForm.start_at).toISOString(),
                end_at: new Date(unavailabilityForm.end_at).toISOString(),
                reason: unavailabilityForm.reason.trim(),
                unavailability_type: unavailabilityForm.unavailability_type,
            },
        ),
        onSuccess: async () => {
            setUnavailabilityForm(initialUnavailability());
            await queryClient.invalidateQueries({
                queryKey: ['planning-resource-unavailabilities', selectedResourceId],
            });
        },
    });
    const deleteUnavailabilityMutation = useMutation({
        mutationFn: async (id) => api.delete(`/v2/schedule/resources/unavailabilities/${id}`),
        onSuccess: () => queryClient.invalidateQueries({
            queryKey: ['planning-resource-unavailabilities', selectedResourceId],
        }),
    });
    const closureMutation = useMutation({
        mutationFn: async () => api.post('/v2/schedule/closures', {
            ...closureForm,
            name: closureForm.name.trim(),
            start_at: new Date(closureForm.start_at).toISOString(),
            end_at: new Date(closureForm.end_at).toISOString(),
        }),
        onSuccess: async () => {
            setClosureForm(initialClosure());
            await refresh();
        },
    });
    const deleteClosureMutation = useMutation({
        mutationFn: async (id) => api.delete(`/v2/schedule/closures/${id}`),
        onSuccess: refresh,
    });
    const error = skillsMutation.error
        || resourceMutation.error
        || resourceMembersMutation.error
        || unavailabilityMutation.error
        || deleteUnavailabilityMutation.error
        || closureMutation.error
        || deleteClosureMutation.error;

    const toggleSkill = (skillId) => setSelectedSkills((current) => ({
        ...current,
        [skillId]: {
            level: 1,
            is_certified: false,
            valid_until: '',
            ...current[skillId],
            enabled: !current[skillId]?.enabled,
        },
    }));
    const setSkill = (skillId, key, value) => setSelectedSkills((current) => ({
        ...current,
        [skillId]: { enabled: true, level: 1, is_certified: false, valid_until: '', ...current[skillId], [key]: value },
    }));
    const toggleResourceMember = (userId) => setSelectedResourceMembers((current) => ({
        ...current,
        [userId]: {
            is_lead: false,
            ...current[userId],
            enabled: !current[userId]?.enabled,
        },
    }));
    const setResourceLead = (userId, value) => setSelectedResourceMembers((current) => ({
        ...current,
        [userId]: { enabled: true, ...current[userId], is_lead: value },
    }));

    return (
        <div className="fixed inset-0 z-[140] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm">
            <div className="flex max-h-[94vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
                <header className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
                    <div>
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-blue-600"><Settings2 className="h-4 w-4" /> Paramètres planning</p>
                        <h2 className="mt-1 text-xl font-black text-slate-950">Compétences, ressources et fermetures</h2>
                    </div>
                    <button type="button" onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md hover:bg-slate-100" title="Fermer"><X className="h-5 w-5" /></button>
                </header>

                <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-slate-50 p-2">
                    {[
                        ['skills', UserRoundCheck, 'Compétences équipes'],
                        ['resources', Truck, 'Ressources'],
                        ['closures', CalendarOff, 'Fermetures'],
                    ].map(([key, Icon, label]) => (
                        <button key={key} type="button" onClick={() => setTab(key)} className={`flex h-10 shrink-0 items-center gap-2 rounded-md px-4 text-sm font-black ${tab === key ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-white'}`}>
                            <Icon className="h-4 w-4" /> {label}
                        </button>
                    ))}
                </nav>

                <div className="overflow-y-auto p-5">
                    {tab === 'skills' && (
                        <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
                            <aside className="rounded-md border border-slate-200 bg-slate-50 p-4">
                                <FieldLabel>Collaborateur</FieldLabel>
                                <select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)} className="field">
                                    {users.map((user) => <option key={user.id} value={user.id}>{user.name} · {user.role}</option>)}
                                </select>
                                <p className="mt-3 text-xs font-semibold leading-5 text-slate-500">Affectez les métiers, permis et habilitations réellement détenus. Une date expirée exclut automatiquement le collaborateur des suggestions.</p>
                            </aside>
                            <section className="rounded-md border border-slate-200">
                                <div className="grid gap-3 p-4 md:grid-cols-2 xl:grid-cols-3">
                                    {(skillsQuery.data || []).map((skill) => {
                                        const value = selectedSkills[skill.id] || {};
                                        return (
                                            <div key={skill.id} className={`rounded-md border p-3 ${value.enabled ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-white'}`}>
                                                <button type="button" onClick={() => toggleSkill(skill.id)} className="flex w-full items-start justify-between gap-3 text-left">
                                                    <div><p className="font-black text-slate-900">{skill.name}</p><p className="mt-0.5 text-[10px] font-bold uppercase text-slate-400">{skill.category}</p></div>
                                                    <span className={`grid h-6 w-6 place-items-center rounded border ${value.enabled ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300 text-transparent'}`}><Check className="h-4 w-4" /></span>
                                                </button>
                                                {value.enabled && (
                                                    <div className="mt-3 grid gap-2">
                                                        <label><FieldLabel>Niveau</FieldLabel><select value={value.level || 1} onChange={(event) => setSkill(skill.id, 'level', event.target.value)} className="field">{[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level}</option>)}</select></label>
                                                        <label className="flex items-center gap-2 text-xs font-bold text-slate-700"><input type="checkbox" checked={Boolean(value.is_certified)} onChange={(event) => setSkill(skill.id, 'is_certified', event.target.checked)} /> Certification contrôlée</label>
                                                        {skill.requires_expiry && <label><FieldLabel>Valide jusqu’au</FieldLabel><input type="date" value={value.valid_until || ''} onChange={(event) => setSkill(skill.id, 'valid_until', event.target.value)} className="field" /></label>}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className="flex justify-end border-t border-slate-200 bg-slate-50 p-4">
                                    <button type="button" onClick={() => skillsMutation.mutate()} disabled={!selectedUserId || skillsMutation.isPending} className="flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40"><Save className="h-4 w-4" /> Enregistrer les compétences</button>
                                </div>
                            </section>
                        </div>
                    )}

                    {tab === 'resources' && (
                        <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
                            <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
                                <h3 className="font-black text-slate-900">Nouvelle ressource</h3>
                                <div className="mt-4 grid gap-3">
                                    <label><FieldLabel>Type</FieldLabel><select value={resourceForm.resource_type} onChange={(event) => setResourceForm((current) => ({ ...current, resource_type: event.target.value }))} className="field"><option value="VEHICLE">Véhicule</option><option value="MACHINE">Machine</option><option value="STATION">Station</option><option value="TEAM">Équipe</option><option value="PAIR">Binôme</option></select></label>
                                    <label><FieldLabel>Code</FieldLabel><input value={resourceForm.code} onChange={(event) => setResourceForm((current) => ({ ...current, code: event.target.value }))} placeholder="VEH-01" className="field" /></label>
                                    <label><FieldLabel>Nom</FieldLabel><input value={resourceForm.name} onChange={(event) => setResourceForm((current) => ({ ...current, name: event.target.value }))} placeholder="Fourgon métreur 1" className="field" /></label>
                                    <button type="button" onClick={() => resourceMutation.mutate()} disabled={!resourceForm.code.trim() || !resourceForm.name.trim() || resourceMutation.isPending} className="flex h-10 items-center justify-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40"><Plus className="h-4 w-4" /> Ajouter la ressource</button>
                                </div>
                            </section>
                            <div className="grid gap-4">
                                <section className="rounded-md border border-slate-200">
                                    <div className="border-b border-slate-200 px-4 py-3"><h3 className="font-black text-slate-900">Ressources disponibles</h3></div>
                                    <div className="grid gap-2 p-3 sm:grid-cols-2">
                                    {(resourcesQuery.data || []).map((resource) => (
                                        <button
                                            key={resource.id}
                                            type="button"
                                            onClick={() => setSelectedResourceId(String(resource.id))}
                                            className={`flex items-center gap-3 rounded-md border px-3 py-3 text-left ${
                                                String(resource.id) === String(selectedResourceId)
                                                    ? 'border-blue-400 bg-blue-50'
                                                    : 'border-slate-200 bg-white'
                                            }`}
                                        >
                                            <div className="grid h-9 w-9 place-items-center rounded bg-slate-100 text-slate-600"><Truck className="h-4 w-4" /></div>
                                            <div className="min-w-0 flex-1"><p className="truncate font-black text-slate-900">{resource.name}</p><p className="text-xs font-bold text-slate-400">{resource.code} · {resource.resource_type}</p></div>
                                            <span className={`rounded px-2 py-1 text-[10px] font-black ${resource.status === 'ACTIVE' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{resource.status}</span>
                                        </button>
                                    ))}
                                    {!resourcesQuery.data?.length && <p className="p-8 text-center text-sm font-bold text-slate-400">Aucune ressource configurée.</p>}
                                    </div>
                                </section>

                                {selectedResourceId && (
                                    <section className="grid gap-4 rounded-md border border-slate-200 p-4 xl:grid-cols-2">
                                        <div>
                                            <div className="flex items-center justify-between gap-3">
                                                <div>
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Équipe ou binôme</p>
                                                    <h3 className="mt-1 font-black text-slate-900">Membres autorisés</h3>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => resourceMembersMutation.mutate()}
                                                    disabled={resourceMembersMutation.isPending}
                                                    className="flex h-9 items-center gap-2 rounded-md bg-slate-950 px-3 text-xs font-black text-white disabled:opacity-40"
                                                >
                                                    <Save className="h-4 w-4" /> Enregistrer
                                                </button>
                                            </div>
                                            <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
                                                {users.map((user) => {
                                                    const value = selectedResourceMembers[user.id] || {};
                                                    return (
                                                        <div key={user.id} className="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2">
                                                            <input type="checkbox" checked={Boolean(value.enabled)} onChange={() => toggleResourceMember(user.id)} />
                                                            <div className="min-w-0 flex-1"><p className="truncate text-sm font-black text-slate-900">{user.name}</p><p className="text-[10px] font-bold uppercase text-slate-400">{user.role}</p></div>
                                                            <label className="flex items-center gap-1 text-[10px] font-black text-slate-500">
                                                                <input type="checkbox" checked={Boolean(value.is_lead)} onChange={(event) => setResourceLead(user.id, event.target.checked)} disabled={!value.enabled} />
                                                                Responsable
                                                            </label>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>

                                        <div className="border-t border-slate-200 pt-4 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-amber-600">Disponibilité ressource</p>
                                            <h3 className="mt-1 font-black text-slate-900">Maintenance ou indisponibilité</h3>
                                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                                <input type="datetime-local" value={unavailabilityForm.start_at} onChange={(event) => setUnavailabilityForm((current) => ({ ...current, start_at: event.target.value }))} className="field" />
                                                <input type="datetime-local" value={unavailabilityForm.end_at} onChange={(event) => setUnavailabilityForm((current) => ({ ...current, end_at: event.target.value }))} className="field" />
                                                <input value={unavailabilityForm.reason} onChange={(event) => setUnavailabilityForm((current) => ({ ...current, reason: event.target.value }))} placeholder="Maintenance, panne, contrôle..." className="field sm:col-span-2" />
                                                <button type="button" onClick={() => unavailabilityMutation.mutate()} disabled={!unavailabilityForm.reason.trim() || unavailabilityMutation.isPending} className="flex h-10 items-center justify-center gap-2 rounded-md bg-amber-500 px-3 text-xs font-black text-white disabled:opacity-40 sm:col-span-2"><CalendarOff className="h-4 w-4" /> Bloquer la ressource</button>
                                            </div>
                                            <div className="mt-3 space-y-2">
                                                {(resourceUnavailabilitiesQuery.data || []).map((row) => (
                                                    <div key={row.id} className="flex items-center gap-2 rounded-md bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900">
                                                        <span className="min-w-0 flex-1">{row.reason} · {new Date(row.start_at).toLocaleString('fr-FR')} → {new Date(row.end_at).toLocaleString('fr-FR')}</span>
                                                        <button type="button" onClick={() => deleteUnavailabilityMutation.mutate(row.id)} className="grid h-7 w-7 shrink-0 place-items-center rounded border border-amber-200" title="Supprimer"><X className="h-3.5 w-3.5" /></button>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </section>
                                )}
                            </div>
                        </div>
                    )}

                    {tab === 'closures' && (
                        <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
                            <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
                                <h3 className="font-black text-slate-900">Jour férié ou fermeture</h3>
                                <div className="mt-4 grid gap-3">
                                    <label><FieldLabel>Libellé</FieldLabel><input value={closureForm.name} onChange={(event) => setClosureForm((current) => ({ ...current, name: event.target.value }))} placeholder="Fermeture estivale" className="field" /></label>
                                    <label><FieldLabel>Type</FieldLabel><select value={closureForm.closure_type} onChange={(event) => setClosureForm((current) => ({ ...current, closure_type: event.target.value }))} className="field"><option value="PUBLIC_HOLIDAY">Jour férié</option><option value="COLLECTIVE_CLOSURE">Fermeture collective</option><option value="MAINTENANCE">Maintenance</option></select></label>
                                    <label><FieldLabel>Début</FieldLabel><input type="datetime-local" value={closureForm.start_at} onChange={(event) => setClosureForm((current) => ({ ...current, start_at: event.target.value }))} className="field" /></label>
                                    <label><FieldLabel>Fin</FieldLabel><input type="datetime-local" value={closureForm.end_at} onChange={(event) => setClosureForm((current) => ({ ...current, end_at: event.target.value }))} className="field" /></label>
                                    <button type="button" onClick={() => closureMutation.mutate()} disabled={!closureForm.name.trim() || closureMutation.isPending} className="flex h-10 items-center justify-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40"><Plus className="h-4 w-4" /> Ajouter la fermeture</button>
                                </div>
                            </section>
                            <section className="rounded-md border border-slate-200">
                                <div className="border-b border-slate-200 px-4 py-3"><h3 className="font-black text-slate-900">Calendrier des fermetures</h3></div>
                                <div className="divide-y divide-slate-100">
                                    {(closuresQuery.data || []).map((closure) => (
                                        <div key={closure.id} className="flex items-center gap-3 px-4 py-3">
                                            <CalendarOff className="h-5 w-5 shrink-0 text-amber-600" />
                                            <div className="min-w-0 flex-1"><p className="font-black text-slate-900">{closure.name}</p><p className="text-xs font-semibold text-slate-500">{new Date(closure.start_at).toLocaleString('fr-FR')} → {new Date(closure.end_at).toLocaleString('fr-FR')}</p></div>
                                            <button type="button" onClick={() => deleteClosureMutation.mutate(closure.id)} className="grid h-9 w-9 place-items-center rounded-md border border-red-200 text-red-700" title="Supprimer"><X className="h-4 w-4" /></button>
                                        </div>
                                    ))}
                                    {!closuresQuery.data?.length && <p className="p-8 text-center text-sm font-bold text-slate-400">Aucune fermeture enregistrée.</p>}
                                </div>
                            </section>
                        </div>
                    )}

                    {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">{error.response?.data?.detail || 'La mise à jour a échoué.'}</div>}
                </div>
            </div>
        </div>
    );
}
