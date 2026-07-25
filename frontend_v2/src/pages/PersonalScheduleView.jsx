import React, { useMemo, useState } from 'react';
import {
    AlertCircle,
    Bell,
    CalendarDays,
    CheckCircle2,
    ChevronRight,
    Clock3,
    Coffee,
    MapPin,
    RefreshCw,
    UserRound,
} from 'lucide-react';

const VIEW_OPTIONS = [
    { id: 'today', label: "Aujourd'hui" },
    { id: 'week', label: 'Cette semaine' },
];

const STATUS_META = {
    DONE: { label: 'Terminé', className: 'bg-emerald-50 text-emerald-700' },
    COMPLETED: { label: 'Terminé', className: 'bg-emerald-50 text-emerald-700' },
    FINISHED: { label: 'Terminé', className: 'bg-emerald-50 text-emerald-700' },
    CANCELLED: { label: 'Annulé', className: 'bg-slate-100 text-slate-500' },
    CANCELED: { label: 'Annulé', className: 'bg-slate-100 text-slate-500' },
    BLOCKED: { label: 'Bloqué', className: 'bg-rose-50 text-rose-700' },
    IN_PROGRESS: { label: 'En cours', className: 'bg-blue-50 text-blue-700' },
    STARTED: { label: 'En cours', className: 'bg-blue-50 text-blue-700' },
    READY: { label: 'Prêt', className: 'bg-cyan-50 text-cyan-700' },
    PLANNED: { label: 'Planifié', className: 'bg-indigo-50 text-indigo-700' },
    SCHEDULED: { label: 'Planifié', className: 'bg-indigo-50 text-indigo-700' },
    TODO: { label: 'À faire', className: 'bg-amber-50 text-amber-700' },
    PENDING: { label: 'À faire', className: 'bg-amber-50 text-amber-700' },
    APPROVED: { label: 'Validé', className: 'bg-slate-100 text-slate-600' },
};

const ACTION_BY_CATEGORY = {
    TASK: 'Réaliser la tâche',
    ORDER: 'Traiter la commande',
    MEETING: 'Participer au rendez-vous',
    INSTALLATION: 'Réaliser la pose',
    CRM: 'Effectuer le suivi client',
    REMINDER: 'Relancer le contact',
    MEASURE: 'Effectuer le métré',
    WORKSHOP: "Réaliser l'étape atelier",
    DELIVERY: 'Effectuer la livraison',
    PURCHASE: "Traiter l'action achat",
};

const COMPLETED_STATUSES = new Set(['DONE', 'COMPLETED', 'FINISHED', 'CANCELLED', 'CANCELED']);
const pad = (value) => String(value).padStart(2, '0');
const dayKey = (value) => {
    const date = new Date(value);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};
