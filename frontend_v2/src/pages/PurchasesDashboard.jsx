import React, { useState } from 'react';
import { ShoppingCart, Plus, FileText, Search, ArrowRight, CheckCircle, PackageOpen, X, Truck, Users, Phone, Mail, MapPin, Sparkles, BrainCircuit, Building2 } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import PartnerDirectory from '../components/PartnerDirectory';

export default function PurchasesDashboard() {
    const [currentTab, setCurrentTab] = useState('orders'); // 'orders', 'suppliers', or 'partners'
    
    // Orders state
    const [searchTerm, setSearchTerm] = useState("");
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedPO, setSelectedPO] = useState(null);
    const [showReceiveModal, setShowReceiveModal] = useState(false);
    
    // AI Recommendations state
    
    // Suppliers state
    const [showSupplierModal, setShowSupplierModal] = useState(false);
    const [newSupplier, setNewSupplier] = useState({ name: '', contact_name: '', email: '', phone: '', address: '', tax_id: '' });
    
    // Create form
    const [newPO, setNewPO] = useState({ supplier: '', expected_date: '', notes: '', lines: [] });
    
    // Receive form
    const [receiveTargetLoc, setReceiveTargetLoc] = useState('');

    const queryClient = useQueryClient();

    const { data: purchases = [] } = useQuery({
        queryKey: ['purchases'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/');
            return res.data;
        }
    });

    const { data: suppliers = [] } = useQuery({
        queryKey: ['suppliers'],
        queryFn: async () => {
            const res = await api.get('/v2/suppliers/');
            return res.data;
        }
    });

    const { data: variantsData = [] } = useQuery({
        queryKey: ['variants'],
        queryFn: async () => {
            const stockRes = await api.get('/v2/stock/');
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

    const { data: aiRecommendations = [], isLoading: loadingAi } = useQuery({
        queryKey: ['ai-recs'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/ai-recommendations');
            return res.data;
        },
        enabled: currentTab === 'ai'
    });

    const availableVariants = variantsData;
    const locations = locationsData;

    const handleCreateSupplier = async () => {
        try {
            await api.post('/v2/suppliers/', newSupplier);
            setShowSupplierModal(false);
            setNewSupplier({ name: '', contact_name: '', email: '', phone: '', address: '', tax_id: '' });
            queryClient.invalidateQueries(['suppliers']);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la création du fournisseur.");
        }
    };

    const handleCreatePO = async () => {
        try {
            const lines = newPO.lines.map(l => ({
                variant_id: l.variant_id,
                quantity: parseFloat(l.quantity),
                unit_price: parseFloat(l.unit_price)
            }));
            await api.post('/v2/purchases/', { ...newPO, lines });
            setShowCreateModal(false);
            setNewPO({ supplier: '', expected_date: '', notes: '', lines: [] });
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
        try {
            await api.post(`/v2/purchases/${selectedPO.id}/receive`, { target_location_id: parseInt(receiveTargetLoc) });
            setShowReceiveModal(false);
            setSelectedPO(null);
            queryClient.invalidateQueries(['purchases']);
            alert("Réception effectuée avec succès et stock mis à jour !");
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la réception.");
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
        setNewPO({ ...newPO, lines: [...newPO.lines, { variant_id: '', quantity: 1, unit_price: 0 }] });
    };
    
    const updateLine = (index, field, value) => {
        const newLines = [...newPO.lines];
        newLines[index][field] = value;
        setNewPO({ ...newPO, lines: newLines });
    };

    const removeLine = (index) => {
        const newLines = [...newPO.lines];
        newLines.splice(index, 1);
        setNewPO({ ...newPO, lines: newLines });
    };

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
                            placeholder={currentTab === 'orders' ? "Rechercher Bon de Commande..." : "Rechercher Fournisseur..."} 
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
                        <button onClick={fetchAiRecommendations} className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
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
                                <div key={sup.id} className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm">
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
                                                    setNewPO({ supplier: '', expected_date: '', notes: 'Généré par IA SCM', lines: [{variant_id: rec.variant_id, quantity: rec.suggested_quantity, unit_price: 0}] });
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
                    <div className="h-full">
                        <PartnerDirectory type="SUPPLIER" />
                    </div>
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
                                </div>
                            </div>
                            
                            <div className="p-8">
                                <h4 className="font-black text-sm text-slate-400 uppercase tracking-widest mb-4">Lignes de Commande</h4>
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-slate-50 border-b border-slate-200">
                                        <tr>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Produit</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Prix Unitaire</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Commandé</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Reçu</th>
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
                                                <td className="py-4 px-4 text-right font-mono text-sm">{line.unit_price} €</td>
                                                <td className="py-4 px-4 text-center font-black text-blue-600 text-lg">{line.quantity}</td>
                                                <td className="py-4 px-4 text-center font-black text-emerald-600 text-lg">{line.quantity_received}</td>
                                                <td className="py-4 px-4 text-right font-black text-slate-800 text-sm">{(line.quantity * line.unit_price).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>

                                {(selectedPO.status === 'DRAFT' || selectedPO.status === 'SENT' || selectedPO.status === 'PARTIAL') && (
                                    <div className="mt-8 flex justify-end">
                                        <button onClick={() => setShowReceiveModal(true)} className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl shadow-lg shadow-emerald-500/30 transition-all font-black flex items-center gap-2">
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
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-4xl w-full border border-slate-100 max-h-[90vh] flex flex-col">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl flex items-center gap-3">
                                <Plus className="w-6 h-6 text-blue-600"/> Nouveau Bon de Commande
                            </h3>
                            <button onClick={()=>setShowCreateModal(false)} className="text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        
                        <div className="grid grid-cols-2 gap-4 mb-6 shrink-0">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Fournisseur</label>
                                <select value={newPO.supplier} onChange={e=>setNewPO({...newPO, supplier: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500">
                                    <option value="">-- Choisir dans le catalogue --</option>
                                    {suppliers.map(s => (
                                        <option key={s.id} value={s.name}>{s.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Date de Livraison Prévue</label>
                                <input type="date" value={newPO.expected_date} onChange={e=>setNewPO({...newPO, expected_date: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"/>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto mb-6 bg-slate-50 border border-slate-200 rounded-2xl p-4">
                            <h4 className="font-black text-sm text-slate-500 uppercase tracking-widest mb-4 flex justify-between items-center">
                                Lignes (<span className="text-blue-600">{newPO.lines.length}</span>)
                                <button type="button" onClick={addLineToPO} className="text-xs bg-white border border-slate-200 px-3 py-1.5 rounded-lg text-blue-600 hover:bg-blue-50 flex items-center gap-1 shadow-sm">
                                    <Plus className="w-3 h-3"/> Ajouter Ligne
                                </button>
                            </h4>
                            <div className="space-y-3">
                                {newPO.lines.map((line, idx) => (
                                    <div key={idx} className="flex gap-3 items-center bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
                                        <div className="flex-1">
                                            <select value={line.variant_id} onChange={e=>updateLine(idx, 'variant_id', e.target.value)} className="w-full bg-transparent font-bold text-slate-800 text-sm outline-none">
                                                <option value="">-- Sélectionner Article --</option>
                                                {availableVariants.map(v => (
                                                    <option key={v.id} value={v.id}>{v.product_name} - {v.reference}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="w-24">
                                            <input type="number" placeholder="Qté" value={line.quantity} onChange={e=>updateLine(idx, 'quantity', e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 text-center font-black text-blue-600"/>
                                        </div>
                                        <div className="w-24">
                                            <input type="number" placeholder="Prix U." value={line.unit_price} onChange={e=>updateLine(idx, 'unit_price', e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 text-center font-mono text-slate-600"/>
                                        </div>
                                        <button onClick={() => removeLine(idx)} className="p-2 text-red-400 hover:bg-red-50 rounded-lg"><X className="w-4 h-4"/></button>
                                    </div>
                                ))}
                                {newPO.lines.length === 0 && (
                                    <div className="text-center py-6 text-slate-400 font-bold text-sm">
                                        Cliquez sur "Ajouter Ligne" pour commencer.
                                    </div>
                                )}
                            </div>
                        </div>

                        <button onClick={handleCreatePO} disabled={!newPO.supplier || newPO.lines.length === 0} className="w-full py-4 bg-blue-600 disabled:bg-slate-300 hover:bg-blue-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg shrink-0">
                            Valider la Commande
                        </button>
                    </div>
                </div>
            )}

            {/* RECEIVE MODAL */}
            {showReceiveModal && selectedPO && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-md w-full border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl flex items-center gap-3">
                                <Truck className="w-6 h-6 text-emerald-600"/> Réceptionner
                            </h3>
                            <button onClick={()=>setShowReceiveModal(false)} className="text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        <p className="text-sm font-bold text-slate-500 mb-6">
                            La réception complète ajoutera les stocks en attente du Bon de Commande <span className="text-slate-900">{selectedPO.reference}</span> vers l'entrepôt physique choisi.
                        </p>
                        <div className="mb-6">
                            <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Emplacement de Destination</label>
                            <select value={receiveTargetLoc} onChange={e=>setReceiveTargetLoc(e.target.value)} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                <option value="">-- Choisir un entrepôt --</option>
                                {locations.map(l => (
                                    <option key={l.id} value={l.id}>{l.name}</option>
                                ))}
                            </select>
                        </div>
                        <button onClick={handleReceivePO} disabled={!receiveTargetLoc} className="w-full py-4 bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                            Confirmer la Réception
                        </button>
                    </div>
                </div>
            )}

            {/* SUPPLIER MODAL */}
            {showSupplierModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl flex items-center gap-3">
                                <Truck className="w-6 h-6 text-emerald-600"/> Nouveau Fournisseur
                            </h3>
                            <button onClick={()=>setShowSupplierModal(false)} className="text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        
                        <div className="space-y-4 mb-6">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Nom d'Entreprise (Requis)</label>
                                <input type="text" value={newSupplier.name} onChange={e=>setNewSupplier({...newSupplier, name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Ex: CORTIZO SA"/>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Contact Principal</label>
                                    <input type="text" value={newSupplier.contact_name} onChange={e=>setNewSupplier({...newSupplier, contact_name: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Nom prénom"/>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Téléphone</label>
                                    <input type="text" value={newSupplier.phone} onChange={e=>setNewSupplier({...newSupplier, phone: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="+33..."/>
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Email</label>
                                <input type="email" value={newSupplier.email} onChange={e=>setNewSupplier({...newSupplier, email: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="contact@..."/>
                            </div>
                        </div>

                        <button onClick={handleCreateSupplier} disabled={!newSupplier.name} className="w-full py-4 bg-emerald-600 disabled:bg-slate-300 hover:bg-emerald-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                            Enregistrer au Catalogue
                        </button>
                    </div>
                </div>
            )}

        </div>
    );
}
