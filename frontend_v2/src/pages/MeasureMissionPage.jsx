import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
    AlertTriangle,
    ArrowLeft,
    CalendarDays,
    Building2,
    Check,
    CheckCircle2,
    ChevronRight,
    ClipboardCheck,
    Clock3,
    Copy,
    DoorOpen,
    Download,
    FileText,
    Loader2,
    MapPin,
    Menu,
    Plus,
    Ruler,
    Save,
    Trash2,
    Upload,
    UserRound,
} from 'lucide-react';
import Sidebar from '../components/Sidebar';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

const STATUS_META = {
    DRAFT: ['Brouillon', 'bg-slate-100 text-slate-700'],
    TO_SCHEDULE: ['À planifier', 'bg-amber-100 text-amber-800'],
    SCHEDULED: ['Planifiée', 'bg-blue-100 text-blue-800'],
    IN_CAPTURE: ['Saisie des cotes', 'bg-indigo-100 text-indigo-800'],
    ON_SITE: ['Sur site', 'bg-indigo-100 text-indigo-800'],
    TO_REVIEW: ['Contrôle BE', 'bg-orange-100 text-orange-800'],
    CORRECTION_REQUIRED: ['À corriger', 'bg-red-100 text-red-800'],
    VALIDATED: ['Validée BE', 'bg-emerald-100 text-emerald-800'],
    QUOTED: ['Chiffrée', 'bg-teal-100 text-teal-800'],
    CANCELLED: ['Annulée', 'bg-slate-200 text-slate-600'],
};

const SOURCE_META = {
    SITE_VISIT: {
        label: 'Métré MMG sur chantier',
        short: 'Relevé MMG',
        description: 'Une mission est planifiée et les cotes sont relevées sur place par MMG.',
        icon: MapPin,
    },
    CLIENT_DOCUMENTS: {
        label: 'Cotes apportées par le client',
        short: 'Cotes client',
        description: 'Plans, croquis ou relevés client à contrôler avant tout engagement de fabrication.',
        icon: FileText,
    },
    AGENCY_ASSISTED: {
        label: 'Saisie assistée en agence',
        short: 'Saisie agence',
        description: 'Le commercial ou technicien structure les cotes avec le client au comptoir.',
        icon: Building2,
    },
};

const VERIFICATION_META = {
    UNVERIFIED: ['À contrôler', 'border-slate-200 bg-slate-50 text-slate-700'],
    BE_REVIEWED: ['Contrôlé BE', 'border-blue-200 bg-blue-50 text-blue-700'],
    CLIENT_APPROVAL_REQUIRED: ['Validation client requise', 'border-amber-200 bg-amber-50 text-amber-800'],
    SITE_VERIFICATION_REQUIRED: ['Vérification chantier requise', 'border-red-200 bg-red-50 text-red-700'],
    READY_FOR_FABRICATION: ['Bon pour fabrication', 'border-emerald-200 bg-emerald-50 text-emerald-700'],
};

const OPENING_STATUS_META = {
    DRAFT: ['À compléter', 'bg-slate-100 text-slate-600'],
    COMPLETE: ['Terminé', 'bg-blue-100 text-blue-700'],
    TO_REVIEW: ['À contrôler', 'bg-orange-100 text-orange-700'],
    CORRECTION_REQUIRED: ['Correction', 'bg-red-100 text-red-700'],
    VALIDATED: ['Validé', 'bg-emerald-100 text-emerald-700'],
};

const emptyOpening = {
    label: '',
    room: '',
    product_type: 'WINDOW',
    width_mm: '',
    height_mm: '',
    passage_height_mm: '',
    material: 'ALU',
    opening_type: '',
    opening_side: '',
    sash_count: 1,
    installation_type: '',
    status: 'DRAFT',
    notes: '',
};

const toLocalInput = value => {
    if (!value) return '';
    const date = new Date(value);
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 16);
};

const formatDate = value => value
    ? new Date(value).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })
    : 'Non planifiée';

const apiError = error => error?.response?.data?.detail || 'Une erreur est survenue.';

function StatusBadge({ status, opening = false }) {
    const meta = (opening ? OPENING_STATUS_META : STATUS_META)[status] || [status, 'bg-slate-100 text-slate-700'];
    return (
        <span className={`inline-flex rounded-md px-2 py-1 text-[10px] font-black uppercase ${meta[1]}`}>
            {meta[0]}
        </span>
    );
}

function Field({ label, children, className = '' }) {
    return (
        <label className={`block ${className}`}>
            <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">{label}</span>
            {children}
        </label>
    );
}

const inputClass = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100';

