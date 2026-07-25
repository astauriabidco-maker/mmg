import React, { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
    AlertTriangle,
    ArrowLeft,
    ArrowRight,
    CalendarDays,
    CheckCircle2,
    ExternalLink,
    Filter,
    Plus,
    RefreshCw,
    Search,
    Trash2,
    UserRound,
    X,
} from 'lucide-react';
import api from '../services/api';

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

function getPeriod(anchor, view) {
    if (view === 'day') {
        const start = new Date(anchor);
        start.setHours(0, 0, 0, 0);
        return { start, end: addDays(start, 1) };
    }
    if (view === 'week') {
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

function ModalShell({ title, eyebrow, onClose, children, footer }) {
    return (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/55 p-3 backdrop-blur-sm">
            <div className="flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
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
    };
};

export default function ScheduleDashboard() {
    const queryClient = useQueryClient();
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
    const period = useMemo(() => getPeriod(anchor, view), [anchor, view]);

    const metaQuery = useQuery({
        queryKey: ['schedule-meta'],
        queryFn: async () => (await api.get('/v2/schedule/meta')).data,
    });
    const eventsQuery = useQuery({
        queryKey: ['schedule-events', period.start.toISOString(), period.end.toISOString(), ownerId, typeFilter],
        queryFn: async () => (await api.get('/v2/schedule/events', {
            params: {
                start_at: period.start.toISOString(),
                end_at: period.end.toISOString(),
                owner_id: ownerId || undefined,
                types: typeFilter === 'ALL' ? undefined : typeFilter,
                include_unscheduled: true,
            },
        })).data,
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
        else if (view === 'week') setAnchor(addDays(anchor, direction * 7));
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
    });
    const saveEvent = () => updateMutation.mutate({
        event: selectedEvent,
        payload: {
            start_at: new Date(editForm.start_at).toISOString(),
            end_at: new Date(editForm.end_at).toISOString(),
            assigned_user_id: editForm.assigned_user_id ? Number(editForm.assigned_user_id) : null,
            status: selectedEvent.source_type === 'CALENDAR_TASK' ? editForm.status : undefined,
        },
    });

    const periodTitle = view === 'day'
        ? formatLongDate(anchor)
        : view === 'week'
            ? `${new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' }).format(period.start)} au ${new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }).format(addDays(period.end, -1))}`
            : new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric' }).format(anchor);

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
                        <button
                            type="button"
                            onClick={() => setCreateForm(initialTask(anchor))}
                            className="flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white hover:bg-blue-700"
                        >
                            <Plus className="h-4 w-4" /> Planifier
                        </button>
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
                            {[['day', 'Jour'], ['week', 'Semaine'], ['month', 'Mois']].map(([key, label]) => (
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
        </div>
    );
}

function TaskForm({ form, setForm, meta }) {
    const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
    return (
        <div className="grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2"><FieldLabel text="Objet" /><input autoFocus value={form.title} onChange={(event) => set('title', event.target.value)} placeholder="Ex. Préparer la commande chantier Diderot" className="field" /></label>
            <label><FieldLabel text="Type" /><select value={form.category} onChange={(event) => set('category', event.target.value)} className="field">{['TASK', 'ORDER', 'MEETING', 'INSTALLATION'].map((key) => <option key={key} value={key}>{CATEGORY_META[key].label}</option>)}</select></label>
            <label><FieldLabel text="Priorité" /><select value={form.priority} onChange={(event) => set('priority', event.target.value)} className="field"><option value="LOW">Basse</option><option value="NORMAL">Normale</option><option value="HIGH">Haute</option><option value="URGENT">Urgente</option></select></label>
            <label><FieldLabel text="Début" /><input type="datetime-local" value={form.start_at} onChange={(event) => set('start_at', event.target.value)} className="field" /></label>
            <label><FieldLabel text="Fin" /><input type="datetime-local" value={form.end_at} onChange={(event) => set('end_at', event.target.value)} className="field" /></label>
            <label><FieldLabel text="Responsable" /><select value={form.assigned_user_id} onChange={(event) => set('assigned_user_id', event.target.value)} className="field"><option value="">Non affecté</option>{(meta?.users || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
            <label><FieldLabel text="Commande signée liée" /><select value={form.sale_order_id} onChange={(event) => set('sale_order_id', event.target.value)} className="field"><option value="">Aucune</option>{(meta?.sale_orders || []).map((order) => <option key={order.id} value={order.id}>{order.reference} · {order.client_name}</option>)}</select></label>
            <label className="sm:col-span-2"><FieldLabel text="Client" /><select value={form.client_id} onChange={(event) => set('client_id', event.target.value)} className="field"><option value="">Aucun client</option>{(meta?.clients || []).map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}</select></label>
            <label className="sm:col-span-2"><FieldLabel text="Consignes" /><textarea value={form.description} onChange={(event) => set('description', event.target.value)} rows={3} placeholder="Informations utiles à l'équipe..." className="field resize-none" /></label>
        </div>
    );
}

function EventForm({ event, form, setForm, meta }) {
    const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
    return (
        <div className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2">
                {[['Référence', event.reference], ['Client', event.client_name], ['Responsable', event.owner_name], ['Lieu', event.location]].filter(([, value]) => value).map(([label, value]) => (
                    <div key={label} className="border-l-2 border-slate-200 pl-3"><p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p><p className="mt-1 text-sm font-bold text-slate-800">{value}</p></div>
                ))}
            </div>
            {event.subtitle && <p className="rounded-md bg-slate-50 p-3 text-sm font-medium text-slate-600">{event.subtitle}</p>}
            {event.editable && form ? (
                <div className="grid gap-4 sm:grid-cols-2">
                    <label><FieldLabel text="Début" /><input type="datetime-local" value={form.start_at} onChange={(e) => set('start_at', e.target.value)} className="field" /></label>
                    <label><FieldLabel text="Fin" /><input type="datetime-local" value={form.end_at} onChange={(e) => set('end_at', e.target.value)} className="field" /></label>
                    <label className={event.source_type === 'CALENDAR_TASK' ? '' : 'sm:col-span-2'}><FieldLabel text="Responsable" /><select value={form.assigned_user_id} onChange={(e) => set('assigned_user_id', e.target.value)} className="field"><option value="">Non affecté</option>{(meta?.users || []).map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
                    {event.source_type === 'CALENDAR_TASK' && <label><FieldLabel text="Statut" /><select value={form.status} onChange={(e) => set('status', e.target.value)} className="field"><option value="TODO">À faire</option><option value="IN_PROGRESS">En cours</option><option value="DONE">Terminé</option></select></label>}
                </div>
            ) : (
                <p className="text-sm font-semibold text-slate-500">Cette échéance se pilote depuis son dossier d’origine.</p>
            )}
        </div>
    );
}

function FieldLabel({ text }) {
    return <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">{text}</span>;
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
