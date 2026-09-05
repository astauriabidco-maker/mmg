import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BellRing, Building2, CalendarClock, CheckCircle2, ClipboardList, Download, FileText, Mail, MapPin, Merge, Package, Phone, Plus, Search, Send, Truck, Upload, Users, Wrench, X } from 'lucide-react';
import api from '../services/api';
import BusinessTimeline from '../components/BusinessTimeline';
import CRMClientActionWorkspace from '../components/CRMClientActionWorkspace';
import CRMCockpit from '../components/CRMCockpit';
import CRMOpportunityPipeline from '../components/CRMOpportunityPipeline';
import MeasureMissionBoard from '../components/MeasureMissionBoard';
import { useAuth } from '../context/AuthContext';
import { userHasAnyRole } from '../utils/roleNavigation';

const saleAmount = (sale) => (sale.lines || []).reduce(
    (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
    0
);

const isPresalesStatus = (status) => ['DRAFT', 'SENT', 'CANCELLED'].includes(status);
const isActivePresalesStatus = (status) => ['DRAFT', 'SENT'].includes(status);
const CRM_FILTER_STORAGE_KEY = 'mmg.crm.clientFilters.v1';
const COMMERCIAL_STATUS_OPTIONS = [
    { value: '', label: 'Tous statuts' },
    { value: 'active_opportunity', label: 'Opportunité active' },
    { value: 'to_follow_up', label: 'À relancer' },
    { value: 'missing_next_action', label: 'Sans prochaine action' },
    { value: 'quote_sent', label: 'Devis envoyé' },
    { value: 'quote_signed', label: 'Devis signé' },
    { value: 'quiet', label: 'Calme' },
];
const COMMERCIAL_STATUS_LABELS = {
    active_opportunity: 'Opportunité',
    to_follow_up: 'À relancer',
    missing_next_action: 'Sans action',
    quote_sent: 'Devis envoyé',
    quote_signed: 'Signé',
    quiet: 'Calme',
};
const COMMERCIAL_STATUS_STYLES = {
    active_opportunity: 'bg-blue-100 text-blue-700',
    to_follow_up: 'bg-red-100 text-red-700',
    missing_next_action: 'bg-amber-100 text-amber-800',
    quote_sent: 'bg-indigo-100 text-indigo-700',
    quote_signed: 'bg-emerald-100 text-emerald-700',
    quiet: 'bg-slate-100 text-slate-600',
};

export default function CRMClientsDashboard() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [crmView, setCrmView] = useState('home');
    const [searchTerm, setSearchTerm] = useState('');
    const [segmentFilter, setSegmentFilter] = useState('');
    const [tagFilter, setTagFilter] = useState('');
    const [commercialStatusFilter, setCommercialStatusFilter] = useState('');
    const [selectedClientId, setSelectedClientId] = useState(null);
    const [showProposalStarter, setShowProposalStarter] = useState(false);
    const [showClientModal, setShowClientModal] = useState(false);
    const [showMeasureStarter, setShowMeasureStarter] = useState(false);
    const [showSiteModal, setShowSiteModal] = useState(false);
    const [showDuplicates, setShowDuplicates] = useState(false);
    const [isCreatingClient, setIsCreatingClient] = useState(false);
    const [isCreatingSite, setIsCreatingSite] = useState(false);
    const [isImportingClients, setIsImportingClients] = useState(false);
    const [importPreview, setImportPreview] = useState(null);
    const [pendingImportFile, setPendingImportFile] = useState(null);
    const [importUpdateExisting, setImportUpdateExisting] = useState(false);
    const [clientDataMessage, setClientDataMessage] = useState('');
    const [clientDraft, setClientDraft] = useState({
        name: '',
        contact_name: '',
        phone: '',
        email: '',
        address: '',
        tax_id: '',
        customer_type: 'B2B',
        segment: '',
        tags: '',
    });
    const [siteDraft, setSiteDraft] = useState({
        label: 'Chantier',
        address_line1: '',
        address_line2: '',
        postal_code: '',
        city: '',
        country: 'FR',
        contact_name: '',
        contact_phone: '',
        access_instructions: '',
        is_default: false,
    });

    const planMeasureForClient = () => {
        setShowMeasureStarter(true);
    };

    const startMeasureFlow = (source, scope = 'SUPPLY_AND_INSTALL') => {
        const params = new URLSearchParams({ source, scope });
        if (selectedClient?.id) params.set('clientId', selectedClient.id);
        setShowMeasureStarter(false);
        navigate(`/measure-missions/new?${params.toString()}`);
    };

    const { data: clients = [], refetch: refetchClients } = useQuery({
        queryKey: ['partners', 'clients'],
        queryFn: async () => {
            const res = await api.get('/v2/partners/clients');
            return res.data;
        }
    });

    const duplicatesQuery = useQuery({
        queryKey: ['partners', 'clients', 'duplicates'],
        enabled: showDuplicates,
        queryFn: async () => {
            const response = await api.get('/v2/partners/clients/duplicates');
            return Array.isArray(response.data) ? response.data : [];
        },
    });

    const segmentationQuery = useQuery({
        queryKey: ['partners', 'clients', 'segmentation'],
        queryFn: async () => {
            const response = await api.get('/v2/partners/clients/segmentation');
            return response.data;
        },
    });

    const { data: sales = [] } = useQuery({
        queryKey: ['sales'],
        queryFn: async () => {
            const res = await api.get('/v2/sales/');
            return res.data;
        }
    });

    const { data: dossiers = [] } = useQuery({
        queryKey: ['mmg-dossiers'],
        queryFn: async () => {
            const res = await api.get('/v2/mmg/');
            return res.data;
        }
    });

    const normalize = (value) => String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const formatDate = (value) => value ? new Date(value).toLocaleDateString('fr-FR') : '-';
    const getClientSignals = (clientId) => segmentationQuery.data?.client_signals?.[clientId] || segmentationQuery.data?.client_signals?.[String(clientId)] || null;

    useEffect(() => {
        try {
            const saved = JSON.parse(localStorage.getItem(CRM_FILTER_STORAGE_KEY) || '{}');
            if (saved.searchTerm) setSearchTerm(saved.searchTerm);
            if (saved.segmentFilter) setSegmentFilter(saved.segmentFilter);
            if (saved.tagFilter) setTagFilter(saved.tagFilter);
            if (saved.commercialStatusFilter) setCommercialStatusFilter(saved.commercialStatusFilter);
        } catch {
            localStorage.removeItem(CRM_FILTER_STORAGE_KEY);
        }
    }, []);

    useEffect(() => {
        localStorage.setItem(CRM_FILTER_STORAGE_KEY, JSON.stringify({
            searchTerm,
            segmentFilter,
            tagFilter,
            commercialStatusFilter,
        }));
    }, [searchTerm, segmentFilter, tagFilter, commercialStatusFilter]);

    const statusLabel = (sale) => {
        if (sale.status === 'DRAFT') return 'À envoyer';
        if (sale.status === 'SENT') return 'En attente signature';
        if (sale.status === 'VALIDATED') return 'Signé';
        if (sale.status === 'DELIVERED') return 'Livré';
        if (sale.status === 'CANCELLED') return 'Annulé';
        if (sale.status === 'IN_DESIGN') return 'Bureau études';
        if (sale.status === 'READY_FOR_PROD') return 'Prêt atelier';
        if (sale.status === 'IN_PRODUCTION') return 'En production';
        return sale.status || 'Inconnu';
    };

    const createQuoteForClient = () => {
        if (!selectedClient) return;
        setShowProposalStarter(true);
    };

    const openSale = (saleId) => {
        navigate(`/sales/${saleId}?from=crm`);
    };

    const updateClientDraft = (field, value) => {
        setClientDraft(prev => ({ ...prev, [field]: value }));
    };

    const resetClientDraft = () => {
        setClientDraft({
            name: '',
            contact_name: '',
            phone: '',
            email: '',
            address: '',
            tax_id: '',
            customer_type: 'B2B',
            segment: '',
            tags: '',
        });
    };

    const createClient = async () => {
        if (!clientDraft.name.trim()) {
            return alert('Renseignez le nom du client.');
        }
        setIsCreatingClient(true);
        try {
            const payload = {
                name: clientDraft.name.trim(),
                contact_name: clientDraft.contact_name.trim() || null,
                phone: clientDraft.phone.trim() || null,
                email: clientDraft.email.trim() || null,
                address: clientDraft.address.trim() || null,
                tax_id: clientDraft.tax_id.trim() || null,
                customer_type: clientDraft.customer_type,
                segment: clientDraft.segment.trim() || null,
                tags: clientDraft.tags
                    .split(',')
                    .map(tag => tag.trim())
                    .filter(Boolean),
                is_active: true,
            };
            const res = await api.post('/v2/partners/clients', payload);
            await refetchClients();
            setSelectedClientId(res.data.id);
            setCrmView('clients');
            setSearchTerm('');
            setShowClientModal(false);
            resetClientDraft();
        } catch (err) {
            console.error('Create client error:', err);
            alert(err.response?.data?.detail || 'Erreur lors de la création du client.');
        } finally {
            setIsCreatingClient(false);
        }
    };

    const exportClients = async () => {
        setClientDataMessage('');
        try {
            const response = await api.get('/v2/partners/clients/export.csv', {
                responseType: 'blob',
            });
            const url = URL.createObjectURL(response.data);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'clients-crm.csv';
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            setClientDataMessage('Export clients généré.');
        } catch (error) {
            setClientDataMessage(error?.response?.data?.detail || "L'export clients a échoué.");
        }
    };

    const previewImportClients = async (file) => {
        if (!file) return;
        setIsImportingClients(true);
        setClientDataMessage('');
        setImportPreview(null);
        setPendingImportFile(file);
        try {
            const formData = new FormData();
            formData.append('file', file);
            const response = await api.post('/v2/partners/clients/import/preview', formData, {
                params: { update_existing: importUpdateExisting },
            });
            const result = response.data;
            setImportPreview(result);
            setClientDataMessage(
                `Prévisualisation : ${result.created} création(s), ${result.updated} mise(s) à jour, ${result.skipped} doublon(s) ignoré(s), ${result.rejected || 0} rejet(s).`,
            );
        } catch (error) {
            setPendingImportFile(null);
            setClientDataMessage(error?.response?.data?.detail || "La prévisualisation de l'import clients a échoué.");
        } finally {
            setIsImportingClients(false);
        }
    };

    const applyClientImport = async () => {
        if (!pendingImportFile) return;
        setIsImportingClients(true);
        setClientDataMessage('');
        try {
            const formData = new FormData();
            formData.append('file', pendingImportFile);
            const response = await api.post('/v2/partners/clients/import', formData, {
                params: { update_existing: importUpdateExisting },
            });
            await refetchClients();
            const result = response.data;
            setImportPreview(result);
            setPendingImportFile(null);
            setClientDataMessage(
                `Import appliqué : ${result.created} créé(s), ${result.updated} mis à jour, ${result.skipped} ignoré(s), ${result.rejected || 0} rejet(s).`,
            );
        } catch (error) {
            setClientDataMessage(error?.response?.data?.detail || "L'import clients a échoué.");
        } finally {
            setIsImportingClients(false);
        }
    };

    const mergeDuplicateGroup = async (group) => {
        const [target, ...sources] = group.clients || [];
        if (!target || !sources.length) return;
        if (!window.confirm(`Fusionner ${sources.length} fiche(s) dans « ${target.name} » ?`)) return;
        try {
            await api.post(`/v2/partners/clients/${target.id}/merge`, {
                source_client_ids: sources.map(client => client.id),
                confirm: true,
            });
            setSelectedClientId(target.id);
            await Promise.all([refetchClients(), duplicatesQuery.refetch()]);
            setClientDataMessage('Fiches clients fusionnées avec leur historique.');
        } catch (error) {
            setClientDataMessage(error?.response?.data?.detail || 'La fusion a échoué.');
        }
    };

    const isRecipeCleanupClient = (client) => {
        const markers = [
            client?.name,
            client?.contact_name,
            client?.email,
            client?.phone,
            client?.tax_id,
            client?.segment,
            ...(client?.tags || []),
        ].filter(Boolean).join(' ').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        if (client?.name?.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').startsWith('recette ')) {
            return true;
        }
        return [
            'recette doublon',
            'recette crm',
            'fixture',
            'test a supprimer',
            'a supprimer',
        ].some(marker => markers.includes(marker));
    };

    const deleteRecipeClient = async (client) => {
        if (!client?.id) return;
        if (!window.confirm(`Supprimer définitivement la fiche de recette « ${client.name} » et ses contacts ?`)) return;
        setClientDataMessage('');
        try {
            await api.delete(`/v2/partners/clients/${client.id}/recipe-fixture`);
            await Promise.all([refetchClients(), duplicatesQuery.refetch()]);
            setSelectedClientId(null);
            setClientDataMessage(`Fiche de recette supprimée : ${client.name}.`);
        } catch (error) {
            setClientDataMessage(error?.response?.data?.detail || "La suppression de la fiche de recette a échoué.");
        }
    };

    const clientSegments = useMemo(() => (
        [...new Set(clients.map(client => client.segment).filter(Boolean))].sort()
    ), [clients]);
    const clientTags = useMemo(() => (
        (segmentationQuery.data?.tags || []).map(item => item.tag)
    ), [segmentationQuery.data]);

    const filteredClients = useMemo(() => {
        const needle = normalize(searchTerm);
        return clients
            .filter(client => client.is_active !== false)
            .filter(client => !segmentFilter || client.segment === segmentFilter)
            .filter(client => !tagFilter || (client.tags || []).includes(tagFilter))
            .filter(client => {
                if (!commercialStatusFilter) return true;
                const statuses = getClientSignals(client.id)?.statuses || [];
                return statuses.includes(commercialStatusFilter);
            })
            .filter(client => {
                if (!needle) return true;
                return [
                    client.name,
                    client.contact_name,
                    client.phone,
                    client.email,
                    client.address,
                    client.tax_id,
                    client.segment,
                    ...(client.tags || []),
                ].some(value => normalize(value).includes(needle));
            });
    }, [clients, searchTerm, segmentFilter, tagFilter, commercialStatusFilter, segmentationQuery.data]);

    const selectedClient = useMemo(() => (
        clients.find(client => client.id === selectedClientId) || filteredClients[0] || null
    ), [clients, filteredClients, selectedClientId]);

    const { data: clientSites = [], refetch: refetchClientSites } = useQuery({
        queryKey: ['client-sites', selectedClient?.id],
        enabled: Boolean(selectedClient?.id),
        queryFn: async () => {
            const response = await api.get('/v2/mmg/sites', { params: { client_id: selectedClient.id } });
            return response.data;
        },
    });

    const openSiteCreation = () => {
        setSiteDraft({
            label: clientSites.length ? `Chantier ${clientSites.length + 1}` : 'Chantier principal',
            address_line1: '',
            address_line2: '',
            postal_code: '',
            city: '',
            country: selectedClient?.country || 'FR',
            contact_name: selectedClient?.contact_name || '',
            contact_phone: selectedClient?.phone || '',
            access_instructions: '',
            is_default: clientSites.length === 0,
        });
        setShowSiteModal(true);
    };

    const createClientSite = async () => {
        if (!selectedClient?.id || !siteDraft.address_line1.trim()) {
            return alert("Renseignez l'adresse du chantier.");
        }
        setIsCreatingSite(true);
        try {
            await api.post('/v2/mmg/sites', {
                ...siteDraft,
                client_id: selectedClient.id,
                label: siteDraft.label.trim() || 'Chantier',
                address_line1: siteDraft.address_line1.trim(),
                address_line2: siteDraft.address_line2.trim() || null,
                postal_code: siteDraft.postal_code.trim() || null,
                city: siteDraft.city.trim() || null,
                contact_name: siteDraft.contact_name.trim() || null,
                contact_phone: siteDraft.contact_phone.trim() || null,
                access_instructions: siteDraft.access_instructions.trim() || null,
            });
            await refetchClientSites();
            setShowSiteModal(false);
        } catch (requestError) {
            alert(requestError?.response?.data?.detail || 'Impossible de créer le chantier.');
        } finally {
            setIsCreatingSite(false);
        }
    };

    const startMeasureForSite = site => {
        const params = new URLSearchParams({
            source: 'SITE_VISIT',
            scope: 'SUPPLY_AND_INSTALL',
            scopeLabel: 'Par défaut : fourniture + pose',
            clientId: String(selectedClient.id),
            siteId: String(site.id),
        });
        navigate(`/measure-missions/new?${params.toString()}`);
    };

    const startMeasureForOpportunity = opportunity => {
        const linkedSiteId = opportunity.site_address_id
            || opportunity.site_id
            || opportunity.client_site_id
            || clientSites.find(site => site.is_default)?.id
            || (clientSites.length === 1 ? clientSites[0].id : null);
        const params = new URLSearchParams({
            source: 'SITE_VISIT',
            scope: 'SUPPLY_AND_INSTALL',
            clientId: String(selectedClient.id),
            opportunityId: String(opportunity.id),
        });
        if (linkedSiteId) params.set('siteId', String(linkedSiteId));
        navigate(`/measure-missions/new?${params.toString()}`);
    };

    const clientSales = useMemo(() => {
        if (!selectedClient) return [];
        const clientKeys = [
            selectedClient.name,
            selectedClient.phone,
            selectedClient.email,
        ].map(normalize).filter(Boolean);
        return sales.filter(sale => {
            const saleKeys = [
                sale.client_name,
                sale.client_contact,
                sale.client_email,
            ].map(normalize).filter(Boolean);
            return clientKeys.some(key => saleKeys.includes(key));
        });
    }, [sales, selectedClient]);

    const totals = useMemo(() => {
        return clientSales.reduce((acc, sale) => {
            const amount = saleAmount(sale);
            if (isPresalesStatus(sale.status)) {
                acc.presales += 1;
                acc.presalesAmount += amount;
            } else {
                acc.orders += 1;
                acc.orderAmount += amount;
            }
            acc.invoices += (sale.invoices || []).filter(invoice => !String(invoice.reference || '').startsWith('AV-')).length;
            acc.deliveryNotes += (sale.delivery_notes || []).length;
            return acc;
        }, { presales: 0, presalesAmount: 0, orders: 0, orderAmount: 0, invoices: 0, deliveryNotes: 0 });
    }, [clientSales]);

    const presalesQuotes = useMemo(() => (
        clientSales
            .filter(sale => isPresalesStatus(sale.status))
            .sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0))
    ), [clientSales]);

    const executionOrders = useMemo(() => (
        clientSales
            .filter(sale => !isPresalesStatus(sale.status))
            .sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0))
    ), [clientSales]);

    const clientDossiers = useMemo(() => {
        if (!selectedClient) return [];
        const clientKeys = [
            selectedClient.name,
            selectedClient.phone,
            selectedClient.email,
        ].map(normalize).filter(Boolean);
        return dossiers
            .filter(dossier => {
                const dossierKeys = [
                    dossier.client_name,
                    dossier.client_contact,
                    dossier.client_email,
                ].map(normalize).filter(Boolean);
                return clientKeys.some(key => dossierKeys.includes(key));
            })
            .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    }, [dossiers, selectedClient]);

    const activePresalesQuotes = useMemo(() => (
        presalesQuotes.filter(sale => isActivePresalesStatus(sale.status))
    ), [presalesQuotes]);

    const openMeasureDossiers = useMemo(() => (
        clientDossiers.filter(dossier => dossier.status !== 'VALIDATED')
    ), [clientDossiers]);

    const nextActions = useMemo(() => {
        const actions = [];
        const draft = activePresalesQuotes.find(sale => sale.status === 'DRAFT');
        const sent = activePresalesQuotes.find(sale => sale.status === 'SENT');
        const pendingMeasure = openMeasureDossiers[0];

        if (selectedClient && (!selectedClient.phone || !selectedClient.email)) {
            actions.push({
                key: 'complete-contact',
                tone: 'slate',
                title: 'Compléter la fiche client',
                detail: 'Téléphone ou email manquant pour les relances.',
                onClick: () => setShowClientModal(true),
            });
        }

        if (draft) {
            actions.push({
                key: `draft-${draft.id}`,
                tone: 'blue',
                title: 'Envoyer la proposition',
                detail: `${draft.reference} · ${formatMoney(saleAmount(draft))}`,
                saleId: draft.id,
            });
        }
        if (sent) {
            actions.push({
                key: `sent-${sent.id}`,
                tone: 'amber',
                title: 'Relancer la signature',
                detail: `${sent.reference} · envoyé le ${formatDate(sent.updated_at || sent.created_at)}`,
                saleId: sent.id,
            });
        }
        if (pendingMeasure) {
            actions.push({
                key: `measure-${pendingMeasure.id}`,
                tone: 'emerald',
                title: 'Traiter la prise de côte',
                detail: `${pendingMeasure.reference} · ${formatDate(pendingMeasure.created_at)}`,
                onClick: () => setCrmView('measures'),
            });
        }
        if (actions.length === 0 && selectedClient) {
            actions.push({
                key: 'new-proposal',
                tone: 'slate',
                title: 'Créer une nouvelle proposition',
                detail: 'Aucun devis ouvert côté avant-vente.',
                onClick: createQuoteForClient,
            });
        }
        return actions.slice(0, 3);
    }, [activePresalesQuotes, selectedClient, openMeasureDossiers]);

    const commerceOverview = useMemo(() => {
        const draftQuotes = sales.filter(sale => sale.status === 'DRAFT');
        const sentQuotes = sales.filter(sale => sale.status === 'SENT');
        const signedOrders = sales.filter(sale => !isPresalesStatus(sale.status));
        const openMeasures = dossiers.filter(dossier => dossier.status !== 'VALIDATED');
        const clientSignals = segmentationQuery.data?.client_signals || {};
        const followUpClients = Object.values(clientSignals).filter(signal => (signal.statuses || []).includes('to_follow_up')).length;
        const withoutActionClients = Object.values(clientSignals).filter(signal => (signal.statuses || []).includes('missing_next_action')).length;
        return {
            clients: clients.filter(client => client.is_active !== false).length,
            draftQuotes: draftQuotes.length,
            sentQuotes: sentQuotes.length,
            signedOrders: signedOrders.length,
            openMeasures: openMeasures.length,
            followUpClients,
            withoutActionClients,
            signedAmount: signedOrders.reduce((sum, sale) => sum + saleAmount(sale), 0),
        };
    }, [clients, sales, dossiers, segmentationQuery.data]);

    const sellerQueue = useMemo(() => ([
        {
            key: 'follow-up',
            label: 'Relances à faire',
            value: commerceOverview.followUpClients,
            detail: 'Clients avec relance ou décision attendue.',
            tone: 'red',
            view: 'cockpit',
        },
        {
            key: 'quotes',
            label: 'Devis envoyés',
            value: commerceOverview.sentQuotes,
            detail: 'À suivre jusqu’à signature ou relance.',
            tone: 'blue',
            view: 'pipeline',
        },
        {
            key: 'missing-action',
            label: 'Sans prochaine action',
            value: commerceOverview.withoutActionClients,
            detail: 'À reprendre pour éviter les opportunités dormantes.',
            tone: 'amber',
            view: 'cockpit',
        },
        {
            key: 'measures',
            label: 'Métrés ouverts',
            value: commerceOverview.openMeasures,
            detail: 'À contrôler avec BE avant proposition finale.',
            tone: 'emerald',
            view: 'measures',
        },
    ]), [commerceOverview]);

    const clientTimeline = useMemo(() => {
        const events = [];
        clientSales.forEach(sale => {
            events.push({
                key: `sale-${sale.id}`,
                date: sale.created_at,
                label: isPresalesStatus(sale.status) ? 'Devis avant-vente' : 'Commande',
                detail: `${sale.reference} · ${statusLabel(sale)} · ${formatMoney(saleAmount(sale))}`,
                tone: isPresalesStatus(sale.status) ? 'blue' : 'emerald',
                saleId: sale.id,
            });
            if (sale.signed_at) {
                events.push({
                    key: `signed-${sale.id}`,
                    date: sale.signed_at,
                    label: 'Signature client',
                    detail: sale.reference,
                    tone: 'emerald',
                    saleId: sale.id,
                });
            }
            (sale.invoices || []).forEach(invoice => {
                events.push({
                    key: `invoice-${invoice.id}`,
                    date: invoice.created_at,
                    label: String(invoice.reference || '').startsWith('AV-') ? 'Avoir' : 'Facture',
                    detail: `${invoice.reference} · ${formatMoney(invoice.total_ttc || invoice.total_ht || 0)}`,
                    tone: String(invoice.reference || '').startsWith('AV-') ? 'red' : 'indigo',
                    saleId: sale.id,
                });
            });
            (sale.delivery_notes || []).forEach(note => {
                events.push({
                    key: `delivery-${note.id}`,
                    date: note.signed_at || note.created_at,
                    label: note.status === 'RETURNED' ? 'Retour client' : 'Livraison',
                    detail: `${note.reference} · ${note.status || 'BL'}`,
                    tone: note.status === 'RETURNED' ? 'red' : 'teal',
                    saleId: sale.id,
                });
            });
        });
        return events
            .filter(event => event.date)
            .sort((a, b) => new Date(b.date) - new Date(a.date))
            .slice(0, 8);
    }, [clientSales]);

    const statusClassName = (status) => {
        if (status === 'DRAFT') return 'border-slate-200 bg-slate-50 text-slate-600';
        if (status === 'SENT') return 'border-blue-200 bg-blue-50 text-blue-700';
        if (status === 'CANCELLED') return 'border-red-200 bg-red-50 text-red-700';
        if (status === 'VALIDATED') return 'border-emerald-200 bg-emerald-50 text-emerald-700';
        if (['IN_DESIGN', 'READY_FOR_PROD'].includes(status)) return 'border-amber-200 bg-amber-50 text-amber-700';
        if (status === 'IN_PRODUCTION') return 'border-orange-200 bg-orange-50 text-orange-700';
        if (status === 'DELIVERED') return 'border-teal-200 bg-teal-50 text-teal-700';
        return 'border-slate-200 bg-slate-50 text-slate-600';
    };

    const navItems = [
        { key: 'home', label: 'Parcours vendeur', group: 'Accueil', icon: ArrowRight },
        { key: 'cockpit', label: 'Pilotage commercial', group: 'Décider', icon: BellRing },
        { key: 'pipeline', label: 'Pipeline', group: 'Suivre', icon: ClipboardList },
        { key: 'clients', label: 'Clients & contacts', group: 'Gérer', icon: Users },
        { key: 'measures', label: 'Métrés / BE', group: 'Préparer', icon: Wrench },
    ];

    return (
        <div className="w-full h-[calc(100vh-80px)] font-sans flex flex-col overflow-hidden bg-slate-50 border-y border-slate-200/80 animate-fade-in">
            <div className="shrink-0 border-b border-slate-200 bg-white px-5 py-5 lg:px-8">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                    <div>
                        <div className="inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-blue-700">
                            <Users className="h-4 w-4" />
                            Commerce & ventes
                        </div>
                        <h2 className="mt-3 text-3xl font-black tracking-tight text-slate-950">Commencer par la prochaine action commerciale.</h2>
                        <p className="mt-2 max-w-3xl text-sm font-bold text-slate-500">
                            Un parcours simple pour qualifier, relancer, préparer le devis, puis passer en commande signée.
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <button
                            onClick={() => setShowClientModal(true)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-700 hover:bg-slate-50"
                        >
                            <Users className="h-4 w-4" />
                            Nouveau client
                        </button>
                        <button
                            onClick={createQuoteForClient}
                            disabled={!selectedClient}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none"
                        >
                            <Plus className="h-4 w-4" />
                            Préparer un devis
                        </button>
                        <button
                            onClick={planMeasureForClient}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-black text-white shadow-lg shadow-emerald-500/20 hover:bg-emerald-500"
                        >
                            <ClipboardList className="h-4 w-4" />
                            Lancer un métré
                        </button>
                    </div>
                </div>
                <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200 bg-slate-50/80 p-2">
                    <div className="flex min-w-max items-center gap-2">
                        {navItems.map(item => {
                            const Icon = item.icon;
                            const selected = crmView === item.key;
                            return (
                                <button
                                    key={item.key}
                                    type="button"
                                    onClick={() => setCrmView(item.key)}
                                    className={`flex items-center gap-3 rounded-xl px-4 py-3 text-left transition-all ${selected ? 'bg-slate-950 text-white shadow-sm' : 'bg-white text-slate-600 hover:bg-blue-50 hover:text-blue-700'}`}
                                >
                                    <Icon className={`h-4 w-4 ${selected ? 'text-white' : 'text-slate-400'}`} />
                                    <span>
                                        <span className={`block text-[9px] font-black uppercase tracking-widest ${selected ? 'text-blue-100' : 'text-slate-400'}`}>{item.group}</span>
                                        <span className="block text-sm font-black">{item.label}</span>
                                    </span>
                                </button>
                            );
                        })}
                    </div>
                </div>
            </div>

            {crmView === 'home' && (
                <div className="flex-1 overflow-y-auto p-5 lg:p-8">
                    <section className="rounded-3xl border border-blue-100 bg-gradient-to-br from-blue-50 via-white to-emerald-50 p-5 shadow-sm lg:p-6">
                        <div className="flex flex-col gap-6 xl:flex-row xl:items-stretch">
                            <div className="flex-1">
                                <p className="text-[10px] font-black uppercase tracking-[0.24em] text-blue-600">Parcours vendeur</p>
                                <h3 className="mt-3 text-3xl font-black tracking-tight text-slate-950">À traiter maintenant</h3>
                                <p className="mt-2 max-w-2xl text-sm font-bold leading-6 text-slate-600">
                                    Le commercial part des relances et devis ouverts. Les vues de gestion restent disponibles, mais ne prennent plus toute la place.
                                </p>
                                <div className="mt-5 grid gap-3 md:grid-cols-4">
                                    <JourneyStep number="1" title="Qualifier" detail="Client, besoin, budget, chantier." />
                                    <JourneyStep number="2" title="Métrer" detail="Cotes client ou rendez-vous terrain." />
                                    <JourneyStep number="3" title="Deviser" detail="Préparer, envoyer, suivre." />
                                    <JourneyStep number="4" title="Signer" detail="Commande puis passage production." />
                                </div>
                            </div>
                            <div className="rounded-2xl border border-white/80 bg-white p-5 shadow-sm xl:w-80">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Portefeuille</p>
                                <p className="mt-3 text-4xl font-black text-slate-950">{commerceOverview.clients}</p>
                                <p className="text-xs font-black uppercase tracking-widest text-slate-400">client(s) actifs</p>
                                <div className="mt-4 grid grid-cols-2 gap-2">
                                    <MiniKpi label="Devis envoyés" value={commerceOverview.sentQuotes} />
                                    <MiniKpi label="CA signé" value={formatMoney(commerceOverview.signedAmount)} />
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
                        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">File commerciale</p>
                                    <h3 className="mt-1 text-2xl font-black text-slate-950">Prochaines priorités visibles</h3>
                                </div>
                                <button onClick={() => setCrmView('cockpit')} className="hidden rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-black text-white hover:bg-slate-800 md:inline-flex">
                                    Ouvrir le pilotage
                                </button>
                            </div>
                            <div className="mt-5 grid gap-3 md:grid-cols-2">
                                {sellerQueue.map(item => (
                                    <SellerQueueCard key={item.key} item={item} onOpen={() => setCrmView(item.view)} />
                                ))}
                            </div>
                        </div>
                        <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Actions rapides</p>
                            <div className="mt-4 space-y-3">
                                <QuickAction icon={Users} title="Créer une fiche client" detail="Prospect, contact, segment." onClick={() => setShowClientModal(true)} />
                                <QuickAction icon={Plus} title="Préparer un devis" detail={selectedClient ? selectedClient.name : 'Sélectionner un client d’abord.'} onClick={createQuoteForClient} disabled={!selectedClient} />
                                <QuickAction icon={ClipboardList} title="Lancer un métré" detail="Chantier, plans ou saisie agence." onClick={planMeasureForClient} />
                                <QuickAction icon={Search} title="Retrouver un client" detail="Liste, filtres, contacts, doublons." onClick={() => setCrmView('clients')} />
                            </div>
                        </div>
                    </section>

                    <section className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <WorkspaceCard icon={BellRing} eyebrow="Décider" title="Pilotage commercial" detail="KPIs, relances, portefeuille et attention commerciale." onOpen={() => setCrmView('cockpit')} />
                        <WorkspaceCard icon={ClipboardList} eyebrow="Suivre" title="Pipeline avant-vente" detail="Opportunités, devis envoyés, signatures et pertes." onOpen={() => setCrmView('pipeline')} />
                        <WorkspaceCard icon={Users} eyebrow="Gérer" title="Clients & contacts" detail="Fiches, contacts multiples, imports, exports, doublons." onOpen={() => setCrmView('clients')} />
                        <WorkspaceCard icon={Wrench} eyebrow="Préparer" title="Métrés / BE" detail="Prise de cotes, contrôle BE et liaison au devis." onOpen={() => setCrmView('measures')} />
                    </section>
                </div>
            )}

            {crmView === 'cockpit' && (
                <CRMCockpit
                    onOpenClient={clientId => {
                        setSelectedClientId(clientId);
                        setCrmView('clients');
                    }}
                    onOpenMeasure={missionId => navigate(`/measure-missions/${missionId}`)}
                />
            )}

            {crmView === 'pipeline' && (
                <CRMOpportunityPipeline
                    clients={clients}
                    onOpenClient={clientId => {
                        setSelectedClientId(clientId);
                        setCrmView('clients');
                    }}
                    onOpenOrder={saleOrderId => openSale(saleOrderId)}
                    onPlanMeasure={(opportunity, source = 'SITE_VISIT', missionId = null) => {
                        if (missionId) {
                            navigate(`/measure-missions/${missionId}`);
                            return;
                        }
                        const params = new URLSearchParams({
                            source,
                            scope: source === 'SITE_VISIT' ? 'SUPPLY_AND_INSTALL' : 'SUPPLY_ONLY',
                            clientId: String(opportunity.client_id),
                            opportunityId: String(opportunity.id),
                        });
                        if (opportunity.site_address_id) params.set('siteId', String(opportunity.site_address_id));
                        navigate(`/measure-missions/new?${params.toString()}`);
                    }}
                />
            )}

            {crmView === 'measures' && (
                <div className="flex-1 min-h-0 overflow-y-auto">
                    <MeasureMissionBoard />
                </div>
            )}

            {crmView === 'clients' && (
                <div className="grid flex-1 min-h-0 grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)]">
                    <aside className="flex max-h-56 min-h-0 flex-col border-b border-slate-200 bg-white xl:max-h-none xl:border-b-0 xl:border-r">
                        <div className="border-b border-slate-200 p-4">
                            <div className="relative">
                                <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
                                <input
                                    value={searchTerm}
                                    onChange={event => setSearchTerm(event.target.value)}
                                    placeholder="Client, téléphone..."
                                    className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-3 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                                />
                            </div>
	                            <select
	                                value={segmentFilter}
	                                onChange={event => setSegmentFilter(event.target.value)}
	                                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
	                            >
	                                <option value="">Tous les segments</option>
	                                {clientSegments.map(segment => <option key={segment} value={segment}>{segment}</option>)}
	                            </select>
	                            <div className="mt-2 grid grid-cols-2 gap-2">
	                                <select
	                                    value={tagFilter}
	                                    onChange={event => setTagFilter(event.target.value)}
	                                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
	                                    aria-label="Filtrer par tag"
	                                >
	                                    <option value="">Tous tags</option>
	                                    {clientTags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
	                                </select>
	                                <select
	                                    value={commercialStatusFilter}
	                                    onChange={event => setCommercialStatusFilter(event.target.value)}
	                                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
	                                    aria-label="Filtrer par statut commercial"
	                                >
	                                    {COMMERCIAL_STATUS_OPTIONS.map(option => (
	                                        <option key={option.value || 'all'} value={option.value}>{option.label}</option>
	                                    ))}
	                                </select>
	                            </div>
	                            {(searchTerm || segmentFilter || tagFilter || commercialStatusFilter) && (
	                                <button
	                                    type="button"
	                                    onClick={() => {
	                                        setSearchTerm('');
	                                        setSegmentFilter('');
	                                        setTagFilter('');
	                                        setCommercialStatusFilter('');
	                                    }}
	                                    className="mt-2 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[10px] font-black uppercase tracking-wide text-slate-500 hover:bg-white"
	                                >
	                                    Réinitialiser les filtres
	                                </button>
	                            )}
	                            {segmentationQuery.data?.segments?.length ? (
	                                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
	                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">Segments actifs</p>
	                                    <div className="mt-2 space-y-1.5">
	                                        {segmentationQuery.data.segments.slice(0, 3).map(segment => (
	                                            <button
	                                                key={segment.segment}
	                                                type="button"
	                                                onClick={() => setSegmentFilter(segment.segment === 'Sans segment' ? '' : segment.segment)}
	                                                className="flex w-full items-center justify-between rounded-lg bg-white px-2 py-1.5 text-left text-[10px] font-bold text-slate-600 hover:bg-blue-50"
	                                            >
	                                                <span className="truncate">{segment.segment}</span>
	                                                <span className="font-black text-slate-900">{segment.clients}</span>
	                                            </button>
	                                        ))}
	                                    </div>
	                                </div>
	                            ) : null}
	                            <button
	                                onClick={() => setShowClientModal(true)}
	                                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-black text-white hover:bg-slate-800"
                            >
                                <Plus className="h-4 w-4" />
                                Nouveau client
                            </button>
                            <div className="mt-2 grid grid-cols-3 gap-1.5">
                                <label className="inline-flex cursor-pointer items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] font-black text-slate-600 hover:bg-slate-50">
                                    <Upload className="h-3.5 w-3.5" />
                                    {isImportingClients ? 'Import…' : 'Importer'}
	                                    <input
	                                        type="file"
	                                        accept=".csv,text/csv"
	                                        className="hidden"
	                                        disabled={isImportingClients}
	                                        onChange={event => {
	                                            previewImportClients(event.target.files?.[0]);
	                                            event.target.value = '';
	                                        }}
	                                    />
	                                </label>
                                <button
                                    onClick={exportClients}
                                    className="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-2 text-[10px] font-black text-slate-600 hover:bg-slate-50"
                                >
                                    <Download className="h-3.5 w-3.5" />
                                    Exporter
                                </button>
                                <button
                                    onClick={() => setShowDuplicates(true)}
                                    className="inline-flex items-center justify-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2 py-2 text-[10px] font-black text-amber-800 hover:bg-amber-100"
                                >
                                    <Merge className="h-3.5 w-3.5" />
                                    Doublons
                                </button>
                            </div>
	                            {clientDataMessage && (
	                                <p className="mt-2 text-[10px] font-bold leading-relaxed text-slate-500">{clientDataMessage}</p>
	                            )}
	                            {importPreview && (
	                                <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50/70 p-3 text-[10px] font-bold text-blue-950">
	                                    <div className="flex items-start justify-between gap-2">
	                                        <div>
	                                            <p className="font-black uppercase tracking-wide text-blue-700">Contrôle import CRM</p>
	                                            <p className="mt-1">
	                                                {importPreview.created} création(s) · {importPreview.updated} mise(s) à jour · {importPreview.skipped} doublon(s) · {importPreview.rejected || 0} rejet(s)
	                                            </p>
	                                        </div>
	                                        {pendingImportFile && (
	                                            <button
	                                                type="button"
	                                                onClick={applyClientImport}
	                                                disabled={isImportingClients}
	                                                className="rounded-lg bg-blue-600 px-2.5 py-1.5 font-black text-white hover:bg-blue-500 disabled:bg-blue-300"
	                                            >
	                                                Appliquer
	                                            </button>
	                                        )}
	                                    </div>
	                                    <label className="mt-2 flex items-center gap-2 text-blue-800">
	                                        <input
	                                            type="checkbox"
	                                            checked={importUpdateExisting}
	                                            onChange={event => {
	                                                setImportUpdateExisting(event.target.checked);
	                                                setImportPreview(null);
	                                                setPendingImportFile(null);
	                                                setClientDataMessage('Choix modifié : relancez la prévisualisation du fichier.');
	                                            }}
	                                        />
	                                        Mettre à jour les doublons détectés
	                                    </label>
	                                    <div className="mt-2 max-h-36 overflow-auto rounded-lg bg-white/70">
	                                        {(importPreview.rows || []).slice(0, 8).map(row => (
	                                            <div key={`${row.line}-${row.name}`} className="border-b border-blue-100 px-2 py-1 last:border-b-0">
	                                                <span className="font-black">Ligne {row.line}</span> · {row.name || 'Sans nom'} · {row.action}
	                                                {row.reasons?.length ? <span className="text-amber-700"> · {row.reasons.join(', ')}</span> : null}
	                                            </div>
	                                        ))}
	                                        {(importPreview.rows || []).length > 8 && (
	                                            <div className="px-2 py-1 text-blue-500">+ {(importPreview.rows || []).length - 8} ligne(s) supplémentaire(s)</div>
	                                        )}
	                                    </div>
	                                </div>
	                            )}
	                        </div>
                        <div className="flex-1 overflow-auto p-3">
                            {filteredClients.length ? (
                                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-1">
                                    {filteredClients.map(client => {
                                        const isSelected = selectedClient?.id === client.id;
                                        return (
                                            <button
                                                key={client.id}
                                                onClick={() => setSelectedClientId(client.id)}
                                                className={`min-w-0 border-l-4 px-3 py-3 text-left transition-colors ${isSelected ? 'border-blue-600 bg-blue-50' : 'border-transparent hover:bg-slate-50'}`}
                                            >
                                                <p className="truncate text-sm font-black text-slate-900">{client.name}</p>
                                                <p className="mt-1 truncate text-xs font-semibold text-slate-500">{client.phone || client.email || 'Coordonnées à compléter'}</p>
	                                                {(client.segment || client.tags?.length) && (
	                                                    <p className="mt-1 truncate text-[9px] font-black uppercase tracking-wide text-blue-600">
	                                                        {[client.segment, ...(client.tags || [])].filter(Boolean).join(' · ')}
	                                                    </p>
	                                                )}
	                                                <div className="mt-2 flex flex-wrap gap-1">
	                                                    {(getClientSignals(client.id)?.statuses || ['quiet']).slice(0, 3).map(status => (
	                                                        <span
	                                                            key={status}
	                                                            className={`rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-wide ${COMMERCIAL_STATUS_STYLES[status] || COMMERCIAL_STATUS_STYLES.quiet}`}
	                                                        >
	                                                            {COMMERCIAL_STATUS_LABELS[status] || status}
	                                                        </span>
	                                                    ))}
	                                                </div>
	                                            </button>
	                                        );
	                                    })}
                                </div>
                            ) : (
                                <div className="py-8 text-center text-xs font-bold text-slate-400">Aucun client trouvé.</div>
                            )}
                        </div>
                    </aside>
                    <main className="min-h-0 overflow-y-auto bg-slate-50/40 p-4 lg:p-5">
                        {!selectedClient ? (
                            <div className="flex h-full min-h-80 flex-col items-center justify-center border border-dashed border-slate-300 bg-white p-8 text-center">
                                <Users className="h-12 w-12 text-slate-200" />
                                <p className="mt-3 text-lg font-black text-slate-700">Aucun client sélectionné</p>
                                <p className="mt-1 text-sm font-semibold text-slate-400">Sélectionnez un client ou créez une nouvelle fiche.</p>
                            </div>
                        ) : (
                            <CRMClientActionWorkspace
                                client={selectedClient}
                                sites={clientSites}
                                presalesQuotes={presalesQuotes}
                                executionOrders={executionOrders}
                                dossiers={clientDossiers}
                                totals={totals}
                                timeline={clientTimeline}
                                formatDate={formatDate}
                                formatMoney={formatMoney}
                                statusLabel={statusLabel}
                                statusClassName={statusClassName}
                                onCreateProposal={createQuoteForClient}
                                onPlanMeasure={planMeasureForClient}
                                onCreateSite={openSiteCreation}
                                onPlanMeasureForSite={startMeasureForSite}
                                onPlanMeasureForOpportunity={startMeasureForOpportunity}
                                onOpenSale={openSale}
                                onClientChanged={refetchClients}
                                canDeleteRecipeClient={userHasAnyRole(user, ['ADMIN', 'SUPER_ADMIN']) && isRecipeCleanupClient(selectedClient)}
                                onDeleteRecipeClient={() => deleteRecipeClient(selectedClient)}
                                onOpenMeasures={(dossier) => dossier?.measure_mission_id
                                    ? navigate(`/measure-missions/${dossier.measure_mission_id}`)
                                    : setCrmView('measures')}
                            />
                        )}
                    </main>
                </div>
            )}

            {false && crmView === 'clients' && (
            <div className="grid grid-cols-[360px_1fr] flex-1 min-h-0">
                <aside className="bg-white border-r border-slate-200 flex flex-col min-h-0">
                    <div className="p-5 border-b border-slate-200">
                        <div className="relative">
                            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                            <input
                                value={searchTerm}
                                onChange={event => setSearchTerm(event.target.value)}
                                placeholder="Rechercher client, téléphone..."
                                className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                        </div>
                        <button
                            onClick={() => setShowClientModal(true)}
                            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-black text-white hover:bg-slate-800"
                        >
                            <Plus className="w-4 h-4" />
                            Nouveau client
                        </button>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-2">
                        {filteredClients.map(client => {
                            const isSelected = selectedClient?.id === client.id;
                            return (
                                <button
                                    key={client.id}
                                    onClick={() => setSelectedClientId(client.id)}
                                    className={`w-full text-left rounded-2xl border p-4 transition-all ${isSelected ? 'border-indigo-300 bg-indigo-50 shadow-sm' : 'border-slate-200 bg-white hover:border-indigo-200 hover:bg-slate-50'}`}
                                >
                                    <div className="flex items-start gap-3">
                                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center font-black ${isSelected ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
                                            {client.name?.charAt(0)?.toUpperCase() || 'C'}
                                        </div>
                                        <div className="min-w-0">
                                            <p className="font-black text-slate-900 truncate">{client.name}</p>
                                            <p className="text-xs font-bold text-slate-500 truncate">{client.phone || client.email || 'Coordonnées à compléter'}</p>
                                        </div>
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </aside>

                <main className="min-h-0 overflow-y-auto p-6">
                    {!selectedClient ? (
                        <div className="h-full rounded-2xl border border-dashed border-slate-200 bg-white flex flex-col items-center justify-center text-center p-10">
                            <Users className="w-14 h-14 text-slate-200 mb-4" />
                            <p className="text-lg font-black text-slate-600">Aucun client sélectionné</p>
                            <p className="text-sm font-bold text-slate-400 mt-1">Sélectionnez un client dans la liste ou créez-en un nouveau.</p>
                            <button
                                onClick={() => setShowClientModal(true)}
                                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white hover:bg-blue-500"
                            >
                                <Plus className="w-4 h-4" />
                                Créer un client
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <section className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                <div className="border-b border-slate-100 bg-slate-50/70 px-6 py-4">
                                    <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-indigo-500">Cockpit client</p>
                                            <h3 className="mt-1 text-2xl font-black text-slate-900">À comprendre en 5 secondes</h3>
                                            <p className="mt-1 text-sm font-bold text-slate-500">Identité, action suivante, opportunités et historique commercial.</p>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            <button
                                                onClick={createQuoteForClient}
                                                className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-black text-white shadow-md shadow-blue-500/20 hover:bg-blue-500"
                                            >
                                                <Plus className="w-4 h-4" />
                                                Proposition
                                            </button>
                                            <button
                                                onClick={planMeasureForClient}
                                                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-black text-white shadow-md shadow-emerald-500/20 hover:bg-emerald-500"
                                            >
                                                <ClipboardList className="w-4 h-4" />
                                                Prise de côte
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                <div className="p-6 flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-indigo-500 mb-2">Identité client</p>
                                        <h3 className="text-3xl font-black text-slate-900 tracking-tight">{selectedClient.name}</h3>
                                        {selectedClient.contact_name && <p className="text-sm font-bold text-slate-500 mt-1">{selectedClient.contact_name}</p>}
                                        <div className="mt-4 flex flex-wrap items-center gap-2">
                                            {selectedClient.phone && (
                                                <a href={`tel:${selectedClient.phone}`} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-100">
                                                    <Phone className="w-4 h-4 text-blue-500" />
                                                    Appeler
                                                </a>
                                            )}
                                            {selectedClient.email && (
                                                <a href={`mailto:${selectedClient.email}`} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-100">
                                                    <Mail className="w-4 h-4 text-indigo-500" />
                                                    Écrire
                                                </a>
                                            )}
                                            <button
                                                onClick={createQuoteForClient}
                                                className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-black text-blue-700 hover:bg-blue-100"
                                            >
                                                <Plus className="w-4 h-4" />
                                                Proposition
                                            </button>
                                            <button
                                                onClick={planMeasureForClient}
                                                className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700 hover:bg-emerald-100"
                                            >
                                                <ClipboardList className="w-4 h-4" />
                                                Prise de côte
                                            </button>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-3 w-full xl:w-auto xl:grid-cols-4">
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Avant-vente</p>
                                            <p className="text-2xl font-black text-slate-900">{totals.presales}</p>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Commandes</p>
                                            <p className="text-2xl font-black text-slate-900">{totals.orders}</p>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">CA signé HT</p>
                                            <p className="text-2xl font-black text-slate-900">{formatMoney(totals.orderAmount)}</p>
                                        </div>
                                        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Métrés</p>
                                            <p className="text-2xl font-black text-emerald-900">{clientDossiers.length}</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 px-6 pb-6">
                                    <InfoLine icon={Phone} label="Téléphone" value={selectedClient.phone} />
                                    <InfoLine icon={Mail} label="Email" value={selectedClient.email} />
                                    <InfoLine icon={MapPin} label="Adresse de facturation" value={selectedClient.address} />
                                </div>
                            </section>

                            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                                <div className="flex flex-col gap-3 border-b border-slate-100 bg-slate-50/70 px-6 py-4 md:flex-row md:items-center md:justify-between">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Chantiers du client</p>
                                        <p className="mt-1 text-sm font-bold text-slate-600">
                                            Chaque adresse possède son propre numéro et peut lancer directement un métré.
                                        </p>
                                    </div>
                                    <button
                                        onClick={openSiteCreation}
                                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-black text-white hover:bg-slate-800"
                                    >
                                        <Plus className="h-4 w-4" />
                                        Nouveau chantier
                                    </button>
                                </div>
                                {clientSites.length ? (
                                    <div className="divide-y divide-slate-100">
                                        {clientSites.map(site => (
                                            <div key={site.id} className="flex flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
                                                <div className="min-w-0">
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="font-mono text-xs font-black text-emerald-700">{site.reference}</span>
                                                        <span className="text-sm font-black text-slate-900">{site.label}</span>
                                                        {site.is_default && (
                                                            <span className="rounded-md bg-blue-50 px-2 py-1 text-[9px] font-black uppercase text-blue-700">Principal</span>
                                                        )}
                                                    </div>
                                                    <p className="mt-1 text-sm font-bold text-slate-600">
                                                        {[site.address_line1, site.address_line2, [site.postal_code, site.city].filter(Boolean).join(' '), site.country].filter(Boolean).join(', ')}
                                                    </p>
                                                    {(site.contact_name || site.access_instructions) && (
                                                        <p className="mt-1 text-xs font-semibold text-slate-400">
                                                            {[site.contact_name, site.contact_phone, site.access_instructions].filter(Boolean).join(' · ')}
                                                        </p>
                                                    )}
                                                </div>
                                                <button
                                                    onClick={() => startMeasureForSite(site)}
                                                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs font-black text-emerald-800 hover:bg-emerald-100"
                                                >
                                                    <ClipboardList className="h-4 w-4" />
                                                    Planifier un métré
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="px-6 py-8 text-center">
                                        <MapPin className="mx-auto h-8 w-8 text-slate-300" />
                                        <p className="mt-2 text-sm font-black text-slate-600">Aucun chantier enregistré pour ce client.</p>
                                        <p className="mt-1 text-xs font-bold text-slate-400">Créez l’adresse une seule fois, puis réutilisez-la dans tous les métrés et devis.</p>
                                    </div>
                                )}
                            </section>

                            <section className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_1fr] items-start">
                                <div className="space-y-6">
                                    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
                                        <div className="mb-4 flex items-center justify-between">
                                            <div>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Prochaines actions</p>
                                                <p className="text-sm font-bold text-slate-700">Ce qu'il faut faire maintenant.</p>
                                            </div>
                                            <BellRing className="w-5 h-5 text-amber-500" />
                                        </div>
                                        <div className="space-y-3">
                                            {nextActions.map(action => (
                                                <button
                                                    key={action.key}
                                                    onClick={action.onClick || (() => openSale(action.saleId))}
                                                    className={`w-full text-left rounded-2xl border p-4 hover:shadow-sm transition-all ${actionToneClass(action.tone)}`}
                                                >
                                                    <p className="text-sm font-black">{action.title}</p>
                                                    <p className="mt-1 text-xs font-bold opacity-75">{action.detail}</p>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Documents liés</p>
                                        <div className="grid grid-cols-2 gap-3">
                                            <DocMetric icon={FileText} label="Factures" value={totals.invoices} />
                                            <DocMetric icon={Truck} label="BL" value={totals.deliveryNotes} />
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                    <div className="px-5 py-4 bg-blue-50 border-b border-blue-100">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Opportunités ouvertes</p>
                                        <p className="text-sm font-bold text-blue-950">Propositions non signées et prises de côte en cours.</p>
                                    </div>
                                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 p-5 border-b border-slate-100">
                                        <PipelineStep label="Brouillons" count={presalesQuotes.filter(sale => sale.status === 'DRAFT').length} amount={formatMoney(presalesQuotes.filter(sale => sale.status === 'DRAFT').reduce((sum, sale) => sum + saleAmount(sale), 0))} tone="slate" />
                                        <PipelineStep label="Envoyés" count={presalesQuotes.filter(sale => sale.status === 'SENT').length} amount={formatMoney(presalesQuotes.filter(sale => sale.status === 'SENT').reduce((sum, sale) => sum + saleAmount(sale), 0))} tone="blue" />
                                        <PipelineStep label="Métrés ouverts" count={openMeasureDossiers.length} amount={`${clientDossiers.filter(dossier => dossier.status === 'VALIDATED').length} réalisé(s)`} tone="emerald" />
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {[...presalesQuotes, ...clientDossiers].length === 0 && (
                                            <div className="p-10 text-center">
                                                <FileText className="w-12 h-12 mx-auto text-blue-200 mb-3" />
                                                <p className="text-sm font-black text-slate-600">Aucune opportunité ouverte pour ce client.</p>
                                                <div className="mt-4 flex justify-center gap-2">
                                                    <button onClick={createQuoteForClient} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-black text-white hover:bg-blue-500">
                                                        <Plus className="w-4 h-4" />
                                                        Proposition
                                                    </button>
                                                    <button onClick={planMeasureForClient} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-black text-white hover:bg-emerald-500">
                                                        <ClipboardList className="w-4 h-4" />
                                                        Prise de côte
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                        {presalesQuotes.map(sale => (
                                            <SaleRow
                                                key={`sale-${sale.id}`}
                                                sale={sale}
                                                total={saleAmount(sale)}
                                                statusLabel={statusLabel(sale)}
                                                statusClassName={statusClassName(sale.status)}
                                                formatDate={formatDate}
                                                formatMoney={formatMoney}
                                                onOpen={() => openSale(sale.id)}
                                            />
                                        ))}
                                        {clientDossiers.map(dossier => (
                                            <DossierRow
                                                key={`dossier-${dossier.id}`}
                                                dossier={dossier}
                                                formatDate={formatDate}
                                                onOpen={() => dossier.measure_mission_id
                                                    ? navigate(`/measure-missions/${dossier.measure_mission_id}`)
                                                    : setCrmView('measures')}
                                            />
                                        ))}
                                    </div>
                                </div>
                            </section>

                            <section className="grid grid-cols-[1fr_320px] gap-6 items-start">
                                <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                    <div className="px-5 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Commandes & exécution</p>
                                            <p className="text-sm font-bold text-slate-600">Devis signés, production, livraisons et facturation.</p>
                                        </div>
                                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {executionOrders.map(sale => (
                                            <SaleRow
                                                key={sale.id}
                                                sale={sale}
                                                total={saleAmount(sale)}
                                                statusLabel={statusLabel(sale)}
                                                statusClassName={statusClassName(sale.status)}
                                                formatDate={formatDate}
                                                formatMoney={formatMoney}
                                                onOpen={() => openSale(sale.id)}
                                            />
                                        ))}
                                        {executionOrders.length === 0 && (
                                            <div className="p-10 text-center">
                                                <ClipboardList className="w-12 h-12 mx-auto text-slate-200 mb-3" />
                                                <p className="text-sm font-black text-slate-500">Aucune commande signée pour ce client.</p>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
                                    <div className="flex items-center justify-between mb-4">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Timeline client</p>
                                            <p className="text-sm font-bold text-slate-700">Derniers événements</p>
                                        </div>
                                        <CalendarClock className="w-5 h-5 text-slate-400" />
                                    </div>
                                    <div className="space-y-3">
                                        {clientTimeline.map(event => (
                                            <button
                                                key={event.key}
                                                onClick={() => openSale(event.saleId)}
                                                className="w-full grid grid-cols-[12px_1fr] gap-3 text-left group"
                                            >
                                                <span className={`mt-1.5 h-3 w-3 rounded-full ${timelineDotClass(event.tone)}`} />
                                                <span className="min-w-0 pb-3 border-b border-slate-100 group-last:border-b-0">
                                                    <span className="block text-xs font-black text-slate-900">{event.label}</span>
                                                    <span className="block text-xs font-bold text-slate-500 truncate">{event.detail}</span>
                                                    <span className="block mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">{formatDate(event.date)}</span>
                                                </span>
                                            </button>
                                        ))}
                                        {clientTimeline.length === 0 && (
                                            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-center">
                                                <CalendarClock className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                                                <p className="text-xs font-black text-slate-500">Aucun historique commercial.</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </section>
                        </div>
                    )}
                </main>
            </div>
            )}

            {showSiteModal && selectedClient && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
                    <div className="w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
                        <div className="flex items-start justify-between bg-slate-900 px-6 py-5 text-white">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-300">Nouveau chantier client</p>
                                <h3 className="mt-2 text-2xl font-black">{selectedClient.name}</h3>
                                <p className="mt-1 text-sm font-bold text-slate-300">Le numéro de chantier sera généré automatiquement.</p>
                            </div>
                            <button onClick={() => setShowSiteModal(false)} className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <div className="grid gap-4 p-6 md:grid-cols-6">
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Nom du chantier</span>
                                <input value={siteDraft.label} onChange={event => setSiteDraft(current => ({ ...current, label: event.target.value }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-4">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Adresse *</span>
                                <div className="mt-2 flex gap-2">
                                    <input value={siteDraft.address_line1} onChange={event => setSiteDraft(current => ({ ...current, address_line1: event.target.value }))} placeholder="Numéro et voie" className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                                    {selectedClient.address && (
                                        <button
                                            type="button"
                                            onClick={() => setSiteDraft(current => ({ ...current, address_line1: selectedClient.address }))}
                                            className="shrink-0 rounded-xl border border-slate-200 bg-white px-3 text-xs font-black text-slate-600 hover:bg-slate-50"
                                        >
                                            Adresse client
                                        </button>
                                    )}
                                </div>
                            </label>
                            <label className="md:col-span-3">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Complément</span>
                                <input value={siteDraft.address_line2} onChange={event => setSiteDraft(current => ({ ...current, address_line2: event.target.value }))} placeholder="Bâtiment, étage, porte..." className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-1">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Code postal</span>
                                <input value={siteDraft.postal_code} onChange={event => setSiteDraft(current => ({ ...current, postal_code: event.target.value }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Ville</span>
                                <input value={siteDraft.city} onChange={event => setSiteDraft(current => ({ ...current, city: event.target.value }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Contact sur place</span>
                                <input value={siteDraft.contact_name} onChange={event => setSiteDraft(current => ({ ...current, contact_name: event.target.value }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Téléphone chantier</span>
                                <input value={siteDraft.contact_phone} onChange={event => setSiteDraft(current => ({ ...current, contact_phone: event.target.value }))} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Pays</span>
                                <input value={siteDraft.country} onChange={event => setSiteDraft(current => ({ ...current, country: event.target.value.toUpperCase() }))} maxLength={2} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold uppercase outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-6">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Accès et contraintes</span>
                                <textarea value={siteDraft.access_instructions} onChange={event => setSiteDraft(current => ({ ...current, access_instructions: event.target.value }))} placeholder="Accès, stationnement, étage, horaires, personne à prévenir..." className="mt-2 min-h-24 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-emerald-500" />
                            </label>
                            <label className="md:col-span-6 flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-black text-slate-700">
                                <input type="checkbox" checked={siteDraft.is_default} onChange={event => setSiteDraft(current => ({ ...current, is_default: event.target.checked }))} className="h-4 w-4" />
                                Utiliser ce chantier par défaut pour ce client
                            </label>
                        </div>
                        <div className="flex justify-end gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4">
                            <button onClick={() => setShowSiteModal(false)} className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-600 hover:bg-slate-100">Annuler</button>
                            <button onClick={createClientSite} disabled={isCreatingSite} className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-black text-white hover:bg-emerald-500 disabled:bg-slate-300">
                                {isCreatingSite ? 'Création...' : 'Créer le chantier'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showProposalStarter && selectedClient && (
                <CRMQuoteComposer
                    client={selectedClient}
                    onClose={() => setShowProposalStarter(false)}
                    onCreated={(sale) => {
                        setShowProposalStarter(false);
                        setSelectedClientId(selectedClient.id);
                        openSale(sale.id);
                    }}
                />
            )}

            {showMeasureStarter && (
                <MeasureFlowStarter
                    client={selectedClient}
                    onClose={() => setShowMeasureStarter(false)}
                    onStart={startMeasureFlow}
                />
            )}

            {showClientModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-6">
                    <div className="w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
                        <div className="bg-slate-900 px-6 py-5 text-white">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-200">CRM Avant-vente</p>
                            <h3 className="mt-2 text-2xl font-black">Nouveau client</h3>
                            <p className="mt-1 text-sm font-bold text-slate-300">Créez la fiche client avant toute proposition commerciale.</p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-6">
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Nom client *</span>
                                <input
                                    value={clientDraft.name}
                                    onChange={event => updateClientDraft('name', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Entreprise ou particulier"
                                />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Contact</span>
                                <input
                                    value={clientDraft.contact_name}
                                    onChange={event => updateClientDraft('contact_name', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Nom du contact"
                                />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Type</span>
                                <select
                                    value={clientDraft.customer_type}
                                    onChange={event => updateClientDraft('customer_type', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                >
                                    <option value="B2B">Entreprise</option>
                                    <option value="B2C">Particulier</option>
                                </select>
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Segment</span>
                                <input
                                    value={clientDraft.segment}
                                    onChange={event => updateClientDraft('segment', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Ex. Grands comptes"
                                />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Tags</span>
                                <input
                                    value={clientDraft.tags}
                                    onChange={event => updateClientDraft('tags', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Prioritaire, Prescription"
                                />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Téléphone</span>
                                <input
                                    value={clientDraft.phone}
                                    onChange={event => updateClientDraft('phone', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="+237..."
                                />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Email</span>
                                <input
                                    value={clientDraft.email}
                                    onChange={event => updateClientDraft('email', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="client@example.com"
                                />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Adresse</span>
                                <input
                                    value={clientDraft.address}
                                    onChange={event => updateClientDraft('address', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Adresse client ou chantier"
                                />
                            </label>
                            <label className="md:col-span-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Identifiant fiscal</span>
                                <input
                                    value={clientDraft.tax_id}
                                    onChange={event => updateClientDraft('tax_id', event.target.value)}
                                    className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    placeholder="Optionnel"
                                />
                            </label>
                        </div>
                        <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4">
                            <button
                                onClick={() => {
                                    setShowClientModal(false);
                                    resetClientDraft();
                                }}
                                className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-600 hover:bg-slate-100"
                            >
                                Annuler
                            </button>
                            <button
                                onClick={createClient}
                                disabled={isCreatingClient}
                                className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-300"
                            >
                                {isCreatingClient ? 'Création...' : 'Créer le client'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {showDuplicates && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
                    <div className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
                        <div className="flex items-start justify-between bg-slate-900 px-6 py-5 text-white">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-amber-300">Qualité des données CRM</p>
                                <h3 className="mt-2 text-2xl font-black">Doublons clients détectés</h3>
                                <p className="mt-1 text-sm font-semibold text-slate-300">La fiche la plus ancienne est proposée comme cible. Tout l’historique est réaffecté avant suppression.</p>
                            </div>
                            <button onClick={() => setShowDuplicates(false)} className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white"><X className="h-5 w-5" /></button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6">
                            {duplicatesQuery.isLoading ? (
                                <p className="py-10 text-center text-sm font-bold text-slate-500">Analyse des fiches clients…</p>
                            ) : duplicatesQuery.isError ? (
                                <p className="border-l-4 border-red-500 bg-red-50 px-4 py-3 text-sm font-bold text-red-800">Impossible d’analyser les doublons.</p>
                            ) : !duplicatesQuery.data?.length ? (
                                <div className="py-10 text-center">
                                    <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
                                    <p className="mt-3 text-lg font-black text-slate-800">Aucun doublon probable</p>
                                    <p className="mt-1 text-sm font-semibold text-slate-500">Les emails, téléphones, identifiants fiscaux et noms/adresses sont cohérents.</p>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    {duplicatesQuery.data.map((group, index) => (
                                        <div key={`${group.clients?.[0]?.id}-${index}`} className="border border-amber-200 bg-amber-50/50 p-4">
                                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                <div>
                                                    <p className="text-xs font-black uppercase tracking-widest text-amber-800">Similarité {group.score}%</p>
                                                    <p className="mt-1 text-xs font-semibold text-slate-600">{(group.reasons || []).join(' · ')}</p>
                                                </div>
                                                <button
                                                    onClick={() => mergeDuplicateGroup(group)}
                                                    className="inline-flex items-center justify-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-xs font-black text-white hover:bg-amber-500"
                                                >
                                                    <Merge className="h-4 w-4" />
                                                    Fusionner
                                                </button>
                                            </div>
                                            <div className="mt-3 grid gap-2 md:grid-cols-2">
                                                {(group.clients || []).map((duplicate, duplicateIndex) => (
                                                    <div key={duplicate.id} className="border border-slate-200 bg-white px-3 py-3">
                                                        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{duplicateIndex === 0 ? 'Fiche cible conservée' : 'Fiche source fusionnée'}</p>
                                                        <p className="mt-1 text-sm font-black text-slate-900">{duplicate.name}</p>
                                                        <p className="mt-1 text-xs font-semibold text-slate-500">{duplicate.email || duplicate.phone || 'Sans coordonnées'}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function CRMQuoteComposer({ client, onClose, onCreated }) {
    const [catalogSearch, setCatalogSearch] = useState('');
    const [lineMode, setLineMode] = useState('stock');
    const [isCreating, setIsCreating] = useState(false);
    const [quote, setQuote] = useState({
        validity_days: 30,
        tax_rate: 20,
        notes: '',
        lines: [],
    });

    const { data: products = [], isLoading, isError, error, refetch } = useQuery({
        queryKey: ['products', 'crm-quote-composer'],
        retry: 1,
        queryFn: async () => {
            const res = await api.get('/v2/stock/products');
            return res.data;
        }
    });

    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const normalizedSearch = catalogSearch.trim().toLowerCase();
    const catalogItems = products.flatMap(product => (product.variants || []).map(variant => {
        const reference = variant.reference || product.reference_base;
        const productType = (product.product_type || 'stockable').toLowerCase();
        const unitPrice = Number(variant.sale_price ?? variant.price ?? variant.unit_price ?? variant.list_price ?? variant.cost_price ?? 0);
        return {
            variant_id: variant.id,
            reference,
            label: `${product.name}${variant.color ? ` - ${variant.color}` : ''}`,
            unit: product.unit || 'u',
            unitPrice,
            productType,
            status: product.catalog_status || 'ACTIVE',
            availableStock: Number(variant.available_quantity ?? variant.quantity_in_stock ?? 0),
            searchable: `${product.name} ${product.reference_base || ''} ${reference || ''} ${variant.supplier_reference || ''} ${product.supplier || ''}`.toLowerCase(),
        };
    }));

    const visibleItems = catalogItems
        .filter(item => lineMode === 'service' ? item.productType === 'service' : item.productType !== 'service')
        .filter(item => !normalizedSearch || item.searchable.includes(normalizedSearch))
        .slice(0, 12);

    const quoteTotal = quote.lines.reduce((sum, line) => (
        sum + Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)
    ), 0);

    const updateQuote = (field, value) => {
        setQuote(prev => ({ ...prev, [field]: value }));
    };

    const updateLine = (index, field, value) => {
        setQuote(prev => ({
            ...prev,
            lines: prev.lines.map((line, currentIndex) => currentIndex === index ? { ...line, [field]: value } : line),
        }));
    };

    const removeLine = (index) => {
        setQuote(prev => ({
            ...prev,
            lines: prev.lines.filter((_, currentIndex) => currentIndex !== index),
        }));
    };

    const addCatalogLine = (item) => {
        if (item.status !== 'ACTIVE') {
            return alert("Article non actif: qualifiez-le dans le catalogue avant de le vendre.");
        }
        setQuote(prev => ({
            ...prev,
            lines: [
                ...prev.lines,
                {
                    line_type: item.productType === 'service' ? 'service' : 'stock',
                    variant_id: item.variant_id,
                    description: `${item.label} (${item.reference})`,
                    quantity: 1,
                    unit_price: item.unitPrice,
                    discount_pct: 0,
                    unit: item.unit,
                    reference: item.reference,
                    availableStock: item.availableStock,
                }
            ]
        }));
        setCatalogSearch('');
    };

    const addFreeServiceLine = () => {
        setQuote(prev => ({
            ...prev,
            lines: [
                ...prev.lines,
                {
                    line_type: 'service',
                    variant_id: null,
                    description: 'Prestation',
                    quantity: 1,
                    unit_price: 0,
                    discount_pct: 0,
                    unit: 'u',
                }
            ]
        }));
    };

    const createQuote = async () => {
        const validLines = quote.lines
            .map(line => ({
                line_type: line.line_type || (line.variant_id ? 'stock' : 'service'),
                variant_id: line.variant_id || null,
                description: String(line.description || '').trim(),
                quantity: Number(line.quantity || 0),
                unit_price: Number(line.unit_price || 0),
                discount_pct: Number(line.discount_pct || 0),
            }))
            .filter(line => line.description && line.quantity > 0);

        if (validLines.length === 0) {
            return alert('Ajoutez au moins une ligne de devis.');
        }
        const zeroPricedStockLine = validLines.find(line => line.line_type === 'stock' && line.unit_price <= 0);
        if (zeroPricedStockLine) {
            return alert(`Prix HT manquant: renseignez le prix de vente de "${zeroPricedStockLine.description}".`);
        }

        setIsCreating(true);
        try {
            const payload = {
                client_name: client.name,
                client_contact: client.phone || null,
                client_email: client.email || null,
                client_address: client.address || null,
                notes: quote.notes.trim() || null,
                validity_days: Number(quote.validity_days || 30),
                tax_rate: Number(quote.tax_rate || 0),
                currency: 'EUR',
                workflow_type: 'FREE_SALE',
                lines: validLines,
            };
            const res = await api.post('/v2/sales/', payload);
            onCreated(res.data);
        } catch (err) {
            console.error('CRM quote error:', err);
            alert(err.response?.data?.detail || 'Erreur lors de la création de la proposition.');
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-6">
            <div className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
                <div className="flex items-center justify-between bg-slate-900 px-6 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-200">CRM avant-vente</p>
                        <h3 className="mt-2 text-2xl font-black">Composer une proposition</h3>
                        <p className="mt-1 text-sm font-bold text-slate-300">{client.name} · brouillon de devis libre</p>
                    </div>
                    <button onClick={onClose} className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white">
                        <X className="h-6 w-6" />
                    </button>
                </div>

                <div className="grid flex-1 grid-cols-[390px_1fr] gap-0 overflow-hidden">
                    <aside className="min-h-0 overflow-y-auto border-r border-slate-200 bg-slate-50 p-5">
                        <div className="mb-4 rounded-2xl border border-blue-100 bg-blue-50 p-4">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Client sélectionné</p>
                            <p className="mt-2 text-xl font-black text-blue-950">{client.name}</p>
                            <p className="mt-1 text-xs font-bold text-blue-700">{[client.phone, client.email].filter(Boolean).join(' · ') || 'Coordonnées à compléter'}</p>
                        </div>

                        <div className="mb-4 flex rounded-xl border border-slate-200 bg-white p-1">
                            <button onClick={() => setLineMode('stock')} className={`flex-1 rounded-lg px-3 py-2 text-xs font-black uppercase ${lineMode === 'stock' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-50'}`}>
                                Stock
                            </button>
                            <button onClick={() => setLineMode('service')} className={`flex-1 rounded-lg px-3 py-2 text-xs font-black uppercase ${lineMode === 'service' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-50'}`}>
                                Prestation
                            </button>
                        </div>

                        <div className="relative mb-4">
                            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                            <input
                                value={catalogSearch}
                                onChange={event => setCatalogSearch(event.target.value)}
                                placeholder={lineMode === 'stock' ? 'Référence, article, fournisseur...' : 'Pose, SAV, déplacement...'}
                                className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>

                        {lineMode === 'service' && (
                            <button onClick={addFreeServiceLine} className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-black text-white hover:bg-emerald-500">
                                <Wrench className="h-4 w-4" />
                                Ajouter prestation libre
                            </button>
                        )}

                        {isError && (
                            <div className="mb-3 rounded-xl border border-red-100 bg-red-50 p-4">
                                <p className="text-sm font-black text-red-700">Catalogue indisponible</p>
                                <p className="mt-1 text-xs font-bold text-red-600">{error?.response?.data?.detail || error?.message || 'Erreur inconnue'}</p>
                                <button onClick={() => refetch()} className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-black text-red-700 hover:bg-red-100">Réessayer</button>
                            </div>
                        )}

                        <div className="space-y-2">
                            {isLoading && <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm font-bold text-slate-500">Chargement du catalogue...</div>}
                            {!isLoading && !isError && visibleItems.length === 0 && (
                                <div className="rounded-xl border border-amber-100 bg-amber-50 p-4 text-sm font-bold text-amber-800">Aucun résultat. Utilisez une prestation libre si nécessaire.</div>
                            )}
                            {visibleItems.map(item => (
                                <button
                                    key={item.variant_id}
                                    onClick={() => addCatalogLine(item)}
                                    disabled={item.status !== 'ACTIVE'}
                                    className={`w-full rounded-xl border p-3 text-left transition-all ${item.status !== 'ACTIVE' ? 'cursor-not-allowed border-amber-200 bg-amber-50 opacity-70' : 'border-slate-200 bg-white hover:border-blue-300 hover:bg-blue-50/50'}`}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="min-w-0">
                                            <p className="truncate text-sm font-black text-slate-900">{item.label}</p>
                                            <p className="mt-1 font-mono text-[10px] font-black uppercase text-slate-400">{item.reference}</p>
                                        </div>
                                        <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-slate-500">{lineMode === 'service' ? 'Service' : 'Stock'}</span>
                                    </div>
                                    <div className="mt-3 grid grid-cols-3 gap-2">
                                        <MetricPill label="Prix HT" value={formatMoney(item.unitPrice)} />
                                        <MetricPill label="Stock" value={`${Math.round(item.availableStock * 100) / 100} ${item.unit}`} />
                                        <MetricPill label="Unité" value={item.unit} />
                                    </div>
                                </button>
                            ))}
                        </div>
                    </aside>

                    <main className="min-h-0 overflow-y-auto p-6">
                        <div className="mb-5 grid grid-cols-3 gap-4">
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Validité</span>
                                <input type="number" min="1" value={quote.validity_days} onChange={event => updateQuote('validity_days', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                            </label>
                            <label>
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">TVA %</span>
                                <input type="number" min="0" step="0.1" value={quote.tax_rate} onChange={event => updateQuote('tax_rate', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                            </label>
                            <div className="rounded-2xl border border-slate-200 bg-slate-900 px-5 py-3 text-white">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total HT</p>
                                <p className="mt-1 text-2xl font-black">{formatMoney(quoteTotal)}</p>
                            </div>
                        </div>

                        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
                            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-5 py-4">
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Lignes de proposition</p>
                                    <p className="text-sm font-bold text-slate-700">Articles stock ou prestations hors fabrication.</p>
                                </div>
                                <p className="text-sm font-black text-slate-900">{quote.lines.length} ligne(s)</p>
                            </div>
                            <div className="divide-y divide-slate-100">
                                {quote.lines.length === 0 && (
                                    <div className="p-10 text-center">
                                        <Package className="mx-auto mb-3 h-10 w-10 text-slate-300" />
                                        <p className="font-black text-slate-700">Ajoutez une ligne depuis le catalogue.</p>
                                        <p className="mt-1 text-sm font-bold text-slate-500">Le brouillon ne sera créé qu'après ajout d'au moins une ligne.</p>
                                    </div>
                                )}
                                {quote.lines.map((line, index) => {
                                    const lineTotal = Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100);
                                    return (
                                        <div key={`${line.reference || line.description}-${index}`} className="grid grid-cols-12 gap-3 p-4">
                                            <div className="col-span-12 md:col-span-5">
                                                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Désignation</label>
                                                <input value={line.description} onChange={event => updateLine(index, 'description', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                                            </div>
                                            <div className="col-span-4 md:col-span-2">
                                                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Qté</label>
                                                <input type="number" min="0" step="0.01" value={line.quantity} onChange={event => updateLine(index, 'quantity', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                                            </div>
                                            <div className="col-span-4 md:col-span-2">
                                                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Prix HT</label>
                                                <input type="number" min="0" step="0.01" value={line.unit_price} onChange={event => updateLine(index, 'unit_price', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                                            </div>
                                            <div className="col-span-4 md:col-span-2">
                                                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Remise</label>
                                                <input type="number" min="0" max="100" step="0.1" value={line.discount_pct} onChange={event => updateLine(index, 'discount_pct', event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500" />
                                            </div>
                                            <div className="col-span-12 md:col-span-1 flex items-end justify-between gap-3 md:block">
                                                <p className="pb-2 text-sm font-black text-slate-900 md:text-right">{formatMoney(lineTotal)}</p>
                                                <button onClick={() => removeLine(index)} className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs font-black text-red-600 hover:bg-red-100">
                                                    <X className="h-4 w-4" />
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <label className="mt-5 block">
                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Notes</span>
                            <textarea value={quote.notes} onChange={event => updateQuote('notes', event.target.value)} placeholder="Conditions, contexte client, remarques..." className="mt-2 h-24 w-full resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500" />
                        </label>
                    </main>
                </div>

                <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-6 py-4">
                    <p className="text-sm font-bold text-slate-500">La proposition sera créée en brouillon CRM, sans réservation stock.</p>
                    <div className="flex items-center gap-3">
                        <button onClick={onClose} className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-600 hover:bg-slate-100">Annuler</button>
                        <button onClick={createQuote} disabled={isCreating} className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-300">
                            <Send className="h-4 w-4" />
                            {isCreating ? 'Création...' : 'Créer le brouillon'}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function MetricPill({ label, value }) {
    return (
        <div className="rounded-lg border border-slate-100 bg-slate-50 px-2 py-1.5">
            <p className="text-[9px] font-black uppercase text-slate-400">{label}</p>
            <p className="truncate text-xs font-black text-slate-800">{value}</p>
        </div>
    );
}

function JourneyStep({ number, title, detail }) {
    return (
        <div className="rounded-2xl border border-white/80 bg-white/90 p-4 shadow-sm">
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-blue-600 text-xs font-black text-white">{number}</span>
            <p className="mt-3 text-sm font-black text-slate-950">{title}</p>
            <p className="mt-1 text-xs font-bold leading-5 text-slate-500">{detail}</p>
        </div>
    );
}

function MiniKpi({ label, value }) {
    return (
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
            <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className="mt-1 truncate text-lg font-black text-slate-950">{value}</p>
        </div>
    );
}

function SellerQueueCard({ item, onOpen }) {
    const tones = {
        red: 'border-red-100 bg-red-50 text-red-950',
        blue: 'border-blue-100 bg-blue-50 text-blue-950',
        amber: 'border-amber-100 bg-amber-50 text-amber-950',
        emerald: 'border-emerald-100 bg-emerald-50 text-emerald-950',
    };
    return (
        <button
            type="button"
            onClick={onOpen}
            className={`group rounded-2xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-md ${tones[item.tone] || tones.blue}`}
        >
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{item.label}</p>
                    <p className="mt-3 text-4xl font-black">{item.value}</p>
                </div>
                <span className="rounded-full bg-white/80 p-2 transition-transform group-hover:translate-x-1">
                    <ArrowRight className="h-4 w-4" />
                </span>
            </div>
            <p className="mt-3 text-sm font-bold leading-5 opacity-75">{item.detail}</p>
        </button>
    );
}

function QuickAction({ icon: Icon, title, detail, onClick, disabled = false }) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
        >
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-blue-600 shadow-sm">
                <Icon className="h-5 w-5" />
            </span>
            <span className="min-w-0">
                <span className="block text-sm font-black text-slate-950">{title}</span>
                <span className="mt-0.5 block truncate text-xs font-bold text-slate-500">{detail}</span>
            </span>
        </button>
    );
}

function WorkspaceCard({ icon: Icon, eyebrow, title, detail, onOpen }) {
    return (
        <button
            type="button"
            onClick={onOpen}
            className="group rounded-3xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md"
        >
            <div className="flex items-start justify-between gap-4">
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                    <Icon className="h-5 w-5" />
                </span>
                <ArrowRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-blue-600" />
            </div>
            <p className="mt-5 text-[10px] font-black uppercase tracking-widest text-blue-600">{eyebrow}</p>
            <h4 className="mt-1 text-lg font-black text-slate-950">{title}</h4>
            <p className="mt-2 text-sm font-bold leading-6 text-slate-500">{detail}</p>
        </button>
    );
}

function InfoLine({ icon: Icon, label, value }) {
    return (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 min-w-0">
            <div className="flex items-center gap-2 text-slate-400 mb-2">
                <Icon className="w-4 h-4" />
                <span className="text-[10px] font-black uppercase tracking-widest">{label}</span>
            </div>
            <p className="text-sm font-black text-slate-800 truncate">{value || 'Non renseigné'}</p>
        </div>
    );
}

function MeasureFlowStarter({ client, onClose, onStart }) {
    const options = [
        {
            source: 'SITE_VISIT',
            scope: 'SUPPLY_AND_INSTALL',
            icon: MapPin,
            title: 'Planifier un métré sur chantier',
            description: 'MMG affecte un métreur, planifie le rendez-vous et relève les cotes sur place.',
            tone: 'border-emerald-200 bg-emerald-50 text-emerald-950',
        },
        {
            source: 'CLIENT_DOCUMENTS',
            scope: 'SUPPLY_ONLY',
            scopeLabel: 'Par défaut : fourniture seule',
            icon: FileText,
            title: 'Importer les cotes du client',
            description: 'Le client apporte plans, croquis ou relevés. Le BE les contrôle avant fabrication.',
            tone: 'border-amber-200 bg-amber-50 text-amber-950',
        },
        {
            source: 'AGENCY_ASSISTED',
            scope: 'SUPPLY_ONLY',
            scopeLabel: 'Par défaut : fourniture seule',
            icon: Building2,
            title: 'Saisir les cotes en agence',
            description: 'Un commercial ou technicien structure les ouvrages avec le client au comptoir.',
            tone: 'border-blue-200 bg-blue-50 text-blue-950',
        },
    ];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
            <div className="w-full max-w-4xl overflow-hidden border border-slate-200 bg-white shadow-2xl">
                <div className="flex items-start justify-between bg-slate-900 px-6 py-5 text-white">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-blue-200">Dossier fabrication</p>
                        <h3 className="mt-2 text-2xl font-black">Comment les cotes sont-elles obtenues ?</h3>
                        <p className="mt-1 text-sm font-bold text-slate-300">
                            {client ? `${client.name} est déjà sélectionné.` : 'Le client pourra être sélectionné à l’étape suivante.'}
                        </p>
                    </div>
                    <button onClick={onClose} className="rounded-full p-2 text-slate-300 hover:bg-white/10 hover:text-white"><X className="h-5 w-5" /></button>
                </div>
                <div className="grid gap-3 p-6 md:grid-cols-3">
                    {options.map(option => {
                        const Icon = option.icon;
                        return (
                            <button
                                key={option.source}
                                onClick={() => onStart(option.source, option.scope)}
                                className={`min-h-52 border p-5 text-left transition-transform hover:-translate-y-0.5 hover:shadow-md ${option.tone}`}
                            >
                                <Icon className="h-7 w-7" />
                                <p className="mt-5 text-lg font-black">{option.title}</p>
                                <p className="mt-2 text-sm font-semibold leading-6 opacity-80">{option.description}</p>
                                <span className="mt-4 inline-flex rounded-md border border-current/20 px-2 py-1 text-[10px] font-black uppercase tracking-widest">
                                    {option.scopeLabel}
                                </span>
                                <span className="mt-5 inline-flex items-center gap-2 text-xs font-black uppercase tracking-widest">Continuer <ArrowRight className="h-4 w-4" /></span>
                            </button>
                        );
                    })}
                </div>
                <div className="border-t border-slate-200 bg-slate-50 px-6 py-4 text-xs font-bold text-slate-600">
                    Dans tous les cas : saisie multi-ouvrages, contrôle BE et traçabilité de la responsabilité des cotes.
                </div>
            </div>
        </div>
    );
}

function PipelineStep({ label, count, amount, tone }) {
    const toneClasses = {
        slate: 'border-slate-200 bg-slate-50 text-slate-700',
        blue: 'border-blue-200 bg-blue-50 text-blue-700',
        emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
        red: 'border-red-200 bg-red-50 text-red-700',
    };

    return (
        <div className={`rounded-2xl border p-4 ${toneClasses[tone] || toneClasses.slate}`}>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{label}</p>
            <div className="mt-3 flex items-end justify-between gap-3">
                <p className="text-3xl font-black">{count}</p>
                <p className="text-sm font-black">{amount}</p>
            </div>
        </div>
    );
}

function actionToneClass(tone) {
    const classes = {
        blue: 'border-blue-200 bg-blue-50 text-blue-900 hover:bg-blue-100',
        amber: 'border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100',
        emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900 hover:bg-emerald-100',
        slate: 'border-slate-200 bg-slate-50 text-slate-800 hover:bg-slate-100',
    };
    return classes[tone] || classes.slate;
}

function timelineDotClass(tone) {
    const classes = {
        blue: 'bg-blue-500',
        emerald: 'bg-emerald-500',
        indigo: 'bg-indigo-500',
        teal: 'bg-teal-500',
        red: 'bg-red-500',
    };
    return classes[tone] || 'bg-slate-300';
}

function SaleRow({ sale, total, statusLabel, statusClassName, formatDate, formatMoney, onOpen }) {
    return (
        <button
            onClick={onOpen}
            className="w-full grid grid-cols-[1fr_170px_130px_40px] gap-4 px-5 py-4 items-center text-left hover:bg-blue-50/40 transition-colors"
        >
            <div className="min-w-0">
                <p className="font-black text-slate-900 truncate">{sale.reference}</p>
                <p className="text-xs font-bold text-slate-500">{formatDate(sale.created_at)} · {sale.lines?.length || 0} ligne(s)</p>
                <BusinessTimeline sale={sale} compact />
            </div>
            <span className={`justify-self-start rounded-lg border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${statusClassName}`}>
                {statusLabel}
            </span>
            <p className="text-right font-black text-slate-900">{formatMoney(total)}</p>
            <ArrowRight className="w-4 h-4 text-slate-400" />
        </button>
    );
}

function DossierRow({ dossier, formatDate, onOpen }) {
    const isDone = dossier.status === 'VALIDATED';
    const statusClass = isDone
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-amber-200 bg-amber-50 text-amber-700';

    return (
        <button
            onClick={onOpen}
            className="w-full grid grid-cols-[1fr_170px_130px_40px] gap-4 px-5 py-4 items-center text-left hover:bg-emerald-50/40 transition-colors"
        >
            <div className="min-w-0">
                <p className="font-black text-slate-900 truncate">{dossier.reference}</p>
                <p className="text-xs font-bold text-slate-500">{formatDate(dossier.created_at)} · {dossier.client_address || 'Adresse à compléter'}</p>
            </div>
            <span className={`justify-self-start rounded-lg border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${statusClass}`}>
                {isDone ? 'Métré réalisé' : 'Métré à traiter'}
            </span>
            <p className="text-right text-xs font-black uppercase tracking-widest text-emerald-700">Fabrication</p>
            <ArrowRight className="w-4 h-4 text-slate-400" />
        </button>
    );
}

function DocMetric({ icon: Icon, label, value }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Icon className="w-4 h-4 text-slate-400 mb-2" />
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className="text-2xl font-black text-slate-900">{value}</p>
        </div>
    );
}
