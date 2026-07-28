import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AlertTriangle,
    ArrowRight,
    BarChart3,
    BellRing,
    CalendarPlus,
    CalendarClock,
    Check,
    ClipboardList,
    Clock3,
    History,
    Mail,
    RefreshCw,
    Send,
    Settings2,
    Target,
    TrendingUp,
    Users,
    UserRound,
    UserPlus,
    X,
} from 'lucide-react';
import api from '../services/api';

const STAGE_LABELS = {
    nouveau: 'Nouvelles',
    qualifie: 'Qualifiées',
    metre_a_planifier: 'Métré à planifier',
    metre_en_cours: 'Métré en cours',
    proposition_a_preparer: 'Proposition à préparer',
    proposition_a_valider: 'Proposition à valider',
    proposition_envoyee: 'Proposition envoyée',
    negociation: 'Négociation',
};

const SEVERITY_STYLES = {
    CRITICAL: 'border-red-500 bg-red-50 text-red-950',
    HIGH: 'border-orange-500 bg-orange-50 text-orange-950',
    MEDIUM: 'border-amber-400 bg-amber-50 text-amber-950',
    LOW: 'border-slate-300 bg-slate-50 text-slate-800',
};

const DELIVERY_STYLES = {
    SENT: 'bg-emerald-100 text-emerald-800',
    SKIPPED: 'bg-amber-100 text-amber-800',
    FAILED: 'bg-red-100 text-red-800',
    PREPARED: 'bg-slate-100 text-slate-700',
};

