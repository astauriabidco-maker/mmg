import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BellRing, CalendarClock, CheckCircle2, ClipboardList, FileText, Mail, MapPin, Phone, Plus, Search, Truck, Users } from 'lucide-react';
import api from '../services/api';

const saleAmount = (sale) => (sale.lines || []).reduce(
    (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
    0
);

const isPresalesStatus = (status) => ['DRAFT', 'SENT', 'CANCELLED'].includes(status);
const isActivePresalesStatus = (status) => ['DRAFT', 'SENT'].includes(status);

export default function CRMClientsDashboard() {
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedClientId, setSelectedClientId] = useState(null);
    const [showProposalStarter, setShowProposalStarter] = useState(false);

    const { data: clients = [] } = useQuery({
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

    const composeQuoteForClient = () => {
        if (!selectedClient) return;
        setShowProposalStarter(false);
        navigate('/manager?view=sales', {
            state: {
                view: 'sales',
                openManualQuote: true,
                prefillClient: selectedClient,
            }
        });
    };

    const openSale = (saleId) => {
        navigate(`/manager?view=sale-detail&id=${saleId}`);
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

    const activePresalesQuotes = useMemo(() => (
        presalesQuotes.filter(sale => isActivePresalesStatus(sale.status))
    ), [presalesQuotes]);

    const nextActions = useMemo(() => {
        const actions = [];
        const draft = activePresalesQuotes.find(sale => sale.status === 'DRAFT');
        const sent = activePresalesQuotes.find(sale => sale.status === 'SENT');

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
    }, [activePresalesQuotes, selectedClient]);

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
        <div className="max-w-[1600px] h-[calc(100vh-100px)] mx-auto font-sans flex flex-col overflow-hidden bg-slate-50/50 border border-slate-200/60 rounded-[2rem] shadow-2xl animate-fade-in">
            <div className="bg-slate-900 px-8 py-6 text-white shrink-0 rounded-t-[2rem]">
                <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-5">
                    <div>
                        <div className="inline-flex items-center gap-2 rounded-xl bg-white/10 border border-white/10 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-blue-100 mb-3">
                            <Users className="w-4 h-4" />
                            CRM Clients
                        </div>
                        <h2 className="text-3xl font-black tracking-tight">Clients & relation commerciale</h2>
                        <p className="mt-2 text-sm font-bold text-slate-300 max-w-3xl">
                            Pilotez l'avant-vente client: propositions ouvertes, relances, historique et passage vers l'exécution.
                        </p>
                    </div>
                    <button
                        onClick={createQuoteForClient}
                        disabled={!selectedClient}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400"
                    >
                        <Plus className="w-4 h-4" />
                        Créer une proposition
                    </button>
                </div>
            </div>

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
                            <p className="text-sm font-bold text-slate-400 mt-1">Sélectionnez un client dans la liste.</p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <section className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                <div className="p-6 flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-indigo-500 mb-2">Fiche client</p>
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
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-3 gap-3 w-full xl:w-auto">
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
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 px-6 pb-6">
                                    <InfoLine icon={Phone} label="Téléphone" value={selectedClient.phone} />
                                    <InfoLine icon={Mail} label="Email" value={selectedClient.email} />
                                    <InfoLine icon={MapPin} label="Adresse" value={selectedClient.address} />
                                </div>
                            </section>

                            <section className="grid grid-cols-[1fr_320px] gap-6 items-start">
                                <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                    <div className="px-5 py-4 bg-blue-50 border-b border-blue-100 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-600">Avant-vente client</p>
                                            <p className="text-sm font-bold text-blue-950">Devis ouverts, signature en attente et opportunités à décider.</p>
                                        </div>
                                        <button
                                            onClick={createQuoteForClient}
                                            className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-black text-white shadow-md shadow-blue-500/20 hover:bg-blue-500"
                                        >
                                            <Plus className="w-4 h-4" />
                                            Créer une proposition
                                        </button>
                                    </div>

                                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 p-5 border-b border-slate-100">
                                        <PipelineStep label="Brouillons" count={presalesQuotes.filter(sale => sale.status === 'DRAFT').length} amount={formatMoney(presalesQuotes.filter(sale => sale.status === 'DRAFT').reduce((sum, sale) => sum + saleAmount(sale), 0))} tone="slate" />
                                        <PipelineStep label="Envoyés" count={presalesQuotes.filter(sale => sale.status === 'SENT').length} amount={formatMoney(presalesQuotes.filter(sale => sale.status === 'SENT').reduce((sum, sale) => sum + saleAmount(sale), 0))} tone="blue" />
                                        <PipelineStep label="Perdus / annulés" count={presalesQuotes.filter(sale => sale.status === 'CANCELLED').length} amount={formatMoney(presalesQuotes.filter(sale => sale.status === 'CANCELLED').reduce((sum, sale) => sum + saleAmount(sale), 0))} tone="red" />
                                    </div>

                                    <div className="divide-y divide-slate-100">
                                        {presalesQuotes.map(sale => (
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
                                        {presalesQuotes.length === 0 && (
                                            <div className="p-10 text-center">
                                                <FileText className="w-12 h-12 mx-auto text-blue-200 mb-3" />
                                                <p className="text-sm font-black text-slate-600">Aucun devis en avant-vente pour ce client.</p>
                                                <button onClick={createQuoteForClient} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-black text-white hover:bg-blue-500">
                                                    <Plus className="w-4 h-4" />
                                                    Créer le premier devis
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="space-y-4">
                                    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
                                        <div className="flex items-center justify-between mb-4">
                                            <div>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">À traiter</p>
                                                <p className="text-sm font-bold text-slate-700">Actions avant-vente</p>
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

            {showProposalStarter && selectedClient && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-6">
                    <div className="w-full max-w-xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl">
                        <div className="bg-slate-900 px-6 py-5 text-white">
                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-200">Nouvelle proposition CRM</p>
                            <h3 className="mt-2 text-2xl font-black">Préparer une proposition</h3>
                            <p className="mt-1 text-sm font-bold text-slate-300">{selectedClient.name}</p>
                        </div>
                        <div className="space-y-4 p-6">
                            <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4">
                                <p className="text-sm font-black text-blue-950">On reste dans le CRM.</p>
                                <p className="mt-1 text-sm font-bold text-blue-800">
                                    Le client est déjà sélectionné. L'étape suivante ouvre seulement le compositeur de devis avec ce client prérempli.
                                </p>
                            </div>
                            <div className="grid grid-cols-1 gap-3 text-sm font-bold text-slate-700">
                                <InfoLine icon={Phone} label="Téléphone" value={selectedClient.phone} />
                                <InfoLine icon={Mail} label="Email" value={selectedClient.email} />
                                <InfoLine icon={MapPin} label="Adresse" value={selectedClient.address} />
                            </div>
                        </div>
                        <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50 px-6 py-4">
                            <button
                                onClick={() => setShowProposalStarter(false)}
                                className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-600 hover:bg-slate-100"
                            >
                                Rester sur la fiche
                            </button>
                            <button
                                onClick={composeQuoteForClient}
                                className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500"
                            >
                                Composer le devis
                            </button>
                        </div>
                    </div>
                </div>
            )}
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

function PipelineStep({ label, count, amount, tone }) {
    const toneClasses = {
        slate: 'border-slate-200 bg-slate-50 text-slate-700',
        blue: 'border-blue-200 bg-blue-50 text-blue-700',
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
            </div>
            <span className={`justify-self-start rounded-lg border px-3 py-1.5 text-[10px] font-black uppercase tracking-widest ${statusClassName}`}>
                {statusLabel}
            </span>
            <p className="text-right font-black text-slate-900">{formatMoney(total)}</p>
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
