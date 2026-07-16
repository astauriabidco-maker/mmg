import React, { useState } from 'react';
import { ShoppingCart, Plus, FileText, Search, ArrowRight, CheckCircle, PackageOpen, X, Truck, Users, Phone, Mail, MapPin, Sparkles, BrainCircuit, Building2 } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
const getStatusColor = (status) => {
    switch (status) {
        case 'DRAFT': return 'bg-slate-100 text-slate-600';
        case 'SENT': return 'bg-blue-100 text-blue-700';
        case 'PARTIAL': return 'bg-orange-100 text-orange-700';
        case 'RECEIVED': return 'bg-emerald-100 text-emerald-700';
        case 'CANCELLED': return 'bg-red-100 text-red-700';
        default: return 'bg-slate-100 text-slate-600';
    }
};

export default function PurchasesDashboard() {
    const [currentTab, setCurrentTab] = useState('orders'); // 'orders', 'suppliers', or 'partners'
    
    // Orders state
    const [searchTerm, setSearchTerm] = useState("");
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedPO, setSelectedPO] = useState(null);
    const [showReceiveModal, setShowReceiveModal] = useState(false);
    const [showSupplierInvoiceModal, setShowSupplierInvoiceModal] = useState(false);
    
    // Suppliers state
    const [selectedSupplierId, setSelectedSupplierId] = useState(null);
    
    // AI Recommendations state
    
    // Suppliers state
    const [showSupplierModal, setShowSupplierModal] = useState(false);
    const emptySupplierForm = {
        name: '',
        contact_name: '',
        email: '',
        phone: '',
        address: '',
        tax_id: '',
        website: '',
        payment_terms: '',
        lead_time_days: '',
        preferred_contact_method: 'email',
        notes: '',
    };
    const [newSupplier, setNewSupplier] = useState(emptySupplierForm);
    
    // Create form
    const emptyPOForm = { supplier: '', expected_date: '', notes: '', global_discount_percent: 0, lines: [] };
    const [newPO, setNewPO] = useState(emptyPOForm);
    
    // Receive form
    const [receiveTargetLoc, setReceiveTargetLoc] = useState('');
    const [receiveLines, setReceiveLines] = useState([]);
    const [supplierInvoiceRef, setSupplierInvoiceRef] = useState('');
    const [supplierInvoiceDueDate, setSupplierInvoiceDueDate] = useState('');
    const [supplierInvoiceNotes, setSupplierInvoiceNotes] = useState('');
    const [supplierInvoiceLines, setSupplierInvoiceLines] = useState([]);

    const queryClient = useQueryClient();

    const { data: purchases = [] } = useQuery({
        queryKey: ['purchases'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/');
            return res.data;
        }
    });

    const { data: suppliers = [] } = useQuery({
        queryKey: ['suppliers', 'v2'],
        queryFn: async () => {
            const res = await api.get('/v2/partners/suppliers');
            return res.data;
        }
    });

    const { data: variantsData = [] } = useQuery({
        queryKey: ['variants'],
        queryFn: async () => {
            const stockRes = await api.get('/v2/stock/products');
            const flatVariants = [];
            stockRes.data.forEach(p => {
                p.variants.forEach(v => {
                    flatVariants.push({ ...v, product_name: p.name });
                });
            });
            return flatVariants;
        }
    });

    const { data: locationsData = [] } = useQuery({
        queryKey: ['locations'],
        queryFn: async () => {
            const locRes = await api.get('/v2/stock/locations');
            return locRes.data.filter(l => l.usage === 'internal');
        }
    });

    const { data: aiRecommendations = [], isLoading: loadingAi, refetch: refetchAiRecommendations } = useQuery({
        queryKey: ['ai-recs'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/ai-recommendations');
            return res.data;
        },
        enabled: currentTab === 'ai'
    });

    const availableVariants = variantsData;
    const locations = locationsData;
    const selectedSupplier = suppliers.find(s => s.name === newPO.supplier);
    const poGrossTotal = newPO.lines.reduce((sum, line) => {
        const qty = parseFloat(line.quantity || 0);
        const price = parseFloat(line.unit_price || 0);
        return sum + (Number.isFinite(qty) && Number.isFinite(price) ? qty * price : 0);
    }, 0);
    const poLineDiscountTotal = newPO.lines.reduce((sum, line) => {
        const qty = parseFloat(line.quantity || 0);
        const price = parseFloat(line.unit_price || 0);
        const discount = Math.max(0, Math.min(parseFloat(line.discount_percent || 0), 100));
        const gross = Number.isFinite(qty) && Number.isFinite(price) ? qty * price : 0;
        return sum + gross * (discount / 100);
    }, 0);
    const poAfterLineDiscount = poGrossTotal - poLineDiscountTotal;
    const poGlobalDiscountPercent = Math.max(0, Math.min(parseFloat(newPO.global_discount_percent || 0), 100));
    const poGlobalDiscountAmount = poAfterLineDiscount * (poGlobalDiscountPercent / 100);
    const poSubtotal = poAfterLineDiscount - poGlobalDiscountAmount;
    const validLines = newPO.lines.filter(line => line.variant_id && parseFloat(line.quantity || 0) > 0).length;

    const handleCreateSupplier = async () => {
        try {
            const payload = {
                ...newSupplier,
                lead_time_days: newSupplier.lead_time_days === '' ? null : parseInt(newSupplier.lead_time_days, 10),
            };
            await api.post('/v2/partners/suppliers', payload);
            setShowSupplierModal(false);
            setNewSupplier(emptySupplierForm);
            queryClient.invalidateQueries(['suppliers', 'v2']);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la création du fournisseur.");
        }
    };

    const handleCreatePO = async () => {
        try {
            const lines = newPO.lines
                .filter(l => l.variant_id && parseFloat(l.quantity || 0) > 0)
                .map(l => ({
                variant_id: l.variant_id,
                quantity: parseFloat(l.quantity),
                unit_price: parseFloat(l.unit_price),
                discount_percent: Math.max(0, Math.min(parseFloat(l.discount_percent || 0), 100)),
            }));
            await api.post('/v2/purchases/', { ...newPO, lines });
            setShowCreateModal(false);
            setNewPO(emptyPOForm);
            queryClient.invalidateQueries(['purchases']);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la création de la commande.");
        }
    };

    const handleReceivePO = async () => {
        if (!receiveTargetLoc) {
            alert("Veuillez sélectionner un emplacement de destination.");
            return;
        }
        const lines = receiveLines
            .map(line => ({ line_id: line.line_id, quantity: parseFloat(line.quantity || 0) }))
            .filter(line => line.quantity > 0);
        if (lines.length === 0) {
            alert("Veuillez saisir au moins une quantité à réceptionner.");
            return;
        }
        try {
            await api.post(`/v2/purchases/${selectedPO.id}/receive`, { target_location_id: parseInt(receiveTargetLoc), lines });
            setShowReceiveModal(false);
            queryClient.invalidateQueries(['purchases']);
            await openPODetails(selectedPO.id);
            alert("Réception effectuée avec succès et stock mis à jour !");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la réception.");
        }
    };

    const openPODetails = async (po_id) => {
        try {
            const res = await api.get(`/v2/purchases/${po_id}`);
            setSelectedPO(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    const addLineToPO = () => {
        setNewPO({ ...newPO, lines: [...newPO.lines, { variant_id: '', quantity: 1, unit_price: 0, discount_percent: 0 }] });
    };
    
    const updateLine = (index, field, value) => {
        const newLines = [...newPO.lines];
        newLines[index][field] = value;
        if (field === 'variant_id') {
            const variant = availableVariants.find(v => String(v.id) === String(value));
            if (variant && (!newLines[index].unit_price || parseFloat(newLines[index].unit_price) === 0)) {
                newLines[index].unit_price = variant.cost_price || 0;
            }
        }
        setNewPO({ ...newPO, lines: newLines });
    };

    const removeLine = (index) => {
        const newLines = [...newPO.lines];
        newLines.splice(index, 1);
        setNewPO({ ...newPO, lines: newLines });
    };

    const openReceiveModal = () => {
        const lines = (selectedPO?.lines || [])
            .map(line => {
                const remaining = Math.max((line.quantity || 0) - (line.quantity_received || 0), 0);
                return {
                    line_id: line.id,
                    product_name: line.product_name,
                    variant_ref: line.variant_ref,
                    ordered: line.quantity || 0,
                    received: line.quantity_received || 0,
                    remaining,
                    quantity: remaining,
                };
            })
            .filter(line => line.remaining > 0);
        setReceiveTargetLoc('');
        setReceiveLines(lines);
        setShowReceiveModal(true);
    };

    const updateReceiveLine = (lineId, value) => {
        setReceiveLines(lines => lines.map(line => (
            line.line_id === lineId
                ? { ...line, quantity: Math.min(Math.max(parseFloat(value || 0), 0), line.remaining) }
                : line
        )));
    };

    const receiveQuantityTotal = receiveLines.reduce((sum, line) => sum + (parseFloat(line.quantity || 0) || 0), 0);

    const openSupplierInvoiceModal = () => {
        const lines = (selectedPO?.lines || [])
            .map(line => ({
                line_id: line.id,
                product_name: line.product_name,
                variant_ref: line.variant_ref,
                received: line.quantity_received || 0,
                invoiced: line.quantity_invoiced || 0,
                invoiceable: line.quantity_invoiceable || 0,
                quantity: line.quantity_invoiceable || 0,
            }))
            .filter(line => line.invoiceable > 0);
        setSupplierInvoiceRef('');
        setSupplierInvoiceDueDate('');
        setSupplierInvoiceNotes('');
        setSupplierInvoiceLines(lines);
        setShowSupplierInvoiceModal(true);
    };

    const updateSupplierInvoiceLine = (lineId, value) => {
        setSupplierInvoiceLines(lines => lines.map(line => (
            line.line_id === lineId
                ? { ...line, quantity: Math.min(Math.max(parseFloat(value || 0), 0), line.invoiceable) }
                : line
        )));
    };

    const supplierInvoiceQuantityTotal = supplierInvoiceLines.reduce((sum, line) => sum + (parseFloat(line.quantity || 0) || 0), 0);

    const handleCreateSupplierInvoice = async () => {
        const lines = supplierInvoiceLines
            .map(line => ({ purchase_order_line_id: line.line_id, quantity: parseFloat(line.quantity || 0) }))
            .filter(line => line.quantity > 0);
        if (lines.length === 0) {
            alert("Veuillez saisir au moins une quantité facturée.");
            return;
        }
        try {
            await api.post(`/v2/purchases/${selectedPO.id}/supplier-invoices`, {
                supplier_reference: supplierInvoiceRef,
                due_date: supplierInvoiceDueDate || null,
                notes: supplierInvoiceNotes,
                lines,
            });
            setShowSupplierInvoiceModal(false);
            queryClient.invalidateQueries(['purchases']);
            await openPODetails(selectedPO.id);
            alert("Facture fournisseur rapprochée avec les réceptions.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors du rapprochement facture fournisseur.");
        }
    };


    const filteredPurchases = purchases.filter(p => 
        p.reference.toLowerCase().includes(searchTerm.toLowerCase()) || 
        p.supplier.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="max-w-[1600px] h-[calc(100vh-100px)] mx-auto font-sans flex overflow-hidden bg-slate-50/50 border border-slate-200/60 rounded-[2rem] shadow-2xl animate-fade-in relative">
            
            {/* LEFT SIDEBAR : PO LIST */}
            <div className="w-[400px] bg-white border-r border-slate-200 flex flex-col items-stretch h-full shadow-xl z-20 relative">
                <div className="p-6 border-b border-slate-200 flex flex-col gap-4 relative z-10 bg-white">
                    <h3 className="font-black text-slate-900 flex items-center gap-3 tracking-tight text-xl">
                        <ShoppingCart className="text-blue-600 w-6 h-6"/> Achats & Appro.
                    </h3>
                    
                    {/* TABS */}
                    <div className="flex bg-slate-100 p-1 rounded-xl">
                        <button 
                            onClick={() => setCurrentTab('orders')}
                            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'orders' ? 'bg-white shadow text-blue-600' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Commandes
                        </button>
                        <button 
                            onClick={() => setCurrentTab('suppliers')}
                            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'suppliers' ? 'bg-white shadow text-emerald-600' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Fournisseurs
                        </button>
                        <button 
                            onClick={() => setCurrentTab('ai')}
                            className={`flex-1 py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'ai' ? 'bg-white shadow text-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}
                            title="Anticipation des Stocks"
                        >
                            <Sparkles className="w-4 h-4 mx-auto"/>
                        </button>
                    </div>

                    <div className="relative">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                        <input 
                            type="text" 
                            placeholder={currentTab === 'orders' ? "Rechercher Bon de Commande..." : currentTab === 'suppliers' ? "Rechercher Fournisseur..." : "Rechercher une recommandation..."} 
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                    {currentTab === 'orders' && (
                        <button onClick={() => setShowCreateModal(true)} className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <Plus className="w-5 h-5"/> Créer Commande
                        </button>
                    )}
                    {currentTab === 'suppliers' && (
                        <button onClick={() => setShowSupplierModal(true)} className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <Plus className="w-5 h-5"/> Nv. Fournisseur
                        </button>
                    )}
                    {currentTab === 'ai' && (
                        <button onClick={() => refetchAiRecommendations()} className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <BrainCircuit className="w-5 h-5"/> Relancer l'Analyse
                        </button>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {currentTab === 'orders' && (
                        <>
                            {filteredPurchases.map(po => (
                                <div 
                                    key={po.id} 
                                    onClick={() => openPODetails(po.id)}
                                    className={`p-4 rounded-xl cursor-pointer border-2 transition-all ${selectedPO?.id === po.id ? 'bg-blue-50 border-blue-500 shadow-md' : 'bg-white border-slate-100 hover:border-slate-300 shadow-sm'}`}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className="font-black text-slate-900">{po.reference}</span>
                                        <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-md ${getStatusColor(po.status)}`}>{po.status}</span>
                                    </div>
                                    <div className="flex justify-between items-center text-sm">
                                        <span className="font-bold text-slate-600">{po.supplier}</span>
                                        <span className="font-black text-slate-800">{po.total_amount.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span>
                                    </div>
                                    <div className="text-xs text-slate-400 mt-2 font-medium flex items-center gap-1">
                                        <FileText className="w-3 h-3"/> {po.lines_count} Lignes
                                    </div>
                                </div>
                            ))}
                            {filteredPurchases.length === 0 && (
                                <div className="text-center py-10 text-slate-400 font-bold">Aucune commande trouvée.</div>
                            )}
                        </>
                    )}
                    {currentTab === 'suppliers' && (
                        <>
                            {suppliers.filter(s => s.name.toLowerCase().includes(searchTerm.toLowerCase())).map(sup => (
                                <div 
                                    key={sup.id} 
                                    onClick={() => setSelectedSupplierId(sup.id)}
                                    className={`p-4 rounded-xl cursor-pointer border-2 transition-all ${selectedSupplierId === sup.id ? 'bg-emerald-50 border-emerald-500 shadow-md' : 'bg-white border-slate-100 hover:border-slate-300 shadow-sm'}`}
                                >
                                    <h4 className="font-black text-slate-800 text-lg flex items-center gap-2"><Truck className="w-4 h-4 text-emerald-500"/> {sup.name}</h4>
                                    <div className="mt-3 space-y-1">
                                        {sup.contact_name && <p className="text-xs text-slate-500 flex items-center gap-2"><Users className="w-3.5 h-3.5"/> {sup.contact_name}</p>}
                                        {sup.phone && <p className="text-xs text-slate-500 flex items-center gap-2"><Phone className="w-3.5 h-3.5"/> {sup.phone}</p>}
                                        {sup.email && <p className="text-xs text-slate-500 flex items-center gap-2"><Mail className="w-3.5 h-3.5"/> {sup.email}</p>}
                                    </div>
                                </div>
                            ))}
                            {suppliers.length === 0 && (
                                <div className="text-center py-10 text-slate-400 font-bold">Aucun fournisseur trouvé.</div>
                            )}
                        </>
                    )}
                    {currentTab === 'ai' && (
                        <div className="space-y-4">
                            {loadingAi ? (
                                <div className="text-center py-10 text-indigo-400 font-bold flex flex-col items-center">
                                    <BrainCircuit className="w-8 h-8 animate-pulse mb-2" />
                                    Analyse SCM en cours...
                                </div>
                            ) : (
                                <>
                                    {aiRecommendations.map((rec, idx) => (
                                        <div key={idx} className="p-4 rounded-xl bg-indigo-50 border border-indigo-100 shadow-sm relative overflow-hidden">
                                            <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
                                            <h4 className="font-black text-slate-800 text-sm flex items-start justify-between">
                                                <span>{rec.product_name}</span>
                                                <span className="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full">{rec.confidence}% IA</span>
                                            </h4>
                                            <p className="text-[10px] font-mono text-slate-500 mb-2">{rec.reference}</p>
                                            
                                            <div className="flex justify-between items-center mb-2 bg-white rounded-lg p-2 border border-indigo-50">
                                                <div className="text-center">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase">Stock Actuel</div>
                                                    <div className="font-black text-red-500">{rec.current_stock}</div>
                                                </div>
                                                <div className="text-center">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase">Qté Suggérée</div>
                                                    <div className="font-black text-indigo-600">+{rec.suggested_quantity}</div>
                                                </div>
                                            </div>
                                            
                                            <p className="text-xs text-slate-600 font-medium leading-tight">
                                                {rec.reason}
                                            </p>
                                            
                                            <button 
                                                onClick={() => {
                                                    setNewPO({ ...emptyPOForm, notes: 'Généré par IA SCM', lines: [{variant_id: rec.variant_id, quantity: rec.suggested_quantity, unit_price: 0, discount_percent: 0}] });
                                                    setShowCreateModal(true);
                                                }}
                                                className="mt-3 w-full py-2 bg-white border border-indigo-200 hover:bg-indigo-100 text-indigo-700 text-xs font-black rounded-lg transition-colors"
                                            >
                                                Préparer Commande
                                            </button>
                                        </div>
                                    ))}
                                    {aiRecommendations.length === 0 && (
                                        <div className="text-center py-10 text-slate-400 font-bold">Aucune recommandation critique. Stock optimal.</div>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* MAIN AREA : PO DETAILS */}
            <div className="flex-1 flex flex-col bg-slate-50 relative overflow-y-auto">
                {currentTab === 'suppliers' ? (
                    selectedSupplierId ? (
                        <SupplierProfile 
                            sup={suppliers.find(s => s.id === selectedSupplierId)} 
                            purchases={purchases} 
                            openPODetails={openPODetails} 
                            setCurrentTab={setCurrentTab} 
                        />
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                            <Building2 className="w-24 h-24 text-slate-200 mb-6" />
                            <h2 className="text-2xl font-black text-slate-500">Aucun fournisseur sélectionné</h2>
                            <p className="font-medium mt-2">Sélectionnez un fournisseur à gauche pour voir sa fiche et son historique.</p>
                        </div>
                    )
                ) : selectedPO ? (
                    <div className="p-8 max-w-4xl mx-auto w-full">
                        <div className="bg-white rounded-3xl shadow-xl border border-slate-200 overflow-hidden">
                            <div className="px-8 py-6 border-b border-slate-100 bg-slate-900 text-white flex justify-between items-start relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-48 h-48 bg-blue-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
                                <div className="relative z-10">
                                    <div className="flex items-center gap-3 mb-2">
                                        <h2 className="text-3xl font-black tracking-tight">{selectedPO.reference}</h2>
                                        <span className={`text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md ${getStatusColor(selectedPO.status)} border border-white/20`}>{selectedPO.status}</span>
                                    </div>
                                    <p className="text-lg font-medium text-slate-300">Fournisseur : <span className="font-bold text-white">{selectedPO.supplier}</span></p>
                                </div>
                                <div className="relative z-10 text-right flex flex-col justify-end items-end gap-2">
                                    <span className="text-sm font-bold text-slate-400">Total Commande</span>
                                    <span className="text-4xl font-black tracking-tight text-emerald-400">{selectedPO.total_amount.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span>
                                    <span className={`text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md ${selectedPO.supplier_invoice_status === 'FULL' ? 'bg-emerald-100 text-emerald-700' : selectedPO.supplier_invoice_status === 'PARTIAL' ? 'bg-orange-100 text-orange-700' : 'bg-slate-100 text-slate-600'}`}>
                                        Facture fournisseur {selectedPO.supplier_invoice_status === 'FULL' ? 'rapprochée' : selectedPO.supplier_invoice_status === 'PARTIAL' ? 'partielle' : 'à rapprocher'}
                                    </span>
                                </div>
                            </div>
                            
                            <div className="p-8">
                                <div className="grid grid-cols-3 gap-4 mb-8">
                                    <div className="rounded-2xl bg-blue-50 border border-blue-100 p-4">
                                        <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">Commandé</p>
                                        <p className="text-2xl font-black text-blue-700">{(selectedPO.lines || []).reduce((sum, line) => sum + Number(line.quantity || 0), 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-4">
                                        <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Réceptionné</p>
                                        <p className="text-2xl font-black text-emerald-700">{Number(selectedPO.quantity_received || 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-orange-50 border border-orange-100 p-4">
                                        <p className="text-[10px] font-black text-orange-500 uppercase tracking-widest">Facturé fournisseur</p>
                                        <p className="text-2xl font-black text-orange-700">{Number(selectedPO.quantity_invoiced || 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                </div>

                                <h4 className="font-black text-sm text-slate-400 uppercase tracking-widest mb-4">Lignes de Commande</h4>
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-slate-50 border-b border-slate-200">
                                        <tr>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Produit</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Prix Unitaire</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Commandé</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Reçu</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Facturé</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Total Ligne</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                            {selectedPO.lines && selectedPO.lines.map((line, idx) => (
                                            <tr key={idx} className="hover:bg-slate-50 transition-colors">
                                                <td className="py-4 px-4">
                                                    <span className="font-bold text-slate-800 block text-sm">{line.product_name}</span>
                                                    <span className="text-[10px] font-black text-slate-400 uppercase">{line.variant_ref}</span>
                                                </td>
                                                <td className="py-4 px-4 text-right font-mono text-sm">
                                                    {line.unit_price} €
                                                    {(line.discount_percent || 0) > 0 && <div className="text-[10px] text-emerald-600 font-black">-{line.discount_percent}%</div>}
                                                </td>
                                                <td className="py-4 px-4 text-center font-black text-blue-600 text-lg">{line.quantity}</td>
                                                <td className="py-4 px-4 text-center font-black text-emerald-600 text-lg">{line.quantity_received}</td>
                                                <td className="py-4 px-4 text-center">
                                                    <span className={`inline-flex px-2.5 py-1 rounded-lg text-sm font-black ${line.quantity_invoiced >= line.quantity_received && line.quantity_received > 0 ? 'bg-emerald-50 text-emerald-700' : line.quantity_invoiced > 0 ? 'bg-orange-50 text-orange-700' : 'bg-slate-50 text-slate-500'}`}>
                                                        {line.quantity_invoiced || 0}
                                                    </span>
                                                </td>
                                                <td className="py-4 px-4 text-right font-black text-slate-800 text-sm">{(line.line_total ?? line.quantity * line.unit_price).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>

                                <div className="mt-8 grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-4">
                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                                        <div className="flex items-center justify-between mb-4">
                                            <div>
                                                <h4 className="font-black text-slate-900">Factures fournisseur rapprochées</h4>
                                                <p className="text-xs font-bold text-slate-500">Contrôle : une facture ne peut pas dépasser les quantités réceptionnées.</p>
                                            </div>
                                            <span className="text-xs font-black text-slate-400">{selectedPO.supplier_invoices?.length || 0} facture(s)</span>
                                        </div>
                                        <div className="space-y-2">
                                            {(selectedPO.supplier_invoices || []).map(invoice => (
                                                <div key={invoice.id} className="bg-white border border-slate-200 rounded-xl p-3 flex items-center justify-between">
                                                    <div>
                                                        <p className="font-black text-slate-900">{invoice.supplier_reference || invoice.reference}</p>
                                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{invoice.reference} · {new Date(invoice.issue_date).toLocaleDateString('fr-FR')}</p>
                                                    </div>
                                                    <div className="text-right">
                                                        <p className="font-black text-slate-900">{Number(invoice.total_amount || 0).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</p>
                                                        <p className="text-[10px] font-black text-orange-600 uppercase tracking-widest">{invoice.status}</p>
                                                    </div>
                                                </div>
                                            ))}
                                            {(selectedPO.supplier_invoices || []).length === 0 && (
                                                <div className="text-sm font-bold text-slate-400">Aucune facture fournisseur rapprochée pour ce bon.</div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="rounded-2xl border border-orange-100 bg-orange-50 p-5">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-orange-500 mb-2">Reste facturable</p>
                                        <p className="text-3xl font-black text-orange-700">{Math.max(Number(selectedPO.quantity_received || 0) - Number(selectedPO.quantity_invoiced || 0), 0).toLocaleString('fr-FR')}</p>
                                        <button onClick={openSupplierInvoiceModal} disabled={Math.max(Number(selectedPO.quantity_received || 0) - Number(selectedPO.quantity_invoiced || 0), 0) <= 0} className="mt-4 w-full px-4 py-3 rounded-xl bg-orange-600 disabled:bg-slate-300 text-white font-black hover:bg-orange-500">
                                            Rapprocher facture
                                        </button>
                                    </div>
                                </div>

                                {(selectedPO.status === 'DRAFT' || selectedPO.status === 'SENT' || selectedPO.status === 'PARTIAL') && (
                                    <div className="mt-8 flex justify-end">
                                        <button onClick={openReceiveModal} className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-lg shadow-emerald-500/30 transition-all font-black flex items-center gap-2">
                                            <PackageOpen className="w-5 h-5"/> Réceptionner les Articles
                                        </button>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                        <ShoppingCart className="w-24 h-24 text-slate-200 mb-6" />
                        <h2 className="text-2xl font-black text-slate-500">Aucune commande sélectionnée</h2>
                        <p className="font-medium mt-2">Sélectionnez un bon de commande à gauche pour voir les détails.</p>
                    </div>
                )}
            </div>

            {/* CREATE MODAL */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-6xl w-full border border-slate-100 max-h-[92vh] flex flex-col overflow-hidden">
                        <div className="px-8 py-6 bg-slate-900 text-white flex justify-between items-start">
                            <div>
                                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-300/20 text-blue-200 text-[10px] font-black uppercase tracking-widest mb-3">
                                    <Plus className="w-3.5 h-3.5" /> Achat fournisseur
                                </div>
                                <h3 className="font-black text-3xl">Nouveau bon de commande</h3>
                                <p className="text-sm font-medium text-slate-300 mt-1">Sélection fournisseur, articles, prix et conditions avant validation.</p>
                            </div>
                            <button onClick={()=>setShowCreateModal(false)} className="text-slate-300 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="flex-1 overflow-y-auto bg-slate-50">
                            <div className="grid grid-cols-1 xl:grid-cols-[1.45fr_0.75fr] gap-6 p-8">
                                <div className="space-y-6">
                                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Fournisseur</label>
                                                <select value={newPO.supplier} onChange={e=>setNewPO({...newPO, supplier: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500">
                                                    <option value="">Choisir un fournisseur</option>
                                                    {suppliers.map(s => (
                                                        <option key={s.id} value={s.name}>{s.name}</option>
                                                    ))}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Livraison prévue</label>
                                                <input type="date" value={newPO.expected_date} onChange={e=>setNewPO({...newPO, expected_date: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"/>
                                            </div>
                                        </div>
                                        {selectedSupplier && (
                                            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
                                                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Contact</p>
                                                    <p className="font-black text-slate-800 truncate">{selectedSupplier.contact_name || selectedSupplier.email || 'Non renseigné'}</p>
                                                </div>
                                                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Délai moyen</p>
                                                    <p className="font-black text-slate-800">{selectedSupplier.lead_time_days ? `${selectedSupplier.lead_time_days} jours` : 'Non renseigné'}</p>
                                                </div>
                                                <div className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                                                    <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Paiement</p>
                                                    <p className="font-black text-slate-800 truncate">{selectedSupplier.payment_terms || 'Non renseigné'}</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                                        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                            <div>
                                                <h4 className="font-black text-slate-900">Articles commandés</h4>
                                                <p className="text-xs font-medium text-slate-500">{validLines}/{newPO.lines.length} ligne(s) prêtes</p>
                                            </div>
                                            <button type="button" onClick={addLineToPO} className="text-sm bg-blue-600 text-white px-4 py-2 rounded-xl font-black hover:bg-blue-500 flex items-center gap-2 shadow-sm">
                                                <Plus className="w-4 h-4"/> Ajouter une ligne
                                            </button>
                                        </div>
                                        <div className="p-4 space-y-3">
                                            {newPO.lines.map((line, idx) => {
                                                const variant = availableVariants.find(v => String(v.id) === String(line.variant_id));
                                                const quantity = parseFloat(line.quantity || 0) || 0;
                                                const unitPrice = parseFloat(line.unit_price || 0) || 0;
                                                const lineDiscount = Math.max(0, Math.min(parseFloat(line.discount_percent || 0), 100));
                                                const grossLineTotal = quantity * unitPrice;
                                                const lineTotal = grossLineTotal * (1 - lineDiscount / 100);
                                                return (
                                                    <div key={idx} className="grid grid-cols-[1fr_90px_120px_96px_128px_40px] gap-3 items-center bg-slate-50 p-3 rounded-xl border border-slate-200">
                                                        <div>
                                                            <select value={line.variant_id} onChange={e=>updateLine(idx, 'variant_id', e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 text-sm outline-none focus:ring-2 focus:ring-blue-500">
                                                                <option value="">Sélectionner un article du catalogue</option>
                                                                {availableVariants.map(v => (
                                                                    <option key={v.id} value={v.id}>{v.product_name} - {v.reference}</option>
                                                                ))}
                                                            </select>
                                                            {variant && (
                                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-1">
                                                                    {variant.reference} · stock actuel {variant.quantity_in_stock ?? 0}
                                                                </p>
                                                            )}
                                                        </div>
                                                        <div>
                                                            <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Qté</label>
                                                            <input type="number" min="0" placeholder="Qté" value={line.quantity} onChange={e=>updateLine(idx, 'quantity', e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl p-3 text-center font-black text-blue-600 outline-none focus:ring-2 focus:ring-blue-500"/>
                                                        </div>
                                                        <div>
                                                            <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Prix négocié</label>
                                                            <input type="number" min="0" step="0.01" placeholder="Prix U." value={line.unit_price} onChange={e=>updateLine(idx, 'unit_price', e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl p-3 text-center font-mono font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"/>
                                                        </div>
                                                        <div>
                                                            <label className="block text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Remise %</label>
                                                            <input type="number" min="0" max="100" step="0.1" value={line.discount_percent || 0} onChange={e=>updateLine(idx, 'discount_percent', e.target.value)} className="w-full bg-white border border-slate-200 rounded-xl p-3 text-center font-black text-emerald-600 outline-none focus:ring-2 focus:ring-emerald-500"/>
                                                        </div>
                                                        <div className="text-right pr-2">
                                                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Net ligne</p>
                                                            {lineDiscount > 0 && <p className="text-[10px] text-slate-400 line-through">{grossLineTotal.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</p>}
                                                            <p className="font-black text-slate-900">{lineTotal.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</p>
                                                        </div>
                                                        <button onClick={() => removeLine(idx)} className="p-2 text-red-400 hover:bg-red-50 rounded-lg"><X className="w-4 h-4"/></button>
                                                    </div>
                                                );
                                            })}
                                            {newPO.lines.length === 0 && (
                                                <button onClick={addLineToPO} className="w-full border-2 border-dashed border-slate-200 rounded-2xl py-10 text-slate-400 hover:text-blue-600 hover:border-blue-200 hover:bg-blue-50 font-black">
                                                    Ajouter le premier article
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Notes internes / conditions</label>
                                        <textarea value={newPO.notes} onChange={e=>setNewPO({...newPO, notes: e.target.value})} className="w-full min-h-[90px] bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 resize-none" placeholder="Référence fournisseur, urgence, consigne de livraison, conditions négociées..."/>
                                    </div>
                                </div>

                                <aside className="space-y-4">
                                    <div className="bg-slate-900 text-white rounded-2xl p-6 shadow-xl">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Net commande HT</p>
                                        <p className="text-4xl font-black">{poSubtotal.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</p>
                                        <div className="mt-5">
                                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1.5">Remise globale %</label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="100"
                                                step="0.1"
                                                value={newPO.global_discount_percent}
                                                onChange={e=>setNewPO({...newPO, global_discount_percent: e.target.value})}
                                                className="w-full bg-white/10 border border-white/10 rounded-xl p-3 text-white font-black outline-none focus:ring-2 focus:ring-blue-400"
                                            />
                                        </div>
                                        <div className="mt-5 space-y-2 text-sm font-bold text-slate-300">
                                            <div className="flex justify-between"><span>Brut articles</span><span>{poGrossTotal.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span></div>
                                            <div className="flex justify-between"><span>Remises lignes</span><span>-{poLineDiscountTotal.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span></div>
                                            <div className="flex justify-between"><span>Remise globale</span><span>-{poGlobalDiscountAmount.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span></div>
                                        </div>
                                        <div className="mt-5 grid grid-cols-2 gap-3">
                                            <div className="bg-white/10 rounded-xl p-3">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Lignes</p>
                                                <p className="text-xl font-black">{newPO.lines.length}</p>
                                            </div>
                                            <div className="bg-white/10 rounded-xl p-3">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Prêtes</p>
                                                <p className="text-xl font-black">{validLines}</p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
                                        <h4 className="font-black text-slate-900 mb-3">Contrôles avant validation</h4>
                                        <div className="space-y-3 text-sm font-bold">
                                            <div className={`flex items-center gap-2 ${newPO.supplier ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                <CheckCircle className="w-4 h-4" /> Fournisseur sélectionné
                                            </div>
                                            <div className={`flex items-center gap-2 ${validLines > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                <CheckCircle className="w-4 h-4" /> Au moins une ligne exploitable
                                            </div>
                                            <div className={`flex items-center gap-2 ${poSubtotal >= 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                                                <CheckCircle className="w-4 h-4" /> Montant calculé
                                            </div>
                                        </div>
                                    </div>
                                </aside>
                            </div>
                        </div>

                        <div className="px-8 py-5 bg-white border-t border-slate-100 flex justify-between items-center">
                            <button onClick={()=>setShowCreateModal(false)} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-black hover:bg-slate-50">Annuler</button>
                            <button onClick={handleCreatePO} disabled={!newPO.supplier || validLines === 0} className="px-8 py-4 bg-blue-600 disabled:bg-slate-300 hover:bg-blue-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg shrink-0">
                                Valider la commande
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* RECEIVE MODAL */}
            {showReceiveModal && selectedPO && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-4xl w-full border border-slate-100 overflow-hidden">
                        <div className="px-8 py-6 bg-slate-900 text-white flex justify-between items-start">
                            <div>
                                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-300/20 text-emerald-200 text-[10px] font-black uppercase tracking-widest mb-3">
                                    <Truck className="w-3.5 h-3.5"/> Réception fournisseur
                                </div>
                                <h3 className="font-black text-3xl">Réception partielle</h3>
                                <p className="text-sm font-medium text-slate-300 mt-1">{selectedPO.reference} · {selectedPO.supplier}</p>
                            </div>
                            <button onClick={()=>setShowReceiveModal(false)} className="text-slate-300 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="p-8 space-y-6 bg-slate-50">
                            <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-4">
                                <div className="bg-white rounded-2xl border border-slate-200 p-5">
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Emplacement de destination</label>
                                    <select value={receiveTargetLoc} onChange={e=>setReceiveTargetLoc(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                        <option value="">Choisir un entrepôt</option>
                                        {locations.map(l => (
                                            <option key={l.id} value={l.id}>{l.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="bg-emerald-600 text-white rounded-2xl p-5 shadow-lg">
                                    <p className="text-[10px] font-black text-emerald-100 uppercase tracking-widest">Total à recevoir</p>
                                    <p className="text-3xl font-black mt-2">{receiveQuantityTotal.toLocaleString('fr-FR')}</p>
                                    <p className="text-xs font-bold text-emerald-100 mt-1">{receiveLines.filter(l => parseFloat(l.quantity || 0) > 0).length} ligne(s)</p>
                                </div>
                            </div>

                            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                    <div>
                                        <h4 className="font-black text-slate-900">Lignes à réceptionner</h4>
                                        <p className="text-xs font-medium text-slate-500">Saisissez uniquement les quantités réellement arrivées.</p>
                                    </div>
                                    <button
                                        onClick={() => setReceiveLines(lines => lines.map(line => ({ ...line, quantity: line.remaining })))}
                                        className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 text-sm font-black hover:bg-slate-50"
                                    >
                                        Tout recevoir
                                    </button>
                                </div>
                                <div className="divide-y divide-slate-100">
                                    {receiveLines.map(line => (
                                        <div key={line.line_id} className="grid grid-cols-[1fr_110px_110px_130px] gap-4 items-center px-5 py-4">
                                            <div>
                                                <p className="font-black text-slate-900">{line.product_name}</p>
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{line.variant_ref}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Commandé</p>
                                                <p className="font-black text-slate-800">{Number(line.ordered || 0).toLocaleString('fr-FR')}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Reste</p>
                                                <p className="font-black text-orange-600">{Number(line.remaining || 0).toLocaleString('fr-FR')}</p>
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Reçu maintenant</label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={line.remaining}
                                                    step="0.01"
                                                    value={line.quantity}
                                                    onChange={e => updateReceiveLine(line.line_id, e.target.value)}
                                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-center font-black text-emerald-600 outline-none focus:ring-2 focus:ring-emerald-500"
                                                />
                                            </div>
                                        </div>
                                    ))}
                                    {receiveLines.length === 0 && (
                                        <div className="p-10 text-center text-slate-400 font-black">
                                            Toutes les lignes de ce bon sont déjà réceptionnées.
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="px-8 py-5 bg-white border-t border-slate-100 flex justify-between items-center">
                            <button onClick={()=>setShowReceiveModal(false)} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-black hover:bg-slate-50">Annuler</button>
                            <button onClick={handleReceivePO} disabled={!receiveTargetLoc || receiveQuantityTotal <= 0} className="px-8 py-4 bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                                Valider la réception
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SUPPLIER INVOICE MODAL */}
            {showSupplierInvoiceModal && selectedPO && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-4xl w-full border border-slate-100 overflow-hidden">
                        <div className="px-8 py-6 bg-slate-900 text-white flex justify-between items-start">
                            <div>
                                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-500/10 border border-orange-300/20 text-orange-200 text-[10px] font-black uppercase tracking-widest mb-3">
                                    <FileText className="w-3.5 h-3.5"/> Facture fournisseur
                                </div>
                                <h3 className="font-black text-3xl">Rapprocher une facture</h3>
                                <p className="text-sm font-medium text-slate-300 mt-1">{selectedPO.reference} · {selectedPO.supplier}</p>
                            </div>
                            <button onClick={()=>setShowSupplierInvoiceModal(false)} className="text-slate-300 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="p-8 space-y-6 bg-slate-50">
                            <div className="grid grid-cols-1 md:grid-cols-[1fr_220px_180px] gap-4">
                                <div className="bg-white rounded-2xl border border-slate-200 p-5">
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Référence facture fournisseur</label>
                                    <input value={supplierInvoiceRef} onChange={e=>setSupplierInvoiceRef(e.target.value)} placeholder="Ex: FAC-CORTIZO-2026-0716" className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-orange-500"/>
                                </div>
                                <div className="bg-white rounded-2xl border border-slate-200 p-5">
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Échéance</label>
                                    <input type="date" value={supplierInvoiceDueDate} onChange={e=>setSupplierInvoiceDueDate(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-orange-500"/>
                                </div>
                                <div className="bg-orange-600 text-white rounded-2xl p-5 shadow-lg">
                                    <p className="text-[10px] font-black text-orange-100 uppercase tracking-widest">Quantité facturée</p>
                                    <p className="text-3xl font-black mt-2">{supplierInvoiceQuantityTotal.toLocaleString('fr-FR')}</p>
                                    <p className="text-xs font-bold text-orange-100 mt-1">{supplierInvoiceLines.filter(l => parseFloat(l.quantity || 0) > 0).length} ligne(s)</p>
                                </div>
                            </div>

                            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                    <div>
                                        <h4 className="font-black text-slate-900">Lignes reçues à facturer</h4>
                                        <p className="text-xs font-medium text-slate-500">Le maximum correspond au réceptionné moins le déjà facturé.</p>
                                    </div>
                                    <button
                                        onClick={() => setSupplierInvoiceLines(lines => lines.map(line => ({ ...line, quantity: line.invoiceable })))}
                                        className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 text-sm font-black hover:bg-slate-50"
                                    >
                                        Tout facturer
                                    </button>
                                </div>
                                <div className="divide-y divide-slate-100">
                                    {supplierInvoiceLines.map(line => (
                                        <div key={line.line_id} className="grid grid-cols-[1fr_110px_110px_130px] gap-4 items-center px-5 py-4">
                                            <div>
                                                <p className="font-black text-slate-900">{line.product_name}</p>
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{line.variant_ref}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Reçu</p>
                                                <p className="font-black text-emerald-700">{Number(line.received || 0).toLocaleString('fr-FR')}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Facturable</p>
                                                <p className="font-black text-orange-600">{Number(line.invoiceable || 0).toLocaleString('fr-FR')}</p>
                                            </div>
                                            <div>
                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Facturé</label>
                                                <input
                                                    type="number"
                                                    min="0"
                                                    max={line.invoiceable}
                                                    step="0.01"
                                                    value={line.quantity}
                                                    onChange={e => updateSupplierInvoiceLine(line.line_id, e.target.value)}
                                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 text-center font-black text-orange-600 outline-none focus:ring-2 focus:ring-orange-500"
                                                />
                                            </div>
                                        </div>
                                    ))}
                                    {supplierInvoiceLines.length === 0 && (
                                        <div className="p-10 text-center text-slate-400 font-black">
                                            Rien à facturer : aucune réception non facturée.
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="bg-white rounded-2xl border border-slate-200 p-5">
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Notes rapprochement</label>
                                <textarea value={supplierInvoiceNotes} onChange={e=>setSupplierInvoiceNotes(e.target.value)} className="w-full min-h-[80px] bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-orange-500 resize-none" placeholder="Écart de prix, frais de port, remarque comptable..."/>
                            </div>
                        </div>

                        <div className="px-8 py-5 bg-white border-t border-slate-100 flex justify-between items-center">
                            <button onClick={()=>setShowSupplierInvoiceModal(false)} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-black hover:bg-slate-50">Annuler</button>
                            <button onClick={handleCreateSupplierInvoice} disabled={supplierInvoiceQuantityTotal <= 0} className="px-8 py-4 bg-orange-600 disabled:bg-slate-300 hover:bg-orange-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                                Valider le rapprochement
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SUPPLIER MODAL */}
            {showSupplierModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-4xl w-full border border-slate-100 overflow-hidden">
                        <div className="flex justify-between items-center mb-6">
                            <div className="px-8 pt-8">
                                <h3 className="font-black text-2xl flex items-center gap-3">
                                    <Truck className="w-6 h-6 text-emerald-600"/> Nouveau Fournisseur
                                </h3>
                                <p className="text-sm font-medium text-slate-500 mt-1">Créez une fiche exploitable pour achats, réception et suivi fournisseur.</p>
                            </div>
                            <button onClick={()=>setShowSupplierModal(false)} className="mr-6 mt-6 text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        
                        <div className="px-8 pb-8 grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-6">
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Nom d'entreprise requis</label>
                                    <input type="text" value={newSupplier.name} onChange={e=>setNewSupplier({...newSupplier, name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Ex: CORTIZO SA"/>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Contact principal</label>
                                        <input type="text" value={newSupplier.contact_name} onChange={e=>setNewSupplier({...newSupplier, contact_name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Nom prénom"/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Téléphone</label>
                                        <input type="text" value={newSupplier.phone} onChange={e=>setNewSupplier({...newSupplier, phone: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="+33..."/>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Email achats</label>
                                        <input type="email" value={newSupplier.email} onChange={e=>setNewSupplier({...newSupplier, email: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="contact@..."/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Site web / portail</label>
                                        <input type="text" value={newSupplier.website} onChange={e=>setNewSupplier({...newSupplier, website: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="https://..."/>
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Adresse fournisseur</label>
                                    <input type="text" value={newSupplier.address} onChange={e=>setNewSupplier({...newSupplier, address: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Adresse complète"/>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">SIRET / TVA</label>
                                        <input type="text" value={newSupplier.tax_id} onChange={e=>setNewSupplier({...newSupplier, tax_id: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="FR..."/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Délai moyen</label>
                                        <input type="number" min="0" value={newSupplier.lead_time_days} onChange={e=>setNewSupplier({...newSupplier, lead_time_days: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="jours"/>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Paiement</label>
                                        <input type="text" value={newSupplier.payment_terms} onChange={e=>setNewSupplier({...newSupplier, payment_terms: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="30j fin de mois"/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Contact préféré</label>
                                        <select value={newSupplier.preferred_contact_method} onChange={e=>setNewSupplier({...newSupplier, preferred_contact_method: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                            <option value="email">Email</option>
                                            <option value="phone">Téléphone</option>
                                            <option value="portal">Portail fournisseur</option>
                                        </select>
                                    </div>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Notes achats</label>
                                    <textarea value={newSupplier.notes} onChange={e=>setNewSupplier({...newSupplier, notes: e.target.value})} className="w-full min-h-[94px] bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500 resize-none" placeholder="Conditions, gamme, interlocuteur, contraintes livraison..."/>
                                </div>
                            </div>
                        </div>

                        <div className="px-8 py-5 bg-slate-50 border-t border-slate-100 flex justify-between items-center">
                            <p className="text-xs font-bold text-slate-500">La fiche sera disponible pour les bons de commande et le suivi fournisseur.</p>
                            <button onClick={handleCreateSupplier} disabled={!newSupplier.name} className="px-8 py-4 bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                                Enregistrer la fiche
                            </button>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
}

const SupplierProfile = ({ sup, purchases, openPODetails, setCurrentTab }) => {
    const [activeTab, setActiveTab] = useState('overview');

    const supOrders = purchases.filter(p => p.supplier === sup.name);
    const totalSpent = supOrders.reduce((sum, order) => sum + (order.total_amount || 0), 0);
    const totalOrders = supOrders.length;
    const receivedOrders = supOrders.filter(o => o.status === 'RECEIVED').length;
    const pendingOrders = supOrders.filter(o => o.status !== 'RECEIVED' && o.status !== 'CANCELLED').length;
    
    // Average order value
    const avgOrderValue = totalOrders > 0 ? (totalSpent / totalOrders) : 0;
    const openWebsite = () => {
        if (!sup.website) return;
        const url = sup.website.startsWith('http') ? sup.website : `https://${sup.website}`;
        window.open(url, '_blank', 'noopener,noreferrer');
    };

    return (
        <div className="flex flex-col h-full bg-slate-50 relative overflow-hidden animate-fade-in">
            {/* TOP HEADER - Full Width */}
            <div className="bg-slate-900 text-white shrink-0 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
                <div className="absolute bottom-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl translate-y-1/2 -translate-x-1/3"></div>
                
                <div className="px-10 pt-12 pb-6 relative z-10 max-w-6xl mx-auto w-full">
                    <div className="flex items-start gap-8">
                        <div className="w-28 h-28 rounded-3xl bg-gradient-to-br from-emerald-400 to-emerald-600 text-white flex items-center justify-center font-black text-5xl shadow-2xl shadow-emerald-500/30 border-4 border-emerald-300/30 shrink-0">
                            {sup.name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 mt-2">
                            <div className="flex items-center gap-4 mb-2">
                                <h2 className="text-4xl font-black tracking-tight">{sup.name}</h2>
                                {sup.customer_type && (
                                    <span className="bg-white/10 text-emerald-300 border border-emerald-400/30 px-3 py-1 rounded-full text-xs font-black uppercase tracking-widest">
                                        {sup.customer_type}
                                    </span>
                                )}
                            </div>
                            <div className="flex items-center gap-6 text-slate-300 font-medium">
                                {sup.tax_id && (
                                    <div className="flex items-center gap-2">
                                        <Building2 className="w-4 h-4 text-slate-500" /> SIRET: {sup.tax_id}
                                    </div>
                                )}
                                {sup.contact_name && (
                                    <div className="flex items-center gap-2">
                                        <Users className="w-4 h-4 text-slate-500" /> {sup.contact_name}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="text-right mt-2 flex flex-col items-end">
                            <button onClick={() => setCurrentTab('orders')} className="bg-white/10 hover:bg-white/20 border border-white/10 text-white px-6 py-3 rounded-xl font-bold transition-all shadow-lg flex items-center gap-2">
                                <FileText className="w-4 h-4" /> Nouveau Bon
                            </button>
                            <span className="text-xs text-slate-400 mt-3 font-medium">Créé le {new Date(sup.created_at || Date.now()).toLocaleDateString('fr-FR')}</span>
                        </div>
                    </div>

                    {/* Navigation Tabs */}
                    <div className="flex items-center gap-8 mt-10 border-b border-white/10">
                        <button onClick={() => setActiveTab('overview')} className={`pb-4 px-2 text-sm font-bold uppercase tracking-widest transition-all ${activeTab === 'overview' ? 'text-emerald-400 border-b-2 border-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}>
                            Vue d'Ensemble
                        </button>
                        <button onClick={() => setActiveTab('orders')} className={`pb-4 px-2 text-sm font-bold uppercase tracking-widest transition-all ${activeTab === 'orders' ? 'text-emerald-400 border-b-2 border-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}>
                            Commandes ({totalOrders})
                        </button>
                        <button onClick={() => setActiveTab('analytics')} className={`pb-4 px-2 text-sm font-bold uppercase tracking-widest transition-all ${activeTab === 'analytics' ? 'text-emerald-400 border-b-2 border-emerald-400' : 'text-slate-400 hover:text-slate-200'}`}>
                            Analytics
                        </button>
                    </div>
                </div>
            </div>

            {/* TAB CONTENT */}
            <div className="flex-1 overflow-y-auto">
                <div className="max-w-6xl mx-auto w-full p-10 space-y-8">
                    
                    {activeTab === 'overview' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            {/* KPI Row */}
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                                            <ShoppingCart className="w-5 h-5 text-blue-600" />
                                        </div>
                                    </div>
                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Total Dépensé</p>
                                    <h3 className="text-2xl font-black text-slate-800">{totalSpent.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</h3>
                                </div>
                                
                                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center">
                                            <PackageOpen className="w-5 h-5 text-orange-600" />
                                        </div>
                                    </div>
                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Commandes en Cours</p>
                                    <h3 className="text-2xl font-black text-slate-800">{pendingOrders}</h3>
                                </div>

                                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center">
                                            <CheckCircle className="w-5 h-5 text-emerald-600" />
                                        </div>
                                    </div>
                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Total Réceptionné</p>
                                    <h3 className="text-2xl font-black text-slate-800">{receivedOrders}</h3>
                                </div>

                                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
                                            <Sparkles className="w-5 h-5 text-indigo-600" />
                                        </div>
                                    </div>
                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Panier Moyen</p>
                                    <h3 className="text-2xl font-black text-slate-800">{avgOrderValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</h3>
                                </div>
                            </div>

                            {/* Contact & Info */}
                            <div className="grid grid-cols-1 md:grid-cols-[1fr_0.8fr] gap-8">
                                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                                    <div className="p-6 border-b border-slate-100 bg-slate-50">
                                        <h3 className="font-black text-slate-800 flex items-center gap-2"><Users className="w-5 h-5 text-slate-400"/> Contact & raccourcis</h3>
                                    </div>
                                    <div className="p-6 space-y-6">
                                        <div className="grid grid-cols-2 gap-3">
                                            <a href={sup.phone ? `tel:${sup.phone}` : undefined} className={`px-4 py-3 rounded-xl border text-sm font-black flex items-center justify-center gap-2 ${sup.phone ? 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'border-slate-100 bg-slate-50 text-slate-300 pointer-events-none'}`}>
                                                <Phone className="w-4 h-4" /> Appeler
                                            </a>
                                            <a href={sup.email ? `mailto:${sup.email}` : undefined} className={`px-4 py-3 rounded-xl border text-sm font-black flex items-center justify-center gap-2 ${sup.email ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100' : 'border-slate-100 bg-slate-50 text-slate-300 pointer-events-none'}`}>
                                                <Mail className="w-4 h-4" /> Écrire
                                            </a>
                                            <button onClick={openWebsite} disabled={!sup.website} className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-slate-700 disabled:text-slate-300 disabled:bg-slate-50 text-sm font-black flex items-center justify-center gap-2 hover:bg-slate-50">
                                                <Building2 className="w-4 h-4" /> Portail
                                            </button>
                                            <a href={sup.address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(sup.address)}` : undefined} target="_blank" rel="noreferrer" className={`px-4 py-3 rounded-xl border text-sm font-black flex items-center justify-center gap-2 ${sup.address ? 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50' : 'border-slate-100 bg-slate-50 text-slate-300 pointer-events-none'}`}>
                                                <MapPin className="w-4 h-4" /> Itinéraire
                                            </a>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                                                    <Users className="w-5 h-5 text-slate-500" />
                                                </div>
                                                <div>
                                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-0.5">Contact Principal</p>
                                                    <p className="font-bold text-slate-800">{sup.contact_name || 'Non renseigné'}</p>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                                                    <Phone className="w-5 h-5 text-slate-500" />
                                                </div>
                                                <div>
                                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-0.5">Téléphone</p>
                                                    <p className="font-bold text-slate-800">{sup.phone || 'Non renseigné'}</p>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-4">
                                                <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                                                    <Mail className="w-5 h-5 text-slate-500" />
                                                </div>
                                                <div>
                                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-0.5">Email</p>
                                                    <p className="font-bold text-blue-600 hover:underline cursor-pointer">{sup.email || 'Non renseigné'}</p>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
                                    <div className="p-6 border-b border-slate-100 bg-slate-50">
                                        <h3 className="font-black text-slate-800 flex items-center gap-2"><MapPin className="w-5 h-5 text-slate-400"/> Conditions achats</h3>
                                    </div>
                                    <div className="p-6 flex-1">
                                        <div className="grid grid-cols-2 gap-4 mb-6">
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Délai moyen</p>
                                                <p className="font-black text-slate-800">{sup.lead_time_days ? `${sup.lead_time_days} j` : 'Non renseigné'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Paiement</p>
                                                <p className="font-black text-slate-800">{sup.payment_terms || 'Non renseigné'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Contact</p>
                                                <p className="font-black text-slate-800">{sup.preferred_contact_method || 'Non renseigné'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Site</p>
                                                <p className="font-black text-slate-800 truncate">{sup.website || 'Non renseigné'}</p>
                                            </div>
                                        </div>
                                        <div className="text-center p-6 bg-slate-50 rounded-2xl border border-slate-100 mb-6">
                                            <MapPin className="w-8 h-8 text-slate-300 mx-auto mb-3" />
                                            <p className="font-bold text-slate-600">{sup.address || 'Aucune adresse renseignée.'}</p>
                                        </div>
                                        {sup.tax_id && (
                                            <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-4 flex items-center gap-4">
                                                <Building2 className="w-6 h-6 text-emerald-500" />
                                                <div>
                                                    <p className="text-[10px] font-black text-emerald-600 uppercase tracking-widest">Numéro SIRET / TVA</p>
                                                    <p className="font-black text-emerald-900">{sup.tax_id}</p>
                                                </div>
                                            </div>
                                        )}
                                        {sup.notes && (
                                            <div className="bg-amber-50 border border-amber-100 rounded-2xl p-4 mt-4">
                                                <p className="text-[10px] font-black text-amber-700 uppercase tracking-widest mb-2">Notes achats</p>
                                                <p className="font-bold text-amber-950 whitespace-pre-wrap">{sup.notes}</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {activeTab === 'orders' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            {supOrders.length > 0 ? (
                                <div className="bg-white rounded-3xl shadow-sm border border-slate-200 overflow-hidden">
                                    <table className="w-full text-left border-collapse">
                                        <thead className="bg-slate-50 border-b border-slate-200">
                                            <tr>
                                                <th className="py-4 px-6 text-[10px] font-black text-slate-500 uppercase tracking-widest">Référence</th>
                                                <th className="py-4 px-6 text-[10px] font-black text-slate-500 uppercase tracking-widest">Date / Lignes</th>
                                                <th className="py-4 px-6 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Statut</th>
                                                <th className="py-4 px-6 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Montant</th>
                                                <th className="py-4 px-6"></th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100">
                                            {supOrders.map(order => (
                                                <tr key={order.id} className="hover:bg-slate-50 transition-colors group">
                                                    <td className="py-4 px-6 font-black text-slate-900">{order.reference}</td>
                                                    <td className="py-4 px-6">
                                                        <span className="block font-bold text-slate-600">{new Date(order.created_at || Date.now()).toLocaleDateString('fr-FR')}</span>
                                                        <span className="text-xs text-slate-400 font-medium">{order.lines_count} articles</span>
                                                    </td>
                                                    <td className="py-4 px-6 text-center">
                                                        <span className={`text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md ${getStatusColor(order.status)}`}>{order.status}</span>
                                                    </td>
                                                    <td className="py-4 px-6 text-right font-black text-slate-800">
                                                        {order.total_amount.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}
                                                    </td>
                                                    <td className="py-4 px-6 text-right">
                                                        <button 
                                                            onClick={() => {
                                                                setCurrentTab('orders');
                                                                openPODetails(order.id);
                                                            }}
                                                            className="p-2 bg-white border border-slate-200 text-blue-600 hover:bg-blue-50 hover:border-blue-200 rounded-lg opacity-0 group-hover:opacity-100 transition-all shadow-sm flex items-center gap-2 ml-auto"
                                                        >
                                                            <ArrowRight className="w-4 h-4" /> Voir Détails
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : (
                                <div className="bg-white rounded-3xl border border-slate-200 p-16 text-center flex flex-col items-center justify-center shadow-sm">
                                    <PackageOpen className="w-16 h-16 text-slate-200 mb-4" />
                                    <h3 className="font-black text-slate-800 text-2xl mb-2">Aucune commande</h3>
                                    <p className="font-medium text-slate-500 max-w-md">Vous n'avez pas encore passé de commande auprès de ce fournisseur.</p>
                                    <button className="mt-6 bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-3 rounded-xl font-black shadow-lg shadow-emerald-500/30 flex items-center gap-2 transition-all">
                                        <Plus className="w-5 h-5"/> Créer un Bon de Commande
                                    </button>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'analytics' && (
                        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                            <div className="bg-white rounded-3xl border border-slate-200 p-16 text-center flex flex-col items-center justify-center shadow-sm">
                                <BrainCircuit className="w-16 h-16 text-indigo-200 mb-4" />
                                <h3 className="font-black text-slate-800 text-2xl mb-2">Analyse SCM & Performance</h3>
                                <p className="font-medium text-slate-500 max-w-md">Les métriques avancées (délais de livraison moyens, taux de conformité, évolution des prix) seront bientôt disponibles pour ce fournisseur.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
