import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    ArrowRight,
    CalendarClock,
    CheckCircle2,
    ClipboardList,
    Plus,
    Search,
    Target,
    UserRound,
    X,
} from 'lucide-react';
import api from '../services/api';

const STAGES = {
    nouveau: { label: 'Nouveau besoin', probability: 10 },
    qualifie: { label: 'Besoin qualifié', probability: 30 },
    metre_a_planifier: { label: 'Métré à planifier', probability: 40 },
    metre_en_cours: { label: 'Métré en cours', probability: 50 },
    proposition_a_preparer: { label: 'Proposition à préparer', probability: 60 },
    proposition_a_valider: { label: 'Proposition à valider', probability: 65 },
    proposition_envoyee: { label: 'Proposition envoyée', probability: 70 },
    negociation: { label: 'Négociation', probability: 80 },
    gagne: { label: 'Gagné', probability: 100 },
    perdu: { label: 'Perdu', probability: 0 },
};

const COLUMNS = [
    {
        key: 'new',
        label: 'Demande reçue',
        detail: 'À prendre en charge',
        stages: ['nouveau'],
        tone: 'slate',
    },
    {
        key: 'qualified',
        label: 'À qualifier',
        detail: 'Périmètre, délai et décision',
        stages: ['qualifie'],
        tone: 'blue',
    },
    {
        key: 'study',
        label: 'Étude & chiffrage',
        detail: 'Cotes, diagnostic et prix',
        stages: ['metre_a_planifier', 'metre_en_cours', 'proposition_a_preparer'],
        tone: 'emerald',
    },
    {
        key: 'review',
        label: 'Proposition à valider',
        detail: 'Contrôle interne avant envoi',
        stages: ['proposition_a_valider'],
        tone: 'indigo',
    },
    {
        key: 'sent',
        label: 'Proposition envoyée',
        detail: 'Relance client planifiée',
        stages: ['proposition_envoyee'],
        tone: 'amber',
    },
    {
        key: 'decision',
        label: 'Négociation / décision',
        detail: 'Arbitrage final du client',
        stages: ['negociation'],
        tone: 'amber',
    },
    {
        key: 'closed',
        label: 'Clôturées',
        detail: 'Signées ou perdues',
        stages: ['gagne', 'perdu'],
        tone: 'red',
    },
];

const NEED_LABELS = {
    fourniture_pose: 'Fourniture + pose',
    fourniture_seule: 'Fourniture seule',
    sav: 'SAV',
    autre: 'Autre besoin',
};

const ORIGIN_OPTIONS = [
    ['AGENCE', 'Passage en agence'],
    ['TELEPHONE', 'Téléphone'],
    ['EMAIL', 'Email'],
    ['SITE_WEB', 'Site web'],
    ['RECOMMANDATION', 'Recommandation'],
    ['APPEL_OFFRES', "Appel d'offres"],
    ['AUTRE', 'Autre'],
];

const EMPTY_DRAFT = {
    client_id: '',
    title: '',
    origin: 'AGENCE',
    need_type: 'fourniture_pose',
    estimated_amount: '',
    probability: 10,
    next_milestone: 'Qualifier le besoin avec le client',
    next_milestone_at: '',
};

const normalize = value => String(value || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

const formatMoney = value => Number(value || 0).toLocaleString('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
});

const formatDate = value => value
    ? new Date(value).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })
    : 'Non planifiée';

const readableError = error => (
    error?.response?.data?.detail
    || error?.message
    || "L'opération n'a pas pu être enregistrée."
);

