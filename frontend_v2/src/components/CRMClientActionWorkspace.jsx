import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    AlertCircle,
    ArrowRight,
    Briefcase,
    CalendarClock,
    CheckCircle2,
    ClipboardList,
    FileText,
    History,
    Loader2,
    Mail,
    MapPin,
    MessageSquareText,
    Phone,
    PhoneCall,
    Plus,
    RefreshCw,
    Star,
    Tags,
    Target,
    Trash2,
    UserPlus,
    X,
} from 'lucide-react';
import api from '../services/api';

const OPEN_ACTIVITY_STATUSES = new Set(['A_FAIRE', 'TODO', 'TO_DO', 'PLANNED', 'OPEN', 'PENDING']);
const CLOSED_OPPORTUNITY_STATUSES = new Set(['GAGNE', 'PERDU', 'WON', 'LOST', 'CANCELLED', 'CLOSED']);

const asList = (payload) => {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.items)) return payload.items;
    if (Array.isArray(payload?.results)) return payload.results;
    return [];
};

const toOpportunity = (item) => ({
    ...item,
    title: item.title || item.name || item.label || item.reference || 'Opportunité sans titre',
    stage: item.stage || item.status || 'QUALIFICATION',
    probability: Number(item.probability ?? item.probability_pct ?? 0),
    amount: Number(item.amount ?? item.estimated_amount ?? item.value ?? 0),
    nextMilestone: item.next_milestone || item.next_action || item.next_step || 'Prochain jalon à définir',
    nextDate: item.next_milestone_at || item.next_action_at || item.next_action_date || item.expected_close_date,
});

const toActivity = (item) => ({
    ...item,
    activityType: item.activity_type || item.type || 'FOLLOW_UP',
    subject: item.subject || item.title || item.label || 'Activité CRM',
    status: item.status || (item.completed_at ? 'termine' : 'a_faire'),
    dueAt: item.due_at || item.scheduled_at || item.next_action_at,
    completedAt: item.completed_at || item.done_at,
    notes: item.note || item.notes || item.description || '',
});

const isOpenActivity = (activity) => OPEN_ACTIVITY_STATUSES.has(String(activity.status || '').toUpperCase());
const isConvertedOpportunity = (opportunity) => (
    Boolean(opportunity.won_at || opportunity.converted_at || opportunity.converted || opportunity.is_converted || opportunity.sale_order_id || opportunity.sale_id || opportunity.order_id)
    || ['GAGNE', 'WON'].includes(String(opportunity.stage || '').toUpperCase())
);
const isOpenOpportunity = (opportunity) => (
    !isConvertedOpportunity(opportunity)
    && !CLOSED_OPPORTUNITY_STATUSES.has(String(opportunity.stage || '').toUpperCase())
);

const CONTACT_PRIORITY_OPTIONS = [
    [1, 'Priorité 1 · décision rapide'],
    [2, 'Priorité 2 · important'],
    [3, 'Priorité 3 · standard'],
    [4, 'Priorité 4 · secondaire'],
    [5, 'Priorité 5 · information'],
];

const CONTACT_INFLUENCE_OPTIONS = [
    ['', 'Influence à qualifier'],
    ['DECISION_MAKER', 'Décisionnaire'],
    ['PRESCRIBER', 'Prescripteur'],
    ['BUYER', 'Acheteur'],
    ['SITE_CONTACT', 'Contact chantier'],
    ['TECHNICAL_CONTACT', 'Contact technique'],
    ['ACCOUNTING', 'Comptabilité'],
    ['OTHER', 'Autre'],
];

const CONTACT_CHANNEL_OPTIONS = [
    ['', 'Canal préféré'],
    ['EMAIL', 'Email'],
    ['PHONE', 'Téléphone'],
    ['SMS', 'SMS'],
    ['WHATSAPP', 'WhatsApp'],
    ['IN_PERSON', 'Rendez-vous'],
];

const influenceLabel = value => CONTACT_INFLUENCE_OPTIONS.find(([code]) => code === value)?.[1] || value;
const channelLabel = value => CONTACT_CHANNEL_OPTIONS.find(([code]) => code === value)?.[1] || value;

