import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    BellRing,
    CheckCircle2,
    Clock3,
    ExternalLink,
    MessageSquare,
    ShieldAlert,
    UserRound,
    X,
} from 'lucide-react';
import api from '../services/api';
import {
    notifyPlanningIncidents,
    requestPlanningNotificationPermission,
} from '../services/planningDeviceNotifications';

const STATUS_META = {
    OPEN: { label: 'Ouvert', tone: 'bg-red-50 text-red-700 border-red-200' },
    ACKNOWLEDGED: { label: 'Pris en charge', tone: 'bg-blue-50 text-blue-700 border-blue-200' },
    RESOLVED: { label: 'Résolu', tone: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
};
const SEVERITY_META = {
    LOW: { label: 'Faible', tone: 'bg-slate-100 text-slate-700' },
    MEDIUM: { label: 'Modérée', tone: 'bg-amber-50 text-amber-700' },
    HIGH: { label: 'Élevée', tone: 'bg-orange-50 text-orange-700' },
    CRITICAL: { label: 'Critique', tone: 'bg-red-600 text-white' },
};
const ACTION_LABELS = {
    CREATED: 'Incident déclenché',
    ACKNOWLEDGED: 'Prise en charge',
    REASSIGNED: 'Réaffectation',
    COMMENTED: 'Commentaire',
    RESOLVED: 'Résolution manuelle',
    AUTO_RESOLVED: 'Résolution automatique',
    ESCALATED: 'Escalade',
};

const ageLabel = (value) => {
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} h`;
    return `${Math.floor(hours / 24)} j`;
};
const formatDateTime = (value) => value
    ? new Intl.DateTimeFormat('fr-FR', {
        dateStyle: 'short',
        timeStyle: 'short',
    }).format(new Date(value))
    : '—';
const mutationError = (...mutations) => {
    const error = mutations.find((mutation) => mutation.error)?.error;
    const detail = error?.response?.data?.detail;
    return typeof detail === 'string' ? detail : (error ? 'Action impossible.' : null);
};

export default function PlanningIncidentCenter({ users = [], onClose }) {
    const queryClient = useQueryClient();
    const [statusFilter, setStatusFilter] = useState('OPEN,ACKNOWLEDGED');
    const [severityFilter, setSeverityFilter] = useState('');
    const [selectedId, setSelectedId] = useState(null);
    const [comment, setComment] = useState('');
    const [managerId, setManagerId] = useState('');
    const [responsibleId, setResponsibleId] = useState('');
    const [notice, setNotice] = useState(null);
    const [devicePermission, setDevicePermission] = useState(
        typeof Notification !== 'undefined' ? Notification.permission : 'unsupported',
    );

    const incidentsQuery = useQuery({
        queryKey: ['planning-incidents', statusFilter, severityFilter],
        queryFn: async () => (await api.get('/v2/schedule/incidents', {
            params: {
                incident_status: statusFilter || undefined,
                severity: severityFilter || undefined,
            },
        })).data,
        refetchInterval: 60000,
    });
    const detailQuery = useQuery({
        queryKey: ['planning-incident', selectedId],
        queryFn: async () => (await api.get(`/v2/schedule/incidents/${selectedId}`)).data,
        enabled: Boolean(selectedId),
    });
    const incidents = incidentsQuery.data?.incidents || [];
    const selected = detailQuery.data;

    useEffect(() => {
        notifyPlanningIncidents(incidents);
    }, [incidents]);
    useEffect(() => {
        if (!selected) return;
        setManagerId(selected.assigned_manager_user_id ? String(selected.assigned_manager_user_id) : '');
        setResponsibleId(selected.responsible_user_id ? String(selected.responsible_user_id) : '');
    }, [selected]);

    const invalidate = () => {
        queryClient.invalidateQueries({ queryKey: ['planning-incidents'] });
        queryClient.invalidateQueries({ queryKey: ['planning-incident'] });
        queryClient.invalidateQueries({ queryKey: ['planning-notifications'] });
        queryClient.invalidateQueries({ queryKey: ['schedule-events'] });
    };
    const actionMutation = useMutation({
        mutationFn: async ({ action, payload = {} }) => (
            await api.post(`/v2/schedule/incidents/${selectedId}/${action}`, payload)
        ).data,
        onSuccess: (_, variables) => {
            setComment('');
            setNotice(
                variables.action === 'resolve'
                    ? 'Incident résolu.'
                    : variables.action === 'acknowledge'
                        ? 'Incident pris en charge.'
                        : 'Incident mis à jour.',
            );
            invalidate();
        },
    });
    const reassignMutation = useMutation({
        mutationFn: async (payload) => (
            await api.post(`/v2/schedule/incidents/${selectedId}/reassign`, payload)
        ).data,
        onSuccess: () => {
            setComment('');
            setNotice('Affectation mise à jour.');
            invalidate();
        },
    });

    const summary = incidentsQuery.data?.summary || {};
    const rows = useMemo(() => incidents.slice().sort((left, right) => {
        const severityRank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
        return (severityRank[right.severity] - severityRank[left.severity])
            || (new Date(left.triggered_at) - new Date(right.triggered_at));
    }), [incidents]);

    const enableDeviceAlerts = async () => {
        const permission = await requestPlanningNotificationPermission();
        setDevicePermission(permission);
        if (permission === 'granted') notifyPlanningIncidents(incidents);
    };

    return (
        <div className="min-h-[650px] bg-slate-50">
            <header className="border-b border-slate-200 bg-white px-4 py-5 sm:px-6 xl:px-8">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-red-600" />
                            <h2 className="text-xl font-black text-slate-950">Centre d’incidents planning</h2>
                        </div>
                        <p className="mt-1 text-sm font-semibold text-slate-500">
                            Traiter les blocages et dérives sans transformer chaque événement en notification.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {devicePermission !== 'granted' && devicePermission !== 'unsupported' && (
                            <button
                                type="button"
                                onClick={enableDeviceAlerts}
                                className="flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-700"
                            >
                                <BellRing className="h-4 w-4" /> Alertes appareil
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-700"
                        >
                            <X className="h-4 w-4" /> Retour au planning
                        </button>
                    </div>
                </div>
                <div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                    {[
                        ['Ouverts', summary.open || 0, 'text-red-700'],
                        ['Pris en charge', summary.acknowledged || 0, 'text-blue-700'],
                        ['Critiques', summary.critical || 0, 'text-red-700'],
                        ['Escaladés', summary.escalated || 0, 'text-orange-700'],
                        ['Résolus', summary.resolved || 0, 'text-emerald-700'],
                    ].map(([label, value, tone]) => (
                        <div key={label} className="border-l-2 border-slate-200 bg-slate-50 px-4 py-3">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
                            <strong className={`mt-1 block text-2xl font-black ${tone}`}>{value}</strong>
                        </div>
                    ))}
                </div>
            </header>

            <div className="grid min-h-[560px] xl:grid-cols-[minmax(0,1fr)_420px]">
                <main className="min-w-0 border-r border-slate-200 bg-white">
                    <div className="flex flex-wrap gap-2 border-b border-slate-200 px-4 py-3 sm:px-6">
                        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-bold">
                            <option value="OPEN,ACKNOWLEDGED">À traiter</option>
                            <option value="OPEN">Ouverts</option>
                            <option value="ACKNOWLEDGED">Pris en charge</option>
                            <option value="RESOLVED">Résolus</option>
                            <option value="">Tous</option>
                        </select>
                        <select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm font-bold">
                            <option value="">Toutes criticités</option>
                            <option value="CRITICAL">Critique</option>
                            <option value="HIGH">Élevée</option>
                            <option value="MEDIUM">Modérée</option>
                            <option value="LOW">Faible</option>
                        </select>
                    </div>
                    <div className="divide-y divide-slate-100">
                        {rows.map((incident) => (
                            <button
                                key={incident.id}
                                type="button"
                                onClick={() => setSelectedId(incident.id)}
                                className={`grid w-full gap-3 px-4 py-4 text-left hover:bg-slate-50 sm:px-6 lg:grid-cols-[120px_minmax(0,1fr)_150px_90px] ${selectedId === incident.id ? 'bg-blue-50' : ''}`}
                            >
                                <div>
                                    <span className={`inline-flex rounded px-2 py-1 text-[10px] font-black uppercase ${SEVERITY_META[incident.severity]?.tone}`}>
                                        {SEVERITY_META[incident.severity]?.label}
                                    </span>
                                    {incident.escalation_level > 0 && (
                                        <span className="ml-1 inline-flex rounded bg-orange-100 px-2 py-1 text-[10px] font-black uppercase text-orange-800">
                                            Escaladé
                                        </span>
                                    )}
                                </div>
                                <div className="min-w-0">
                                    <p className="truncate font-black text-slate-950">{incident.title}</p>
                                    <p className="mt-1 line-clamp-2 text-xs font-semibold text-slate-500">{incident.message}</p>
                                    <p className="mt-2 font-mono text-[10px] font-bold text-slate-400">{incident.reference}</p>
                                </div>
                                <div className="text-xs">
                                    <p className="font-black text-slate-700">{incident.responsible_name || 'Non affecté'}</p>
                                    <p className="mt-1 font-semibold text-slate-400">{incident.assigned_manager_name || 'Sans pilote'}</p>
                                </div>
                                <div className="text-right">
                                    <span className={`inline-flex rounded border px-2 py-1 text-[10px] font-black uppercase ${STATUS_META[incident.status]?.tone}`}>
                                        {STATUS_META[incident.status]?.label}
                                    </span>
                                    <p className="mt-2 text-xs font-black text-slate-500">{ageLabel(incident.triggered_at)}</p>
                                </div>
                            </button>
                        ))}
                        {!rows.length && !incidentsQuery.isLoading && (
                            <div className="py-20 text-center">
                                <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
                                <p className="mt-3 font-black text-slate-800">Aucun incident dans cette vue</p>
                            </div>
                        )}
                    </div>
                </main>

                <aside className="bg-slate-50 p-4 sm:p-5">
                    {!selected ? (
                        <div className="border-t border-slate-200 py-16 text-center">
                            <ShieldAlert className="mx-auto h-9 w-9 text-slate-300" />
                            <p className="mt-3 text-sm font-black text-slate-700">Sélectionnez un incident</p>
                            <p className="mt-1 text-xs font-semibold text-slate-400">Le traitement et l’historique apparaîtront ici.</p>
                        </div>
                    ) : (
                        <div>
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <p className="font-mono text-[10px] font-black text-blue-600">{selected.reference}</p>
                                    <h3 className="mt-1 text-lg font-black text-slate-950">{selected.title}</h3>
                                </div>
                                <span className={`rounded border px-2 py-1 text-[10px] font-black uppercase ${STATUS_META[selected.status]?.tone}`}>
                                    {STATUS_META[selected.status]?.label}
                                </span>
                            </div>
                            <p className="mt-3 text-sm font-semibold leading-6 text-slate-600">{selected.message}</p>
                            <div className="mt-4 grid grid-cols-2 gap-px bg-slate-200">
                                <div className="bg-white p-3">
                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Déclenché</p>
                                    <p className="mt-1 text-xs font-black text-slate-700">{formatDateTime(selected.triggered_at)}</p>
                                </div>
                                <div className="bg-white p-3">
                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Ancienneté</p>
                                    <p className="mt-1 text-xs font-black text-slate-700">{ageLabel(selected.triggered_at)}</p>
                                </div>
                            </div>

                            {selected.status !== 'RESOLVED' && (
                                <div className="mt-5 space-y-3 border-t border-slate-200 pt-4">
                                    {selected.status === 'OPEN' && (
                                        <button
                                            type="button"
                                            onClick={() => actionMutation.mutate({
                                                action: 'acknowledge',
                                                payload: { comment: comment || undefined },
                                            })}
                                            disabled={actionMutation.isPending}
                                            className="flex h-10 w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40"
                                        >
                                            <CheckCircle2 className="h-4 w-4" /> Prendre en charge
                                        </button>
                                    )}
                                    <label>
                                        <span className="mb-1 block text-[10px] font-black uppercase tracking-widest text-slate-500">Pilote incident</span>
                                        <select value={managerId} onChange={(event) => setManagerId(event.target.value)} className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm font-bold">
                                            <option value="">Sélectionner</option>
                                            {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                                        </select>
                                    </label>
                                    <label>
                                        <span className="mb-1 block text-[10px] font-black uppercase tracking-widest text-slate-500">Responsable opérationnel</span>
                                        <select value={responsibleId} onChange={(event) => setResponsibleId(event.target.value)} className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm font-bold">
                                            <option value="">Sélectionner</option>
                                            {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                                        </select>
                                    </label>
                                    <button
                                        type="button"
                                        onClick={() => reassignMutation.mutate({
                                            assigned_manager_user_id: managerId ? Number(managerId) : undefined,
                                            responsible_user_id: responsibleId ? Number(responsibleId) : undefined,
                                            comment: comment || undefined,
                                        })}
                                        disabled={reassignMutation.isPending || (!managerId && !responsibleId)}
                                        className="flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 text-sm font-black text-slate-700 disabled:opacity-40"
                                    >
                                        <UserRound className="h-4 w-4" /> Réaffecter
                                    </button>
                                    <label>
                                        <span className="mb-1 block text-[10px] font-black uppercase tracking-widest text-slate-500">Compte rendu</span>
                                        <textarea value={comment} onChange={(event) => setComment(event.target.value)} rows="3" placeholder="Action réalisée, consigne ou résolution..." className="w-full rounded-md border border-slate-200 p-3 text-sm outline-none focus:border-blue-500" />
                                    </label>
                                    <div className="grid grid-cols-2 gap-2">
                                        <button
                                            type="button"
                                            onClick={() => actionMutation.mutate({ action: 'comments', payload: { comment } })}
                                            disabled={actionMutation.isPending || comment.trim().length < 2}
                                            className="flex h-10 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-black text-slate-700 disabled:opacity-40"
                                        >
                                            <MessageSquare className="h-4 w-4" /> Commenter
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => actionMutation.mutate({ action: 'resolve', payload: { comment } })}
                                            disabled={actionMutation.isPending || comment.trim().length < 2}
                                            className="flex h-10 items-center justify-center gap-2 rounded-md bg-emerald-600 text-sm font-black text-white disabled:opacity-40"
                                        >
                                            <CheckCircle2 className="h-4 w-4" /> Résoudre
                                        </button>
                                    </div>
                                </div>
                            )}
                            {selected.source_url && (
                                <a href={selected.source_url} className="mt-3 flex h-10 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-black text-slate-700">
                                    <ExternalLink className="h-4 w-4" /> Ouvrir le dossier lié
                                </a>
                            )}
                            {notice && <p className="mt-3 rounded-md bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700">{notice}</p>}
                            {mutationError(actionMutation, reassignMutation) && (
                                <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs font-bold text-red-700">
                                    {mutationError(actionMutation, reassignMutation)}
                                </p>
                            )}

                            <div className="mt-6 border-t border-slate-200 pt-4">
                                <div className="flex items-center gap-2">
                                    <Clock3 className="h-4 w-4 text-slate-400" />
                                    <h4 className="text-sm font-black text-slate-900">Historique complet</h4>
                                </div>
                                <div className="mt-3 border-l-2 border-slate-200 pl-4">
                                    {(selected.history || []).slice().reverse().map((entry) => (
                                        <div key={entry.id} className="relative pb-4">
                                            <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-blue-500 ring-2 ring-white" />
                                            <p className="text-xs font-black text-slate-800">{ACTION_LABELS[entry.action] || entry.action}</p>
                                            <p className="mt-0.5 text-[10px] font-semibold text-slate-400">{entry.actor_name} · {formatDateTime(entry.created_at)}</p>
                                            {entry.comment && <p className="mt-1 text-xs font-semibold leading-5 text-slate-600">{entry.comment}</p>}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </aside>
            </div>
        </div>
    );
}
