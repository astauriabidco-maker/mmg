import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
    FileText, Download, CheckCircle, Clock, AlertTriangle, Filter, Search, Plus, CreditCard, Banknote, BellRing, Undo2
} from 'lucide-react';
import api from '../services/api';
import { openPdfWithFeedback, downloadFileWithFeedback } from '../services/pdf';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function AccountingDashboard() {
    const queryClient = useQueryClient();

    const { data: invoices = [], isLoading } = useQuery({
        queryKey: ['invoices'],
        queryFn: async () => {
            const res = await api.get('/v2/accounting/invoices');
            return res.data;
        }
    });

    const [searchTerm, setSearchTerm] = useState("");
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
        if (!paymentData.amount || paymentData.amount <= 0) return alert("Montant invalide");
        
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
        try {
            await api.post(`/v2/accounting/invoices/${inv.id}/remind`);
            alert(`Relance envoyée au client pour la facture ${inv.reference} !`);
        } catch (e) {
            alert('Erreur lors de la relance');
        }
    };

    const openPaymentModal = (inv) => {
        const totalPaid = inv.payments.reduce((acc, p) => acc + p.amount, 0);
        const remainder = inv.total - totalPaid;
        setSelectedInvoice(inv);
        setPaymentData({ amount: remainder, method: "VIREMENT", reference: "" });
        setShowPaymentModal(true);
    };

    const filteredInvoices = invoices.filter(inv => {
        const matchSearch = inv.reference.toLowerCase().includes(searchTerm.toLowerCase()) || 
                            inv.client_name.toLowerCase().includes(searchTerm.toLowerCase());
        const matchStatus = statusFilter === "ALL" || inv.status === statusFilter;
        return matchSearch && matchStatus;
    });

    const totalUnpaid = invoices.filter(i => i.status !== "PAID").reduce((acc, i) => acc + (i.total - i.payments.reduce((s, p)=>s+p.amount, 0)), 0);
    const totalRevenue = invoices.filter(i => i.status !== "DRAFT").reduce((acc, i) => acc + i.total, 0);

    return (
        <div className="space-y-6 max-w-7xl mx-auto animate-fade-in pb-12">
            
            {/* KPI ROW */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Chiffre d'Affaires</p>
                        <h2 className="text-3xl font-black text-slate-800">{totalRevenue.toLocaleString('fr-FR')} €</h2>
                    </div>
                    <div className="w-12 h-12 bg-blue-50 text-blue-500 rounded-full flex items-center justify-center">
                        <Banknote className="w-6 h-6" />
                    </div>
                </div>

                <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Restant Dû (Créances)</p>
                        <h2 className="text-3xl font-black text-red-600">{totalUnpaid.toLocaleString('fr-FR')} €</h2>
                    </div>
                    <div className="w-12 h-12 bg-red-50 text-red-500 rounded-full flex items-center justify-center">
                        <AlertTriangle className="w-6 h-6" />
                    </div>
                </div>

                <div className="bg-gradient-to-r from-indigo-600 to-blue-700 p-6 rounded-2xl shadow-lg flex flex-col justify-center items-start text-white">
                    <p className="text-sm font-bold text-indigo-100 mb-2">Clôture Comptable</p>
                    <button 
                        onClick={handleExportFEC}
                        className="w-full bg-white text-indigo-700 font-black py-3 rounded-xl shadow-md hover:scale-105 transition-transform flex items-center justify-center gap-2"
                    >
                        <Download className="w-5 h-5"/>
                        Export FEC (Norme FR)
                    </button>
                </div>
            </div>

            {/* MAIN LIST */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="p-6 border-b border-slate-100 flex flex-wrap gap-4 items-center justify-between bg-slate-50/50">
                    <div className="flex gap-4 flex-1 min-w-[300px]">
                        <div className="relative flex-1">
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
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                        >
                            <option value="ALL">Tous les statuts</option>
                            <option value="UNPAID">Non Payé</option>
                            <option value="PARTIAL">Paiement Partiel</option>
                            <option value="PAID">Payé</option>
                            <option value="AVOIR">Avoir (Annulé)</option>
                        </select>
                        <button 
                            onClick={() => setShowNewInvoiceModal(true)}
                            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-xl shadow-sm transition-colors flex items-center gap-2"
                        >
                            <Plus className="w-4 h-4" /> Nouvelle Facture
                        </button>
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
                                <th className="p-4 text-right">Reste à payer</th>
                                <th className="p-4 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="text-sm">
                            {filteredInvoices.map((inv) => {
                                const totalPaid = inv.payments.reduce((acc, p) => acc + p.amount, 0);
                                const remainder = inv.total - totalPaid;

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
                                            {inv.status === "PAID" && <span className="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><CheckCircle className="w-3 h-3"/> PAYÉ</span>}
                                            {inv.status === "PARTIAL" && <span className="bg-orange-100 text-orange-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><Clock className="w-3 h-3"/> ACOMPTE</span>}
                                            {inv.status === "UNPAID" && <span className="bg-red-100 text-red-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><AlertTriangle className="w-3 h-3"/> EN ATTENTE</span>}
                                            {inv.status === "AVOIR" && <span className="bg-slate-200 text-slate-700 px-2 py-1 rounded text-xs font-bold flex items-center w-max gap-1"><Undo2 className="w-3 h-3"/> AVOIR</span>}
                                        </td>
                                        <td className="p-4 text-right font-black text-slate-800">
                                            {inv.total.toLocaleString('fr-FR', {minimumFractionDigits: 2})} €
                                        </td>
                                        <td className="p-4 text-right font-bold text-slate-500">
                                            {remainder > 0 && inv.status !== "AVOIR" ? <span className="text-red-500">{remainder.toLocaleString('fr-FR', {minimumFractionDigits: 2})} €</span> : "-"}
                                        </td>
                                        <td className="p-4 text-center">
                                            <div className="flex justify-center gap-2">
                                                {(inv.status === "UNPAID" || inv.status === "PARTIAL") && (
                                                    <button 
                                                        onClick={() => handleRemind(inv)}
                                                        className="p-2 bg-orange-50 text-orange-600 hover:bg-orange-600 hover:text-white rounded-lg transition-colors"
                                                        title="Envoyer une relance (Email/SMS)"
                                                    >
                                                        <BellRing className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {inv.status !== "PAID" && inv.status !== "AVOIR" && (
                                                    <button 
                                                        onClick={() => openPaymentModal(inv)}
                                                        className="p-2 bg-blue-50 text-blue-600 hover:bg-blue-600 hover:text-white rounded-lg transition-colors"
                                                        title="Ajouter un paiement / acompte"
                                                    >
                                                        <CreditCard className="w-4 h-4" />
                                                    </button>
                                                )}
                                                {inv.status !== "AVOIR" && (
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
                    {filteredInvoices.length === 0 && !isLoading && (
                        <div className="p-12 text-center text-slate-400">
                            Aucune facture trouvée.
                        </div>
                    )}
                </div>
            </div>

            {/* PAYMENT MODAL */}
            {showPaymentModal && selectedInvoice && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-[2rem] max-w-md w-full p-8 shadow-2xl animate-fade-in-up">
                        <h3 className="text-2xl font-black text-slate-800 mb-2">Nouvel Encaissement</h3>
                        <p className="text-slate-500 text-sm mb-6">Facture {selectedInvoice.reference} - {selectedInvoice.client_name}</p>
                        
                        <div className="space-y-4 mb-8">
                            <div>
                                <label className="block text-xs font-bold text-slate-400 uppercase mb-2">Montant (€)</label>
                                <input 
                                    type="number" 
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
            {showNewInvoiceModal && (
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