const DELIVERY_LABELS = {
    SENT: 'Envoyé',
    SKIPPED: 'Non envoyé',
    FAILED: 'Échec',
    PREPARED: 'Préparé',
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

const defaultActionDate = () => {
    const date = new Date();
    date.setDate(date.getDate() + 1);
    date.setHours(9, 0, 0, 0);
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
};

export default function CRMCockpit({ onOpenClient, onOpenMeasure }) {
    const [horizonDays, setHorizonDays] = useState(14);
    const [selectedOwnerId, setSelectedOwnerId] = useState('');
    const [workingKey, setWorkingKey] = useState('');
    const [actionError, setActionError] = useState('');
    const [emailComposer, setEmailComposer] = useState(null);
    const [sendConfirmed, setSendConfirmed] = useState(false);
    const [notification, setNotification] = useState(null);
    const [showRules, setShowRules] = useState(false);
    const [savingRuleId, setSavingRuleId] = useState(null);
    const [cockpitAction, setCockpitAction] = useState(null);

    const cockpitQuery = useQuery({
        queryKey: ['crm-cockpit', horizonDays, selectedOwnerId],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/crm/cockpit', {
                params: {
                    horizon_days: horizonDays,
                    stale_days: 7,
                    owner_user_id: selectedOwnerId ? Number(selectedOwnerId) : undefined,
                },
            });
            return response.data;
        },
    });

    const templatesQuery = useQuery({
        queryKey: ['crm-reminder-templates'],
        queryFn: async () => (await api.get('/v2/mmg/crm/reminder-templates')).data,
    });

    const historyQuery = useQuery({
        queryKey: ['crm-reminder-history'],
        queryFn: async () => (
            await api.get('/v2/mmg/crm/reminders/history', { params: { limit: 8 } })
        ).data,
    });

    const rulesQuery = useQuery({
        queryKey: ['crm-reminder-rules'],
        queryFn: async () => (await api.get('/v2/mmg/crm/reminder-rules')).data,
    });

    const plansQuery = useQuery({
        queryKey: ['crm-reminder-plans', selectedOwnerId],
        queryFn: async () => {
            return (
                await api.get('/v2/mmg/crm/reminder-plans', {
                    params: {
                        status: 'PENDING',
                        assigned_user_id: selectedOwnerId ? Number(selectedOwnerId) : undefined,
                        limit: 100,
                    },
                })
            ).data;
        },
        enabled: cockpitQuery.isSuccess,
    });

    const usersQuery = useQuery({
        queryKey: ['crm-reminder-users'],
        queryFn: async () => (await api.get('/v2/config/users')).data,
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

    const previewEmail = async (reminder, templateId = null) => {
        setActionError('');
        setWorkingKey(reminder.key);
        setSendConfirmed(false);
        try {
            const response = await api.post('/v2/mmg/crm/reminders/preview', {
                plan_id: reminder.plan_id || null,
                client_id: reminder.client_id,
                opportunity_id: reminder.opportunity_id,
                template_id: templateId,
                reminder_kind: reminder.kind,
                due_at: reminder.due_at,
            });
            setEmailComposer({
                reminder,
                ...response.data,
            });
        } catch (error) {
            setActionError(error?.response?.data?.detail || "La prévisualisation de l'email a échoué.");
        } finally {
            setWorkingKey('');
        }
    };

    const changeEmailTemplate = async templateId => {
        if (!emailComposer) return;
        await previewEmail(emailComposer.reminder, Number(templateId));
    };

    const sendEmailReminder = async () => {
        if (!emailComposer || !sendConfirmed) return;
        setWorkingKey(emailComposer.reminder.key);
        setActionError('');
        try {
            const response = await api.post('/v2/mmg/crm/reminders/send', {
                plan_id: emailComposer.reminder.plan_id || null,
                reminder_key: emailComposer.reminder.key,
                client_id: emailComposer.reminder.client_id,
                opportunity_id: emailComposer.reminder.opportunity_id,
                template_id: emailComposer.template_id,
                recipient: emailComposer.recipient,
                subject: emailComposer.subject,
                message: emailComposer.message,
                confirm_send: true,
            });
            const delivery = response.data;
            setNotification({
                tone: delivery.status === 'SENT' ? 'success' : delivery.status === 'FAILED' ? 'error' : 'warning',
                message: delivery.notification,
            });
            await Promise.all([historyQuery.refetch(), cockpitQuery.refetch(), plansQuery.refetch()]);
            setEmailComposer(null);
            setSendConfirmed(false);
        } catch (error) {
            const message = error?.response?.data?.detail || "L'envoi de la relance a échoué.";
            setActionError(message);
            setNotification({ tone: 'error', message });
        } finally {
            setWorkingKey('');
        }
    };

    const previewPlannedReminder = plan => previewEmail({
        key: plan.plan_key,
        plan_id: plan.id,
        kind: 'PLANNED_RULE',
        client_id: plan.client_id,
        client_name: plan.client_name,
        client_email: plan.client_email,
        opportunity_id: plan.opportunity_id,
        reference: plan.opportunity_reference,
        title: plan.opportunity_title,
        due_at: plan.due_at,
    }, plan.template_id);

    const cancelPlannedReminder = async plan => {
        if (!window.confirm(`Ignorer cette relance pour ${plan.client_name} ?`)) return;
        setWorkingKey(plan.plan_key);
        setActionError('');
        try {
            await api.post(`/v2/mmg/crm/reminder-plans/${plan.id}/cancel`, {
                reason: 'Relance ignorée après validation humaine',
            });
            await plansQuery.refetch();
            setNotification({
                tone: 'success',
                message: `La relance de ${plan.client_name} a été retirée de la file.`,
            });
        } catch (error) {
            setActionError(error?.response?.data?.detail || "La relance n'a pas pu être ignorée.");
        } finally {
            setWorkingKey('');
        }
    };

    const saveReminderRule = async (ruleId, patch) => {
        setSavingRuleId(ruleId);
        setActionError('');
        try {
            await api.patch(`/v2/mmg/crm/reminder-rules/${ruleId}`, patch);
            await Promise.all([rulesQuery.refetch(), plansQuery.refetch()]);
            setNotification({ tone: 'success', message: 'Règle de relance mise à jour.' });
        } catch (error) {
            setActionError(error?.response?.data?.detail || "La règle n'a pas pu être enregistrée.");
            throw error;
        } finally {
            setSavingRuleId(null);
        }
    };

    const refreshActionableCockpit = async () => {
        await Promise.all([cockpitQuery.refetch(), plansQuery.refetch()]);
    };

    const assignOpportunityOwner = async values => {
        const item = cockpitAction.item;
        const opportunityId = item.opportunity_id || item.id;
        setWorkingKey(item.key);
        setActionError('');
        try {
            await api.post(`/v2/mmg/crm/cockpit/opportunities/${opportunityId}/assign-owner`, {
                owner_user_id: Number(values.owner_user_id),
            });
            await refreshActionableCockpit();
            setNotification({
                tone: 'success',
                message: `${item.client_name} est maintenant affecté à ${values.owner_name}.`,
            });
            setCockpitAction(null);
        } catch (error) {
            setActionError(error?.response?.data?.detail || "L'affectation n'a pas pu être enregistrée.");
        } finally {
            setWorkingKey('');
        }
    };

    const scheduleOpportunityAction = async values => {
        const item = cockpitAction.item;
        const opportunityId = item.opportunity_id || item.id;
        setWorkingKey(item.key);
        setActionError('');
        try {
            await api.post(`/v2/mmg/crm/cockpit/opportunities/${opportunityId}/schedule-action`, {
                activity_type: values.activity_type,
                subject: values.subject,
                note: values.note || null,
                due_at: new Date(values.due_at).toISOString(),
                reminder_plan_id: item.kind === 'PLANNED_REMINDER' ? item.target_id : null,
            });
            await refreshActionableCockpit();
            setNotification({
                tone: 'success',
                message: `Prochaine action planifiée pour ${item.client_name}.`,
            });
            setCockpitAction(null);
        } catch (error) {
            setActionError(error?.response?.data?.detail || "La prochaine action n'a pas pu être planifiée.");
        } finally {
            setWorkingKey('');
        }
    };

    const prepareCockpitReminder = item => previewEmail({
        ...item,
        key: item.key || `opportunity-${item.id}`,
        plan_id: item.plan_id || (item.kind === 'PLANNED_REMINDER' ? item.target_id : null),
        kind: item.kind || 'MISSING_NEXT_STEP',
        opportunity_id: item.opportunity_id || item.id,
        suggested_subject: item.suggested_subject || `Relancer ${item.client_name}`,
        due_at: item.due_at || null,
    });

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
                    <div className="flex flex-wrap items-center gap-2">
                        <label className="flex h-10 items-center gap-2 border border-slate-200 bg-white px-3">
                            <UserRound className="h-4 w-4 text-slate-400" />
                            <select
                                value={selectedOwnerId}
                                onChange={event => setSelectedOwnerId(event.target.value)}
                                className="max-w-48 bg-transparent text-xs font-black text-slate-700 outline-none"
                                aria-label="Filtrer par responsable"
                            >
                                <option value="">Toute l'équipe</option>
                                {(usersQuery.data || []).filter(user => user.is_active).map(user => (
                                    <option key={user.id} value={user.id}>
                                        {[user.first_name, user.last_name].filter(Boolean).join(' ') || user.username}
                                    </option>
                                ))}
                            </select>
                        </label>
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

                <section className="grid border-y border-slate-200 bg-white sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                    <Metric icon={Target} label="Opportunités" value={metrics.open_opportunities} />
                    <Metric icon={TrendingUp} label="Pipeline pondéré" value={formatMoney(metrics.weighted_pipeline_amount)} tone="blue" />
                    <Metric icon={CalendarClock} label="Relances aujourd'hui" value={metrics.reminders_today} tone={metrics.reminders_today ? 'blue' : 'slate'} />
                    <Metric icon={Clock3} label="Relances en retard" value={metrics.overdue_reminders} tone={metrics.overdue_reminders ? 'red' : 'slate'} />
                    <Metric icon={AlertTriangle} label="Sans prochaine action" value={metrics.opportunities_without_action} tone={metrics.opportunities_without_action ? 'amber' : 'slate'} />
                    <Metric icon={ClipboardList} label="Métrés à planifier" value={metrics.measures_to_schedule} tone={metrics.measures_to_schedule ? 'amber' : 'slate'} />
                </section>

                <section className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(420px,0.95fr)]">
                    <div className="border-y border-slate-200 bg-white">
                        <SectionHeader
                            icon={Users}
                            eyebrow="Charge commerciale"
                            title="Retards et portefeuille par responsable"
                            detail="Les dossiers non affectés restent visibles et doivent être attribués."
                        />
                        <OwnerPerformanceTable
                            owners={data.owners || []}
                            onSelectOwner={ownerId => setSelectedOwnerId(ownerId ? String(ownerId) : '')}
                        />
                    </div>

                    <div className="border-y border-slate-200 bg-white">
                        <SectionHeader
                            icon={CalendarClock}
                            eyebrow="Priorités du jour"
                            title="À traiter avant de prospecter"
                            detail="Relances arrivées à échéance et dossiers sans prochaine action."
                        />
                        <DailyCommercialFocus
                            today={data.reminders_today || []}
                            overdue={data.overdue_reminders || []}
                            withoutAction={data.opportunities_without_action || []}
                            onOpenClient={onOpenClient}
                            onAssign={item => setCockpitAction({ mode: 'assign', item })}
                            onSchedule={item => setCockpitAction({ mode: 'schedule', item })}
                            onPrepareReminder={prepareCockpitReminder}
                        />
                    </div>
                </section>

                <section className="border-y border-slate-200 bg-white">
                    <SectionHeader
                        icon={BarChart3}
                        eyebrow="Conversion mesurée"
                        title="Taux de passage par étape"
                        detail="Calculé uniquement sur les sorties d'étape réellement historisées ; les dossiers encore ouverts ne faussent pas le taux."
                    />
                    <StageConversionTable conversions={data.stage_conversions || []} />
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

                {notification && (
                    <div className={`flex items-center justify-between border-l-4 px-4 py-3 text-sm font-bold ${
                        notification.tone === 'success'
                            ? 'border-emerald-500 bg-emerald-50 text-emerald-900'
                            : notification.tone === 'warning'
                                ? 'border-amber-500 bg-amber-50 text-amber-900'
                                : 'border-red-500 bg-red-50 text-red-900'
                    }`}>
                        <span className="flex items-center gap-2">
                            <BellRing className="h-4 w-4" />
                            {notification.message}
                        </span>
                        <button onClick={() => setNotification(null)} title="Fermer la notification">
                            <X className="h-4 w-4" />
                        </button>
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
                                    <div className="flex flex-col gap-3">
                                        <div className="min-w-0">
                                            <p className="text-[10px] font-black uppercase tracking-widest opacity-60">{reminder.reference || reminder.kind}</p>
                                            <p className="mt-1 text-sm font-black">{reminder.client_name} · {reminder.title}</p>
                                            <p className="mt-1 text-xs font-semibold opacity-75">{reminder.reason}</p>
                                            {reminder.due_at && <p className="mt-2 text-[10px] font-black uppercase">Échéance {formatDateTime(reminder.due_at)}</p>}
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            <button
                                                onClick={() => onOpenClient(reminder.client_id)}
                                                className="inline-flex items-center gap-2 border border-current/20 bg-white/70 px-3 py-2 text-xs font-black"
                                            >
                                                <UserRound className="h-4 w-4" />
                                                Client
                                            </button>
                                            {reminder.kind !== 'UNSCHEDULED_MEASURE' && reminder.client_email && (
                                                <button
                                                    onClick={() => previewEmail(reminder)}
                                                    disabled={workingKey === reminder.key}
                                                    className="inline-flex items-center gap-2 border border-blue-200 bg-white px-3 py-2 text-xs font-black text-blue-800 disabled:opacity-50"
                                                >
                                                    <Mail className="h-4 w-4" />
                                                    Email
                                                </button>
                                            )}
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

                <section className="border-y border-slate-200 bg-white">
                    <div className="flex flex-col gap-4 border-b border-slate-200 px-5 py-4 md:flex-row md:items-center md:justify-between">
                        <div className="flex items-start gap-3">
                            <BellRing className="mt-1 h-5 w-5 text-blue-600" />
                            <div>
                                <p className="text-[9px] font-black uppercase tracking-widest text-blue-600">Planification semi-automatique</p>
                                <h4 className="mt-1 text-lg font-black text-slate-950">Relances planifiées</h4>
                                <p className="mt-1 text-xs font-semibold text-slate-500">
                                    La règle propose une échéance et un responsable. Aucun email ne part sans validation humaine.
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="bg-slate-100 px-3 py-2 text-xs font-black text-slate-700">
                                {(plansQuery.data || []).length} en attente
                            </span>
                            <button
                                onClick={() => setShowRules(value => !value)}
                                className={`inline-flex items-center gap-2 border px-3 py-2 text-xs font-black ${
                                    showRules
                                        ? 'border-slate-950 bg-slate-950 text-white'
                                        : 'border-slate-200 bg-white text-slate-700'
                                }`}
                            >
                                <Settings2 className="h-4 w-4" />
                                Règles
                            </button>
                        </div>
                    </div>

                    {showRules && (
                        <ReminderRulesPanel
                            rules={rulesQuery.data || []}
                            templates={templatesQuery.data || []}
                            users={(usersQuery.data || []).filter(user => user.is_active)}
                            savingRuleId={savingRuleId}
                            onSave={saveReminderRule}
                        />
                    )}

                    <div className="divide-y divide-slate-100">
                        {(plansQuery.data || []).map(plan => (
                            <PlannedReminderRow
                                key={plan.id}
                                plan={plan}
                                working={workingKey === plan.plan_key}
                                onOpenClient={onOpenClient}
                                onPreview={previewPlannedReminder}
                                onCancel={cancelPlannedReminder}
                            />
                        ))}
                        {plansQuery.isLoading && (
                            <div className="flex items-center justify-center gap-2 px-5 py-10 text-sm font-bold text-slate-500">
                                <RefreshCw className="h-4 w-4 animate-spin" />
                                Calcul des prochaines relances
                            </div>
                        )}
                        {!plansQuery.isLoading && !(plansQuery.data || []).length && (
                            <EmptyState title="Aucune relance planifiée" detail="La file se remplira selon les étapes et délais configurés." />
                        )}
                    </div>
                </section>

                <section className="border-y border-slate-200 bg-white">
                    <SectionHeader
                        icon={History}
                        eyebrow="Traçabilité commerciale"
                        title="Historique des relances email"
                        detail="Chaque tentative conserve son destinataire, son auteur et son résultat."
                    />
                    <div className="divide-y divide-slate-100">
                        {(historyQuery.data || []).map(delivery => (
                            <div key={delivery.id} className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center">
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-black text-slate-900">{delivery.subject}</p>
                                    <p className="mt-1 truncate text-xs font-semibold text-slate-500">
                                        {delivery.client_name} · {delivery.recipient}
                                    </p>
                                    {delivery.error_message && (
                                        <p className="mt-1 text-xs font-bold text-red-700">{delivery.error_message}</p>
                                    )}
                                </div>
                                <span className={`w-fit px-2.5 py-1 text-[10px] font-black uppercase ${DELIVERY_STYLES[delivery.status] || DELIVERY_STYLES.PREPARED}`}>
                                    {DELIVERY_LABELS[delivery.status] || delivery.status}
                                </span>
                                <div className="text-left md:text-right">
                                    <p className="text-xs font-black text-slate-700">{formatDateTime(delivery.sent_at || delivery.created_at)}</p>
                                    <p className="mt-1 text-[9px] font-bold uppercase tracking-wide text-slate-400">{delivery.created_by}</p>
                                </div>
                            </div>
                        ))}
                        {!historyQuery.isLoading && !(historyQuery.data || []).length && (
                            <EmptyState title="Aucune relance envoyée" detail="Les prochaines tentatives apparaîtront ici, y compris les échecs." />
                        )}
                    </div>
                </section>
            </div>

            {emailComposer && (
                <EmailComposer
                    composer={emailComposer}
                    templates={templatesQuery.data || []}
                    confirmed={sendConfirmed}
                    sending={workingKey === emailComposer.reminder.key}
                    onClose={() => {
                        setEmailComposer(null);
                        setSendConfirmed(false);
                    }}
                    onChange={patch => {
                        setEmailComposer(current => ({ ...current, ...patch }));
                        setSendConfirmed(false);
                    }}
                    onTemplateChange={changeEmailTemplate}
                    onConfirmChange={setSendConfirmed}
                    onSend={sendEmailReminder}
                />
            )}

            {cockpitAction && (
                <CockpitOpportunityActionModal
                    action={cockpitAction}
                    users={(usersQuery.data || []).filter(user => user.is_active)}
                    saving={workingKey === cockpitAction.item.key}
                    onClose={() => setCockpitAction(null)}
                    onSubmit={cockpitAction.mode === 'assign'
                        ? assignOpportunityOwner
                        : scheduleOpportunityAction}
                />
            )}
        </div>
    );
}

function OwnerPerformanceTable({ owners, onSelectOwner }) {
    if (!owners.length) {
        return <EmptyState title="Aucun portefeuille actif" detail="Les responsables apparaîtront dès qu'une opportunité leur sera affectée." />;
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left">
                <thead className="border-b border-slate-200 bg-slate-50 text-[9px] font-black uppercase tracking-widest text-slate-400">
                    <tr>
                        <th className="px-5 py-3">Responsable</th>
                        <th className="px-3 py-3 text-right">Dossiers</th>
                        <th className="px-3 py-3 text-right">Pipeline</th>
                        <th className="px-3 py-3 text-right">Aujourd'hui</th>
                        <th className="px-3 py-3 text-right">Retards</th>
                        <th className="px-3 py-3 text-right">Sans action</th>
                        <th className="w-12 px-3 py-3" />
                    </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                    {owners.map(owner => (
                        <tr key={owner.owner_user_id || 'unassigned'} className="hover:bg-slate-50">
                            <td className="px-5 py-3 text-sm font-black text-slate-900">{owner.owner_name}</td>
                            <td className="px-3 py-3 text-right text-sm font-black text-slate-700">{owner.open_opportunities}</td>
                            <td className="px-3 py-3 text-right text-sm font-black text-slate-900">{formatMoney(owner.pipeline_amount)}</td>
                            <td className="px-3 py-3 text-right text-sm font-black text-blue-700">{owner.reminders_today}</td>
                            <td className={`px-3 py-3 text-right text-sm font-black ${owner.overdue_reminders ? 'text-red-700' : 'text-slate-400'}`}>
                                {owner.overdue_reminders}
                            </td>
                            <td className={`px-3 py-3 text-right text-sm font-black ${owner.opportunities_without_action ? 'text-amber-700' : 'text-slate-400'}`}>
                                {owner.opportunities_without_action}
                            </td>
                            <td className="px-3 py-3 text-right">
                                {owner.owner_user_id && (
                                    <button
                                        onClick={() => onSelectOwner(owner.owner_user_id)}
                                        title={`Filtrer sur ${owner.owner_name}`}
                                        className="inline-flex h-8 w-8 items-center justify-center text-slate-400 hover:bg-slate-100 hover:text-blue-700"
                                    >
                                        <ArrowRight className="h-4 w-4" />
                                    </button>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function DailyCommercialFocus({
    today,
    overdue,
    withoutAction,
    onOpenClient,
    onAssign,
    onSchedule,
    onPrepareReminder,
}) {
    const items = [
        ...overdue.map(item => ({ ...item, focusTone: 'red', focusLabel: 'En retard' })),
        ...today.map(item => ({ ...item, focusTone: 'blue', focusLabel: "Aujourd'hui" })),
        ...withoutAction.map(item => ({
            ...item,
            key: `without-action-${item.id}`,
            focusTone: 'amber',
            focusLabel: 'Sans action',
            reason: STAGE_LABELS[item.stage] || item.stage,
            kind: 'MISSING_NEXT_STEP',
            opportunity_id: item.id,
            suggested_subject: `Relancer ${item.client_name}`,
        })),
    ].slice(0, 8);
    const tones = {
        red: 'bg-red-100 text-red-700',
        blue: 'bg-blue-100 text-blue-700',
        amber: 'bg-amber-100 text-amber-800',
    };
    if (!items.length) {
        return <EmptyState title="Aucune urgence commerciale" detail="Les relances et prochaines actions sont à jour." />;
    }
    return (
        <div className="divide-y divide-slate-100">
            {items.map(item => (
                <div key={item.key} className="grid gap-3 px-5 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                    <button
                        onClick={() => onOpenClient(item.client_id)}
                        className="flex min-w-0 items-center gap-3 text-left hover:text-blue-700"
                    >
                        <span className={`shrink-0 px-2 py-1 text-[9px] font-black uppercase tracking-wide ${tones[item.focusTone]}`}>
                            {item.focusLabel}
                        </span>
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-black">{item.client_name} · {item.title}</p>
                            <p className="mt-1 truncate text-xs font-semibold text-slate-500">{item.reason || item.reference}</p>
                        </div>
                        <ArrowRight className="h-4 w-4 shrink-0 text-slate-300" />
                    </button>
                    <div className="flex items-center gap-1 sm:justify-end">
                        <button
                            onClick={() => onAssign(item)}
                            title="Affecter un responsable"
                            className="inline-flex h-9 w-9 items-center justify-center border border-slate-200 bg-white text-slate-500 hover:border-blue-300 hover:text-blue-700"
                        >
                            <UserPlus className="h-4 w-4" />
                        </button>
                        <button
                            onClick={() => onSchedule(item)}
                            title="Planifier une action"
                            className="inline-flex h-9 w-9 items-center justify-center border border-slate-200 bg-white text-slate-500 hover:border-blue-300 hover:text-blue-700"
                        >
                            <CalendarPlus className="h-4 w-4" />
                        </button>
                        <button
                            onClick={() => onPrepareReminder(item)}
                            disabled={!item.client_email}
                            title={item.client_email ? 'Préparer une relance email' : 'Email client manquant'}
                            className="inline-flex h-9 w-9 items-center justify-center border border-slate-200 bg-white text-slate-500 hover:border-blue-300 hover:text-blue-700 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-300"
                        >
                            <Mail className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            ))}
            {(overdue.length + today.length + withoutAction.length) > items.length && (
                <p className="px-5 py-3 text-xs font-bold text-slate-500">
                    {(overdue.length + today.length + withoutAction.length) - items.length} autre(s) priorité(s) dans les sections détaillées.
                </p>
            )}
        </div>
    );
}

function StageConversionTable({ conversions }) {
    if (!conversions.length) {
        return <EmptyState title="Historique en cours de constitution" detail="Les taux apparaîtront après les premiers changements d'étape." />;
    }
    return (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-7">
            {conversions.map(item => (
                <div key={item.stage} className="border-b border-r border-slate-100 px-4 py-4 last:border-r-0">
                    <p className="min-h-8 text-xs font-black text-slate-700">{STAGE_LABELS[item.stage] || item.stage}</p>
                    <p className={`mt-3 text-2xl font-black ${item.conversion_rate === null ? 'text-slate-300' : 'text-emerald-700'}`}>
                        {item.conversion_rate === null ? '—' : `${item.conversion_rate}%`}
                    </p>
                    <p className="mt-1 text-[10px] font-bold text-slate-500">
                        {item.decided_count
                            ? `${item.advanced_count} avancée(s) · ${item.lost_count} perdue(s)`
                            : `${item.entered_count} entrée(s) · aucune sortie`}
                    </p>
                </div>
            ))}
        </div>
    );
}

function PlannedReminderRow({ plan, working, onOpenClient, onPreview, onCancel }) {
    const overdue = new Date(plan.due_at).getTime() < Date.now();
    return (
        <div className="grid gap-4 px-5 py-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(180px,0.65fr)_minmax(180px,0.65fr)_auto] lg:items-center">
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <span className={`px-2 py-1 text-[9px] font-black uppercase tracking-wide ${
                        overdue ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                    }`}>
                        {overdue ? 'En retard' : STAGE_LABELS[plan.stage_snapshot] || plan.stage_snapshot}
                    </span>
                    <span className="text-[10px] font-black uppercase tracking-wide text-slate-400">
                        {plan.opportunity_reference}
                    </span>
                </div>
                <p className="mt-2 truncate text-sm font-black text-slate-950">
                    {plan.client_name} · {plan.opportunity_title}
                </p>
                <p className="mt-1 text-xs font-semibold text-slate-500">{plan.rule_name}</p>
            </div>
            <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Échéance</p>
                <p className={`mt-1 text-xs font-black ${overdue ? 'text-red-700' : 'text-slate-800'}`}>
                    {formatDateTime(plan.due_at)}
                </p>
            </div>
            <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Responsable</p>
                <p className={`mt-1 text-xs font-black ${plan.assigned_user_name ? 'text-slate-800' : 'text-amber-700'}`}>
                    {plan.assigned_user_name || 'À affecter'}
                </p>
            </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
                <button
                    onClick={() => onOpenClient(plan.client_id)}
                    className="inline-flex items-center gap-2 border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700"
                >
                    <UserRound className="h-4 w-4" />
                    Client
                </button>
                {plan.client_email && (
                    <button
                        onClick={() => onPreview(plan)}
                        disabled={working}
                        className="inline-flex items-center gap-2 bg-blue-600 px-3 py-2 text-xs font-black text-white disabled:bg-slate-300"
                    >
                        {working ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                        Préparer
                    </button>
                )}
                <button
                    onClick={() => onCancel(plan)}
                    disabled={working}
                    title="Ignorer cette relance"
                    className="inline-flex h-9 w-9 items-center justify-center border border-slate-200 bg-white text-slate-400 hover:border-red-200 hover:text-red-600 disabled:opacity-50"
                >
                    <X className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}

function ReminderRulesPanel({ rules, templates, users, savingRuleId, onSave }) {
    return (
        <div className="border-b border-slate-200 bg-slate-50">
            <div className="grid gap-3 px-5 py-4 lg:grid-cols-2">
                {rules.map(rule => (
                    <ReminderRuleEditor
                        key={rule.id}
                        rule={rule}
                        templates={templates}
                        users={users}
                        saving={savingRuleId === rule.id}
                        onSave={onSave}
                    />
                ))}
            </div>
            {!rules.length && (
                <div className="px-5 py-8 text-center text-sm font-bold text-slate-500">
                    Chargement des règles de relance...
                </div>
            )}
        </div>
    );
}

function ReminderRuleEditor({ rule, templates, users, saving, onSave }) {
    const [draft, setDraft] = useState({
        delay_days: rule.delay_days,
        template_id: rule.template_id || '',
        assignment_strategy: rule.assignment_strategy,
        fixed_user_id: rule.fixed_user_id || '',
        is_active: rule.is_active,
    });

    useEffect(() => {
        setDraft({
            delay_days: rule.delay_days,
            template_id: rule.template_id || '',
            assignment_strategy: rule.assignment_strategy,
            fixed_user_id: rule.fixed_user_id || '',
            is_active: rule.is_active,
        });
    }, [rule]);

    const save = async () => {
        await onSave(rule.id, {
            delay_days: Number(draft.delay_days),
            template_id: draft.template_id ? Number(draft.template_id) : null,
            assignment_strategy: draft.assignment_strategy,
            fixed_user_id: draft.assignment_strategy === 'FIXED_USER' && draft.fixed_user_id
                ? Number(draft.fixed_user_id)
                : null,
            is_active: draft.is_active,
        });
    };

    return (
        <div className="border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-sm font-black text-slate-950">{STAGE_LABELS[rule.stage] || rule.name}</p>
                    <p className="mt-1 text-[10px] font-bold uppercase tracking-wide text-slate-400">{rule.name}</p>
                </div>
                <label className="flex items-center gap-2 text-xs font-black text-slate-600">
                    <input
                        type="checkbox"
                        checked={draft.is_active}
                        onChange={event => setDraft(current => ({ ...current, is_active: event.target.checked }))}
                        className="h-4 w-4"
                    />
                    Active
                </label>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label>
                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Délai après entrée</span>
                    <div className="mt-1 flex items-center border border-slate-200 bg-slate-50">
                        <input
                            type="number"
                            min="0"
                            max="90"
                            value={draft.delay_days}
                            onChange={event => setDraft(current => ({ ...current, delay_days: event.target.value }))}
                            className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm font-black outline-none"
                        />
                        <span className="pr-3 text-xs font-bold text-slate-500">jours</span>
                    </div>
                </label>
                <label>
                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Modèle email</span>
                    <select
                        value={draft.template_id}
                        onChange={event => setDraft(current => ({ ...current, template_id: event.target.value }))}
                        className="mt-1 w-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold outline-none"
                    >
                        <option value="">Modèle par défaut</option>
                        {templates.map(template => (
                            <option key={template.id} value={template.id}>{template.name}</option>
                        ))}
                    </select>
                </label>
                <label>
                    <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Affectation</span>
                    <select
                        value={draft.assignment_strategy}
                        onChange={event => setDraft(current => ({
                            ...current,
                            assignment_strategy: event.target.value,
                            fixed_user_id: event.target.value === 'FIXED_USER' ? current.fixed_user_id : '',
                        }))}
                        className="mt-1 w-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold outline-none"
                    >
                        <option value="OPPORTUNITY_OWNER">Responsable opportunité</option>
                        <option value="FIXED_USER">Utilisateur fixe</option>
                    </select>
                </label>
                {draft.assignment_strategy === 'FIXED_USER' && (
                    <label>
                        <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Responsable fixe</span>
                        <select
                            value={draft.fixed_user_id}
                            onChange={event => setDraft(current => ({ ...current, fixed_user_id: event.target.value }))}
                            className="mt-1 w-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold outline-none"
                        >
                            <option value="">Sélectionner</option>
                            {users.map(user => (
                                <option key={user.id} value={user.id}>
                                    {[user.first_name, user.last_name].filter(Boolean).join(' ') || user.username}
                                </option>
                            ))}
                        </select>
                    </label>
                )}
            </div>
            <div className="mt-4 flex justify-end">
                <button
                    onClick={save}
                    disabled={saving || (draft.assignment_strategy === 'FIXED_USER' && !draft.fixed_user_id)}
                    className="inline-flex items-center gap-2 bg-slate-950 px-3 py-2 text-xs font-black text-white disabled:bg-slate-300"
                >
                    {saving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                    Enregistrer
                </button>
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

function CockpitOpportunityActionModal({ action, users, saving, onClose, onSubmit }) {
    const { mode, item } = action;
    const [form, setForm] = useState({
        owner_user_id: item.owner_user_id ? String(item.owner_user_id) : '',
        activity_type: 'appel',
        subject: item.suggested_subject || `Relancer ${item.client_name}`,
        note: item.reason || '',
        due_at: defaultActionDate(),
    });

    useEffect(() => {
        setForm({
            owner_user_id: item.owner_user_id ? String(item.owner_user_id) : '',
            activity_type: 'appel',
            subject: item.suggested_subject || `Relancer ${item.client_name}`,
            note: item.reason || '',
            due_at: defaultActionDate(),
        });
    }, [item, mode]);

    const submit = event => {
        event.preventDefault();
        if (mode === 'assign') {
            const owner = users.find(user => String(user.id) === form.owner_user_id);
            if (!owner) return;
            onSubmit({
                owner_user_id: form.owner_user_id,
                owner_name: [owner.first_name, owner.last_name].filter(Boolean).join(' ') || owner.username,
            });
            return;
        }
        if (!form.subject.trim() || !form.due_at) return;
        onSubmit(form);
    };

    const isValid = mode === 'assign'
        ? Boolean(form.owner_user_id)
        : Boolean(form.subject.trim() && form.due_at);

    return (
        <div className="fixed inset-0 z-[125] flex items-center justify-center bg-slate-950/60 p-3 backdrop-blur-sm">
            <form onSubmit={submit} className="w-full max-w-xl overflow-hidden bg-white shadow-2xl">
                <header className="flex items-start justify-between gap-4 bg-slate-950 px-5 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-300">
                            {item.reference || 'Action commerciale'}
                        </p>
                        <h3 className="mt-1 text-xl font-black">
                            {mode === 'assign' ? 'Affecter le dossier' : 'Planifier la prochaine action'}
                        </h3>
                        <p className="mt-1 text-xs font-semibold text-slate-300">
                            {item.client_name} · {item.title}
                        </p>
                    </div>
                    <button type="button" onClick={onClose} title="Fermer" className="p-2 text-slate-300 hover:text-white">
                        <X className="h-5 w-5" />
                    </button>
                </header>

                <div className="space-y-4 p-5">
                    {mode === 'assign' ? (
                        <label className="block">
                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Responsable commercial</span>
                            <select
                                value={form.owner_user_id}
                                onChange={event => setForm(current => ({ ...current, owner_user_id: event.target.value }))}
                                autoFocus
                                className="mt-2 w-full border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                            >
                                <option value="">Sélectionner un responsable</option>
                                {users.map(user => (
                                    <option key={user.id} value={user.id}>
                                        {[user.first_name, user.last_name].filter(Boolean).join(' ') || user.username}
                                    </option>
                                ))}
                            </select>
                            <p className="mt-2 text-xs font-semibold text-slate-500">
                                Les relances encore en attente seront transférées au même responsable.
                            </p>
                        </label>
                    ) : (
                        <>
                            <div className="grid gap-4 sm:grid-cols-2">
                                <label>
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Type d'action</span>
                                    <select
                                        value={form.activity_type}
                                        onChange={event => setForm(current => ({ ...current, activity_type: event.target.value }))}
                                        className="mt-2 w-full border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                                    >
                                        <option value="appel">Appel</option>
                                        <option value="email">Email</option>
                                        <option value="rendez_vous">Rendez-vous</option>
                                        <option value="tache">Tâche</option>
                                    </select>
                                </label>
                                <label>
                                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Échéance</span>
                                    <input
                                        type="datetime-local"
                                        value={form.due_at}
                                        onChange={event => setForm(current => ({ ...current, due_at: event.target.value }))}
                                        className="mt-2 w-full border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                                    />
                                </label>
                            </div>
                            <label className="block">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Action attendue</span>
                                <input
                                    value={form.subject}
                                    onChange={event => setForm(current => ({ ...current, subject: event.target.value }))}
                                    autoFocus
                                    maxLength={255}
                                    className="mt-2 w-full border border-slate-200 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                                />
                            </label>
                            <label className="block">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Contexte utile</span>
                                <textarea
                                    value={form.note}
                                    onChange={event => setForm(current => ({ ...current, note: event.target.value }))}
                                    rows={3}
                                    className="mt-2 w-full resize-none border border-slate-200 px-3 py-3 text-sm font-semibold text-slate-700 outline-none focus:border-blue-500"
                                />
                            </label>
                        </>
                    )}
                </div>

                <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4">
                    <button
                        type="button"
                        onClick={onClose}
                        className="border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-600"
                    >
                        Annuler
                    </button>
                    <button
                        type="submit"
                        disabled={saving || !isValid}
                        className="inline-flex items-center gap-2 bg-blue-600 px-4 py-2.5 text-sm font-black text-white disabled:bg-slate-300"
                    >
                        {saving
                            ? <RefreshCw className="h-4 w-4 animate-spin" />
                            : mode === 'assign'
                                ? <UserPlus className="h-4 w-4" />
                                : <CalendarPlus className="h-4 w-4" />}
                        {mode === 'assign' ? 'Affecter' : 'Planifier'}
                    </button>
                </footer>
            </form>
        </div>
    );
}

function EmailComposer({
    composer,
    templates,
    confirmed,
    sending,
    onClose,
    onChange,
    onTemplateChange,
    onConfirmChange,
    onSend,
}) {
    return (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/60 p-3 backdrop-blur-sm">
            <div className="flex max-h-[94vh] w-full max-w-3xl flex-col overflow-hidden bg-white shadow-2xl">
                <header className="flex items-start justify-between gap-4 bg-slate-950 px-5 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-300">Relance contrôlée</p>
                        <h3 className="mt-1 text-xl font-black">Prévisualiser l’email</h3>
                        <p className="mt-1 text-xs font-semibold text-slate-300">
                            {composer.reminder.client_name} · aucun envoi sans votre confirmation.
                        </p>
                    </div>
                    <button onClick={onClose} title="Fermer" className="p-2 text-slate-300 hover:text-white">
                        <X className="h-5 w-5" />
                    </button>
                </header>

                <div className="min-h-0 space-y-4 overflow-y-auto p-5">
                    {!composer.smtp_configured && (
                        <div className="border-l-4 border-amber-500 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-900">
                            SMTP non configuré : vous pouvez préparer le message, mais il ne quittera pas la plateforme.
                        </div>
                    )}

                    <label className="block">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Modèle</span>
                        <select
                            value={composer.template_id}
                            onChange={event => onTemplateChange(event.target.value)}
                            className="mt-2 w-full border border-slate-200 bg-slate-50 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                        >
                            {templates.map(template => (
                                <option key={template.id} value={template.id}>{template.name}</option>
                            ))}
                        </select>
                    </label>

                    <label className="block">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Destinataire</span>
                        <input
                            type="email"
                            value={composer.recipient}
                            onChange={event => onChange({ recipient: event.target.value })}
                            className="mt-2 w-full border border-slate-200 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                        />
                    </label>

                    <label className="block">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Objet</span>
                        <input
                            value={composer.subject}
                            onChange={event => onChange({ subject: event.target.value })}
                            className="mt-2 w-full border border-slate-200 px-3 py-3 text-sm font-bold text-slate-900 outline-none focus:border-blue-500"
                        />
                    </label>

                    <label className="block">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Message</span>
                        <textarea
                            rows={11}
                            value={composer.message}
                            onChange={event => onChange({ message: event.target.value })}
                            className="mt-2 w-full resize-y border border-slate-200 px-3 py-3 text-sm font-medium leading-6 text-slate-900 outline-none focus:border-blue-500"
                        />
                    </label>

                    <label className="flex items-start gap-3 border border-slate-200 bg-slate-50 px-4 py-4">
                        <input
                            type="checkbox"
                            checked={confirmed}
                            onChange={event => onConfirmChange(event.target.checked)}
                            className="mt-0.5 h-5 w-5"
                        />
                        <span className="text-sm font-bold text-slate-700">
                            J’ai vérifié le destinataire, l’objet et le contenu. J’autorise cet envoi.
                        </span>
                    </label>
                </div>

                <footer className="flex flex-col-reverse gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4 sm:flex-row sm:justify-end">
                    <button onClick={onClose} className="border border-slate-300 bg-white px-5 py-3 text-sm font-black text-slate-700">
                        Annuler
                    </button>
                    <button
                        onClick={onSend}
                        disabled={!confirmed || !composer.recipient.trim() || !composer.subject.trim() || !composer.message.trim() || sending}
                        className="inline-flex items-center justify-center gap-2 bg-blue-600 px-5 py-3 text-sm font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                        {sending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                        Envoyer la relance
                    </button>
                </footer>
            </div>
        </div>
    );
}