export default function CRMOpportunityPipeline({
    clients,
    onOpenClient,
    onOpenOrder,
    onPlanMeasure,
}) {
    const [searchTerm, setSearchTerm] = useState('');
    const [showCreate, setShowCreate] = useState(false);
    const [draft, setDraft] = useState(EMPTY_DRAFT);
    const [workingId, setWorkingId] = useState(null);
    const [error, setError] = useState('');
    const [lossTarget, setLossTarget] = useState(null);
    const [lossReason, setLossReason] = useState('');

    const opportunitiesQuery = useQuery({
        queryKey: ['crm-opportunities', 'pipeline'],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/opportunities');
            return Array.isArray(response.data) ? response.data : [];
        },
    });

    const opportunities = opportunitiesQuery.data || [];
    const missionsQuery = useQuery({
        queryKey: ['measure-missions', 'crm-opportunity-pipeline'],
        queryFn: async () => {
            const response = await api.get('/v2/mmg/missions');
            return Array.isArray(response.data) ? response.data : [];
        },
    });
    const missionsByOpportunity = useMemo(() => {
        const result = new Map();
        (missionsQuery.data || []).forEach(mission => {
            if (!mission.opportunity_id) return;
            const previous = result.get(mission.opportunity_id);
            if (!previous || new Date(mission.created_at || 0) > new Date(previous.created_at || 0)) {
                result.set(mission.opportunity_id, mission);
            }
        });
        return result;
    }, [missionsQuery.data]);
    const filtered = useMemo(() => {
        const needle = normalize(searchTerm);
        if (!needle) return opportunities;
        return opportunities.filter(item => [
            item.reference,
            item.title,
            item.client_name,
            item.owner_name,
            item.next_milestone,
        ].some(value => normalize(value).includes(needle)));
    }, [opportunities, searchTerm]);

    const groupedColumns = useMemo(() => COLUMNS.map(column => ({
        ...column,
        items: filtered
            .filter(item => column.stages.includes(item.stage))
            .map(item => ({ ...item, measure_mission: missionsByOpportunity.get(item.id) || null }))
            .sort((a, b) => new Date(a.next_milestone_at || '2999-12-31') - new Date(b.next_milestone_at || '2999-12-31')),
    })), [filtered, missionsByOpportunity]);

    const openItems = opportunities.filter(item => !['gagne', 'perdu'].includes(item.stage));
    const wonItems = opportunities.filter(item => item.stage === 'gagne');
    const weightedPipeline = openItems.reduce(
        (sum, item) => sum + (Number(item.estimated_amount || 0) * Number(item.probability || 0) / 100),
        0,
    );
    const withoutAction = openItems.filter(item => !item.next_milestone || !item.next_milestone_at).length;

    const createOpportunity = async event => {
        event.preventDefault();
        if (!draft.client_id || !draft.title.trim()) {
            setError('Sélectionnez un client et nommez le besoin.');
            return;
        }
        setWorkingId('create');
        setError('');
        try {
            await api.post('/v2/mmg/opportunities', {
                client_id: Number(draft.client_id),
                title: draft.title.trim(),
                origin: draft.origin,
                need_type: draft.need_type,
                stage: 'nouveau',
                estimated_amount: draft.estimated_amount === '' ? null : Number(draft.estimated_amount),
                probability: Number(draft.probability || 10),
                next_milestone: draft.next_milestone.trim() || null,
                next_milestone_at: draft.next_milestone_at
                    ? new Date(draft.next_milestone_at).toISOString()
                    : null,
            });
            await opportunitiesQuery.refetch();
            setDraft(EMPTY_DRAFT);
            setShowCreate(false);
        } catch (requestError) {
            setError(readableError(requestError));
        } finally {
            setWorkingId(null);
        }
    };

    const updateStage = async (opportunity, stage, options = {}) => {
        setWorkingId(opportunity.id);
        setError('');
        try {
            await api.patch(`/v2/mmg/opportunities/${opportunity.id}`, {
                stage,
                probability: STAGES[stage]?.probability ?? opportunity.probability,
                ...(options.next_milestone !== undefined
                    ? { next_milestone: options.next_milestone }
                    : {}),
                ...(options.loss_reason !== undefined
                    ? { loss_reason: options.loss_reason }
                    : {}),
            });
            await opportunitiesQuery.refetch();
            if (options.after) options.after();
        } catch (requestError) {
            setError(readableError(requestError));
        } finally {
            setWorkingId(null);
        }
    };

    const planMeasure = (opportunity, source = 'SITE_VISIT') => {
        const openMission = () => onPlanMeasure(
            opportunity,
            source,
            opportunity.measure_mission?.id || null,
        );
        if (opportunity.stage === 'qualifie') {
            updateStage(opportunity, 'metre_a_planifier', {
                next_milestone: 'Planifier et réaliser le métré',
                after: openMission,
            });
            return;
        }
        openMission();
    };

    const closeAsLost = async event => {
        event.preventDefault();
        if (!lossTarget || !lossReason.trim()) return;
        await updateStage(lossTarget, 'perdu', {
            next_milestone: null,
            loss_reason: lossReason.trim(),
            after: () => {
                setLossTarget(null);
                setLossReason('');
            },
        });
    };

    if (opportunitiesQuery.isLoading || missionsQuery.isLoading) {
        return <PipelineMessage title="Chargement du pipeline…" detail="Lecture des opportunités CRM." />;
    }

    if (opportunitiesQuery.isError || missionsQuery.isError) {
        return (
            <PipelineMessage
                title="Le pipeline CRM est indisponible"
                detail={readableError(opportunitiesQuery.error || missionsQuery.error)}
                action={<button onClick={() => Promise.all([opportunitiesQuery.refetch(), missionsQuery.refetch()])} className="text-sm font-black text-blue-700">Réessayer</button>}
            />
        );
    }

    return (
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-slate-50/50">
            <div className="border-b border-slate-200 bg-white px-5 py-4 lg:px-7">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <PipelineMetric label="Opportunités ouvertes" value={openItems.length} />
                    <PipelineMetric label="Pipeline pondéré" value={formatMoney(weightedPipeline)} tone="blue" />
                    <PipelineMetric label="Sans prochaine action" value={withoutAction} tone={withoutAction ? 'amber' : 'slate'} />
                    <PipelineMetric label="Transférées en commande" value={wonItems.length} tone="emerald" />
                </div>
                <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="relative w-full lg:max-w-xl">
                        <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                        <input
                            value={searchTerm}
                            onChange={event => setSearchTerm(event.target.value)}
                            placeholder="Référence, besoin, client, responsable…"
                            className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm font-bold text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                        />
                    </div>
                    <button
                        onClick={() => {
                            setDraft(EMPTY_DRAFT);
                            setError('');
                            setShowCreate(true);
                        }}
                        className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-black text-white hover:bg-blue-500"
                    >
                        <Plus className="h-4 w-4" />
                        Nouvelle opportunité
                    </button>
                </div>
                {error && (
                    <div className="mt-3 border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
                        {error}
                    </div>
                )}
            </div>

            <div className="flex min-h-[560px] gap-4 overflow-x-auto p-5 lg:p-7">
                {groupedColumns.map(column => (
                    <PipelineColumn
                        key={column.key}
                        column={column}
                        workingId={workingId}
                        onOpenClient={onOpenClient}
                        onOpenOrder={onOpenOrder}
                        onPlanMeasure={planMeasure}
                        onAdvance={(opportunity, stage, options) => updateStage(opportunity, stage, options)}
                        onMarkLost={opportunity => {
                            setLossTarget(opportunity);
                            setLossReason('');
                            setError('');
                        }}
                    />
                ))}
            </div>

            {showCreate && (
                <OpportunityDialog
                    clients={clients}
                    draft={draft}
                    setDraft={setDraft}
                    saving={workingId === 'create'}
                    error={error}
                    onClose={() => setShowCreate(false)}
                    onSubmit={createOpportunity}
                />
            )}
            {lossTarget && (
                <LossDialog
                    opportunity={lossTarget}
                    reason={lossReason}
                    setReason={setLossReason}
                    saving={workingId === lossTarget.id}
                    error={error}
                    onClose={() => setLossTarget(null)}
                    onSubmit={closeAsLost}
                />
            )}
        </div>
    );
}

