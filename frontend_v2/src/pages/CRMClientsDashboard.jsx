import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BellRing, Building2, CalendarClock, CheckCircle2, ClipboardList, FileText, Mail, MapPin, Package, Phone, Plus, Search, Send, Truck, Users, Wrench, X } from 'lucide-react';
import api from '../services/api';
import MMGDossiers from './MMGDossiers';
import BusinessTimeline from '../components/BusinessTimeline';
import CRMClientActionWorkspace from '../components/CRMClientActionWorkspace';

const saleAmount = (sale) => (sale.lines || []).reduce(
    (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
    0
);

const isPresalesStatus = (status) => ['DRAFT', 'SENT', 'CANCELLED'].includes(status);
const isActivePresalesStatus = (status) => ['DRAFT', 'SENT'].includes(status);

export default function CRMClientsDashboard() {
    const navigate = useNavigate();
    const [crmView, setCrmView] = useState('pipeline');
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedClientId, setSelectedClientId] = useState(null);
    const [showProposalStarter, setShowProposalStarter] = useState(false);
    const [showClientModal, setShowClientModal] = useState(false);
    const [showMeasureStarter, setShowMeasureStarter] = useState(false);
    const [showSiteModal, setShowSiteModal] = useState(false);
    const [isCreatingClient, setIsCreatingClient] = useState(false);
    const [isCreatingSite, setIsCreatingSite] = useState(false);
    const [clientDraft, setClientDraft] = useState({
        name: '',
        contact_name: '',
        phone: '',
        email: '',
        address: '',
        tax_id: '',
        customer_type: 'B2B',
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
        navigate(`/manager?view=sale-detail&id=${saleId}&from=crm`);
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

    const filteredClients = useMemo(() => {
        const needle = normalize(searchTerm);
        return clients
            .filter(client => client.is_active !== false)
            .filter(client => {
                if (!needle) return true;
                return [
                    client.name,
                    client.contact_name,
                    client.phone,
                    client.email,
                    client.address,
                    client.tax_id
                ].some(value => normalize(value).includes(needle));
            });
    }, [clients, searchTerm]);

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

    const allPresalesQuotes = useMemo(() => (
        sales
            .filter(sale => isPresalesStatus(sale.status))
            .filter(sale => {
                const needle = normalize(searchTerm);
                if (!needle || crmView !== 'pipeline') return true;
                return [
                    sale.reference,
                    sale.client_name,
                    sale.client_contact,
                    sale.client_email,
                ].some(value => normalize(value).includes(needle));
            })
            .sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0))
    ), [sales, searchTerm, crmView]);

    const filteredDossiers = useMemo(() => {
        const needle = normalize(searchTerm);
        return dossiers
            .filter(dossier => {
                if (!needle || crmView !== 'pipeline') return true;
                return [
                    dossier.reference,
                    dossier.client_name,
                    dossier.client_contact,
                    dossier.client_email,
                ].some(value => normalize(value).includes(needle));
            })
            .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
    }, [dossiers, searchTerm, crmView]);

    const crmPipelineTotal = allPresalesQuotes.reduce((sum, sale) => sum + saleAmount(sale), 0);
    const measurePending = filteredDossiers.filter(dossier => dossier.status !== 'VALIDATED');
    const measureValidated = filteredDossiers.filter(dossier => dossier.status === 'VALIDATED');
    const quoteDrafts = allPresalesQuotes.filter(sale => sale.status === 'DRAFT');
    const quoteSent = allPresalesQuotes.filter(sale => sale.status === 'SENT');
    const quoteLost = allPresalesQuotes.filter(sale => sale.status === 'CANCELLED');

    const crmPipelineColumns = [
        {
            key: 'request',
            label: 'Demande reçue',
            detail: 'Créer un client, une proposition ou une prise de côte',
            tone: 'slate',
            items: [],
            kind: 'empty',
        },
        {
            key: 'measure_pending',
            label: 'Métré à traiter',
            detail: 'Prises de côte reçues, à contrôler',
            tone: 'emerald',
            items: measurePending,
            kind: 'dossier',
        },
        {
            key: 'measure_done',
            label: 'Métré réalisé',
            detail: 'Dossiers validés, prêts pour chiffrage',
            tone: 'emerald',
            items: measureValidated,
            kind: 'dossier',
        },
        {
            key: 'quote_draft',
            label: 'Chiffrage / devis',
            detail: 'Propositions en préparation',
            tone: 'blue',
            items: quoteDrafts,
            kind: 'sale',
        },
        {
            key: 'quote_sent',
            label: 'Devis envoyé / relance',
            detail: 'Client à suivre jusqu’à signature',
            tone: 'amber',
            items: quoteSent,
            kind: 'sale',
        },
        {
            key: 'lost',
            label: 'Perdu / annulé',
            detail: 'Opportunités clôturées sans commande',
            tone: 'red',
            items: quoteLost,
            kind: 'sale',
        },
    ];

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

    return (
        <div className="w-full h-[calc(100vh-80px)] font-sans flex flex-col overflow-hidden bg-white border-y border-slate-200/80 animate-fade-in">
            <div className="bg-slate-900 px-8 py-6 text-white shrink-0">
                <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-5">
                    <div>
                        <div className="inline-flex items-center gap-2 rounded-xl bg-white/10 border border-white/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-blue-100 mb-3">
                            <Users className="w-4 h-4" />
                            CRM Avant-vente
                        </div>
                        <h2 className="text-3xl font-black tracking-tight">Avant-vente & relation client</h2>
                        <p className="mt-2 text-sm font-bold text-slate-300 max-w-3xl">
                            Qualifiez les clients, les prises de côte et les propositions avant leur passage en commande signée.
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="inline-flex rounded-xl border border-white/10 bg-white/10 p-1">
                            <button
                                onClick={() => setCrmView('pipeline')}
                                className={`rounded-lg px-4 py-2 text-sm font-black transition-all ${crmView === 'pipeline' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-300 hover:text-white'}`}
                            >
                                Pipeline avant-vente
                            </button>
                            <button
                                onClick={planMeasureForClient}
                                className={`rounded-lg px-4 py-2 text-sm font-black transition-all ${crmView === 'measures' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-300 hover:text-white'}`}
                            >
                                Métrés fabrication
                            </button>
                            <button
                                onClick={() => setCrmView('clients')}
                                className={`rounded-lg px-4 py-2 text-sm font-black transition-all ${crmView === 'clients' ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-300 hover:text-white'}`}
                            >
                                Fiches clients
                            </button>
                        </div>
                        <button
                            onClick={() => setShowClientModal(true)}
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/10 px-5 py-3 text-sm font-black text-white hover:bg-white/15"
                        >
                            <Users className="w-4 h-4" />
                            Nouveau client
                        </button>
                        <button
                            onClick={createQuoteForClient}
                            disabled={!selectedClient}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400"
                        >
                            <Plus className="w-4 h-4" />
                            Créer une proposition
                        </button>
                        <button
                            onClick={planMeasureForClient}
                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-emerald-500/20 hover:bg-emerald-500"
                        >
                            <ClipboardList className="w-4 h-4" />
                            Prise de côte
                        </button>
                    </div>
                </div>
            </div>

            {crmView === 'pipeline' && (
                <div className="flex-1 min-h-0 overflow-y-auto p-6">
                    <div className="mb-5 grid grid-cols-1 gap-4 lg:grid-cols-4">
                        <CrmMetric label="Métrés ouverts" value={measurePending.length + measureValidated.length} detail={`${measurePending.length} à traiter · ${measureValidated.length} réalisés`} tone="emerald" />
                        <CrmMetric label="Chiffrages en cours" value={quoteDrafts.length} detail="Devis à préparer" tone="slate" />
                        <CrmMetric label="Relances client" value={quoteSent.length} detail="Devis envoyés" tone="amber" />
                        <CrmMetric label="Montant pipeline" value={formatMoney(crmPipelineTotal)} detail="Avant-vente total" tone="emerald" />
                    </div>

                    <div className="mb-5 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
                        <div className="relative w-full lg:max-w-md">
                            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                            <input
                                value={searchTerm}
                                onChange={event => setSearchTerm(event.target.value)}
                                placeholder="Rechercher opportunité, client, téléphone..."
                                className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500"
                            />
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <button
                                onClick={() => setCrmView('clients')}
                                className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-700 hover:bg-slate-50"
                            >
                                <Users className="w-4 h-4" />
                                Ouvrir les fiches clients
                            </button>
                            <button
                                onClick={planMeasureForClient}
                                className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-black text-white shadow-md shadow-emerald-500/20 hover:bg-emerald-500"
                            >
                                <ClipboardList className="w-4 h-4" />
                                Nouvelle prise de côte
                            </button>
                            <button
                                onClick={createQuoteForClient}
                                disabled={!selectedClient}
                                className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-black text-white shadow-md shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-200 disabled:text-slate-400"
                            >
                                <Plus className="w-4 h-4" />
                                Créer une proposition
                            </button>
                        </div>
                    </div>

                    <div className="flex min-h-[520px] gap-5 overflow-x-auto pb-3">
                        {crmPipelineColumns.map(column => {
                            const columnAmount = column.kind === 'sale' ? column.items.reduce((sum, sale) => sum + saleAmount(sale), 0) : 0;
                            return (
                                <section key={column.key} className="flex min-h-0 w-80 shrink-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
                                    <div className="border-b border-slate-100 p-4">
                                        <div className="flex items-start justify-between gap-3">
                                            <div>
                                                <p className="text-sm font-black text-slate-900">{column.label}</p>
                                                <p className="mt-1 text-xs font-bold text-slate-500">{column.detail}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-lg font-black text-slate-900">{column.items.length}</p>
                                                {column.kind === 'sale' && <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{formatMoney(columnAmount)}</p>}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50/70 p-4">
                                        {column.kind === 'empty' && (
                                            <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-4">
                                                <p className="text-sm font-black text-slate-700">Point d’entrée client</p>
                                                <p className="mt-1 text-xs font-bold text-slate-500">
                                                    Pour une fabrication : créez une prise de côte. Pour une vente simple : créez une proposition.
                                                </p>
                                                <div className="mt-4 grid gap-2">
                                                    <button
                                                        onClick={planMeasureForClient}
                                                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-3 py-2 text-xs font-black text-white hover:bg-emerald-500"
                                                    >
                                                        <ClipboardList className="w-4 h-4" />
                                                        Prise de côte
                                                    </button>
                                                    <button
                                                        onClick={createQuoteForClient}
                                                        disabled={!selectedClient}
                                                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-black text-blue-700 hover:bg-blue-100 disabled:opacity-50"
                                                    >
                                                        <Plus className="w-4 h-4" />
                                                        Proposition libre
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                        {column.kind === 'dossier' && column.items.map(dossier => (
                                            <CrmDossierCard
                                                key={dossier.id}
                                                dossier={dossier}
                                                formatDate={formatDate}
                                                onOpen={() => dossier.measure_mission_id
                                                    ? navigate(`/measure-missions/${dossier.measure_mission_id}`)
                                                    : setCrmView('measures')}
                                            />
                                        ))}
                                        {column.kind === 'sale' && column.items.map(sale => (
                                            <CrmOpportunityCard
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
                                        {column.kind !== 'empty' && column.items.length === 0 && (
                                            <div className="flex h-36 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white text-center">
                                                <p className="px-6 text-sm font-bold text-slate-400">Aucun élément dans cette étape.</p>
                                            </div>
                                        )}
                                    </div>
                                </section>
                            );
                        })}
                    </div>
                </div>
            )}

            {crmView === 'measures' && (
                <div className="flex-1 min-h-0 overflow-y-auto bg-white">
                    <div className="border-b border-slate-200 bg-emerald-50 px-8 py-5">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Avant-vente fabrication</p>
                                <h3 className="mt-1 text-2xl font-black text-slate-900">Prises de côtes & dossiers techniques</h3>
                                <p className="mt-1 text-sm font-bold text-slate-600">
                                    Une fabrication MMG démarre ici : métré, dossier technique, puis devis fabrication.
                                </p>
                            </div>
                            <button
                                onClick={() => setCrmView('pipeline')}
                                className="inline-flex items-center justify-center gap-2 rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm font-black text-emerald-700 hover:bg-emerald-100"
                            >
                                <ArrowRight className="w-4 h-4 rotate-180" />
                                Retour pipeline CRM
                            </button>
                        </div>
                    </div>
                    <MMGDossiers isEmbedded={true} />
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
                            <button
                                onClick={() => setShowClientModal(true)}
                                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-black text-white hover:bg-slate-800"
                            >
                                <Plus className="h-4 w-4" />
                                Nouveau client
                            </button>
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

function CrmMetric({ label, value, detail, tone }) {
    const toneClasses = {
        blue: 'border-blue-100 bg-blue-50 text-blue-700',
        emerald: 'border-emerald-100 bg-emerald-50 text-emerald-700',
        amber: 'border-amber-100 bg-amber-50 text-amber-700',
        slate: 'border-slate-200 bg-white text-slate-800',
    };

    return (
        <div className={`rounded-2xl border p-5 shadow-sm ${toneClasses[tone] || toneClasses.slate}`}>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{label}</p>
            <p className="mt-2 text-2xl font-black">{value}</p>
            <p className="mt-1 text-xs font-bold opacity-75">{detail}</p>
        </div>
    );
}

function CrmOpportunityCard({ sale, total, statusLabel, statusClassName, formatDate, formatMoney, onOpen }) {
    const lineCount = (sale.lines || []).length;

    return (
        <button
            onClick={onOpen}
            className="w-full rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="truncate text-base font-black text-slate-900">{sale.client_name || 'Client inconnu'}</p>
                    <p className="mt-1 font-mono text-[10px] font-black uppercase tracking-widest text-slate-400">{sale.reference}</p>
                </div>
                <p className="whitespace-nowrap text-base font-black text-slate-900">{formatMoney(total)}</p>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className={`rounded-md border px-2 py-1 text-[10px] font-black uppercase tracking-widest ${statusClassName}`}>
                    {statusLabel}
                </span>
                <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                    {lineCount} ligne(s)
                </span>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
                <p className="text-xs font-bold text-slate-500">{formatDate(sale.updated_at || sale.created_at)}</p>
                <span className="inline-flex items-center gap-1 text-xs font-black text-blue-700">
                    Ouvrir
                    <ArrowRight className="h-4 w-4" />
                </span>
            </div>
        </button>
    );
}

function CrmDossierCard({ dossier, formatDate, onOpen }) {
    const statusLabel = dossier.status === 'VALIDATED' ? 'Métré réalisé' : 'À traiter';
    const statusClass = dossier.status === 'VALIDATED'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-amber-200 bg-amber-50 text-amber-700';

    return (
        <button
            onClick={onOpen}
            className="w-full rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-all hover:border-emerald-300 hover:shadow-md"
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <p className="truncate text-base font-black text-slate-900">{dossier.client_name || 'Client inconnu'}</p>
                    <p className="mt-1 font-mono text-[10px] font-black uppercase tracking-widest text-slate-400">{dossier.reference}</p>
                </div>
                <span className={`shrink-0 rounded-md border px-2 py-1 text-[9px] font-black uppercase tracking-widest ${statusClass}`}>
                    {statusLabel}
                </span>
            </div>
            <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Chantier</p>
                <p className="mt-1 text-xs font-bold text-slate-600">{dossier.client_address || 'Adresse à compléter'}</p>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
                <p className="text-xs font-bold text-slate-500">{formatDate(dossier.created_at)}</p>
                <span className="inline-flex items-center gap-1 text-xs font-black text-emerald-700">
                    Ouvrir métrés
                    <ArrowRight className="h-4 w-4" />
                </span>
            </div>
        </button>
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
