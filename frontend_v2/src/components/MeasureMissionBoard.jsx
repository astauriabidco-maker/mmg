import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AlertTriangle,
    CalendarDays,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    ClipboardCheck,
    Clock3,
    MapPin,
    Plus,
    Ruler,
    UserRound,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

const STATUS = {
    DRAFT: { label: 'Brouillon', tone: 'bg-slate-100 text-slate-700' },
    TO_SCHEDULE: { label: 'À planifier', tone: 'bg-amber-100 text-amber-800' },
    SCHEDULED: { label: 'Planifié', tone: 'bg-blue-100 text-blue-800' },
    IN_CAPTURE: { label: 'Relevé en cours', tone: 'bg-indigo-100 text-indigo-800' },
    ON_SITE: { label: 'Sur chantier', tone: 'bg-indigo-100 text-indigo-800' },
    TO_REVIEW: { label: 'Contrôle BE', tone: 'bg-orange-100 text-orange-800' },
    CORRECTION_REQUIRED: { label: 'Correction', tone: 'bg-red-100 text-red-700' },
    VALIDATED: { label: 'Validé BE', tone: 'bg-emerald-100 text-emerald-800' },
    QUOTED: { label: 'Devis créé', tone: 'bg-teal-100 text-teal-800' },
    CANCELLED: { label: 'Annulé', tone: 'bg-slate-200 text-slate-500' },
};

const SOURCE = {
    SITE_VISIT: 'Métré MMG',
    CLIENT_DOCUMENTS: 'Cotes client',
    AGENCY_ASSISTED: 'Saisie agence',
};

const startOfWeek = input => {
    const date = new Date(input);
    date.setHours(0, 0, 0, 0);
    const day = date.getDay() || 7;
    date.setDate(date.getDate() - day + 1);
    return date;
};

const addDays = (input, days) => {
    const date = new Date(input);
    date.setDate(date.getDate() + days);
    return date;
};

const sameDay = (left, right) => (
    left
    && new Date(left).toDateString() === new Date(right).toDateString()
);

const formatDay = date => new Intl.DateTimeFormat('fr-FR', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
}).format(date);

const formatTime = value => value
    ? new Date(value).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
    : '';

function MissionStatus({ status }) {
    const meta = STATUS[status] || { label: status, tone: 'bg-slate-100 text-slate-700' };
    return <span className={`rounded-md px-2 py-1 text-[10px] font-black uppercase ${meta.tone}`}>{meta.label}</span>;
}

function MissionRow({ mission, onOpen }) {
    const validated = mission.openings?.filter(item => item.status === 'VALIDATED').length || 0;
    const site = mission.site;
    return (
        <button
            onClick={onOpen}
            className="grid w-full gap-3 border-b border-slate-100 px-4 py-4 text-left transition-colors last:border-0 hover:bg-slate-50 md:grid-cols-[minmax(200px,1.3fr)_minmax(150px,1fr)_minmax(140px,1fr)_auto]"
        >
            <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                    <strong className="truncate text-sm text-slate-950">{mission.reference}</strong>
                    <MissionStatus status={mission.status} />
                </div>
                <p className="mt-1 truncate text-sm font-bold text-slate-700">{mission.client_name}</p>
                <p className="mt-1 truncate text-xs font-semibold text-slate-400">{mission.purpose || SOURCE[mission.source_type]}</p>
            </div>
            <div className="min-w-0 text-xs font-bold text-slate-600">
                <p className="flex items-center gap-2"><MapPin className="h-4 w-4 shrink-0 text-blue-600" /><span className="truncate">{site ? `${site.reference} · ${site.city || site.address_line1}` : 'Chantier à préciser'}</span></p>
                <p className="mt-2 flex items-center gap-2"><UserRound className="h-4 w-4 shrink-0 text-indigo-600" /><span className="truncate">{mission.assigned_user_name || 'Non affecté'}</span></p>
            </div>
            <div className="text-xs font-bold text-slate-600">
                <p className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-amber-600" />{mission.scheduled_start ? new Date(mission.scheduled_start).toLocaleDateString('fr-FR') : 'Non planifié'}</p>
                <p className="mt-2 flex items-center gap-2"><Ruler className="h-4 w-4 text-emerald-600" />{validated}/{mission.openings?.length || 0} validé(s)</p>
            </div>
            <div className="flex items-center justify-end">
                <ChevronRight className="h-5 w-5 text-slate-300" />
            </div>
        </button>
    );
}