const startOfDay = (value) => {
    const date = new Date(value);
    date.setHours(0, 0, 0, 0);
    return date;
};
const addDays = (value, amount) => {
    const date = new Date(value);
    date.setDate(date.getDate() + amount);
    return date;
};
const mondayOf = (value) => {
    const date = startOfDay(value);
    const weekday = date.getDay() || 7;
    date.setDate(date.getDate() - weekday + 1);
    return date;
};
const normalizeStatus = (value) => String(value || 'TODO').toUpperCase();
const formatTime = (value) => new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
}).format(new Date(value));
const formatDay = (value, compact = false) => new Intl.DateTimeFormat('fr-FR', compact
    ? { weekday: 'short', day: 'numeric', month: 'short' }
    : { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(value));

function belongsToUser(event, currentUser) {
    if (!currentUser) return true;
    const userId = currentUser.id ?? currentUser.user_id;
    if (userId == null) return true;
    const ownerId = event.owner_id ?? event.assigned_user_id ?? event.user_id;
    return ownerId != null && String(ownerId) === String(userId);
}

function eventAction(event) {
    return event.action_expected
        || event.expected_action
        || event.next_action
        || ACTION_BY_CATEGORY[event.category]
        || 'Consulter les instructions';
}

function eventLocation(event) {
    return event.location
        || event.site_address
        || event.address
        || event.client_name
        || (event.category === 'WORKSHOP' ? 'Atelier MMG' : 'Lieu à confirmer');
}

function EventStatus({ status }) {
    const normalized = normalizeStatus(status);
    const meta = STATUS_META[normalized] || {
        label: normalized.replaceAll('_', ' ').toLowerCase(),
        className: 'bg-slate-100 text-slate-600',
    };
    return (
        <span className={`inline-flex min-h-7 items-center rounded px-2.5 text-[10px] font-black uppercase ${meta.className}`}>
            {meta.label}
        </span>
    );
}

function ScheduleRow({ event, onOpenEvent, highlighted = false }) {
    const clickable = typeof onOpenEvent === 'function';
    const Component = clickable ? 'button' : 'div';
    const endLabel = event.end_at ? ` – ${formatTime(event.end_at)}` : '';
    return (
        <Component
            type={clickable ? 'button' : undefined}
            onClick={clickable ? () => onOpenEvent(event) : undefined}
            className={`grid min-h-24 w-full grid-cols-[4.25rem_minmax(0,1fr)_auto] items-start gap-3 border-b border-slate-200 px-4 py-4 text-left last:border-b-0 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:px-5 ${
                highlighted ? 'bg-blue-50/70' : 'bg-white'
            } ${clickable ? 'transition hover:bg-slate-50 active:bg-slate-100' : ''}`}
        >
            <div className="pt-0.5">
                <p className="text-sm font-black tabular-nums text-slate-950">{formatTime(event.start_at)}</p>
                <p className="mt-1 hidden text-[11px] font-bold text-slate-400 sm:block">{endLabel || 'Horaire prévu'}</p>
            </div>
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <h3 className="min-w-0 text-sm font-black leading-5 text-slate-950 sm:text-base">{event.title}</h3>
                    <EventStatus status={event.status} />
                </div>
                <p className="mt-1.5 flex items-start gap-1.5 text-xs font-bold text-blue-700 sm:text-sm">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{eventAction(event)}</span>
                </p>
                <p className="mt-1.5 flex items-start gap-1.5 text-xs font-semibold text-slate-500">
                    <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span className="line-clamp-2">{eventLocation(event)}</span>
                </p>
                {event.reference && (
                    <p className="mt-1 text-[10px] font-black uppercase tracking-wide text-slate-400">{event.reference}</p>
                )}
            </div>
            {clickable && <ChevronRight className="mt-2 h-5 w-5 shrink-0 text-slate-300" />}
        </Component>
    );
}

function AbsenceRow({ event }) {
    return (
        <div className="flex min-h-16 items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 last:border-b-0 sm:px-5">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded bg-slate-200 text-slate-600">
                <Coffee className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-black text-slate-800">{event.title || 'Indisponibilité'}</p>
                <p className="mt-0.5 text-xs font-semibold text-slate-500">
                    {formatDay(event.start_at, true)} · {formatTime(event.start_at)}
                    {event.end_at ? ` – ${formatTime(event.end_at)}` : ''}
                </p>
            </div>
            <span className="text-[10px] font-black uppercase text-slate-500">Absent</span>
        </div>
    );
}

function LoadingState() {
    return (
        <div className="divide-y divide-slate-200 border-y border-slate-200 bg-white" aria-label="Chargement du planning">
            {[0, 1, 2].map((item) => (
                <div key={item} className="grid min-h-24 grid-cols-[4.25rem_1fr] gap-3 px-4 py-4 sm:grid-cols-[6rem_1fr] sm:px-5">
                    <div className="h-4 w-12 animate-pulse rounded bg-slate-200" />
                    <div>
                        <div className="h-4 w-2/3 animate-pulse rounded bg-slate-200" />
                        <div className="mt-3 h-3 w-1/2 animate-pulse rounded bg-slate-100" />
                        <div className="mt-2 h-3 w-3/4 animate-pulse rounded bg-slate-100" />
                    </div>
                </div>
            ))}
        </div>
    );
}

function EmptyState({ view }) {
    return (
        <div className="border-y border-slate-200 bg-white px-5 py-12 text-center">
            <CheckCircle2 className="mx-auto h-9 w-9 text-emerald-500" />
            <h3 className="mt-3 text-base font-black text-slate-900">Aucune tâche planifiée</h3>
            <p className="mx-auto mt-1 max-w-sm text-sm font-medium text-slate-500">
                {view === 'today'
                    ? "Votre journée est libre pour l'instant."
                    : "Aucune intervention n'est prévue cette semaine."}
            </p>
        </div>
    );
}

export default function PersonalScheduleView({
    events = [],
    currentUser = null,
    loading = false,
    onOpenEvent,
    onRefresh,
    notifications = [],
}) {
    const [view, setView] = useState('today');
    const now = new Date();
    const todayStart = startOfDay(now);
    const todayEnd = addDays(todayStart, 1);
    const weekStart = mondayOf(now);
    const weekEnd = addDays(weekStart, 7);

    const personalEvents = useMemo(() => events
        .filter((event) => event?.start_at && belongsToUser(event, currentUser))
        .sort((left, right) => new Date(left.start_at) - new Date(right.start_at)), [events, currentUser]);

    const rangeStart = view === 'today' ? todayStart : weekStart;
    const rangeEnd = view === 'today' ? todayEnd : weekEnd;
    const visibleEvents = personalEvents.filter((event) => {
        const start = new Date(event.start_at);
        const end = new Date(event.end_at || event.start_at);
        return start < rangeEnd && end >= rangeStart;
    });
    const absences = visibleEvents.filter((event) => event.category === 'ABSENCE' || event.source_type === 'USER_ABSENCE');
    const tasks = visibleEvents.filter((event) => event.category !== 'ABSENCE' && event.source_type !== 'USER_ABSENCE');
    const upcomingTasks = personalEvents.filter((event) => (
        event.category !== 'ABSENCE'
        && event.source_type !== 'USER_ABSENCE'
        && new Date(event.end_at || event.start_at) >= now
        && !COMPLETED_STATUSES.has(normalizeStatus(event.status))
    ));
    const nextTask = upcomingTasks[0] || null;
    const groupedTasks = tasks.reduce((groups, event) => {
        const key = dayKey(event.start_at);
        if (!groups[key]) groups[key] = [];
        groups[key].push(event);
        return groups;
    }, {});
    const displayName = currentUser?.full_name
        || currentUser?.name
        || currentUser?.username
        || 'Mon planning';

    return (
        <main className="min-h-[calc(100vh-64px)] bg-slate-50 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-slate-950">
            <header className="border-b border-slate-200 bg-white px-4 pb-4 pt-[max(1rem,env(safe-area-inset-top))] sm:px-6 lg:px-8">
                <div className="mx-auto flex max-w-5xl items-start justify-between gap-3">
                    <div className="min-w-0">
                        <p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-blue-600">
                            <UserRound className="h-3.5 w-3.5" /> Planning personnel
                        </p>
                        <h1 className="mt-1 truncate text-xl font-black sm:text-2xl">{displayName}</h1>
                        <p className="mt-1 text-xs font-semibold capitalize text-slate-500">{formatDay(now)}</p>
                    </div>
                    {onRefresh && (
                        <button
                            type="button"
                            onClick={onRefresh}
                            disabled={loading}
                            className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                            title="Actualiser le planning"
                            aria-label="Actualiser le planning"
                        >
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </button>
                    )}
                </div>
                <div className="mx-auto mt-4 flex max-w-5xl rounded-md bg-slate-100 p-1">
                    {VIEW_OPTIONS.map((option) => (
                        <button
                            key={option.id}
                            type="button"
                            onClick={() => setView(option.id)}
                            className={`min-h-10 flex-1 rounded px-3 text-sm font-black transition ${
                                view === option.id ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'
                            }`}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            </header>

            <div className="mx-auto max-w-5xl">
                {notifications.length > 0 && (
                    <section className="border-b border-amber-200 bg-amber-50 px-4 py-3 sm:px-6 lg:px-8">
                        <p className="flex items-center gap-2 text-xs font-black text-amber-900">
                            <Bell className="h-4 w-4" />
                            {notifications.length} nouvelle{notifications.length > 1 ? 's' : ''} affectation{notifications.length > 1 ? 's' : ''} ou modification{notifications.length > 1 ? 's' : ''}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs font-semibold text-amber-800">{notifications[0]?.message}</p>
                    </section>
                )}
                {!loading && nextTask && (
                    <section className="border-b border-blue-200 bg-blue-600 px-4 py-5 text-white sm:px-6 lg:px-8">
                        <p className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-blue-100">
                            <Clock3 className="h-4 w-4" /> Prochaine tâche
                        </p>
                        <button
                            type="button"
                            onClick={() => onOpenEvent?.(nextTask)}
                            className="mt-3 flex w-full items-start justify-between gap-3 text-left"
                            disabled={!onOpenEvent}
                        >
                            <div className="min-w-0">
                                <h2 className="text-lg font-black leading-6">{nextTask.title}</h2>
                                <p className="mt-1 text-sm font-bold text-blue-100">
                                    {formatDay(nextTask.start_at, true)} · {formatTime(nextTask.start_at)}
                                    {nextTask.end_at ? ` – ${formatTime(nextTask.end_at)}` : ''}
                                </p>
                                <p className="mt-2 flex items-start gap-1.5 text-sm font-semibold text-white">
                                    <MapPin className="mt-0.5 h-4 w-4 shrink-0" />
                                    <span>{eventLocation(nextTask)}</span>
                                </p>
                            </div>
                            {onOpenEvent && <ChevronRight className="mt-2 h-5 w-5 shrink-0 text-blue-100" />}
                        </button>
                    </section>
                )}

                {absences.length > 0 && (
                    <section aria-labelledby="absence-heading">
                        <div className="flex items-center gap-2 bg-slate-100 px-4 py-3 sm:px-5">
                            <AlertCircle className="h-4 w-4 text-slate-500" />
                            <h2 id="absence-heading" className="text-xs font-black uppercase tracking-wide text-slate-600">
                                Indisponibilité
                            </h2>
                        </div>
                        {absences.map((event) => <AbsenceRow key={event.id} event={event} />)}
                    </section>
                )}

                <section aria-labelledby="schedule-heading">
                    <div className="flex items-center justify-between gap-3 px-4 py-4 sm:px-5">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Interventions</p>
                            <h2 id="schedule-heading" className="mt-1 text-lg font-black">
                                {view === 'today' ? "Programme d'aujourd'hui" : 'Programme de la semaine'}
                            </h2>
                        </div>
                        <span className="shrink-0 text-sm font-black text-slate-500">
                            {tasks.length} {tasks.length > 1 ? 'tâches' : 'tâche'}
                        </span>
                    </div>

                    {loading ? <LoadingState /> : tasks.length === 0 ? <EmptyState view={view} /> : (
                        <div>
                            {Object.entries(groupedTasks).map(([key, dayEvents]) => (
                                <div key={key}>
                                    {view === 'week' && (
                                        <div className="sticky top-0 z-10 border-y border-slate-200 bg-slate-100/95 px-4 py-2.5 backdrop-blur sm:px-5">
                                            <p className="text-xs font-black capitalize text-slate-700">{formatDay(dayEvents[0].start_at)}</p>
                                        </div>
                                    )}
                                    <div className="border-y border-slate-200 bg-white">
                                        {dayEvents.map((event) => (
                                            <ScheduleRow
                                                key={event.id}
                                                event={event}
                                                onOpenEvent={onOpenEvent}
                                                highlighted={nextTask?.id === event.id}
                                            />
                                        ))}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            </div>
        </main>
    );
}
