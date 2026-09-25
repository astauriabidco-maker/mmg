import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    AlertTriangle,
    ArrowRight,
    Calendar,
    CheckCircle,
    Clock,
    FileText,
    MapPin,
    Package,
    Plus,
    RefreshCw,
    Search,
    Truck,
    User,
} from 'lucide-react';
import api, { API_BASE_URL } from '../services/api';

const LOGISTICS_VIEWS = [
    { id: 'ship', label: 'À expédier', icon: Package },
    { id: 'routes', label: 'Tournées', icon: Truck },
    { id: 'notes', label: 'Bons de livraison', icon: FileText },
    { id: 'driver', label: 'Chauffeur', icon: MapPin },
    { id: 'returns', label: 'Retours & anomalies', icon: AlertTriangle },
];

const STATUS_META = {
    READY: { label: 'Prêt quai', className: 'bg-amber-50 text-amber-700 border-amber-100' },
    ASSIGNED: { label: 'Assigné', className: 'bg-blue-50 text-blue-700 border-blue-100' },
    IN_TRANSIT: { label: 'En tournée', className: 'bg-indigo-50 text-indigo-700 border-indigo-100' },
    DELIVERED: { label: 'Livré', className: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
    RETURNED: { label: 'Retourné', className: 'bg-orange-50 text-orange-700 border-orange-100' },
    ISSUE: { label: 'Anomalie', className: 'bg-red-50 text-red-700 border-red-100' },
    CANCELLED: { label: 'Annulé', className: 'bg-slate-100 text-slate-600 border-slate-200' },
};

const ROUTE_STATUS_META = {
    PLANNED: { label: 'Planifiée', className: 'bg-slate-100 text-slate-700 border-slate-200' },
    IN_TRANSIT: { label: 'En tournée', className: 'bg-indigo-50 text-indigo-700 border-indigo-100' },
    COMPLETED: { label: 'Terminée', className: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
};

const normalizeText = value => String(value || '').toLowerCase();

export default function DeliveryDashboard() {
    const [searchParams, setSearchParams] = useSearchParams();
    const activeView = searchParams.get('logisticsMenu') || 'ship';
    const [routes, setRoutes] = useState([]);
    const [readyNotes, setReadyNotes] = useState([]);
    const [queue, setQueue] = useState({ summary: {}, items: [] });
    const [isLoading, setIsLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [showNewRouteModal, setShowNewRouteModal] = useState(false);
    const [newRouteData, setNewRouteData] = useState({
        driver_name: '',
        vehicle: 'Camion 1 (Iveco)',
        planned_date: '',
        note_ids: [],
    });

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [resRoutes, resNotes, resQueue] = await Promise.all([
                api.get('/v2/logistics/routes'),
                api.get('/v2/logistics/notes/ready'),
                api.get('/v2/logistics/queue'),
            ]);
            setRoutes(resRoutes.data || []);
            setReadyNotes(resNotes.data || []);
            setQueue(resQueue.data || { summary: {}, items: [] });
        } catch (error) {
            console.error('Error fetching logistics data', error);
        } finally {
            setIsLoading(false);
        }
    };

    const allNotes = useMemo(() => {
        const byId = new Map();
        readyNotes.forEach(note => byId.set(note.id, note));
        routes.forEach(route => (route.notes || []).forEach(note => byId.set(note.id, { ...note, route })));
        return Array.from(byId.values()).sort((a, b) => String(a.reference || '').localeCompare(String(b.reference || '')));
    }, [readyNotes, routes]);

    const filteredNotes = allNotes.filter(note => {
        const term = normalizeText(searchTerm);
        return !term
            || normalizeText(note.reference).includes(term)
            || normalizeText(note.client_name).includes(term)
            || normalizeText(note.delivery_address).includes(term)
            || normalizeText(note.status).includes(term);
    });

    const issueNotes = allNotes.filter(note => ['ISSUE', 'RETURNED', 'CANCELLED'].includes(note.status));
    const inTransitRoutes = routes.filter(route => route.status === 'IN_TRANSIT');
    const plannedRoutes = routes.filter(route => route.status === 'PLANNED');
    const deliveredNotes = allNotes.filter(note => note.status === 'DELIVERED');
    const queueItems = queue.items || [];
    const queueSummary = queue.summary || {};
    const readyCount = queueSummary.ready_count ?? readyNotes.length;
    const issueCount = queueSummary.issue_count ?? issueNotes.length;
    const deliveredCount = queueSummary.delivered_count ?? deliveredNotes.length;
    const filteredQueueItems = queueItems.filter(item => {
        const term = normalizeText(searchTerm);
        return !term
            || normalizeText(item.reference).includes(term)
            || normalizeText(item.client_name).includes(term)
            || normalizeText(item.delivery_address).includes(term)
            || normalizeText(item.status).includes(term)
            || normalizeText(item.next_action).includes(term);
    });
    const activeQueueItems = filteredQueueItems.filter(item => item.next_action !== 'CLOSE');

    const changeView = (view) => {
        setSearchParams({ view: 'logistics', logisticsMenu: view });
    };

    const handleCreateRoute = async () => {
        if (!newRouteData.driver_name.trim() || !newRouteData.planned_date) {
            alert('Veuillez remplir le chauffeur et la date.');
            return;
        }
        try {
            await api.post('/v2/logistics/routes', newRouteData);
            setShowNewRouteModal(false);
            setNewRouteData({ driver_name: '', vehicle: 'Camion 1 (Iveco)', planned_date: '', note_ids: [] });
            fetchData();
        } catch (error) {
            alert(error.response?.data?.detail || 'Erreur de création de tournée');
        }
    };

    const handleStartRoute = async (routeId) => {
        try {
            await api.post(`/v2/logistics/routes/${routeId}/start`);
            fetchData();
        } catch (error) {
            alert(error.response?.data?.detail || 'Erreur au démarrage de la tournée.');
        }
    };

    const statusBadge = (status) => {
        const meta = STATUS_META[status] || STATUS_META.READY;
        return <span className={`rounded-lg border px-2.5 py-1 text-[10px] font-black uppercase tracking-widest ${meta.className}`}>{meta.label}</span>;
    };

    const routeStatusBadge = (status) => {
        const meta = ROUTE_STATUS_META[status] || ROUTE_STATUS_META.PLANNED;
        return <span className={`rounded-lg border px-2.5 py-1 text-[10px] font-black uppercase tracking-widest ${meta.className}`}>{meta.label}</span>;
    };

    const renderNoteCard = (note, actionLabel = 'Préparer tournée') => (
        <div key={note.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="font-mono text-xs font-black text-blue-600">{note.reference}</p>
                    <h3 className="mt-1 text-lg font-black text-slate-950">{note.client_name}</h3>
                    <p className="mt-1 flex items-start gap-2 text-sm font-bold text-slate-500">
                        <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                        {note.delivery_address || 'Adresse non renseignée'}
                    </p>
                </div>
                {statusBadge(note.status)}
            </div>
            {note.delivery_notes && (
                <p className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs font-bold text-slate-600">{note.delivery_notes}</p>
            )}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                    {note.route?.reference ? `Tournée ${note.route.reference}` : 'Non assigné'}
                </p>
                {note.status === 'DELIVERED' && note.signature_path ? (
                    <a href={`${API_BASE_URL}/${note.signature_path}`} target="_blank" rel="noreferrer" className="rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-xs font-black text-emerald-700 hover:bg-emerald-100">
                        Voir signature
                    </a>
                ) : (
                    <button onClick={() => setShowNewRouteModal(true)} className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-black text-white hover:bg-slate-800">
                        {actionLabel} <ArrowRight className="ml-1 inline h-3.5 w-3.5" />
                    </button>
                )}
            </div>
        </div>
    );

    const renderQueueItem = (item) => {
        const actionLabels = {
            COMPLETE_DELIVERY_INFO: 'Compléter',
            ASSIGN_ROUTE: 'Planifier',
            START_ROUTE: 'Démarrer',
            COLLECT_SIGNATURE: 'Signature',
            ARCHIVE_PROOF: 'Preuve',
            HANDLE_ISSUE: 'Traiter',
        };
        const priorityClass = item.priority === 'CRITICAL'
            ? 'border-red-100 bg-red-50'
            : item.priority === 'URGENT'
                ? 'border-amber-100 bg-amber-50'
                : 'border-slate-200 bg-white';
        const handleQueueAction = () => {
            if (item.next_action === 'ASSIGN_ROUTE') {
                setShowNewRouteModal(true);
                return;
            }
            if (item.next_action === 'HANDLE_ISSUE' || item.next_action === 'COMPLETE_DELIVERY_INFO') {
                changeView('returns');
                return;
            }
            if (item.next_action === 'COLLECT_SIGNATURE') {
                changeView('driver');
                return;
            }
            changeView('routes');
        };
        return (
            <div key={item.note_id} className={`rounded-2xl border p-4 shadow-sm ${priorityClass}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <p className="font-mono text-xs font-black text-blue-600">{item.reference}</p>
                            {statusBadge(item.status)}
                        </div>
                        <h3 className="mt-2 text-lg font-black text-slate-950">{item.client_name}</h3>
                        <p className="mt-1 flex items-start gap-2 text-sm font-bold text-slate-500">
                            <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
                            {item.delivery_address || 'Adresse à compléter'}
                        </p>
                    </div>
                    <div className="rounded-xl border border-white/60 bg-white px-3 py-2 text-right shadow-sm">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Action</p>
                        <p className="text-sm font-black text-slate-900">{actionLabels[item.next_action] || 'Suivre'}</p>
                    </div>
                </div>
                {(item.blockers?.length > 0 || item.signals?.length > 0) && (
                    <div className="mt-4 flex flex-wrap gap-2">
                        {(item.blockers || []).map(blocker => (
                            <span key={blocker} className="rounded-lg border border-red-100 bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-red-600">{blocker.replaceAll('_', ' ')}</span>
                        ))}
                        {(item.signals || []).slice(0, 3).map(signal => (
                            <span key={signal} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">{signal.replaceAll('_', ' ')}</span>
                        ))}
                    </div>
                )}
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/70 pt-4">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                        {item.route_reference ? `${item.route_reference} · ${item.driver_name || 'Chauffeur à préciser'}` : 'Non assigné'}
                    </p>
                    <button onClick={handleQueueAction} className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-black text-white hover:bg-slate-800">
                        {actionLabels[item.next_action] || 'Ouvrir'} <ArrowRight className="ml-1 inline h-3.5 w-3.5" />
                    </button>
                </div>
            </div>
        );
    };

    const renderRouteCard = (route) => {
        const notes = route.notes || [];
        const delivered = notes.filter(note => note.status === 'DELIVERED').length;
        const progress = notes.length ? Math.round((delivered / notes.length) * 100) : 0;
        return (
            <div key={route.id} className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
                <div className="flex flex-col gap-4 border-b border-slate-100 bg-slate-50 px-5 py-4 xl:flex-row xl:items-center xl:justify-between">
                    <div>
                        <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-xl font-black text-slate-950">{route.reference}</h3>
                            {routeStatusBadge(route.status)}
                        </div>
                        <p className="mt-2 flex flex-wrap gap-4 text-sm font-bold text-slate-500">
                            <span className="inline-flex items-center gap-1"><Calendar className="h-4 w-4" /> {new Date(route.planned_date).toLocaleDateString('fr-FR')}</span>
                            <span className="inline-flex items-center gap-1"><User className="h-4 w-4" /> {route.driver_name}</span>
                            <span className="inline-flex items-center gap-1"><Truck className="h-4 w-4" /> {route.vehicle}</span>
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="rounded-xl border border-slate-200 bg-white px-4 py-2">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Livré</p>
                            <p className="text-lg font-black text-slate-950">{delivered}/{notes.length}</p>
                        </div>
                        {route.status === 'PLANNED' && (
                            <button onClick={() => handleStartRoute(route.id)} className="rounded-xl bg-indigo-600 px-4 py-3 text-sm font-black text-white hover:bg-indigo-500">
                                Démarrer
                            </button>
                        )}
                    </div>
                </div>
                <div className="p-5">
                    <div className="mb-4 h-2 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full bg-indigo-500" style={{ width: `${progress}%` }} />
                    </div>
                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                        {notes.map(note => (
                            <div key={note.id} className="rounded-2xl border border-slate-100 bg-slate-50 p-3">
                                <div className="flex items-center justify-between gap-3">
                                    <div className="min-w-0">
                                        <p className="truncate font-black text-slate-900">{note.client_name}</p>
                                        <p className="truncate text-xs font-bold text-slate-500">{note.reference} · {note.delivery_address || 'Adresse non renseignée'}</p>
                                    </div>
                                    {note.status === 'DELIVERED' ? <CheckCircle className="h-5 w-5 shrink-0 text-emerald-500" /> : statusBadge(note.status)}
                                </div>
                            </div>
                        ))}
                        {notes.length === 0 && <p className="text-sm font-bold text-slate-400">Aucun BL assigné.</p>}
                    </div>
                </div>
            </div>
        );
    };

    const currentViewMeta = LOGISTICS_VIEWS.find(view => view.id === activeView) || LOGISTICS_VIEWS[0];
    const CurrentIcon = currentViewMeta.icon;

    return (
        <div className="min-h-[calc(100vh-96px)] bg-slate-50">
            <div className="border-y border-slate-200 bg-white px-6 py-5 xl:px-8">
                <div className="flex flex-col gap-5 2xl:flex-row 2xl:items-center 2xl:justify-between">
                    <div>
                        <div className="flex items-center gap-3">
                            <CurrentIcon className="h-6 w-6 text-blue-600" />
                            <h2 className="text-2xl font-black text-slate-950">Logistique & Expédition</h2>
                        </div>
                        <p className="mt-1 text-sm font-bold text-slate-500">Transformer les BL prêts en livraisons signées, visibles et contrôlées.</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <button onClick={() => setShowNewRouteModal(true)} className="rounded-xl bg-slate-900 px-5 py-3 text-sm font-black text-white hover:bg-slate-800">
                            <Plus className="mr-2 inline h-4 w-4" /> Nouvelle tournée
                        </button>
                        <button onClick={fetchData} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-black text-slate-600 hover:bg-slate-50">
                            <RefreshCw className="mr-2 inline h-4 w-4" /> Actualiser
                        </button>
                    </div>
                </div>
                <div className="mt-5 grid grid-cols-1 gap-3 xl:grid-cols-[1fr_auto]">
                    <div className="relative">
                        <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
                        <input value={searchTerm} onChange={event => setSearchTerm(event.target.value)} placeholder="Rechercher BL, client, adresse..." className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3 pl-12 pr-4 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:flex">
                        {LOGISTICS_VIEWS.map(view => {
                            const Icon = view.icon;
                            const selected = activeView === view.id;
                            return (
                                <button key={view.id} onClick={() => changeView(view.id)} className={`rounded-xl border px-4 py-3 text-xs font-black transition-colors ${selected ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'}`}>
                                    <Icon className="mr-2 inline h-4 w-4" /> {view.label}
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>

            <div className="p-6 xl:p-8">
                <div className="mb-6 grid grid-cols-2 gap-4 xl:grid-cols-5">
                    {[
                        ['Prêts quai', readyCount, 'À assigner', 'amber'],
                        ['Tournées prévues', plannedRoutes.length, 'Planifiées', 'blue'],
                        ['En tournée', inTransitRoutes.length, 'À suivre', 'indigo'],
                        ['Livrés', deliveredCount, 'Signés', 'emerald'],
                        ['Anomalies/retours', issueCount, 'À traiter', issueCount ? 'red' : 'slate'],
                    ].map(([label, value, helper, tone]) => (
                        <div key={label} className={`rounded-2xl border p-4 ${tone === 'red' ? 'border-red-100 bg-red-50 text-red-700' : tone === 'emerald' ? 'border-emerald-100 bg-emerald-50 text-emerald-700' : tone === 'indigo' ? 'border-indigo-100 bg-indigo-50 text-indigo-700' : tone === 'blue' ? 'border-blue-100 bg-blue-50 text-blue-700' : tone === 'amber' ? 'border-amber-100 bg-amber-50 text-amber-700' : 'border-slate-200 bg-white text-slate-700'}`}>
                            <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{label}</p>
                            <p className="mt-2 text-3xl font-black">{value}</p>
                            <p className="mt-1 text-xs font-bold opacity-80">{helper}</p>
                        </div>
                    ))}
                </div>

                {isLoading ? (
                    <div className="rounded-3xl border border-slate-200 bg-white py-20 text-center font-black text-slate-400">Chargement logistique...</div>
                ) : activeView === 'ship' ? (
                    <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[1fr_360px]">
                        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-500">File expédition</p>
                            <h3 className="mt-1 text-2xl font-black text-slate-950">À traiter dans le bon ordre</h3>
                            <p className="mt-1 text-sm font-bold text-slate-500">Priorité calculée depuis statut BL, tournée, adresse, contact et preuve de livraison.</p>
                            <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-2">
                                {activeQueueItems.map(renderQueueItem)}
                                {activeQueueItems.length === 0 && <EmptyState icon={Package} title="Aucune action logistique urgente" text="Les BL prêts, anomalies et tournées en cours apparaîtront ici." />}
                            </div>
                        </section>
                        <aside className="space-y-4">
                            <DecisionPanel readyCount={readyCount} plannedCount={plannedRoutes.length} issueCount={issueCount} blockedCount={queueSummary.blocked_count || 0} />
                        </aside>
                    </div>
                ) : activeView === 'routes' ? (
                    <div className="space-y-5">{routes.map(renderRouteCard)}{routes.length === 0 && <EmptyState icon={Truck} title="Aucune tournée" text="Créez une tournée depuis les BL prêts." />}</div>
                ) : activeView === 'notes' ? (
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 2xl:grid-cols-3">{filteredNotes.map(note => renderNoteCard(note, 'Ouvrir'))}</div>
                ) : activeView === 'driver' ? (
                    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">{routes.filter(route => ['PLANNED', 'IN_TRANSIT'].includes(route.status)).map(renderRouteCard)}</div>
                ) : (
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">{issueNotes.map(note => renderNoteCard(note, 'Traiter'))}{issueNotes.length === 0 && <EmptyState icon={CheckCircle} title="Aucune anomalie logistique" text="Les retours, annulations et problèmes de livraison seront visibles ici." />}</div>
                )}
            </div>

            {showNewRouteModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
                    <div className="w-full max-w-2xl overflow-hidden rounded-3xl bg-white shadow-2xl">
                        <div className="border-b border-slate-100 px-8 py-6">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-500">Planification tournée</p>
                            <h3 className="mt-1 text-2xl font-black text-slate-950">Créer une tournée</h3>
                        </div>
                        <div className="space-y-5 px-8 py-6">
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <Field label="Chauffeur / équipe">
                                    <input value={newRouteData.driver_name} onChange={event => setNewRouteData({ ...newRouteData, driver_name: event.target.value })} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 font-bold outline-none focus:ring-2 focus:ring-blue-500" placeholder="Nom chauffeur" />
                                </Field>
                                <Field label="Véhicule">
                                    <select value={newRouteData.vehicle} onChange={event => setNewRouteData({ ...newRouteData, vehicle: event.target.value })} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 font-bold outline-none focus:ring-2 focus:ring-blue-500">
                                        <option value="Camion 1 (Iveco)">Camion 1 (Iveco)</option>
                                        <option value="Camion 2 (Renault)">Camion 2 (Renault)</option>
                                        <option value="Fourgon (Peugeot)">Fourgon (Peugeot)</option>
                                    </select>
                                </Field>
                            </div>
                            <Field label="Date de livraison prévue">
                                <input type="date" value={newRouteData.planned_date} onChange={event => setNewRouteData({ ...newRouteData, planned_date: event.target.value })} className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                            </Field>
                            <Field label="BL à charger">
                                <div className="max-h-64 space-y-2 overflow-y-auto rounded-2xl border border-slate-200 bg-slate-50 p-2">
                                    {readyNotes.map(note => (
                                        <label key={note.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-100 bg-white p-3 hover:border-blue-200">
                                            <input
                                                type="checkbox"
                                                className="h-4 w-4 rounded border-slate-300 text-blue-600"
                                                checked={newRouteData.note_ids.includes(note.id)}
                                                onChange={event => {
                                                    const ids = event.target.checked
                                                        ? [...newRouteData.note_ids, note.id]
                                                        : newRouteData.note_ids.filter(id => id !== note.id);
                                                    setNewRouteData({ ...newRouteData, note_ids: ids });
                                                }}
                                            />
                                            <div className="min-w-0">
                                                <p className="truncate font-black text-slate-900">{note.client_name}</p>
                                                <p className="truncate text-xs font-bold text-slate-500">{note.reference} · {note.delivery_address || 'Adresse non renseignée'}</p>
                                            </div>
                                        </label>
                                    ))}
                                    {readyNotes.length === 0 && <p className="p-6 text-center text-sm font-bold text-slate-400">Aucun BL prêt.</p>}
                                </div>
                            </Field>
                        </div>
                        <div className="flex justify-end gap-3 border-t border-slate-100 bg-slate-50 px-8 py-5">
                            <button onClick={() => setShowNewRouteModal(false)} className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-600 hover:bg-slate-50">Annuler</button>
                            <button onClick={handleCreateRoute} className="rounded-xl bg-blue-600 px-6 py-3 text-sm font-black text-white hover:bg-blue-500">Créer la tournée</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function Field({ label, children }) {
    return (
        <div>
            <label className="mb-1.5 block text-xs font-black uppercase tracking-widest text-slate-400">{label}</label>
            {children}
        </div>
    );
}

function EmptyState({ icon: Icon, title, text }) {
    return (
        <div className="col-span-full rounded-3xl border-2 border-dashed border-slate-200 bg-slate-50 py-16 text-center">
            <Icon className="mx-auto h-12 w-12 text-slate-300" />
            <h3 className="mt-4 text-lg font-black text-slate-700">{title}</h3>
            <p className="mt-1 text-sm font-bold text-slate-400">{text}</p>
        </div>
    );
}

function DecisionPanel({ readyCount, plannedCount, issueCount, blockedCount }) {
    const decision = issueCount > 0
        ? 'Traiter les anomalies avant de charger une nouvelle tournée.'
        : blockedCount > 0
            ? 'Compléter les BL bloqués avant planification.'
        : readyCount > 0
            ? 'Constituer une tournée avec les BL prêts au quai.'
            : plannedCount > 0
                ? 'Démarrer ou suivre les tournées planifiées.'
                : 'Aucune action logistique urgente.';
    return (
        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-[10px] font-black uppercase tracking-widest text-blue-500">Prochaine action</p>
            <h3 className="mt-2 text-xl font-black text-slate-950">{decision}</h3>
            <div className="mt-5 space-y-3 text-sm font-bold text-slate-600">
                <p className="flex gap-2"><Package className="h-5 w-5 text-amber-500" /> Charger uniquement des BL prêts.</p>
                <p className="flex gap-2"><Truck className="h-5 w-5 text-indigo-500" /> Démarrer la tournée quand le camion est réellement parti.</p>
                <p className="flex gap-2"><Clock className="h-5 w-5 text-slate-400" /> La preuve de livraison reste côté interface chauffeur.</p>
            </div>
        </div>
    );
}