export default function MeasureMissionPage() {
    const navigate = useNavigate();
    const { missionId } = useParams();
    const [searchParams] = useSearchParams();
    const { user } = useAuth();
    const isNew = !missionId;
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');
    const [clients, setClients] = useState([]);
    const [users, setUsers] = useState([]);
    const [sites, setSites] = useState([]);
    const [mission, setMission] = useState(null);
    const [selectedOpeningId, setSelectedOpeningId] = useState(null);
    const [openingForm, setOpeningForm] = useState(emptyOpening);
    const [planForm, setPlanForm] = useState({
        client_id: searchParams.get('clientId') || '',
        source_type: searchParams.get('source') || 'SITE_VISIT',
        project_scope: searchParams.get('scope') || 'SUPPLY_AND_INSTALL',
        site_address_id: '',
        assigned_user_id: '',
        scheduled_start: '',
        scheduled_end: '',
        purpose: '',
        notes: '',
        create_site: false,
        site: {
            label: 'Chantier',
            address_line1: '',
            address_line2: '',
            postal_code: '',
            city: '',
            country: 'FR',
            contact_name: '',
            contact_phone: '',
            access_instructions: '',
        },
    });

    const roles = new Set([user?.role, ...(user?.roles || [])].filter(Boolean));
    const canReview = [...roles].some(role => ['ADMIN', 'MANAGER', 'QUALITY_CONTROLLER', 'WORKSHOP_LEAD'].includes(role));
    const selectedOpening = mission?.openings?.find(item => item.id === selectedOpeningId);
    const openingCount = mission?.openings?.length || 0;
    const completedCount = mission?.openings?.filter(item => ['COMPLETE', 'TO_REVIEW', 'VALIDATED'].includes(item.status)).length || 0;

    const selectedClient = useMemo(
        () => clients.find(client => String(client.id) === String(planForm.client_id)),
        [clients, planForm.client_id],
    );

    useEffect(() => {
        const bootstrap = async () => {
            setLoading(true);
            setError('');
            try {
                if (isNew) {
                    const [clientsResponse, usersResponse] = await Promise.all([
                        api.get('/v2/partners/clients'),
                        api.get('/v2/config/users'),
                    ]);
                    setClients(clientsResponse.data.filter(client => client.is_active !== false));
                    setUsers(usersResponse.data.filter(item => item.is_active));
                } else {
                    const response = await api.get(`/v2/mmg/missions/${missionId}`);
                    setMission(response.data);
                    setPlanForm(current => ({
                        ...current,
                        client_id: response.data.client_id,
                        site_address_id: response.data.site_address_id || '',
                        assigned_user_id: response.data.assigned_user_id || '',
                        source_type: response.data.source_type,
                        project_scope: response.data.project_scope,
                        scheduled_start: toLocalInput(response.data.scheduled_start),
                        scheduled_end: toLocalInput(response.data.scheduled_end),
                        purpose: response.data.purpose || '',
                        notes: response.data.notes || '',
                    }));
                    const usersResponse = await api.get('/v2/config/users');
                    setUsers(usersResponse.data.filter(item => item.is_active));
                    if (response.data.openings?.length) {
                        selectOpening(response.data.openings[0]);
                    }
                }
            } catch (requestError) {
                setError(apiError(requestError));
            } finally {
                setLoading(false);
            }
        };
        bootstrap();
    }, [isNew, missionId]);

    useEffect(() => {
        const loadSites = async () => {
            if (!planForm.client_id) {
                setSites([]);
                return;
            }
            try {
                const response = await api.get('/v2/mmg/sites', { params: { client_id: planForm.client_id } });
                setSites(response.data);
                if (isNew && response.data.length && !planForm.site_address_id) {
                    const defaultSite = response.data.find(site => site.is_default) || response.data[0];
                    setPlanForm(current => ({ ...current, site_address_id: defaultSite.id }));
                }
            } catch {
                setSites([]);
            }
        };
        loadSites();
    }, [planForm.client_id, isNew]);

    const selectOpening = opening => {
        setSelectedOpeningId(opening.id);
        setOpeningForm({
            ...emptyOpening,
            ...opening,
            width_mm: opening.width_mm ?? '',
            height_mm: opening.height_mm ?? '',
            passage_height_mm: opening.passage_height_mm ?? '',
        });
    };

    const refreshMission = async (preferredOpeningId = selectedOpeningId) => {
        const response = await api.get(`/v2/mmg/missions/${missionId}`);
        setMission(response.data);
        const next = response.data.openings?.find(item => item.id === preferredOpeningId);
        if (next) selectOpening(next);
        else if (response.data.openings?.length) selectOpening(response.data.openings[0]);
        else {
            setSelectedOpeningId(null);
            setOpeningForm(emptyOpening);
        }
    };

    const submitPlan = async event => {
        event.preventDefault();
        if (!planForm.client_id) {
            setError('Sélectionnez clairement le client de la mission.');
            return;
        }
        setSaving(true);
        setError('');
        try {
            const payload = {
                client_id: Number(planForm.client_id),
                source_type: planForm.source_type,
                project_scope: planForm.project_scope,
                assigned_user_id: planForm.assigned_user_id ? Number(planForm.assigned_user_id) : null,
                scheduled_start: planForm.scheduled_start || null,
                scheduled_end: planForm.scheduled_end || null,
                purpose: planForm.purpose || null,
                notes: planForm.notes || null,
                status: planForm.source_type === 'SITE_VISIT'
                    ? (planForm.assigned_user_id && planForm.scheduled_start ? 'SCHEDULED' : 'TO_SCHEDULE')
                    : 'IN_CAPTURE',
            };
            if (planForm.create_site) {
                payload.site = { ...planForm.site, client_id: Number(planForm.client_id) };
            } else if (planForm.site_address_id) {
                payload.site_address_id = Number(planForm.site_address_id);
            }
            const response = await api.post('/v2/mmg/missions', payload);
            navigate(`/measure-missions/${response.data.id}`, { replace: true });
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const savePlan = async () => {
        setSaving(true);
        setError('');
        try {
            await api.put(`/v2/mmg/missions/${missionId}`, {
                site_address_id: planForm.site_address_id ? Number(planForm.site_address_id) : null,
                assigned_user_id: planForm.assigned_user_id ? Number(planForm.assigned_user_id) : null,
                project_scope: planForm.project_scope,
                scheduled_start: planForm.scheduled_start || null,
                scheduled_end: planForm.scheduled_end || null,
                purpose: planForm.purpose || null,
                notes: planForm.notes || null,
            });
            await refreshMission();
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const newOpening = () => {
        setSelectedOpeningId(null);
        setOpeningForm({
            ...emptyOpening,
            label: `Ouvrage ${openingCount + 1}`,
        });
    };

    const saveOpening = async (markComplete = false) => {
        setSaving(true);
        setError('');
        const payload = {
            ...openingForm,
            width_mm: openingForm.width_mm === '' ? null : Number(openingForm.width_mm),
            height_mm: openingForm.height_mm === '' ? null : Number(openingForm.height_mm),
            passage_height_mm: openingForm.passage_height_mm === '' ? null : Number(openingForm.passage_height_mm),
            sash_count: Number(openingForm.sash_count || 1),
            status: markComplete ? 'COMPLETE' : openingForm.status,
        };
        try {
            let response;
            if (selectedOpeningId) {
                response = await api.put(`/v2/mmg/missions/${missionId}/openings/${selectedOpeningId}`, payload);
            } else {
                response = await api.post(`/v2/mmg/missions/${missionId}/openings`, payload);
            }
            await refreshMission(response.data.id);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const duplicateOpening = async () => {
        if (!selectedOpening) return;
        setSaving(true);
        try {
            const payload = {
                ...openingForm,
                label: `${openingForm.label} - copie`,
                status: 'DRAFT',
            };
            delete payload.id;
            delete payload.mission_id;
            delete payload.sequence;
            delete payload.created_at;
            delete payload.updated_at;
            const response = await api.post(`/v2/mmg/missions/${missionId}/openings`, payload);
            await refreshMission(response.data.id);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const deleteOpening = async () => {
        if (!selectedOpeningId || !window.confirm('Supprimer cet ouvrage de la mission ?')) return;
        setSaving(true);
        try {
            await api.delete(`/v2/mmg/missions/${missionId}/openings/${selectedOpeningId}`);
            await refreshMission(null);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const changeStatus = async status => {
        setSaving(true);
        setError('');
        try {
            const response = await api.patch(`/v2/mmg/missions/${missionId}/status`, { status });
            setMission(response.data);
            if (response.data.openings?.length) selectOpening(response.data.openings[0]);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const uploadDocuments = async event => {
        const files = Array.from(event.target.files || []);
        if (!files.length) return;
        setSaving(true);
        setError('');
        try {
            let latest;
            for (const file of files) {
                const data = new FormData();
                data.append('file', file);
                latest = await api.post(`/v2/mmg/missions/${missionId}/documents`, data, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                });
            }
            setMission(latest.data);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            event.target.value = '';
            setSaving(false);
        }
    };

    const downloadDocument = async document => {
        try {
            const response = await api.get(
                `/v2/mmg/missions/${missionId}/documents/${document.id}/download`,
                { responseType: 'blob' },
            );
            const href = URL.createObjectURL(response.data);
            const anchor = window.document.createElement('a');
            anchor.href = href;
            anchor.download = document.original_filename;
            anchor.click();
            URL.revokeObjectURL(href);
        } catch (requestError) {
            setError(apiError(requestError));
        }
    };

    const deleteDocument = async documentId => {
        if (!window.confirm('Supprimer ce document source ?')) return;
        try {
            const response = await api.delete(`/v2/mmg/missions/${missionId}/documents/${documentId}`);
            setMission(response.data);
        } catch (requestError) {
            setError(apiError(requestError));
        }
    };

    const confirmVerification = async action => {
        setSaving(true);
        setError('');
        try {
            const response = await api.patch(`/v2/mmg/missions/${missionId}/verification`, { action });
            setMission(response.data);
        } catch (requestError) {
            setError(apiError(requestError));
        } finally {
            setSaving(false);
        }
    };

    const managerNavigate = view => navigate(`/manager?view=${view}`);
    const missionLocked = ['VALIDATED', 'QUOTED', 'CANCELLED'].includes(mission?.status);
    const isSiteVisit = (mission?.source_type || planForm.source_type) === 'SITE_VISIT';
    const sourceMeta = SOURCE_META[mission?.source_type || planForm.source_type] || SOURCE_META.SITE_VISIT;
    const verificationMeta = VERIFICATION_META[mission?.verification_status] || VERIFICATION_META.UNVERIFIED;

    if (loading || (!isNew && !mission)) {
        return <div className="min-h-screen bg-slate-50 flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-blue-600" /></div>;
    }

    return (
        <div className="min-h-screen bg-slate-50">
            <Sidebar activeView="crm" setActiveView={managerNavigate} isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
            <main className="min-h-screen lg:ml-72">
                <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white px-4 md:px-7">
                    <button onClick={() => setSidebarOpen(true)} className="rounded-lg border border-slate-200 p-2 lg:hidden">
                        <Menu className="h-5 w-5" />
                    </button>
                    <button onClick={() => navigate('/manager?view=crm')} className="inline-flex items-center gap-2 text-sm font-black text-slate-600 hover:text-slate-950">
                        <ArrowLeft className="h-4 w-4" />
                        CRM
                    </button>
                    <ChevronRight className="h-4 w-4 text-slate-300" />
                    <span className="truncate text-sm font-black text-slate-900">
                        {isNew ? 'Créer un dossier de cotes' : mission?.reference}
                    </span>
                </header>

                {error && (
                    <div className="mx-4 mt-4 flex items-start gap-3 border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 md:mx-7">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        {error}
                    </div>
                )}

                {isNew ? (
                    <form onSubmit={submitPlan}>
                        <section className="border-b border-slate-200 bg-white px-4 py-7 md:px-7">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Avant-vente fabrication</p>
                            <h1 className="mt-1 text-2xl font-black text-slate-950 md:text-3xl">Créer un dossier de cotes</h1>
                            <p className="mt-2 max-w-3xl text-sm font-semibold text-slate-500">
                                Choisissez l'origine des mesures. Le contrôle BE reste commun aux trois parcours.
                            </p>
                        </section>
                        <section className="grid gap-8 px-4 py-7 md:px-7 2xl:grid-cols-[minmax(0,1fr)_360px]">
                            <div className="space-y-8">
                                <div>
                                    <h2 className="mb-4 text-lg font-black text-slate-900">1. Origine et responsabilité des cotes</h2>
                                    <div className="grid gap-3 lg:grid-cols-3">
                                        {Object.entries(SOURCE_META).map(([source, meta]) => {
                                            const Icon = meta.icon;
                                            const selected = planForm.source_type === source;
                                            return (
                                                <button
                                                    type="button"
                                                    key={source}
                                                    onClick={() => setPlanForm(current => ({
                                                        ...current,
                                                        source_type: source,
                                                        assigned_user_id: source === 'SITE_VISIT' ? current.assigned_user_id : '',
                                                        scheduled_start: source === 'SITE_VISIT' ? current.scheduled_start : '',
                                                        scheduled_end: source === 'SITE_VISIT' ? current.scheduled_end : '',
                                                    }))}
                                                    className={`border p-4 text-left transition-colors ${selected ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white hover:border-blue-300'}`}
                                                >
                                                    <Icon className={`h-5 w-5 ${selected ? 'text-blue-700' : 'text-slate-400'}`} />
                                                    <p className="mt-3 text-sm font-black text-slate-950">{meta.label}</p>
                                                    <p className="mt-1 text-xs font-semibold leading-5 text-slate-500">{meta.description}</p>
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                                        <Field label="Périmètre commercial">
                                            <select value={planForm.project_scope} onChange={event => setPlanForm(current => ({ ...current, project_scope: event.target.value }))} className={inputClass}>
                                                <option value="SUPPLY_AND_INSTALL">Fourniture avec pose</option>
                                                <option value="SUPPLY_ONLY">Fourniture seule</option>
                                            </select>
                                        </Field>
                                        <div className={`border px-4 py-3 text-xs font-bold ${planForm.source_type === 'SITE_VISIT' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
                                            {planForm.source_type === 'SITE_VISIT'
                                                ? 'Les cotes seront relevées par MMG et pourront être libérées après contrôle BE.'
                                                : planForm.project_scope === 'SUPPLY_ONLY'
                                                    ? 'Après contrôle BE, une validation explicite des cotes par le client sera exigée.'
                                                    : 'Une vérification MMG sur chantier restera obligatoire avant fabrication et pose.'}
                                        </div>
                                    </div>
                                </div>

                                <div className="border-t border-slate-200 pt-7">
                                    <h2 className="mb-4 text-lg font-black text-slate-900">2. Client et chantier</h2>
                                    <div className="grid gap-4 md:grid-cols-2">
                                        <Field label="Client">
                                            <select
                                                value={planForm.client_id}
                                                onChange={event => setPlanForm(current => ({ ...current, client_id: event.target.value, site_address_id: '' }))}
                                                className={inputClass}
                                            >
                                                <option value="">Sélectionner un client</option>
                                                {clients.map(client => <option key={client.id} value={client.id}>{client.name} · {client.phone || 'sans téléphone'}</option>)}
                                            </select>
                                        </Field>
                                        <Field label="Adresse chantier enregistrée">
                                            <select
                                                value={planForm.site_address_id}
                                                disabled={planForm.create_site || !planForm.client_id}
                                                onChange={event => setPlanForm(current => ({ ...current, site_address_id: event.target.value }))}
                                                className={inputClass}
                                            >
                                                <option value="">Choisir une adresse</option>
                                                {sites.map(site => <option key={site.id} value={site.id}>{site.label} · {site.address_line1}, {site.postal_code} {site.city}</option>)}
                                            </select>
                                        </Field>
                                    </div>
                                    {selectedClient && (
                                        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 border-l-4 border-blue-500 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-950">
                                            <strong>{selectedClient.name}</strong>
                                            <span>{selectedClient.phone || 'Téléphone non renseigné'}</span>
                                            <span>{selectedClient.email || 'Email non renseigné'}</span>
                                        </div>
                                    )}
                                    <label className="mt-4 flex items-center gap-3 text-sm font-black text-slate-700">
                                        <input
                                            type="checkbox"
                                            checked={planForm.create_site}
                                            onChange={event => setPlanForm(current => ({ ...current, create_site: event.target.checked }))}
                                            className="h-4 w-4"
                                        />
                                        Créer une nouvelle adresse chantier
                                    </label>
                                    {planForm.create_site && (
                                        <div className="mt-4 grid gap-4 border-t border-slate-200 pt-4 md:grid-cols-6">
                                            <Field label="Libellé" className="md:col-span-2"><input value={planForm.site.label} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, label: event.target.value } }))} className={inputClass} /></Field>
                                            <Field label="Adresse" className="md:col-span-4"><input required value={planForm.site.address_line1} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, address_line1: event.target.value } }))} className={inputClass} /></Field>
                                            <Field label="Code postal" className="md:col-span-2"><input value={planForm.site.postal_code} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, postal_code: event.target.value } }))} className={inputClass} /></Field>
                                            <Field label="Ville" className="md:col-span-3"><input value={planForm.site.city} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, city: event.target.value } }))} className={inputClass} /></Field>
                                            <Field label="Pays" className="md:col-span-1"><input value={planForm.site.country} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, country: event.target.value } }))} className={inputClass} /></Field>
                                            <Field label="Consignes d'accès" className="md:col-span-6"><textarea value={planForm.site.access_instructions} onChange={event => setPlanForm(current => ({ ...current, site: { ...current.site, access_instructions: event.target.value } }))} className={`${inputClass} min-h-20`} /></Field>
                                        </div>
                                    )}
                                </div>

                                <div className="border-t border-slate-200 pt-7">
                                    <h2 className="mb-4 text-lg font-black text-slate-900">{isSiteVisit ? '3. Affectation et rendez-vous' : '3. Préparation du dossier technique'}</h2>
                                    {isSiteVisit ? (
                                        <div className="grid gap-4 md:grid-cols-3">
                                            <Field label="Métreur affecté">
                                                <select value={planForm.assigned_user_id} onChange={event => setPlanForm(current => ({ ...current, assigned_user_id: event.target.value }))} className={inputClass}>
                                                    <option value="">À affecter</option>
                                                    {users.map(item => <option key={item.id} value={item.id}>{[item.first_name, item.last_name].filter(Boolean).join(' ') || item.username} · {item.job_title || item.role}</option>)}
                                                </select>
                                            </Field>
                                            <Field label="Début planifié"><input type="datetime-local" value={planForm.scheduled_start} onChange={event => setPlanForm(current => ({ ...current, scheduled_start: event.target.value }))} className={inputClass} /></Field>
                                            <Field label="Fin planifiée"><input type="datetime-local" value={planForm.scheduled_end} onChange={event => setPlanForm(current => ({ ...current, scheduled_end: event.target.value }))} className={inputClass} /></Field>
                                        </div>
                                    ) : (
                                        <div className="border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-bold text-blue-900">
                                            Le dossier sera créé immédiatement en saisie. Vous pourrez ensuite joindre les plans ou croquis et décrire plusieurs ouvrages avant le contrôle BE.
                                        </div>
                                    )}
                                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                                        <Field label="Objet du dossier"><input value={planForm.purpose} onChange={event => setPlanForm(current => ({ ...current, purpose: event.target.value }))} placeholder="Ex. remplacement de 6 menuiseries" className={inputClass} /></Field>
                                        <Field label="Notes de préparation"><input value={planForm.notes} onChange={event => setPlanForm(current => ({ ...current, notes: event.target.value }))} placeholder="Contraintes, contact, matériel à prévoir" className={inputClass} /></Field>
                                    </div>
                                </div>
                            </div>
                            <aside className="self-start border-t border-slate-200 pt-6 2xl:border-l 2xl:border-t-0 2xl:pl-8 2xl:pt-0">
                                <h2 className="text-lg font-black text-slate-900">Dossier prêt ?</h2>
                                <div className="mt-4 space-y-3 text-sm font-bold text-slate-600">
                                    <p className="flex gap-2"><Check className={`h-4 w-4 shrink-0 ${planForm.client_id ? 'text-emerald-600' : 'text-slate-300'}`} /> Client identifié</p>
                                    <p className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-emerald-600" /> Origine des cotes déclarée</p>
                                    <p className="flex gap-2"><Check className={`h-4 w-4 shrink-0 ${planForm.site_address_id || (planForm.create_site && planForm.site.address_line1) ? 'text-emerald-600' : 'text-slate-300'}`} /> Chantier identifié</p>
                                    {isSiteVisit ? (
                                        <>
                                            <p className="flex gap-2"><Check className={`h-4 w-4 shrink-0 ${planForm.assigned_user_id ? 'text-emerald-600' : 'text-slate-300'}`} /> Métreur affecté</p>
                                            <p className="flex gap-2"><Check className={`h-4 w-4 shrink-0 ${planForm.scheduled_start ? 'text-emerald-600' : 'text-slate-300'}`} /> Rendez-vous planifié</p>
                                        </>
                                    ) : (
                                        <p className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-amber-500" /> Validation finale encore bloquée</p>
                                    )}
                                </div>
                                <button disabled={saving} className="mt-7 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-black text-white hover:bg-blue-500 disabled:opacity-50">
                                    {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarDays className="h-4 w-4" />}
                                    {isSiteVisit ? 'Créer la mission' : 'Créer le dossier de cotes'}
                                </button>
                            </aside>
                        </section>
                    </form>
                ) : (
                    <>
                        <section className="border-b border-slate-200 bg-white px-4 py-6 md:px-7">
                            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                                <div>
                                    <div className="flex flex-wrap items-center gap-3">
                                        <StatusBadge status={mission.status} />
                                        <span className="inline-flex border border-blue-200 bg-blue-50 px-2 py-1 text-[10px] font-black uppercase text-blue-700">{sourceMeta.short}</span>
                                        <span className={`inline-flex border px-2 py-1 text-[10px] font-black uppercase ${verificationMeta[1]}`}>{verificationMeta[0]}</span>
                                        <span className="text-xs font-black text-slate-400">{mission.reference}</span>
                                    </div>
                                    <h1 className="mt-2 text-2xl font-black text-slate-950 md:text-3xl">{mission.client_name}</h1>
                                    <p className="mt-1 text-sm font-bold text-slate-500">{mission.purpose || 'Mission de prise de côtes'}</p>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {mission.status === 'SCHEDULED' && <button onClick={() => changeStatus('IN_CAPTURE')} className="rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-black text-white">Démarrer le relevé</button>}
                                    {['IN_CAPTURE', 'ON_SITE', 'CORRECTION_REQUIRED'].includes(mission.status) && <button onClick={() => changeStatus('TO_REVIEW')} className="rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-black text-white">Envoyer au contrôle BE</button>}
                                    {mission.status === 'TO_REVIEW' && canReview && (
                                        <>
                                            <button onClick={() => changeStatus('CORRECTION_REQUIRED')} className="rounded-lg border border-red-200 bg-white px-4 py-2.5 text-sm font-black text-red-700">Demander correction</button>
                                            <button onClick={() => changeStatus('VALIDATED')} className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-black text-white">Valider le métré</button>
                                        </>
                                    )}
                                    {mission.status === 'VALIDATED' && mission.verification_status === 'CLIENT_APPROVAL_REQUIRED' && (
                                        <button onClick={() => confirmVerification('CLIENT_APPROVED')} className="rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-black text-white">Confirmer validation client</button>
                                    )}
                                    {mission.status === 'VALIDATED' && mission.verification_status === 'SITE_VERIFICATION_REQUIRED' && canReview && (
                                        <button onClick={() => confirmVerification('SITE_VERIFIED')} className="rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-black text-white">Confirmer vérification chantier MMG</button>
                                    )}
                                </div>
                            </div>
                            <div className="mt-6 grid gap-4 border-t border-slate-100 pt-5 sm:grid-cols-2 xl:grid-cols-4">
                                <div className="flex gap-3"><MapPin className="h-5 w-5 text-blue-600" /><div><p className="text-[10px] font-black uppercase text-slate-400">Chantier</p><p className="text-sm font-black text-slate-800">{mission.site ? `${mission.site.address_line1}, ${mission.site.postal_code || ''} ${mission.site.city || ''}` : 'Adresse à préciser'}</p></div></div>
                                <div className="flex gap-3"><UserRound className="h-5 w-5 text-indigo-600" /><div><p className="text-[10px] font-black uppercase text-slate-400">{isSiteVisit ? 'Métreur' : 'Origine'}</p><p className="text-sm font-black text-slate-800">{isSiteVisit ? (mission.assigned_user_name || 'Non affecté') : sourceMeta.label}</p></div></div>
                                <div className="flex gap-3"><Clock3 className="h-5 w-5 text-amber-600" /><div><p className="text-[10px] font-black uppercase text-slate-400">{isSiteVisit ? 'Rendez-vous' : 'Périmètre'}</p><p className="text-sm font-black text-slate-800">{isSiteVisit ? formatDate(mission.scheduled_start) : (mission.project_scope === 'SUPPLY_ONLY' ? 'Fourniture seule' : 'Fourniture avec pose')}</p></div></div>
                                <div className="flex gap-3"><ClipboardCheck className="h-5 w-5 text-emerald-600" /><div><p className="text-[10px] font-black uppercase text-slate-400">Avancement</p><p className="text-sm font-black text-slate-800">{completedCount}/{openingCount} ouvrage(s) terminé(s)</p></div></div>
                            </div>
                        </section>

                        {!missionLocked && isSiteVisit && (
                            <section className="border-b border-slate-200 bg-slate-100 px-4 py-4 md:px-7">
                                <div className="grid gap-3 md:grid-cols-4">
                                    <select value={planForm.assigned_user_id} onChange={event => setPlanForm(current => ({ ...current, assigned_user_id: event.target.value }))} className={inputClass}>
                                        <option value="">Métreur à affecter</option>
                                        {users.map(item => <option key={item.id} value={item.id}>{[item.first_name, item.last_name].filter(Boolean).join(' ') || item.username}</option>)}
                                    </select>
                                    <input type="datetime-local" value={planForm.scheduled_start} onChange={event => setPlanForm(current => ({ ...current, scheduled_start: event.target.value }))} className={inputClass} />
                                    <input type="datetime-local" value={planForm.scheduled_end} onChange={event => setPlanForm(current => ({ ...current, scheduled_end: event.target.value }))} className={inputClass} />
                                    <button onClick={savePlan} disabled={saving} className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-black text-white"><Save className="h-4 w-4" /> Enregistrer planning</button>
                                </div>
                            </section>
                        )}

                        <section className="border-b border-slate-200 bg-white px-4 py-5 md:px-7">
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Documents source</p>
                                    <h2 className="mt-1 text-base font-black text-slate-900">Plans, croquis et relevés fournis</h2>
                                    <p className="mt-1 text-xs font-semibold text-slate-500">
                                        {mission.source_type === 'CLIENT_DOCUMENTS'
                                            ? 'Au moins un document client est obligatoire avant le contrôle BE.'
                                            : 'Conservez ici les éléments utilisés pour établir les cotes.'}
                                    </p>
                                </div>
                                {!missionLocked && (
                                    <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-black text-blue-700 hover:bg-blue-100">
                                        <Upload className="h-4 w-4" />
                                        Ajouter des documents
                                        <input type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" onChange={uploadDocuments} className="hidden" />
                                    </label>
                                )}
                            </div>
                            <div className="mt-4 flex flex-wrap gap-2">
                                {mission.source_documents?.map(document => (
                                    <div key={document.id} className="flex max-w-full items-center gap-2 border border-slate-200 bg-slate-50 px-3 py-2">
                                        <FileText className="h-4 w-4 shrink-0 text-slate-500" />
                                        <button onClick={() => downloadDocument(document)} className="max-w-64 truncate text-left text-xs font-black text-slate-700 hover:text-blue-700">{document.original_filename}</button>
                                        <button onClick={() => downloadDocument(document)} title="Télécharger" className="p-1 text-slate-400 hover:text-blue-700"><Download className="h-3.5 w-3.5" /></button>
                                        {!missionLocked && <button onClick={() => deleteDocument(document.id)} title="Supprimer" className="p-1 text-slate-400 hover:text-red-600"><Trash2 className="h-3.5 w-3.5" /></button>}
                                    </div>
                                ))}
                                {!mission.source_documents?.length && <p className="text-xs font-bold text-slate-400">Aucun document joint.</p>}
                            </div>
                        </section>

                        <section className="grid min-h-[calc(100vh-330px)] lg:grid-cols-[300px_minmax(0,1fr)]">
                            <aside className="border-b border-slate-200 bg-white lg:border-b-0 lg:border-r">
                                <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Ouvrages relevés</p>
                                        <p className="mt-1 text-sm font-black text-slate-900">{openingCount} élément(s)</p>
                                    </div>
                                    {!missionLocked && <button onClick={newOpening} title="Ajouter un ouvrage" className="rounded-lg bg-blue-600 p-2 text-white"><Plus className="h-4 w-4" /></button>}
                                </div>
                                <div className="max-h-72 overflow-y-auto p-2 lg:max-h-none">
                                    {mission.openings?.map(opening => (
                                        <button
                                            key={opening.id}
                                            onClick={() => selectOpening(opening)}
                                            className={`mb-1 w-full border-l-4 px-3 py-3 text-left ${opening.id === selectedOpeningId ? 'border-blue-600 bg-blue-50' : 'border-transparent hover:bg-slate-50'}`}
                                        >
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="min-w-0">
                                                    <p className="truncate text-sm font-black text-slate-900">{opening.sequence}. {opening.label}</p>
                                                    <p className="mt-1 text-xs font-bold text-slate-500">{opening.room || 'Pièce non précisée'} · {opening.width_mm || '?'} × {opening.height_mm || '?'} mm</p>
                                                </div>
                                                <StatusBadge status={opening.status} opening />
                                            </div>
                                        </button>
                                    ))}
                                    {!openingCount && <p className="p-6 text-center text-sm font-bold text-slate-400">Ajoutez le premier ouvrage du dossier de cotes.</p>}
                                </div>
                            </aside>

                            <div className="bg-white px-4 py-6 md:px-7">
                                <div className="mx-auto max-w-5xl">
                                    <div className="flex flex-col gap-3 border-b border-slate-200 pb-5 sm:flex-row sm:items-center sm:justify-between">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Saisie technique</p>
                                            <h2 className="mt-1 text-xl font-black text-slate-950">{selectedOpeningId ? `Ouvrage ${selectedOpening?.sequence}` : 'Nouvel ouvrage'}</h2>
                                        </div>
                                        {selectedOpeningId && !missionLocked && (
                                            <div className="flex gap-2">
                                                <button onClick={duplicateOpening} title="Dupliquer" className="rounded-lg border border-slate-200 p-2.5 text-slate-600 hover:bg-slate-50"><Copy className="h-4 w-4" /></button>
                                                <button onClick={deleteOpening} title="Supprimer" className="rounded-lg border border-red-200 p-2.5 text-red-600 hover:bg-red-50"><Trash2 className="h-4 w-4" /></button>
                                            </div>
                                        )}
                                    </div>

                                    {(selectedOpeningId || !missionLocked) ? (
                                        <div className="py-6">
                                            <div className="grid gap-4 md:grid-cols-6">
                                                <Field label="Repère / libellé" className="md:col-span-3"><input disabled={missionLocked} value={openingForm.label} onChange={event => setOpeningForm(current => ({ ...current, label: event.target.value }))} className={inputClass} placeholder="Ex. F01 - fenêtre séjour" /></Field>
                                                <Field label="Pièce" className="md:col-span-3"><input disabled={missionLocked} value={openingForm.room} onChange={event => setOpeningForm(current => ({ ...current, room: event.target.value }))} className={inputClass} placeholder="Séjour, chambre 1..." /></Field>
                                                <Field label="Type" className="md:col-span-2"><select disabled={missionLocked} value={openingForm.product_type} onChange={event => setOpeningForm(current => ({ ...current, product_type: event.target.value }))} className={inputClass}><option value="WINDOW">Fenêtre</option><option value="DOOR">Porte</option><option value="SLIDING">Coulissant</option><option value="CURTAIN_WALL">Façade / verrière</option><option value="OTHER">Autre</option></select></Field>
                                                <Field label="Matière" className="md:col-span-2"><select disabled={missionLocked} value={openingForm.material} onChange={event => setOpeningForm(current => ({ ...current, material: event.target.value }))} className={inputClass}><option>ALU</option><option>PVC</option><option>ACIER</option><option>BOIS</option></select></Field>
                                                <Field label="Type d'ouverture" className="md:col-span-2"><input disabled={missionLocked} value={openingForm.opening_type} onChange={event => setOpeningForm(current => ({ ...current, opening_type: event.target.value }))} className={inputClass} placeholder="Battant, coulissant..." /></Field>
                                            </div>

                                            <div className="my-6 border-t border-slate-200 pt-6">
                                                <div className="mb-4 flex items-center gap-2"><Ruler className="h-5 w-5 text-blue-600" /><h3 className="font-black text-slate-900">Dimensions de référence</h3></div>
                                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                                                    <Field label="Largeur tableau (mm)"><input type="number" min="0" disabled={missionLocked} value={openingForm.width_mm} onChange={event => setOpeningForm(current => ({ ...current, width_mm: event.target.value }))} className={inputClass} /></Field>
                                                    <Field label="Hauteur tableau (mm)"><input type="number" min="0" disabled={missionLocked} value={openingForm.height_mm} onChange={event => setOpeningForm(current => ({ ...current, height_mm: event.target.value }))} className={inputClass} /></Field>
                                                    <Field label="Passage utile (mm)"><input type="number" min="0" disabled={missionLocked} value={openingForm.passage_height_mm} onChange={event => setOpeningForm(current => ({ ...current, passage_height_mm: event.target.value }))} className={inputClass} /></Field>
                                                    <Field label="Nombre de vantaux"><input type="number" min="1" disabled={missionLocked} value={openingForm.sash_count} onChange={event => setOpeningForm(current => ({ ...current, sash_count: event.target.value }))} className={inputClass} /></Field>
                                                </div>
                                            </div>

                                            <div className="grid gap-4 border-t border-slate-200 pt-6 md:grid-cols-3">
                                                <Field label="Sens d'ouverture"><input disabled={missionLocked} value={openingForm.opening_side} onChange={event => setOpeningForm(current => ({ ...current, opening_side: event.target.value }))} className={inputClass} /></Field>
                                                <Field label="Type de pose"><input disabled={missionLocked} value={openingForm.installation_type} onChange={event => setOpeningForm(current => ({ ...current, installation_type: event.target.value }))} className={inputClass} placeholder="Neuf, rénovation..." /></Field>
                                                <Field label="Observations"><input disabled={missionLocked} value={openingForm.notes} onChange={event => setOpeningForm(current => ({ ...current, notes: event.target.value }))} className={inputClass} placeholder="Jeux, aplomb, accès..." /></Field>
                                            </div>

                                            {!missionLocked && (
                                                <div className="mt-7 flex flex-col-reverse gap-2 border-t border-slate-200 pt-5 sm:flex-row sm:justify-end">
                                                    <button onClick={() => saveOpening(false)} disabled={saving || !openingForm.label} className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-black text-slate-700 disabled:opacity-40"><Save className="h-4 w-4" /> Enregistrer brouillon</button>
                                                    <button onClick={() => saveOpening(true)} disabled={saving || !openingForm.label || !openingForm.width_mm || !openingForm.height_mm} className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-black text-white disabled:opacity-40"><CheckCircle2 className="h-4 w-4" /> Terminer l'ouvrage</button>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="flex min-h-80 flex-col items-center justify-center text-center">
                                            <DoorOpen className="h-12 w-12 text-slate-300" />
                                            <p className="mt-4 font-black text-slate-600">Sélectionnez un ouvrage.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </section>
                    </>
                )}
            </main>
        </div>
    );
}
