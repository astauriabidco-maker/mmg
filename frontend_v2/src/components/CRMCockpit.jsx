import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AlertTriangle,
    ArrowRight,
    CalendarClock,
    Check,
    ClipboardList,
    Clock3,
    RefreshCw,
    Target,
    TrendingUp,
    UserRound,
} from 'lucide-react';
import api from '../services/api';

const STAGE_LABELS = {
    nouveau: 'Nouvelles',
    qualifie: 'Qualifiées',
    metre_a_planifier: 'Métré à planifier',
    metre_en_cours: 'Métré en cours',
    proposition_a_preparer: 'Proposition à préparer',
    proposition_envoyee: 'Proposition envoyée',
    negociation: 'Négociation',
};

const SEVERITY_STYLES = {
    CRITICAL: 'border-red-500 bg-red-50 text-red-950',
    HIGH: 'border-orange-500 bg-orange-50 text-orange-950',
    MEDIUM: 'border-amber-400 bg-amber-50 text-amber-950',
    LOW: 'border-slate-300 bg-slate-50 text-slate-800',
};

const formatMoney = value => Number(value || 0).toLocaleString('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
});

const formatDateTime = value => value
    ? new Date(value).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
    : 'À planifier';

const isToday = value => {
    if (!value) return false;
    const date = new Date(value);
    const today = new Date();
    return date.getFullYear() === today.getFullYear()
        && date.getMonth() === today.getMonth()
        && date.getDate() === today.getDate();
};