export default function MeasureMissionBoard() {
    const navigate = useNavigate();
    const [mode, setMode] = useState('calendar');
    const [weekAnchor, setWeekAnchor] = useState(() => startOfWeek(new Date()));
    const [statusFilter, setStatusFilter] = useState('ACTIVE');
    const [assigneeFilter, setAssigneeFilter] = useState('');

    const { data: missions = [], isLoading, error } = useQuery({
        queryKey: ['measure-missions'],
        queryFn: async () => (await api.get('/v2/mmg/missions')).data,
    });
    const { data: users = [] } = useQuery({
        queryKey: ['config-users-measure'],
        queryFn: async () => (await api.get('/v2/config/users')).data.filter(user => user.is_active),
    });

    const weekDays = useMemo(
        () => Array.from({ length: 7 }, (_, index) => addDays(weekAnchor, index)),
        [weekAnchor],
    );
    const filtered = useMemo(() => missions.filter(mission => {
        if (assigneeFilter && String(mission.assigned_user_id || '') !== assigneeFilter) return false;
        if (statusFilter === 'ACTIVE') return !['QUOTED', 'CANCELLED'].includes(mission.status);
        if (statusFilter === 'UNSCHEDULED') return ['DRAFT', 'TO_SCHEDULE'].includes(mission.status) || !mission.scheduled_start;
        if (statusFilter === 'BE') return ['TO_REVIEW', 'CORRECTION_REQUIRED'].includes(mission.status);
        if (statusFilter === 'DONE') return ['VALIDATED', 'QUOTED'].includes(mission.status);
        return true;
    }), [missions, statusFilter, assigneeFilter]);

    const metrics = useMemo(() => ({
        unscheduled: missions.filter(item => ['DRAFT', 'TO_SCHEDULE'].includes(item.status) || (!item.scheduled_start && item.status !== 'CANCELLED')).length,
        week: missions.filter(item => weekDays.some(day => sameDay(item.scheduled_start, day))).length,
        review: missions.filter(item => item.status === 'TO_REVIEW').length,
        correction: missions.filter(item => item.status === 'CORRECTION_REQUIRED').length,
    }), [missions, weekDays]);

    return (
        <div className="min-h-full bg-slate-50">
            <header className="border-b border-slate-200 bg-white px-4 py-5 md:px-8">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Missions de métré</p>
                        <h2 className="mt-1 text-2xl font-black text-slate-950">Planification et contrôle technique</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-500">Affectez les métreurs, suivez les rendez-vous et libérez les dossiers vers le chiffrage.</p>
                    </div>
                    <button onClick={() => navigate('/measure-missions/new')} className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 text-sm font-black text-white hover:bg-emerald-500">
                        <Plus className="h-4 w-4" />
                        Nouvelle mission
                    </button>
                </div>
                <div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                    <button onClick={() => setStatusFilter('UNSCHEDULED')} className="flex items-center justify-between border border-amber-200 bg-amber-50 px-4 py-3 text-left">
                        <span><span className="block text-[10px] font-black uppercase text-amber-700">À planifier</span><span className="mt-1 block text-xs font-bold text-amber-900">Affectation ou date manquante</span></span>
                        <strong className="text-2xl text-amber-800">{metrics.unscheduled}</strong>
                    </button>
                    <button onClick={() => { setStatusFilter('ACTIVE'); setMode('calendar'); }} className="flex items-center justify-between border border-blue-200 bg-blue-50 px-4 py-3 text-left">
                        <span><span className="block text-[10px] font-black uppercase text-blue-700">Cette semaine</span><span className="mt-1 block text-xs font-bold text-blue-900">Rendez-vous planifiés</span></span>
                        <strong className="text-2xl text-blue-800">{metrics.week}</strong>
                    </button>
                    <button onClick={() => setStatusFilter('BE')} className="flex items-center justify-between border border-orange-200 bg-orange-50 px-4 py-3 text-left">
                        <span><span className="block text-[10px] font-black uppercase text-orange-700">Contrôle BE</span><span className="mt-1 block text-xs font-bold text-orange-900">Dossiers à vérifier</span></span>
                        <strong className="text-2xl text-orange-800">{metrics.review}</strong>
                    </button>
                    <button onClick={() => setStatusFilter('BE')} className="flex items-center justify-between border border-red-200 bg-red-50 px-4 py-3 text-left">
                        <span><span className="block text-[10px] font-black uppercase text-red-700">Corrections</span><span className="mt-1 block text-xs font-bold text-red-900">Retours vers le métreur</span></span>
                        <strong className="text-2xl text-red-800">{metrics.correction}</strong>
                    </button>
                </div>
            </header>

            <div className="border-b border-slate-200 bg-white px-4 py-3 md:px-8">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap gap-2">
                        {[
                            ['ACTIVE', 'En cours'],
                            ['UNSCHEDULED', 'À planifier'],
                            ['BE', 'Contrôle BE'],
                            ['DONE', 'Validés / devis'],
                            ['ALL', 'Tous'],
                        ].map(([value, label]) => (
                            <button key={value} onClick={() => setStatusFilter(value)} className={`rounded-lg px-3 py-2 text-xs font-black ${statusFilter === value ? 'bg-slate-950 text-white' : 'border border-slate-200 bg-white text-slate-600'}`}>{label}</button>
                        ))}
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                        <select value={assigneeFilter} onChange={event => setAssigneeFilter(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700">
                            <option value="">Tous les métreurs</option>
                            {users.map(user => <option key={user.id} value={user.id}>{[user.first_name, user.last_name].filter(Boolean).join(' ') || user.username}</option>)}
                        </select>
                        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-1">
                            <button onClick={() => setMode('calendar')} className={`rounded-md px-3 py-1.5 text-xs font-black ${mode === 'calendar' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'}`}>Calendrier</button>
                            <button onClick={() => setMode('list')} className={`rounded-md px-3 py-1.5 text-xs font-black ${mode === 'list' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-500'}`}>Liste</button>
                        </div>
                    </div>
                </div>
            </div>

            {error && <div className="m-4 flex items-center gap-2 border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 md:m-8"><AlertTriangle className="h-4 w-4" />Impossible de charger les missions.</div>}
            {isLoading ? (
                <div className="p-12 text-center text-sm font-bold text-slate-400">Chargement des missions…</div>
            ) : mode === 'calendar' ? (
                <section className="px-4 py-5 md:px-8">
                    <div className="mb-4 flex items-center justify-between">
                        <button onClick={() => setWeekAnchor(current => addDays(current, -7))} title="Semaine précédente" className="rounded-lg border border-slate-200 bg-white p-2"><ChevronLeft className="h-4 w-4" /></button>
                        <div className="text-center">
                            <p className="text-sm font-black text-slate-900">Semaine du {weekAnchor.toLocaleDateString('fr-FR')}</p>
                            <button onClick={() => setWeekAnchor(startOfWeek(new Date()))} className="mt-1 text-xs font-black text-blue-600">Aujourd’hui</button>
                        </div>
                        <button onClick={() => setWeekAnchor(current => addDays(current, 7))} title="Semaine suivante" className="rounded-lg border border-slate-200 bg-white p-2"><ChevronRight className="h-4 w-4" /></button>
                    </div>
                    <div className="grid gap-2 lg:grid-cols-7">
                        {weekDays.map(day => {
                            const dayMissions = filtered.filter(mission => sameDay(mission.scheduled_start, day));
                            const isToday = sameDay(new Date(), day);
                            return (
                                <div key={day.toISOString()} className={`min-h-40 border bg-white ${isToday ? 'border-blue-400' : 'border-slate-200'}`}>
                                    <div className={`border-b px-3 py-2 text-xs font-black uppercase ${isToday ? 'border-blue-200 bg-blue-50 text-blue-800' : 'border-slate-100 text-slate-500'}`}>{formatDay(day)}</div>
                                    <div className="space-y-2 p-2">
                                        {dayMissions.map(mission => (
                                            <button key={mission.id} onClick={() => navigate(`/measure-missions/${mission.id}`)} className="w-full border-l-4 border-blue-500 bg-slate-50 px-2 py-2 text-left hover:bg-blue-50">
                                                <p className="text-[10px] font-black text-blue-700">{formatTime(mission.scheduled_start)} · {mission.reference}</p>
                                                <p className="mt-1 truncate text-xs font-black text-slate-900">{mission.client_name}</p>
                                                <p className="mt-1 truncate text-[10px] font-bold text-slate-500">{mission.assigned_user_name || 'Non affecté'}</p>
                                            </button>
                                        ))}
                                        {!dayMissions.length && <p className="px-2 py-5 text-center text-[10px] font-bold text-slate-300">Libre</p>}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {filtered.some(mission => !mission.scheduled_start) && (
                        <div className="mt-5 border border-amber-200 bg-amber-50">
                            <div className="flex items-center gap-2 border-b border-amber-200 px-4 py-3 text-sm font-black text-amber-900"><Clock3 className="h-4 w-4" />Missions sans rendez-vous</div>
                            {filtered.filter(mission => !mission.scheduled_start).map(mission => <MissionRow key={mission.id} mission={mission} onOpen={() => navigate(`/measure-missions/${mission.id}`)} />)}
                        </div>
                    )}
                </section>
            ) : (
                <section className="px-4 py-5 md:px-8">
                    <div className="border border-slate-200 bg-white">
                        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
                            <ClipboardCheck className="h-4 w-4 text-emerald-600" />
                            <h3 className="text-sm font-black text-slate-900">{filtered.length} mission(s)</h3>
                        </div>
                        {filtered.map(mission => <MissionRow key={mission.id} mission={mission} onOpen={() => navigate(`/measure-missions/${mission.id}`)} />)}
                        {!filtered.length && <div className="p-12 text-center"><CheckCircle2 className="mx-auto h-10 w-10 text-emerald-300" /><p className="mt-3 text-sm font-black text-slate-500">Aucune mission dans cette vue.</p></div>}
                    </div>
                </section>
            )}
        </div>
    );
}