function PipelineMetric({ label, value, tone = 'slate' }) {
    const tones = {
        slate: 'border-slate-200 bg-white text-slate-950',
        blue: 'border-blue-200 bg-blue-50 text-blue-950',
        amber: 'border-amber-200 bg-amber-50 text-amber-950',
        emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    };
    return (
        <div className={`border px-4 py-3 ${tones[tone]}`}>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-55">{label}</p>
            <p className="mt-1 text-2xl font-black">{value}</p>
        </div>
    );
}

function PipelineColumn({
    column,
    workingId,
    onOpenClient,
    onOpenOrder,
    onPlanMeasure,
    onAdvance,
    onMarkLost,
}) {
    const amount = column.items.reduce((sum, item) => sum + Number(item.estimated_amount || 0), 0);
    const toneClasses = {
        slate: 'border-t-slate-400',
        blue: 'border-t-blue-500',
        emerald: 'border-t-emerald-500',
        indigo: 'border-t-indigo-500',
        amber: 'border-t-amber-500',
        red: 'border-t-red-500',
    };
    return (
        <section className={`flex w-[310px] shrink-0 flex-col border border-t-4 border-slate-200 bg-white ${toneClasses[column.tone]}`}>
            <div className="border-b border-slate-100 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <h3 className="text-sm font-black text-slate-950">{column.label}</h3>
                        <p className="mt-1 text-xs font-semibold text-slate-500">{column.detail}</p>
                    </div>
                    <span className="bg-slate-100 px-2 py-1 text-xs font-black text-slate-700">{column.items.length}</span>
                </div>
                {amount > 0 && <p className="mt-3 text-xs font-black text-slate-500">{formatMoney(amount)}</p>}
            </div>
            <div className="flex-1 space-y-3 bg-slate-50/70 p-3">
                {column.items.map(opportunity => (
                    <OpportunityCard
                        key={opportunity.id}
                        opportunity={opportunity}
                        busy={workingId === opportunity.id}
                        onOpenClient={() => onOpenClient(opportunity.client_id)}
                        onOpenOrder={() => onOpenOrder(opportunity.sale_order_id)}
                        onPlanMeasure={source => onPlanMeasure(opportunity, source)}
                        onAdvance={(stage, options) => onAdvance(opportunity, stage, options)}
                        onMarkLost={() => onMarkLost(opportunity)}
                    />
                ))}
                {!column.items.length && (
                    <div className="flex h-32 items-center justify-center border border-dashed border-slate-200 bg-white px-6 text-center">
                        <p className="text-xs font-bold text-slate-400">Aucune opportunité à cette étape.</p>
                    </div>
                )}
            </div>
        </section>
    );
}