export default function CRMCockpit({ onOpenClient, onOpenMeasure }) {
    const [horizonDays, setHorizonDays] = useState(14);
    const [workingKey, setWorkingKey] = useState('');
    const [actionError, setActionError] = useState('');

    const cockpitQuery = useQuery({
        queryKey: ['crm-cockpit', horizonDays],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/crm/cockpit', {
                params: { horizon_days: horizonDays, stale_days: 7 },
            });
            return response.data;
        },
    });

    const data = cockpitQuery.data;
    const agendaGroups = useMemo(() => {
        const groups = { overdue: [], today: [], upcoming: [], unscheduled: [] };
        (data?.agenda || []).forEach(item => {
            if (!item.start_at) groups.unscheduled.push(item);
            else if (item.overdue) groups.overdue.push(item);
            else if (isToday(item.start_at)) groups.today.push(item);
            else groups.upcoming.push(item);
        });
        return groups;
    }, [data]);

    const materializeReminder = async reminder => {
        setActionError('');
        setWorkingKey(reminder.key);
        try {
            if (reminder.existing_activity_id) {
                await api.patch(`/v2/mmg/activities/${reminder.existing_activity_id}`, {
                    status: 'termine',
                });
            } else {
                const dueAt = new Date();
                dueAt.setDate(dueAt.getDate() + 1);
                dueAt.setHours(9, 0, 0, 0);
                await api.post('/v2/mmg/activities', {
                    client_id: reminder.client_id,
                    opportunity_id: reminder.opportunity_id,
                    activity_type: 'tache',
                    subject: reminder.suggested_subject,
                    note: `Relance suggérée automatiquement : ${reminder.reason}`,
                    due_at: dueAt.toISOString(),
                    status: 'a_faire',
                });
            }
            await cockpitQuery.refetch();
        } catch (error) {
            setActionError(error?.response?.data?.detail || "L'action de relance n'a pas pu être enregistrée.");
        } finally {
            setWorkingKey('');
        }
    };

    if (cockpitQuery.isLoading) {
        return (
            <div className="flex min-h-96 items-center justify-center bg-white">
                <RefreshCw className="h-6 w-6 animate-spin text-blue-600" />
            </div>
        );
    }

    if (cockpitQuery.isError) {
        return (
            <div className="m-5 border-l-4 border-red-500 bg-red-50 p-5 text-red-900">
                <p className="font-black">Le cockpit commercial est indisponible.</p>
                <button onClick={() => cockpitQuery.refetch()} className="mt-3 text-sm font-black underline">
                    Réessayer
                </button>
            </div>
        );
    }

    const metrics = data.metrics;

    return (
        <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50/60">
            <div className="mx-auto w-full max-w-[1720px] space-y-5 p-4 lg:p-6">
                <header className="flex flex-col gap-4 border-b border-slate-200 bg-white px-5 py-5 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Cockpit équipe commerciale</p>
                        <h3 className="mt-1 text-2xl font-black tracking-tight text-slate-950">Portefeuille, agenda et relances</h3>
                        <p className="mt-1 text-sm font-semibold text-slate-500">
                            Une seule file de travail pour savoir quoi traiter, quand et pour quel client.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="inline-flex border border-slate-200 bg-slate-50 p-1">
                            {[7, 14, 30].map(days => (
                                <button
                                    key={days}
                                    onClick={() => setHorizonDays(days)}
                                    className={`px-3 py-2 text-xs font-black ${horizonDays === days ? 'bg-slate-950 text-white' : 'text-slate-600 hover:bg-white'}`}
                                >
                                    {days} jours
                                </button>
                            ))}
                        </div>
                        <button
                            onClick={() => cockpitQuery.refetch()}
                            title="Actualiser le cockpit"
                            className="inline-flex h-10 w-10 items-center justify-center border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                        >
                            <RefreshCw className="h-4 w-4" />
                        </button>
                    </div>
                </header>

                <section className="grid border-y border-slate-200 bg-white sm:grid-cols-2 xl:grid-cols-6">
                    <Metric icon={Target} label="Opportunités" value={metrics.open_opportunities} />
                    <Metric icon={TrendingUp} label="Pipeline brut" value={formatMoney(metrics.pipeline_amount)} />
                    <Metric icon={TrendingUp} label="Pipeline pondéré" value={formatMoney(metrics.weighted_pipeline_amount)} tone="blue" />
                    <Metric icon={Clock3} label="Actions en retard" value={metrics.overdue_actions} tone={metrics.overdue_actions ? 'red' : 'slate'} />
                    <Metric icon={ClipboardList} label="Métrés à planifier" value={metrics.measures_to_schedule} tone={metrics.measures_to_schedule ? 'amber' : 'slate'} />
                    <Metric icon={AlertTriangle} label="Relances détectées" value={metrics.automatic_reminders} tone={metrics.automatic_reminders ? 'amber' : 'slate'} />
                </section>

                <section className="border-y border-slate-200 bg-white">
                    <div className="border-b border-slate-200 px-5 py-4">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Portefeuille commercial</p>
                        <h4 className="mt-1 text-lg font-black text-slate-950">Valeur et charge par étape</h4>
                    </div>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
                        {data.stages.map(stage => (
                            <div key={stage.stage} className="min-w-0 border-b border-r border-slate-100 px-4 py-4 last:border-r-0">
                                <div className="flex items-start justify-between gap-2">
                                    <p className="text-xs font-black text-slate-700">{STAGE_LABELS[stage.stage] || stage.stage}</p>
                                    <span className="bg-slate-100 px-2 py-1 text-[10px] font-black text-slate-700">{stage.count}</span>
                                </div>
                                <p className="mt-4 text-xl font-black text-slate-950">{formatMoney(stage.amount)}</p>
                                <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-blue-600">
                                    {formatMoney(stage.weighted_amount)} pondéré
                                </p>
                            </div>
                        ))}
                    </div>
                </section>

                {actionError && (
                    <div className="border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-900">
                        {actionError}
                    </div>
                )}

                <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(420px,0.85fr)]">
                    <section className="border-y border-slate-200 bg-white">
                        <SectionHeader
                            icon={CalendarClock}
                            eyebrow={`Agenda à ${horizonDays} jours`}
                            title="Rendez-vous, relances et métrés"
                            detail="Les éléments non planifiés restent visibles jusqu'à affectation."
                        />
                        <div className="divide-y divide-slate-100">
                            <AgendaGroup title="En retard" items={agendaGroups.overdue} tone="red" onOpenClient={onOpenClient} onOpenMeasure={onOpenMeasure} />
                            <AgendaGroup title="Aujourd'hui" items={agendaGroups.today} tone="blue" onOpenClient={onOpenClient} onOpenMeasure={onOpenMeasure} />
                            <AgendaGroup title="À venir" items={agendaGroups.upcoming} tone="slate" onOpenClient={onOpenClient} onOpenMeasure={onOpenMeasure} />
                            <AgendaGroup title="À planifier" items={agendaGroups.unscheduled} tone="amber" onOpenClient={onOpenClient} onOpenMeasure={onOpenMeasure} />
                            {!data.agenda.length && (
                                <EmptyState title="Agenda dégagé" detail="Aucune activité ou mission de métré sur cet horizon." />
                            )}
                        </div>
                    </section>

                    <section className="border-y border-slate-200 bg-white">
                        <SectionHeader
                            icon={AlertTriangle}
                            eyebrow="Détection automatique"
                            title="Relances recommandées"
                            detail="Une recommandation ne devient une tâche qu'après validation."
                        />
                        <div className="divide-y divide-slate-100">
                            {data.reminders.map(reminder => (
                                <div key={reminder.key} className={`border-l-4 px-4 py-4 ${SEVERITY_STYLES[reminder.severity] || SEVERITY_STYLES.LOW}`}>
                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                        <div className="min-w-0">
                                            <p className="text-[10px] font-black uppercase tracking-widest opacity-60">{reminder.reference || reminder.kind}</p>
                                            <p className="mt-1 text-sm font-black">{reminder.client_name} · {reminder.title}</p>
                                            <p className="mt-1 text-xs font-semibold opacity-75">{reminder.reason}</p>
                                            {reminder.due_at && <p className="mt-2 text-[10px] font-black uppercase">Échéance {formatDateTime(reminder.due_at)}</p>}
                                        </div>
                                        <div className="flex shrink-0 gap-2">
                                            <button
                                                onClick={() => onOpenClient(reminder.client_id)}
                                                className="inline-flex items-center gap-2 border border-current/20 bg-white/70 px-3 py-2 text-xs font-black"
                                            >
                                                <UserRound className="h-4 w-4" />
                                                Client
                                            </button>
                                            <button
                                                onClick={() => reminder.kind === 'UNSCHEDULED_MEASURE'
                                                    ? onOpenMeasure(reminder.target_id)
                                                    : materializeReminder(reminder)}
                                                disabled={workingKey === reminder.key}
                                                className="inline-flex items-center gap-2 bg-slate-950 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                                            >
                                                {reminder.existing_activity_id
                                                    ? <Check className="h-4 w-4" />
                                                    : reminder.kind === 'UNSCHEDULED_MEASURE'
                                                        ? <ClipboardList className="h-4 w-4" />
                                                        : <CalendarClock className="h-4 w-4" />}
                                                {reminder.existing_activity_id
                                                    ? 'Marquer fait'
                                                    : reminder.kind === 'UNSCHEDULED_MEASURE'
                                                        ? 'Planifier métré'
                                                        : 'Planifier'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {!data.reminders.length && (
                                <EmptyState title="Aucune relance urgente" detail="Toutes les opportunités ont une prochaine action cohérente." />
                            )}
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}

function Metric({ icon: Icon, label, value, tone = 'slate' }) {
    const tones = {
        slate: 'text-slate-950',
        blue: 'text-blue-700',
        red: 'text-red-700',
        amber: 'text-amber-700',
    };
    return (
        <div className="border-b border-r border-slate-100 px-4 py-4 last:border-r-0">
            <div className="flex items-center gap-2 text-slate-400">
                <Icon className="h-4 w-4" />
                <span className="text-[9px] font-black uppercase tracking-widest">{label}</span>
            </div>
            <p className={`mt-3 text-2xl font-black ${tones[tone]}`}>{value}</p>
        </div>
    );
}

function SectionHeader({ icon: Icon, eyebrow, title, detail }) {
    return (
        <div className="flex items-start gap-3 border-b border-slate-200 px-5 py-4">
            <Icon className="mt-1 h-5 w-5 text-blue-600" />
            <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-blue-600">{eyebrow}</p>
                <h4 className="mt-1 text-lg font-black text-slate-950">{title}</h4>
                <p className="mt-1 text-xs font-semibold text-slate-500">{detail}</p>
            </div>
        </div>
    );
}

function AgendaGroup({ title, items, tone, onOpenClient, onOpenMeasure }) {
    if (!items.length) return null;
    const tones = {
        red: 'text-red-700',
        blue: 'text-blue-700',
        amber: 'text-amber-700',
        slate: 'text-slate-500',
    };
    return (
        <div>
            <p className={`border-b border-slate-100 bg-slate-50 px-5 py-2 text-[9px] font-black uppercase tracking-widest ${tones[tone]}`}>{title} · {items.length}</p>
            <div className="divide-y divide-slate-100">
                {items.map(item => (
                    <button
                        key={`${item.kind}-${item.id}`}
                        onClick={() => item.kind === 'MEASURE' ? onOpenMeasure(item.id) : onOpenClient(item.client_id)}
                        className="flex w-full items-center gap-4 px-5 py-3 text-left hover:bg-slate-50"
                    >
                        <div className={`h-2.5 w-2.5 shrink-0 ${item.overdue ? 'bg-red-500' : item.kind === 'MEASURE' ? 'bg-emerald-500' : 'bg-blue-500'}`} />
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-black text-slate-900">{item.title}</p>
                            <p className="mt-1 truncate text-xs font-semibold text-slate-500">{item.client_name} · {item.reference || item.status}</p>
                        </div>
                        <div className="shrink-0 text-right">
                            <p className="text-xs font-black text-slate-700">{formatDateTime(item.start_at)}</p>
                            <p className="mt-1 text-[9px] font-bold uppercase tracking-wide text-slate-400">{item.owner_name || 'Non affecté'}</p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-slate-300" />
                    </button>
                ))}
            </div>
        </div>
    );
}

function EmptyState({ title, detail }) {
    return (
        <div className="px-6 py-12 text-center">
            <Check className="mx-auto h-8 w-8 text-emerald-500" />
            <p className="mt-3 text-sm font-black text-slate-800">{title}</p>
            <p className="mt-1 text-xs font-semibold text-slate-400">{detail}</p>
        </div>
    );
}
