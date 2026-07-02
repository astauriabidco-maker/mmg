import React, { useState } from 'react';
import { Users, FileText, Search, ArrowRight, CheckCircle, X, DollarSign, Send, Clock, AlertTriangle, FileCheck, Plus, ListTodo, UploadCloud, Copy, Sparkles, BrainCircuit, Package, Wrench, Tag, RefreshCw } from 'lucide-react';
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
    const [workshopPrepFiles, setWorkshopPrepFiles] = useState([]);
    const [workshopPrepPreview, setWorkshopPrepPreview] = useState(null);
    const [isWorkshopPreparing, setIsWorkshopPreparing] = useState(false);

    // AI Copilot State
    const [showAIModal, setShowAIModal] = useState(false);
    const [aiPrompt, setAiPrompt] = useState('');
    const [isGenerating, setIsGenerating] = useState(false);
    const [showManualQuoteModal, setShowManualQuoteModal] = useState(false);
    const [isCreatingManualQuote, setIsCreatingManualQuote] = useState(false);
    const [manualClientSearch, setManualClientSearch] = useState('');
    const [manualCatalogSearch, setManualCatalogSearch] = useState('');
    const [manualQuoteLineMode, setManualQuoteLineMode] = useState('stock');
    const [isManualNewClient, setIsManualNewClient] = useState(false);
    const [manualQuote, setManualQuote] = useState({
        client_name: "",
        client_contact: "",
        client_email: "",
        client_address: "",
        notes: "",
        validity_days: 30,
        tax_rate: 20,
        currency: "EUR",
        workflow_type: "FREE_SALE",
        lines: []
    });

    const { data: sales = [], isLoading: isLoadingSales } = useQuery({
        queryKey: ['sales'],
        queryFn: async () => {
            const res = await api.get('/v2/sales/');
            return res.data;
        }
    });

    const { data: clients = [], refetch: refetchClients } = useQuery({
        queryKey: ['partners', 'clients'],
        queryFn: async () => {
            const res = await api.get('/v2/partners/clients');
            return res.data;
        }
    });

    const {
        data: stockProducts = [],
        isLoading: isLoadingStockProducts,
        isError: hasStockProductsError,
        error: stockProductsError,
        refetch: refetchStockProducts
    } = useQuery({
        queryKey: ['products'],
        enabled: showManualQuoteModal,
        retry: 1,
        queryFn: async () => {
            const res = await api.get('/v2/stock/products');
            return res.data;
        }
    });

    const { data: stockQuants = [] } = useQuery({
        queryKey: ['quants'],
        enabled: showManualQuoteModal,
        queryFn: async () => {
            const res = await api.get('/v2/stock/quants');
            return res.data;
        }
    });

    const { data: stockLocations = [] } = useQuery({
        queryKey: ['locations'],
        enabled: showManualQuoteModal,
        queryFn: async () => {
            const res = await api.get('/v2/stock/locations');
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

    const getWorkflowLabel = (workflowType) => {
        switch (workflowType) {
            case 'FABRICATION_FROM_MEASURE':
                return 'Fabrication depuis métré';
            case 'FABRICATION_ESTIMATE':
                return 'Pré-devis fabrication';
            case 'FREE_SALE':
            default:
                return 'Devis libre pièces/prestations';
        }
    };

    const getWorkflowBadgeClass = (workflowType) => {
        switch (workflowType) {
            case 'FABRICATION_FROM_MEASURE':
                return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            case 'FABRICATION_ESTIMATE':
                return 'bg-amber-100 text-amber-700 border-amber-200';
            case 'FREE_SALE':
            default:
                return 'bg-slate-100 text-slate-600 border-slate-200';
        }
    };

    const hasMeasureContext = (sale) => (sale?.mmg_dossiers || []).length > 0;

    const canPrepareWorkshop = (sale) => {
        if (!sale || !['VALIDATED', 'IN_DESIGN'].includes(sale.status)) return false;
        if ((sale.workflow_type || 'FREE_SALE') === 'FREE_SALE') return false;
        if (sale.workflow_type === 'FABRICATION_ESTIMATE' && !hasMeasureContext(sale)) return false;
        return true;
    };

    const getWorkshopBlockedMessage = (sale) => {
        if (!sale || !['VALIDATED', 'IN_DESIGN'].includes(sale.status)) return null;
        if ((sale.workflow_type || 'FREE_SALE') === 'FREE_SALE') {
            return "Ce devis libre est réservé aux pièces, accessoires, prestations ou SAV. Pour une fabrication, créez un métré.";
        }
        if (sale.workflow_type === 'FABRICATION_ESTIMATE' && !hasMeasureContext(sale)) {
            return "Ce pré-devis fabrication doit être rattaché à un métré avant préparation atelier.";
        }
        return null;
    };
    
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
            setWorkshopPrepFiles([]);
            setWorkshopPrepPreview(null);
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
                quoteDraft.workflow_type = quoteDraft.workflow_type || "FABRICATION_ESTIMATE";
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

    const resetManualQuote = () => {
        setManualQuote({
            client_name: "",
            client_contact: "",
            client_email: "",
            client_address: "",
            notes: "",
            validity_days: 30,
            tax_rate: 20,
            currency: "EUR",
            workflow_type: "FREE_SALE",
            lines: []
        });
        setManualClientSearch('');
        setManualCatalogSearch('');
        setManualQuoteLineMode('stock');
        setIsManualNewClient(false);
    };

    const updateManualQuoteField = (field, value) => {
        setManualQuote(prev => ({ ...prev, [field]: value }));
    };

    const updateManualLine = (index, field, value) => {
        setManualQuote(prev => ({
            ...prev,
            lines: prev.lines.map((line, idx) => idx === index ? { ...line, [field]: value } : line)
        }));
    };

    const addServiceLine = () => {
        setManualQuote(prev => ({
            ...prev,
            lines: [...prev.lines, { line_type: "service", description: "", quantity: 1, unit_price: 0, discount_pct: 0 }]
        }));
    };

    const addServiceLineFromCatalog = (item) => {
        if (item.isDraft) {
            return alert("Prestation brouillon: activez-la dans le catalogue avant de l'utiliser.");
        }
        setManualQuote(prev => ({
            ...prev,
            lines: [...prev.lines, {
                line_type: "service",
                variant_id: item.variant_id,
                description: item.label,
                quantity: 1,
                unit_price: item.unitPrice,
                discount_pct: 0,
                catalog_reference: item.reference,
                catalog_status: item.status,
                unit: item.unit
            }]
        }));
        setManualCatalogSearch('');
    };

    const removeManualLine = (index) => {
        setManualQuote(prev => ({
            ...prev,
            lines: prev.lines.filter((_, idx) => idx !== index)
        }));
    };

    const getProductStatusLabel = (status) => {
        if (status === 'DRAFT') return 'Brouillon';
        if (status === 'ARCHIVED') return 'Archivé';
        return 'Actif';
    };

    const getProductStatusClass = (status) => {
        if (status === 'DRAFT') return 'bg-amber-100 text-amber-700 border-amber-200';
        if (status === 'ARCHIVED') return 'bg-slate-100 text-slate-500 border-slate-200';
        return 'bg-emerald-100 text-emerald-700 border-emerald-200';
    };

    const getInternalStockForVariant = (variantId) => {
        const internalLocationIds = stockLocations
            .filter(location => location.usage === 'internal')
            .map(location => location.id);
        return stockQuants
            .filter(quant => quant.variant_id === variantId && internalLocationIds.includes(quant.location_id))
            .reduce((sum, quant) => sum + Number(quant.quantity || 0), 0);
    };

    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const formatDate = (value) => value ? new Date(value).toLocaleDateString('fr-FR') : '-';
    const getLineTypeLabel = (lineType) => (lineType === 'STOCK_ITEM' ? 'Article stock' : 'Prestation');
    const getLineTypeClass = (lineType) => (
        lineType === 'STOCK_ITEM'
            ? 'bg-blue-50 text-blue-700 border-blue-100'
            : 'bg-emerald-50 text-emerald-700 border-emerald-100'
    );
    const getReservationStatusClass = (status) => {
        if (status === 'reserved') return 'bg-amber-50 text-amber-700 border-amber-100';
        if (status === 'consumed') return 'bg-emerald-50 text-emerald-700 border-emerald-100';
        if (status === 'cancelled') return 'bg-slate-100 text-slate-500 border-slate-200';
        return 'bg-blue-50 text-blue-700 border-blue-100';
    };
    const getReservationStatusLabel = (status) => {
        if (status === 'reserved') return 'Réservée';
        if (status === 'consumed') return 'Consommée';
        if (status === 'cancelled') return 'Annulée';
        return status || 'Inconnu';
    };
    const getReservationLineSourceId = (source) => {
        const match = String(source || '').match(/^sale_order_line:(\d+)$/);
        return match ? Number(match[1]) : null;
    };
    const normalizeSearchText = (value) => String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const filteredManualClients = clients
        .filter(client => client.is_active !== false)
        .filter(client => {
            const search = normalizeSearchText(manualClientSearch);
            if (!search) return false;
            return [
                client.name,
                client.contact_name,
                client.phone,
                client.email,
                client.address,
                client.tax_id
            ].some(value => normalizeSearchText(value).includes(search));
        })
        .slice(0, 8);
    const stockProductsErrorStatus = stockProductsError?.response?.status;
    const stockProductsErrorDetail = stockProductsError?.response?.data?.detail || stockProductsError?.message || "Erreur inconnue";

    const catalogItems = stockProducts.flatMap(product => (product.variants || []).map(variant => {
        const unitPrice = Number(variant.sale_price ?? variant.price ?? variant.unit_price ?? variant.list_price ?? variant.cost_price ?? 0);
        const availableStock = Number(variant.available_quantity ?? getInternalStockForVariant(variant.id));
        const status = product.catalog_status || 'ACTIVE';
        const reference = variant.reference || product.reference_base;
        const productType = (product.product_type || 'stockable').toLowerCase();
        return {
            product,
            variant,
            variant_id: variant.id,
            reference,
            label: `${product.name}${variant.color ? ` - ${variant.color}` : ''}`,
            supplierReference: variant.supplier_reference || '',
            unit: product.unit || 'u',
            unitPrice,
            availableStock,
            status,
            productType,
            isDraft: status === 'DRAFT',
            searchable: `${product.name} ${product.reference_base || ''} ${reference || ''} ${variant.supplier_reference || ''} ${product.supplier || ''}`.toLowerCase()
        };
    }));

    const filteredCatalogItems = catalogItems
        .filter(item => item.productType !== 'service')
        .filter(item => !manualCatalogSearch.trim() || item.searchable.includes(manualCatalogSearch.trim().toLowerCase()))
        .slice(0, 12);

    const filteredServiceCatalogItems = catalogItems
        .filter(item => item.productType === 'service')
        .filter(item => !manualCatalogSearch.trim() || item.searchable.includes(manualCatalogSearch.trim().toLowerCase()))
        .slice(0, 12);

    const addStockLineFromCatalog = (item) => {
        if (item.isDraft) {
            return alert("Article brouillon: qualifiez-le dans le catalogue avant de le vendre.");
        }
        if (item.unitPrice <= 0) {
            return alert("Prix HT manquant: renseignez un prix de vente dans le catalogue avant d'ajouter cet article au devis.");
        }
        setManualQuote(prev => ({
            ...prev,
            lines: [...prev.lines, {
                line_type: "stock",
                variant_id: item.variant_id,
                description: `${item.label} (${item.reference})`,
                quantity: 1,
                unit_price: item.unitPrice,
                discount_pct: 0,
                catalog_reference: item.reference,
                catalog_status: item.status,
                available_stock: item.availableStock,
                unit: item.unit
            }]
        }));
        setManualCatalogSearch('');
    };

    const selectManualClient = (client) => {
        setManualQuote(prev => ({
            ...prev,
            client_name: client.name || "",
            client_contact: client.phone || "",
            client_email: client.email || "",
            client_address: client.address || ""
        }));
        setManualClientSearch('');
        setIsManualNewClient(false);
    };

    const startManualNewClient = () => {
        setManualQuote(prev => ({
            ...prev,
            client_name: manualClientSearch.trim(),
            client_contact: "",
            client_email: "",
            client_address: ""
        }));
        setManualClientSearch('');
        setIsManualNewClient(true);
    };

    const createManualQuote = async () => {
        const validLines = manualQuote.lines
            .map(line => ({
                line_type: line.line_type || (line.variant_id ? "stock" : "service"),
                variant_id: line.variant_id || null,
                description: line.description.trim(),
                quantity: Number(line.quantity || 0),
                unit_price: Number(line.unit_price || 0),
                discount_pct: Number(line.discount_pct || 0)
            }))
            .filter(line => line.description && line.quantity > 0);

        if (!manualQuote.client_name.trim()) {
            return alert("Renseignez le nom du client.");
        }
        if (validLines.length === 0) {
            return alert("Ajoutez au moins une ligne de devis avec une désignation et une quantité.");
        }

        setIsCreatingManualQuote(true);
        try {
            if (isManualNewClient) {
                try {
                    await api.post('/v2/partners/clients', {
                        name: manualQuote.client_name.trim(),
                        phone: manualQuote.client_contact.trim() || null,
                        email: manualQuote.client_email.trim() || null,
                        address: manualQuote.client_address.trim() || null,
                        customer_type: "B2C",
                        is_active: true
                    });
                    queryClient.invalidateQueries(['partners', 'clients']);
                } catch (clientErr) {
                    if (clientErr.response?.status !== 400) throw clientErr;
                }
            }

            const payload = {
                ...manualQuote,
                client_name: manualQuote.client_name.trim(),
                client_contact: manualQuote.client_contact.trim() || null,
                client_email: manualQuote.client_email.trim() || null,
                client_address: manualQuote.client_address.trim() || null,
                notes: manualQuote.notes.trim() || null,
                validity_days: Number(manualQuote.validity_days || 30),
                tax_rate: Number(manualQuote.tax_rate || 0),
                lines: validLines
            };
            const res = await api.post('/v2/sales/', payload);
            setShowManualQuoteModal(false);
            resetManualQuote();
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(res.data.id);
            alert("Devis libre créé en brouillon.");
        } catch (err) {
            console.error("Manual quote error:", err);
            alert(err.response?.data?.detail || "Erreur lors de la création du devis manuel.");
        } finally {
            setIsCreatingManualQuote(false);
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

    const buildWorkshopPrepFormData = () => {
        const formData = new FormData();
        workshopPrepFiles.forEach(file => formData.append("files", file));
        formData.append("source_location", "WH/Stock");
        return formData;
    };

    const previewWorkshopPreparation = async () => {
        if (!selectedSale || workshopPrepFiles.length === 0) {
            return alert("Ajoutez au moins un fichier atelier.");
        }
        setIsWorkshopPreparing(true);
        try {
            const res = await api.post(`/v2/sales/${selectedSale.id}/prepare-workshop/preview`, buildWorkshopPrepFormData(), {
                headers: { "Content-Type": "multipart/form-data" }
            });
            setWorkshopPrepPreview(res.data);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Prévisualisation atelier impossible.");
        } finally {
            setIsWorkshopPreparing(false);
        }
    };

    const reserveWorkshopPreparation = async () => {
        if (!selectedSale || !workshopPrepPreview) return;
        const status = workshopPrepPreview.summary?.stock_match_status || {};
        if (workshopPrepPreview.issues?.some(issue => issue.severity === 'error')) {
            return alert("Réservation bloquée : corrigez les alertes workflow.");
        }
        if ((status.not_found || 0) > 0 || (status.shortage || 0) > 0) {
            return alert("Réservation bloquée : références inconnues ou stock insuffisant.");
        }
        if (!window.confirm(`Réserver le stock atelier pour ${selectedSale.reference} ?`)) return;
        setIsWorkshopPreparing(true);
        try {
            const res = await api.post(`/v2/sales/${selectedSale.id}/prepare-workshop/reserve`, buildWorkshopPrepFormData(), {
                headers: { "Content-Type": "multipart/form-data" }
            });
            alert(res.data.message || "Stock réservé pour atelier.");
            setWorkshopPrepFiles([]);
            setWorkshopPrepPreview(null);
            queryClient.invalidateQueries(['sales']);
            openSaleDetails(selectedSale.id);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Réservation atelier impossible.");
        } finally {
            setIsWorkshopPreparing(false);
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
            alert(err.response?.data?.detail || "Erreur lors du lancement en production");
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
            case 'READY_FOR_PROD': return 'Préparation atelier';
            case 'IN_PRODUCTION': return 'En Production';
            case 'CANCELLED': return 'Refusé / Annulé';
            case 'DELIVERED': return 'Livré & Facturé';
            default: return status;
        }
    };

    const saleCycleSteps = [
        { key: 'draft', label: 'Brouillon', statuses: ['DRAFT'] },
        { key: 'sent', label: 'Envoyé', statuses: ['SENT'] },
        { key: 'validated', label: 'Signé/Validé', statuses: ['VALIDATED', 'IN_DESIGN'] },
        { key: 'reserved', label: 'Réservé', statuses: ['READY_FOR_PROD', 'IN_PRODUCTION'] },
        { key: 'billed', label: 'Facturé/Acompte', statuses: ['DELIVERED'] }
    ];

    const getSaleCycleState = (sale) => {
        if (!sale) return { activeIndex: 0, isCancelled: false, hasStockLines: false, hasReservedLines: false };

        const hasStockLines = (sale.lines || []).some(line => line.line_type === 'STOCK_ITEM' || line.variant_id);
        const hasReservedLines = (sale.lines || []).some(line => Number(line.reserved_quantity || 0) > 0);
        const statusIndex = saleCycleSteps.findIndex(step => step.statuses.includes(sale.status));
        let activeIndex = statusIndex >= 0 ? statusIndex : 0;

        if (hasReservedLines || ['READY_FOR_PROD', 'IN_PRODUCTION'].includes(sale.status)) {
            activeIndex = Math.max(activeIndex, 3);
        }
        if (sale.status === 'DELIVERED') {
            activeIndex = 4;
        }

        return {
            activeIndex,
            isCancelled: sale.status === 'CANCELLED',
            hasStockLines,
            hasReservedLines
        };
    };

    const getSaleCycleCaption = (sale, stepKey) => {
        const cycle = getSaleCycleState(sale);
        if (cycle.isCancelled) return "Cycle interrompu";
        if (stepKey === 'reserved') {
            if (!cycle.hasStockLines) return "Sans stock";
            return cycle.hasReservedLines || cycle.activeIndex >= 3 ? "Stock bloqué" : "À réserver";
        }
        if (stepKey === 'billed') {
            return sale?.status === 'DELIVERED' ? "Terminé" : "À venir";
        }
        if (stepKey === 'validated' && sale?.signed_at) return "Signature client";
        return cycle.activeIndex >= saleCycleSteps.findIndex(step => step.key === stepKey) ? "OK" : "À venir";
    };

    const SaleCycleIndicator = ({ sale, compact = false }) => {
        const cycle = getSaleCycleState(sale);
        const activeStep = saleCycleSteps[cycle.activeIndex] || saleCycleSteps[0];

        if (compact) {
            return (
                <div className="mt-3">
                    <div className="flex items-center gap-1.5">
                        {saleCycleSteps.map((step, idx) => {
                            const isDone = !cycle.isCancelled && idx <= cycle.activeIndex;
                            const isActive = idx === cycle.activeIndex;
                            return (
                                <div
                                    key={step.key}
                                    title={step.label}
                                    className={`h-1.5 flex-1 rounded-full ${cycle.isCancelled ? 'bg-red-200' : isDone ? (isActive ? 'bg-blue-600' : 'bg-emerald-400') : 'bg-slate-200'}`}
                                />
                            );
                        })}
                    </div>
                    <p className={`mt-1 text-[10px] font-black uppercase tracking-widest ${cycle.isCancelled ? 'text-red-500' : 'text-slate-400'}`}>
                        {cycle.isCancelled ? 'Annulé' : activeStep.label}
                    </p>
                </div>
            );
        }

        return (
            <div className="px-8 py-6 border-b border-slate-100 bg-white">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Cycle devis</p>
                        <p className="text-sm font-bold text-slate-600">Lecture rapide du passage commercial jusqu'à la réservation et la facturation.</p>
                    </div>
                    {cycle.isCancelled && (
                        <span className="text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg bg-red-100 text-red-700 border border-red-200">
                            Cycle interrompu
                        </span>
                    )}
                </div>
                <div className="grid grid-cols-5 gap-2">
                    {saleCycleSteps.map((step, idx) => {
                        const isDone = !cycle.isCancelled && idx < cycle.activeIndex;
                        const isActive = !cycle.isCancelled && idx === cycle.activeIndex;
                        const isFuture = !cycle.isCancelled && idx > cycle.activeIndex;
                        return (
                            <div
                                key={step.key}
                                className={`rounded-2xl border p-3 min-h-[86px] ${isActive ? 'bg-blue-50 border-blue-200 shadow-sm' : isDone ? 'bg-emerald-50 border-emerald-100' : cycle.isCancelled ? 'bg-red-50 border-red-100' : 'bg-slate-50 border-slate-200'}`}
                            >
                                <div className="flex items-center gap-2 mb-2">
                                    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-black ${isActive ? 'bg-blue-600 text-white' : isDone ? 'bg-emerald-500 text-white' : cycle.isCancelled ? 'bg-red-200 text-red-700' : 'bg-slate-200 text-slate-500'}`}>
                                        {isDone ? <CheckCircle className="w-3.5 h-3.5" /> : idx + 1}
                                    </span>
                                    <span className={`text-[10px] font-black uppercase tracking-widest ${isActive ? 'text-blue-700' : isDone ? 'text-emerald-700' : cycle.isCancelled ? 'text-red-600' : 'text-slate-400'}`}>
                                        {isActive ? 'En cours' : isDone ? 'Fait' : isFuture ? 'À venir' : 'Arrêt'}
                                    </span>
                                </div>
                                <p className="text-sm font-black text-slate-900 leading-tight">{step.label}</p>
                                <p className="text-xs font-bold text-slate-500 mt-1">{getSaleCycleCaption(sale, step.key)}</p>
                            </div>
                        );
                    })}
                </div>
            </div>
        );
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
                            <Users className="text-blue-600 w-5 h-5"/> Ventes & Devis
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
                            onClick={() => {
                                refetchClients();
                                setShowManualQuoteModal(true);
                            }}
                            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-black shadow-md shadow-slate-900/10 flex items-center gap-2 transition-all"
                        >
                            <Plus className="w-4 h-4"/> Devis libre
                        </button>
                        <button
                            onClick={() => setMainTab('dossiers')}
                            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black shadow-md shadow-emerald-500/20 flex items-center gap-2 transition-all"
                        >
                            <ListTodo className="w-4 h-4"/> Métré fabrication
                        </button>
                        <button 
                            onClick={() => setShowAIModal(true)} 
                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black shadow-md shadow-indigo-500/20 flex items-center gap-2 transition-all"
                        >
                            <Sparkles className="w-4 h-4"/> Assistant devis IA
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
                                                        <span className={`inline-block mt-3 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getWorkflowBadgeClass(sale.workflow_type)}`}>
                                                            {getWorkflowLabel(sale.workflow_type)}
                                                        </span>
                                                        <SaleCycleIndicator sale={sale} compact />
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
                                            <span className={`inline-block mt-3 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getWorkflowBadgeClass(sale.workflow_type)}`}>
                                                {getWorkflowLabel(sale.workflow_type)}
                                            </span>
                                            <SaleCycleIndicator sale={sale} compact />
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
                                            <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg border ${getWorkflowBadgeClass(selectedSale.workflow_type)}`}>
                                                {getWorkflowLabel(selectedSale.workflow_type)}
                                            </span>
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

                            <SaleCycleIndicator sale={selectedSale} />

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
                                        <p className="text-sm font-bold text-slate-700"><span className="text-slate-400 font-normal w-24 inline-block">Workflow:</span> {getWorkflowLabel(selectedSale.workflow_type)}</p>
                                    </div>
                                </div>
                            </div>

                            {getWorkshopBlockedMessage(selectedSale) && (
                                <div className="px-8 pb-6">
                                    <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                                        <div>
                                            <p className="text-xs font-black text-amber-700 uppercase tracking-widest mb-1">Atelier non disponible</p>
                                            <p className="text-sm font-bold text-amber-900">{getWorkshopBlockedMessage(selectedSale)}</p>
                                        </div>
                                        <button
                                            onClick={() => setMainTab('dossiers')}
                                            className="px-4 py-3 bg-white text-amber-700 border border-amber-200 rounded-xl font-black text-sm hover:bg-amber-100 transition-colors flex items-center justify-center gap-2"
                                        >
                                            <ListTodo className="w-4 h-4" /> Aller aux métrés
                                        </button>
                                    </div>
                                </div>
                            )}

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
                                <h4 className="font-black text-xs text-slate-400 uppercase tracking-widest mb-4">Détail du devis</h4>
                                <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse">
                                    <thead className="bg-slate-50 border-b border-slate-200">
                                        <tr>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest w-1/2">Description</th>
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest">Type</th>
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
                                                    <td className="py-4 px-4">
                                                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg border text-[10px] font-black uppercase tracking-widest ${getLineTypeClass(line.line_type)}`}>
                                                            {line.line_type === 'STOCK_ITEM' ? <Package className="w-3 h-3" /> : <Wrench className="w-3 h-3" />}
                                                            {getLineTypeLabel(line.line_type)}
                                                        </span>
                                                        {line.variant?.reference && (
                                                            <p className="mt-1 text-[10px] font-bold text-slate-400">{line.variant.reference}</p>
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

                                {(selectedSale.workflow_type === 'FREE_SALE' || selectedSale.reservations?.length > 0 || selectedSale.invoices?.length > 0) && (
                                    <div className="mt-6 bg-slate-50 border border-slate-200 rounded-2xl p-5">
                                        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3 mb-5">
                                            <div>
                                                <h4 className="font-black text-xs text-slate-500 uppercase tracking-widest">Traçabilité devis libre</h4>
                                                <p className="text-sm font-semibold text-slate-500 mt-1">Réservations commerciales, lignes stock réservées et facture rattachée.</p>
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                <span className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                                    {selectedSale.lines?.filter(line => line.line_type === 'STOCK_ITEM').length || 0} article(s) stock
                                                </span>
                                                <span className="px-3 py-1.5 rounded-xl bg-white border border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                                    {selectedSale.lines?.filter(line => line.line_type !== 'STOCK_ITEM').length || 0} prestation(s)
                                                </span>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                            <div className="bg-white border border-slate-200 rounded-xl p-4">
                                                <div className="flex items-center justify-between mb-3">
                                                    <p className="text-xs font-black uppercase tracking-widest text-slate-400">Réservations</p>
                                                    <span className="text-xs font-black text-slate-600">{selectedSale.reservations?.length || 0}</span>
                                                </div>
                                                {selectedSale.reservations?.length > 0 ? (
                                                    <div className="space-y-3">
                                                        {selectedSale.reservations.map(reservation => {
                                                            const totalReserved = reservation.lines?.reduce((sum, line) => sum + Number(line.reserved_quantity || 0), 0) || 0;
                                                            return (
                                                                <div key={reservation.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                                    <div className="flex items-start justify-between gap-3">
                                                                        <div>
                                                                            <p className="text-sm font-black text-slate-900">{reservation.reference}</p>
                                                                            <p className="text-[11px] font-bold text-slate-500">{reservation.source_label || 'Source non renseignée'} - {formatDate(reservation.created_at)}</p>
                                                                        </div>
                                                                        <span className={`px-2 py-1 rounded-lg border text-[10px] font-black uppercase tracking-widest ${getReservationStatusClass(reservation.status)}`}>
                                                                            {getReservationStatusLabel(reservation.status)}
                                                                        </span>
                                                                    </div>
                                                                    <div className="mt-3 space-y-2">
                                                                        {reservation.lines?.map(line => {
                                                                            const sourceLineId = getReservationLineSourceId(line.source);
                                                                            const saleLine = selectedSale.lines?.find(item => item.id === sourceLineId);
                                                                            return (
                                                                                <div key={line.id} className="flex items-center justify-between gap-3 text-xs bg-white border border-slate-100 rounded-lg px-3 py-2">
                                                                                    <div>
                                                                                        <p className="font-black text-slate-800">{line.supplier_reference || line.variant?.reference || line.designation || 'Référence stock'}</p>
                                                                                        <p className="font-semibold text-slate-400">{saleLine?.description || line.designation || 'Ligne stock réservée'}</p>
                                                                                    </div>
                                                                                    <div className="text-right">
                                                                                        <p className="font-black text-amber-700">{Number(line.reserved_quantity || 0).toLocaleString('fr-FR')} {line.unit || saleLine?.variant?.product?.unit || ''}</p>
                                                                                        <p className="font-semibold text-slate-400">sur {Number(line.requested_quantity || 0).toLocaleString('fr-FR')} demandé</p>
                                                                                    </div>
                                                                                </div>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                    <p className="mt-3 text-[11px] font-black text-slate-500 uppercase tracking-widest">{totalReserved.toLocaleString('fr-FR')} unité(s) réservée(s)</p>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <p className="text-sm font-bold text-slate-400 bg-slate-50 border border-dashed border-slate-200 rounded-xl p-4">Aucune réservation commerciale rattachée pour l’instant.</p>
                                                )}
                                            </div>

                                            <div className="bg-white border border-slate-200 rounded-xl p-4">
                                                <div className="flex items-center justify-between mb-3">
                                                    <p className="text-xs font-black uppercase tracking-widest text-slate-400">Facturation</p>
                                                    <span className="text-xs font-black text-slate-600">{selectedSale.invoices?.length || 0}</span>
                                                </div>
                                                {selectedSale.invoices?.length > 0 ? (
                                                    <div className="space-y-3">
                                                        {selectedSale.invoices.map(invoice => (
                                                            <div key={invoice.id} className="flex items-center justify-between gap-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                                <div>
                                                                    <p className="text-sm font-black text-slate-900">{invoice.reference}</p>
                                                                    <p className="text-[11px] font-bold text-slate-500">{formatDate(invoice.issue_date)} - {invoice.status}</p>
                                                                </div>
                                                                <div className="text-right">
                                                                    <p className="text-sm font-black text-slate-900">{formatMoney(invoice.total)}</p>
                                                                    <a
                                                                        href={`${api.defaults.baseURL}/v2/pdf/invoice/${invoice.id}`}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="text-[11px] font-black text-blue-600 hover:text-blue-800"
                                                                    >
                                                                        PDF facture
                                                                    </a>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="text-sm font-bold text-slate-400 bg-slate-50 border border-dashed border-slate-200 rounded-xl p-4">Aucune facture générée pour ce devis.</p>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                )}
                                
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
                        {selectedSale.status === 'VALIDATED' && (selectedSale.workflow_type || 'FREE_SALE') === 'FREE_SALE' && (
                            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm mb-8">
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                    <div>
                                        <h3 className="font-black text-xl text-slate-900 mb-1">Devis libre signé</h3>
                                        <p className="text-sm font-medium text-slate-500">
                                            Ce devis concerne des pièces, accessoires, prestations ou SAV. Il reste hors workflow fabrication atelier.
                                        </p>
                                    </div>
                                    <span className="bg-slate-100 text-slate-700 border border-slate-200 px-4 py-2 rounded-xl font-black text-xs uppercase">
                                        Pas de métré atelier
                                    </span>
                                </div>
                            </div>
                        )}

                        {selectedSale.status === 'VALIDATED' && (selectedSale.workflow_type || 'FREE_SALE') !== 'FREE_SALE' && (
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

                        {canPrepareWorkshop(selectedSale) && (
                            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm mb-8">
                                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
                                    <div>
                                        <h3 className="font-black text-xl text-slate-900 mb-1 flex items-center gap-2">
                                            <UploadCloud className="w-5 h-5 text-amber-500" />
                                            Préparer atelier
                                        </h3>
                                        <p className="text-sm font-medium text-slate-500">
                                            Chargez les fichiers Proges/Orgadata pour prévisualiser puis réserver le stock sans le débiter.
                                        </p>
                                    </div>
                                    <label className="bg-amber-50 text-amber-700 border border-amber-200 px-4 py-3 rounded-xl font-black text-sm shadow-sm cursor-pointer hover:bg-amber-100 transition-colors flex items-center justify-center gap-2 min-w-[220px]">
                                        {workshopPrepFiles.length ? `${workshopPrepFiles.length} fichier(s)` : "Choisir fichiers atelier"}
                                        <UploadCloud className="w-4 h-4"/>
                                        <input
                                            type="file"
                                            multiple
                                            accept=".txt,.pdf"
                                            className="hidden"
                                            onChange={(event) => {
                                                setWorkshopPrepFiles(Array.from(event.target.files || []));
                                                setWorkshopPrepPreview(null);
                                            }}
                                        />
                                    </label>
                                </div>

                                <div className="flex flex-wrap gap-3 mt-5">
                                    <button
                                        onClick={previewWorkshopPreparation}
                                        disabled={isWorkshopPreparing || workshopPrepFiles.length === 0}
                                        className="px-5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white font-black transition-colors"
                                    >
                                        {isWorkshopPreparing ? "Analyse..." : "Prévisualiser"}
                                    </button>
                                    <button
                                        onClick={reserveWorkshopPreparation}
                                        disabled={isWorkshopPreparing || !workshopPrepPreview}
                                        className="px-5 py-3 rounded-xl bg-amber-500 hover:bg-amber-400 disabled:bg-slate-200 disabled:text-slate-400 text-white font-black transition-colors"
                                    >
                                        Réserver pour atelier
                                    </button>
                                </div>

                                {workshopPrepPreview && (
                                    <div className="mt-5 space-y-4">
                                        {workshopPrepPreview.issues?.length > 0 && (
                                            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
                                                <p className="text-xs font-black text-amber-700 uppercase mb-2">Contrôles workflow</p>
                                                <div className="space-y-1">
                                                    {workshopPrepPreview.issues.map((issue, idx) => (
                                                        <p key={idx} className={`text-sm font-bold ${issue.severity === 'error' ? 'text-red-700' : 'text-amber-700'}`}>
                                                            {issue.message || issue.code}
                                                        </p>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        <div className="grid grid-cols-4 gap-3">
                                            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4">
                                                <span className="text-[10px] font-black text-slate-400 uppercase">Lignes</span>
                                                <p className="text-2xl font-black text-slate-900">{workshopPrepPreview.summary?.debit_lines || 0}</p>
                                            </div>
                                            <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-4">
                                                <span className="text-[10px] font-black text-emerald-600 uppercase">OK</span>
                                                <p className="text-2xl font-black text-emerald-700">{workshopPrepPreview.summary?.stock_match_status?.ok || 0}</p>
                                            </div>
                                            <div className="bg-red-50 border border-red-100 rounded-2xl p-4">
                                                <span className="text-[10px] font-black text-red-600 uppercase">Inconnues</span>
                                                <p className="text-2xl font-black text-red-700">{workshopPrepPreview.summary?.stock_match_status?.not_found || 0}</p>
                                            </div>
                                            <div className="bg-orange-50 border border-orange-100 rounded-2xl p-4">
                                                <span className="text-[10px] font-black text-orange-600 uppercase">Manques</span>
                                                <p className="text-2xl font-black text-orange-700">{workshopPrepPreview.summary?.stock_match_status?.shortage || 0}</p>
                                            </div>
                                        </div>
                                        <div className="border border-slate-200 rounded-2xl overflow-hidden max-h-64 overflow-y-auto">
                                            <table className="w-full text-left">
                                                <thead className="bg-slate-50 sticky top-0">
                                                    <tr>
                                                        <th className="px-4 py-3 text-[10px] font-black text-slate-400 uppercase">Référence</th>
                                                        <th className="px-4 py-3 text-[10px] font-black text-slate-400 uppercase">Produit</th>
                                                        <th className="px-4 py-3 text-[10px] font-black text-slate-400 uppercase text-right">Demandé</th>
                                                        <th className="px-4 py-3 text-[10px] font-black text-slate-400 uppercase text-right">Disponible</th>
                                                        <th className="px-4 py-3 text-[10px] font-black text-slate-400 uppercase text-center">Statut</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-slate-100">
                                                    {workshopPrepPreview.stock_matches?.map((line, idx) => (
                                                        <tr key={`${line.reference}-${idx}`} className="hover:bg-slate-50">
                                                            <td className="px-4 py-3 font-mono font-black text-sm">{line.supplier}/{line.reference}</td>
                                                            <td className="px-4 py-3 text-sm font-bold text-slate-700">{line.product_name || "Non trouvé"}</td>
                                                            <td className="px-4 py-3 text-sm font-black text-right">{line.requested_quantity} {line.unit}</td>
                                                            <td className="px-4 py-3 text-sm font-black text-right">{line.available_quantity}</td>
                                                            <td className="px-4 py-3 text-center">
                                                                <span className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase ${line.status === 'ok' ? 'bg-emerald-100 text-emerald-700' : line.status === 'shortage' ? 'bg-orange-100 text-orange-700' : 'bg-red-100 text-red-700'}`}>
                                                                    {line.status}
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* IN_DESIGN ACTION */}
                        {selectedSale.status === 'IN_DESIGN' && (selectedSale.workflow_type || 'FREE_SALE') !== 'FREE_SALE' && (
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
                                        <h4 className="font-bold text-sm mb-1 text-white">Fichiers atelier Proges/Orgadata</h4>
                                        <p className="text-xs text-purple-100">Utilisez la carte Préparer atelier ci-dessus pour prévisualiser et réserver le stock sans débit immédiat.</p>
                                    </div>
                                    <span className="bg-white/15 text-white px-4 py-2 rounded-lg font-black text-sm border border-white/20 w-full sm:w-auto text-center shrink-0">
                                        Réservation sécurisée
                                    </span>
                                </div>
                            </div>
                        )}

                        {/* READY_FOR_PROD ACTION */}
                        {selectedSale.status === 'READY_FOR_PROD' && (selectedSale.workflow_type || 'FREE_SALE') !== 'FREE_SALE' && (
                            <div className="bg-gradient-to-r from-amber-500 to-yellow-500 rounded-2xl p-6 text-white flex flex-col md:flex-row justify-between items-center gap-4 shadow-lg shadow-amber-500/20 mb-8">
                                <div>
                                    <h3 className="font-black text-xl mb-1">Dossier Prêt & Stock Réservé</h3>
                                    <p className="text-amber-100 text-sm font-medium">La préparation atelier est validée sans débit réel. Transmettez à l'Atelier Live.</p>
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
                                    Assistant devis IA
                                </h2>
                                <p className="text-indigo-100 text-sm mt-1">Transformez une demande client en brouillon de devis à vérifier.</p>
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
                                    {isGenerating ? "Analyse en cours..." : "Créer le brouillon IA"}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* MANUAL QUOTE MODAL */}
            {showManualQuoteModal && (
                <div className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-[200] flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-6xl max-h-[92vh] overflow-hidden animate-fade-in flex flex-col">
                        <div className="bg-slate-900 p-6 flex justify-between items-center text-white shrink-0">
                            <div>
                                <h2 className="text-2xl font-black flex items-center gap-3">
                                    <FileText className="w-6 h-6 text-blue-200" />
                                    Nouveau devis libre
                                </h2>
                                <p className="text-slate-300 text-sm mt-1">Pièces, accessoires, prestations ou SAV. Pour une fabrication, démarrez par un métré.</p>
                            </div>
                            <button onClick={() => setShowManualQuoteModal(false)} className="p-2 hover:bg-white/10 rounded-full transition-colors text-slate-300 hover:text-white">
                                <X className="w-6 h-6" />
                            </button>
                        </div>

                        <div className="p-6 overflow-y-auto space-y-6">
                            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div>
                                    <p className="text-xs font-black text-amber-700 uppercase tracking-widest mb-1">Règle métier</p>
                                    <p className="text-sm font-bold text-amber-900">
                                        Ce devis libre ne pourra pas partir en préparation atelier fabrication. Utilisez un métré pour les menuiseries sur mesure.
                                    </p>
                                </div>
                                <button
                                    onClick={() => {
                                        setShowManualQuoteModal(false);
                                        setMainTab('dossiers');
                                    }}
                                    className="px-4 py-3 bg-white text-amber-700 border border-amber-200 rounded-xl font-black text-sm hover:bg-amber-100 transition-colors flex items-center justify-center gap-2"
                                >
                                    <ListTodo className="w-4 h-4" /> Créer un métré
                                </button>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="md:col-span-2 relative z-50">
                                    <label className="block text-xs font-black text-slate-400 uppercase mb-2">Rechercher un client</label>
                                    <div className="relative">
                                        <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                                        <input
                                            type="text"
                                            value={manualClientSearch}
                                            onChange={e => {
                                                setManualClientSearch(e.target.value);
                                                setIsManualNewClient(false);
                                            }}
                                            placeholder="Tapez un nom ou téléphone..."
                                            className="w-full pl-12 pr-4 py-4 bg-slate-50 border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 transition-all font-bold text-slate-900 outline-none"
                                        />
                                    </div>

                                    {manualClientSearch && !manualQuote.client_name && !isManualNewClient && (
                                        <div className="absolute top-full mt-2 left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">
                                            {filteredManualClients.map(client => (
                                                    <button
                                                        key={client.id}
                                                        className="w-full text-left px-6 py-4 hover:bg-slate-50 border-b border-slate-100 last:border-0 transition-colors flex items-center justify-between"
                                                        onClick={() => selectManualClient(client)}
                                                    >
                                                        <div>
                                                            <p className="font-bold text-slate-900">{client.name}</p>
                                                            <p className="text-xs text-slate-500">{client.phone || "Sans téléphone"} • {client.email || "Sans email"}</p>
                                                        </div>
                                                        <ArrowRight className="w-4 h-4 text-slate-300" />
                                                    </button>
                                            ))}
                                            {filteredManualClients.length === 0 && (
                                                <div className="px-6 py-4 bg-amber-50 border-b border-amber-100">
                                                    <p className="text-sm font-black text-amber-900">Aucun client existant trouvé.</p>
                                                    <p className="text-xs font-bold text-amber-700 mt-1">Vérifiez l’orthographe ou créez ce client depuis ce devis.</p>
                                                </div>
                                            )}
                                            <button
                                                className="w-full text-left px-6 py-4 bg-blue-50 hover:bg-blue-100 text-blue-700 font-bold transition-colors flex items-center gap-2"
                                                onClick={startManualNewClient}
                                            >
                                                <Plus className="w-5 h-5"/> Créer le nouveau client "{manualClientSearch}"
                                            </button>
                                        </div>
                                    )}
                                </div>

                                {manualQuote.client_name && (
                                    <div className="md:col-span-2 bg-gradient-to-r from-blue-50 to-indigo-50/30 p-5 rounded-2xl border border-blue-100 flex items-center justify-between shadow-sm">
                                        <div>
                                            <div className="flex items-center gap-3 mb-1">
                                                <h4 className="font-black text-xl text-blue-900">{manualQuote.client_name}</h4>
                                                <span className="text-[10px] font-black text-blue-600 bg-blue-200/50 px-2 py-1 rounded-md uppercase tracking-widest">
                                                    {isManualNewClient ? "Nouveau client" : "Annuaire"}
                                                </span>
                                            </div>
                                            <p className="text-sm font-bold text-blue-700/80">
                                                {[manualQuote.client_contact, manualQuote.client_email].filter(Boolean).join(" • ") || "Coordonnées à compléter"}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => {
                                                updateManualQuoteField('client_name', '');
                                                updateManualQuoteField('client_contact', '');
                                                updateManualQuoteField('client_email', '');
                                                updateManualQuoteField('client_address', '');
                                                setIsManualNewClient(false);
                                            }}
                                            className="bg-white/70 hover:bg-white text-blue-600 p-2 rounded-xl transition-all shadow-sm"
                                        >
                                            <X className="w-5 h-5"/>
                                        </button>
                                    </div>
                                )}

                                {isManualNewClient && manualQuote.client_name && (
                                    <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-50 p-5 rounded-2xl border border-slate-100">
                                        <div className="md:col-span-2">
                                            <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Nom / Raison sociale</label>
                                            <input
                                                value={manualQuote.client_name}
                                                onChange={e => updateManualQuoteField('client_name', e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Téléphone</label>
                                            <input
                                                value={manualQuote.client_contact}
                                                onChange={e => updateManualQuoteField('client_contact', e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1">Email</label>
                                            <input
                                                type="email"
                                                value={manualQuote.client_email}
                                                onChange={e => updateManualQuoteField('client_email', e.target.value)}
                                                className="w-full bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                            />
                                        </div>
                                    </div>
                                )}

                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase mb-2">Validité</label>
                                        <input
                                            type="number"
                                            min="1"
                                            value={manualQuote.validity_days}
                                            onChange={e => updateManualQuoteField('validity_days', e.target.value)}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase mb-2">TVA %</label>
                                        <input
                                            type="number"
                                            min="0"
                                            step="0.1"
                                            value={manualQuote.tax_rate}
                                            onChange={e => updateManualQuoteField('tax_rate', e.target.value)}
                                            className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                        />
                                    </div>
                                </div>
                                <div className="md:col-span-2">
                                    <label className="block text-xs font-black text-slate-400 uppercase mb-2">Adresse</label>
                                    <input
                                        value={manualQuote.client_address}
                                        onChange={e => updateManualQuoteField('client_address', e.target.value)}
                                        placeholder="Adresse du chantier ou du client"
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </div>
                            </div>

                            <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-5 items-start">
                                <div className="border border-slate-200 rounded-2xl overflow-hidden bg-white">
                                    <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
                                        <div className="flex items-center justify-between gap-3">
                                            <h3 className="font-black text-slate-800 flex items-center gap-2">
                                                <Package className="w-4 h-4 text-blue-600" /> Catalogue stock
                                            </h3>
                                            <div className="flex bg-white border border-slate-200 p-1 rounded-xl">
                                                <button
                                                    onClick={() => setManualQuoteLineMode('stock')}
                                                    className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${manualQuoteLineMode === 'stock' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'}`}
                                                >
                                                    Stock
                                                </button>
                                                <button
                                                    onClick={() => setManualQuoteLineMode('service')}
                                                    className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${manualQuoteLineMode === 'service' ? 'bg-slate-900 text-white shadow-sm' : 'text-slate-500 hover:bg-slate-50'}`}
                                                >
                                                    Prestation
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {manualQuoteLineMode === 'stock' ? (
                                        <div className="p-4 space-y-4">
                                            <button
                                                type="button"
                                                onClick={() => setManualQuoteLineMode('stock')}
                                                className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-blue-500/20"
                                            >
                                                <Package className="w-4 h-4" /> Ajouter article stock
                                            </button>
                                            <div>
                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Recherche catalogue</label>
                                                <div className="relative">
                                                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                                    <input
                                                        value={manualCatalogSearch}
                                                        onChange={e => setManualCatalogSearch(e.target.value)}
                                                        placeholder="Référence, produit, fournisseur..."
                                                        className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                                    />
                                                </div>
                                            </div>

                                            {hasStockProductsError && (
                                                <div className="bg-red-50 border border-red-100 rounded-xl p-4 text-sm font-bold text-red-700 space-y-3">
                                                    <div className="flex items-start gap-2">
                                                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                                                        <div>
                                                            <p>Catalogue stock indisponible.</p>
                                                            <p className="text-xs font-semibold text-red-600 mt-1">
                                                                {stockProductsErrorStatus ? `HTTP ${stockProductsErrorStatus} - ` : ''}{stockProductsErrorDetail}
                                                            </p>
                                                            <p className="text-xs font-semibold text-red-600 mt-1">
                                                                Le devis peut contenir des prestations, mais les articles stock doivent attendre le catalogue.
                                                            </p>
                                                        </div>
                                                    </div>
                                                    <button
                                                        type="button"
                                                        onClick={() => refetchStockProducts()}
                                                        className="inline-flex items-center gap-2 px-3 py-2 bg-white border border-red-200 rounded-lg text-xs font-black text-red-700 hover:bg-red-100"
                                                    >
                                                        <RefreshCw className="w-3.5 h-3.5" /> Réessayer
                                                    </button>
                                                </div>
                                            )}

                                            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                                                {isLoadingStockProducts && (
                                                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-bold text-slate-500">Chargement du catalogue...</div>
                                                )}
                                                {!hasStockProductsError && !isLoadingStockProducts && filteredCatalogItems.length === 0 && (
                                                    <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm font-bold text-amber-800">
                                                        Aucun article stock ne correspond à cette recherche. Créez une prestation si la vente ne concerne pas une référence catalogue.
                                                    </div>
                                                )}
                                                {filteredCatalogItems.map(item => {
                                                    const isBlockedForQuote = item.isDraft || item.unitPrice <= 0;
                                                    return (
                                                    <button
                                                        key={item.variant_id}
                                                        type="button"
                                                        onClick={() => addStockLineFromCatalog(item)}
                                                        disabled={isBlockedForQuote}
                                                        className={`w-full text-left border rounded-xl p-3 transition-all ${isBlockedForQuote ? 'border-amber-200 bg-amber-50/60 cursor-not-allowed opacity-75' : 'border-slate-200 hover:border-blue-300 hover:bg-blue-50/40'}`}
                                                    >
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="min-w-0">
                                                                <p className="font-black text-slate-900 text-sm truncate">{item.label}</p>
                                                                <p className="text-[10px] font-mono font-black text-slate-400 uppercase mt-1">{item.reference}</p>
                                                            </div>
                                                            <span className={`shrink-0 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getProductStatusClass(item.status)}`}>
                                                                {getProductStatusLabel(item.status)}
                                                            </span>
                                                        </div>
                                                        <div className="grid grid-cols-3 gap-2 mt-3">
                                                            <div className="bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                                                                <p className="text-[9px] font-black text-slate-400 uppercase">Stock</p>
                                                                <p className={`text-sm font-black ${item.availableStock > 0 ? 'text-emerald-600' : 'text-red-600'}`}>{Math.round(item.availableStock * 100) / 100} {item.unit}</p>
                                                            </div>
                                                            <div className="bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                                                                <p className="text-[9px] font-black text-slate-400 uppercase">Prix HT</p>
                                                                <p className="text-sm font-black text-slate-800">{formatMoney(item.unitPrice)}</p>
                                                            </div>
                                                            <div className="bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                                                                <p className="text-[9px] font-black text-slate-400 uppercase">Unité</p>
                                                                <p className="text-sm font-black text-slate-800">{item.unit}</p>
                                                            </div>
                                                        </div>
                                                        {item.unitPrice <= 0 && (
                                                            <p className="mt-2 text-[11px] font-bold text-red-700">Prix catalogue absent: article bloqué pour devis client.</p>
                                                        )}
                                                    </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="p-4 space-y-4">
                                            <button
                                                type="button"
                                                onClick={addServiceLine}
                                                className="w-full px-4 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-emerald-500/20"
                                            >
                                                <Wrench className="w-4 h-4" /> Ajouter prestation libre
                                            </button>
                                            <div>
                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Recherche prestations</label>
                                                <div className="relative">
                                                    <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                                    <input
                                                        value={manualCatalogSearch}
                                                        onChange={e => setManualCatalogSearch(e.target.value)}
                                                        placeholder="Pose, SAV, déplacement, main-d'oeuvre..."
                                                        className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500"
                                                    />
                                                </div>
                                            </div>
                                            <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4">
                                                <p className="text-xs font-black text-emerald-700 uppercase tracking-widest mb-1">Catalogue prestations</p>
                                                <p className="text-sm font-bold text-emerald-900">
                                                    Les prestations pré-enregistrées restent hors stock: elles ne réservent ni ne débitent de matière.
                                                </p>
                                            </div>
                                            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                                                {isLoadingStockProducts && (
                                                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-bold text-slate-500">Chargement des prestations...</div>
                                                )}
                                                {!hasStockProductsError && !isLoadingStockProducts && filteredServiceCatalogItems.length === 0 && (
                                                    <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm font-bold text-amber-800">
                                                        Aucune prestation catalogue ne correspond. Utilisez une prestation libre si le cas est exceptionnel.
                                                    </div>
                                                )}
                                                {filteredServiceCatalogItems.map(item => (
                                                    <button
                                                        key={item.variant_id}
                                                        type="button"
                                                        onClick={() => addServiceLineFromCatalog(item)}
                                                        disabled={item.isDraft}
                                                        className={`w-full text-left border rounded-xl p-3 transition-all ${item.isDraft ? 'border-amber-200 bg-amber-50/60 cursor-not-allowed opacity-75' : 'border-slate-200 hover:border-emerald-300 hover:bg-emerald-50/40'}`}
                                                    >
                                                        <div className="flex items-start justify-between gap-3">
                                                            <div className="min-w-0">
                                                                <p className="font-black text-slate-900 text-sm truncate">{item.label}</p>
                                                                <p className="text-[10px] font-mono font-black text-slate-400 uppercase mt-1">{item.reference}</p>
                                                            </div>
                                                            <span className={`shrink-0 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getProductStatusClass(item.status)}`}>
                                                                {getProductStatusLabel(item.status)}
                                                            </span>
                                                        </div>
                                                        <div className="grid grid-cols-2 gap-2 mt-3">
                                                            <div className="bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                                                                <p className="text-[9px] font-black text-slate-400 uppercase">Prix HT</p>
                                                                <p className="text-sm font-black text-slate-800">{formatMoney(item.unitPrice)}</p>
                                                            </div>
                                                            <div className="bg-white border border-slate-100 rounded-lg px-2 py-1.5">
                                                                <p className="text-[9px] font-black text-slate-400 uppercase">Unité</p>
                                                                <p className="text-sm font-black text-slate-800">{item.unit}</p>
                                                            </div>
                                                        </div>
                                                        {item.unitPrice <= 0 && (
                                                            <p className="mt-2 text-[11px] font-bold text-amber-700">Prix catalogue absent: renseignez le prix HT sur la ligne.</p>
                                                        )}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <div className="border border-slate-200 rounded-2xl overflow-hidden bg-white">
                                    <div className="bg-slate-50 px-4 py-3 flex items-center justify-between border-b border-slate-200">
                                        <h3 className="font-black text-slate-800">Lignes du devis libre</h3>
                                        <div className="flex items-center gap-2">
                                            <button onClick={() => setManualQuoteLineMode('stock')} className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-black text-xs flex items-center gap-2">
                                                <Package className="w-4 h-4" /> Ajouter article stock
                                            </button>
                                            <button onClick={() => setManualQuoteLineMode('service')} className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-black text-xs flex items-center gap-2">
                                                <Wrench className="w-4 h-4" /> Ajouter prestation
                                            </button>
                                        </div>
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {manualQuote.lines.length === 0 && (
                                            <div className="p-8 text-center">
                                                <Package className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                                                <p className="font-black text-slate-700">Ajoutez un article stock ou une prestation.</p>
                                                <p className="text-sm font-medium text-slate-500 mt-1">Le devis libre doit rester composé de références catalogue disponibles ou de prestations clairement identifiées.</p>
                                            </div>
                                        )}
                                        {manualQuote.lines.map((line, index) => {
                                            const lineTotal = Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100);
                                            const requestedQty = Number(line.quantity || 0);
                                            const stockShortage = line.line_type === 'stock' && Number(line.available_stock || 0) < requestedQty;
                                            return (
                                                <div key={index} className="grid grid-cols-12 gap-3 p-4 items-end">
                                                    <div className="col-span-12 flex items-center justify-between gap-3">
                                                        <div className="flex items-center gap-2 min-w-0">
                                                            <span className={`shrink-0 text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${line.line_type === 'stock' ? 'bg-blue-100 text-blue-700 border-blue-200' : 'bg-emerald-100 text-emerald-700 border-emerald-200'}`}>
                                                                {line.line_type === 'stock' ? 'Article stock' : 'Prestation'}
                                                            </span>
                                                            {line.catalog_reference && <span className="text-[10px] font-mono font-black text-slate-400 truncate">{line.catalog_reference}</span>}
                                                            {line.catalog_status && (
                                                                <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getProductStatusClass(line.catalog_status)}`}>
                                                                    {getProductStatusLabel(line.catalog_status)}
                                                                </span>
                                                            )}
                                                        </div>
                                                        <p className="text-sm font-black text-slate-900">{formatMoney(lineTotal)}</p>
                                                    </div>
                                                    <div className="col-span-12 md:col-span-5">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Désignation *</label>
                                                        <input
                                                            value={line.description}
                                                            onChange={e => updateManualLine(index, 'description', e.target.value)}
                                                            placeholder={line.line_type === 'stock' ? "Article du catalogue" : "Ex: pose, déplacement, SAV..."}
                                                            className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                                        />
                                                    </div>
                                                    <div className="col-span-4 md:col-span-2">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Qté</label>
                                                        <input
                                                            type="number"
                                                            min="0"
                                                            step="0.01"
                                                            value={line.quantity}
                                                            onChange={e => updateManualLine(index, 'quantity', e.target.value)}
                                                            className={`w-full bg-white border rounded-xl px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 ${stockShortage ? 'border-red-300 bg-red-50' : 'border-slate-200'}`}
                                                        />
                                                    </div>
                                                    <div className="col-span-4 md:col-span-2">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Prix HT</label>
                                                        <input
                                                            type="number"
                                                            min="0"
                                                            step="0.01"
                                                            value={line.unit_price}
                                                            onChange={e => updateManualLine(index, 'unit_price', e.target.value)}
                                                            className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                                        />
                                                    </div>
                                                    <div className="col-span-3 md:col-span-2">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase mb-2">Remise %</label>
                                                        <input
                                                            type="number"
                                                            min="0"
                                                            max="100"
                                                            step="0.1"
                                                            value={line.discount_pct}
                                                            onChange={e => updateManualLine(index, 'discount_pct', e.target.value)}
                                                            className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500"
                                                        />
                                                    </div>
                                                    <button
                                                        onClick={() => removeManualLine(index)}
                                                        className="col-span-1 h-10 rounded-xl border border-slate-200 text-slate-400 hover:text-red-600 hover:border-red-200 flex items-center justify-center"
                                                        title="Supprimer la ligne"
                                                    >
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                    {line.line_type === 'stock' && (
                                                        <div className={`col-span-12 rounded-xl px-3 py-2 text-xs font-bold flex items-center gap-2 ${stockShortage ? 'bg-red-50 text-red-700 border border-red-100' : 'bg-slate-50 text-slate-600 border border-slate-100'}`}>
                                                            <Tag className="w-4 h-4 shrink-0" />
                                                            Stock disponible: {Math.round(Number(line.available_stock || 0) * 100) / 100} {line.unit || 'u'}.
                                                            {stockShortage ? " Quantité demandée supérieure au stock connu: vérifiez avant envoi." : " Référence catalogue conservée sur la ligne de devis."}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase mb-2">Notes</label>
                                <textarea
                                    value={manualQuote.notes}
                                    onChange={e => updateManualQuoteField('notes', e.target.value)}
                                    placeholder="Conditions, remarques commerciales, contraintes chantier..."
                                    className="w-full h-24 bg-slate-50 border border-slate-200 rounded-xl p-4 text-sm font-medium text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                                />
                            </div>
                        </div>

                        <div className="p-6 border-t border-slate-200 flex flex-col sm:flex-row justify-end gap-3 shrink-0">
                            <button 
                                onClick={() => setShowManualQuoteModal(false)}
                                className="px-6 py-3 bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl font-bold transition-all"
                            >
                                Annuler
                            </button>
                            <button 
                                onClick={createManualQuote}
                                disabled={isCreatingManualQuote}
                                className="px-6 py-3 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-400 text-white rounded-xl font-black shadow-lg shadow-slate-900/20 flex items-center justify-center gap-2 transition-all active:scale-95"
                            >
                                {isCreatingManualQuote ? <Clock className="w-5 h-5 animate-pulse" /> : <Send className="w-5 h-5" />}
                                {isCreatingManualQuote ? "Création..." : "Créer le brouillon"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