function OpportunityCard({
    opportunity,
    busy,
    onOpenClient,
    onOpenOrder,
    onPlanMeasure,
    onAdvance,
    onMarkLost,
}) {
    const isInstall = opportunity.need_type === 'fourniture_pose';
    const [showStudyRoutes, setShowStudyRoutes] = useState(false);
    const isTerminal = ['gagne', 'perdu'].includes(opportunity.stage);
    const action = (() => {
        if (opportunity.stage === 'nouveau') {
            return {
                label: 'Qualifier',
                onClick: () => onAdvance('qualifie', { next_milestone: "Choisir le parcours d'étude" }),
            };
        }
        if (opportunity.stage === 'qualifie' && isInstall) {
            return {
                label: "Choisir le parcours d'étude",
                onClick: () => setShowStudyRoutes(current => !current),
                icon: ClipboardList,
            };
        }
        if (opportunity.stage === 'qualifie') {
            const nextMilestone = opportunity.need_type === 'sav'
                ? 'Réaliser le diagnostic et préparer le chiffrage'
                : 'Préparer le chiffrage commercial';
            return {
                label: opportunity.need_type === 'sav' ? 'Démarrer le diagnostic' : 'Démarrer le chiffrage',
                onClick: () => onAdvance('proposition_a_preparer', { next_milestone: nextMilestone }),
            };
        }
        if (['metre_a_planifier', 'metre_en_cours'].includes(opportunity.stage)) {
            return {
                label: opportunity.measure_mission ? 'Ouvrir la mission' : 'Créer la mission',
                onClick: () => onPlanMeasure(opportunity.measure_mission?.source_type || 'SITE_VISIT'),
                icon: ClipboardList,
            };
        }
        if (opportunity.stage === 'proposition_a_preparer') {
            return {
                label: 'Soumettre à validation',
                onClick: () => onAdvance('proposition_a_valider', {
                    next_milestone: 'Contrôler le prix et les documents avant envoi',
                }),
            };
        }
        if (opportunity.stage === 'proposition_a_valider') {
            return {
                label: 'Marquer comme envoyée',
                onClick: () => onAdvance('proposition_envoyee', {
                    next_milestone: 'Relancer le client après envoi',
                }),
            };
        }
        if (opportunity.stage === 'proposition_envoyee') {
            return {
                label: 'Passer en négociation',
                onClick: () => onAdvance('negociation', { next_milestone: 'Obtenir la décision du client' }),
            };
        }
        if (opportunity.stage === 'gagne') {
            return {
                label: opportunity.sale_order_id ? 'Ouvrir la commande' : 'Ouvrir la fiche client',
                onClick: opportunity.sale_order_id ? onOpenOrder : onOpenClient,
            };
        }
        if (opportunity.stage === 'perdu') {
            return {
                label: 'Réouvrir',
                onClick: () => onAdvance('qualifie', { next_milestone: 'Requalifier le besoin client' }),
            };
        }
        return { label: 'Ouvrir la fiche client', onClick: onOpenClient, icon: ArrowRight };
    })();
    const ActionIcon = action.icon || ArrowRight;
    const overdue = opportunity.next_milestone_at
        && new Date(opportunity.next_milestone_at) < new Date()
        && !['gagne', 'perdu'].includes(opportunity.stage);

    return (
        <article className="border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="font-mono text-[10px] font-black text-blue-700">{opportunity.reference}</p>
                    <h4 className="mt-1 line-clamp-2 text-sm font-black text-slate-950">{opportunity.title}</h4>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="bg-slate-100 px-2 py-1 text-[9px] font-black uppercase text-slate-600">
                        {opportunity.probability}%
                    </span>
                    <span className="max-w-32 bg-blue-50 px-2 py-1 text-right text-[8px] font-black uppercase text-blue-700">
                        {STAGES[opportunity.stage]?.label || opportunity.stage}
                    </span>
                </div>
            </div>
            <button onClick={onOpenClient} className="mt-3 flex w-full items-center gap-2 text-left text-xs font-black text-slate-700 hover:text-blue-700">
                <UserRound className="h-3.5 w-3.5" />
                <span className="truncate">{opportunity.client_name || `Client #${opportunity.client_id}`}</span>
            </button>
            <div className="mt-3 grid grid-cols-2 gap-2 border-y border-slate-100 py-3">
                <div>
                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Montant</p>
                    <p className="mt-1 text-sm font-black text-slate-900">{formatMoney(opportunity.estimated_amount)}</p>
                </div>
                <div>
                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Besoin</p>
                    <p className="mt-1 text-xs font-black text-slate-700">{NEED_LABELS[opportunity.need_type] || opportunity.need_type}</p>
                </div>
            </div>
            <div className={`mt-3 border-l-2 pl-3 ${overdue ? 'border-red-500' : 'border-blue-400'}`}>
                <p className={`text-xs font-black ${overdue ? 'text-red-700' : 'text-slate-800'}`}>
                    {opportunity.next_milestone || 'Prochaine action à définir'}
                </p>
                <p className="mt-1 flex items-center gap-1 text-[10px] font-bold text-slate-500">
                    <CalendarClock className="h-3.5 w-3.5" />
                    {formatDate(opportunity.next_milestone_at)}
                    {opportunity.owner_name ? ` · ${opportunity.owner_name}` : ' · Non affectée'}
                </p>
            </div>
            <button
                onClick={action.onClick}
                disabled={busy}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2.5 text-xs font-black text-white hover:bg-slate-800 disabled:cursor-wait disabled:bg-slate-300"
            >
                {busy ? 'Enregistrement…' : action.label}
                {!busy && <ActionIcon className="h-4 w-4" />}
            </button>
            {showStudyRoutes && (
                <div className="mt-2 grid gap-2 border border-emerald-200 bg-emerald-50 p-2">
                    <StudyRouteButton label="Visite chantier MMG" onClick={() => onPlanMeasure('SITE_VISIT')} />
                    <StudyRouteButton label="Cotes fournies par le client" onClick={() => onPlanMeasure('CLIENT_DOCUMENTS')} />
                    <StudyRouteButton label="Saisie accompagnée en agence" onClick={() => onPlanMeasure('AGENCY_ASSISTED')} />
                </div>
            )}
            {!isTerminal && (
                <button
                    onClick={onMarkLost}
                    disabled={busy}
                    className="mt-2 w-full px-3 py-2 text-[10px] font-black uppercase tracking-wider text-red-600 hover:bg-red-50 disabled:text-slate-300"
                >
                    Classer comme perdue
                </button>
            )}
        </article>
    );
}

