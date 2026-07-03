import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ClipboardList, FileText, Mail, MapPin, Phone, Plus, Search, Truck, Users } from 'lucide-react';
import api from '../services/api';

export default function CRMClientsDashboard() {
    const navigate = useNavigate();
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedClientId, setSelectedClientId] = useState(null);

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
            const amount = (sale.lines || []).reduce(
                (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
                0
            );
            acc.quoteAmount += amount;
            acc.invoices += (sale.invoices || []).filter(invoice => !String(invoice.reference || '').startsWith('AV-')).length;
            acc.deliveryNotes += (sale.delivery_notes || []).length;
            return acc;
        }, { quoteAmount: 0, invoices: 0, deliveryNotes: 0 });
    }, [clientSales]);

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
                            Retrouvez les coordonnées, devis, factures et livraisons d'un client avant de lancer une nouvelle vente.
                        </p>
                    </div>
                    <button
                        onClick={createQuoteForClient}
                        disabled={!selectedClient}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-black text-white shadow-lg shadow-blue-500/20 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-400"
                    >
                        <Plus className="w-4 h-4" />
                        Créer un devis pour ce client
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
                                    </div>
                                    <div className="grid grid-cols-3 gap-3 w-full xl:w-auto">
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Devis</p>
                                            <p className="text-2xl font-black text-slate-900">{clientSales.length}</p>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Factures</p>
                                            <p className="text-2xl font-black text-slate-900">{totals.invoices}</p>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-5 py-4">
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">CA devis HT</p>
                                            <p className="text-2xl font-black text-slate-900">{formatMoney(totals.quoteAmount)}</p>
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
                                    <div className="px-5 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Devis & ventes</p>
                                            <p className="text-sm font-bold text-slate-600">Historique commercial lié au client.</p>
                                        </div>
                                        <ClipboardList className="w-5 h-5 text-slate-400" />
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {clientSales.map(sale => {
                                            const total = (sale.lines || []).reduce(
                                                (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
                                                0
                                            );
                                            return (
                                                <button
                                                    key={sale.id}
                                                    onClick={() => openSale(sale.id)}
                                                    className="w-full grid grid-cols-[1fr_150px_130px_40px] gap-4 px-5 py-4 items-center text-left hover:bg-blue-50/40 transition-colors"
                                                >
                                                    <div className="min-w-0">
                                                        <p className="font-black text-slate-900 truncate">{sale.reference}</p>
                                                        <p className="text-xs font-bold text-slate-500">{formatDate(sale.created_at)} · {sale.lines?.length || 0} ligne(s)</p>
                                                    </div>
                                                    <span className="justify-self-start rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-widest text-slate-600">
                                                        {statusLabel(sale)}
                                                    </span>
                                                    <p className="text-right font-black text-slate-900">{formatMoney(total)}</p>
                                                    <ArrowRight className="w-4 h-4 text-slate-400" />
                                                </button>
                                            );
                                        })}
                                        {clientSales.length === 0 && (
                                            <div className="p-10 text-center">
                                                <FileText className="w-12 h-12 mx-auto text-slate-200 mb-3" />
                                                <p className="text-sm font-black text-slate-500">Aucun devis lié à ce client.</p>
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
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Documents liés</p>
                                        <div className="grid grid-cols-2 gap-3">
                                            <DocMetric icon={FileText} label="Factures" value={totals.invoices} />
                                            <DocMetric icon={Truck} label="BL" value={totals.deliveryNotes} />
                                        </div>
                                    </div>
                                    <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-amber-700 mb-2">Prochaine évolution</p>
                                        <p className="text-sm font-bold text-amber-900">
                                            Ajouter une timeline d'échanges, relances et opportunités quand l'API CRM sera disponible.
                                        </p>
                                    </div>
                                </div>
                            </section>
                        </div>
                    )}
                </main>
            </div>
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

function DocMetric({ icon: Icon, label, value }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Icon className="w-4 h-4 text-slate-400 mb-2" />
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className="text-2xl font-black text-slate-900">{value}</p>
        </div>
    );
}