export default function CRMClientActionWorkspace({
    client,
    sites,
    presalesQuotes,
    executionOrders,
    dossiers,
    totals,
    timeline,
    formatDate,
    formatMoney,
    statusLabel,
    statusClassName,
    onCreateProposal,
    onPlanMeasure,
    onCreateSite,
    onPlanMeasureForSite,
    onPlanMeasureForOpportunity,
    onOpenSale,
    onOpenMeasures,
    onClientChanged,
}) {
    const [actionMode, setActionMode] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [showContactForm, setShowContactForm] = useState(false);
    const [showSegmentationForm, setShowSegmentationForm] = useState(false);
    const [segmentationDraft, setSegmentationDraft] = useState({
        segment: '',
        tags: '',
    });
    const [contactDraft, setContactDraft] = useState({
        name: '',
        role: '',
        priority: 3,
        influence_role: '',
        preferred_channel: '',
        email_consent: false,
        email: '',
        phone: '',
        is_primary: false,
        notes: '',
    });
    const [opportunityDraft, setOpportunityDraft] = useState({
        title: '',
        stage: 'nouveau',
        probability: 20,
        amount: '',
        site_address_id: '',
        next_milestone: '',
        next_milestone_at: '',
    });
    const [activityDraft, setActivityDraft] = useState({
        subject: '',
        due_at: '',
        notes: '',
        opportunity_id: '',
    });

    const opportunitiesQuery = useQuery({
        queryKey: ['crm-opportunities', client.id],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/opportunities', { params: { client_id: client.id } });
            return asList(response.data).map(toOpportunity);
        },
    });

    const activitiesQuery = useQuery({
        queryKey: ['crm-activities', client.id],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/activities', { params: { client_id: client.id } });
            return asList(response.data).map(toActivity);
        },
    });

    const contactsQuery = useQuery({
        queryKey: ['crm-client-contacts', client.id],
        queryFn: async () => {
            const response = await api.get(`/v2/partners/clients/${client.id}/contacts`);
            return asList(response.data);
        },
    });

    const contactDuplicatesQuery = useQuery({
        queryKey: ['crm-client-contacts', client.id, 'duplicates'],
        queryFn: async () => {
            const response = await api.get(`/v2/partners/clients/${client.id}/contacts/duplicates`);
            return asList(response.data);
        },
    });

    const opportunities = opportunitiesQuery.data || [];
    const activities = activitiesQuery.data || [];
    const contacts = contactsQuery.data || [];
    const contactDuplicateGroups = contactDuplicatesQuery.data || [];
    const openOpportunities = useMemo(
        () => opportunities.filter(isOpenOpportunity).sort((a, b) => new Date(a.nextDate || '2999-12-31') - new Date(b.nextDate || '2999-12-31')),
        [opportunities],
    );
    const convertedOpportunities = useMemo(
        () => opportunities.filter(isConvertedOpportunity).sort((a, b) => new Date(b.converted_at || b.updated_at || 0) - new Date(a.converted_at || a.updated_at || 0)),
        [opportunities],
    );
    const pendingActivities = useMemo(
        () => activities.filter(isOpenActivity).sort((a, b) => new Date(a.dueAt || '2999-12-31') - new Date(b.dueAt || '2999-12-31')),
        [activities],
    );
    const activityHistory = useMemo(
        () => activities.filter(activity => !isOpenActivity(activity)).sort((a, b) => new Date(b.completedAt || b.updated_at || b.created_at || 0) - new Date(a.completedAt || a.updated_at || a.created_at || 0)),
        [activities],
    );

    const nextAction = pendingActivities[0]
        ? {
            eyebrow: 'Activité prioritaire',
            title: pendingActivities[0].subject,
            detail: pendingActivities[0].dueAt ? `Échéance ${formatDate(pendingActivities[0].dueAt)}` : 'Échéance à définir',
            tone: isOverdue(pendingActivities[0].dueAt) ? 'red' : 'blue',
        }
        : openOpportunities[0]
            ? {
                eyebrow: 'Prochain jalon commercial',
                title: openOpportunities[0].nextMilestone,
                detail: `${openOpportunities[0].title}${openOpportunities[0].nextDate ? ` · ${formatDate(openOpportunities[0].nextDate)}` : ''}`,
                tone: 'amber',
            }
            : {
                eyebrow: 'Prochaine action',
                title: 'Qualifier une nouvelle opportunité',
                detail: 'Aucune activité ni opportunité ouverte pour ce client.',
                tone: 'slate',
            };

    const resetAndOpen = (mode) => {
        setSubmitError('');
        setActionMode(mode);
        if (mode === 'opportunity') {
            setOpportunityDraft({
                title: '',
                stage: 'nouveau',
                probability: 20,
                amount: '',
                site_address_id: '',
                next_milestone: '',
                next_milestone_at: '',
            });
        } else {
            setActivityDraft({
                subject: mode === 'call' ? `Appel avec ${client.name}` : `Relancer ${client.name}`,
                due_at: mode === 'call' ? '' : toLocalDateTimeInput(new Date(Date.now() + 24 * 60 * 60 * 1000)),
                notes: '',
                opportunity_id: openOpportunities[0]?.id ? String(openOpportunities[0].id) : '',
            });
        }
    };

    const submitAction = async () => {
        setSubmitError('');
        setIsSubmitting(true);
        try {
            if (actionMode === 'opportunity') {
                if (!opportunityDraft.title.trim()) throw new Error("Donnez un nom à l'opportunité.");
                await api.post('/v2/mmg/opportunities', {
                    client_id: client.id,
                    site_address_id: opportunityDraft.site_address_id ? Number(opportunityDraft.site_address_id) : null,
                    title: opportunityDraft.title.trim(),
                    stage: 'nouveau',
                    probability: 10,
                    estimated_amount: Number(opportunityDraft.amount || 0),
                    need_type: 'autre',
                    next_milestone: opportunityDraft.next_milestone.trim() || null,
                    next_milestone_at: opportunityDraft.next_milestone_at
                        ? new Date(opportunityDraft.next_milestone_at).toISOString()
                        : null,
                });
                await opportunitiesQuery.refetch();
            } else {
                if (!activityDraft.subject.trim()) throw new Error("Renseignez l'objet de l'activité.");
                const isCall = actionMode === 'call';
                await api.post('/v2/mmg/activities', {
                    client_id: client.id,
                    opportunity_id: activityDraft.opportunity_id ? Number(activityDraft.opportunity_id) : null,
                    activity_type: isCall ? 'appel' : 'tache',
                    subject: activityDraft.subject.trim(),
                    note: activityDraft.notes.trim() || null,
                    due_at: isCall ? null : activityDraft.due_at || null,
                    status: isCall ? 'termine' : 'a_faire',
                });
                await activitiesQuery.refetch();
            }
            setActionMode(null);
        } catch (requestError) {
            setSubmitError(
                requestError?.response?.data?.detail
                || requestError.message
                || "L'action CRM n'a pas pu être enregistrée.",
            );
        } finally {
            setIsSubmitting(false);
        }
    };

    const completeActivity = async (activity) => {
        if (!activity?.id) return;
        setSubmitError('');
        try {
            await api.patch(`/v2/mmg/activities/${activity.id}`, { status: 'termine' });
            await activitiesQuery.refetch();
        } catch (requestError) {
            setSubmitError(
                requestError?.response?.data?.detail
                || "L'activité n'a pas pu être clôturée.",
            );
        }
    };

    const createContact = async (event) => {
        event.preventDefault();
        if (!contactDraft.name.trim()) return;
        setSubmitError('');
        setIsSubmitting(true);
        try {
            await api.post(`/v2/partners/clients/${client.id}/contacts`, {
                name: contactDraft.name.trim(),
                role: contactDraft.role.trim() || null,
                priority: Number(contactDraft.priority || 3),
                influence_role: contactDraft.influence_role || null,
                preferred_channel: contactDraft.preferred_channel || null,
                email_consent: contactDraft.email_consent,
                email_consent_at: contactDraft.email_consent ? new Date().toISOString() : null,
                email: contactDraft.email.trim() || null,
                phone: contactDraft.phone.trim() || null,
                is_primary: contactDraft.is_primary,
                notes: contactDraft.notes.trim() || null,
            });
            await Promise.all([contactsQuery.refetch(), contactDuplicatesQuery.refetch(), onClientChanged?.()]);
            setContactDraft({
                name: '',
                role: '',
                priority: 3,
                influence_role: '',
                preferred_channel: '',
                email_consent: false,
                email: '',
                phone: '',
                is_primary: false,
                notes: '',
            });
            setShowContactForm(false);
        } catch (error) {
            setSubmitError(readableError(error));
        } finally {
            setIsSubmitting(false);
        }
    };

    const setPrimaryContact = async (contact) => {
        setSubmitError('');
        try {
            await api.patch(
                `/v2/partners/clients/${client.id}/contacts/${contact.id}`,
                { is_primary: true },
            );
            await Promise.all([contactsQuery.refetch(), contactDuplicatesQuery.refetch(), onClientChanged?.()]);
        } catch (error) {
            setSubmitError(readableError(error));
        }
    };

    const deleteContact = async (contact) => {
        if (!window.confirm(`Supprimer le contact « ${contact.name} » ?`)) return;
        setSubmitError('');
        try {
            await api.delete(`/v2/partners/clients/${client.id}/contacts/${contact.id}`);
            await Promise.all([contactsQuery.refetch(), contactDuplicatesQuery.refetch(), onClientChanged?.()]);
        } catch (error) {
            setSubmitError(readableError(error));
        }
    };

    const openSegmentationForm = () => {
        setSegmentationDraft({
            segment: client.segment || '',
            tags: (client.tags || []).join(', '),
        });
        setShowSegmentationForm(true);
    };

    const saveSegmentation = async (event) => {
        event.preventDefault();
        setSubmitError('');
        setIsSubmitting(true);
        try {
            await api.put(`/v2/partners/clients/${client.id}`, {
                name: client.name,
                contact_name: client.contact_name || null,
                email: client.email || null,
                phone: client.phone || null,
                address: client.address || null,
                country: client.country || 'FR',
                tax_id: client.tax_id || null,
                customer_type: client.customer_type || 'B2B',
                segment: segmentationDraft.segment.trim() || null,
                tags: segmentationDraft.tags
                    .split(',')
                    .map(tag => tag.trim())
                    .filter(Boolean),
                is_active: client.is_active !== false,
            });
            await onClientChanged?.();
            setShowSegmentationForm(false);
        } catch (error) {
            setSubmitError(readableError(error));
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="mx-auto w-full max-w-[1680px] space-y-5">
            <header className="border-l-4 border-blue-500 bg-blue-50/70 px-5 py-5">
                <div className="flex flex-col gap-4 2xl:flex-row 2xl:items-start 2xl:justify-between">
                    <div className="min-w-0">
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Fiche client CRM</p>
                        <h3 className="mt-1 truncate text-2xl font-black tracking-tight text-slate-950 lg:text-3xl">{client.name}</h3>
                        <p className="mt-1 text-sm font-bold text-slate-500">{client.contact_name || 'Contact principal à renseigner'}</p>
                        {(client.segment || client.tags?.length) && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                                {client.segment && <span className="rounded-full bg-blue-100 px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-blue-800">{client.segment}</span>}
                                {(client.tags || []).map(tag => <span key={tag} className="rounded-full bg-white px-2.5 py-1 text-[9px] font-black uppercase tracking-widest text-slate-600">{tag}</span>)}
                            </div>
                        )}
                        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-bold text-slate-600">
                            {client.phone && <a href={`tel:${client.phone}`} className="inline-flex items-center gap-2 hover:text-blue-700"><Phone className="h-4 w-4" />{client.phone}</a>}
                            {client.email && <a href={`mailto:${client.email}`} className="inline-flex items-center gap-2 hover:text-blue-700"><Mail className="h-4 w-4" />{client.email}</a>}
                            <span className="inline-flex min-w-0 items-center gap-2"><MapPin className="h-4 w-4 shrink-0" /><span className="truncate">{client.address || 'Adresse de facturation à compléter'}</span></span>
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
                        <ActionButton icon={Target} label="Nouvelle opportunité" onClick={() => resetAndOpen('opportunity')} primary />
                        <ActionButton icon={CalendarClock} label="Planifier une relance" onClick={() => resetAndOpen('follow-up')} />
                        <ActionButton icon={PhoneCall} label="Noter un appel" onClick={() => resetAndOpen('call')} />
                        <ActionButton icon={Tags} label="Segmenter" onClick={openSegmentationForm} />
                        <ActionButton icon={ClipboardList} label="Planifier un métré" onClick={onPlanMeasure} accent />
                    </div>
                </div>
            </header>

            {submitError && !actionMode && (
                <div className="flex items-start gap-3 border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{submitError}</span>
                </div>
            )}

            <section className={`grid gap-4 border-l-4 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center ${nextActionTone(nextAction.tone)}`}>
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{nextAction.eyebrow}</p>
                    <p className="mt-1 text-lg font-black">{nextAction.title}</p>
                    <p className="mt-1 text-sm font-semibold opacity-80">{nextAction.detail}</p>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                    <MiniMetric label="Opportunités" value={openOpportunities.length} />
                    <MiniMetric label="À faire" value={pendingActivities.length} />
                    <MiniMetric label="CA signé" value={formatMoney(totals.orderAmount)} />
                </div>
            </section>

            <section className="border-y border-l-4 border-slate-200 border-l-blue-500 bg-white">
                <SectionHeading
                    eyebrow="Interlocuteurs"
                    title={`Contacts du compte (${contacts.length})`}
                    detail="Un contact principal alimente les devis et relances ; les autres interlocuteurs restent disponibles sur la fiche."
                    tone="cyan"
                    action={(
                        <button
                            onClick={() => setShowContactForm(current => !current)}
                            className="inline-flex items-center gap-2 text-xs font-black text-blue-700 hover:text-blue-900"
                        >
                            <UserPlus className="h-4 w-4" />
                            Ajouter un contact
                        </button>
                    )}
                />
                {!!contactDuplicateGroups.length && (
                    <div className="border-b border-amber-200 bg-amber-50 px-4 py-3">
                        <div className="flex items-start gap-3">
                            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                            <div className="min-w-0">
                                <p className="text-xs font-black uppercase tracking-widest text-amber-800">
                                    Doublons contacts suspectés
                                </p>
                                <p className="mt-1 text-xs font-semibold text-amber-900">
                                    Vérifiez avant relance : un même décideur ou téléphone peut apparaître plusieurs fois sur cette fiche.
                                </p>
                                <div className="mt-2 grid gap-2">
                                    {contactDuplicateGroups.map((group, index) => (
                                        <div key={`${group.score}-${index}`} className="rounded-lg border border-amber-200 bg-white/70 px-3 py-2">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-amber-700">
                                                Score {group.score}% · {(group.reasons || []).join(' · ')}
                                            </p>
                                            <p className="mt-1 text-xs font-bold text-slate-700">
                                                {(group.contacts || []).map(contact => `${contact.name}${contact.email ? ` <${contact.email}>` : ''}`).join(' ↔ ')}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
                {showContactForm && (
                    <form onSubmit={createContact} className="grid gap-3 border-b border-slate-200 bg-blue-50/40 p-4 md:grid-cols-2 xl:grid-cols-4">
                        <input
                            required
                            value={contactDraft.name}
                            onChange={event => setContactDraft(current => ({ ...current, name: event.target.value }))}
                            placeholder="Nom du contact"
                            className={inputClass}
                        />
                        <input
                            value={contactDraft.role}
                            onChange={event => setContactDraft(current => ({ ...current, role: event.target.value }))}
                            placeholder="Fonction / rôle"
                            className={inputClass}
                        />
                        <select
                            value={contactDraft.priority}
                            onChange={event => setContactDraft(current => ({ ...current, priority: Number(event.target.value) }))}
                            className={inputClass}
                        >
                            {CONTACT_PRIORITY_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                        <select
                            value={contactDraft.influence_role}
                            onChange={event => setContactDraft(current => ({ ...current, influence_role: event.target.value }))}
                            className={inputClass}
                        >
                            {CONTACT_INFLUENCE_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                        <input
                            type="email"
                            value={contactDraft.email}
                            onChange={event => setContactDraft(current => ({ ...current, email: event.target.value }))}
                            placeholder="Email"
                            className={inputClass}
                        />
                        <input
                            value={contactDraft.phone}
                            onChange={event => setContactDraft(current => ({ ...current, phone: event.target.value }))}
                            placeholder="Téléphone"
                            className={inputClass}
                        />
                        <select
                            value={contactDraft.preferred_channel}
                            onChange={event => setContactDraft(current => ({ ...current, preferred_channel: event.target.value }))}
                            className={inputClass}
                        >
                            {CONTACT_CHANNEL_OPTIONS.map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                        <label className="inline-flex items-center gap-2 text-xs font-black text-slate-700">
                            <input
                                type="checkbox"
                                checked={contactDraft.is_primary}
                                onChange={event => setContactDraft(current => ({ ...current, is_primary: event.target.checked }))}
                            />
                            Contact principal
                        </label>
                        <label className="inline-flex items-center gap-2 text-xs font-black text-slate-700">
                            <input
                                type="checkbox"
                                checked={contactDraft.email_consent}
                                onChange={event => setContactDraft(current => ({ ...current, email_consent: event.target.checked }))}
                            />
                            Consentement email
                        </label>
                        <input
                            value={contactDraft.notes}
                            onChange={event => setContactDraft(current => ({ ...current, notes: event.target.value }))}
                            placeholder="Notes"
                            className={`${inputClass} md:col-span-1 xl:col-span-2`}
                        />
                        <div className="flex justify-end gap-2">
                            <button type="button" onClick={() => setShowContactForm(false)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-600">Annuler</button>
                            <button type="submit" disabled={isSubmitting} className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-black text-white disabled:bg-slate-300">Enregistrer</button>
                        </div>
                    </form>
                )}
                <AsyncBlock
                    loading={contactsQuery.isLoading}
                    error={contactsQuery.error}
                    onRetry={() => contactsQuery.refetch()}
                    empty={!contacts.length}
                    emptyIcon={UserPlus}
                    emptyTitle="Aucun contact enregistré"
                    emptyDetail="Ajoutez les décideurs, prescripteurs et interlocuteurs chantier."
                >
                    <div className="grid gap-px bg-slate-100 md:grid-cols-2 xl:grid-cols-3">
                        {contacts.map(contact => (
                            <div key={contact.id} className="bg-white p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="flex items-center gap-2">
                                            <p className="truncate text-sm font-black text-slate-900">{contact.name}</p>
                                            {contact.is_primary && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest text-amber-800">Principal</span>}
                                        </div>
                                        <p className="mt-1 truncate text-xs font-semibold text-slate-500">{contact.role || 'Interlocuteur'}</p>
                                        <div className="mt-2 flex flex-wrap gap-1.5">
                                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest text-slate-600">P{contact.priority || 3}</span>
                                            {contact.influence_role && <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest text-blue-700">{influenceLabel(contact.influence_role)}</span>}
                                            {contact.preferred_channel && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest text-emerald-700">{channelLabel(contact.preferred_channel)}</span>}
                                            {contact.email_consent && <span className="rounded-full bg-purple-50 px-2 py-0.5 text-[8px] font-black uppercase tracking-widest text-purple-700">Email OK</span>}
                                        </div>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-1">
                                        {!contact.is_primary && (
                                            <button type="button" onClick={() => setPrimaryContact(contact)} title="Définir comme principal" className="rounded-md p-1.5 text-slate-400 hover:bg-amber-50 hover:text-amber-700"><Star className="h-4 w-4" /></button>
                                        )}
                                        <button type="button" onClick={() => deleteContact(contact)} title="Supprimer" className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-700"><Trash2 className="h-4 w-4" /></button>
                                    </div>
                                </div>
                                <div className="mt-3 space-y-1 text-xs font-semibold text-slate-600">
                                    {contact.email && <a href={`mailto:${contact.email}`} className="flex items-center gap-2 hover:text-blue-700"><Mail className="h-3.5 w-3.5" />{contact.email}</a>}
                                    {contact.phone && <a href={`tel:${contact.phone}`} className="flex items-center gap-2 hover:text-blue-700"><Phone className="h-3.5 w-3.5" />{contact.phone}</a>}
                                </div>
                            </div>
                        ))}
                    </div>
                </AsyncBlock>
            </section>

            <section className="border-y border-l-4 border-slate-200 border-l-indigo-500 bg-white">
                <SectionHeading
                    eyebrow="Pipeline client"
                    title="Opportunités ouvertes"
                    detail="Étape, probabilité, montant et prochain jalon commercial."
                    tone="indigo"
                    action={<button onClick={() => resetAndOpen('opportunity')} className="inline-flex items-center gap-2 text-xs font-black text-blue-700 hover:text-blue-900"><Plus className="h-4 w-4" />Nouvelle opportunité</button>}
                />
                <AsyncBlock
                    loading={opportunitiesQuery.isLoading}
                    error={opportunitiesQuery.error}
                    onRetry={() => opportunitiesQuery.refetch()}
                    empty={!openOpportunities.length && !convertedOpportunities.length}
                    emptyIcon={Target}
                    emptyTitle="Aucune opportunité ouverte"
                    emptyDetail="Créez une opportunité pour formaliser le besoin, le montant attendu et la prochaine décision."
                >
                    <div className="divide-y divide-slate-100">
                        {openOpportunities.map(opportunity => (
                            <OpportunityRow
                                key={opportunity.id || opportunity.title}
                                opportunity={opportunity}
                                formatDate={formatDate}
                                formatMoney={formatMoney}
                                onPlanMeasure={() => onPlanMeasureForOpportunity(opportunity)}
                            />
                        ))}
                        {convertedOpportunities.length > 0 && (
                            <div className="bg-emerald-50/60 px-5 py-2 text-[9px] font-black uppercase tracking-widest text-emerald-700">
                                Converties en commande
                            </div>
                        )}
                        {convertedOpportunities.map(opportunity => (
                            <OpportunityRow
                                key={opportunity.id || opportunity.title}
                                opportunity={opportunity}
                                formatDate={formatDate}
                                formatMoney={formatMoney}
                                converted
                            />
                        ))}
                    </div>
                </AsyncBlock>
            </section>

            <div className="grid gap-5 2xl:grid-cols-2">
                <section className="border-y border-l-4 border-slate-200 border-l-cyan-500 bg-white">
                    <SectionHeading
                        eyebrow="Agenda commercial"
                        title="Activités à faire"
                        detail="Relances, appels et jalons qui demandent une action."
                        tone="cyan"
                        action={<button onClick={() => resetAndOpen('follow-up')} className="inline-flex items-center gap-2 text-xs font-black text-blue-700 hover:text-blue-900"><Plus className="h-4 w-4" />Planifier</button>}
                    />
                    <AsyncBlock
                        loading={activitiesQuery.isLoading}
                        error={activitiesQuery.error}
                        onRetry={() => activitiesQuery.refetch()}
                        empty={!pendingActivities.length}
                        emptyIcon={CheckCircle2}
                        emptyTitle="Aucune activité en attente"
                        emptyDetail="Le client n'a pas de relance ou d'action planifiée."
                    >
                        <div className="divide-y divide-slate-100">
                            {pendingActivities.slice(0, 8).map(activity => (
                                <ActivityRow
                                    key={activity.id || `${activity.subject}-${activity.dueAt}`}
                                    activity={activity}
                                    formatDate={formatDate}
                                    onComplete={() => completeActivity(activity)}
                                />
                            ))}
                        </div>
                    </AsyncBlock>
                </section>

                <section className="border-y border-l-4 border-slate-200 border-l-slate-400 bg-white">
                    <SectionHeading eyebrow="Mémoire CRM" title="Historique des activités" detail="Appels, notes et actions commerciales terminées." tone="slate" />
                    <AsyncBlock
                        loading={activitiesQuery.isLoading}
                        error={activitiesQuery.error}
                        onRetry={() => activitiesQuery.refetch()}
                        empty={!activityHistory.length}
                        emptyIcon={History}
                        emptyTitle="Aucune activité historisée"
                        emptyDetail="Les appels notés et les relances terminées apparaîtront ici."
                    >
                        <div className="divide-y divide-slate-100">
                            {activityHistory.slice(0, 8).map(activity => (
                                <ActivityRow key={activity.id || `${activity.subject}-${activity.completedAt}`} activity={activity} formatDate={formatDate} history />
                            ))}
                        </div>
                    </AsyncBlock>
                </section>
            </div>

            <section className="border-y border-l-4 border-slate-200 border-l-emerald-500 bg-white">
                <SectionHeading
                    eyebrow="Contexte opérationnel"
                    title="Chantiers, métrés et propositions"
                    detail="Les éléments existants restent accessibles sans quitter la fiche client."
                    tone="emerald"
                    action={<button onClick={onCreateSite} className="inline-flex items-center gap-2 text-xs font-black text-slate-700 hover:text-slate-950"><Plus className="h-4 w-4" />Nouveau chantier</button>}
                />
                <div className="grid divide-y divide-slate-200 xl:grid-cols-3 xl:divide-x xl:divide-y-0">
                    <ContextColumn
                        icon={MapPin}
                        title={`Chantiers (${sites.length})`}
                        empty="Aucun chantier enregistré."
                    >
                        {sites.slice(0, 5).map(site => (
                            <div key={site.id} className="flex items-start justify-between gap-3 border-b border-slate-100 py-3 last:border-0">
                                <div className="min-w-0">
                                    <p className="truncate text-sm font-black text-slate-900">{site.reference} · {site.label}</p>
                                    <p className="mt-1 line-clamp-2 text-xs font-semibold text-slate-500">{formatSiteAddress(site)}</p>
                                </div>
                                <button onClick={() => onPlanMeasureForSite(site)} title="Planifier un métré" className="shrink-0 rounded-lg border border-emerald-200 p-2 text-emerald-700 hover:bg-emerald-50"><ClipboardList className="h-4 w-4" /></button>
                            </div>
                        ))}
                    </ContextColumn>
                    <ContextColumn
                        icon={ClipboardList}
                        title={`Métrés (${dossiers.length})`}
                        empty="Aucun métré pour ce client."
                    >
                        {dossiers.slice(0, 5).map(dossier => (
                            <button key={dossier.id} onClick={() => dossier.measure_mission_id ? onOpenMeasures(dossier) : onOpenMeasures()} className="flex w-full items-center justify-between gap-3 border-b border-slate-100 py-3 text-left last:border-0 hover:text-emerald-700">
                                <span className="min-w-0">
                                    <span className="block truncate text-sm font-black">{dossier.reference}</span>
                                    <span className="mt-1 block text-xs font-semibold text-slate-500">{dossier.status === 'VALIDATED' ? 'Métré réalisé' : 'À traiter'} · {formatDate(dossier.created_at)}</span>
                                </span>
                                <ArrowRight className="h-4 w-4 shrink-0" />
                            </button>
                        ))}
                    </ContextColumn>
                    <ContextColumn
                        icon={FileText}
                        title={`Propositions (${presalesQuotes.length})`}
                        empty="Aucune proposition commerciale."
                    >
                        {presalesQuotes.slice(0, 5).map(sale => (
                            <button key={sale.id} onClick={() => onOpenSale(sale.id)} className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-100 py-3 text-left last:border-0 hover:text-blue-700">
                                <span className="min-w-0">
                                    <span className="block truncate text-sm font-black">{sale.reference}</span>
                                    <span className="mt-1 block text-xs font-semibold text-slate-500">{statusLabel(sale)} · {formatDate(sale.created_at)}</span>
                                </span>
                                <span className="text-sm font-black">{formatMoney(saleAmount(sale))}</span>
                            </button>
                        ))}
                    </ContextColumn>
                </div>
            </section>

            <section className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_360px]">
                <div className="border-y border-l-4 border-slate-200 border-l-amber-500 bg-white">
                    <SectionHeading eyebrow="Après signature" title={`Commandes & exécution (${executionOrders.length})`} detail="Consultation uniquement : l'exécution reste dans le module Commandes signées." tone="amber" />
                    {executionOrders.length ? (
                        <div className="divide-y divide-slate-100">
                            {executionOrders.slice(0, 6).map(sale => (
                                <button key={sale.id} onClick={() => onOpenSale(sale.id)} className="grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 px-5 py-4 text-left hover:bg-slate-50">
                                    <span className="min-w-0">
                                        <span className="block truncate text-sm font-black text-slate-900">{sale.reference}</span>
                                        <span className="mt-1 block text-xs font-semibold text-slate-500">{formatDate(sale.created_at)}</span>
                                    </span>
                                    <span className={`rounded-md border px-2 py-1 text-[9px] font-black uppercase tracking-widest ${statusClassName(sale.status)}`}>{statusLabel(sale)}</span>
                                    <span className="text-sm font-black text-slate-900">{formatMoney(saleAmount(sale))}</span>
                                </button>
                            ))}
                        </div>
                    ) : <InlineEmpty icon={Briefcase} title="Aucune commande signée" detail="Les propositions gagnées apparaîtront ici pour consultation." />}
                </div>
                <div className="border-y border-l-4 border-slate-200 border-l-violet-500 bg-white">
                    <SectionHeading eyebrow="Historique client" title="Derniers événements" tone="violet" />
                    {timeline.length ? (
                        <div className="divide-y divide-slate-100 px-5">
                            {timeline.slice(0, 7).map(event => (
                                <button key={event.key} onClick={() => onOpenSale(event.saleId)} className="grid w-full grid-cols-[10px_minmax(0,1fr)] gap-3 py-3 text-left">
                                    <span className="mt-1.5 h-2.5 w-2.5 rounded-full bg-blue-500" />
                                    <span className="min-w-0">
                                        <span className="block text-xs font-black text-slate-900">{event.label}</span>
                                        <span className="block truncate text-xs font-semibold text-slate-500">{event.detail}</span>
                                        <span className="mt-1 block text-[9px] font-black uppercase tracking-widest text-slate-400">{formatDate(event.date)}</span>
                                    </span>
                                </button>
                            ))}
                        </div>
                    ) : <InlineEmpty icon={History} title="Aucun historique" detail="Les événements client apparaîtront ici." />}
                </div>
            </section>

            {actionMode && (
                <ActionDialog
                    mode={actionMode}
                    client={client}
                    sites={sites}
                    opportunities={openOpportunities}
                    opportunityDraft={opportunityDraft}
                    setOpportunityDraft={setOpportunityDraft}
                    activityDraft={activityDraft}
                    setActivityDraft={setActivityDraft}
                    isSubmitting={isSubmitting}
                    error={submitError}
                    onClose={() => setActionMode(null)}
                    onSubmit={submitAction}
                />
            )}

            {showSegmentationForm && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
                    <form onSubmit={saveSegmentation} className="w-full max-w-lg overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
                        <div className="flex items-start justify-between bg-slate-900 px-6 py-5 text-white">
                            <div>
                                <p className="text-[9px] font-black uppercase tracking-widest text-blue-200">Segmentation CRM</p>
                                <h3 className="mt-2 text-xl font-black">{client.name}</h3>
                            </div>
                            <button type="button" onClick={() => setShowSegmentationForm(false)} className="rounded-full p-2 text-slate-300 hover:bg-white/10"><X className="h-5 w-5" /></button>
                        </div>
                        <div className="space-y-4 p-6">
                            <Field label="Segment">
                                <input value={segmentationDraft.segment} onChange={event => setSegmentationDraft(current => ({ ...current, segment: event.target.value }))} placeholder="Ex. Architectes, Grands comptes, Particuliers" className={inputClass} />
                            </Field>
                            <Field label="Tags">
                                <input value={segmentationDraft.tags} onChange={event => setSegmentationDraft(current => ({ ...current, tags: event.target.value }))} placeholder="Prioritaire, Prescription, Relance Q4" className={inputClass} />
                            </Field>
                        </div>
                        <div className="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                            <button type="button" onClick={() => setShowSegmentationForm(false)} className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-600">Annuler</button>
                            <button type="submit" disabled={isSubmitting} className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-black text-white disabled:bg-slate-300">Enregistrer</button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}

function ActionButton({ icon: Icon, label, onClick, primary, accent }) {
    const tone = primary
        ? 'border-blue-600 bg-blue-600 text-white hover:bg-blue-500'
        : accent
            ? 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500'
            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50';
    return (
        <button onClick={onClick} className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border px-3 text-xs font-black ${tone}`}>
            <Icon className="h-4 w-4" />
            <span>{label}</span>
        </button>
    );
}

function SectionHeading({ eyebrow, title, detail, action, tone = 'slate' }) {
    const tones = {
        slate: 'bg-slate-50 text-slate-950',
        indigo: 'bg-indigo-50 text-indigo-950',
        cyan: 'bg-cyan-50 text-cyan-950',
        emerald: 'bg-emerald-50 text-emerald-950',
        amber: 'bg-amber-50 text-amber-950',
        violet: 'bg-violet-50 text-violet-950',
    };
    const eyebrowTones = {
        slate: 'text-slate-500',
        indigo: 'text-indigo-600',
        cyan: 'text-cyan-700',
        emerald: 'text-emerald-700',
        amber: 'text-amber-700',
        violet: 'text-violet-700',
    };
    return (
        <div className={`flex flex-col gap-3 border-b border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${tones[tone] || tones.slate}`}>
            <div>
                <p className={`text-[9px] font-black uppercase tracking-widest ${eyebrowTones[tone] || eyebrowTones.slate}`}>{eyebrow}</p>
                <h4 className="mt-1 text-base font-black">{title}</h4>
                {detail && <p className="mt-1 text-xs font-semibold text-slate-500">{detail}</p>}
            </div>
            {action}
        </div>
    );
}

function readableError(error) {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail
            .map(item => (typeof item === 'string' ? item : item?.msg))
            .filter(Boolean)
            .join(' · ') || 'Les données reçues ne sont pas valides.';
    }
    if (detail && typeof detail === 'object') {
        return detail.msg || detail.message || 'Les données reçues ne sont pas valides.';
    }
    return error?.message || 'Une erreur est survenue.';
}

function AsyncBlock({ loading, error, onRetry, empty, emptyIcon, emptyTitle, emptyDetail, children }) {
    if (loading) {
        return (
            <div className="flex min-h-28 items-center justify-center gap-2 text-sm font-bold text-slate-500">
                <Loader2 className="h-5 w-5 animate-spin" />
                Chargement des données CRM...
            </div>
        );
    }
    if (error) {
        return (
            <div className="flex min-h-28 flex-col items-center justify-center px-5 py-6 text-center">
                <AlertCircle className="h-6 w-6 text-red-500" />
                <p className="mt-2 text-sm font-black text-red-800">Données CRM indisponibles</p>
                <p className="mt-1 max-w-xl text-xs font-semibold text-slate-500">{readableError(error)}</p>
                <button onClick={onRetry} className="mt-3 inline-flex items-center gap-2 text-xs font-black text-blue-700"><RefreshCw className="h-4 w-4" />Réessayer</button>
            </div>
        );
    }
    if (empty) return <InlineEmpty icon={emptyIcon} title={emptyTitle} detail={emptyDetail} />;
    return children;
}

function InlineEmpty({ icon: Icon, title, detail }) {
    return (
        <div className="flex min-h-28 flex-col items-center justify-center px-5 py-6 text-center">
            <Icon className="h-7 w-7 text-slate-300" />
            <p className="mt-2 text-sm font-black text-slate-700">{title}</p>
            <p className="mt-1 max-w-xl text-xs font-semibold text-slate-400">{detail}</p>
        </div>
    );
}

function MiniMetric({ label, value }) {
    return (
        <div className="min-w-20 border-l border-current/10 px-3 first:border-l-0">
            <p className="text-[9px] font-black uppercase tracking-widest opacity-60">{label}</p>
            <p className="mt-1 truncate text-sm font-black">{value}</p>
        </div>
    );
}

function OpportunityRow({ opportunity, formatDate, formatMoney, onPlanMeasure, converted }) {
    return (
        <div className="grid gap-3 px-5 py-4 md:grid-cols-[minmax(0,1.4fr)_140px_110px_130px_minmax(160px,1fr)_auto] md:items-center">
            <div className="min-w-0">
                <p className="truncate text-sm font-black text-slate-950">{opportunity.title}</p>
                {opportunity.notes && <p className="mt-1 line-clamp-1 text-xs font-semibold text-slate-500">{opportunity.notes}</p>}
            </div>
            <LabeledValue label="Étape" value={converted ? 'Convertie' : opportunityLabel(opportunity.stage)} />
            <div>
                <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Probabilité</p>
                <div className="mt-1 flex items-center gap-2">
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-blue-600" style={{ width: `${Math.max(0, Math.min(100, opportunity.probability))}%` }} /></div>
                    <span className="text-xs font-black text-slate-700">{opportunity.probability}%</span>
                </div>
            </div>
            <LabeledValue label="Montant" value={formatMoney(opportunity.amount)} />
            <LabeledValue
                label={converted ? 'Conversion' : 'Prochain jalon'}
                value={converted
                    ? `${opportunity.sale_reference || opportunity.order_reference || 'Commande créée'}${(opportunity.won_at || opportunity.converted_at) ? ` · ${formatDate(opportunity.won_at || opportunity.converted_at)}` : ''}`
                    : `${opportunity.nextMilestone}${opportunity.nextDate ? ` · ${formatDate(opportunity.nextDate)}` : ''}`}
            />
            {converted ? (
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-emerald-800">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Convertie
                </span>
            ) : (
                <button
                    onClick={onPlanMeasure}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-black text-emerald-800 hover:bg-emerald-100"
                >
                    <ClipboardList className="h-4 w-4" />
                    Planifier un métré
                </button>
            )}
        </div>
    );
}

function ActivityRow({ activity, formatDate, history, onComplete }) {
    const overdue = !history && isOverdue(activity.dueAt);
    return (
        <div className="grid grid-cols-[36px_minmax(0,1fr)_auto] items-start gap-3 px-5 py-4">
            <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${history ? 'bg-emerald-50 text-emerald-700' : overdue ? 'bg-red-50 text-red-700' : 'bg-blue-50 text-blue-700'}`}>
                {['appel', 'CALL'].includes(activity.activityType) ? <PhoneCall className="h-4 w-4" /> : <MessageSquareText className="h-4 w-4" />}
            </div>
            <div className="min-w-0">
                <p className="truncate text-sm font-black text-slate-900">{activity.subject}</p>
                {activity.notes && <p className="mt-1 line-clamp-2 text-xs font-semibold text-slate-500">{activity.notes}</p>}
            </div>
            <div className="text-right">
                <p className={`text-xs font-black ${overdue ? 'text-red-700' : 'text-slate-600'}`}>{formatDate(history ? activity.completedAt : activity.dueAt)}</p>
                <p className="mt-1 text-[9px] font-black uppercase tracking-widest text-slate-400">{history ? 'Terminé' : overdue ? 'En retard' : 'À faire'}</p>
                {!history && onComplete && (
                    <button
                        type="button"
                        onClick={onComplete}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-emerald-200 px-2 py-1 text-[10px] font-black text-emerald-700 hover:bg-emerald-50"
                    >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Terminer
                    </button>
                )}
            </div>
        </div>
    );
}

function ContextColumn({ icon: Icon, title, empty, children }) {
    const hasChildren = React.Children.count(children) > 0;
    return (
        <div className="min-w-0 px-5 py-4">
            <div className="mb-2 flex items-center gap-2 text-slate-700"><Icon className="h-4 w-4" /><p className="text-sm font-black">{title}</p></div>
            {hasChildren ? children : <p className="py-5 text-center text-xs font-semibold text-slate-400">{empty}</p>}
        </div>
    );
}

function LabeledValue({ label, value }) {
    return (
        <div className="min-w-0">
            <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className="mt-1 truncate text-xs font-black text-slate-700" title={value}>{value || '-'}</p>
        </div>
    );
}

function ActionDialog({
    mode,
    client,
    sites,
    opportunities,
    opportunityDraft,
    setOpportunityDraft,
    activityDraft,
    setActivityDraft,
    isSubmitting,
    error,
    onClose,
    onSubmit,
}) {
    const isOpportunity = mode === 'opportunity';
    const isCall = mode === 'call';
    const title = isOpportunity ? 'Nouvelle opportunité' : isCall ? 'Noter un appel' : 'Planifier une relance';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
            <div className="w-full max-w-2xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
                <div className="flex items-start justify-between bg-slate-900 px-6 py-5 text-white">
                    <div>
                        <p className="text-[9px] font-black uppercase tracking-widest text-blue-200">CRM · {client.name}</p>
                        <h3 className="mt-2 text-xl font-black">{title}</h3>
                    </div>
                    <button onClick={onClose} className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white"><X className="h-5 w-5" /></button>
                </div>
                {isOpportunity ? (
                    <div className="grid gap-4 p-6 sm:grid-cols-2">
                        <Field label="Nom de l'opportunité" wide>
                            <input value={opportunityDraft.title} onChange={event => setOpportunityDraft(current => ({ ...current, title: event.target.value }))} placeholder="Ex. Menuiseries chantier Bonapriso" className={inputClass} />
                        </Field>
                        <Field label="Entrée dans le pipeline">
                            <div className={`${inputClass} flex items-center bg-slate-50 font-black text-slate-700`}>
                                Nouveau besoin à qualifier
                            </div>
                        </Field>
                        <Field label="Montant estimé HT">
                            <input type="number" min="0" step="0.01" value={opportunityDraft.amount} onChange={event => setOpportunityDraft(current => ({ ...current, amount: event.target.value }))} className={inputClass} />
                        </Field>
                        <Field label="Chantier lié">
                            <select value={opportunityDraft.site_address_id} onChange={event => setOpportunityDraft(current => ({ ...current, site_address_id: event.target.value }))} className={inputClass}>
                                <option value="">Aucun chantier</option>
                                {sites.map(site => <option key={site.id} value={site.id}>{site.reference} · {site.label}</option>)}
                            </select>
                        </Field>
                        <Field label="Date du prochain jalon">
                            <input type="date" value={opportunityDraft.next_milestone_at} onChange={event => setOpportunityDraft(current => ({ ...current, next_milestone_at: event.target.value }))} className={inputClass} />
                        </Field>
                        <Field label="Prochain jalon" wide>
                            <input value={opportunityDraft.next_milestone} onChange={event => setOpportunityDraft(current => ({ ...current, next_milestone: event.target.value }))} placeholder="Ex. Valider le rendez-vous de métré" className={inputClass} />
                        </Field>
                    </div>
                ) : (
                    <div className="grid gap-4 p-6 sm:grid-cols-2">
                        <Field label={isCall ? "Objet de l'appel" : 'Objet de la relance'} wide>
                            <input value={activityDraft.subject} onChange={event => setActivityDraft(current => ({ ...current, subject: event.target.value }))} className={inputClass} />
                        </Field>
                        {!isCall && (
                            <Field label="Date et heure">
                                <input type="datetime-local" value={activityDraft.due_at} onChange={event => setActivityDraft(current => ({ ...current, due_at: event.target.value }))} className={inputClass} />
                            </Field>
                        )}
                        <Field label="Opportunité liée" wide={isCall}>
                            <select value={activityDraft.opportunity_id} onChange={event => setActivityDraft(current => ({ ...current, opportunity_id: event.target.value }))} className={inputClass}>
                                <option value="">Aucune opportunité</option>
                                {opportunities.map(opportunity => <option key={opportunity.id} value={opportunity.id}>{opportunity.title}</option>)}
                            </select>
                        </Field>
                        <Field label={isCall ? "Compte rendu de l'appel" : 'Message ou objectif'} wide>
                            <textarea value={activityDraft.notes} onChange={event => setActivityDraft(current => ({ ...current, notes: event.target.value }))} className={`${inputClass} min-h-28`} placeholder={isCall ? 'Décisions, objections, prochaine étape...' : 'Sujet de la relance et résultat attendu...'} />
                        </Field>
                    </div>
                )}
                {error && <div className="mx-6 mb-4 border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">{error}</div>}
                <div className="flex justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                    <button onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-600 hover:bg-slate-100">Annuler</button>
                    <button onClick={onSubmit} disabled={isSubmitting} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-black text-white hover:bg-blue-500 disabled:bg-slate-300">
                        {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                        {isCall ? "Enregistrer l'appel" : 'Enregistrer'}
                    </button>
                </div>
            </div>
        </div>
    );
}

function Field({ label, wide, children }) {
    return (
        <label className={wide ? 'sm:col-span-2' : ''}>
            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</span>
            <div className="mt-2">{children}</div>
        </label>
    );
}

const inputClass = 'w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100';

function nextActionTone(tone) {
    const tones = {
        red: 'border-red-500 bg-red-50 text-red-950',
        blue: 'border-blue-600 bg-blue-50 text-blue-950',
        amber: 'border-amber-500 bg-amber-50 text-amber-950',
        slate: 'border-slate-400 bg-slate-50 text-slate-900',
    };
    return tones[tone] || tones.slate;
}

function opportunityLabel(stage) {
    const labels = {
        nouveau: 'Nouveau',
        qualifie: 'Besoin qualifié',
        metre_a_planifier: 'Métré à planifier',
        metre_en_cours: 'Métré en cours',
        proposition_a_preparer: 'Chiffrage',
        proposition_a_valider: 'Proposition à valider',
        proposition_envoyee: 'Proposition envoyée',
        negociation: 'Négociation',
        gagne: 'Gagnée',
        perdu: 'Perdue',
        QUALIFICATION: 'Qualification',
        NEEDS_ANALYSIS: 'Besoin qualifié',
        MEASURE_PLANNED: 'Métré à planifier',
        QUOTATION: 'Chiffrage',
        NEGOTIATION: 'Négociation',
    };
    return labels[String(stage || '').toUpperCase()] || stage;
}

function isOverdue(value) {
    return Boolean(value) && new Date(value).getTime() < Date.now();
}

function toLocalDateTimeInput(date) {
    const offset = date.getTimezoneOffset();
    return new Date(date.getTime() - offset * 60 * 1000).toISOString().slice(0, 16);
}

function formatSiteAddress(site) {
    return [
        site.address_line1,
        site.address_line2,
        [site.postal_code, site.city].filter(Boolean).join(' '),
        site.country,
    ].filter(Boolean).join(', ');
}

function saleAmount(sale) {
    return (sale.lines || []).reduce(
        (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
        0,
    );
}