function StudyRouteButton({ label, onClick }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className="flex items-center justify-between bg-white px-3 py-2 text-left text-[11px] font-black text-emerald-900 hover:bg-emerald-100"
        >
            {label}
            <ArrowRight className="h-3.5 w-3.5" />
        </button>
    );
}

function OpportunityDialog({
    clients,
    draft,
    setDraft,
    saving,
    error,
    onClose,
    onSubmit,
}) {
    const update = (field, value) => setDraft(current => ({ ...current, [field]: value }));
    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4">
            <form onSubmit={onSubmit} className="max-h-[92vh] w-full max-w-3xl overflow-y-auto bg-white shadow-2xl">
                <header className="flex items-start justify-between gap-4 bg-slate-900 px-6 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-300">CRM avant-vente</p>
                        <h2 className="mt-1 text-2xl font-black">Enregistrer une nouvelle demande</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-300">Le besoin reste dans le CRM jusqu'à la signature client.</p>
                    </div>
                    <button type="button" onClick={onClose} title="Fermer" className="p-2 text-slate-300 hover:text-white">
                        <X className="h-5 w-5" />
                    </button>
                </header>
                <div className="grid gap-4 p-6 md:grid-cols-2">
                    <Field label="Client" wide>
                        <select required value={draft.client_id} onChange={event => update('client_id', event.target.value)} className={inputClass}>
                            <option value="">Sélectionner un client…</option>
                            {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
                        </select>
                    </Field>
                    <Field label="Besoin / projet" wide>
                        <input required value={draft.title} onChange={event => update('title', event.target.value)} placeholder="Ex. Remplacement menuiseries du siège" className={inputClass} />
                    </Field>
                    <Field label="Nature du besoin">
                        <select value={draft.need_type} onChange={event => update('need_type', event.target.value)} className={inputClass}>
                            {Object.entries(NEED_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                    </Field>
                    <Field label="Origine">
                        <select value={draft.origin} onChange={event => update('origin', event.target.value)} className={inputClass}>
                            {ORIGIN_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                    </Field>
                    <Field label="Montant estimé HT">
                        <input type="number" min="0" step="0.01" value={draft.estimated_amount} onChange={event => update('estimated_amount', event.target.value)} placeholder="0,00" className={inputClass} />
                    </Field>
                    <Field label="Probabilité">
                        <select value={draft.probability} onChange={event => update('probability', event.target.value)} className={inputClass}>
                            <option value="10">10 % · demande reçue</option>
                            <option value="20">20 % · besoin probable</option>
                            <option value="30">30 % · qualification avancée</option>
                        </select>
                    </Field>
                    <Field label="Prochaine action">
                        <input value={draft.next_milestone} onChange={event => update('next_milestone', event.target.value)} className={inputClass} />
                    </Field>
                    <Field label="Échéance">
                        <input type="datetime-local" value={draft.next_milestone_at} onChange={event => update('next_milestone_at', event.target.value)} className={inputClass} />
                    </Field>
                    {error && (
                        <div className="border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-800 md:col-span-2">
                            {error}
                        </div>
                    )}
                </div>
                <footer className="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                    <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-700 hover:bg-slate-100">
                        Annuler
                    </button>
                    <button type="submit" disabled={saving} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-black text-white hover:bg-blue-500 disabled:bg-slate-300">
                        {saving ? 'Création…' : 'Ajouter à Demande reçue'}
                        {!saving && <Target className="h-4 w-4" />}
                    </button>
                </footer>
            </form>
        </div>
    );
}

function LossDialog({
    opportunity,
    reason,
    setReason,
    saving,
    error,
    onClose,
    onSubmit,
}) {
    return (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-950/55 p-4">
            <form onSubmit={onSubmit} className="w-full max-w-lg bg-white shadow-2xl">
                <header className="flex items-start justify-between gap-4 bg-slate-900 px-6 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-red-300">Clôture commerciale</p>
                        <h2 className="mt-1 text-xl font-black">Classer l'opportunité comme perdue</h2>
                        <p className="mt-1 text-sm font-semibold text-slate-300">{opportunity.reference} · {opportunity.client_name}</p>
                    </div>
                    <button type="button" onClick={onClose} title="Fermer" className="p-2 text-slate-300 hover:text-white">
                        <X className="h-5 w-5" />
                    </button>
                </header>
                <div className="p-6">
                    <label>
                        <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">Motif obligatoire</span>
                        <textarea
                            required
                            rows="4"
                            value={reason}
                            onChange={event => setReason(event.target.value)}
                            placeholder="Prix, délai, concurrence, projet abandonné…"
                            className={inputClass}
                        />
                    </label>
                    {error && (
                        <div className="mt-4 border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">
                            {error}
                        </div>
                    )}
                </div>
                <footer className="flex items-center justify-end gap-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
                    <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-700 hover:bg-slate-100">
                        Annuler
                    </button>
                    <button type="submit" disabled={saving || !reason.trim()} className="rounded-lg bg-red-600 px-5 py-2.5 text-sm font-black text-white hover:bg-red-500 disabled:bg-slate-300">
                        {saving ? 'Clôture…' : 'Confirmer la perte'}
                    </button>
                </footer>
            </form>
        </div>
    );
}

function Field({ label, wide, children }) {
    return (
        <label className={wide ? 'md:col-span-2' : ''}>
            <span className="mb-1.5 block text-[10px] font-black uppercase tracking-widest text-slate-500">{label}</span>
            {children}
        </label>
    );
}

function PipelineMessage({ title, detail, action }) {
    return (
        <div className="flex flex-1 items-center justify-center bg-slate-50 p-8">
            <div className="max-w-lg border border-slate-200 bg-white p-8 text-center">
                <CheckCircle2 className="mx-auto h-10 w-10 text-slate-300" />
                <p className="mt-3 text-lg font-black text-slate-900">{title}</p>
                <p className="mt-1 text-sm font-semibold text-slate-500">{detail}</p>
                {action && <div className="mt-4">{action}</div>}
            </div>
        </div>
    );
}

const inputClass = 'w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100';
