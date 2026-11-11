import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { 
    FileText, Download, CheckCircle, Clock, AlertTriangle, Search, Plus, CreditCard, BellRing, Undo2
} from 'lucide-react';
import api from '../services/api';
import { invoiceAccounting, accountingTotals } from '../utils/accounting';
import { openPdfWithFeedback, downloadFileWithFeedback } from '../services/pdf';
import { useAuth } from '../context/AuthContext';

export default function AccountingDashboard() {
    const queryClient = useQueryClient();
    const { user } = useAuth();
    const canEdit = user?.permissions?.includes('*') || user?.permissions?.includes('ACC_EDIT');

    const { data: invoices = [], isLoading, isError, refetch } = useQuery({
        queryKey: ['invoices'],
        queryFn: async () => {
            const res = await api.get('/v2/accounting/invoices');
            return res.data;
        }
    });

    const [searchParams] = useSearchParams();
    const [searchTerm, setSearchTerm] = useState(() => searchParams.get('invoice') || '');
    const [statusFilter, setStatusFilter] = useState("ALL");

    const [showPaymentModal, setShowPaymentModal] = useState(false);
    const [selectedInvoice, setSelectedInvoice] = useState(null);
    const [paymentData, setPaymentData] = useState({ amount: 0, method: "VIREMENT", reference: "" });

    const [showNewInvoiceModal, setShowNewInvoiceModal] = useState(false);
    const [newInvoiceData, setNewInvoiceData] = useState({
        client_name: '',
        client_address: '',
        client_siret: '',
        due_date: new Date(new Date().setDate(new Date().getDate() + 30)).toISOString().split('T')[0],
        description: '',
        quantity: 1,
        unit_price: 0,
        tax_rate: 20
    });

    const handleExportFEC = () => {
        downloadFileWithFeedback('/v2/accounting/export/fec', 'export-fec.txt');
    };

    const handlePaymentSubmit = async () => {
        const current = invoices.find(invoice => invoice.id === selectedInvoice?.id);
        const balance = current && invoiceAccounting(current);
        if (!balance?.canPay || !Number.isFinite(paymentData.amount) || paymentData.amount <= 0 || paymentData.amount > balance.due) {
            return alert("Paiement impossible ou montant supérieur au solde restant dû.");
        }
        
        try {
            await api.post(`/v2/accounting/invoices/${selectedInvoice.id}/pay`, paymentData);
            setShowPaymentModal(false);
            queryClient.invalidateQueries({ queryKey: ['invoices'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Erreur de paiement");
        }
    };

    const handleCreateInvoice = async (e) => {
        e.preventDefault();
        try {
            await api.post('/v2/accounting/invoices', {
                client_name: newInvoiceData.client_name,
                client_address: newInvoiceData.client_address,
                client_siret: newInvoiceData.client_siret,
                due_date: new Date(newInvoiceData.due_date).toISOString(),
                lines: [{
                    description: newInvoiceData.description,
                    quantity: parseFloat(newInvoiceData.quantity),
                    unit_price: parseFloat(newInvoiceData.unit_price),
                    tax_rate: parseFloat(newInvoiceData.tax_rate)
                }]
            });
            setShowNewInvoiceModal(false);
            setNewInvoiceData({
                client_name: '', client_address: '', client_siret: '',
                due_date: new Date(new Date().setDate(new Date().getDate() + 30)).toISOString().split('T')[0],
                description: '', quantity: 1, unit_price: 0, tax_rate: 20
            });
            queryClient.invalidateQueries({ queryKey: ['invoices'] });
        } catch (e) {
            alert(e.response?.data?.detail || 'Erreur lors de la création de la facture');
        }
    };

    const handleCreditNote = async (inv) => {
        if (!invoiceAccounting(inv).canCredit) return;
        if (!window.confirm(`Émettre un avoir pour la facture ${inv.reference} ? Cela l'annulera comptablement.`)) return;
        try {
            await api.post(`/v2/accounting/invoices/${inv.id}/credit_note`);
            alert('Avoir généré avec succès !');
            queryClient.invalidateQueries({ queryKey: ['invoices'] });
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur lors de la création de l'avoir.");
        }
    };

    const handleRemind = async (inv) => {
        if (!invoiceAccounting(inv).canRemind) return;
        try {
            await api.post(`/v2/accounting/invoices/${inv.id}/remind`);
            alert(`Relance envoyée au client pour la facture ${inv.reference} !`);
        } catch (e) {
            alert(e.response?.data?.detail || 'Erreur lors de la relance');
        }
    };

    const openPaymentModal = (inv) => {
        const balance = invoiceAccounting(inv);
        if (!balance.canPay) return;
        const remainder = balance.due;
        setSelectedInvoice(inv);
        setPaymentData({ amount: remainder, method: "VIREMENT", reference: "" });
        setShowPaymentModal(true);
    };

    const filteredInvoices = invoices.filter(inv => {
        const matchSearch = inv.reference.toLowerCase().includes(searchTerm.toLowerCase()) || 
                            inv.client_name.toLowerCase().includes(searchTerm.toLowerCase());
        const balance = invoiceAccounting(inv);
        const matchStatus = statusFilter === 'ALL'
            || (statusFilter === 'DUE' && balance.due > 0)
            || (statusFilter === 'CUSTOMER_CREDIT' && balance.credit > 0)
            || balance.status === statusFilter;
        return matchSearch && matchStatus;
    });

    const totals = accountingTotals(invoices);
    const money = value => Number(value || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const metrics = [
        { label: 'Facturé net TTC', value: totals.revenue },
        { label: 'Encaissé', value: totals.paid },
        { label: 'Reste dû', value: totals.due },
        { label: 'Crédit client', value: totals.credit },
    ];

    return (
        <div className="space-y-5 w-full h-[calc(100vh-80px)] overflow-y-auto p-4 pb-12 bg-slate-50 md:p-6">
            <dl className="grid grid-cols-2 gap-3 xl:grid-cols-4">
                {metrics.map(metric => (
                    <div key={metric.label} className="rounded-xl border border-slate-200 bg-white p-4">
                        <dt className="text-sm font-bold text-slate-600">{metric.label}</dt>
                        <dd className="mt-2 text-xl font-black tabular-nums text-slate-900 sm:text-2xl">{isLoading || isError ? '—' : money(metric.value)}</dd>
                    </div>
                ))}
            </dl>
            {isError && (
                <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
                    Impossible de charger les factures. <button type="button" className="font-bold underline" onClick={() => refetch()}>Réessayer</button>
                </p>
            )}

            {/* MAIN LIST */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-6 border-b border-slate-100 flex flex-wrap gap-4 items-center justify-between bg-slate-50/50">
                    <div className="flex flex-1 flex-wrap items-center gap-3">
                        <div className="relative min-w-52 flex-1">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <input 
                                type="text"
                                placeholder="Rechercher une facture (N°, Client)..."
                                className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-xl focus:ring-2 ring-blue-500/20 outline-none text-sm"
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                            />
                        </div>
                        <select 
                            className="border border-slate-200 rounded-xl px-4 py-2 text-sm text-slate-600 font-bold bg-white outline-none focus:ring-2 ring-blue-500/20"
                            aria-label="Filtrer les factures"
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                        >
                            <option value="ALL">Toutes les pièces</option>
                            <option value="DUE">Reste à encaisser</option>
                            <option value="CUSTOMER_CREDIT">Crédits clients</option>
                            <option value="UNPAID">Non Payé</option>
                            <option value="PARTIAL">Paiement Partiel</option>
                            <option value="PAID">Payé</option>
                            <option value="AVOIR">Avoir</option>
                            <option value="CREDITED">Facture créditée</option>
                            <option value="PARTIALLY_CREDITED">Facture partiellement créditée</option>
                        </select>
                        {canEdit && <button
                            onClick={() => setShowNewInvoiceModal(true)}
                            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-xl shadow-sm transition-colors flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4" /> Nouvelle facture
                        </button>}
                        {canEdit && <button type="button" onClick={handleExportFEC} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50">
                            <Download className="h-4 w-4" /> Export FEC
                        </button>}
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400 font-bold border-b border-slate-100">
                                <th className="p-4">N° Facture</th>
                                <th className="p-4">Date & Client</th>
                                <th className="p-4">Statut</th>
                                <th className="p-4 text-right">Montant TTC</th>
                                <th className="p-4 text-right">Encaissé</th>
                                <th className="p-4 text-right">Solde</th>
                                <th className="p-4 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="text-sm">
                            {filteredInvoices.map((inv) => {
                                const balance = invoiceAccounting(inv);
                                const remainder = balance.due;

                                return (
                                    <tr key={inv.id} className="border-b border-slate-50 hover:bg-slate-50/50 transition-colors">
                                        <td className="p-4 font-mono font-bold text-slate-700">
                                            {inv.reference}
                                            {inv.qr_code_hash && <div className="text-[9px] text-slate-300 font-normal truncate max-w-[100px]" title={inv.qr_code_hash}>NF525 Sealed</div>}
                                        </td>
                                        <td className="p-4">
                                            <p className="font-bold text-slate-800">{inv.client_name}</p>
                                            <p className="text-xs text-slate-500">{new Date(inv.issue_date).toLocaleDateString('fr-FR')}</p>
                                        </td>
                                        <td className="p-4">
                                            {['CREDITED', 'PARTIALLY_CREDITED'].includes(balance.status) && <span className="bg-slate-200 text-slate-700 px-2 py-1 rounded text-xs font-bold">{balance.status === 'CREDITED' ? 'CRÉDITÉE' : 'PARTIELLEMENT CRÉDITÉE'}</span>}
                                            {balance.status === "PAID" && <span className="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><CheckCircle className="w-3 h-3"/> PAYÉ</span>}
                                            {balance.status === "PARTIAL" && <span className="bg-orange-100 text-orange-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><Clock className="w-3 h-3"/> PAYÉ EN PARTIE</span>}
                                            {balance.status === "UNPAID" && <span className="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><AlertTriangle className="w-3 h-3"/> EN ATTENTE</span>}
                                            {balance.status === "AVOIR" && <span className="bg-slate-200 text-slate-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><Undo2 className="w-3 h-3"/> AVOIR</span>}
                                        </td>
                                        <td className="p-4 text-right font-black text-slate-800">
                                            {money(inv.total)}
                                        </td>
                                        <td className="p-4 text-right tabular-nums text-slate-700">
                                            {balance.status === 'AVOIR' ? '—' : money(inv.total_paid)}
                                        </td>
                                        <td className="p-4 text-right font-bold text-slate-500">
                                            {remainder > 0 ? <span className="text-red-500">{remainder.toLocaleString('fr-FR', {minimumFractionDigits: 2})} €</span> : "0,00 €"}
                                            {balance.credit > 0 && <p className="mt-1 text-xs text-indigo-700">Crédit client {money(balance.credit)}</p>}
                                            {balance.refund > 0 && <p className="text-xs text-indigo-600">À rembourser : {balance.refund.toLocaleString('fr-FR')} € (non enregistré)</p>}
                                            {balance.status === 'AVOIR' && inv.source_invoice_reference && <p className="text-xs">Sur {inv.source_invoice_reference}</p>}
                                        </td>
                                        <td className="p-4 text-center">
                                            <div className="flex justify-center gap-2">
                                                {canEdit && balance.canRemind && (
                                                    <button 
                                                        onClick={() => handleRemind(inv)}
                                                        className="p-2 bg-orange-50 text-orange-600 hover:bg-orange-600 hover:text-white rounded-lg transition-colors"
                                                        title="Envoyer une relance (Email/SMS)"
                                                    >
                                                        <BellRing className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canEdit && balance.canPay && (
                                                    <button 
                                                        onClick={() => openPaymentModal(inv)}
                                                        className="p-2 bg-blue-50 text-blue-600 hover:bg-blue-600 hover:text-white rounded-lg transition-colors"
                                                        title="Ajouter un paiement / acompte"
                                                    >
                                                        <CreditCard className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {canEdit && balance.canCredit && (
                                                    <button 
                                                        onClick={() => handleCreditNote(inv)}
                                                        className="p-2 bg-red-50 text-red-600 hover:bg-red-600 hover:text-white rounded-lg transition-colors"
                                                        title="Générer un Avoir comptable"
                                                    >
                                                        <Undo2 className="w-4 h-4" />
                                                    </button>
                                                )}
                                                <button 
                                                    onClick={() => openPdfWithFeedback(`/v2/pdf/invoice/${inv.id}`)}
                                                    className="p-2 bg-slate-100 text-slate-500 hover:bg-slate-200 rounded-lg transition-colors"
                                                    title="Télécharger la facture PDF"
                                                >
                                                    <FileText className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    {filteredInvoices.length === 0 && !isLoading && !isError && (
                        <div className="p-12 text-center text-slate-400">
                            Aucune facture trouvée.
                        </div>
                    )}
                </div>
            </div>

            {/* PAYMENT MODAL */}
            {canEdit && showPaymentModal && selectedInvoice && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-[2rem] max-w-md w-full p-8 shadow-2xl animate-fade-in-up">
                        <h3 className="text-2xl font-black text-slate-800 mb-2">Nouvel Encaissement</h3>
                        <p className="text-slate-500 text-sm mb-6">Facture {selectedInvoice.reference} - {selectedInvoice.client_name}</p>
                        
                        <div className="space-y-4 mb-8">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Montant (€)</label>
                                <input 
                                    type="number" min="0.01" step="0.01" max={invoiceAccounting(invoices.find(inv => inv.id === selectedInvoice.id) || selectedInvoice).due}
                                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl font-black text-xl text-slate-800 outline-none focus:border-blue-500"
                                    value={paymentData.amount}
                                    onChange={(e) => setPaymentData({...paymentData, amount: parseFloat(e.target.value)})}
                                />
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Moyen de paiement</label>
                                <select 
                                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700 outline-none focus:border-blue-500"
                                    value={paymentData.method}
                                    onChange={(e) => setPaymentData({...paymentData, method: e.target.value})}
                                >
                                    <option value="VIREMENT">Virement Bancaire</option>
                                    <option value="CB">Carte Bancaire</option>
                                    <option value="CHEQUE">Chèque</option>
                                    <option value="ESPECES">Espèces</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Référence (Trx, N° Chèque...)</label>
                                <input 
                                    type="text" 
                                    className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-700 outline-none focus:border-blue-500"
                                    value={paymentData.reference}
                                    onChange={(e) => setPaymentData({...paymentData, reference: e.target.value})}
                                />
                            </div>
                        </div>

                        <div className="flex gap-4">
                            <button 
                                onClick={() => setShowPaymentModal(false)}
                                className="flex-1 py-4 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl transition-colors"
                            >
                                Annuler
                            </button>
                            <button 
                                onClick={handlePaymentSubmit}
                                className="flex-1 py-4 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl shadow-lg transition-colors"
                            >
                                Valider
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* NEW INVOICE MODAL */}
            {canEdit && showNewInvoiceModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-[2rem] max-w-2xl w-full p-8 shadow-2xl animate-fade-in-up max-h-[90vh] overflow-y-auto">
                        <h3 className="text-2xl font-black text-slate-800 mb-6 flex items-center gap-2">
                            <FileText className="w-6 h-6 text-blue-500" /> Nouvelle Facture
                        </h3>
                        
                        <form onSubmit={handleCreateInvoice} className="space-y-6">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="col-span-2 md:col-span-1">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Client *</label>
                                    <input 
                                        type="text" required
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.client_name}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, client_name: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-2 md:col-span-1">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">SIRET</label>
                                    <input 
                                        type="text" 
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.client_siret}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, client_siret: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Adresse</label>
                                    <input 
                                        type="text" 
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.client_address}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, client_address: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-2 md:col-span-1">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Date d'échéance *</label>
                                    <input 
                                        type="date" required
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.due_date}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, due_date: e.target.value})}
                                    />
                                </div>
                            </div>
                            
                            <hr className="border-slate-100" />
                            
                            <h4 className="font-bold text-slate-700">Ligne de Facturation (Simplifiée)</h4>
                            <div className="grid grid-cols-12 gap-4">
                                <div className="col-span-12 md:col-span-5">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Description *</label>
                                    <input 
                                        type="text" required
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.description}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, description: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-4 md:col-span-2">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Qté *</label>
                                    <input 
                                        type="number" required step="0.01"
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.quantity}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, quantity: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-4 md:col-span-3">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">P.U HT *</label>
                                    <input 
                                        type="number" required step="0.01"
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.unit_price}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, unit_price: e.target.value})}
                                    />
                                </div>
                                <div className="col-span-4 md:col-span-2">
                                    <label className="block text-xs font-bold text-slate-400 uppercase mb-2">TVA (%) *</label>
                                    <input 
                                        type="number" required step="0.1"
                                        className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 outline-none focus:border-blue-500"
                                        value={newInvoiceData.tax_rate}
                                        onChange={(e) => setNewInvoiceData({...newInvoiceData, tax_rate: e.target.value})}
                                    />
                                </div>
                            </div>
                            
                            <div className="flex justify-end gap-4 mt-8">
                                <button 
                                    type="button"
                                    onClick={() => setShowNewInvoiceModal(false)}
                                    className="px-6 py-4 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-xl transition-colors"
                                >
                                    Annuler
                                </button>
                                <button 
                                    type="submit"
                                    className="px-6 py-4 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl shadow-lg transition-colors"
                                >
                                    Créer la facture
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

        </div>
    );
}
