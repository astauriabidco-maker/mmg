import React, { useState } from 'react';
import { Users, FileText, Search, ArrowRight, CheckCircle, X, DollarSign, Send, Clock, AlertTriangle, FileCheck, Plus, ListTodo, UploadCloud, Copy, Sparkles, BrainCircuit } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import MMGDossiers from './MMGDossiers';
import WindowVisualizer from '../components/WindowVisualizer';
import PartnerDirectory from '../components/PartnerDirectory';

export default function SalesDashboard() {
    const queryClient = useQueryClient();
    
    const [mainTab, setMainTab] = useState('pipeline'); // 'pipeline' | 'dossiers' | 'partners'
    const [pipelineView, setPipelineView] = useState('kanban'); // 'list' | 'kanban'
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedSale, setSelectedSale] = useState(null);
    const [isStatusUpdating, setIsStatusUpdating] = useState(false);
    const [isUploadingBOM, setIsUploadingBOM] = useState(false);

    // AI Copilot State
    const [showAIModal, setShowAIModal] = useState(false);
    const [aiPrompt, setAiPrompt] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);

    const { data: sales = [], isLoading: isLoadingSales } = useQuery({
        queryKey: ['sales'],
        queryFn: async () => {
            const res = await api.get('/v2/sales/');
            return res.data;
        }
    });

    const { data: serverStages = [], refetch: refetchStages } = useQuery({
        queryKey: ['pipelineStages'],
        queryFn: async () => {
            const res = await api.get('/v2/sales/stages');
            return res.data;
        }
    });

    const [pipelineStages, setPipelineStages] = useState([]);
    
    // Sync local state with server state
    React.useEffect(() => {
        if (serverStages && serverStages.length > 0) {
            setPipelineStages(serverStages);
        }
    }, [serverStages]);

    const saveStagesToServer = async (newStages) => {
        setPipelineStages(newStages);
        try {
            await api.post('/v2/sales/stages', newStages);
            queryClient.invalidateQueries(['pipelineStages']);
        } catch (err) {
            console.error("Erreur lors de la sauvegarde des étapes", err);
            alert("Erreur lors de la sauvegarde des étapes du pipeline.");
        }
    };

    const handleAddStage = () => {
        const newStage = { id: `STAGE_${Date.now()}`, title: "Nouvelle Étape" };
        const newStages = [...pipelineStages, newStage];
        saveStagesToServer(newStages);
    };

    const handleRenameStage = (id, newTitle) => {
        const newStages = pipelineStages.map(s => s.id === id ? { ...s, title: newTitle } : s);
        saveStagesToServer(newStages);
    };

    const handleDeleteStage = (id) => {
        if (!window.confirm("Êtes-vous sûr de vouloir supprimer cette étape ?")) return;
        const newStages = pipelineStages.filter(s => s.id !== id);
        saveStagesToServer(newStages);
    };

    const openSaleDetails = async (sale_id) => {
        try {
            const res = await api.get(`/v2/sales/${sale_id}`);
            setSelectedSale(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    const updateStatus = async (newStatus) => {
        if(!selectedSale) return;
        setIsStatusUpdating(true);
        try {
            await api.put(`/v2/sales/${selectedSale.id}/status?status=${newStatus}`);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la mise à jour du statut");
        } finally {
            setIsStatusUpdating(false);
        }
    };

    const handleDragStart = (e, id) => {
        e.dataTransfer.setData("saleId", id.toString());
    };
    const handleDragOver = (e) => e.preventDefault();
    const handleDrop = async (e, newStatus) => {
        e.preventDefault();
        const saleId = e.dataTransfer.getData("saleId");
        if (saleId) {
            setIsStatusUpdating(true);
            try {
                await api.put(`/v2/sales/${saleId}/status?status=${newStatus}`);
                queryClient.invalidateQueries(['sales']);
                if (selectedSale && selectedSale.id.toString() === saleId) {
                    openSaleDetails(saleId);
                }
            } catch (err) {
                console.error(err);
                alert("Erreur lors de la mise à jour du statut");
            } finally {
                setIsStatusUpdating(false);
            }
        }
    };

    const validateSale = async () => {
        if(!selectedSale) return;
        setIsStatusUpdating(true);
        try {
            await api.put(`/v2/sales/${selectedSale.id}/status?status=VALIDATED`);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de la validation");
        } finally {
            setIsStatusUpdating(false);
        }
    };

    const handleAIGenerate = async () => {
        if (!aiPrompt.trim()) return;
        setIsGenerating(true);
        try {
            const res = await api.post('/v2/sales/ai-quote', { prompt: aiPrompt });
            
            if (res.data.type === 'stages_updated') {
                setShowAIModal(false);
                setAiPrompt('');
                queryClient.invalidateQueries(['pipelineStages']);
                alert(res.data.message);
            } else {
                const quoteDraft = res.data.quote || res.data;
                const createRes = await api.post('/v2/sales/', quoteDraft);
                
                setShowAIModal(false);
                setAiPrompt('');
                queryClient.invalidateQueries(['sales']);
                openSaleDetails(createRes.data.id);
                alert("Devis généré avec succès par l'IA !");
            }
        } catch (err) {
            console.error("AI Error:", err);
            alert("Erreur lors de l'opération avec l'IA.");
        } finally {
            setIsGenerating(false);
        }
    };
    const sendToDesign = async () => {
        if(!selectedSale) return;
        setIsStatusUpdating(true);
        try {
            await api.put(`/v2/sales/${selectedSale.id}/status?status=IN_DESIGN`);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
        } catch (err) {
            console.error(err);
            alert("Erreur lors de l'envoi au BE");
        } finally {
            setIsStatusUpdating(false);
        }
    };

    const launchProduction = async () => {
        if(!selectedSale) return;
        setIsStatusUpdating(true);
        try {
            await api.post(`/v2/sales/${selectedSale.id}/launch-production`);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
            alert("✅ Dossier lancé en production avec succès ! Les fiches de suivi ont été générées.");
        } catch (err) {
            console.error(err);
            alert("Erreur lors du lancement en production");
        } finally {
            setIsStatusUpdating(false);
        }
    };

    const generateMetre = async () => {
        if (!selectedSale) return;
        setIsStatusUpdating(true);
        try {
            await api.post(`/v2/mmg/from-sale/${selectedSale.id}`);
            alert("✅ Demande de métré générée avec succès ! Le technicien a été notifié.");
            // Refresh details
            const res = await api.get(`/v2/sales/${selectedSale.id}`);
            setSelectedSale(res.data);
        } catch(err) {
            console.error(err);
            alert("Erreur lors de la génération du métré.");
        } finally {
            setIsStatusUpdating(false);
        }
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setIsUploadingBOM(true);
        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await api.post(`/v2/stock/import-bom/${selectedSale.id}`, formData, {
                headers: { "Content-Type": "multipart/form-data" }
            });
            let alertMsg = `✅ Succès: ${res.data.processed_count} articles ont été débités du stock.`;
            
            if (res.data.warnings && res.data.warnings.length > 0) {
                alertMsg += `\n\n⚠️ AVERTISSEMENT RUPTURE DE STOCK :\n- ` + res.data.warnings.join('\n- ');
            }
            if (res.data.not_found && res.data.not_found.length > 0) {
                alertMsg += `\n\n❌ Références introuvables :\n- ` + res.data.not_found.join('\n- ');
            }
            alert(alertMsg);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
        } catch (error) {
            console.error("Erreur import BOM", error);
            alert("Erreur lors de l'import de la nomenclature. Vérifiez le fichier.");
        } finally {
            setIsUploadingBOM(false);
            e.target.value = null; // reset
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'DRAFT': return 'bg-slate-100 text-slate-600 border-slate-200';
            case 'SENT': return 'bg-blue-100 text-blue-700 border-blue-200';
            case 'VALIDATED': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            case 'IN_DESIGN': return 'bg-purple-100 text-purple-700 border-purple-200';
            case 'READY_FOR_PROD': return 'bg-amber-100 text-amber-700 border-amber-200';
            case 'IN_PRODUCTION': return 'bg-orange-100 text-orange-700 border-orange-200';
            case 'CANCELLED': return 'bg-red-100 text-red-700 border-red-200';
            case 'DELIVERED': return 'bg-indigo-100 text-indigo-700 border-indigo-200';
            default: return 'bg-slate-100 text-slate-600 border-slate-200';
        }
    };

    const getStatusLabel = (status) => {
        switch (status) {
            case 'DRAFT': return 'Brouillon';
            case 'SENT': return 'Envoyé au Client';
            case 'VALIDATED': return 'Validé (Signé)';
            case 'IN_DESIGN': return 'Bureau d\'Études';
            case 'READY_FOR_PROD': return 'Nomenclature (BOM)';
            case 'IN_PRODUCTION': return 'En Production';
            case 'CANCELLED': return 'Refusé / Annulé';
            case 'DELIVERED': return 'Livré & Facturé';
            default: return status;
        }
    };

    const filteredSales = sales.filter(s => 
        s.reference.toLowerCase().includes(searchTerm.toLowerCase()) || 
        s.client_name.toLowerCase().includes(searchTerm.toLowerCase())
    );

    // Calculate total pipeline value
    const pipelineValue = sales
        .filter(s => ['DRAFT', 'SENT'].includes(s.status))
        .reduce((sum, s) => sum + s.lines.reduce((lsum, l) => lsum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0), 0);

    const validatedValue = sales
        .filter(s => ['VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'DELIVERED', 'IN_PRODUCTION'].includes(s.status))
        .reduce((sum, s) => sum + s.lines.reduce((lsum, l) => lsum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0), 0);

    return (
        <div className="max-w-[1600px] h-[calc(100vh-100px)] mx-auto font-sans flex flex-col overflow-hidden bg-slate-50/50 border border-slate-200/60 rounded-[2rem] shadow-2xl animate-fade-in relative">
            
            {/* TOP NAVIGATION TABS */}
            <div className="bg-slate-900 px-6 py-4 flex gap-4 shrink-0 rounded-t-[2rem]">
                <button 
                    onClick={() => setMainTab('pipeline')}
                    className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'pipeline' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:bg-slate-800'}`}
                >
                    <DollarSign className="w-5 h-5"/> Pipeline Commercial
                </button>
                <button 
                    onClick={() => setMainTab('dossiers')}
                    className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'dossiers' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:bg-slate-800'}`}
                >
                    <ListTodo className="w-5 h-5"/> Métrés & Dossiers Techniques
                </button>
                <button 
                    onClick={() => setMainTab('clients')}
                    className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'clients' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:bg-slate-800'}`}
                >
                    <Users className="w-5 h-5"/> Annuaire Clients
                </button>
            </div>

            {mainTab === 'clients' && (
                <div className="flex-1 overflow-hidden">
                    <PartnerDirectory type="CLIENT" />
                </div>
            )}

            {mainTab === 'dossiers' && (
                <div className="flex-1 overflow-hidden">
                    <MMGDossiers isEmbedded={true} />
                </div>
            )}

            {mainTab === 'pipeline' && (
            <div className="flex-1 flex flex-col overflow-hidden relative">
                {/* PIPELINE HEADER CONTROLS */}
                <div className="bg-white border-b border-slate-200 p-4 flex items-center justify-between shrink-0 z-20">
                    <div className="flex items-center gap-4">
                        <h3 className="font-black text-slate-900 flex items-center gap-2 tracking-tight text-lg">
                            <Users className="text-blue-600 w-5 h-5"/> CRM & Devis
                        </h3>
                        <div className="h-6 w-px bg-slate-200"></div>
                        <div className="flex bg-slate-100 p-1 rounded-xl">
                            <button onClick={() => setPipelineView('kanban')} className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${pipelineView === 'kanban' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-800'}`}>Kanban</button>
                            <button onClick={() => setPipelineView('list')} className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${pipelineView === 'list' ? 'bg-white shadow-sm text-slate-800' : 'text-slate-500 hover:text-slate-800'}`}>Liste</button>
                        </div>
                        <div className="flex items-center gap-4 ml-4">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-slate-400 uppercase">Pipeline</span>
                                <span className="text-sm font-black text-blue-600">{pipelineValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0})}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-bold text-slate-400 uppercase">Validé</span>
                                <span className="text-sm font-black text-emerald-600">{validatedValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0})}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div className="flex items-center gap-3">
                        <div className="relative w-64">
                            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                            <input 
                                type="text" 
                                placeholder="Rechercher..." 
                                value={searchTerm}
                                onChange={e => setSearchTerm(e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                            />
                        </div>
                        <button 
                            onClick={() => setShowAIModal(true)} 
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black shadow-md shadow-indigo-500/20 flex items-center gap-2 transition-all"
                        >
                            <Sparkles className="w-4 h-4"/> Nouveau Devis IA
                        </button>
                    </div>
                </div>

                <div className="flex-1 flex overflow-hidden relative bg-slate-50/50">
                    
                    {/* KANBAN VIEW */}
                    {pipelineView === 'kanban' && (
                        <div className="flex-1 overflow-x-auto p-6 flex gap-6 items-start h-full pb-10">
                            {pipelineStages.map(col => {
                                const colSales = filteredSales.filter(s => s.status === col.id);
                                const colValue = colSales.reduce((sum, s) => sum + s.lines.reduce((lsum, l) => lsum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0), 0);
                                
                                return (
                                    <div 
                                        key={col.id}
                                        onDragOver={handleDragOver}
                                        onDrop={(e) => handleDrop(e, col.id)}
                                        className="w-80 shrink-0 flex flex-col h-full"
                                    >
                                        <div className="flex items-center justify-between mb-4 px-2 group">
                                            <div className="flex-1 mr-2">
                                                <input 
                                                    type="text" 
                                                    value={col.title}
                                                    onChange={(e) => {
                                                        const newStages = pipelineStages.map(s => s.id === col.id ? { ...s, title: e.target.value } : s);
                                                        setPipelineStages(newStages);
                                                    }}
                                                    onBlur={() => saveStagesToServer(pipelineStages)}
                                                    className="font-black text-slate-700 text-sm bg-transparent border-none outline-none focus:ring-2 focus:ring-blue-500 rounded px-1 w-full"
                                                />
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold text-slate-500">{colValue > 0 ? colValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}) : ''}</span>
                                                <span className="text-slate-400 font-bold text-xs bg-slate-200 px-1.5 py-0.5 rounded">{colSales.length}</span>
                                                <button onClick={() => handleDeleteStage(col.id)} className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-opacity">
                                                    <X className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                        <div className={`flex-1 overflow-y-auto space-y-3 p-2 rounded-2xl ${isStatusUpdating ? 'opacity-50' : ''} bg-slate-100/50 border border-slate-200/50 min-h-[150px]`}>
                                            {colSales.map(sale => {
                                                const total = sale.lines.reduce((sum, l) => sum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0);
                                                return (
                                                    <div 
                                                        key={sale.id}
                                                        draggable
                                                        onDragStart={(e) => handleDragStart(e, sale.id)}
                                                        onClick={() => openSaleDetails(sale.id)}
                                                        className={`bg-white p-4 rounded-xl shadow-sm border-2 cursor-grab active:cursor-grabbing hover:shadow-md transition-all ${selectedSale?.id === sale.id ? 'border-blue-500 ring-2 ring-blue-50' : 'border-slate-200 hover:border-blue-300'}`}
                                                    >
                                                        <div className="flex justify-between items-start mb-2">
                                                            <span className="font-black text-slate-800 text-sm leading-tight">{sale.client_name}</span>
                                                        </div>
                                                        <div className="flex justify-between items-end mt-4">
                                                            <span className="font-bold text-slate-400 text-[10px] uppercase tracking-wider">{sale.reference}</span>
                                                            <span className="font-black text-slate-700 text-sm">{total.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0})}</span>
                                                        </div>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                )
                            })}
                            
                            {/* ADD NEW STAGE BUTTON */}
                            <div className="w-80 shrink-0 flex flex-col h-full opacity-60 hover:opacity-100 transition-opacity">
                                <button 
                                    onClick={handleAddStage}
                                    className="flex items-center justify-center gap-2 h-12 border-2 border-dashed border-slate-300 rounded-xl text-slate-500 font-bold hover:border-blue-400 hover:text-blue-600 hover:bg-blue-50 transition-all"
                                >
                                    <Plus className="w-5 h-5" /> Ajouter une étape
                                </button>
                            </div>
                        </div>
                    )}

                    {/* LIST VIEW (Legacy) */}
                    {pipelineView === 'list' && (
                        <div className="w-[400px] bg-white border-r border-slate-200 flex flex-col h-full shadow-xl z-10 shrink-0">
                            <div className="flex-1 overflow-y-auto p-4 space-y-3">
                                {filteredSales.map(sale => {
                                    const total = sale.lines.reduce((sum, l) => sum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0);
                                    return (
                                        <div 
                                            key={sale.id} 
                                            onClick={() => openSaleDetails(sale.id)}
                                            className={`p-4 rounded-xl cursor-pointer border-2 transition-all ${selectedSale?.id === sale.id ? 'bg-blue-50 border-blue-500 shadow-md' : 'bg-white border-slate-100 hover:border-slate-300 shadow-sm'}`}
                                        >
                                            <div className="flex justify-between items-start mb-2">
                                                <span className="font-black text-slate-900">{sale.client_name}</span>
                                                <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getStatusColor(sale.status)}`}>{getStatusLabel(sale.status)}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm">
                                                <span className="font-bold text-slate-400 text-xs">{sale.reference}</span>
                                                <span className="font-black text-slate-800">{total.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span>
                                            </div>
                                        </div>
                                    );
                                })}
                                {filteredSales.length === 0 && (
                                    <div className="text-center py-10 text-slate-400 font-bold">Aucun devis trouvé.</div>
                                )}
                            </div>
                        </div>
                    )}

            {/* MAIN AREA : SALE DETAILS OVERLAY / PANEL */}
            {(pipelineView === 'list' || selectedSale) && (
                <div className={`${pipelineView === 'kanban' ? 'absolute inset-y-0 right-0 w-[800px] border-l shadow-2xl z-40 bg-slate-50 shadow-slate-900/10' : 'flex-1'} flex flex-col relative overflow-y-auto`}>
                    {selectedSale ? (
                        <div className="p-8 max-w-4xl mx-auto w-full relative">
                            {pipelineView === 'kanban' && (
                                <button onClick={() => setSelectedSale(null)} className="absolute top-4 right-4 p-2 bg-white rounded-full shadow-md text-slate-500 hover:text-slate-800 z-50">
                                    <X className="w-5 h-5" />
                                </button>
                            )}
                        {/* HEADER CARD */}
                        <div className="bg-white rounded-[2rem] shadow-xl border border-slate-200 overflow-hidden mb-8 mt-4">
                            <div className="px-8 py-8 border-b border-slate-100 bg-slate-900 text-white relative overflow-hidden">
                                <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
                                
                                <div className="flex justify-between items-start relative z-10">
                                    <div>
                                        <div className="flex items-center gap-3 mb-3">
                                            <h2 className="text-3xl font-black tracking-tight">{selectedSale.client_name}</h2>
                                            <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg border ${getStatusColor(selectedSale.status)}`}>{getStatusLabel(selectedSale.status)}</span>
                                        </div>
                                        <div className="flex gap-6 text-slate-400 text-sm font-medium">
                                            <p>Réf: <span className="text-white font-bold">{selectedSale.reference}</span></p>
                                            <p>Date: <span className="text-white font-bold">{new Date(selectedSale.created_at).toLocaleDateString('fr-FR')}</span></p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <span className="text-sm font-bold text-slate-400 uppercase tracking-widest">Total Devis HT</span>
                                        <div className="text-5xl font-black tracking-tight text-white mt-1">
                                            {selectedSale.lines.reduce((sum, l) => sum + (l.quantity * l.unit_price * (1 - l.discount_pct / 100)), 0).toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            {/* PIPELINE ACTIONS */}
                            <div className="bg-slate-50 px-8 py-4 border-b border-slate-200 flex gap-3 flex-wrap">
                                <a 
                                    href={`${api.defaults.baseURL}/v2/pdf/quote/${selectedSale.id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-6 py-3 rounded-xl font-bold flex items-center justify-center gap-2 bg-slate-900 text-white hover:bg-slate-800 shadow-md shadow-slate-900/20 transition-all"
                                >
                                    <FileText className="w-4 h-4"/> Télécharger PDF
                                </a>
                                <button 
                                    onClick={() => updateStatus('SENT')}
                                    disabled={selectedSale.status !== 'DRAFT'}
                                    className={`flex-1 min-w-[150px] py-3 rounded-xl font-bold flex items-center justify-center gap-2 transition-all ${selectedSale.status === 'DRAFT' ? 'bg-blue-600 text-white hover:bg-blue-500 shadow-md shadow-blue-500/20' : 'bg-slate-200 text-slate-400 cursor-not-allowed'}`}
                                >
                                    <Send className="w-4 h-4"/> Envoyer (Mail)
                                </button>
                                <button 
                                    onClick={() => updateStatus('VALIDATED')}
                                    disabled={!['DRAFT', 'SENT'].includes(selectedSale.status)}
                                    className={`flex-1 min-w-[200px] py-3 rounded-xl font-bold flex items-center justify-center gap-2 transition-all ${['DRAFT', 'SENT'].includes(selectedSale.status) ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-md shadow-emerald-500/20' : 'bg-slate-200 text-slate-400 cursor-not-allowed'}`}
                                >
                                    <CheckCircle className="w-4 h-4"/> Marquer Validé (Signé)
                                </button>
                                <button 
                                    onClick={() => updateStatus('CANCELLED')}
                                    disabled={['CANCELLED', 'DELIVERED'].includes(selectedSale.status)}
                                    className={`px-6 py-3 rounded-xl font-bold flex items-center justify-center gap-2 transition-all ${!['CANCELLED', 'DELIVERED'].includes(selectedSale.status) ? 'bg-white border border-red-200 text-red-600 hover:bg-red-50' : 'bg-slate-200 text-slate-400 cursor-not-allowed'}`}
                                >
                                    <X className="w-4 h-4"/> Refusé
                                </button>
                            </div>

                            {/* CLIENT DETAILS */}
                            <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
                                <div>
                                    <h4 className="font-black text-xs text-slate-400 uppercase tracking-widest mb-4">Informations Client</h4>
                                    <div className="space-y-3 bg-slate-50 p-5 rounded-2xl border border-slate-100">
                                        {selectedSale.client_contact && <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-20 inline-block">Contact:</span> {selectedSale.client_contact}</p>}
                                        {selectedSale.client_email && <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-20 inline-block">Email:</span> {selectedSale.client_email}</p>}
                                        {selectedSale.client_address && <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-20 inline-block">Adresse:</span> {selectedSale.client_address}</p>}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="font-black text-xs text-slate-400 uppercase tracking-widest mb-4">Conditions B2B</h4>
                                    <div className="space-y-3 bg-slate-50 p-5 rounded-2xl border border-slate-100">
                                        <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-24 inline-block">Validité:</span> {selectedSale.validity_days} jours</p>
                                        <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-24 inline-block">TVA:</span> {selectedSale.tax_rate} %</p>
                                        <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-24 inline-block">Devise:</span> {selectedSale.currency}</p>
                                    </div>
                                </div>
                            </div>

                            {/* METRES ASSOCIES */}
                            {selectedSale.mmg_dossiers && selectedSale.mmg_dossiers.length > 0 && (
                                <div className="px-8 pb-4">
                                    <h4 className="font-black text-xs text-blue-600 uppercase tracking-widest mb-4">Métrés Associés (Chantiers)</h4>
                                    <div className="grid grid-cols-1 gap-4">
                                        {selectedSale.mmg_dossiers.map(m => (
                                            <div key={m.id} className="bg-blue-50 border border-blue-100 p-4 rounded-xl flex items-center justify-between">
                                                <div>
                                                    <p className="font-bold text-blue-900">{m.reference}</p>
                                                    <p className="text-xs text-blue-600">Statut: {m.status}</p>
                                                </div>
                                                <button 
                                                    onClick={() => {
                                                        setMainTab('dossiers');
                                                    }}
                                                    className="px-3 py-1.5 bg-white text-blue-600 text-xs font-bold rounded-lg shadow-sm border border-blue-200"
                                                >
                                                    Ouvrir
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* LINES */}
                            <div className="px-8 pb-8">
                                <h4 className="font-black text-xs text-slate-400 uppercase tracking-widest mb-4">Détail des Prestations</h4>
                                <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-slate-50 border-b border-slate-200">
                                        <tr>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest w-1/2">Description</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Qté</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Prix Unitaire</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-right">Total HT</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        {selectedSale.lines && selectedSale.lines.map((line, idx) => {
                                            const visualConfig = line.visual_config ? JSON.parse(line.visual_config) : null;
                                            return (
                                                <tr key={idx} className="hover:bg-slate-50 transition-colors">
                                                    <td className="py-4 px-4 font-bold text-slate-800 text-sm">
                                                        {line.description}
                                                        {visualConfig && (
                                                            <div className="mt-2 bg-white border border-slate-200 rounded-lg inline-block p-2">
                                                                <WindowVisualizer 
                                                                    type={visualConfig.type} 
                                                                    width={visualConfig.width} 
                                                                    height={visualConfig.height} 
                                                                    color={visualConfig.color} 
                                                                    hasRollerShutter={visualConfig.hasRollerShutter}
                                                                    openingDirection={visualConfig.openingDirection}
                                                                    glassType={visualConfig.glassType}
                                                                    hasMuntins={visualConfig.hasMuntins}
                                                                    bottomPanelHeight={visualConfig.bottomPanelHeight}
                                                                    scale={0.06} 
                                                                />
                                                            </div>
                                                        )}
                                                    </td>
                                                    <td className="py-4 px-4 text-center font-black text-blue-600">{line.quantity}</td>
                                                    <td className="py-4 px-4 text-right font-mono text-slate-600">{line.unit_price.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</td>
                                                    <td className="py-4 px-4 text-right font-black text-slate-900">{(line.quantity * line.unit_price * (1 - line.discount_pct / 100)).toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                                </div>
                                
                                {selectedSale.notes && (
                                    <div className="mt-6 bg-yellow-50/50 border border-yellow-100 p-4 rounded-xl flex gap-3">
                                        <FileCheck className="w-5 h-5 text-yellow-600 shrink-0"/>
                                        <p className="text-sm font-medium text-yellow-800">{selectedSale.notes}</p>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* SENT ACTION */}
                        {selectedSale.status === 'SENT' && (
                            <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-6 text-white shadow-lg shadow-blue-500/20 mb-8">
                                <div className="flex justify-between items-start mb-6">
                                    <div>
                                        <h3 className="font-black text-xl mb-1">En Négociation</h3>
                                        <p className="text-blue-100 text-sm font-medium">Le devis a été envoyé. En attente de signature électronique du client.</p>
                                    </div>
                                    <button 
                                        onClick={validateSale}
                                        disabled={isStatusUpdating}
                                        className="bg-white/10 text-white border border-white/20 px-4 py-2 rounded-xl font-bold hover:bg-white/20 transition-colors text-sm"
                                    >
                                        Ou Valider Manuellement
                                    </button>
                                </div>
                                
                                {selectedSale.signature_token && (
                                    <div className="bg-slate-900/40 rounded-xl p-4 flex items-center justify-between border border-white/10 backdrop-blur-sm">
                                        <div className="overflow-hidden mr-4">
                                            <p className="text-xs font-bold text-blue-200 uppercase tracking-widest mb-1">Lien Sécurisé Client</p>
                                            <p className="font-mono text-sm text-white opacity-80 truncate">
                                                {window.location.origin}/portal/sign/{selectedSale.signature_token}
                                            </p>
                                        </div>
                                        <button 
                                            onClick={() => {
                                                navigator.clipboard.writeText(`${window.location.origin}/portal/sign/${selectedSale.signature_token}`);
                                                alert("Lien copié dans le presse-papier !");
                                            }}
                                            className="bg-blue-500 hover:bg-blue-400 text-white px-4 py-2 rounded-lg font-bold shadow-md transition-colors flex items-center gap-2 shrink-0"
                                        >
                                            <Copy className="w-4 h-4"/> Copier
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* VALIDATED ACTION */}
                        {selectedSale.status === 'VALIDATED' && (
                            <div className="bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl p-6 text-white flex flex-col md:flex-row justify-between items-center gap-4 shadow-lg shadow-emerald-500/20 mb-8">
                                <div>
                                    <h3 className="font-black text-xl mb-1">Bon de Commande Signé !</h3>
                                    <p className="text-emerald-100 text-sm font-medium">Vous devez maintenant faire un métré précis ou transmettre au BE.</p>
                                </div>
                                <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto">
                                    <button 
                                        onClick={generateMetre}
                                        disabled={isStatusUpdating}
                                        className="w-full sm:w-auto bg-white/20 text-white border border-white/30 px-4 py-3 rounded-xl font-bold hover:bg-white/30 transition-colors flex items-center justify-center gap-2"
                                    >
                                        Générer Métré
                                    </button>
                                    <button 
                                        onClick={sendToDesign}
                                        disabled={isStatusUpdating}
                                        className="w-full sm:w-auto bg-white text-emerald-700 px-6 py-3 rounded-xl font-black shadow-md hover:scale-105 transition-transform flex items-center justify-center gap-2"
                                    >
                                        {isStatusUpdating ? "Envoi..." : "Bureau d'Études"} <ArrowRight className="w-4 h-4"/>
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* IN_DESIGN ACTION */}
                        {selectedSale.status === 'IN_DESIGN' && (
                            <div className="bg-gradient-to-r from-purple-600 to-indigo-600 rounded-2xl p-6 text-white shadow-lg shadow-purple-500/20 mb-8">
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <h3 className="font-black text-xl mb-1">En Bureau d'Études</h3>
                                        <p className="text-purple-100 text-sm font-medium">En attente des fichiers de fabrication (Orgadata/Proges).</p>
                                    </div>
                                    <div className="bg-white/20 px-3 py-1 rounded-full text-xs font-bold border border-white/30 flex items-center gap-2">
                                        <div className="w-2 h-2 rounded-full bg-white animate-pulse"></div>
                                        BE / MÉTODES
                                    </div>
                                </div>
                                <div className="bg-white/10 rounded-xl p-4 border border-white/20 flex flex-col sm:flex-row items-center justify-between gap-4">
                                    <div>
                                        <h4 className="font-bold text-sm mb-1 text-white">Nomenclature Orgadata/Proges</h4>
                                        <p className="text-xs text-purple-100">Importez le fichier BOM pour débiter les stocks et débloquer la production.</p>
                                    </div>
                                    <label className="bg-white text-purple-600 px-4 py-2 rounded-lg font-black text-sm shadow-md cursor-pointer hover:scale-105 transition-transform flex items-center justify-center gap-2 w-full sm:w-auto shrink-0">
                                        {isUploadingBOM ? "Chargement..." : "Importer BOM"}
                                        <UploadCloud className="w-4 h-4"/>
                                        <input type="file" accept=".xml,.csv" className="hidden" onChange={handleFileUpload} disabled={isUploadingBOM} />
                                    </label>
                                </div>
                            </div>
                        )}

                        {/* READY_FOR_PROD ACTION */}
                        {selectedSale.status === 'READY_FOR_PROD' && (
                            <div className="bg-gradient-to-r from-amber-500 to-yellow-500 rounded-2xl p-6 text-white flex flex-col md:flex-row justify-between items-center gap-4 shadow-lg shadow-amber-500/20 mb-8">
                                <div>
                                    <h3 className="font-black text-xl mb-1">Dossier Prêt & Stock Débité</h3>
                                    <p className="text-amber-100 text-sm font-medium">La nomenclature a été validée. Transmettez à l'Atelier Live.</p>
                                </div>
                                <button 
                                    onClick={launchProduction}
                                    disabled={isStatusUpdating}
                                    className="w-full sm:w-auto bg-white text-amber-700 px-6 py-3 rounded-xl font-black shadow-md hover:scale-105 transition-transform flex items-center justify-center gap-2"
                                >
                                    {isStatusUpdating ? "Lancement..." : "Transmettre à l'Atelier"} <Send className="w-4 h-4"/>
                                </button>
                            </div>
                        )}
                        
                        {/* IN PRODUCTION STATE */}
                        {selectedSale.status === 'IN_PRODUCTION' && (
                            <div className="bg-gradient-to-r from-orange-500 to-amber-500 rounded-2xl p-6 text-white flex flex-col sm:flex-row justify-between items-center gap-4 shadow-lg shadow-orange-500/20 mb-8">
                                <div>
                                    <h3 className="font-black text-xl mb-1">Fabrication en Cours</h3>
                                    <p className="text-orange-100 text-sm font-medium">Les fiches de fabrication sont sur les tablettes de l'Atelier.</p>
                                </div>
                                <div className="bg-white/20 px-3 py-1 rounded-full text-xs font-bold border border-white/30 flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-white animate-pulse"></div>
                                    ATELIER LIVE
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    pipelineView === 'list' && (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                            <Users className="w-24 h-24 text-slate-200 mb-6" />
                            <h2 className="text-2xl font-black text-slate-500">Aucun devis sélectionné</h2>
                            <p className="font-medium mt-2">Sélectionnez un devis à gauche pour voir les détails ou le valider.</p>
                        </div>
                    )
                )}
            </div>
            )}
            </div>
            </div>
            )}

            {/* AI COPILOT MODAL */}
            {showAIModal && (
                <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden animate-fade-in flex flex-col">
                        <div className="bg-indigo-600 p-6 flex justify-between items-center text-white shrink-0">
                            <div>
                                <h2 className="text-2xl font-black flex items-center gap-3">
                                    <BrainCircuit className="w-6 h-6 text-indigo-200" />
                                    Copilote Commercial IA
                                </h2>
                                <p className="text-indigo-100 text-sm mt-1">Parlez-moi naturellement pour générer un devis instantanément.</p>
                            </div>
                            <button onClick={() => setShowAIModal(false)} className="p-2 hover:bg-indigo-500 rounded-full transition-colors text-indigo-100 hover:text-white">
                                <X className="w-6 h-6" />
                            </button>
                        </div>
                        
                        <div className="p-8">
                            <label className="block text-sm font-bold text-slate-700 mb-3">Votre requête client :</label>
                            <div className="relative">
                                <textarea 
                                    value={aiPrompt}
                                    onChange={e => setAiPrompt(e.target.value)}
                                    placeholder="Ex: Je veux un devis pour Mr Martin avec 3 baies coulissantes et 1 porte d'entrée..."
                                    className="w-full h-32 bg-slate-50 border border-slate-200 rounded-xl p-4 text-slate-800 font-medium outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                                />
                                <Sparkles className="absolute right-4 bottom-4 w-5 h-5 text-indigo-300" />
                            </div>

                            <div className="mt-6 flex justify-end gap-3">
                                <button 
                                    onClick={() => setShowAIModal(false)}
                                    className="px-6 py-3 bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl font-bold transition-all"
                                >
                                    Annuler
                                </button>
                                <button 
                                    onClick={handleAIGenerate}
                                    disabled={!aiPrompt.trim() || isGenerating}
                                    className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-300 text-white rounded-xl font-black shadow-lg shadow-indigo-500/30 flex items-center gap-2 transition-all active:scale-95"
                                >
                                    {isGenerating ? <BrainCircuit className="w-5 h-5 animate-pulse" /> : <Send className="w-5 h-5" />}
                                    {isGenerating ? "Analyse en cours..." : "Générer le Devis"}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
