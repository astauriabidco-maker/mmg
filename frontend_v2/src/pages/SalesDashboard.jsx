import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Users, FileText, Search, ArrowRight, CheckCircle, X, DollarSign, Send, Clock, AlertTriangle, FileCheck, Plus, ListTodo, UploadCloud, Copy, Sparkles, BrainCircuit, Package, Wrench, Tag, RefreshCw, Truck, Undo2 } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import MMGDossiers from './MMGDossiers';
import WindowVisualizer from '../components/WindowVisualizer';

export default function SalesDashboard() {
    const queryClient = useQueryClient();
    const navigate = useNavigate();
    const location = useLocation();

    const [mainTab, setMainTab] = useState('pipeline'); // 'pipeline' | 'dossiers'
    const [pipelineView, setPipelineView] = useState('kanban'); // 'list' | 'kanban'
    const [searchTerm, setSearchTerm] = useState("");
    const [pipelineFilter, setPipelineFilter] = useState("all");
    const [selectedSale, setSelectedSale] = useState(null);
    const [isStatusUpdating, setIsStatusUpdating] = useState(false);
    const [isUploadingBOM, setIsUploadingBOM] = useState(false);
    const [isDeliveringFreeSale, setIsDeliveringFreeSale] = useState(false);
    const [isReturningFreeSale, setIsReturningFreeSale] = useState(false);
    const [isCreatingCreditNote, setIsCreatingCreditNote] = useState(false);
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
    const prefillHandledRef = React.useRef(null);

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

    React.useEffect(() => {
        const state = location.state || {};
        const client = state.prefillClient;
        const signature = client ? `${client.id || client.name}-${state.openManualQuote ? 'quote' : 'view'}` : null;
        if (!state.openManualQuote || !client || prefillHandledRef.current === signature) return;

        prefillHandledRef.current = signature;
        setMainTab('pipeline');
        setPipelineView('list');
        setManualQuote(prev => ({
            ...prev,
            client_name: client.name || "",
            client_contact: client.phone || "",
            client_email: client.email || "",
            client_address: client.address || "",
            lines: []
        }));
        setManualClientSearch('');
        setManualCatalogSearch('');
        setManualQuoteLineMode('stock');
        setIsManualNewClient(false);
        setShowManualQuoteModal(true);
        navigate('/manager?view=sales', { replace: true, state: { view: 'sales' } });
    }, [location.state, navigate]);

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
        navigate(`/manager?view=sale-detail&id=${sale_id}`);
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

    const deliverFreeSale = async () => {
        if (!selectedSale) return;
        if (!window.confirm("Confirmer la sortie client ? Le stock réservé sera débité définitivement.")) return;
        setIsDeliveringFreeSale(true);
        try {
            const res = await api.post(`/v2/sales/${selectedSale.id}/deliver-free-sale`);
            await Promise.all([
                queryClient.invalidateQueries(['sales']),
                queryClient.invalidateQueries(['products']),
                queryClient.invalidateQueries(['quants']),
                queryClient.invalidateQueries(['transactions']),
            ]);
            await openSaleDetails(selectedSale.id);
            alert(res.data?.message || "Sortie client effectuée.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la sortie client.");
        } finally {
            setIsDeliveringFreeSale(false);
        }
    };

    const returnFreeSale = async () => {
        if (!selectedSale) return;
        if (!window.confirm("Préparer un retour client pour ce devis livré ?")) return;
        setIsReturningFreeSale(true);
        try {
            const res = await api.post(`/v2/sales/${selectedSale.id}/return-free-sale`);
            await Promise.all([
                queryClient.invalidateQueries(['sales']),
                queryClient.invalidateQueries(['products']),
                queryClient.invalidateQueries(['quants']),
                queryClient.invalidateQueries(['transactions']),
            ]);
            await openSaleDetails(selectedSale.id);
            alert(res.data?.message || "Retour client enregistré.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors du retour client.");
        } finally {
            setIsReturningFreeSale(false);
        }
    };

    const createCreditNote = async (invoice, deliveryNoteId = null) => {
        if (!selectedSale || !invoice) return;
        if (!window.confirm(`Créer un avoir pour la facture ${invoice.reference} ?`)) return;
        setIsCreatingCreditNote(true);
        try {
            await api.post(
                `/v2/accounting/invoices/${invoice.id}/credit-note-from-return`,
                deliveryNoteId ? { delivery_note_id: deliveryNoteId } : undefined
            );
            await queryClient.invalidateQueries(['sales']);
            await openSaleDetails(selectedSale.id);
            alert("Avoir généré avec succès.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la création de l'avoir.");
        } finally {
            setIsCreatingCreditNote(false);
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
        if (status === 'returned') return 'bg-blue-50 text-blue-700 border-blue-100';
        if (status === 'cancelled') return 'bg-slate-100 text-slate-500 border-slate-200';
        return 'bg-blue-50 text-blue-700 border-blue-100';
    };
    const getReservationStatusLabel = (status) => {
        if (status === 'reserved') return 'Réservée';
        if (status === 'consumed') return 'Consommée';
        if (status === 'returned') return 'Retournée';
        if (status === 'cancelled') return 'Annulée';
        return status || 'Inconnu';
    };
    const getReservationLineSourceId = (source) => {
        const match = String(source || '').match(/^sale_order_line:(\d+)$/);
        return match ? Number(match[1]) : null;
    };
    const getSaleReservationSummary = (sale) => {
        const reservations = sale?.reservations || [];
        const activeReservations = reservations.filter(reservation => reservation.status === 'reserved');
        const totalReserved = activeReservations.reduce(
            (sum, reservation) => sum + (reservation.lines || []).reduce(
                (lineSum, line) => lineSum + Number(line.reserved_quantity || 0),
                0
            ),
            0
        );
        return { count: activeReservations.length, totalReserved };
    };
    const isCreditNote = (invoice) => {
        const status = String(invoice?.status || '').toUpperCase();
        const reference = String(invoice?.reference || '').toUpperCase();
        return status === 'AVOIR' || status === 'CREDIT_NOTE' || reference.startsWith('AV-') || Number(invoice?.total || 0) < 0;
    };
    const getSaleCreditNotes = (sale) => {
        const exposedCreditNotes = [
            ...(sale?.credit_notes || []),
            ...(sale?.creditNotes || []),
            ...(sale?.avoirs || []),
        ];
        const invoiceCreditNotes = (sale?.invoices || []).filter(isCreditNote);
        const byId = new Map();
        [...exposedCreditNotes, ...invoiceCreditNotes].forEach(creditNote => {
            if (!creditNote) return;
            byId.set(creditNote.id || creditNote.reference, creditNote);
        });
        return Array.from(byId.values());
    };
    const getSaleBillableInvoices = (sale) => (
        (sale?.invoices || []).filter(invoice => !isCreditNote(invoice) && !['DRAFT', 'CANCELLED', 'VOID'].includes(invoice.status))
    );
    const getFreeSaleTraceability = (sale) => {
        const reservations = sale?.reservations || [];
        const invoices = sale?.invoices || [];
        const billableInvoices = getSaleBillableInvoices(sale);
        const creditNotes = getSaleCreditNotes(sale);
        const deliveryNotes = sale?.delivery_notes || [];
        const activeReservations = reservations.filter(reservation => reservation.status === 'reserved');
        const consumedReservations = reservations.filter(reservation => reservation.status === 'consumed');
        const returnedReservations = reservations.filter(reservation => reservation.status === 'returned');
        const returnedDeliveryNotes = deliveryNotes.filter(note => ['RETURNED', 'CANCELLED'].includes(note.status));
        const reservedQuantity = activeReservations.reduce(
            (sum, reservation) => sum + (reservation.lines || []).reduce(
                (lineSum, line) => lineSum + Number(line.reserved_quantity || 0),
                0
            ),
            0
        );
        const hasStockLines = (sale?.lines || []).some(line => line.line_type === 'STOCK_ITEM' || line.variant_id);
        const isSigned = Boolean(sale?.signed_at) || ['VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale?.status);
        const isReserved = activeReservations.length > 0 || (sale?.lines || []).some(line => Number(line.reserved_quantity || 0) > 0);
        const isReturned = returnedReservations.length > 0 || returnedDeliveryNotes.length > 0;
        const isDelivered = !isReturned && (sale?.status === 'DELIVERED' || deliveryNotes.some(note => note.status === 'DELIVERED' || note.signed_at));
        const isInvoiced = billableInvoices.length > 0;
        const hasCreditNote = creditNotes.length > 0;

        return {
            isSigned,
            isReserved,
            isDelivered,
            isReturned,
            isInvoiced,
            hasCreditNote,
            hasStockLines,
            activeReservations,
            consumedReservations,
            returnedReservations,
            returnedDeliveryNotes,
            billableInvoices,
            creditNotes,
            reservedQuantity,
            reservationsCount: reservations.length,
            invoicesCount: invoices.length,
            billableInvoicesCount: billableInvoices.length,
            creditNotesCount: creditNotes.length,
            deliveryNotesCount: deliveryNotes.length,
        };
    };
    const getFreeSaleBusinessLabel = (sale) => {
        const trace = getFreeSaleTraceability(sale);
        if (sale?.status === 'CANCELLED') return 'Annulé';
        if (trace.isReturned) return 'Retourné';
        if (trace.isInvoiced) return 'Facturé';
        if (trace.isDelivered) return 'Livré';
        if (trace.isReserved) return 'Réservé';
        if (trace.isSigned) return 'Signé';
        if (sale?.status === 'SENT') return 'Envoyé';
        return 'Brouillon';
    };
    const getFreeSaleBusinessClass = (sale) => {
        const label = getFreeSaleBusinessLabel(sale);
        if (label === 'Facturé') return 'bg-emerald-100 text-emerald-700 border-emerald-200';
        if (label === 'Livré') return 'bg-indigo-100 text-indigo-700 border-indigo-200';
        if (label === 'Réservé') return 'bg-amber-100 text-amber-700 border-amber-200';
        if (label === 'Signé') return 'bg-blue-100 text-blue-700 border-blue-200';
        if (label === 'Retourné') return 'bg-sky-100 text-sky-700 border-sky-200';
        if (label === 'Annulé') return 'bg-red-100 text-red-700 border-red-200';
        return 'bg-slate-100 text-slate-600 border-slate-200';
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
        const zeroPricedStockLine = validLines.find(line => line.line_type === "stock" && line.unit_price <= 0);
        if (zeroPricedStockLine) {
            return alert(`Prix HT manquant: renseignez le prix de vente de "${zeroPricedStockLine.description}" avant de créer le devis.`);
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

    const getSaleDisplayLabel = (sale) => (
        (sale?.workflow_type || 'FREE_SALE') === 'FREE_SALE'
            ? getFreeSaleBusinessLabel(sale)
            : getStatusLabel(sale?.status)
    );

    const getSaleDisplayClass = (sale) => (
        (sale?.workflow_type || 'FREE_SALE') === 'FREE_SALE'
            ? getFreeSaleBusinessClass(sale)
            : getStatusColor(sale?.status)
    );

    const saleCycleSteps = [
        { key: 'draft', label: 'Brouillon', statuses: ['DRAFT'] },
        { key: 'sent', label: 'Envoyé', statuses: ['SENT'] },
        { key: 'validated', label: 'Signé', statuses: ['VALIDATED', 'IN_DESIGN'] },
        { key: 'reserved', label: 'Réservé', statuses: ['READY_FOR_PROD', 'IN_PRODUCTION'] },
        { key: 'delivered', label: 'Livré', statuses: ['DELIVERED'] },
        { key: 'billed', label: 'Facturé', statuses: [] }
    ];

    const getSaleCycleState = (sale) => {
        if (!sale) return { activeIndex: 0, isCancelled: false, hasStockLines: false, hasReservedLines: false };

        const hasStockLines = (sale.lines || []).some(line => line.line_type === 'STOCK_ITEM' || line.variant_id);
        const hasReservedLines = (sale.lines || []).some(line => Number(line.reserved_quantity || 0) > 0);
        const trace = getFreeSaleTraceability(sale);
        const statusIndex = saleCycleSteps.findIndex(step => step.statuses.includes(sale.status));
        let activeIndex = statusIndex >= 0 ? statusIndex : 0;

        if (trace.isSigned) {
            activeIndex = Math.max(activeIndex, 2);
        }
        if (hasReservedLines || trace.isReserved || ['READY_FOR_PROD', 'IN_PRODUCTION'].includes(sale.status)) {
            activeIndex = Math.max(activeIndex, 3);
        }
        if (trace.isDelivered) {
            activeIndex = 4;
        }
        if (trace.isInvoiced) {
            activeIndex = 5;
        }

        return {
            activeIndex,
            isCancelled: sale.status === 'CANCELLED',
            hasStockLines,
            hasReservedLines,
            trace
        };
    };

    const getSaleCycleCaption = (sale, stepKey) => {
        const cycle = getSaleCycleState(sale);
        if (cycle.isCancelled) return "Cycle interrompu";
        if (stepKey === 'reserved') {
            if (!cycle.hasStockLines) return "Sans stock";
            return cycle.hasReservedLines || cycle.activeIndex >= 3 ? "Stock bloqué" : "À réserver";
        }
        if (stepKey === 'delivered') {
            return cycle.trace?.isDelivered ? "BL généré" : "À livrer";
        }
        if (stepKey === 'billed') {
            return cycle.trace?.isInvoiced ? "Facture liée" : "À facturer";
        }
        if (stepKey === 'validated' && cycle.trace?.isSigned) return sale?.signed_at ? "Signature client" : "Validation";
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
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
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

    const renderSaleDetailCard = (sale) => {
        const trace = getFreeSaleTraceability(sale);
        const reservationSummary = getSaleReservationSummary(sale);
        const saleTotal = (sale.lines || []).reduce(
            (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
            0
        );
        const isFreeSale = (sale.workflow_type || 'FREE_SALE') === 'FREE_SALE';
        const billableInvoice = trace.billableInvoices?.[0];
        const returnedDeliveryNote = trace.returnedDeliveryNotes?.[0];
        const canCreateCreditNote = trace.isReturned && trace.isInvoiced && !trace.hasCreditNote && billableInvoice;
        const canDeliverFreeSale = isFreeSale && sale.status === 'VALIDATED' && reservationSummary.count > 0;

        const renderPrimaryAction = () => {
            if (sale.status === 'DRAFT') {
                return (
                    <button onClick={() => updateStatus('SENT')} disabled={isStatusUpdating} className="px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 text-white font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-blue-500/20">
                        <Send className="w-4 h-4" /> Envoyer au client
                    </button>
                );
            }
            if (sale.status === 'SENT') {
                return (
                    <button onClick={validateSale} disabled={isStatusUpdating} className="px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 text-white font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-emerald-500/20">
                        <CheckCircle className="w-4 h-4" /> Marquer signé
                    </button>
                );
            }
            if (canDeliverFreeSale) {
                return (
                    <button onClick={deliverFreeSale} disabled={isDeliveringFreeSale} className="px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 text-white font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-emerald-500/20">
                        <Truck className="w-4 h-4" /> {isDeliveringFreeSale ? "Sortie..." : "Sortie client"}
                    </button>
                );
            }
            if (trace.isDelivered) {
                return (
                    <button onClick={returnFreeSale} disabled={isReturningFreeSale} className="px-5 py-3 rounded-xl bg-white hover:bg-blue-50 border border-blue-200 text-blue-700 disabled:bg-slate-100 disabled:text-slate-400 font-black text-sm flex items-center justify-center gap-2">
                        <Undo2 className="w-4 h-4" /> {isReturningFreeSale ? "Retour..." : "Retour client"}
                    </button>
                );
            }
            if (canCreateCreditNote) {
                return (
                    <button onClick={() => createCreditNote(billableInvoice, returnedDeliveryNote?.id)} disabled={isCreatingCreditNote} className="px-5 py-3 rounded-xl bg-rose-600 hover:bg-rose-500 disabled:bg-slate-300 text-white font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-rose-500/20">
                        <FileText className="w-4 h-4" /> {isCreatingCreditNote ? "Création..." : "Créer un avoir"}
                    </button>
                );
            }
            if (!isFreeSale && sale.status === 'VALIDATED') {
                return (
                    <button onClick={sendToDesign} disabled={isStatusUpdating} className="px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 text-white font-black text-sm flex items-center justify-center gap-2 shadow-md shadow-emerald-500/20">
                        Bureau d'Études <ArrowRight className="w-4 h-4" />
                    </button>
                );
            }
            return (
                <span className="px-5 py-3 rounded-xl bg-slate-100 border border-slate-200 text-slate-500 font-black text-sm flex items-center justify-center gap-2">
                    <CheckCircle className="w-4 h-4" /> Aucune action urgente
                </span>
            );
        };

        const timeline = [
            { label: 'Brouillon', done: true, detail: formatDate(sale.created_at) },
            { label: 'Envoyé', done: ['SENT', 'VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale.status), detail: sale.status === 'DRAFT' ? 'À envoyer' : 'Client notifié' },
            { label: 'Signé', done: trace.isSigned, detail: sale.signed_at ? formatDate(sale.signed_at) : (trace.isSigned ? 'Validation interne' : 'En attente') },
            { label: 'Réservé', done: trace.isReserved, detail: trace.isReserved ? `${reservationSummary.totalReserved.toLocaleString('fr-FR')} réservé` : (trace.hasStockLines ? 'À réserver' : 'Sans stock') },
            { label: 'Livré', done: trace.isDelivered || trace.isReturned, detail: trace.isReturned ? 'Retourné' : (trace.isDelivered ? 'BL généré' : 'À livrer') },
            { label: 'Facturé', done: trace.isInvoiced, detail: trace.isInvoiced ? `${trace.billableInvoicesCount} facture(s)` : 'À facturer' },
            { label: 'Avoir', done: trace.hasCreditNote, detail: trace.hasCreditNote ? `${trace.creditNotesCount} avoir(s)` : (trace.isReturned ? 'À décider' : 'Non requis') },
        ];

        return (
            <div className="mb-8 mt-4">
                <section className="bg-white border border-slate-200 rounded-2xl shadow-lg overflow-hidden">
                    <div className="bg-slate-900 text-white px-6 py-5">
                        <div className="flex items-start justify-between gap-5">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2 mb-3">
                                    <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg border ${getSaleDisplayClass(sale)}`}>{getSaleDisplayLabel(sale)}</span>
                                    <span className={`text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-lg border ${getWorkflowBadgeClass(sale.workflow_type)}`}>{getWorkflowLabel(sale.workflow_type)}</span>
                                </div>
                                <h2 className="text-2xl font-black tracking-tight truncate">{sale.client_name}</h2>
                                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm font-bold text-slate-300">
                                    <span>{sale.reference}</span>
                                    <span>{formatDate(sale.created_at)}</span>
                                    <span>{sale.lines?.length || 0} ligne(s)</span>
                                </div>
                            </div>
                            <div className="text-right shrink-0">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total HT</p>
                                <p className="text-3xl font-black tracking-tight">{formatMoney(saleTotal)}</p>
                                <p className="text-xs font-bold text-slate-400">TVA {sale.tax_rate || 0}% · {sale.currency || 'EUR'}</p>
                            </div>
                        </div>
                    </div>

                    <div className="px-6 py-4 border-b border-slate-100 bg-slate-50">
                        <div className="flex items-center justify-between gap-4">
                            <div className="min-w-0">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">Prochaine action</p>
                                <p className="text-sm font-bold text-slate-700">
                                    {sale.status === 'DRAFT' && "Envoyer le devis au client."}
                                    {sale.status === 'SENT' && "Attendre la signature ou valider manuellement."}
                                    {canDeliverFreeSale && "Sortir les articles réservés quand ils sont remis au client."}
                                    {trace.isDelivered && "Le client a été livré. Un retour reste possible si erreur."}
                                    {canCreateCreditNote && "Retour facturé détecté: créer un avoir si la régularisation est confirmée."}
                                    {!['DRAFT', 'SENT'].includes(sale.status) && !canDeliverFreeSale && !trace.isDelivered && !canCreateCreditNote && "Le devis est à jour. Consultez la timeline et les documents liés."}
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2 justify-end shrink-0">
                                {renderPrimaryAction()}
                                <a href={`${api.defaults.baseURL}/v2/pdf/quote/${sale.id}`} target="_blank" rel="noopener noreferrer" className="px-4 py-3 rounded-xl bg-white border border-slate-200 text-slate-800 hover:bg-slate-100 font-black text-sm flex items-center justify-center gap-2">
                                    <FileText className="w-4 h-4" /> PDF devis
                                </a>
                                {!['CANCELLED', 'DELIVERED'].includes(sale.status) && (
                                    <button onClick={() => updateStatus('CANCELLED')} className="px-4 py-3 rounded-xl bg-white border border-red-200 text-red-600 hover:bg-red-50 font-black text-sm flex items-center justify-center gap-2">
                                        <X className="w-4 h-4" /> Refuser
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="p-5 space-y-5">
                        <div className="grid grid-cols-3 gap-3">
                            <div className="border border-slate-200 rounded-xl p-3 bg-white min-w-0">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Client</p>
                                <p className="text-sm font-black text-slate-900 truncate">{sale.client_contact || 'Contact non renseigné'}</p>
                                <p className="text-xs font-bold text-slate-500 truncate">{sale.client_email || 'Email non renseigné'}</p>
                            </div>
                            <div className="border border-slate-200 rounded-xl p-3 bg-white min-w-0">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Conditions</p>
                                <p className="text-sm font-black text-slate-900">Validité {sale.validity_days} jours</p>
                                <p className="text-xs font-bold text-slate-500 truncate">{getWorkflowLabel(sale.workflow_type)}</p>
                            </div>
                            <div className="border border-slate-200 rounded-xl p-3 bg-white min-w-0">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Adresse</p>
                                <p className="text-sm font-black text-slate-900 line-clamp-2">{sale.client_address || 'Adresse non renseignée'}</p>
                            </div>
                        </div>

                        {getWorkshopBlockedMessage(sale) && (
                            <div className="border border-amber-200 rounded-xl p-4 bg-amber-50">
                                <p className="text-[10px] font-black uppercase tracking-widest text-amber-700 mb-1">Règle métier</p>
                                <p className="text-sm font-bold text-amber-900">{getWorkshopBlockedMessage(sale)}</p>
                            </div>
                        )}

                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Cycle métier</p>
                            <div className="grid grid-cols-7 gap-2">
                                {timeline.map((step, index) => (
                                    <div key={step.label} className={`rounded-xl border p-3 min-w-0 ${step.done ? 'bg-emerald-50 border-emerald-100' : 'bg-slate-50 border-slate-200'}`}>
                                        <div className={`w-7 h-7 rounded-full flex items-center justify-center mb-2 ${step.done ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-500'}`}>
                                            {step.done ? <CheckCircle className="w-4 h-4" /> : <span className="text-xs font-black">{index + 1}</span>}
                                        </div>
                                        <p className="font-black text-slate-900 text-sm truncate">{step.label}</p>
                                        <p className="text-[11px] font-bold text-slate-500 truncate">{step.detail}</p>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="grid grid-cols-[1.2fr_0.8fr] gap-4 items-start">
                            <div className="border border-slate-200 rounded-xl p-4 bg-white">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Documents</p>
                                <div className="space-y-2">
                                        <a href={`${api.defaults.baseURL}/v2/pdf/quote/${sale.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm font-black text-slate-800 hover:bg-slate-100">
                                            <span>Devis PDF</span><FileText className="w-4 h-4" />
                                        </a>
                                        {sale.signature_token && (
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    navigator.clipboard.writeText(`${window.location.origin}/portal/sign/${sale.signature_token}`);
                                                    alert("Lien de signature copié.");
                                                }}
                                                className="w-full flex items-center justify-between gap-3 rounded-xl border border-indigo-100 bg-indigo-50 p-3 text-sm font-black text-indigo-900 hover:bg-indigo-100"
                                            >
                                                <span>Lien signature client</span><Copy className="w-4 h-4" />
                                            </button>
                                        )}
                                        {trace.billableInvoices.map(invoice => (
                                            <a key={invoice.id} href={`${api.defaults.baseURL}/v2/pdf/invoice/${invoice.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm font-black text-blue-900 hover:bg-blue-100">
                                                <span>{invoice.reference} · {formatMoney(invoice.total)}</span><FileText className="w-4 h-4" />
                                            </a>
                                        ))}
                                        {trace.creditNotes.map(creditNote => (
                                            <a key={creditNote.id || creditNote.reference} href={`${api.defaults.baseURL}/v2/pdf/invoice/${creditNote.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-rose-100 bg-rose-50 p-3 text-sm font-black text-rose-900 hover:bg-rose-100">
                                                <span>{creditNote.reference || 'Avoir'} · {formatMoney(creditNote.total)}</span><FileText className="w-4 h-4" />
                                            </a>
                                        ))}
                                        {sale.delivery_notes?.map(note => (
                                            <a key={note.id} href={`${api.defaults.baseURL}/v2/pdf/delivery-note/${note.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-sm font-black text-emerald-900 hover:bg-emerald-100">
                                                <span>{note.reference} · {note.status}</span><Truck className="w-4 h-4" />
                                            </a>
                                        ))}
                                </div>
                            </div>

                            <div className="border border-slate-200 rounded-xl p-4 bg-white">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Stock & réservations</p>
                                {sale.reservations?.length > 0 ? (
                                    <div className="space-y-3">
                                        {sale.reservations.map(reservation => {
                                            const totalReserved = reservation.lines?.reduce((sum, line) => sum + Number(line.reserved_quantity || 0), 0) || 0;
                                            return (
                                                <div key={reservation.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div className="min-w-0">
                                                            <p className="text-sm font-black text-slate-900 break-all">{reservation.reference}</p>
                                                            <p className="text-xs font-bold text-slate-500">{formatDate(reservation.created_at)}</p>
                                                        </div>
                                                        <span className={`shrink-0 px-2 py-1 rounded-lg border text-[10px] font-black uppercase tracking-widest ${getReservationStatusClass(reservation.status)}`}>
                                                            {getReservationStatusLabel(reservation.status)}
                                                        </span>
                                                    </div>
                                                    <p className="mt-2 text-xs font-black uppercase tracking-widest text-slate-500">{totalReserved.toLocaleString('fr-FR')} unité(s)</p>
                                                </div>
                                            );
                                        })}
                                    </div>
                                ) : (
                                    <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm font-bold text-slate-400">Aucune réservation rattachée.</p>
                                )}
                            </div>
                        </div>

                        <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
                            <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Lignes du devis</p>
                                <span className="text-xs font-black text-slate-500">{sale.lines?.length || 0} ligne(s)</span>
                            </div>
                            <div className="divide-y divide-slate-100">
                                {(sale.lines || []).map((line, idx) => {
                                    const lineTotal = Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100);
                                    return (
                                        <div key={line.id || idx} className="grid grid-cols-[1fr_120px_60px_110px] gap-3 p-4 items-center">
                                            <div className="min-w-0">
                                                <p className="font-black text-slate-900 leading-tight">{line.description}</p>
                                                {line.variant?.reference && <p className="mt-1 text-xs font-mono font-black text-slate-400">{line.variant.reference}</p>}
                                            </div>
                                            <span className={`inline-flex items-center justify-center gap-1 px-2 py-1 rounded-lg border text-[10px] font-black uppercase tracking-widest ${getLineTypeClass(line.line_type)}`}>
                                                {line.line_type === 'STOCK_ITEM' ? <Package className="w-3 h-3" /> : <Wrench className="w-3 h-3" />}
                                                {getLineTypeLabel(line.line_type)}
                                            </span>
                                            <p className="text-center font-black text-blue-700">{line.quantity}</p>
                                            <p className="text-right font-black text-slate-900">{formatMoney(lineTotal)}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {sale.notes && (
                            <div className="bg-yellow-50/70 border border-yellow-100 rounded-xl p-4 flex gap-3">
                                <FileCheck className="w-5 h-5 text-yellow-600 shrink-0" />
                                <p className="text-sm font-bold text-yellow-900">{sale.notes}</p>
                            </div>
                        )}
                    </div>
                </section>
            </div>
        );
    };

    const getSaleTotal = (sale) => (sale?.lines || []).reduce(
        (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
        0
    );

    const getSaleNextAction = (sale) => {
        const trace = getFreeSaleTraceability(sale);
        const reservationSummary = getSaleReservationSummary(sale);
        const isFreeSale = (sale?.workflow_type || 'FREE_SALE') === 'FREE_SALE';
        if (sale?.status === 'DRAFT') return { label: 'Envoyer au client', tone: 'blue' };
        if (sale?.status === 'SENT') return { label: 'Relancer signature', tone: 'amber' };
        if (isFreeSale && sale?.status === 'VALIDATED' && reservationSummary.count > 0) return { label: 'Sortie client à faire', tone: 'emerald' };
        if (trace.isDelivered && !trace.isReturned) return { label: 'Livré, surveiller retour', tone: 'indigo' };
        if (trace.isReturned && trace.isInvoiced && !trace.hasCreditNote) return { label: 'Avoir à décider', tone: 'rose' };
        if (!isFreeSale && sale?.status === 'VALIDATED') return { label: 'Envoyer au BE', tone: 'emerald' };
        if (!isFreeSale && ['IN_DESIGN', 'READY_FOR_PROD'].includes(sale?.status)) return { label: 'Préparer atelier', tone: 'amber' };
        if (sale?.status === 'CANCELLED') return { label: 'Clôturé', tone: 'slate' };
        return { label: 'À jour', tone: 'slate' };
    };

    const getNextActionClass = (tone) => {
        if (tone === 'blue') return 'bg-blue-50 text-blue-700 border-blue-100';
        if (tone === 'amber') return 'bg-amber-50 text-amber-700 border-amber-100';
        if (tone === 'emerald') return 'bg-emerald-50 text-emerald-700 border-emerald-100';
        if (tone === 'indigo') return 'bg-indigo-50 text-indigo-700 border-indigo-100';
        if (tone === 'rose') return 'bg-rose-50 text-rose-700 border-rose-100';
        return 'bg-slate-100 text-slate-600 border-slate-200';
    };

    const pipelineFilters = [
        { key: 'all', label: 'Tous', match: () => true },
        { key: 'to_send', label: 'À envoyer', match: (sale) => sale.status === 'DRAFT' },
        { key: 'to_sign', label: 'À signer', match: (sale) => sale.status === 'SENT' },
        { key: 'to_deliver', label: 'À livrer', match: (sale) => {
            const trace = getFreeSaleTraceability(sale);
            return (sale.workflow_type || 'FREE_SALE') === 'FREE_SALE' && sale.status === 'VALIDATED' && trace.isReserved;
        }},
        { key: 'to_invoice', label: 'À facturer', match: (sale) => {
            const trace = getFreeSaleTraceability(sale);
            return trace.isDelivered && !trace.isInvoiced;
        }},
        { key: 'returns', label: 'Retours/Avoirs', match: (sale) => {
            const trace = getFreeSaleTraceability(sale);
            return trace.isReturned || trace.hasCreditNote;
        }},
        { key: 'fabrication', label: 'Fabrication', match: (sale) => (sale.workflow_type || 'FREE_SALE') !== 'FREE_SALE' },
    ];

    const SalePipelineCard = ({ sale, compact = false }) => {
        const total = getSaleTotal(sale);
        const trace = getFreeSaleTraceability(sale);
        const nextAction = getSaleNextAction(sale);
        const stockLines = (sale.lines || []).filter(line => line.line_type === 'STOCK_ITEM' || line.variant_id).length;
        const serviceLines = (sale.lines || []).length - stockLines;
        return (
            <div
                draggable={!compact}
                onDragStart={(event) => !compact && handleDragStart(event, sale.id)}
                onClick={() => openSaleDetails(sale.id)}
                className={`bg-white border cursor-pointer transition-all ${compact ? 'p-4 rounded-2xl hover:border-blue-300 hover:shadow-md' : 'p-4 rounded-2xl shadow-sm hover:shadow-md cursor-grab active:cursor-grabbing'} ${selectedSale?.id === sale.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-slate-200'}`}
            >
                <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                        <p className="font-black text-slate-900 leading-tight truncate">{sale.client_name}</p>
                        <p className="mt-1 text-[10px] font-mono font-black text-slate-400 uppercase">{sale.reference}</p>
                    </div>
                    <p className="font-black text-slate-900 whitespace-nowrap">{formatMoney(total)}</p>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getSaleDisplayClass(sale)}`}>{getSaleDisplayLabel(sale)}</span>
                    <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-md border ${getWorkflowBadgeClass(sale.workflow_type)}`}>{getWorkflowLabel(sale.workflow_type)}</span>
                </div>
                <div className={`mt-3 rounded-xl border px-3 py-2 text-xs font-black ${getNextActionClass(nextAction.tone)}`}>
                    {nextAction.label}
                </div>
                <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                    <div className="rounded-lg bg-slate-50 border border-slate-100 p-2">
                        <p className="text-[9px] font-black uppercase text-slate-400">Stock</p>
                        <p className="font-black text-slate-800">{stockLines}</p>
                    </div>
                    <div className="rounded-lg bg-slate-50 border border-slate-100 p-2">
                        <p className="text-[9px] font-black uppercase text-slate-400">Prest.</p>
                        <p className="font-black text-slate-800">{serviceLines}</p>
                    </div>
                    <div className="rounded-lg bg-slate-50 border border-slate-100 p-2">
                        <p className="text-[9px] font-black uppercase text-slate-400">Rés.</p>
                        <p className="font-black text-slate-800">{trace.reservationsCount}</p>
                    </div>
                    <div className="rounded-lg bg-slate-50 border border-slate-100 p-2">
                        <p className="text-[9px] font-black uppercase text-slate-400">Docs</p>
                        <p className="font-black text-slate-800">{trace.billableInvoicesCount + trace.creditNotesCount + trace.deliveryNotesCount}</p>
                    </div>
                </div>
                <SaleCycleIndicator sale={sale} compact />
            </div>
        );
    };

    const activePipelineFilter = pipelineFilters.find(filter => filter.key === pipelineFilter) || pipelineFilters[0];
    const filteredSales = sales
        .filter(s =>
            s.reference.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.client_name.toLowerCase().includes(searchTerm.toLowerCase())
        )
        .filter(s => activePipelineFilter.match(s));

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
            <div className="bg-slate-900 px-6 py-4 flex flex-wrap items-center justify-between gap-4 shrink-0 rounded-t-[2rem]">
                <div className="flex flex-wrap gap-3">
                <button
                    onClick={() => {
                        setMainTab('pipeline');
                        setPipelineView('kanban');
                    }}
                    className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'pipeline' && pipelineView === 'kanban' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:bg-slate-800'}`}
                >
                    <DollarSign className="w-5 h-5"/> Pipeline
                </button>
                <button
                    onClick={() => {
                        setMainTab('pipeline');
                        setPipelineView('list');
                    }}
                    className={`px-6 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'pipeline' && pipelineView === 'list' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-400 hover:bg-slate-800'}`}
                >
                    <FileText className="w-5 h-5"/> Liste devis
                </button>
                </div>
                <button
                    onClick={() => setMainTab('dossiers')}
                    className={`px-5 py-2.5 rounded-xl font-bold flex items-center gap-2 transition-all ${mainTab === 'dossiers' ? 'bg-emerald-600 text-white shadow-lg' : 'text-emerald-200 hover:bg-slate-800'}`}
                >
                    <ListTodo className="w-5 h-5"/> Métrés fabrication
                </button>
            </div>

            {mainTab === 'dossiers' && (
                <div className="flex-1 overflow-hidden">
                    <MMGDossiers isEmbedded={true} />
                </div>
            )}

            {mainTab === 'pipeline' && (
            <div className="flex-1 flex flex-col overflow-hidden relative">
                {/* PIPELINE HEADER CONTROLS */}
	                <div className="bg-white border-b border-slate-200 p-4 shrink-0 z-20 space-y-4">
	                    <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
	                        <div className="flex flex-wrap items-center gap-4">
	                            <h3 className="font-black text-slate-900 flex items-center gap-2 tracking-tight text-lg">
	                                <Users className="text-blue-600 w-5 h-5"/> Ventes & Devis
	                            </h3>
	                            <div className="flex items-center gap-3">
	                                <div className="rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
	                                    <span className="block text-[9px] font-black text-blue-400 uppercase tracking-widest">Pipeline</span>
	                                    <span className="text-sm font-black text-blue-700">{pipelineValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0})}</span>
	                                </div>
	                                <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2">
	                                    <span className="block text-[9px] font-black text-emerald-500 uppercase tracking-widest">Validé</span>
	                                    <span className="text-sm font-black text-emerald-700">{validatedValue.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0})}</span>
	                                </div>
	                            </div>
	                        </div>

	                        <div className="flex flex-wrap items-center gap-3">
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
	                    <div className="flex gap-2 overflow-x-auto pb-1">
	                        {pipelineFilters.map(filter => {
	                            const count = sales.filter(filter.match).length;
	                            return (
	                                <button
	                                    key={filter.key}
	                                    onClick={() => setPipelineFilter(filter.key)}
	                                    className={`shrink-0 px-3 py-2 rounded-xl border text-xs font-black transition-all ${pipelineFilter === filter.key ? 'bg-slate-900 text-white border-slate-900 shadow-sm' : 'bg-white text-slate-600 border-slate-200 hover:border-blue-200 hover:text-blue-700'}`}
	                                >
	                                    {filter.label} <span className={pipelineFilter === filter.key ? 'text-slate-300' : 'text-slate-400'}>{count}</span>
	                                </button>
	                            );
	                        })}
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
	                                            {colSales.map(sale => (
	                                                <SalePipelineCard key={sale.id} sale={sale} />
	                                            ))}
	                                            {colSales.length === 0 && (
	                                                <div className="h-32 rounded-2xl border border-dashed border-slate-200 bg-white/60 flex items-center justify-center text-center px-4">
	                                                    <p className="text-sm font-bold text-slate-400">Aucun devis dans cette étape.</p>
	                                                </div>
	                                            )}
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

                    {/* LIST VIEW */}
                    {pipelineView === 'list' && (
                        <div className="flex-1 overflow-y-auto p-6">
                            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                                <div className="grid grid-cols-[1.1fr_170px_170px_140px_180px] gap-4 px-5 py-3 bg-slate-50 border-b border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-400">
                                    <span>Client / devis</span>
                                    <span>Workflow</span>
                                    <span>Statut métier</span>
                                    <span className="text-right">Montant HT</span>
                                    <span>Prochaine action</span>
                                </div>
                                <div className="divide-y divide-slate-100">
                                    {filteredSales.map(sale => {
                                        const total = getSaleTotal(sale);
                                        const nextAction = getSaleNextAction(sale);
                                        return (
                                            <button
                                                key={sale.id}
                                                type="button"
                                                onClick={() => openSaleDetails(sale.id)}
                                                className="w-full grid grid-cols-[1.1fr_170px_170px_140px_180px] gap-4 px-5 py-4 items-center text-left hover:bg-blue-50/40 transition-colors"
                                            >
                                                <div className="min-w-0">
                                                    <p className="font-black text-slate-900 truncate">{sale.client_name}</p>
                                                    <p className="mt-1 text-xs font-mono font-black text-slate-400">{sale.reference} · {formatDate(sale.created_at)}</p>
                                                </div>
                                                <span className={`justify-self-start text-[10px] font-black uppercase tracking-widest px-2.5 py-1.5 rounded-lg border ${getWorkflowBadgeClass(sale.workflow_type)}`}>
                                                    {getWorkflowLabel(sale.workflow_type)}
                                                </span>
                                                <span className={`justify-self-start text-[10px] font-black uppercase tracking-widest px-2.5 py-1.5 rounded-lg border ${getSaleDisplayClass(sale)}`}>
                                                    {getSaleDisplayLabel(sale)}
                                                </span>
                                                <p className="font-black text-slate-900 text-right">{formatMoney(total)}</p>
                                                <span className={`justify-self-start rounded-xl border px-3 py-2 text-xs font-black ${getNextActionClass(nextAction.tone)}`}>
                                                    {nextAction.label}
                                                </span>
                                            </button>
                                        );
                                    })}
                                    {filteredSales.length === 0 && (
                                        <div className="p-12 text-center">
                                            <FileText className="w-12 h-12 mx-auto text-slate-200 mb-3" />
                                            <p className="text-sm font-black text-slate-500">Aucun devis trouvé avec les filtres actuels.</p>
                                            <p className="text-xs font-bold text-slate-400 mt-1">Changez le filtre ou la recherche.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
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
                                                    const isBlockedForQuote = item.isDraft;
                                                    return (
                                                    <button
                                                        key={item.variant_id}
                                                        type="button"
                                                        onClick={() => addStockLineFromCatalog(item)}
                                                        disabled={isBlockedForQuote}
                                                        className={`w-full text-left border rounded-xl p-3 transition-all ${isBlockedForQuote ? 'border-amber-200 bg-amber-50/60 cursor-not-allowed opacity-75' : item.unitPrice <= 0 ? 'border-amber-200 bg-amber-50/50 hover:border-amber-300 hover:bg-amber-50' : 'border-slate-200 hover:border-blue-300 hover:bg-blue-50/40'}`}
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
                                                            <p className="mt-2 text-[11px] font-bold text-amber-700">Prix catalogue absent: ajoutez l'article puis renseignez le prix HT sur la ligne.</p>
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
                                                            className={`w-full bg-white border rounded-xl px-3 py-2 text-sm font-bold text-slate-800 outline-none focus:ring-2 focus:ring-blue-500 ${line.line_type === 'stock' && Number(line.unit_price || 0) <= 0 ? 'border-amber-300 bg-amber-50' : 'border-slate-200'}`}
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
                                                        <div className={`col-span-12 rounded-xl px-3 py-2 text-xs font-bold flex items-center gap-2 ${stockShortage ? 'bg-red-50 text-red-700 border border-red-100' : Number(line.unit_price || 0) <= 0 ? 'bg-amber-50 text-amber-800 border border-amber-100' : 'bg-slate-50 text-slate-600 border border-slate-100'}`}>
                                                            <Tag className="w-4 h-4 shrink-0" />
                                                            {Number(line.unit_price || 0) <= 0
                                                                ? "Prix HT obligatoire avant création du devis. La référence catalogue est conservée."
                                                                : `Stock disponible: ${Math.round(Number(line.available_stock || 0) * 100) / 100} ${line.unit || 'u'}.`}
                                                            {Number(line.unit_price || 0) > 0 && (stockShortage ? " Quantité demandée supérieure au stock connu: vérifiez avant envoi." : " Référence catalogue conservée sur la ligne de devis.")}
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
