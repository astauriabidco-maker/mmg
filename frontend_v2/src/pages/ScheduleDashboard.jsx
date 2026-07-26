import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    AlertTriangle,
    ArrowLeft,
    ArrowRight,
    Ban,
    CalendarClock,
    CalendarDays,
    CheckCircle2,
    ExternalLink,
    Filter,
    Pause,
    Play,
    Plus,
    RefreshCw,
    Search,
    Save,
    Sparkles,
    Settings2,
    Timer,
    Trash2,
    UserRound,
    X,
} from 'lucide-react';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';
import PersonalScheduleView from './PersonalScheduleView';
import PlanningSettingsModal from '../components/PlanningSettingsModal';

const DAY_NAMES = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const CATEGORY_META = {
    TASK: { label: 'Tâche', tone: 'bg-slate-900 text-white border-slate-900' },
    ORDER: { label: 'Commande', tone: 'bg-indigo-50 text-indigo-800 border-indigo-200' },
    MEETING: { label: 'Rendez-vous', tone: 'bg-fuchsia-50 text-fuchsia-800 border-fuchsia-200' },
    INSTALLATION: { label: 'Pose', tone: 'bg-cyan-50 text-cyan-800 border-cyan-200' },
    CRM: { label: 'CRM', tone: 'bg-blue-50 text-blue-800 border-blue-200' },
    REMINDER: { label: 'Relance', tone: 'bg-amber-50 text-amber-800 border-amber-200' },
    MEASURE: { label: 'Métré', tone: 'bg-violet-50 text-violet-800 border-violet-200' },
    WORKSHOP: { label: 'Atelier', tone: 'bg-orange-50 text-orange-800 border-orange-200' },
    DELIVERY: { label: 'Livraison', tone: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
    PURCHASE: { label: 'Achat', tone: 'bg-rose-50 text-rose-800 border-rose-200' },
    ABSENCE: { label: 'Indisponibilité', tone: 'bg-slate-100 text-slate-700 border-slate-300' },
};
const EXECUTABLE_SOURCES = new Set([
    'CALENDAR_TASK',
    'CRM_ACTIVITY',
    'CRM_MILESTONE',
    'CRM_REMINDER',
    'MEASURE_MISSION',
    'WORKSHOP',
    'DELIVERY',
]);
const EXECUTION_STATUS_META = {
    TODO: { label: 'À faire', tone: 'bg-slate-100 text-slate-700' },
    IN_PROGRESS: { label: 'En cours', tone: 'bg-blue-50 text-blue-700' },
    PAUSED: { label: 'En pause', tone: 'bg-amber-50 text-amber-700' },
    BLOCKED: { label: 'Bloqué', tone: 'bg-red-50 text-red-700' },
    DONE: { label: 'Terminé', tone: 'bg-emerald-50 text-emerald-700' },
};

const pad = (value) => String(value).padStart(2, '0');
const localDateKey = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const toInputDateTime = (value) => {
    const date = value ? new Date(value) : new Date();
    return `${localDateKey(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};
const mondayOf = (value) => {
    const date = new Date(value);
    date.setHours(0, 0, 0, 0);
    const day = date.getDay() || 7;
    date.setDate(date.getDate() - day + 1);
    return date;
};
const addDays = (value, count) => {
    const date = new Date(value);
    date.setDate(date.getDate() + count);
    return date;
};
const addMonths = (value, count) => {
    const date = new Date(value);
    date.setDate(1);
    date.setMonth(date.getMonth() + count);
    return date;
};
const addHours = (value, count) => new Date(new Date(value).getTime() + count * 60 * 60 * 1000);
const formatTime = (value) => new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
}).format(new Date(value));
const formatLongDate = (value) => new Intl.DateTimeFormat('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
}).format(new Date(value));
const roundHours = (value) => Math.round(value * 10) / 10;
const formatExecutionDuration = (minutes = 0) => {
    const total = Math.max(Number(minutes) || 0, 0);
    const hours = Math.floor(total / 60);
    const remainder = total % 60;
    if (!hours) return `${remainder} min`;
    return remainder ? `${hours} h ${remainder} min` : `${hours} h`;
};
const executionActionLabel = (action) => ({
    START: 'Démarrage / reprise',
    PAUSE: 'Mise en pause',
    BLOCK: 'Blocage',
    COMPLETE: 'Tâche terminée',
}[action] || action);
const eventDurationHours = (event) => {
    if (!event.start_at) return 0;
    const start = new Date(event.start_at);
    const end = event.end_at ? new Date(event.end_at) : addHours(start, 1);
    return Math.max((end - start) / (60 * 60 * 1000), 0.5);
};
const overlaps = (left, right) => (
    new Date(left.start_at) < new Date(right.end_at || addHours(right.start_at, 1))
    && new Date(right.start_at) < new Date(left.end_at || addHours(left.start_at, 1))
);
const countConflicts = (events) => events.reduce((total, event, index) => (
    total + (events.slice(index + 1).some((candidate) => overlaps(event, candidate)) ? 1 : 0)
), 0);
const firstDefined = (...values) => values.find((value) => value !== undefined && value !== null);

function getPeriod(anchor, view) {
    if (view === 'day') {
        const start = new Date(anchor);
        start.setHours(0, 0, 0, 0);
        return { start, end: addDays(start, 1) };
    }
    if (view === 'week' || view === 'team') {
        const start = mondayOf(anchor);
        return { start, end: addDays(start, 7) };
    }
    const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const start = mondayOf(monthStart);
    return { start, end: addDays(start, 42) };
}

function EventChip({ event, compact = false, onOpen, onDragStart }) {
    const meta = CATEGORY_META[event.category] || CATEGORY_META.TASK;
    return (
        <button
            type="button"
            draggable={event.editable}
            onDragStart={(dragEvent) => onDragStart?.(dragEvent, event)}
            onClick={(clickEvent) => {
                clickEvent.stopPropagation();
                onOpen(event);
            }}
            className={`w-full border text-left transition hover:shadow-sm ${compact ? 'rounded px-2 py-1' : 'rounded-md px-2.5 py-2'} ${meta.tone}`}
            title={`${meta.label} · ${event.title}`}
        >
            <span className="flex min-w-0 items-center gap-1.5">
                {event.start_at && <span className="shrink-0 text-[10px] font-black">{formatTime(event.start_at)}</span>}
                <span className="truncate text-xs font-bold">{event.title}</span>
            </span>
            {!compact && (
                <span className="mt-1 block truncate text-[10px] font-semibold opacity-70">
                    {event.owner_name || event.client_name || event.reference || meta.label}
                </span>
            )}
        </button>
    );
}

function ModalShell({ title, eyebrow, onClose, children, footer, wide = false }) {
    return (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm">
            <div className={`flex max-h-[92vh] w-full flex-col overflow-hidden rounded-lg bg-white shadow-2xl ${wide ? 'max-w-6xl' : 'max-w-2xl'}`}>
                <header className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">{eyebrow}</p>
                        <h2 className="mt-1 text-xl font-black text-slate-950">{title}</h2>
                    </div>
                    <button type="button" onClick={onClose} className="grid h-9 w-9 place-items-center rounded-md text-slate-500 hover:bg-slate-100" title="Fermer">
                        <X className="h-5 w-5" />
                    </button>
                </header>
                <div className="overflow-y-auto p-5">{children}</div>
                {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-4">{footer}</footer>}
            </div>
        </div>
    );
}

const initialTask = (date = new Date()) => {
    const start = new Date(date);
    start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0);
    const end = new Date(start.getTime() + 60 * 60 * 1000);
    return {
        title: '',
        description: '',
        category: 'TASK',
        priority: 'NORMAL',
        start_at: toInputDateTime(start),
        end_at: toInputDateTime(end),
        assigned_user_id: '',
        client_id: '',
        sale_order_id: '',
        location_label: '',
        location_address: '',
        latitude: null,
        longitude: null,
        required_headcount: 1,
        buffer_minutes_before: 15,
        buffer_minutes_after: 15,
        travel_minutes_before: 0,
        travel_minutes_after: 0,
        skill_requirements: [],
        resource_assignments: [],
    };
};

export default function ScheduleDashboard({ initialSettingsTab = null, onSettingsClosed }) {
    const queryClient = useQueryClient();
    const { user: authUser } = useAuth();
    const [view, setView] = useState(() => (
        typeof window !== 'undefined' && window.innerWidth < 768 ? 'day' : 'week'
    ));
    const [anchor, setAnchor] = useState(new Date());
    const [ownerId, setOwnerId] = useState('');
    const [typeFilter, setTypeFilter] = useState('ALL');
    const [search, setSearch] = useState('');
    const [selectedEvent, setSelectedEvent] = useState(null);
    const [createForm, setCreateForm] = useState(null);
    const [editForm, setEditForm] = useState(null);
    const [notice, setNotice] = useState(null);
    const [conflictRetry, setConflictRetry] = useState(null);
    const [availabilityOpen, setAvailabilityOpen] = useState(false);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [settingsTab, setSettingsTab] = useState(initialSettingsTab || 'skills');
    const [suggestions, setSuggestions] = useState([]);
    const period = useMemo(() => getPeriod(anchor, view), [anchor, view]);

    const metaQuery = useQuery({
        queryKey: ['schedule-meta', authUser?.username],
        queryFn: async () => (await api.get('/v2/schedule/meta')).data,
    });

    useEffect(() => {
        if (!initialSettingsTab || metaQuery.isLoading) return;
        if (!metaQuery.data?.can_manage_resources) {
            setNotice({
                type: 'error',
                text: "Votre profil ne peut pas gérer les compétences et ressources du planning.",
            });
            if (onSettingsClosed) onSettingsClosed();
            return;
        }
        setSettingsTab(['skills', 'resources', 'closures'].includes(initialSettingsTab) ? initialSettingsTab : 'skills');
        setSettingsOpen(true);
    }, [
        initialSettingsTab,
        metaQuery.data?.can_manage_resources,
        metaQuery.isLoading,
        onSettingsClosed,
    ]);
    const personalMode = metaQuery.data?.can_edit === false;
    const currentUserRecord = (metaQuery.data?.users || []).find(
        (user) => user.username === authUser?.username,
    );
    const eventPeriod = personalMode
        ? { start: mondayOf(anchor), end: addDays(mondayOf(anchor), 7) }
        : period;
    const eventOwnerId = personalMode ? (currentUserRecord?.id || '') : ownerId;
    const eventsQuery = useQuery({
        queryKey: [
            'schedule-events',
            eventPeriod.start.toISOString(),
            eventPeriod.end.toISOString(),
            eventOwnerId,
            typeFilter,
        ],
        queryFn: async () => (await api.get('/v2/schedule/events', {
            params: {
                start_at: eventPeriod.start.toISOString(),
                end_at: eventPeriod.end.toISOString(),
                owner_id: eventOwnerId || undefined,
                types: typeFilter === 'ALL' ? undefined : typeFilter,
                include_unscheduled: true,
            },
        })).data,
        enabled: !personalMode || Boolean(currentUserRecord?.id),
    });
    const notificationsQuery = useQuery({
        queryKey: ['planning-notifications'],
        queryFn: async () => (await api.get('/v2/schedule/notifications', {
            params: { unread_only: true },
        })).data,
        enabled: personalMode,
    });
    const capacityQuery = useQuery({
        queryKey: [
            'planning-capacity',
            period.start.toISOString(),
            period.end.toISOString(),
        ],
        queryFn: async () => (await api.get('/v2/schedule/capacity', {
            params: {
                start_at: period.start.toISOString(),
                end_at: period.end.toISOString(),
            },
        })).data,
        enabled: metaQuery.data?.can_edit === true,
    });

    const refresh = () => queryClient.invalidateQueries({ queryKey: ['schedule-events'] });
    const createMutation = useMutation({
        mutationFn: async (payload) => (await api.post('/v2/schedule/tasks', payload)).data,
        onSuccess: () => {
            setCreateForm(null);
            setNotice({ type: 'success', text: 'Action planifiée.' });
            refresh();
        },
        onError: (error, payload) => {
            const detail = error.response?.data?.detail;
            if (error.response?.status === 409 && detail?.conflicts) {
                setConflictRetry({ kind: 'create', payload, detail });
            } else {
                setNotice({ type: 'error', text: typeof detail === 'string' ? detail : 'La planification a échoué.' });
            }
        },
    });
    const suggestionMutation = useMutation({
        mutationFn: async (form) => {
            const start = new Date(form.start_at);
            const end = new Date(form.end_at);
            const durationMinutes = Math.max(Math.round((end - start) / 60000), 15);
            return (await api.post('/v2/schedule/suggestions', {
                title: form.title || 'Action à planifier',
                duration_minutes: durationMinutes,
                window_start: start.toISOString(),
                window_end: addDays(start, 14).toISOString(),
                required_skill_ids: (form.skill_requirements || []).map((item) => Number(item.skill_id)),
                required_resource_ids: (form.resource_assignments || []).map((item) => Number(item.resource_id)),
                location_label: form.location_label || null,
                latitude: form.latitude ?? null,
                longitude: form.longitude ?? null,
                travel_margin_minutes: Math.max(Number(form.buffer_minutes_before || 0), 15),
                step_minutes: 30,
                limit: 8,
            })).data;
        },
        onSuccess: setSuggestions,
        onError: (error) => setNotice({
            type: 'error',
            text: error.response?.data?.detail || 'Aucune suggestion disponible.',
        }),
    });
    const updateMutation = useMutation({
        mutationFn: async ({ event, payload }) => (
            await api.patch(`/v2/schedule/events/${event.source_type}/${event.source_id}`, payload)
        ).data,
        onSuccess: () => {
            setSelectedEvent(null);
            setEditForm(null);
            setNotice({ type: 'success', text: 'Planning mis à jour.' });
            refresh();
        },
        onError: (error, variables) => {
            const detail = error.response?.data?.detail;
            if (error.response?.status === 409 && detail?.conflicts) {
                setConflictRetry({ kind: 'update', payload: variables, detail });
            } else {
                setNotice({ type: 'error', text: typeof detail === 'string' ? detail : 'La modification a échoué.' });
            }
        },
    });
    const deleteMutation = useMutation({
        mutationFn: async (taskId) => api.delete(`/v2/schedule/tasks/${taskId}`),
        onSuccess: () => {
            setSelectedEvent(null);
            setEditForm(null);
            refresh();
        },
    });

    const allEvents = eventsQuery.data?.events || [];
    const normalizedSearch = search.trim().toLowerCase();
    const events = allEvents.filter((event) => !normalizedSearch || [
        event.title,
        event.reference,
        event.client_name,
        event.owner_name,
    ].some((value) => value?.toLowerCase().includes(normalizedSearch)));
    const unscheduled = (eventsQuery.data?.unscheduled || []).filter((event) => !normalizedSearch || [
        event.title,
        event.reference,
        event.client_name,
    ].some((value) => value?.toLowerCase().includes(normalizedSearch)));

    const moveAnchor = (direction) => {
        if (view === 'day') setAnchor(addDays(anchor, direction));
        else if (view === 'week' || view === 'team') setAnchor(addDays(anchor, direction * 7));
        else setAnchor(addMonths(anchor, direction));
    };
    const openEvent = (event) => {
        const fallbackStart = event.start_at ? new Date(event.start_at) : new Date(anchor);
        if (!event.start_at) fallbackStart.setHours(8, 0, 0, 0);
        setSelectedEvent(event);
        setEditForm({
            start_at: toInputDateTime(fallbackStart),
            end_at: event.end_at ? toInputDateTime(event.end_at) : toInputDateTime(addHours(fallbackStart, 1)),
            assigned_user_id: event.owner_id || '',
            status: event.status || '',
            change_reason: '',
        });
    };
    const dropOnDate = (dropEvent, targetDate) => {
        dropEvent.preventDefault();
        const raw = dropEvent.dataTransfer.getData('application/mmg-schedule');
        if (!raw) return;
        const event = JSON.parse(raw);
        const previousStart = event.start_at ? new Date(event.start_at) : new Date();
        const previousEnd = event.end_at ? new Date(event.end_at) : new Date(previousStart.getTime() + 60 * 60 * 1000);
        const duration = Math.max(previousEnd - previousStart, 30 * 60 * 1000);
        const nextStart = new Date(targetDate);
        nextStart.setHours(event.start_at ? previousStart.getHours() : 8, event.start_at ? previousStart.getMinutes() : 0, 0, 0);
        updateMutation.mutate({
            event,
            payload: {
                start_at: nextStart.toISOString(),
                end_at: new Date(nextStart.getTime() + duration).toISOString(),
                assigned_user_id: event.owner_id || undefined,
                change_reason: 'Réorganisation par glisser-déposer',
                source_screen: 'PLANNING_CALENDAR',
            },
        });
    };
    const dropOnTeamSlot = (dropEvent, targetDate, hour, assignedUserId) => {
        dropEvent.preventDefault();
        dropEvent.stopPropagation();
        const raw = dropEvent.dataTransfer.getData('application/mmg-schedule');
        if (!raw) return;
        const event = JSON.parse(raw);
        const previousStart = event.start_at ? new Date(event.start_at) : new Date();
        const previousEnd = event.end_at ? new Date(event.end_at) : addHours(previousStart, 1);
        const duration = Math.max(previousEnd - previousStart, 30 * 60 * 1000);
        const nextStart = new Date(targetDate);
        nextStart.setHours(hour, event.start_at ? previousStart.getMinutes() : 0, 0, 0);
        updateMutation.mutate({
            event,
            payload: {
                start_at: nextStart.toISOString(),
                end_at: new Date(nextStart.getTime() + duration).toISOString(),
                assigned_user_id: assignedUserId ? Number(assignedUserId) : null,
                change_reason: 'Réaffectation depuis la vue équipe',
                source_screen: 'PLANNING_TEAM',
            },
        });
    };
    const dragStart = (dragEvent, event) => {
        dragEvent.dataTransfer.setData('application/mmg-schedule', JSON.stringify(event));
        dragEvent.dataTransfer.effectAllowed = 'move';
    };
    const saveTask = () => createMutation.mutate({
        ...createForm,
        start_at: new Date(createForm.start_at).toISOString(),
        end_at: new Date(createForm.end_at).toISOString(),
        assigned_user_id: createForm.assigned_user_id ? Number(createForm.assigned_user_id) : null,
        client_id: createForm.client_id ? Number(createForm.client_id) : null,
        sale_order_id: createForm.sale_order_id ? Number(createForm.sale_order_id) : null,
        latitude: createForm.latitude ?? null,
        longitude: createForm.longitude ?? null,
    });
    const saveEvent = () => updateMutation.mutate({
        event: selectedEvent,
        payload: {
            start_at: new Date(editForm.start_at).toISOString(),
            end_at: new Date(editForm.end_at).toISOString(),
            assigned_user_id: editForm.assigned_user_id ? Number(editForm.assigned_user_id) : null,
            change_reason: editForm.change_reason || 'Mise à jour depuis la fiche planning',
            source_screen: 'PLANNING_DETAIL',
        },
    });

    const periodTitle = view === 'day'
        ? formatLongDate(anchor)
        : view === 'week' || view === 'team'
            ? `${new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' }).format(period.start)} au ${new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }).format(addDays(period.end, -1))}`
            : new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' }).format(anchor);

    if (personalMode) {
        return (
            <>
                <PersonalScheduleView
                    events={events}
                    currentUser={{ ...authUser, ...currentUserRecord }}
                    loading={metaQuery.isLoading || eventsQuery.isLoading}
                    notifications={notificationsQuery.data || []}
                    onRefresh={() => eventsQuery.refetch()}
                    onOpenEvent={openEvent}
                />
                {selectedEvent && (
                    <ModalShell
                        eyebrow={CATEGORY_META[selectedEvent.category]?.label || 'Planning'}
                        title={selectedEvent.title}
                        onClose={() => { setSelectedEvent(null); setEditForm(null); }}
                        footer={selectedEvent.source_url ? (
                            <a href={selectedEvent.source_url} className="flex h-10 items-center gap-2 rounded-md border border-slate-200 px-4 text-sm font-black text-slate-700">
                                <ExternalLink className="h-4 w-4" /> Ouvrir le dossier
                            </a>
                        ) : null}
                    >
                        <ExecutionPanel event={selectedEvent} />
                    </ModalShell>
                )}
            </>
        );
    }

    return (
        <div className="min-h-[calc(100vh-88px)] bg-white">
            <section className="border-b border-slate-200 px-4 py-4 sm:px-6 xl:px-8">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-2">
                            <CalendarDays className="h-5 w-5 text-blue-600" />
                            <h2 className="text-xl font-black text-slate-950">Planning & Agenda</h2>
                        </div>
                        <p className="mt-1 text-sm font-medium text-slate-500">CRM, métrés, atelier, livraisons et échéances dans une vue commune.</p>
                    </div>
                    {metaQuery.data?.can_edit && (
                        <div className="flex flex-wrap gap-2">
                            {metaQuery.data?.can_manage_availability && (
                                <button
                                    type="button"
                                    onClick={() => setAvailabilityOpen(true)}
                                    className="flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 hover:bg-slate-50"
                                >
                                    <CalendarClock className="h-4 w-4" /> Disponibilités
                                </button>
                            )}
                            {metaQuery.data?.can_manage_resources && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        setSettingsTab('skills');
                                        setSettingsOpen(true);
                                    }}
                                    className="flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-700 hover:bg-slate-50"
                                >
                                    <Settings2 className="h-4 w-4" /> Compétences & ressources
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={() => {
                                    setSuggestions([]);
                                    setCreateForm(initialTask(anchor));
                                }}
                                className="flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white hover:bg-blue-700"
                            >
                                <Plus className="h-4 w-4" /> Planifier
                            </button>
                        </div>
                    )}
                </div>

                <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                    <div className="flex flex-wrap items-center gap-2">
                        <button type="button" onClick={() => moveAnchor(-1)} className="grid h-9 w-9 place-items-center rounded-md border border-slate-200 hover:bg-slate-50" title="Période précédente"><ArrowLeft className="h-4 w-4" /></button>
                        <button type="button" onClick={() => setAnchor(new Date())} className="h-9 rounded-md border border-slate-200 px-3 text-xs font-black hover:bg-slate-50">Aujourd’hui</button>
                        <button type="button" onClick={() => moveAnchor(1)} className="grid h-9 w-9 place-items-center rounded-md border border-slate-200 hover:bg-slate-50" title="Période suivante"><ArrowRight className="h-4 w-4" /></button>
                        <h3 className="min-w-0 px-1 text-base font-black capitalize text-slate-900">{periodTitle}</h3>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <div className="flex h-9 items-center rounded-md border border-slate-200 bg-slate-50 p-1">
                            {[['day', 'Jour'], ['week', 'Semaine'], ['month', 'Mois'], ['team', 'Équipe']].map(([key, label]) => (
                                <button key={key} type="button" onClick={() => setView(key)} className={`h-7 rounded px-3 text-xs font-black ${view === key ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'}`}>{label}</button>
                            ))}
                        </div>
                        <button type="button" onClick={() => eventsQuery.refetch()} className="grid h-9 w-9 place-items-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50" title="Actualiser"><RefreshCw className={`h-4 w-4 ${eventsQuery.isFetching ? 'animate-spin' : ''}`} /></button>
                    </div>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-[minmax(220px,1fr)_220px_220px]">
                    <label className="relative">
                        <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Rechercher client, référence, responsable..." className="h-9 w-full rounded-md border border-slate-200 pl-9 pr-3 text-sm outline-none focus:border-blue-500" />
                    </label>
                    <label className="relative">
                        <Filter className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="h-9 w-full appearance-none rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm font-bold outline-none focus:border-blue-500">
                            <option value="ALL">Tous les flux</option>
                            {Object.entries(CATEGORY_META).map(([key, value]) => <option key={key} value={key}>{value.label}</option>)}
                        </select>
                    </label>
                    <label className="relative">
                        <UserRound className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                        <select value={ownerId} onChange={(event) => setOwnerId(event.target.value)} className="h-9 w-full appearance-none rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm font-bold outline-none focus:border-blue-500">
                            <option value="">Toute l’équipe</option>
                            {(metaQuery.data?.users || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                        </select>
                    </label>
                </div>
            </section>

            {notice && (
                <div className={`mx-4 mt-3 flex items-center justify-between rounded-md border px-4 py-3 text-sm font-bold sm:mx-6 xl:mx-8 ${notice.type === 'error' ? 'border-red-200 bg-red-50 text-red-800' : 'border-emerald-200 bg-emerald-50 text-emerald-800'}`}>
                    <span>{notice.text}</span>
                    <button type="button" onClick={() => setNotice(null)}><X className="h-4 w-4" /></button>
                </div>
            )}

            <div className="grid min-h-[650px] xl:grid-cols-[minmax(0,1fr)_300px]">
                <main className="min-w-0 border-r border-slate-200">
                    {eventsQuery.isLoading ? (
                        <div className="grid h-96 place-items-center text-sm font-bold text-slate-500">Chargement du planning...</div>
                    ) : view === 'team' ? (
                        <>
                            <TeamLoadCockpit
                                response={eventsQuery.data}
                                users={metaQuery.data?.users || []}
                                events={events}
                                ownerId={ownerId}
                            />
                            <CapacityBreakdown
                                data={capacityQuery.data}
                                stations={metaQuery.data?.stations || []}
                            />
                            <TeamView
                                date={anchor}
                                weekStart={period.start}
                                users={metaQuery.data?.users || []}
                                ownerId={ownerId}
                                events={events}
                                onSelectDate={setAnchor}
                                onOpen={openEvent}
                                onDrop={dropOnTeamSlot}
                                onDragStart={dragStart}
                            />
                        </>
                    ) : view === 'month' ? (
                        <MonthView anchor={anchor} events={events} onOpen={openEvent} onDrop={dropOnDate} onDragStart={dragStart} />
                    ) : view === 'week' ? (
                        <WeekView start={period.start} events={events} onOpen={openEvent} onDrop={dropOnDate} onDragStart={dragStart} />
                    ) : (
                        <DayView date={anchor} events={events} onOpen={openEvent} onDrop={dropOnDate} onDragStart={dragStart} />
                    )}
                </main>

                <aside className="bg-slate-50 px-4 py-5">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-amber-600">File opérationnelle</p>
                            <h3 className="mt-1 text-lg font-black text-slate-950">À planifier</h3>
                        </div>
                        <span className="rounded bg-white px-2 py-1 text-xs font-black text-slate-600 ring-1 ring-slate-200">{unscheduled.length}</span>
                    </div>
                    <p className="mt-1 text-xs font-semibold text-slate-500">Glissez une mission ou une tâche atelier sur une journée.</p>
                    <div className="mt-4 space-y-2">
                        {unscheduled.map((event) => (
                            <EventChip key={event.id} event={event} onOpen={openEvent} onDragStart={dragStart} />
                        ))}
                        {!unscheduled.length && (
                            <div className="border-t border-slate-200 py-8 text-center">
                                <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-500" />
                                <p className="mt-2 text-sm font-black text-slate-800">Tout est planifié</p>
                                <p className="mt-1 text-xs text-slate-500">Aucune mission ni tâche atelier en attente.</p>
                            </div>
                        )}
                    </div>
                    <div className="mt-6 border-t border-slate-200 pt-4">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Contrôle</p>
                        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                            {[['Planifiés', eventsQuery.data?.summary?.total || 0], ['En retard', eventsQuery.data?.summary?.overdue || 0], ['Non planifiés', unscheduled.length]].map(([label, value]) => (
                                <div key={label} className="bg-white px-2 py-3 ring-1 ring-slate-200">
                                    <strong className="block text-lg font-black text-slate-950">{value}</strong>
                                    <span className="text-[9px] font-bold uppercase text-slate-400">{label}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </aside>
            </div>

            {createForm && (
                <ModalShell
                    eyebrow="Nouvelle réservation"
                    title="Planifier une action"
                    onClose={() => setCreateForm(null)}
                    footer={<>
                        <button type="button" onClick={() => setCreateForm(null)} className="h-10 rounded-md border border-slate-200 px-4 text-sm font-black text-slate-700">Annuler</button>
                        <button type="button" disabled={!createForm.title || createMutation.isPending} onClick={saveTask} className="h-10 rounded-md bg-blue-600 px-5 text-sm font-black text-white disabled:opacity-40">Enregistrer</button>
                    </>}
                >
                    <TaskForm form={createForm} setForm={setCreateForm} meta={metaQuery.data} />
                    <div className="mt-5 rounded-md border border-blue-200 bg-blue-50 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <p className="font-black text-blue-950">Aide à l’affectation</p>
                                <p className="text-xs font-semibold text-blue-700">Contrôle compétences, horaires, congés, ressources, trajets et charge.</p>
                            </div>
                            <button
                                type="button"
                                onClick={() => suggestionMutation.mutate(createForm)}
                                disabled={!createForm.title || suggestionMutation.isPending}
                                className="flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40"
                            >
                                <Sparkles className="h-4 w-4" /> Suggérer
                            </button>
                        </div>
                        {suggestions.length > 0 && (
                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                {suggestions.slice(0, 6).map((suggestion) => (
                                    <button
                                        key={`${suggestion.candidate_id}-${suggestion.start}`}
                                        type="button"
                                        onClick={() => {
                                            setCreateForm((current) => ({
                                                ...current,
                                                assigned_user_id: suggestion.candidate_id,
                                                start_at: toInputDateTime(suggestion.start),
                                                end_at: toInputDateTime(suggestion.end),
                                            }));
                                        }}
                                        className="rounded-md border border-blue-200 bg-white p-3 text-left hover:border-blue-500"
                                    >
                                        <span className="block text-sm font-black text-slate-900">{suggestion.candidate_name}</span>
                                        <span className="mt-1 block text-xs font-bold text-slate-500">{new Date(suggestion.start).toLocaleString('fr-FR')} · score {suggestion.score}/100</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </ModalShell>
            )}

            {selectedEvent && (
                <ModalShell
                    eyebrow={CATEGORY_META[selectedEvent.category]?.label || 'Planning'}
                    title={selectedEvent.title}
                    onClose={() => { setSelectedEvent(null); setEditForm(null); }}
                    footer={<>
                        {selectedEvent.source_type === 'CALENDAR_TASK' && (
                            <button type="button" onClick={() => deleteMutation.mutate(selectedEvent.source_id)} className="mr-auto flex h-10 items-center gap-2 rounded-md border border-red-200 px-4 text-sm font-black text-red-700"><Trash2 className="h-4 w-4" /> Annuler la tâche</button>
                        )}
                        {selectedEvent.source_url && (
                            <a href={selectedEvent.source_url} className="flex h-10 items-center gap-2 rounded-md border border-slate-200 px-4 text-sm font-black text-slate-700"><ExternalLink className="h-4 w-4" /> Ouvrir le dossier</a>
                        )}
                        {selectedEvent.editable && eventsQuery.data?.can_edit && (
                            <button type="button" onClick={saveEvent} disabled={updateMutation.isPending} className="h-10 rounded-md bg-blue-600 px-5 text-sm font-black text-white">Mettre à jour</button>
                        )}
                    </>}
                >
                    <EventForm event={selectedEvent} form={editForm} setForm={setEditForm} meta={metaQuery.data} />
                </ModalShell>
            )}

            {conflictRetry && (
                <ModalShell
                    eyebrow="Conflit de planning"
                    title="Ce créneau est déjà occupé"
                    onClose={() => setConflictRetry(null)}
                    footer={<>
                        <button type="button" onClick={() => setConflictRetry(null)} className="h-10 rounded-md border border-slate-200 px-4 text-sm font-black">Modifier le créneau</button>
                        <button type="button" onClick={() => {
                            if (conflictRetry.kind === 'create') createMutation.mutate({ ...conflictRetry.payload, allow_conflict: true });
                            else updateMutation.mutate({ ...conflictRetry.payload, payload: { ...conflictRetry.payload.payload, allow_conflict: true } });
                            setConflictRetry(null);
                        }} className="h-10 rounded-md bg-amber-500 px-4 text-sm font-black text-slate-950">Planifier quand même</button>
                    </>}
                >
                    <div className="flex gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 text-amber-900">
                        <AlertTriangle className="h-5 w-5 shrink-0" />
                        <div>
                            <p className="font-black">{conflictRetry.detail.message}</p>
                            <div className="mt-3 space-y-2">
                                {conflictRetry.detail.conflicts.map((item) => (
                                    <p key={item.id} className="text-sm font-semibold">{formatTime(item.start_at)} · {item.title}</p>
                                ))}
                            </div>
                        </div>
                    </div>
                </ModalShell>
            )}
            {availabilityOpen && (
                <AvailabilityModal
                    period={period}
                    onClose={() => setAvailabilityOpen(false)}
                    onChanged={() => {
                        refresh();
                        metaQuery.refetch();
                    }}
                />
            )}
            {settingsOpen && (
                <PlanningSettingsModal
                    users={metaQuery.data?.users || []}
                    initialTab={settingsTab}
                    onClose={() => {
                        setSettingsOpen(false);
                        if (onSettingsClosed) onSettingsClosed();
                    }}
                    onChanged={() => {
                        metaQuery.refetch();
                        refresh();
                    }}
                />
            )}
        </div>
    );
}

const FULL_TIME_SCHEDULE = Object.fromEntries(
    Array.from({ length: 5 }, (_, weekday) => [
        String(weekday),
        [['09:00', '12:30'], ['13:30', '17:00']],
    ]),
);
const WORK_PRESETS = {
    FULL_TIME: FULL_TIME_SCHEDULE,
    FOUR_DAYS: Object.fromEntries(Object.entries(FULL_TIME_SCHEDULE).filter(([day]) => Number(day) < 4)),
    HALF_TIME: Object.fromEntries(
        Array.from({ length: 5 }, (_, weekday) => [String(weekday), [['09:00', '12:30']]]),
    ),
};
const FULL_DAY_NAMES = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
const cloneSchedule = (schedule) => JSON.parse(JSON.stringify(schedule || FULL_TIME_SCHEDULE));
const rowsFromSchedule = (schedule) => Array.from({ length: 7 }, (_, weekday) => {
    const intervals = schedule?.[String(weekday)] || [];
    return {
        weekday,
        enabled: intervals.length > 0,
        morningStart: intervals[0]?.[0] || '09:00',
        morningEnd: intervals[0]?.[1] || '12:30',
        afternoonStart: intervals[1]?.[0] || '',
        afternoonEnd: intervals[1]?.[1] || '',
    };
});
const scheduleFromRows = (rows) => Object.fromEntries(rows
    .filter((row) => row.enabled)
    .map((row) => {
        const intervals = [];
        if (row.morningStart && row.morningEnd) intervals.push([row.morningStart, row.morningEnd]);
        if (row.afternoonStart && row.afternoonEnd) intervals.push([row.afternoonStart, row.afternoonEnd]);
        return [String(row.weekday), intervals];
    })
    .filter(([, intervals]) => intervals.length));
const weeklyHoursFromRows = (rows) => roundHours(rows.reduce((total, row) => {
    if (!row.enabled) return total;
    return total + [
        [row.morningStart, row.morningEnd],
        [row.afternoonStart, row.afternoonEnd],
    ].reduce((dayTotal, [startValue, endValue]) => {
        if (!startValue || !endValue) return dayTotal;
        const [startHour, startMinute] = startValue.split(':').map(Number);
        const [endHour, endMinute] = endValue.split(':').map(Number);
        return dayTotal + Math.max((endHour * 60 + endMinute - startHour * 60 - startMinute) / 60, 0);
    }, 0);
}, 0));

function AvailabilityModal({ period, onClose, onChanged }) {
    const queryClient = useQueryClient();
    const availabilityQuery = useQuery({
        queryKey: ['schedule-availability'],
        queryFn: async () => (await api.get('/v2/schedule/availability', {
            params: {
                start_at: addDays(period.start, -90).toISOString(),
                end_at: addDays(period.end, 365).toISOString(),
            },
        })).data,
    });
    const users = availabilityQuery.data?.users || [];
    const [selectedUserId, setSelectedUserId] = useState('');
    const [scheduleRows, setScheduleRows] = useState(rowsFromSchedule(FULL_TIME_SCHEDULE));
    const [absenceForm, setAbsenceForm] = useState({
        start_at: toInputDateTime(new Date()),
        end_at: toInputDateTime(addHours(new Date(), 8)),
        absence_type: 'LEAVE',
        reason: '',
    });
    const selectedUser = users.find((user) => String(user.id) === String(selectedUserId));

    useEffect(() => {
        if (!selectedUserId && users[0]) setSelectedUserId(String(users[0].id));
    }, [selectedUserId, users]);
    useEffect(() => {
        if (selectedUser) setScheduleRows(rowsFromSchedule(selectedUser.work_schedule));
    }, [selectedUserId, selectedUser]);

    const refreshAvailability = async () => {
        await queryClient.invalidateQueries({ queryKey: ['schedule-availability'] });
        onChanged();
    };
    const scheduleMutation = useMutation({
        mutationFn: async () => api.put(`/v2/schedule/availability/${selectedUser.id}`, {
            work_schedule: scheduleFromRows(scheduleRows),
        }),
        onSuccess: refreshAvailability,
    });
    const absenceMutation = useMutation({
        mutationFn: async () => api.post(`/v2/schedule/availability/${selectedUser.id}/absences`, {
            ...absenceForm,
            start_at: new Date(absenceForm.start_at).toISOString(),
            end_at: new Date(absenceForm.end_at).toISOString(),
            reason: absenceForm.reason.trim() || null,
        }),
        onSuccess: async () => {
            setAbsenceForm((current) => ({ ...current, reason: '' }));
            await refreshAvailability();
        },
    });
    const deleteAbsenceMutation = useMutation({
        mutationFn: async (absenceId) => api.delete(`/v2/schedule/availability/absences/${absenceId}`),
        onSuccess: refreshAvailability,
    });
    const reviewAbsenceMutation = useMutation({
        mutationFn: async ({ absenceId, status }) => api.patch(
            `/v2/schedule/availability/absences/${absenceId}/review`,
            { status },
        ),
        onSuccess: refreshAvailability,
    });
    const setRow = (weekday, key, value) => setScheduleRows((current) => current.map((row) => (
        row.weekday === weekday ? { ...row, [key]: value } : row
    )));
    const applyPreset = (presetKey) => setScheduleRows(rowsFromSchedule(cloneSchedule(WORK_PRESETS[presetKey])));
    const error = scheduleMutation.error || absenceMutation.error || deleteAbsenceMutation.error || reviewAbsenceMutation.error;

    return (
        <ModalShell
            wide
            eyebrow="Capacité réelle"
            title="Disponibilités de l’équipe"
            onClose={onClose}
            footer={(
                <button type="button" onClick={onClose} className="h-10 rounded-md border border-slate-200 bg-white px-4 text-sm font-black text-slate-700">Fermer</button>
            )}
        >
            {availabilityQuery.isLoading ? (
                <div className="py-20 text-center text-sm font-bold text-slate-500">Chargement des disponibilités...</div>
            ) : (
                <div className="space-y-5">
                    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
                        <aside className="rounded-md border border-slate-200 bg-slate-50 p-4">
                            <FieldLabel text="Collaborateur" />
                            <select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)} className="field">
                                {users.map((user) => <option key={user.id} value={user.id}>{user.name} · {user.role}</option>)}
                            </select>
                            {selectedUser && (
                                <div className="mt-4 rounded-md border border-blue-200 bg-blue-50 p-4">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Contrat planifié</p>
                                    <p className="mt-1 text-3xl font-black text-blue-950">{weeklyHoursFromRows(scheduleRows)} h</p>
                                    <p className="mt-1 text-xs font-semibold text-blue-800">La capacité est calculée sur ces plages, après déduction des congés.</p>
                                </div>
                            )}
                            <div className="mt-4 space-y-2">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Modèles</p>
                                <button type="button" onClick={() => applyPreset('FULL_TIME')} className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-xs font-black text-slate-700">35 h · lundi au vendredi</button>
                                <button type="button" onClick={() => applyPreset('FOUR_DAYS')} className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-xs font-black text-slate-700">28 h · quatre jours</button>
                                <button type="button" onClick={() => applyPreset('HALF_TIME')} className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-left text-xs font-black text-slate-700">17,5 h · matinées</button>
                            </div>
                        </aside>

                        <section className="min-w-0 rounded-md border border-slate-200">
                            <div className="border-b border-slate-200 px-4 py-3">
                                <p className="font-black text-slate-900">Horaires individuels</p>
                                <p className="text-xs font-semibold text-slate-500">Deux plages sont possibles par jour pour gérer la pause et les demi-journées.</p>
                            </div>
                            <div className="divide-y divide-slate-100">
                                {scheduleRows.map((row) => (
                                    <div key={row.weekday} className="grid items-center gap-2 px-4 py-3 md:grid-cols-[120px_repeat(4,minmax(90px,1fr))]">
                                        <label className="flex items-center gap-2 text-sm font-black text-slate-800">
                                            <input type="checkbox" checked={row.enabled} onChange={(event) => setRow(row.weekday, 'enabled', event.target.checked)} />
                                            {FULL_DAY_NAMES[row.weekday]}
                                        </label>
                                        {['morningStart', 'morningEnd', 'afternoonStart', 'afternoonEnd'].map((key, index) => (
                                            <label key={key}>
                                                <span className="mb-1 block text-[9px] font-black uppercase text-slate-400">{['Début 1', 'Fin 1', 'Début 2', 'Fin 2'][index]}</span>
                                                <input type="time" disabled={!row.enabled} value={row[key]} onChange={(event) => setRow(row.weekday, key, event.target.value)} className="field disabled:bg-slate-100 disabled:text-slate-300" />
                                            </label>
                                        ))}
                                    </div>
                                ))}
                            </div>
                            <div className="flex justify-end border-t border-slate-200 bg-slate-50 p-4">
                                <button type="button" disabled={!selectedUser || scheduleMutation.isPending} onClick={() => scheduleMutation.mutate()} className="flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white disabled:opacity-40">
                                    <Save className="h-4 w-4" /> Enregistrer les horaires
                                </button>
                            </div>
                        </section>
                    </div>

                    <section className="rounded-md border border-slate-200">
                        <div className="border-b border-slate-200 px-4 py-3">
                            <p className="font-black text-slate-900">Congés et indisponibilités</p>
                            <p className="text-xs font-semibold text-slate-500">Toute demande reste en attente jusqu’à validation d’un responsable. Seules les absences validées réduisent la capacité.</p>
                        </div>
                        <div className="grid gap-3 bg-slate-50 p-4 md:grid-cols-[180px_1fr_1fr_1.4fr_auto]">
                            <select value={absenceForm.absence_type} onChange={(event) => setAbsenceForm((current) => ({ ...current, absence_type: event.target.value }))} className="field">
                                <option value="LEAVE">Congé</option>
                                <option value="RTT">RTT</option>
                                <option value="SICK">Arrêt maladie</option>
                                <option value="TRAINING">Formation</option>
                                <option value="UNAVAILABLE">Indisponible</option>
                            </select>
                            <input type="datetime-local" value={absenceForm.start_at} onChange={(event) => setAbsenceForm((current) => ({ ...current, start_at: event.target.value }))} className="field" />
                            <input type="datetime-local" value={absenceForm.end_at} onChange={(event) => setAbsenceForm((current) => ({ ...current, end_at: event.target.value }))} className="field" />
                            <input value={absenceForm.reason} onChange={(event) => setAbsenceForm((current) => ({ ...current, reason: event.target.value }))} placeholder="Motif ou note interne" className="field" />
                            <button type="button" disabled={!selectedUser || absenceMutation.isPending} onClick={() => absenceMutation.mutate()} className="h-10 rounded-md bg-slate-900 px-4 text-sm font-black text-white disabled:opacity-40">Ajouter</button>
                        </div>
                        <div className="divide-y divide-slate-100">
                            {(selectedUser?.absences || []).map((absence) => (
                                <div key={absence.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                                    <span className="rounded bg-slate-100 px-2 py-1 text-[10px] font-black uppercase text-slate-600">{absence.absence_type}</span>
                                    <span className={`rounded px-2 py-1 text-[10px] font-black uppercase ${absence.status === 'APPROVED' ? 'bg-emerald-50 text-emerald-700' : absence.status === 'REJECTED' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>{absence.status === 'APPROVED' ? 'Validée' : absence.status === 'REJECTED' ? 'Refusée' : 'À valider'}</span>
                                    <span className="text-sm font-black text-slate-800">{new Date(absence.start_at).toLocaleString('fr-FR')} → {new Date(absence.end_at).toLocaleString('fr-FR')}</span>
                                    <span className="min-w-0 flex-1 text-sm font-semibold text-slate-500">{absence.reason || 'Sans note'}</span>
                                    {availabilityQuery.data?.can_approve && absence.status === 'PENDING' && (
                                        <>
                                            <button type="button" onClick={() => reviewAbsenceMutation.mutate({ absenceId: absence.id, status: 'APPROVED' })} className="h-9 rounded-md bg-emerald-600 px-3 text-xs font-black text-white">Valider</button>
                                            <button type="button" onClick={() => reviewAbsenceMutation.mutate({ absenceId: absence.id, status: 'REJECTED' })} className="h-9 rounded-md border border-red-200 px-3 text-xs font-black text-red-700">Refuser</button>
                                        </>
                                    )}
                                    <button type="button" onClick={() => deleteAbsenceMutation.mutate(absence.id)} className="grid h-9 w-9 place-items-center rounded-md border border-red-200 text-red-700 hover:bg-red-50" title="Supprimer l’indisponibilité"><Trash2 className="h-4 w-4" /></button>
                                </div>
                            ))}
                            {!selectedUser?.absences?.length && <p className="px-4 py-8 text-center text-sm font-bold text-slate-400">Aucune indisponibilité enregistrée.</p>}
                        </div>
                    </section>
                    {error && (
                        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
                            {error.response?.data?.detail || 'La mise à jour des disponibilités a échoué.'}
                        </div>
                    )}
                </div>
            )}
        </ModalShell>
    );
}

function TaskForm({ form, setForm, meta }) {
    const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
    const selectClient = (clientId) => {
        const client = (meta?.clients || []).find((item) => String(item.id) === String(clientId));
        const site = client?.default_site;
        setForm((current) => ({
            ...current,
            client_id: clientId,
            location_label: site?.label || current.location_label,
            location_address: site?.address || current.location_address,
            latitude: site?.latitude ?? current.latitude,
            longitude: site?.longitude ?? current.longitude,
        }));
    };
    const toggleSkill = (skillId) => setForm((current) => {
        const exists = (current.skill_requirements || []).some((item) => item.skill_id === skillId);
        return {
            ...current,
            skill_requirements: exists
                ? current.skill_requirements.filter((item) => item.skill_id !== skillId)
                : [...(current.skill_requirements || []), { skill_id: skillId, minimum_level: 1, is_mandatory: true }],
        };
    });
    const toggleResource = (resourceId) => setForm((current) => {
        const exists = (current.resource_assignments || []).some((item) => item.resource_id === resourceId);
        return {
            ...current,
            resource_assignments: exists
                ? current.resource_assignments.filter((item) => item.resource_id !== resourceId)
                : [...(current.resource_assignments || []), { resource_id: resourceId, quantity: 1, status: 'REQUIRED' }],
        };
    });
    return (
        <div className="grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2"><FieldLabel text="Objet" /><input autoFocus value={form.title} onChange={(event) => set('title', event.target.value)} placeholder="Ex. Préparer la commande chantier Diderot" className="field" /></label>
            <label><FieldLabel text="Type" /><select value={form.category} onChange={(event) => set('category', event.target.value)} className="field">{['TASK', 'ORDER', 'MEETING', 'INSTALLATION'].map((key) => <option key={key} value={key}>{CATEGORY_META[key].label}</option>)}</select></label>
            <label><FieldLabel text="Priorité" /><select value={form.priority} onChange={(event) => set('priority', event.target.value)} className="field"><option value="LOW">Basse</option><option value="NORMAL">Normale</option><option value="HIGH">Haute</option><option value="URGENT">Urgente</option></select></label>
            <label><FieldLabel text="Début" /><input type="datetime-local" value={form.start_at} onChange={(event) => set('start_at', event.target.value)} className="field" /></label>
            <label><FieldLabel text="Fin" /><input type="datetime-local" value={form.end_at} onChange={(event) => set('end_at', event.target.value)} className="field" /></label>
            <label><FieldLabel text="Responsable" /><select value={form.assigned_user_id} onChange={(event) => set('assigned_user_id', event.target.value)} className="field"><option value="">Non affecté</option>{(meta?.users || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
            <label><FieldLabel text="Commande signée liée" /><select value={form.sale_order_id} onChange={(event) => set('sale_order_id', event.target.value)} className="field"><option value="">Aucune</option>{(meta?.sale_orders || []).map((order) => <option key={order.id} value={order.id}>{order.reference} · {order.client_name}</option>)}</select></label>
            <label className="sm:col-span-2"><FieldLabel text="Client" /><select value={form.client_id} onChange={(event) => selectClient(event.target.value)} className="field"><option value="">Aucun client</option>{(meta?.clients || []).map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
            <label><FieldLabel text="Lieu" /><input value={form.location_label || ''} onChange={(event) => set('location_label', event.target.value)} placeholder="Atelier, chantier, agence..." className="field" /></label>
            <label><FieldLabel text="Adresse" /><input value={form.location_address || ''} onChange={(event) => setForm((current) => ({ ...current, location_address: event.target.value, latitude: null, longitude: null }))} placeholder="Adresse d’intervention" className="field" /></label>
            <label><FieldLabel text="Effectif requis" /><input type="number" min="1" max="20" value={form.required_headcount || 1} onChange={(event) => set('required_headcount', Number(event.target.value))} className="field" /></label>
            <div className="grid grid-cols-2 gap-2">
                <label><FieldLabel text="Marge avant (min)" /><input type="number" min="0" value={form.buffer_minutes_before || 0} onChange={(event) => set('buffer_minutes_before', Number(event.target.value))} className="field" /></label>
                <label><FieldLabel text="Marge après (min)" /><input type="number" min="0" value={form.buffer_minutes_after || 0} onChange={(event) => set('buffer_minutes_after', Number(event.target.value))} className="field" /></label>
            </div>
            <div className="sm:col-span-2">
                <FieldLabel text="Compétences requises" />
                <div className="flex flex-wrap gap-2 rounded-md border border-slate-200 p-3">
                    {(meta?.skills || []).map((skill) => {
                        const active = (form.skill_requirements || []).some((item) => item.skill_id === skill.id);
                        return <button key={skill.id} type="button" onClick={() => toggleSkill(skill.id)} className={`rounded border px-3 py-2 text-xs font-black ${active ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-slate-200 text-slate-600'}`}>{skill.name}</button>;
                    })}
                    {!meta?.skills?.length && <span className="text-xs font-semibold text-slate-400">Aucune compétence configurée.</span>}
                </div>
            </div>
            <div className="sm:col-span-2">
                <FieldLabel text="Ressources nécessaires" />
                <div className="flex flex-wrap gap-2 rounded-md border border-slate-200 p-3">
                    {(meta?.resources || []).map((resource) => {
                        const active = (form.resource_assignments || []).some((item) => item.resource_id === resource.id);
                        return <button key={resource.id} type="button" onClick={() => toggleResource(resource.id)} className={`rounded border px-3 py-2 text-xs font-black ${active ? 'border-emerald-600 bg-emerald-50 text-emerald-800' : 'border-slate-200 text-slate-600'}`}>{resource.name}</button>;
                    })}
                    {!meta?.resources?.length && <span className="text-xs font-semibold text-slate-400">Aucune ressource configurée.</span>}
                </div>
            </div>
            <label className="sm:col-span-2"><FieldLabel text="Consignes" /><textarea value={form.description} onChange={(event) => set('description', event.target.value)} rows={3} placeholder="Informations utiles à l'équipe..." className="field resize-none" /></label>
        </div>
    );
}

function ExecutionPanel({ event, users = [] }) {
    const queryClient = useQueryClient();
    const [pendingAction, setPendingAction] = useState(null);
    const [transitionForm, setTransitionForm] = useState({
        reason: '',
        note: '',
        time_spent_minutes: '',
        assigned_user_id: '',
    });
    const executionQuery = useQuery({
        queryKey: ['schedule-execution', event.source_type, event.source_id],
        queryFn: async () => (
            await api.get(`/v2/schedule/events/${event.source_type}/${event.source_id}/execution`)
        ).data,
        enabled: EXECUTABLE_SOURCES.has(event.source_type),
    });
    const execution = executionQuery.data;
    const transitionMutation = useMutation({
        mutationFn: async (payload) => (
            await api.post(
                `/v2/schedule/events/${event.source_type}/${event.source_id}/execute`,
                payload,
            )
        ).data,
        onSuccess: (data) => {
            queryClient.setQueryData(
                ['schedule-execution', event.source_type, event.source_id],
                data,
            );
            queryClient.invalidateQueries({ queryKey: ['schedule-events'] });
            queryClient.invalidateQueries({ queryKey: ['planning-notifications'] });
            setPendingAction(null);
            setTransitionForm({
                reason: '',
                note: '',
                time_spent_minutes: '',
                assigned_user_id: '',
            });
        },
    });
    const beginAction = (action) => {
        setPendingAction(action);
        setTransitionForm({
            reason: '',
            note: '',
            time_spent_minutes: action === 'COMPLETE'
                ? String(execution?.elapsed_minutes || '')
                : '',
            assigned_user_id: execution?.assigned_user_id
                ? String(execution.assigned_user_id)
                : '',
        });
    };
    const submitTransition = () => {
        transitionMutation.mutate({
            action: pendingAction,
            reason: transitionForm.reason || null,
            note: transitionForm.note || null,
            time_spent_minutes: transitionForm.time_spent_minutes === ''
                ? null
                : Number(transitionForm.time_spent_minutes),
            assigned_user_id: transitionForm.assigned_user_id
                ? Number(transitionForm.assigned_user_id)
                : null,
            source_screen: 'PLANNING_EXECUTION',
        });
    };
    if (executionQuery.isLoading) {
        return <div className="h-24 animate-pulse rounded-md bg-slate-100" />;
    }
    if (executionQuery.isError) {
        return (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">
                Impossible de charger l’exécution de cette tâche.
            </div>
        );
    }
    if (!execution) return null;

    const statusMeta = EXECUTION_STATUS_META[execution.status]
        || EXECUTION_STATUS_META.TODO;
    const actionButtons = [
        { action: 'START', label: execution.status === 'TODO' ? 'Démarrer' : 'Reprendre', icon: Play, tone: 'bg-blue-600 text-white' },
        { action: 'PAUSE', label: 'Mettre en pause', icon: Pause, tone: 'border border-amber-300 bg-white text-amber-800' },
        { action: 'BLOCK', label: 'Bloquer', icon: Ban, tone: 'border border-red-300 bg-white text-red-700' },
        { action: 'COMPLETE', label: 'Terminer', icon: CheckCircle2, tone: 'bg-emerald-600 text-white' },
    ].filter((item) => execution.allowed_actions.includes(item.action));
    const actionLabel = actionButtons.find((item) => item.action === pendingAction)?.label;
    const errorDetail = transitionMutation.error?.response?.data?.detail;

    return (
        <section className="border-y border-slate-200 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Exécution opérationnelle</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className={`inline-flex min-h-7 items-center rounded px-2.5 text-[10px] font-black uppercase ${statusMeta.tone}`}>
                            {statusMeta.label}
                        </span>
                        <span className="inline-flex min-h-7 items-center gap-1.5 text-sm font-black text-slate-700">
                            <Timer className="h-4 w-4 text-slate-400" />
                            {formatExecutionDuration(execution.elapsed_minutes)}
                        </span>
                    </div>
                    <p className="mt-2 text-xs font-semibold text-slate-500">
                        Responsable : {execution.responsible_name || event.owner_name || 'Non affecté'}
                    </p>
                </div>
                {execution.source_url && (
                    <a href={execution.source_url} className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-200 px-3 text-xs font-black text-slate-700">
                        <ExternalLink className="h-3.5 w-3.5" /> Dossier lié
                    </a>
                )}
            </div>

            {execution.can_execute ? (
                <div className="mt-4 flex flex-wrap gap-2">
                    {actionButtons.map(({ action, label, icon: Icon, tone }) => (
                        <button
                            key={action}
                            type="button"
                            onClick={() => beginAction(action)}
                            className={`inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-black ${tone}`}
                        >
                            <Icon className="h-4 w-4" /> {label}
                        </button>
                    ))}
                    {!actionButtons.length && (
                        <p className="text-sm font-bold text-emerald-700">Cette tâche est terminée.</p>
                    )}
                </div>
            ) : (
                <p className="mt-4 text-sm font-semibold text-slate-500">
                    Seul le responsable affecté ou un responsable planning peut exécuter cette tâche.
                </p>
            )}

            {pendingAction && (
                <div className="mt-4 border-l-4 border-blue-500 bg-slate-50 p-4">
                    <div className="flex items-center justify-between gap-3">
                        <p className="font-black text-slate-900">{actionLabel}</p>
                        <button type="button" onClick={() => setPendingAction(null)} className="text-xs font-black text-slate-500">Fermer</button>
                    </div>
                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        {execution.can_manage && (
                            <label className="sm:col-span-2">
                                <FieldLabel text="Responsable de l’exécution" />
                                <select
                                    value={transitionForm.assigned_user_id}
                                    onChange={(e) => setTransitionForm((current) => ({ ...current, assigned_user_id: e.target.value }))}
                                    className="field"
                                >
                                    <option value="">Responsable actuel</option>
                                    {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
                                </select>
                            </label>
                        )}
                        {(pendingAction === 'PAUSE' || pendingAction === 'BLOCK') && (
                            <label className="sm:col-span-2">
                                <FieldLabel text="Motif obligatoire" />
                                <input
                                    value={transitionForm.reason}
                                    onChange={(e) => setTransitionForm((current) => ({ ...current, reason: e.target.value }))}
                                    placeholder={pendingAction === 'BLOCK' ? 'Pièce manquante, accès impossible…' : 'Pourquoi la tâche est-elle interrompue ?'}
                                    className="field"
                                />
                            </label>
                        )}
                        {pendingAction === 'COMPLETE' && (
                            <label>
                                <FieldLabel text="Temps total passé (minutes)" />
                                <input
                                    type="number"
                                    min="0"
                                    value={transitionForm.time_spent_minutes}
                                    onChange={(e) => setTransitionForm((current) => ({ ...current, time_spent_minutes: e.target.value }))}
                                    className="field"
                                />
                            </label>
                        )}
                        <label className={pendingAction === 'COMPLETE' ? '' : 'sm:col-span-2'}>
                            <FieldLabel text="Compte rendu" />
                            <input
                                value={transitionForm.note}
                                onChange={(e) => setTransitionForm((current) => ({ ...current, note: e.target.value }))}
                                placeholder="Travail réalisé, observation ou consigne…"
                                className="field"
                            />
                        </label>
                    </div>
                    {errorDetail && (
                        <p className="mt-3 text-sm font-bold text-red-700">
                            {typeof errorDetail === 'string' ? errorDetail : 'La transition a échoué.'}
                        </p>
                    )}
                    <button
                        type="button"
                        onClick={submitTransition}
                        disabled={transitionMutation.isPending || (
                            ['PAUSE', 'BLOCK'].includes(pendingAction)
                            && !transitionForm.reason.trim()
                        )}
                        className="mt-3 h-10 rounded-md bg-slate-950 px-5 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-40"
                    >
                        {transitionMutation.isPending ? 'Enregistrement…' : `Confirmer : ${actionLabel}`}
                    </button>
                </div>
            )}

            {execution.history?.length > 0 && (
                <div className="mt-4 divide-y divide-slate-100 border-t border-slate-200">
                    {execution.history.slice(0, 8).map((item) => (
                        <div key={item.id} className="flex flex-wrap items-start justify-between gap-2 py-3">
                            <div>
                                <p className="text-xs font-black uppercase text-blue-700">
                                    {executionActionLabel(item.action)}
                                </p>
                                <p className="mt-1 text-sm font-bold text-slate-800">{item.actor_name}</p>
                                {(item.reason || item.note) && (
                                    <p className="mt-0.5 text-xs font-semibold text-slate-500">
                                        {[item.reason, item.note].filter(Boolean).join(' · ')}
                                    </p>
                                )}
                            </div>
                            <div className="text-right">
                                <p className="text-xs font-bold text-slate-400">{new Date(item.created_at).toLocaleString('fr-FR')}</p>
                                <p className="mt-1 text-xs font-black text-slate-600">{formatExecutionDuration(item.elapsed_minutes)}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}

function EventForm({ event, form, setForm, meta }) {
    const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
    const historyQuery = useQuery({
        queryKey: ['planning-task-history', event.source_id],
        queryFn: async () => (await api.get(`/v2/schedule/tasks/${event.source_id}/history`)).data,
        enabled: event.source_type === 'CALENDAR_TASK',
    });
    return (
        <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
                {[['Référence', event.reference], ['Client', event.client_name], ['Responsable', event.owner_name], ['Lieu', event.location]].filter(([, value]) => value).map(([label, value]) => (
                    <div key={label} className="border-l-2 border-slate-200 pl-3"><p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p><p className="mt-1 text-sm font-bold text-slate-800">{value}</p></div>
                ))}
            </div>
            {event.subtitle && <p className="rounded-md bg-slate-50 p-3 text-sm font-medium text-slate-600">{event.subtitle}</p>}
            {(event.required_skills?.length > 0 || event.resources?.length > 0) && (
                <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-md border border-blue-200 bg-blue-50 p-3">
                        <FieldLabel text="Compétences requises" />
                        <p className="text-sm font-bold text-blue-950">{event.required_skills?.map((item) => item.name).join(', ') || 'Aucune'}</p>
                    </div>
                    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
                        <FieldLabel text="Ressources réservées" />
                        <p className="text-sm font-bold text-emerald-950">{event.resources?.map((item) => item.name).join(', ') || 'Aucune'}</p>
                    </div>
                </div>
            )}
            {EXECUTABLE_SOURCES.has(event.source_type) && (
                <ExecutionPanel event={event} users={meta?.users || []} />
            )}
            {event.editable && form ? (
                <div className="grid gap-4 sm:grid-cols-2">
                    <label><FieldLabel text="Début" /><input type="datetime-local" value={form.start_at} onChange={(e) => set('start_at', e.target.value)} className="field" /></label>
                    <label><FieldLabel text="Fin" /><input type="datetime-local" value={form.end_at} onChange={(e) => set('end_at', e.target.value)} className="field" /></label>
                    <label className="sm:col-span-2"><FieldLabel text="Responsable" /><select value={form.assigned_user_id} onChange={(e) => set('assigned_user_id', e.target.value)} className="field"><option value="">Non affecté</option>{(meta?.users || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
                    {event.source_type === 'CALENDAR_TASK' && <label className="sm:col-span-2"><FieldLabel text="Motif de la modification" /><input value={form.change_reason || ''} onChange={(e) => set('change_reason', e.target.value)} placeholder="Pourquoi cette tâche est-elle déplacée ou réaffectée ?" className="field" /></label>}
                </div>
            ) : (
                <p className="text-sm font-semibold text-slate-500">Cette échéance se pilote depuis son dossier d’origine.</p>
            )}
            {event.source_type === 'CALENDAR_TASK' && (
                <section className="rounded-md border border-slate-200">
                    <div className="border-b border-slate-200 px-4 py-3"><p className="font-black text-slate-900">Historique des changements</p></div>
                    <div className="divide-y divide-slate-100">
                        {(historyQuery.data || []).map((item) => (
                            <div key={item.id} className="px-4 py-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <span className="text-xs font-black uppercase text-blue-700">{item.action}</span>
                                    <span className="text-xs font-semibold text-slate-400">{new Date(item.created_at).toLocaleString('fr-FR')}</span>
                                </div>
                                <p className="mt-1 text-sm font-bold text-slate-800">{item.actor_name}</p>
                                <p className="mt-0.5 text-xs font-semibold text-slate-500">{item.reason || 'Sans motif renseigné'} · {item.source_screen || 'Planning'}</p>
                            </div>
                        ))}
                        {!historyQuery.isLoading && !historyQuery.data?.length && <p className="p-4 text-sm font-semibold text-slate-400">Aucun changement enregistré.</p>}
                    </div>
                </section>
            )}
        </div>
    );
}

function FieldLabel({ text }) {
    return <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">{text}</span>;
}

function normalizeTeamLoad(response, users, events, ownerId) {
    const raw = response?.team_load;
    let rawMembers = [];
    if (Array.isArray(raw)) rawMembers = raw;
    else if (Array.isArray(raw?.members)) rawMembers = raw.members;
    else if (Array.isArray(raw?.users)) rawMembers = raw.users;
    else if (Array.isArray(raw?.items)) rawMembers = raw.items;
    else if (raw && typeof raw === 'object') {
        rawMembers = Object.entries(raw)
            .filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value))
            .map(([key, value]) => ({ user_id: key === 'unassigned' ? null : key, ...value }));
    }

    const visibleUsers = ownerId
        ? users.filter((user) => String(user.id) === String(ownerId))
        : users;
    const members = [
        ...visibleUsers.map((user) => ({ id: user.id, name: user.name || user.username || `Utilisateur ${user.id}` })),
        { id: null, name: 'Non affecté' },
    ];
    const now = new Date();
    return members.map((member) => {
        const memberEvents = events.filter((event) => (
            member.id === null ? !event.owner_id : String(event.owner_id) === String(member.id)
        ));
        const rawMember = rawMembers.find((item) => {
            const rawId = firstDefined(item.user_id, item.owner_id, item.assigned_user_id, item.id);
            return member.id === null
                ? rawId === null || rawId === undefined || rawId === '' || rawId === 'unassigned'
                : String(rawId) === String(member.id);
        }) || {};
        const fallbackHours = roundHours(memberEvents
            .filter((event) => event.source_type !== 'USER_ABSENCE')
            .reduce((sum, event) => sum + eventDurationHours(event), 0));
        const plannedHours = Number(firstDefined(
            rawMember.planned_hours,
            rawMember.scheduled_hours,
            rawMember.hours,
            fallbackHours,
        )) || 0;
        const capacityHours = member.id === null ? 0 : Number(firstDefined(
            rawMember.capacity_hours,
            rawMember.weekly_capacity_hours,
            rawMember.capacity,
            35,
        )) || 0;
        let occupancy = Number(firstDefined(
            rawMember.occupancy_rate,
            rawMember.utilization_rate,
            rawMember.load_rate,
            capacityHours ? (plannedHours / capacityHours) * 100 : 0,
        )) || 0;
        if (occupancy > 0 && occupancy <= 1) occupancy *= 100;
        const overdue = Number(firstDefined(
            rawMember.overdue,
            rawMember.overdue_count,
            rawMember.late_count,
            memberEvents.filter((event) => (
                event.start_at
                && new Date(event.start_at) < now
                && !['DONE', 'COMPLETED', 'TERMINE', 'TERMINÉ'].includes(String(event.status || '').toUpperCase())
            )).length,
        )) || 0;
        const conflicts = Number(firstDefined(
            rawMember.conflicts,
            rawMember.conflict_count,
            countConflicts(memberEvents),
        )) || 0;
        const absenceHours = Number(firstDefined(
            rawMember.absence_hours,
            rawMember.leave_hours,
            0,
        )) || 0;
        const contractHours = Number(firstDefined(
            rawMember.contract_hours,
            rawMember.weekly_hours,
            member.id === null ? 0 : 35,
        )) || 0;
        return {
            ...member,
            plannedHours: roundHours(plannedHours),
            capacityHours: roundHours(capacityHours),
            absenceHours: roundHours(absenceHours),
            contractHours: roundHours(contractHours),
            occupancy: Math.round(occupancy),
            overdue,
            conflicts,
            overloaded: Boolean(firstDefined(rawMember.is_overloaded, occupancy > 100)),
        };
    });
}

function normalizeScheduleAlerts(response, loads, events) {
    const raw = response?.alerts;
    let items = [];
    if (Array.isArray(raw)) items = raw;
    else if (Array.isArray(raw?.items)) items = raw.items;
    else if (raw && typeof raw === 'object') {
        items = Object.entries(raw).flatMap(([key, value]) => {
            if (Array.isArray(value)) return value.map((item) => ({ type: key, ...item }));
            if (typeof value === 'number' && value > 0) return [{ type: key, count: value }];
            if (value && typeof value === 'object') return [{ type: key, ...value }];
            return [];
        });
    }
    const normalized = items.map((item, index) => {
        const type = String(item.type || '').toLowerCase();
        const severity = String(item.severity || '').toLowerCase();
        return {
            id: item.id || `${type || 'alert'}-${index}`,
            title: item.title || item.message || item.label || ({
                overload: 'Collaborateur en surcharge',
                overloaded: 'Collaborateur en surcharge',
                conflict: 'Conflit de planning',
                conflicts: 'Conflits de planning',
                overdue: 'Actions en retard',
                unassigned: 'Actions non affectées',
            }[type] || 'Alerte planning'),
            detail: item.detail || item.owner_name || item.user_name || item.description,
            count: Number(firstDefined(item.count, item.total, item.value, 1)) || 1,
            severity: ['critical', 'high', 'error'].includes(severity)
                ? 'high'
                : (['overload', 'overloaded', 'conflict', 'conflicts'].includes(type) ? 'high' : 'medium'),
        };
    });
    if (normalized.length) return normalized;

    const fallback = [];
    const overloaded = loads.filter((load) => load.overloaded);
    const conflicts = loads.reduce((sum, load) => sum + load.conflicts, 0);
    const overdue = loads.reduce((sum, load) => sum + load.overdue, 0);
    const unassigned = events.filter((event) => !event.owner_id).length;
    if (overloaded.length) fallback.push({
        id: 'fallback-overload',
        title: 'Surcharge équipe',
        detail: overloaded.map((load) => load.name).join(', '),
        count: overloaded.length,
        severity: 'high',
    });
    if (conflicts) fallback.push({ id: 'fallback-conflicts', title: 'Conflits de planning', count: conflicts, severity: 'high' });
    if (overdue) fallback.push({ id: 'fallback-overdue', title: 'Actions en retard', count: overdue, severity: 'medium' });
    if (unassigned) fallback.push({ id: 'fallback-unassigned', title: 'Actions non affectées', count: unassigned, severity: 'medium' });
    return fallback;
}

function CapacityBreakdown({ data, stations }) {
    if (!data) return null;
    const stationNames = Object.fromEntries(stations.map((station) => [String(station.id), station.name]));
    const groups = [
        {
            key: 'by_profession',
            label: 'Capacité par métier',
            rows: Object.entries(data.by_profession || {}).map(([name, value]) => ({ name, ...value })),
        },
        {
            key: 'by_station',
            label: 'Capacité par station',
            rows: Object.entries(data.by_station || {}).map(([id, value]) => ({
                name: stationNames[id] || `Station ${id}`,
                ...value,
            })),
        },
    ].filter((group) => group.rows.length);
    if (!groups.length) return null;

    return (
        <section className="border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
            <div className="grid gap-4 xl:grid-cols-2">
                {groups.map((group) => (
                    <div key={group.key} className="min-w-0">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">{group.label}</p>
                        <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                            {group.rows.map((row) => {
                                const utilization = Number(row.utilization_percent || 0);
                                return (
                                    <div key={row.name} className="w-44 shrink-0 rounded-md border border-slate-200 bg-slate-50 p-3">
                                        <div className="flex items-start justify-between gap-2">
                                            <p className="line-clamp-2 text-xs font-black text-slate-900">{row.name}</p>
                                            <span className={`rounded px-1.5 py-0.5 text-[9px] font-black ${
                                                utilization > 100
                                                    ? 'bg-red-100 text-red-700'
                                                    : utilization >= 80
                                                        ? 'bg-amber-100 text-amber-700'
                                                        : 'bg-emerald-100 text-emerald-700'
                                            }`}>{utilization} %</span>
                                        </div>
                                        <p className="mt-2 text-[10px] font-bold text-slate-500">
                                            {row.planned_hours} h planifiées / {row.capacity_hours} h
                                        </p>
                                        <div className="mt-2 h-1.5 overflow-hidden rounded bg-slate-200">
                                            <div className={`h-full ${
                                                utilization > 100
                                                    ? 'bg-red-500'
                                                    : utilization >= 80
                                                        ? 'bg-amber-500'
                                                        : 'bg-emerald-500'
                                            }`} style={{ width: `${Math.min(utilization, 100)}%` }} />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

function TeamLoadCockpit({ response, users, events, ownerId }) {
    const loads = normalizeTeamLoad(response, users, events, ownerId);
    const alerts = normalizeScheduleAlerts(response, loads, events);
    const staffedLoads = loads.filter((load) => load.id !== null);
    const plannedHours = roundHours(staffedLoads.reduce((sum, load) => sum + load.plannedHours, 0));
    const capacityHours = roundHours(staffedLoads.reduce((sum, load) => sum + load.capacityHours, 0));
    const averageOccupancy = capacityHours ? Math.round((plannedHours / capacityHours) * 100) : 0;
    const conflictCount = loads.reduce((sum, load) => sum + load.conflicts, 0);
    const overdueCount = loads.reduce((sum, load) => sum + load.overdue, 0);

    return (
        <section className="border-b border-slate-200 bg-slate-50 px-4 py-4 sm:px-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Pilotage manager</p>
                    <h3 className="mt-1 text-lg font-black text-slate-950">Charge équipe</h3>
                    <p className="mt-1 text-xs font-semibold text-slate-500">
                        Heures et capacité de la semaine. La capacité est indicative lorsque le backend ne la fournit pas.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    {[
                        ['Planifié', `${plannedHours} h`],
                        ['Capacité', `${capacityHours} h`],
                        ['Occupation', `${averageOccupancy} %`],
                        ['Conflits', conflictCount],
                        ['Retards', overdueCount],
                    ].map(([label, value]) => (
                        <div key={label} className="min-w-24 rounded-md border border-slate-200 bg-white px-3 py-2">
                            <span className="block text-[9px] font-black uppercase tracking-wider text-slate-400">{label}</span>
                            <strong className="mt-0.5 block text-base font-black text-slate-950">{value}</strong>
                        </div>
                    ))}
                </div>
            </div>

            <div className="mt-4 overflow-x-auto pb-1">
                <div className="flex min-w-max gap-2">
                    {loads.map((load) => (
                        <div key={load.id ?? 'unassigned'} className={`w-48 rounded-md border bg-white p-3 ${load.overloaded ? 'border-red-300' : 'border-slate-200'}`}>
                            <div className="flex items-start justify-between gap-2">
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-black text-slate-900">{load.name}</p>
                                    <p className="mt-0.5 text-[10px] font-bold text-slate-500">
                                        {load.plannedHours} h / {load.capacityHours || '—'} h
                                    </p>
                                    {load.absenceHours > 0 && (
                                        <p className="mt-0.5 text-[10px] font-bold text-violet-700">
                                            {load.absenceHours} h d’absence déduite
                                        </p>
                                    )}
                                </div>
                                <span className={`rounded px-2 py-1 text-[10px] font-black ${load.overloaded ? 'bg-red-100 text-red-700' : load.occupancy >= 80 ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                                    {load.capacityHours ? `${load.occupancy} %` : 'Hors charge'}
                                </span>
                            </div>
                            <div className="mt-3 h-1.5 overflow-hidden rounded bg-slate-100">
                                <div className={`h-full rounded ${load.overloaded ? 'bg-red-500' : load.occupancy >= 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(load.occupancy, 100)}%` }} />
                            </div>
                            <div className="mt-3 flex gap-3 text-[10px] font-bold text-slate-500">
                                <span className={load.conflicts ? 'text-red-700' : ''}>{load.conflicts} conflit(s)</span>
                                <span className={load.overdue ? 'text-amber-700' : ''}>{load.overdue} retard(s)</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
                {alerts.slice(0, 6).map((alert) => (
                    <div key={alert.id} className={`flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-bold ${alert.severity === 'high' ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        <span>{alert.title}{alert.detail ? ` · ${alert.detail}` : ''}</span>
                        <strong className="rounded bg-white/70 px-1.5 py-0.5">{alert.count}</strong>
                    </div>
                ))}
                {!alerts.length && (
                    <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800">
                        <CheckCircle2 className="h-4 w-4" /> Aucun conflit ni retard détecté.
                    </div>
                )}
            </div>
        </section>
    );
}

function layoutTeamEvents(events, date) {
    const rangeStart = new Date(date);
    rangeStart.setHours(6, 0, 0, 0);
    const rangeEnd = new Date(date);
    rangeEnd.setHours(21, 0, 0, 0);
    const sorted = events
        .map((event) => {
            const originalStart = new Date(event.start_at);
            const originalEnd = event.end_at ? new Date(event.end_at) : addHours(originalStart, 1);
            return {
                event,
                start: new Date(Math.max(originalStart, rangeStart)),
                end: new Date(Math.min(originalEnd, rangeEnd)),
            };
        })
        .filter((item) => item.start < item.end)
        .sort((left, right) => left.start - right.start);
    const groups = [];
    sorted.forEach((item) => {
        const group = groups[groups.length - 1];
        if (!group || item.start >= group.end) {
            groups.push({ end: item.end, items: [item] });
        } else {
            group.items.push(item);
            if (item.end > group.end) group.end = item.end;
        }
    });
    return groups.flatMap((group) => {
        const laneEnds = [];
        const positioned = group.items.map((item) => {
            let lane = laneEnds.findIndex((end) => end <= item.start);
            if (lane === -1) lane = laneEnds.length;
            laneEnds[lane] = item.end;
            return { ...item, lane };
        });
        return positioned.map((item) => ({
            ...item,
            laneCount: laneEnds.length,
            top: ((item.start - rangeStart) / (60 * 60 * 1000)) * 72,
            height: Math.max(((item.end - item.start) / (60 * 60 * 1000)) * 72, 34),
        }));
    });
}

function TeamView({ date, weekStart, users, ownerId, events, onSelectDate, onOpen, onDrop, onDragStart }) {
    const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
    const visibleUsers = ownerId
        ? users.filter((user) => String(user.id) === String(ownerId))
        : users;
    const inferredUsers = ownerId ? [] : events
        .filter((event) => event.owner_id && !visibleUsers.some((user) => String(user.id) === String(event.owner_id)))
        .reduce((items, event) => (
            items.some((item) => String(item.id) === String(event.owner_id))
                ? items
                : [...items, { id: event.owner_id, name: event.owner_name || `Utilisateur ${event.owner_id}` }]
        ), []);
    const members = [
        ...visibleUsers.map((user) => ({ id: user.id, name: user.name || user.username || `Utilisateur ${user.id}` })),
        ...inferredUsers,
        { id: null, name: 'Non affecté' },
    ];
    const selectedDayEvents = events.filter((event) => (
        event.start_at && localDateKey(new Date(event.start_at)) === localDateKey(date)
    ));
    const hours = Array.from({ length: 15 }, (_, index) => index + 6);
    const totalHeight = hours.length * 72;

    return (
        <section className="bg-white">
            <div className="flex items-center gap-2 overflow-x-auto border-b border-slate-200 px-4 py-3 sm:px-6">
                {days.map((day, index) => (
                    <button
                        key={day.toISOString()}
                        type="button"
                        onClick={() => onSelectDate(day)}
                        className={`min-w-24 rounded-md border px-3 py-2 text-left ${localDateKey(day) === localDateKey(date) ? 'border-blue-600 bg-blue-50 text-blue-900' : 'border-slate-200 bg-white text-slate-600'}`}
                    >
                        <span className="block text-[9px] font-black uppercase tracking-widest">{DAY_NAMES[index]}</span>
                        <strong className="mt-0.5 block text-sm font-black">{day.getDate()} {new Intl.DateTimeFormat('fr-FR', { month: 'short' }).format(day)}</strong>
                    </button>
                ))}
            </div>

            <div className="overflow-x-auto">
                <div style={{ minWidth: `${64 + members.length * 230}px` }}>
                    <div className="sticky top-0 z-30 grid border-b border-slate-200 bg-white" style={{ gridTemplateColumns: `64px repeat(${members.length}, minmax(230px, 1fr))` }}>
                        <div className="border-r border-slate-200 px-2 py-3 text-center text-[9px] font-black uppercase tracking-widest text-slate-400">Heure</div>
                        {members.map((member) => {
                            const count = selectedDayEvents.filter((event) => (
                                member.id === null ? !event.owner_id : String(event.owner_id) === String(member.id)
                            )).length;
                            return (
                                <div key={member.id ?? 'unassigned'} className="border-r border-slate-200 px-3 py-3">
                                    <div className="flex min-w-0 items-center justify-between gap-2">
                                        <span className="truncate text-sm font-black text-slate-900">{member.name}</span>
                                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-black text-slate-600">{count}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    <div className="grid" style={{ gridTemplateColumns: `64px repeat(${members.length}, minmax(230px, 1fr))` }}>
                        <div className="relative border-r border-slate-200 bg-slate-50" style={{ height: `${totalHeight}px` }}>
                            {hours.map((hour, index) => (
                                <span key={hour} className="absolute right-2 text-[10px] font-black text-slate-400" style={{ top: `${index * 72 - 7}px` }}>{pad(hour)}:00</span>
                            ))}
                            <span className="absolute bottom-0 right-2 translate-y-1/2 text-[10px] font-black text-slate-400">21:00</span>
                        </div>
                        {members.map((member) => {
                            const memberEvents = selectedDayEvents.filter((event) => (
                                member.id === null ? !event.owner_id : String(event.owner_id) === String(member.id)
                            ));
                            const positioned = layoutTeamEvents(memberEvents, date);
                            return (
                                <div key={member.id ?? 'unassigned'} className="relative border-r border-slate-200" style={{ height: `${totalHeight}px` }}>
                                    {hours.map((hour, index) => (
                                        <div
                                            key={hour}
                                            onDragOver={(dragEvent) => {
                                                dragEvent.preventDefault();
                                                dragEvent.dataTransfer.dropEffect = 'move';
                                            }}
                                            onDrop={(dropEvent) => onDrop(dropEvent, date, hour, member.id)}
                                            className="absolute inset-x-0 border-b border-slate-100 transition hover:bg-blue-50/60"
                                            style={{ top: `${index * 72}px`, height: '72px' }}
                                            title={`Déplacer à ${pad(hour)}:00 · ${member.name}`}
                                        />
                                    ))}
                                    {positioned.map((item) => {
                                        const meta = CATEGORY_META[item.event.category] || CATEGORY_META.TASK;
                                        const width = 100 / item.laneCount;
                                        return (
                                            <button
                                                key={item.event.id}
                                                type="button"
                                                draggable={item.event.editable}
                                                onDragStart={(dragEvent) => onDragStart(dragEvent, item.event)}
                                                onClick={() => onOpen(item.event)}
                                                className={`absolute z-10 overflow-hidden rounded border px-2 py-1.5 text-left shadow-sm transition hover:z-20 hover:shadow-md ${meta.tone}`}
                                                style={{
                                                    top: `${item.top + 2}px`,
                                                    height: `${Math.max(item.height - 4, 30)}px`,
                                                    left: `calc(${item.lane * width}% + 3px)`,
                                                    width: `calc(${width}% - 6px)`,
                                                }}
                                                title={`${formatTime(item.event.start_at)} · ${item.event.title}`}
                                            >
                                                <span className="block truncate text-[10px] font-black">{formatTime(item.event.start_at)} · {item.event.end_at ? formatTime(item.event.end_at) : ''}</span>
                                                <span className="mt-0.5 block truncate text-xs font-bold">{item.event.title}</span>
                                                {item.height >= 58 && <span className="mt-0.5 block truncate text-[9px] font-semibold opacity-70">{item.event.client_name || item.event.reference || meta.label}</span>}
                                            </button>
                                        );
                                    })}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </section>
    );
}

function MonthView({ anchor, events, onOpen, onDrop, onDragStart }) {
    const start = mondayOf(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
    const days = Array.from({ length: 42 }, (_, index) => addDays(start, index));
    return (
        <div className="overflow-x-auto">
            <div className="min-w-[840px]">
                <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50">{DAY_NAMES.map((day) => <div key={day} className="px-3 py-2 text-center text-[10px] font-black uppercase tracking-widest text-slate-500">{day}</div>)}</div>
                <div className="grid grid-cols-7">
                    {days.map((day) => {
                        const dayEvents = events.filter((event) => localDateKey(new Date(event.start_at)) === localDateKey(day));
                        const outside = day.getMonth() !== anchor.getMonth();
                        return (
                            <div key={day.toISOString()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(event, day)} className={`min-h-28 border-b border-r border-slate-200 p-2 ${outside ? 'bg-slate-50 text-slate-400' : 'bg-white'}`}>
                                <div className={`mb-1 grid h-6 w-6 place-items-center rounded text-xs font-black ${localDateKey(day) === localDateKey(new Date()) ? 'bg-blue-600 text-white' : ''}`}>{day.getDate()}</div>
                                <div className="space-y-1">{dayEvents.slice(0, 3).map((event) => <EventChip key={event.id} event={event} compact onOpen={onOpen} onDragStart={onDragStart} />)}{dayEvents.length > 3 && <button type="button" className="px-1 text-[10px] font-black text-blue-700">+ {dayEvents.length - 3} autres</button>}</div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

function WeekView({ start, events, onOpen, onDrop, onDragStart }) {
    const days = Array.from({ length: 7 }, (_, index) => addDays(start, index));
    return (
        <div className="overflow-x-auto">
            <div className="grid min-w-[980px] grid-cols-7">
                {days.map((day) => {
                    const dayEvents = events.filter((event) => localDateKey(new Date(event.start_at)) === localDateKey(day));
                    return (
                        <section key={day.toISOString()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(event, day)} className="min-h-[650px] border-r border-slate-200 bg-white">
                            <header className="sticky top-0 z-10 border-b border-slate-200 bg-white px-3 py-3 text-center">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{DAY_NAMES[days.indexOf(day)]}</p>
                                <p className={`mx-auto mt-1 grid h-8 w-8 place-items-center rounded text-sm font-black ${localDateKey(day) === localDateKey(new Date()) ? 'bg-blue-600 text-white' : 'text-slate-900'}`}>{day.getDate()}</p>
                            </header>
                            <div className="space-y-2 p-2">
                                {dayEvents.map((event) => <EventChip key={event.id} event={event} onOpen={onOpen} onDragStart={onDragStart} />)}
                                {!dayEvents.length && <p className="py-8 text-center text-[10px] font-bold uppercase text-slate-300">Libre</p>}
                            </div>
                        </section>
                    );
                })}
            </div>
        </div>
    );
}

function DayView({ date, events, onOpen, onDrop, onDragStart }) {
    const slots = Array.from({ length: 16 }, (_, index) => index + 6);
    return (
        <div onDragOver={(event) => event.preventDefault()} onDrop={(event) => onDrop(event, date)} className="px-4 py-4 sm:px-6">
            {slots.map((hour) => {
                const slotEvents = events.filter((event) => new Date(event.start_at).getHours() === hour);
                return (
                    <div key={hour} className="grid min-h-16 grid-cols-[52px_1fr] border-t border-slate-200">
                        <span className="pt-2 text-xs font-black text-slate-400">{pad(hour)}:00</span>
                        <div className="grid gap-2 py-2 sm:grid-cols-2 xl:grid-cols-3">{slotEvents.map((event) => <EventChip key={event.id} event={event} onOpen={onOpen} onDragStart={onDragStart} />)}</div>
                    </div>
                );
            })}
            {!events.length && <div className="py-20 text-center text-sm font-bold text-slate-400">Aucune action planifiée ce jour.</div>}
        </div>
    );
}
