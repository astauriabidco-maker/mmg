import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AlertTriangle,
    ArrowRight,
    BellRing,
    CalendarClock,
    Check,
    ClipboardList,
    Clock3,
    History,
    Mail,
    RefreshCw,
    Send,
    Target,
    TrendingUp,
    UserRound,
    X,
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

export default function CRMCockpit({ onOpenClient, onOpenMeasure }) {
    const [horizonDays, setHorizonDays] = useState(14);
    const [workingKey, setWorkingKey] = useState('');
    const [actionError, setActionError] = useState('');
    const [emailComposer, setEmailComposer] = useState(null);
    const [sendConfirmed, setSendConfirmed] = useState(false);
    const [notification, setNotification] = useState(null);

    const cockpitQuery = useQuery({
        queryKey: ['crm-cockpit', horizonDays],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/crm/cockpit', {
                params: { horizon_days: horizonDays, stale_days: 7 },
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
            await Promise.all([historyQuery.refetch(), cockpitQuery.refetch()]);
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
