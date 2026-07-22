import React, { useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { downloadFileWithFeedback } from '../services/pdf';
import {
    Package, MapPin, Search, Plus, Trash2, Layers,
    ArrowRight, Box, Hash, ChevronRight, ChevronDown,
    Check, X, FileEdit, Truck, RefreshCw, FolderOpen, MoreVertical, Edit3, FileText, Image, LayoutGrid, List, Download, TrendingUp, ClipboardCheck, AlertTriangle, ArrowLeft
} from 'lucide-react';
import ChatterWidget from '../components/ChatterWidget';
import StockValuationView from '../components/StockValuationView';
import { useAuth } from '../context/AuthContext';

export default function StockDashboard() {
    const queryClient = useQueryClient();
    const { user } = useAuth();
    const isManager = user?.role === 'ADMIN' || user?.role === 'MANAGER';
    const isAdmin = user?.role === 'ADMIN';
    const can = (permission) => user?.permissions?.includes('*') || user?.permissions?.includes(permission);
    // Aligné strictement sur les permissions fines du backend (v2_stock.py /
    // seed_permissions.py) : pas de fallback STOCK_EDIT legacy, sinon un rôle
    // ne possédant que STOCK_EDIT verrait des boutons actifs aboutissant à un 403.
    const stockPermissions = {
        receive: can('stock.receive'),
        transfer: can('stock.transfer'),
        adjust: can('stock.adjust'),
        manageLocations: can('stock.locations.manage'),
        qualifyCatalog: can('catalog.qualify'),
        reserveWorkshop: can('workshop.reserve_stock'),
        consumeWorkshop: can('workshop.consume_stock'),
        countInventory: can('inventory.count'),
        validateInventory: can('inventory.validate'),
        receivePurchases: can('purchases.receive'),
        requestPurchases: can('purchases.request'),
    };
    const canManageLocations = isAdmin || stockPermissions.manageLocations;

    const { data: appConfigs = [] } = useQuery({ queryKey: ['configs'], queryFn: async () => { const res = await api.get('/v2/config/app_configs'); return res.data; }});
    const { data: products = [], isLoading: loadingProducts } = useQuery({ queryKey: ['products'], queryFn: async () => { const res = await api.get('/v2/stock/products'); return res.data; }});
    const { data: locations = [], isLoading: loadingLocations } = useQuery({ queryKey: ['locations'], queryFn: async () => { const res = await api.get('/v2/stock/locations'); return res.data; }});
    const { data: quants = [], isLoading: loadingQuants } = useQuery({ queryKey: ['quants'], queryFn: async () => { const res = await api.get('/v2/stock/quants'); return res.data; }});
    const { data: transactions = [], isLoading: loadingTransactions } = useQuery({ queryKey: ['transactions'], queryFn: async () => { const res = await api.get('/v2/stock/transactions'); return res.data; }});
    const { data: reservations = [] } = useQuery({ queryKey: ['workshop-reservations'], queryFn: async () => { const res = await api.get('/v2/stock/workshop-debits/reservations?status=reserved'); return res.data; }});
    const { data: workshopContexts = { sales: [], production_orders: [] } } = useQuery({ queryKey: ['workshop-debit-contexts'], queryFn: async () => { const res = await api.get('/v2/stock/workshop-debits/contexts'); return res.data; }});
    const { data: inventorySessions = [] } = useQuery({ queryKey: ['inventory-sessions'], queryFn: async () => { const res = await api.get('/v2/stock/inventory-sessions'); return res.data; }});
    const { data: purchases = [] } = useQuery({ queryKey: ['purchases'], queryFn: async () => { const res = await api.get('/v2/purchases/'); return res.data; }});
    const { data: purchaseNeedsPayload = { summary: {}, needs: [], groups: [] }, isLoading: loadingPurchaseNeeds } = useQuery({
        queryKey: ['purchase-needs', 'stock-risk'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/needs');
            return res.data;
        },
    });

    const [activeLocationId, setActiveLocationId] = useState('global'); // 'global' or a precise ID
    const [searchTerm, setSearchTerm] = useState('');
    const [currentMenu, setCurrentMenu] = useState('todo'); // 'todo' | 'risk' | 'catalog' | 'stock' | 'services' | 'drafts' | 'locations' | 'workshop' | 'audit' | 'physical-inventory' | 'import-export' | 'valuation' | 'product-detail' | 'location-detail'
    const [inventoryFocus, setInventoryFocus] = useState('catalog'); // 'catalog' | 'stock' | 'drafts' | 'services'
    const [todoRoleFilter, setTodoRoleFilter] = useState('me'); // 'me' | 'stock' | 'atelier' | 'catalogue' | 'achats' | 'manager'
    const [viewMode, setViewMode] = useState('list'); // 'list' | 'kanban'
    const [showLowStockOnly, setShowLowStockOnly] = useState(false);
    const [showDraftOnly, setShowDraftOnly] = useState(false);
    const [expandedProducts, setExpandedProducts] = useState({});
    const [selectedProductId, setSelectedProductId] = useState(null);
    const [selectedLocationId, setSelectedLocationId] = useState(null);
    // Mémorise l'écran d'origine de la fiche produit (catalogue, fiche
    // emplacement...) pour que "Retour" restaure le bon contexte.
    const [productDetailReturnMenu, setProductDetailReturnMenu] = useState(null);

    // Inline edit states
    const [addingSubLocTo, setAddingSubLocTo] = useState(null);
    const [newSubLocName, setNewSubLocName] = useState('');

    const [editingQuant, setEditingQuant] = useState(null); // { variantId: 1, locId: 2 }
    const [quantInputValue, setQuantInputValue] = useState('');

    // Modals
    const [showTransferModal, setShowTransferModal] = useState(false);
    const [transferData, setTransferData] = useState({ variant: null, sourceLocId: null, targetLocId: '', qty: '' });

    const [showNewProductModal, setShowNewProductModal] = useState(false);
    const [showImportModal, setShowImportModal] = useState(false);
    const [showLocationManagerModal, setShowLocationManagerModal] = useState(false);
    const locationNameInputRef = useRef(null);
    const [massImportFile, setMassImportFile] = useState(null);
    const [draftCatalogFile, setDraftCatalogFile] = useState(null);
    const [draftCatalogImporting, setDraftCatalogImporting] = useState(false);
    const [showWorkshopDebitModal, setShowWorkshopDebitModal] = useState(false);
    const [workshopFiles, setWorkshopFiles] = useState([]);
    const [workshopContextValue, setWorkshopContextValue] = useState('');
    const [workshopSourceLocation, setWorkshopSourceLocation] = useState('');
    const [workshopPreview, setWorkshopPreview] = useState(null);
    const [workshopLoading, setWorkshopLoading] = useState(false);
    const [reservationActionId, setReservationActionId] = useState(null);
    const [locationForm, setLocationForm] = useState({ name: '', usage: 'internal', parent_id: '' });
    const [editingLocationId, setEditingLocationId] = useState(null);
    const [editingLocationName, setEditingLocationName] = useState('');
    const [newProductForm, setNewProductForm] = useState({
        reference_base: '', name: '', material_type: 'PVC', unit: 'pce', supplier: '', product_type: 'stockable', available_in_pos: false, image_url: '', technical_doc_url: '', compatible_series: '',
        variant_ref: '', barcode: '', color: '', length_per_unit: '', supplier_reference: '', cost_price: '', min_threshold: 10, location: ''
    });

    const [showEditProductModal, setShowEditProductModal] = useState(false);
    const [editProductForm, setEditProductForm] = useState(null);

    const [showEditVariantModal, setShowEditVariantModal] = useState(false);
    const [editVariantForm, setEditVariantForm] = useState(null);

    const [showAddVariantModal, setShowAddVariantModal] = useState(false);
    const [addVariantForm, setAddVariantForm] = useState(null);

    const [showReceptionModal, setShowReceptionModal] = useState(false);
    const [receptionData, setReceptionData] = useState({ variant: null, targetLocId: '', qty: '' });
    const [receptionSearch, setReceptionSearch] = useState('');
    const [showCustomerIssueModal, setShowCustomerIssueModal] = useState(false);
    const [customerIssueData, setCustomerIssueData] = useState({ variant: null, sourceLocId: '', qty: '', reason: '' });
    const [customerIssueSearch, setCustomerIssueSearch] = useState('');
    const [riskActionVariantId, setRiskActionVariantId] = useState(null);

    const handleFileUpload = async (file, setForm, currentForm, field = 'image_url') => {
        const formData = new FormData();
        formData.append("file", file);
        try {
            const res = await api.post('/v2/stock/products/upload_image', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setForm({...currentForm, [field]: res.data.image_url});
        } catch(e) {
            alert("Erreur lors de l'upload du fichier");
        }
    };

    const handleFileInput = (e, setForm, currentForm, field = 'image_url') => {
        if (e.target.files && e.target.files.length > 0) {
            handleFileUpload(e.target.files[0], setForm, currentForm, field);
        }
    };

    const handlePaste = (e, setForm, currentForm) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const file = items[i].getAsFile();
                handleFileUpload(file, setForm, currentForm, 'image_url');
                e.preventDefault();
                break;
            }
        }
    };

    const defaultNewProductForm = (type = 'stockable') => ({
        reference_base: '',
        name: '',
        material_type: type === 'service' ? 'SERVICE' : 'PVC',
        unit: type === 'service' ? 'forfait' : 'pce',
        supplier: type === 'service' ? 'MMG' : '',
        product_type: type,
        available_in_pos: false,
        image_url: '',
        technical_doc_url: '',
        compatible_series: type === 'service' ? 'Prestation devis libre' : '',
        variant_ref: '',
        barcode: '',
        color: '',
        length_per_unit: '',
        supplier_reference: '',
        cost_price: '',
        min_threshold: type === 'service' ? 0 : 10,
        location: ''
    });

    const openNewProductModal = (type = 'stockable') => {
        setNewProductForm(defaultNewProductForm(type));
        if (type === 'service') {
            selectInventoryFocus('services');
        }
        setShowNewProductModal(true);
    };

    const openSubLocationForm = (parentLoc = null) => {
        setLocationForm({
            name: '',
            usage: parentLoc?.usage || 'internal',
            parent_id: parentLoc ? String(parentLoc.id) : '',
        });
        setShowLocationManagerModal(true);
        window.setTimeout(() => locationNameInputRef.current?.focus(), 80);
    };


    // -------- INLINE LOCATION CREATION --------
    const handleAddSubLocation = async (e, parentId) => {
        if (e && e.preventDefault) e.preventDefault();
        if (!newSubLocName.trim()) { setAddingSubLocTo(null); return; }

        // Find parent to inherit usage, or default to internal
        const parent = locations.find(l => l.id === parentId);
        const usage = parent ? parent.usage : 'internal';

        try {
            await api.post('/v2/stock/locations', {
                name: newSubLocName,
                usage: usage,
                parent_id: parentId === 'root' ? null : parentId
            });
            setNewSubLocName('');
            setAddingSubLocTo(null);
            queryClient.invalidateQueries();
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur lors de la création du lieu.");
        }
    };

    const handleDeleteLocation = async (id, e) => {
        if (e?.stopPropagation) e.stopPropagation();
        if (!window.confirm("Action critique. Souhaitez-vous retirer ce lieu ?")) return;
        try {
            const res = await api.delete(`/v2/stock/locations/${id}`);
            if (activeLocationId === id) setActiveLocationId('global');
            await queryClient.invalidateQueries({ queryKey: ['locations'] });

            if (res.data && res.data.status === 'archived') {
                alert("Information : Cet emplacement ayant un historique de mouvements, il n'a pas été supprimé mais Archivé.");
            } else {
                alert("Emplacement supprimé avec succès.");
            }
        } catch (error) {
            console.error(error);
            const errDetail = error.response?.data?.detail || error.message || "Impossible de traiter la demande.";
            alert("Erreur : " + errDetail);
        }
    };

    const handleCreateManagedLocation = async (event) => {
        event.preventDefault();
        if (!locationForm.name.trim()) return;
        try {
            await api.post('/v2/stock/locations', {
                name: locationForm.name.trim(),
                usage: locationForm.usage,
                parent_id: locationForm.parent_id ? Number(locationForm.parent_id) : null,
            });
            setLocationForm({ name: '', usage: 'internal', parent_id: '' });
            await queryClient.invalidateQueries({ queryKey: ['locations'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Création de zone impossible.");
        }
    };

    const startEditLocation = (location) => {
        setEditingLocationId(location.id);
        setEditingLocationName(location.name);
    };

    const saveLocationName = async (locationId) => {
        if (!editingLocationName.trim()) return;
        try {
            await api.put(`/v2/stock/locations/${locationId}`, { name: editingLocationName.trim() });
            setEditingLocationId(null);
            setEditingLocationName('');
            await queryClient.invalidateQueries({ queryKey: ['locations'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Renommage impossible.");
        }
    };

    // -------- INLINE QUANT EDITING (Auto-Adjustment) --------
    const startEditingQuant = (variantId, locId, currentQty) => {
        setEditingQuant({ variantId, locId });
        setQuantInputValue(currentQty.toString());
    };

    const submitQuantEdit = async () => {
        if (!editingQuant) return;
        const newVal = parseFloat(quantInputValue);
        if (isNaN(newVal)) { setEditingQuant(null); return; }

        const { variantId, locId } = editingQuant;
        const currentQuant = quants.find(q => q.variant_id === variantId && q.location_id === locId);
        const currentQty = currentQuant ? currentQuant.quantity : 0;

        const diff = newVal - currentQty;
        if (diff === 0) { setEditingQuant(null); return; }

        // Determine counter-part location (Inventory Virtual)
        const inventoryLoc = locations.find(l => l.usage === 'inventory');
        if (!inventoryLoc) {
            alert("Veuillez d'abord créer un lieu virtuel (usage: Perte/Ajustement) pour balancer l'inventaire dans la hiérarchie.");
            setEditingQuant(null);
            return;
        }

        const src = diff > 0 ? inventoryLoc.id : locId;
        const dst = diff > 0 ? locId : inventoryLoc.id;
        const qty = Math.abs(diff);

        try {
            await api.post('/v2/stock/transaction', {
                variant_id: variantId,
                quantity: qty,
                location_id: src,
                location_dest_id: dst,
                notes: "Ajustement express"
            });
            queryClient.invalidateQueries();
        } catch (e) {
            alert("Erreur à l'ajustement du stock.");
        }
        setEditingQuant(null);
    };

    const handleQuantInputKeyDown = (e) => {
        if (e.key === 'Enter') submitQuantEdit();
        if (e.key === 'Escape') setEditingQuant(null);
    };

    // -------- EXPLICIT TRANSFER (A -> B) --------
    const openTransferModal = (variant, sourceLocId) => {
        setTransferData({ variant, sourceLocId, targetLocId: '', qty: '' });
        setShowTransferModal(true);
    };

    const submitTransfer = async () => {
        if (!transferData.targetLocId || !transferData.qty || isNaN(transferData.qty) || transferData.qty <= 0) return;
        try {
            await api.post('/v2/stock/transaction', {
                variant_id: transferData.variant.id,
                quantity: parseFloat(transferData.qty),
                location_id: transferData.sourceLocId,
                location_dest_id: parseInt(transferData.targetLocId),
                notes: "Transfert Interne/Manuel"
            });
            setShowTransferModal(false);
            queryClient.invalidateQueries();
        } catch (e) {
            alert("Erreur lors du transfert.");
        }
    };

    // -------- ENTREE STOCK MANUELLE (VIRTUAL SUPPLIER -> DEPOT) --------
    const openReceptionModal = () => {
        setReceptionData({ variant: null, targetLocId: '', qty: '' });
        setReceptionSearch('');
        setShowReceptionModal(true);
    };

    const openReceptionForVariant = (variant, targetLocId = '') => {
        setReceptionData({ variant, targetLocId, qty: '' });
        setReceptionSearch(variant?.reference || '');
        setShowReceptionModal(true);
    };

    const openReceptionForLocation = (location) => {
        setReceptionData({ variant: null, targetLocId: location?.id ? String(location.id) : '', qty: '' });
        setReceptionSearch('');
        setShowReceptionModal(true);
    };

    const submitReception = async () => {
        if (!receptionData.variant || !receptionData.targetLocId || !receptionData.qty || isNaN(receptionData.qty) || receptionData.qty <= 0) return;

        const supplierLoc = locations.find(l => l.usage === 'supplier');

        try {
            await api.post('/v2/stock/transaction', {
                variant_id: receptionData.variant.id,
                quantity: parseFloat(receptionData.qty),
                location_id: supplierLoc?.id || null,       // Source: supplier virtual location, or external if missing
                location_dest_id: parseInt(receptionData.targetLocId), // Dest: Chosen Internal Shelf
                notes: "Réception Achat Direct"
            });
            setShowReceptionModal(false);
            queryClient.invalidateQueries();
        } catch (e) {
            alert("Erreur lors de la réception.");
        }
    };

    // -------- SORTIE STOCK MANUELLE (DEPOT -> CLIENT / EXTERNE) --------
    const openCustomerIssueModal = () => {
        setCustomerIssueData({ variant: null, sourceLocId: '', qty: '', reason: '' });
        setCustomerIssueSearch('');
        setShowCustomerIssueModal(true);
    };

    const openCustomerIssueForVariant = (variant, sourceLocId = '') => {
        setCustomerIssueData({ variant, sourceLocId: sourceLocId ? String(sourceLocId) : '', qty: '', reason: '' });
        setCustomerIssueSearch(variant?.reference || '');
        setShowCustomerIssueModal(true);
    };

    const submitCustomerIssue = async () => {
        const qty = parseFloat(customerIssueData.qty);
        const reason = customerIssueData.reason.trim();
        if (!customerIssueData.variant || !customerIssueData.sourceLocId || !qty || isNaN(qty) || qty <= 0 || !reason) return;

        const customerLoc = locations.find(l => l.usage === 'customer' && l.is_active !== false);
        try {
            await api.post('/v2/stock/transaction', {
                variant_id: customerIssueData.variant.id,
                quantity: qty,
                location_id: parseInt(customerIssueData.sourceLocId),
                location_dest_id: customerLoc?.id || null,
                notes: `Sortie stock manuelle client/externe - ${reason}`,
                reason,
                source_screen: 'stock.manual_customer_issue',
                document_type: 'manual_customer_issue',
            });
            setShowCustomerIssueModal(false);
            await queryClient.invalidateQueries({ queryKey: ['products'] });
            await queryClient.invalidateQueries({ queryKey: ['quants'] });
            await queryClient.invalidateQueries({ queryKey: ['transactions'] });
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur lors de la sortie stock.");
        }
    };

    const createPurchaseRequestFromRisk = async (need) => {
        if (!need?.variant_id || !stockPermissions.requestPurchases) return;
        const quantity = Number(need.suggested_quantity || need.net_need_quantity || 0);
        if (quantity <= 0) {
            alert("Aucune quantité positive à demander pour cette ligne.");
            return;
        }
        if (!need.supplier) {
            alert("Impossible de créer la demande : aucun fournisseur n'est renseigné sur l'article.");
            return;
        }

        setRiskActionVariantId(need.variant_id);
        try {
            await api.post('/v2/purchases/requests', {
                supplier: need.supplier,
                expected_date: null,
                global_discount_percent: 0,
                sensitivity_reason: `Stock à risque - ${need.reference}`,
                notes: [
                    `Créé depuis Inventaire > Stock à risque.`,
                    need.reason ? `Motif: ${need.reason}` : null,
                    need.blocked_reason ? `Point bloquant: ${need.blocked_reason}` : null,
                ].filter(Boolean).join('\n'),
                lines: [{
                    variant_id: need.variant_id,
                    quantity,
                    unit_price: 0,
                    discount_percent: 0,
                    need_priority: need.priority || null,
                    need_reason: need.reason || need.blocked_reason || 'Stock à risque',
                }],
            });
            await queryClient.invalidateQueries({ queryKey: ['purchase-needs'] });
            await queryClient.invalidateQueries({ queryKey: ['purchase-needs', 'stock-risk'] });
            await queryClient.invalidateQueries({ queryKey: ['purchase-requests'] });
            alert("Demande d'achat créée depuis le stock à risque.");
        } catch (e) {
            alert(e.response?.data?.detail || "Erreur lors de la création de la demande d'achat.");
        } finally {
            setRiskActionVariantId(null);
        }
    };

    // -------- PRODUCT AND VARIANT EDITING --------
    const openEditProduct = (e, product) => {
        e.stopPropagation();
        setEditProductForm({
            id: product.id,
            reference_base: product.reference_base,
            name: product.name,
            material_type: product.material_type || '',
            unit: product.unit || '',
            supplier: product.supplier || '',
            product_type: product.product_type || 'stockable',
            available_in_pos: product.available_in_pos || false,
            image_url: product.image_url || '',
            technical_doc_url: product.technical_doc_url || '',
            compatible_series: product.compatible_series || '',
            catalog_status: product.catalog_status || 'ACTIVE'
        });
        setShowEditProductModal(true);
    };

    const submitEditProduct = async () => {
        try {
            await api.put(`/v2/stock/products/${editProductForm.id}`, {
                reference_base: editProductForm.reference_base,
                name: editProductForm.name,
                material_type: editProductForm.material_type,
                unit: editProductForm.unit,
                supplier: editProductForm.supplier,
                product_type: editProductForm.product_type,
                available_in_pos: editProductForm.available_in_pos,
                image_url: editProductForm.image_url,
                technical_doc_url: editProductForm.technical_doc_url,
                compatible_series: editProductForm.compatible_series,
                catalog_status: editProductForm.catalog_status || 'ACTIVE'
            });
            setShowEditProductModal(false);
            queryClient.invalidateQueries();
        } catch (e) { alert("Erreur lors de la modification du produit"); }
    };

    const openEditVariant = (e, variant) => {
        e.stopPropagation();
        setEditVariantForm({
            id: variant.id,
            reference: variant.reference,
            barcode: variant.barcode || '',
            color: variant.color || '',
            length_per_unit: variant.length_per_unit ?? '',
            supplier_reference: variant.supplier_reference || '',
            cost_price: variant.cost_price ?? '',
            min_threshold: variant.min_threshold ?? 10,
            image_url: variant.image_url || '',
            location: variant.location || ''
        });
        setShowEditVariantModal(true);
    };

    const submitEditVariant = async () => {
        try {
            await api.put(`/v2/stock/variants/${editVariantForm.id}`, {
                reference: editVariantForm.reference,
                barcode: editVariantForm.barcode || null,
                color: editVariantForm.color,
                length_per_unit: editVariantForm.length_per_unit ? parseFloat(editVariantForm.length_per_unit) : null,
                supplier_reference: editVariantForm.supplier_reference || null,
                cost_price: editVariantForm.cost_price === '' ? 0 : parseFloat(editVariantForm.cost_price),
                min_threshold: editVariantForm.min_threshold === '' ? 0 : parseFloat(editVariantForm.min_threshold),
                image_url: editVariantForm.image_url || null,
                location: editVariantForm.location || null
            });
            setShowEditVariantModal(false);
            queryClient.invalidateQueries();
        } catch (e) { alert("Erreur lors de la modification de la variante"); }
    };

    // -------- IMPORT CSV --------
    const submitImportFile = async (e) => {
        e.preventDefault();
        if (!massImportFile) return;

        const formData = new FormData();
        formData.append("file", massImportFile);

        try {
            const res = await api.post('/v2/stock/import/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            alert(res.data.message);
            setMassImportFile(null);
            setShowImportModal(false);
            queryClient.invalidateQueries();
        } catch (error) {
            alert(error.response?.data?.detail || "Erreur lors de l'import : Vérifiez votre fichier");
        }
    };

    const submitDraftCatalogImport = async (e) => {
        e.preventDefault();
        if (!draftCatalogFile || draftCatalogImporting) return;

        const formData = new FormData();
        formData.append("file", draftCatalogFile);

        try {
            setDraftCatalogImporting(true);
            const res = await api.post('/v2/stock/catalog/drafts/import', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            alert(res.data.message);
            setDraftCatalogFile(null);
            queryClient.invalidateQueries({ queryKey: ['products'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Import des brouillons impossible.");
        } finally {
            setDraftCatalogImporting(false);
        }
    };

    const downloadDraftCatalogExport = async () => {
        try {
            const res = await api.get('/v2/stock/catalog/drafts/export', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', 'MMG_Brouillons_Catalogue.xlsx');
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.response?.data?.detail || "Export des brouillons impossible.");
        }
    };

    const downloadPimTemplate = async () => {
        try {
            const res = await api.get('/v2/stock/import/template', { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', 'MMG_Template_Import_Produits.xlsx');
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.response?.data?.detail || "Téléchargement du template PIM impossible.");
        }
    };

    // Emplacements internes actifs (l'endpoint /v2/stock/locations ne renvoie
    // que les actifs). Défaut : « WH/Stock » s'il existe, sinon le premier
    // interne actif — convention alignée sur le backfill de la migration
    // d'ancrage des réservations.
    const internalLocations = locations.filter(l => l.usage === 'internal');
    const defaultWorkshopSourceLocation = internalLocations.find(l => l.name === 'WH/Stock')?.name || internalLocations[0]?.name || 'WH/Stock';
    const effectiveWorkshopSourceLocation = workshopSourceLocation || defaultWorkshopSourceLocation;

    const buildWorkshopFormData = () => {
        const formData = new FormData();
        workshopFiles.forEach(file => formData.append("files", file));
        // Champ attendu par l'API : source_location (nom de l'emplacement,
        // Form). Le backend ancre la réservation sur location_id correspondant.
        formData.append("source_location", effectiveWorkshopSourceLocation);
        if (workshopContextValue.startsWith("sale:")) {
            formData.append("sale_order_id", workshopContextValue.split(":")[1]);
        }
        if (workshopContextValue.startsWith("production:")) {
            formData.append("production_order_id", workshopContextValue.split(":")[1]);
        }
        return formData;
    };

    const submitWorkshopPreview = async () => {
        if (!workshopFiles.length) return alert("Ajoutez au moins un fichier de débit atelier.");
        setWorkshopLoading(true);
        try {
            const res = await api.post('/v2/stock/workshop-debits/preview', buildWorkshopFormData(), {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setWorkshopPreview(res.data);
        } catch (error) {
            alert(error.response?.data?.detail || "Prévisualisation impossible.");
        } finally {
            setWorkshopLoading(false);
        }
    };

    const submitWorkshopReservation = async () => {
        if (!workshopPreview) return;
        if (!workshopContextValue) {
            return alert("Sélectionnez un devis validé ou un ordre atelier avant de réserver le stock.");
        }
        const status = workshopPreview.summary?.stock_match_status || {};
        if (workshopPreview.issues?.some(issue => issue.severity === 'error')) {
            return alert("Réservation bloquée : corrigez les alertes workflow.");
        }
        if ((status.not_found || 0) > 0 || (status.shortage || 0) > 0) {
            return alert("Réservation bloquée : références inconnues ou stock insuffisant.");
        }
        setWorkshopLoading(true);
        try {
            await api.post('/v2/stock/workshop-debits/reservations', buildWorkshopFormData(), {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setShowWorkshopDebitModal(false);
            setWorkshopFiles([]);
            setWorkshopContextValue('');
            setWorkshopPreview(null);
            queryClient.invalidateQueries({ queryKey: ['workshop-reservations'] });
            queryClient.invalidateQueries({ queryKey: ['products'] });
            queryClient.invalidateQueries({ queryKey: ['quants'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Réservation impossible.");
        } finally {
            setWorkshopLoading(false);
        }
    };

    const createWorkshopDraftProducts = async () => {
        if (!workshopPreview || (workshopPreview.summary.stock_match_status?.not_found || 0) === 0) return;
        if (!window.confirm("Créer les références inconnues en brouillons catalogue avec quantité zéro ?")) return;
        setWorkshopLoading(true);
        try {
            const res = await api.post('/v2/stock/workshop-debits/draft-products', buildWorkshopFormData(), {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            alert(res.data.message || "Brouillons catalogue créés.");
            const preview = await api.post('/v2/stock/workshop-debits/preview', buildWorkshopFormData(), {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setWorkshopPreview(preview.data);
            queryClient.invalidateQueries({ queryKey: ['products'] });
            queryClient.invalidateQueries({ queryKey: ['quants'] });
        } catch (error) {
            alert(error.response?.data?.detail || "Création des brouillons impossible.");
        } finally {
            setWorkshopLoading(false);
        }
    };

    const refreshWorkshopReservationState = async () => {
        await queryClient.invalidateQueries({ queryKey: ['workshop-reservations'] });
        await queryClient.invalidateQueries({ queryKey: ['products'] });
        await queryClient.invalidateQueries({ queryKey: ['quants'] });
        await queryClient.invalidateQueries({ queryKey: ['transactions'] });
    };

    const consumeWorkshopReservation = async (reservation) => {
        if (!window.confirm(`Confirmer le débit réel atelier pour ${reservation.reference} ? Le stock physique sera décrémenté.`)) return;
        setReservationActionId(reservation.id);
        try {
            const res = await api.post(`/v2/stock/workshop-debits/reservations/${reservation.id}/consume`);
            alert(`${res.data.consumed_lines || 0} ligne(s) débitée(s), ${res.data.created_moves || 0} mouvement(s) créé(s).`);
            await refreshWorkshopReservationState();
        } catch (error) {
            alert(error.response?.data?.detail || "Débit réel impossible.");
        } finally {
            setReservationActionId(null);
        }
    };

    const cancelWorkshopReservation = async (reservation) => {
        if (!window.confirm(`Annuler la réservation ${reservation.reference} ? Le stock physique ne sera pas modifié.`)) return;
        setReservationActionId(reservation.id);
        try {
            const res = await api.post(`/v2/stock/workshop-debits/reservations/${reservation.id}/cancel`);
            alert(`${res.data.cancelled_lines || 0} ligne(s) annulée(s), ${res.data.released_quantity || 0} unité(s) libérée(s).`);
            await refreshWorkshopReservationState();
        } catch (error) {
            alert(error.response?.data?.detail || "Annulation impossible.");
        } finally {
            setReservationActionId(null);
        }
    };

    const openAddVariant = (e, product) => {
        e.stopPropagation();
        setAddVariantForm({
            productId: product.id,
            productName: product.name,
            reference: `${product.reference_base}-`,
            barcode: '',
            color: '',
            cost_price: '',
            min_threshold: 10,
            image_url: '',
            location: ''
        });
        setShowAddVariantModal(true);
    };

    const submitAddVariant = async () => {
        try {
            await api.post(`/v2/stock/products/${addVariantForm.productId}/variants`, {
                reference: addVariantForm.reference,
                barcode: addVariantForm.barcode || null,
                color: addVariantForm.color,
                cost_price: parseFloat(addVariantForm.cost_price) || 0,
                min_threshold: parseFloat(addVariantForm.min_threshold) || 10,
                image_url: addVariantForm.image_url || null,
                location: addVariantForm.location || null
            });
            setShowAddVariantModal(false);
            queryClient.invalidateQueries();
        } catch (e) { alert("Erreur lors de l'ajout de la déclinaison"); }
    };

    // -------- NEW PRODUCT FAST --------
    const handleQuickCreateProduct = async () => {
        if (!newProductForm.name || !newProductForm.reference_base || !newProductForm.variant_ref) {
            return alert("Nom et Références requises");
        }
        try {
            await api.post('/v2/stock/products', {
                reference_base: newProductForm.reference_base, name: newProductForm.name, material_type: newProductForm.material_type, unit: newProductForm.unit, supplier: newProductForm.supplier, product_type: newProductForm.product_type, available_in_pos: newProductForm.available_in_pos, image_url: newProductForm.image_url, compatible_series: newProductForm.compatible_series,
                variants: [{
                    reference: newProductForm.variant_ref, barcode: newProductForm.barcode || null, color: newProductForm.color, length_per_unit: newProductForm.length_per_unit ? parseFloat(newProductForm.length_per_unit) : null,
                    supplier_reference: newProductForm.supplier_reference, cost_price: newProductForm.cost_price ? parseFloat(newProductForm.cost_price) : null,
                    min_threshold: parseFloat(newProductForm.min_threshold)
                }]
            });
            setShowNewProductModal(false);
            queryClient.invalidateQueries();
        } catch (e) {
            alert("Erreur lors de la création.");
        }
    };

    const handlePrintBarcode = async (variantId) => {
        try {
            const res = await api.post(`/v2/printer/print_barcode/${variantId}`);
            alert(res.data.message);
        } catch (e) {
            const msg = e.response?.data?.detail || "Erreur d'impression";
            alert(msg);
        }
    };

    const handleExportExcel = () => {
        downloadFileWithFeedback('/v2/stock/export/inventory', 'inventaire.xlsx');
    };

    // -------- RENDERERS --------
    const renderLocationTree = (parentLoc, depth = 0) => {
        const children = locations.filter(l => l.parent_id === parentLoc.id);
        const isInternal = parentLoc.usage === 'internal';
        const isActive = activeLocationId === parentLoc.id;

        return (
            <div key={parentLoc.id} className="w-full">
                <div
                    className={`group flex items-center justify-between py-2.5 px-3 cursor-pointer rounded-xl transition-all border mb-1 ${isActive ? 'bg-blue-50 border-blue-200 text-blue-700 shadow-sm' : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-900'}`}
                    style={{ paddingLeft: `${depth * 16 + 12}px` }}
                    onClick={() => {
                        setActiveLocationId(parentLoc.id);
                        setInventoryFocus('stock');
                        setShowDraftOnly(false);
                        setSearchTerm('');
                    }}
                >
                    <div className="flex items-center gap-3">
                        {isInternal ? <FolderOpen className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-slate-400 group-hover:text-slate-600'}`} /> : <Truck className="w-4 h-4 text-emerald-500" />}
                        <span className={`text-sm ${isActive ? 'font-black' : 'font-bold'}`}>{parentLoc.name}</span>
                        {!isInternal && <span className="text-[9px] uppercase font-black bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-md border border-emerald-500/20">{parentLoc.usage}</span>}
                    </div>
                    {canManageLocations && (
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button type="button" onClick={(e) => { e.stopPropagation(); setAddingSubLocTo(parentLoc.id); }} className="p-1.5 hover:bg-blue-50 rounded-lg text-slate-400 hover:text-blue-600 transition-colors">
                                <Plus className="w-3.5 h-3.5" />
                            </button>
                            <button type="button" onClick={(e) => handleDeleteLocation(parentLoc.id, e)} className="p-1.5 hover:bg-red-50 rounded-lg text-slate-400 hover:text-red-600 transition-colors">
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    )}
                </div>

                {/* Inline Add Input */}
                {addingSubLocTo === parentLoc.id && (
                    <div className="pl-4 py-1" style={{ paddingLeft: `${(depth+1) * 16 + 12}px` }}>
                        <div className="flex items-center gap-2">
                            <input
                                autoFocus
                                value={newSubLocName}
                                onChange={e=>setNewSubLocName(e.target.value)}
                                onBlur={() => setAddingSubLocTo(null)}
                                onKeyDown={e => {
                                    if (e.key === 'Escape') setAddingSubLocTo(null);
                                    if (e.key === 'Enter') handleAddSubLocation(e, parentLoc.id);
                                }}
                                className="flex-1 text-sm p-2 bg-white border border-slate-200 rounded-lg text-slate-900 placeholder-slate-400 outline-none focus:ring-2 focus:ring-blue-500/30 transition-all"
                                placeholder="Nom sous-lieu... Entrée"
                            />
                        </div>
                    </div>
                )}

                {children.length > 0 && (
                    <div className="flex flex-col">
                        {children.map(c => renderLocationTree(c, depth + 1))}
                    </div>
                )}
            </div>
        );
    };

    const renderManagedLocationTree = (parentLoc, depth = 0) => {
        const children = locations.filter(l => l.parent_id === parentLoc.id);
        const isEditing = editingLocationId === parentLoc.id;
        const usageLabel = {
            internal: 'Stock interne',
            production: 'Production',
            supplier: 'Fournisseur',
            customer: 'Client',
            inventory: 'Inventaire virtuel',
        }[parentLoc.usage] || parentLoc.usage;

        return (
            <div key={parentLoc.id} className="space-y-2">
                <div className="rounded-2xl border border-slate-200 bg-white p-3 flex items-center justify-between gap-3" style={{ marginLeft: `${depth * 18}px` }}>
                    <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${parentLoc.usage === 'internal' ? 'bg-blue-50 text-blue-600' : parentLoc.usage === 'production' ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-500'}`}>
                            {parentLoc.usage === 'internal' ? <FolderOpen className="w-4 h-4" /> : <MapPin className="w-4 h-4" />}
                        </div>
                        <div className="min-w-0">
                            {isEditing ? (
                                <input
                                    autoFocus
                                    value={editingLocationName}
                                    onChange={event => setEditingLocationName(event.target.value)}
                                    onKeyDown={event => {
                                        if (event.key === 'Enter') saveLocationName(parentLoc.id);
                                        if (event.key === 'Escape') setEditingLocationId(null);
                                    }}
                                    className="w-full rounded-lg border border-blue-200 px-3 py-2 text-sm font-black outline-none focus:ring-2 focus:ring-blue-500"
                                />
                            ) : (
                                <p className="font-black text-slate-900 truncate">{parentLoc.name}</p>
                            )}
                            <p className="text-[11px] font-bold text-slate-400">
                                {usageLabel} {parentLoc.parent_id ? `- sous ${locations.find(l => l.id === parentLoc.parent_id)?.name || 'zone'}` : '- zone principale'}
                            </p>
                        </div>
                    </div>
	                    <div className="flex items-center gap-2 shrink-0">
	                        <button
	                            type="button"
	                            onClick={(event) => openLocationDetail(event, parentLoc)}
	                            className="px-3 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-800 text-xs font-black inline-flex items-center gap-1"
	                        >
	                            <MapPin className="w-3.5 h-3.5" />
	                            Fiche
	                        </button>
	                        <button
	                            type="button"
	                            onClick={() => {
	                                setActiveLocationId(parentLoc.id);
                                setInventoryFocus('stock');
                                setShowDraftOnly(false);
                                setSearchTerm('');
                                setShowLocationManagerModal(false);
                            }}
                            className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 text-xs font-black"
                        >
                            Voir stock
                        </button>
                        <button
                            type="button"
                            onClick={() => openSubLocationForm(parentLoc)}
                            className="px-3 py-2 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-black inline-flex items-center gap-1"
                        >
                            <Plus className="w-3.5 h-3.5" />
                            Sous-zone
                        </button>
                        {isEditing ? (
                            <button type="button" onClick={() => saveLocationName(parentLoc.id)} className="px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-black">
                                Enregistrer
                            </button>
                        ) : (
                            <button type="button" onClick={() => startEditLocation(parentLoc)} className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 text-xs font-black">
                                Renommer
                            </button>
                        )}
                        <button type="button" onClick={(event) => handleDeleteLocation(parentLoc.id, event)} className="p-2 rounded-xl border border-red-100 bg-red-50 hover:bg-red-100 text-red-600" title="Archiver ou supprimer">
                            <Trash2 className="w-4 h-4" />
                        </button>
                    </div>
                </div>
                {children.map(child => renderManagedLocationTree(child, depth + 1))}
            </div>
        );
    };

    const toggleExpand = (id) => {
        setExpandedProducts(prev => ({ ...prev, [id]: !prev[id] }));
    };

    const getFullLocationName = (loc) => {
        if (!loc.parent_id) return loc.name;
        const parent = locations.find(l => l.id === loc.parent_id);
        return parent ? `${getFullLocationName(parent)} > ${loc.name}` : loc.name;
    };

    const getLocationDescendantIds = (locationId) => {
        const children = locations.filter(location => location.parent_id === locationId);
        return [locationId, ...children.flatMap(child => getLocationDescendantIds(child.id))];
    };

    const isDraftProduct = (product) => {
        const text = `${product.name || ''} ${product.compatible_series || ''}`.toLowerCase();
        return product.catalog_status === 'DRAFT' || text.includes('[brouillon]') || text.includes('créé depuis prévisualisation débit atelier');
    };

    const selectInventoryFocus = (focus) => {
        setCurrentMenu(focus);
        setInventoryFocus(focus);
        setSearchTerm('');
        setShowLowStockOnly(false);
        setShowDraftOnly(focus === 'drafts');
        if (focus === 'catalog' || focus === 'drafts' || focus === 'services') {
            setActiveLocationId('global');
        }
    };

    const selectTodo = () => {
        setCurrentMenu('todo');
        setSearchTerm('');
        setShowLowStockOnly(false);
        setShowDraftOnly(false);
        setActiveLocationId('global');
    };

    const goToPurchases = () => {
        window.history.pushState(null, '', '/manager?view=purchases');
        window.dispatchEvent(new PopStateEvent('popstate'));
    };

    const getVariantTransactions = (variantId) => {
        return transactions
            .filter(tx => tx.variant_id === variantId)
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 5);
    };

    const getInternalStockForVariant = (variantId) => {
        return quants
            .filter(quant => quant.variant_id === variantId && locations.find(location => location.id === quant.location_id)?.usage === 'internal')
            .reduce((sum, quant) => sum + Number(quant.quantity || 0), 0);
    };

    const getProductSummary = (product) => {
        const variants = product?.variants || [];
        return variants.reduce((summary, variant) => {
            const physicalStock = getInternalStockForVariant(variant.id);
            const reservedQuantity = Number(variant.reserved_quantity || 0);
            const availableQuantity = Number(variant.available_quantity ?? Math.max(physicalStock - reservedQuantity, 0));
            const threshold = Number(variant.min_threshold || 0);
            return {
                physicalStock: summary.physicalStock + physicalStock,
                reserved: summary.reserved + reservedQuantity,
                available: summary.available + availableQuantity,
                valuation: summary.valuation + (physicalStock * Number(variant.cost_price || 0)),
                lowStockVariants: summary.lowStockVariants + (physicalStock <= threshold ? 1 : 0),
            };
        }, { physicalStock: 0, reserved: 0, available: 0, valuation: 0, lowStockVariants: 0 });
    };

    const getProductLocationRows = (product) => {
        const variantById = new Map((product?.variants || []).map(variant => [variant.id, variant]));
        return quants
            .filter(quant => variantById.has(quant.variant_id))
            .map(quant => {
                const location = locations.find(item => item.id === quant.location_id);
                return {
                    ...quant,
                    variant: variantById.get(quant.variant_id),
                    location,
                    locationName: location ? getFullLocationName(location) : 'Emplacement inconnu',
                };
            })
            .filter(row => row.location?.usage === 'internal' && Number(row.quantity || 0) !== 0)
            .sort((a, b) => a.locationName.localeCompare(b.locationName));
    };

    const getProductMovements = (product) => {
        const variantIds = new Set((product?.variants || []).map(variant => variant.id));
        return transactions
            .filter(tx => variantIds.has(tx.variant_id))
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 10);
    };

    const getProductReservations = (product) => {
        const variantIds = new Set((product?.variants || []).map(variant => variant.id));
        const variantRefs = new Set((product?.variants || []).map(variant => variant.reference));
        return reservations.filter(reservation => {
            const lines = reservation.lines || reservation.items || [];
            return lines.some(line => variantIds.has(line.variant_id) || variantRefs.has(line.variant_reference || line.reference));
        });
    };

    const getVariantContext = (variantId) => {
        for (const product of products) {
            const variant = (product.variants || []).find(item => item.id === variantId);
            if (variant) return { product, variant };
        }
        return { product: null, variant: null };
    };

    const getLocationStockRows = (location) => {
        if (!location) return [];
        const locationIds = getLocationDescendantIds(location.id);
        return quants
            .filter(quant => locationIds.includes(quant.location_id) && Number(quant.quantity || 0) !== 0)
            .map(quant => {
                const { product, variant } = getVariantContext(quant.variant_id);
                const quantLocation = locations.find(item => item.id === quant.location_id);
                // Réservé / disponible PAR EMPLACEMENT (renvoyés par /quants sur
                // les emplacements internes) — jamais les totaux globaux de la
                // variante, qui seraient double-comptés en les sommant ici.
                const reservedQuantity = quant.reserved_quantity != null
                    ? Number(quant.reserved_quantity)
                    : Number(variant?.reserved_quantity || 0);
                const availableQuantity = quant.available_quantity != null
                    ? Number(quant.available_quantity)
                    : Math.max(Number(quant.quantity || 0) - reservedQuantity, 0);
                return {
                    ...quant,
                    product,
                    variant,
                    location: quantLocation,
                    locationName: quantLocation ? getFullLocationName(quantLocation) : 'Emplacement inconnu',
                    reservedQuantity,
                    availableQuantity,
                    valuation: Number(quant.quantity || 0) * Number(variant?.cost_price || 0),
                };
            })
            .sort((a, b) => `${a.locationName} ${a.product?.name || ''}`.localeCompare(`${b.locationName} ${b.product?.name || ''}`));
    };

    const getLocationMovements = (location) => {
        if (!location) return [];
        const locationIds = getLocationDescendantIds(location.id);
        return transactions
            .filter(tx => locationIds.includes(tx.location_id) || locationIds.includes(tx.location_dest_id))
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
            .slice(0, 10);
    };

    const getLocationInventorySessions = (location) => {
        if (!location) return [];
        const locationIds = getLocationDescendantIds(location.id);
        return inventorySessions
            .filter(session => locationIds.includes(session.location_id) || (session.lines || []).some(line => locationIds.includes(line.location_id)))
            .slice(0, 6);
    };

    const openProductDetail = (event, product) => {
        event?.stopPropagation?.();
        setProductDetailReturnMenu(currentMenu);
        setSelectedProductId(product.id);
        setCurrentMenu('product-detail');
        setShowLowStockOnly(false);
    };

    const closeProductDetail = () => {
        const target = productDetailReturnMenu && productDetailReturnMenu !== 'product-detail'
            ? productDetailReturnMenu
            : (inventoryFocus || 'catalog');
        setProductDetailReturnMenu(null);
        setCurrentMenu(target);
    };

    const openLocationDetail = (event, location) => {
        event?.stopPropagation?.();
        setSelectedLocationId(location.id);
        setCurrentMenu('location-detail');
    };

    const closeLocationDetail = () => {
        setCurrentMenu('locations');
    };

    const inventoryTitle = showDraftOnly
        ? "Brouillons catalogue"
        : inventoryFocus === 'stock'
            ? (activeLocationId === 'global' ? "Stock réel global" : `Stock réel : ${locations.find(l => l.id === activeLocationId)?.name}`)
            : inventoryFocus === 'services'
                ? "Catalogue prestations"
            : "Catalogue articles";

    const inventorySubtitle = showDraftOnly
        ? "Références à qualifier avant entrée de stock réelle."
        : inventoryFocus === 'stock'
            ? (activeLocationId === 'global'
                ? "Vue globale en lecture : choisissez un emplacement pour ajuster le stock physique."
                : "Ajustement rapide : cliquez sur une quantité pour la modifier.")
            : inventoryFocus === 'services'
                ? "Prestations pré-enregistrées pour les devis libres, sans réservation ni débit de stock."
            : "Référentiel produits, variantes, fournisseurs et fiches techniques.";

    const formatQty = (value) => Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });

    // Calculate Grid Data grouped by Product
    let groupedData = [];
    let totalValuation = 0;
    let totalLowStockCount = 0;
    const totalDraftCount = products.filter(isDraftProduct).length;

    products.forEach(p => {
        const draftProduct = isDraftProduct(p);
        const productType = (p.product_type || 'stockable').toLowerCase();
        const isServiceProduct = productType === 'service';
        if (showDraftOnly && !draftProduct) return;
        if (!showDraftOnly && inventoryFocus === 'services' && !isServiceProduct) return;
        if (!showDraftOnly && inventoryFocus !== 'services' && isServiceProduct) return;
        let hasVisibleVariant = false;
        const variantsData = [];

        p.variants.forEach(v => {
            let stockToDisplay = 0;
            let locId = null;
            if (activeLocationId === 'global') {
                const totalInternalStock = quants.filter(q => q.variant_id === v.id && locations.find(l => l.id === q.location_id)?.usage === 'internal').reduce((acc, curr) => acc + curr.quantity, 0);
                stockToDisplay = totalInternalStock;
            } else {
                // Find all descendant location IDs including the active one
                const getDescendants = (id) => {
                    const children = locations.filter(l => l.parent_id === id).map(l => l.id);
                    return [id, ...children.flatMap(getDescendants)];
                };
                const validLocIds = getDescendants(activeLocationId);

                const totalInSubTree = quants.filter(q => q.variant_id === v.id && validLocIds.includes(q.location_id)).reduce((acc, curr) => acc + curr.quantity, 0);
                stockToDisplay = totalInSubTree;
                locId = activeLocationId;
            }

            const matchSearch = searchTerm === '' ||
                p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                p.reference_base.toLowerCase().includes(searchTerm.toLowerCase()) ||
                v.reference.toLowerCase().includes(searchTerm.toLowerCase());

            const isVisibleBase = searchTerm ? matchSearch : (activeLocationId === 'global' ? true : stockToDisplay > 0);

            const isLowStock = !isServiceProduct && stockToDisplay <= (v.min_threshold || 0);
            if (activeLocationId === 'global' && !isServiceProduct) {
                totalValuation += stockToDisplay * (v.cost_price || 0);
                if (isLowStock) totalLowStockCount++;
            }

            const isVisible = isVisibleBase && (!showLowStockOnly || isLowStock);

            if (isVisible) {
                hasVisibleVariant = true;
                const reservedQuantity = Number(v.reserved_quantity || 0);
                const availableQuantity = Number(
                    v.available_quantity ?? Math.max(stockToDisplay - reservedQuantity, 0)
                );
                variantsData.push({
                    fullVariant: v,
                    variantLabel: v.color || "Standard",
                    variantRef: v.reference,
                    variantId: v.id,
                    stockToDisplay,
                    reservedQuantity,
                    availableQuantity,
                    locId,
                    isLowStock
                });
            }
        });

        if (hasVisibleVariant) {
            groupedData.push({
                product: p,
                variants: variantsData
            });
        }
    });

    const draftProducts = products.filter(isDraftProduct);
    const stockVariants = products
        .filter(product => (product.product_type || 'stockable').toLowerCase() !== 'service')
        .flatMap(product => (product.variants || []).map(variant => {
            const internalStock = quants
                .filter(quant => quant.variant_id === variant.id && locations.find(location => location.id === quant.location_id)?.usage === 'internal')
                .reduce((sum, quant) => sum + Number(quant.quantity || 0), 0);
            const reservedQuantity = Number(variant.reserved_quantity || 0);
            return {
                product,
                variant,
                internalStock,
                reservedQuantity,
                availableQuantity: Number(variant.available_quantity ?? Math.max(internalStock - reservedQuantity, 0)),
                minThreshold: Number(variant.min_threshold || 0),
            };
        }));
    const lowStockVariants = stockVariants
        .filter(item => item.availableQuantity <= item.minThreshold)
        .sort((a, b) => (a.availableQuantity - a.minThreshold) - (b.availableQuantity - b.minThreshold));
    const openInventorySessions = inventorySessions.filter(session => {
        const status = String(session.status || '').toUpperCase();
        return !['CLOSED', 'DONE', 'VALIDATED', 'CANCELLED'].includes(status);
    });
    const inventoryIssueCount = openInventorySessions.reduce((sum, session) => {
        const lines = session.lines || [];
        // Compteur basé uniquement sur le statut réel de la ligne : en comptage
        // aveugle expected_quantity est null, comparer les quantités créerait
        // de faux écarts sur chaque ligne comptée.
        return sum + lines.filter(line => ['variance', 'recount'].includes(String(line.status || '').toLowerCase())).length;
    }, 0);
    const openPurchases = purchases
        .filter(po => ['DRAFT', 'SENT', 'PARTIAL'].includes(String(po.status || '').toUpperCase()))
        .sort((a, b) => new Date(a.expected_date || '2999-12-31') - new Date(b.expected_date || '2999-12-31'));
    const purchaseNeeds = purchaseNeedsPayload.needs || [];
    const purchaseRiskSummary = purchaseNeedsPayload.summary || {};
    const criticalPurchaseNeeds = purchaseNeeds.filter(need => ['CRITICAL', 'URGENT'].includes(String(need.priority || '').toUpperCase()));
    const blockedPurchaseNeeds = purchaseNeeds.filter(need => !need.is_orderable && Number(need.net_need_quantity || 0) > 0);
    const coveredPurchaseNeeds = purchaseNeeds.filter(need => String(need.priority || '').toUpperCase() === 'COVERED');
    const longLeadTimeNeeds = purchaseNeeds.filter(need => Number(need.supplier_lead_time_days || 0) >= 14);
    const riskTotal = criticalPurchaseNeeds.length + blockedPurchaseNeeds.length;
    const recentManualAdjustments = transactions.filter(tx => {
        const documentType = String(tx.document_type || '').toLowerCase();
        const sourceScreen = String(tx.source_screen || '').toLowerCase();
        return documentType.includes('manual_inventory_adjustment') || sourceScreen.includes('manual') || sourceScreen.includes('inventory');
    }).slice(0, 4);
    const todoTotal = lowStockVariants.length + draftProducts.length + reservations.length + openInventorySessions.length + openPurchases.length;
    const todoCounts = {
        lowStock: lowStockVariants.length,
        drafts: draftProducts.length,
        reservations: reservations.length,
        inventory: openInventorySessions.length,
        inventoryIssues: inventoryIssueCount,
        purchases: openPurchases.length,
    };
    const todoActions = {
        showLowStock: () => {
            setCurrentMenu('stock');
            setInventoryFocus('stock');
            setShowDraftOnly(false);
            setShowLowStockOnly(true);
        },
        openRisk: () => setCurrentMenu('risk'),
        showDrafts: () => selectInventoryFocus('drafts'),
        openWorkshopDebit: () => setShowWorkshopDebitModal(true),
        openPhysicalInventory: () => setCurrentMenu('physical-inventory'),
        openMovements: () => setCurrentMenu('audit'),
        openReception: openReceptionModal,
        openPurchases: goToPurchases,
        consumeReservation: consumeWorkshopReservation,
        cancelReservation: cancelWorkshopReservation,
    };
    const locationUsageLabels = {
        internal: 'Stock physique',
        production: 'Production atelier',
        supplier: 'Fournisseur virtuel',
        customer: 'Client virtuel',
        inventory: 'Inventaire virtuel',
    };
    const rootLocations = locations.filter(location => !location.parent_id);
    const physicalLocations = locations.filter(location => location.usage === 'internal');
    const internalRootLocations = rootLocations.filter(location => location.usage === 'internal');
    const virtualLocations = locations.filter(location => location.usage !== 'internal');
    const productionLocations = locations.filter(location => location.usage === 'production');
    const inventoryPageMenus = ['catalog', 'stock', 'services', 'drafts'];
    const isInventoryPage = inventoryPageMenus.includes(currentMenu);
    const selectedProduct = products.find(product => product.id === selectedProductId);
    const selectedProductSummary = selectedProduct ? getProductSummary(selectedProduct) : null;
    const selectedProductLocationRows = selectedProduct ? getProductLocationRows(selectedProduct) : [];
    const selectedProductMovements = selectedProduct ? getProductMovements(selectedProduct) : [];
    const selectedProductReservations = selectedProduct ? getProductReservations(selectedProduct) : [];
    const selectedLocation = locations.find(location => location.id === selectedLocationId);
    const selectedLocationStockRows = selectedLocation ? getLocationStockRows(selectedLocation) : [];
    const selectedLocationMovements = selectedLocation ? getLocationMovements(selectedLocation) : [];
    const selectedLocationInventorySessions = selectedLocation ? getLocationInventorySessions(selectedLocation) : [];
    const selectedLocationChildren = selectedLocation ? locations.filter(location => location.parent_id === selectedLocation.id) : [];
    const selectedLocationSummary = selectedLocationStockRows.reduce((summary, row) => ({
        physicalStock: summary.physicalStock + Number(row.quantity || 0),
        reserved: summary.reserved + Number(row.reservedQuantity || 0),
        available: summary.available + Number(row.availableQuantity || 0),
        valuation: summary.valuation + Number(row.valuation || 0),
    }), { physicalStock: 0, reserved: 0, available: 0, valuation: 0 });
    const stockNavGroups = [
        {
            label: 'Priorités',
            items: [
                { key: 'todo', label: 'À traiter', Icon: AlertTriangle, count: todoTotal, tone: 'slate', onClick: selectTodo },
                { key: 'risk', label: 'Stock à risque', Icon: AlertTriangle, count: riskTotal, tone: 'red', onClick: () => setCurrentMenu('risk') },
            ],
        },
        {
            label: 'Référentiel',
            items: [
                { key: 'catalog', label: 'Catalogue', Icon: Package, tone: 'blue', onClick: () => selectInventoryFocus('catalog') },
                { key: 'stock', label: 'Stock réel', Icon: MapPin, tone: 'emerald', onClick: () => selectInventoryFocus('stock') },
                { key: 'services', label: 'Prestations', Icon: FileEdit, tone: 'emerald', onClick: () => selectInventoryFocus('services') },
                { key: 'drafts', label: 'Brouillons', Icon: FileEdit, count: totalDraftCount, tone: 'amber', onClick: () => selectInventoryFocus('drafts') },
                { key: 'locations', label: 'Zones & emplacements', Icon: MapPin, tone: 'blue', onClick: () => setCurrentMenu('locations') },
            ],
        },
        {
            label: 'Flux & contrôle',
            items: [
                ...(stockPermissions.reserveWorkshop || stockPermissions.consumeWorkshop ? [
                    { key: 'workshop', label: 'Débit atelier', Icon: ArrowRight, count: reservations.length, tone: 'amber', onClick: () => setCurrentMenu('workshop') },
                ] : []),
                { key: 'audit', label: 'Mouvements', Icon: Layers, tone: 'blue', onClick: () => setCurrentMenu('audit') },
                { key: 'physical-inventory', label: 'Inventaire physique', Icon: ClipboardCheck, tone: 'blue', onClick: () => setCurrentMenu('physical-inventory') },
                { key: 'import-export', label: 'Import / Export', Icon: Download, tone: 'blue', onClick: () => setCurrentMenu('import-export') },
                ...(isAdmin ? [
                    { key: 'valuation', label: 'Valorisation', Icon: TrendingUp, tone: 'blue', onClick: () => setCurrentMenu('valuation') },
                ] : []),
            ],
        },
    ];
    const navToneClasses = {
        slate: 'bg-slate-950 text-white shadow-sm',
        red: 'bg-red-600 text-white shadow-sm',
        blue: 'bg-blue-600 text-white shadow-sm',
        emerald: 'bg-emerald-600 text-white shadow-sm',
        amber: 'bg-amber-500 text-white shadow-sm',
    };
    const navCountClasses = {
        slate: 'bg-slate-100 text-slate-700',
        red: 'bg-red-100 text-red-700',
        blue: 'bg-blue-100 text-blue-700',
        emerald: 'bg-emerald-100 text-emerald-700',
        amber: 'bg-amber-100 text-amber-700',
    };

    return (
        <div className="w-full h-[calc(100vh-80px)] font-sans flex flex-col overflow-hidden bg-white border-y border-slate-200/80 animate-fade-in relative">
            <div className="shrink-0 border-b border-slate-200 bg-white">
                <div className="px-6 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-4">
                        <div className="min-w-0">
                            <h3 className="font-black flex items-center gap-3 tracking-tight text-xl text-slate-950">
                                <Box className="text-blue-600 w-5 h-5" /> Inventaire & Stock
                            </h3>
                            <p className="text-sm font-bold text-slate-500 mt-0.5">
                                Piloter les priorités, le catalogue, le stock physique et la traçabilité.
                            </p>
                        </div>

                        <div className="flex flex-1 flex-wrap items-center justify-end gap-2 min-w-[280px]">
                            <div className="relative w-full max-w-lg">
                                <Search className="w-4 h-4 text-slate-400 absolute left-4 top-3.5" />
                                <input
                                    type="text"
                                    placeholder="Rechercher produit, référence, fournisseur..."
                                    value={searchTerm}
                                    onChange={(e) => {
                                        setSearchTerm(e.target.value);
                                        if (!inventoryPageMenus.includes(currentMenu)) {
                                            setCurrentMenu('catalog');
                                            setInventoryFocus('catalog');
                                            setShowDraftOnly(false);
                                        }
                                    }}
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-11 pr-4 text-sm font-bold text-slate-900 outline-none focus:ring-2 focus:ring-blue-500/30 placeholder-slate-400"
                                />
                            </div>
                            {isInventoryPage && (
                                <div className="flex items-center bg-slate-50 rounded-xl p-1 border border-slate-200">
                                    <button
                                        onClick={() => setViewMode('list')}
                                        className={`px-3 py-2 rounded-lg flex items-center justify-center transition-all ${viewMode === 'list' ? 'bg-white shadow border border-slate-200 text-slate-800' : 'text-slate-400 hover:text-slate-600'}`}
                                        title="Vue liste"
                                    >
                                        <List className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => setViewMode('kanban')}
                                        className={`px-3 py-2 rounded-lg flex items-center justify-center transition-all ${viewMode === 'kanban' ? 'bg-white shadow border border-slate-200 text-slate-800' : 'text-slate-400 hover:text-slate-600'}`}
                                        title="Vue cartes"
                                    >
                                        <LayoutGrid className="w-4 h-4" />
                                    </button>
                                </div>
                            )}
                            <button
                                onClick={() => queryClient.invalidateQueries()}
                                className="px-3 py-2.5 text-slate-500 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition-all flex items-center justify-center gap-2 font-black text-sm border border-slate-200 bg-white"
                            >
                                <RefreshCw className="w-4 h-4" />
                                <span className="hidden sm:inline">Actualiser</span>
                            </button>
                        </div>
                    </div>
                </div>

                <div className="px-6 pb-4">
                    <div className="grid grid-cols-1 xl:grid-cols-[260px_1fr_1fr] gap-3">
                        {stockNavGroups.map(group => (
                            <div key={group.label} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-2">
                                <p className="px-2 pb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
                                    {group.label}
                                </p>
                                <div className="flex flex-wrap gap-1.5">
                                    {group.items.map(item => {
                                        const Icon = item.Icon;
                                        const active = currentMenu === item.key;
                                        const count = Number(item.count || 0);
                                        return (
                                            <button
                                                key={item.key}
                                                type="button"
                                                onClick={item.onClick}
                                                className={`inline-flex min-h-[38px] items-center gap-2 rounded-xl px-3 py-2 text-xs font-black transition-all ${active ? navToneClasses[item.tone] : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100 hover:text-slate-950'}`}
                                            >
                                                <Icon className="w-4 h-4 shrink-0" />
                                                <span className="whitespace-nowrap">{item.label}</span>
                                                {count > 0 && (
                                                    <span className={`rounded-lg px-2 py-0.5 text-[10px] font-black ${active ? 'bg-white/15 text-white' : navCountClasses[item.tone]}`}>
                                                        {count}
                                                    </span>
                                                )}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* MAIN CONTENT : GRID / AUDIT */}
            <div className="flex-1 flex flex-col bg-white relative min-h-0">

                {currentMenu === 'stock' && (
                    <div className="px-6 py-3 bg-white border-b border-slate-200 shrink-0">
                        <div className="flex flex-wrap items-center justify-between gap-3 mb-2">
                            <div>
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Filtrer par emplacement</p>
                            </div>
                            <div className="flex items-center gap-2">
                                {canManageLocations && (
                                    <>
                                        <button
                                            type="button"
                                            onClick={() => setAddingSubLocTo('root')}
                                            className="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 text-xs font-black inline-flex items-center gap-1"
                                            title="Créer rapidement une zone"
                                        >
                                            <Plus className="w-3.5 h-3.5" />
                                            Zone
                                        </button>
                                        <button
                                            onClick={() => setShowLocationManagerModal(true)}
                                            className="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-black inline-flex items-center gap-2"
                                        >
                                            <MapPin className="w-4 h-4" />
                                            Gérer les zones
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-2 max-h-32 overflow-y-auto pr-1">
                            <div
                                onClick={() => {
                                    setActiveLocationId('global');
                                    setInventoryFocus('catalog');
                                }}
                                className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all border ${activeLocationId === 'global' ? 'bg-blue-50 border-blue-200 text-blue-700 shadow-sm' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-slate-900'}`}
                            >
                                <MapPin className={`w-5 h-5 ${activeLocationId === 'global' ? 'text-blue-600' : 'text-slate-400'}`} />
                                <span className="font-black text-sm tracking-wide">Vue globale</span>
                            </div>

                            {addingSubLocTo === 'root' && (
                                <div className="p-2 rounded-xl border border-blue-200 bg-blue-50">
                                    <input
                                        autoFocus
                                        value={newSubLocName}
                                        onChange={e=>setNewSubLocName(e.target.value)}
                                        onBlur={() => setAddingSubLocTo(null)}
                                        onKeyDown={e => {
                                            if (e.key === 'Escape') setAddingSubLocTo(null);
                                            if (e.key === 'Enter') handleAddSubLocation(e, 'root');
                                        }}
                                        className="w-full text-sm p-2 bg-white border border-blue-200 rounded-xl text-slate-900 placeholder-slate-400 outline-none focus:ring-2 focus:ring-blue-500/30 transition-all"
                                        placeholder="Nom Entrepôt + Entrée"
                                    />
                                </div>
                            )}

                            {locations.filter(l => !l.parent_id).map(rootLoc => renderLocationTree(rootLoc))}
                        </div>
                    </div>
                )}

                {currentMenu === 'location-detail' && selectedLocation ? (
                    <div className="flex-1 overflow-y-auto w-full bg-slate-50">
                        <div className="w-full p-6 space-y-6">
                            <div className="border border-slate-200 bg-white overflow-hidden shadow-sm">
                                <div className="px-6 py-5 bg-slate-950 text-white flex flex-wrap items-start justify-between gap-4">
                                    <div className="min-w-0">
                                        <button
                                            type="button"
                                            onClick={closeLocationDetail}
                                            className="mb-4 inline-flex items-center gap-2 rounded-xl bg-white/10 hover:bg-white/15 px-3 py-2 text-xs font-black text-slate-200 transition-colors"
                                        >
                                            <ArrowLeft className="w-4 h-4" />
                                            Retour zones
                                        </button>
                                        <div className="flex flex-wrap items-center gap-2 mb-3">
                                            <span className="rounded-lg bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-blue-100">
                                                {locationUsageLabels[selectedLocation.usage] || selectedLocation.usage}
                                            </span>
                                            {selectedLocationChildren.length > 0 && (
                                                <span className="rounded-lg bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-slate-200">
                                                    {selectedLocationChildren.length} sous-zone(s)
                                                </span>
                                            )}
                                        </div>
                                        <h2 className="text-3xl font-black leading-tight truncate">{selectedLocation.name}</h2>
                                        <p className="mt-2 text-sm font-bold text-slate-300">{getFullLocationName(selectedLocation)}</p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setActiveLocationId(selectedLocation.id);
                                                setInventoryFocus('stock');
                                                setShowDraftOnly(false);
                                                setSearchTerm('');
                                                setCurrentMenu('stock');
                                            }}
                                            className="px-4 py-3 rounded-xl bg-white/10 hover:bg-white/15 border border-white/15 text-white text-sm font-black inline-flex items-center gap-2"
                                        >
                                            <Box className="w-4 h-4" />
                                            Voir stock réel
                                        </button>
                                        {stockPermissions.receive && selectedLocation.usage === 'internal' && (
                                            <button
                                                type="button"
                                                onClick={() => openReceptionForLocation(selectedLocation)}
                                                className="px-4 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                            >
                                                <Truck className="w-4 h-4" />
                                                Entrée stock ici
                                            </button>
                                        )}
                                        {canManageLocations && (
                                            <>
                                                <button
                                                    type="button"
                                                    onClick={() => openSubLocationForm(selectedLocation)}
                                                    className="px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                                >
                                                    <Plus className="w-4 h-4" />
                                                    Sous-zone
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => startEditLocation(selectedLocation)}
                                                    className="px-4 py-3 rounded-xl bg-white text-slate-950 text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                                >
                                                    <Edit3 className="w-4 h-4" />
                                                    Renommer
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>

                                <div className="p-6 space-y-6">
                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Stock physique</p>
                                            <p className="mt-2 text-3xl font-black text-slate-950">{formatQty(selectedLocationSummary.physicalStock)}</p>
                                        </div>
                                        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-amber-700">Réservé</p>
                                            <p className="mt-2 text-3xl font-black text-amber-700">{formatQty(selectedLocationSummary.reserved)}</p>
                                        </div>
                                        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-emerald-700">Disponible</p>
                                            <p className="mt-2 text-3xl font-black text-emerald-700">{formatQty(selectedLocationSummary.available)}</p>
                                        </div>
                                        {isAdmin && (
                                            <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4 shadow-sm text-white">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-300">Valorisation</p>
                                                <p className="mt-2 text-3xl font-black">{selectedLocationSummary.valuation.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}</p>
                                            </div>
                                        )}
                                    </div>

                                    <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
                                        <div className="space-y-6 min-w-0">
                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                                                    <div>
                                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Contenu stock</p>
                                                        <h3 className="text-lg font-black text-slate-950">Articles présents dans cette zone</h3>
                                                    </div>
                                                    <span className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-black text-slate-600">
                                                        {selectedLocationStockRows.length} référence(s)
                                                    </span>
                                                </div>
                                                {selectedLocationStockRows.length > 0 ? (
                                                    <div className="divide-y divide-slate-100">
                                                        {selectedLocationStockRows.map(row => (
                                                            <div key={`${row.variant_id}-${row.location_id}`} className="grid grid-cols-1 md:grid-cols-[1fr_150px_130px_120px] gap-3 px-5 py-4 items-center">
                                                                <div className="min-w-0">
                                                                    <button
                                                                        type="button"
                                                                        onClick={(event) => row.product && openProductDetail(event, row.product)}
                                                                        className="text-left font-black text-slate-900 hover:text-blue-700 transition-colors"
                                                                    >
                                                                        {row.product?.name || 'Produit inconnu'}
                                                                    </button>
                                                                    <p className="text-xs font-mono font-bold text-slate-400">{row.variant?.reference || `Variante #${row.variant_id}`}</p>
                                                                    <p className="text-[11px] font-bold text-slate-400">{row.locationName}</p>
                                                                </div>
                                                                <div>
                                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Physique</p>
                                                                    <p className="text-lg font-black text-slate-950">{formatQty(row.quantity)}</p>
                                                                </div>
                                                                <div>
                                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Disponible</p>
                                                                    <p className="text-lg font-black text-emerald-600">{formatQty(row.availableQuantity)}</p>
                                                                </div>
                                                                <div className="flex items-center justify-end gap-2">
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => row.variant && handlePrintBarcode(row.variant.id)}
                                                                        className="p-2 rounded-xl border border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                                                                        title="Imprimer l'étiquette"
                                                                        disabled={!row.variant}
                                                                    >
                                                                        <Hash className="w-4 h-4" />
                                                                    </button>
                                                                    {stockPermissions.transfer && row.variant && selectedLocation.usage === 'internal' && (
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => openTransferModal(row.variant, row.location_id)}
                                                                            className="px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-black inline-flex items-center gap-1.5"
                                                                        >
                                                                            Transférer <ArrowRight className="w-3.5 h-3.5" />
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="px-5 py-10 text-center">
                                                        <MapPin className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                                                        <p className="font-black text-slate-600">Aucun article stocké ici.</p>
                                                        <p className="text-sm font-bold text-slate-400 mt-1">Réceptionnez du stock ou transférez une référence vers cet emplacement.</p>
                                                    </div>
                                                )}
                                            </div>

                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                                    <div>
                                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Mouvements récents</p>
                                                        <h3 className="text-lg font-black text-slate-950">Entrées, sorties et transferts</h3>
                                                    </div>
                                                    <button type="button" onClick={() => setCurrentMenu('audit')} className="text-xs font-black text-blue-600 hover:text-blue-700">
                                                        Audit global
                                                    </button>
                                                </div>
                                                {selectedLocationMovements.length > 0 ? (
                                                    <div className="divide-y divide-slate-100">
                                                        {selectedLocationMovements.map(tx => {
                                                            const isIncoming = tx.location_dest_id && getLocationDescendantIds(selectedLocation.id).includes(tx.location_dest_id);
                                                            // Les emplacements virtuels (fournisseur/client) n'ont
                                                            // pas de nom côté backend : libellé lisible selon le sens.
                                                            const fromLabel = tx.location_from_name || (isIncoming ? 'Fournisseurs' : selectedLocation.name);
                                                            const toLabel = tx.location_to_name || (isIncoming ? selectedLocation.name : 'Clients');
                                                            return (
                                                                <div key={tx.id} className="grid grid-cols-1 md:grid-cols-[140px_1fr_90px] gap-3 px-5 py-4 items-center">
                                                                    <div>
                                                                        <p className="text-xs font-black text-slate-700">{new Date(tx.created_at).toLocaleDateString('fr-FR')}</p>
                                                                        <p className="text-[10px] font-mono text-slate-400">{new Date(tx.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</p>
                                                                    </div>
                                                                    <div className="min-w-0">
                                                                        <div className="flex flex-wrap items-center gap-2">
                                                                            <span className={`rounded-lg px-2 py-1 text-[10px] font-black uppercase ${isIncoming ? 'bg-emerald-50 text-emerald-700' : 'bg-orange-50 text-orange-700'}`}>
                                                                                {isIncoming ? 'Entrée zone' : 'Sortie zone'}
                                                                            </span>
                                                                            <span className="rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-black uppercase text-slate-600">{tx.transaction_type || tx.movement_kind || 'Mouvement'}</span>
                                                                            <span className="truncate text-[11px] font-mono font-bold text-slate-400">{tx.reference}</span>
                                                                        </div>
                                                                        <p className="mt-1 text-xs font-bold text-slate-500 truncate">{tx.notes || `${fromLabel} -> ${toLabel}`}</p>
                                                                    </div>
                                                                    <p className={`text-right text-lg font-black ${isIncoming ? 'text-emerald-600' : 'text-orange-600'}`}>
                                                                        {isIncoming ? '+' : '-'}{formatQty(Math.abs(Number(tx.quantity_change || 0)))}
                                                                    </p>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
                                                        Aucun mouvement récent sur cette zone.
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div className="space-y-6">
                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100">
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Sous-zones</p>
                                                    <h3 className="text-lg font-black text-slate-950">Organisation interne</h3>
                                                </div>
                                                <div className="p-4 space-y-2 max-h-[320px] overflow-y-auto">
                                                    {selectedLocationChildren.length > 0 ? selectedLocationChildren.map(child => (
                                                        <button
                                                            key={child.id}
                                                            type="button"
                                                            onClick={(event) => openLocationDetail(event, child)}
                                                            className="w-full rounded-xl border border-slate-200 bg-slate-50 hover:bg-blue-50 hover:border-blue-200 p-3 text-left transition-colors"
                                                        >
                                                            <p className="font-black text-slate-900">{child.name}</p>
                                                            <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">{locationUsageLabels[child.usage] || child.usage}</p>
                                                        </button>
                                                    )) : (
                                                        <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm font-bold text-slate-400 text-center">Aucune sous-zone.</p>
                                                    )}
                                                </div>
                                            </div>

                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100">
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Inventaires liés</p>
                                                    <h3 className="text-lg font-black text-slate-950">Contrôles physiques</h3>
                                                </div>
                                                <div className="p-4 space-y-2">
                                                    {selectedLocationInventorySessions.length > 0 ? selectedLocationInventorySessions.map(session => (
                                                        <button
                                                            key={session.id}
                                                            type="button"
                                                            onClick={() => setCurrentMenu('physical-inventory')}
                                                            className="w-full rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 p-3 text-left transition-colors"
                                                        >
                                                            <div className="flex items-center justify-between gap-2">
                                                                <p className="font-black text-slate-900">{session.name || session.reference}</p>
                                                                <span className="rounded-lg bg-white px-2 py-1 text-[10px] font-black uppercase text-slate-500 border border-slate-200">{session.status || '-'}</span>
                                                            </div>
                                                            <p className="text-[11px] font-bold text-slate-400 mt-1">{session.lines?.length || 0} ligne(s)</p>
                                                        </button>
                                                    )) : (
                                                        <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm font-bold text-slate-400 text-center">Aucune campagne liée.</p>
                                                    )}
                                                </div>
                                            </div>

                                            <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Actions utiles</p>
                                                <div className="mt-4 grid grid-cols-1 gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setActiveLocationId(selectedLocation.id);
                                                            setCurrentMenu('stock');
                                                            setInventoryFocus('stock');
                                                        }}
                                                        className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-3 text-sm font-black text-slate-700 inline-flex items-center justify-center gap-2"
                                                    >
                                                        <Box className="w-4 h-4" />
                                                        Voir comme filtre stock
                                                    </button>
                                                    {stockPermissions.validateInventory && selectedLocation.usage === 'internal' && (
                                                        <button
                                                            type="button"
                                                            onClick={() => setCurrentMenu('physical-inventory')}
                                                            className="rounded-xl border border-blue-100 bg-blue-50 hover:bg-blue-100 px-4 py-3 text-sm font-black text-blue-700 inline-flex items-center justify-center gap-2"
                                                        >
                                                            <ClipboardCheck className="w-4 h-4" />
                                                            Lancer / ouvrir inventaire
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : currentMenu === 'product-detail' && selectedProduct ? (
                    <div className="flex-1 overflow-y-auto w-full bg-slate-50">
                        <div className="w-full p-6 space-y-6">
                            <div className="border border-slate-200 bg-white overflow-hidden shadow-sm">
                                <div className="px-6 py-5 bg-slate-950 text-white flex flex-wrap items-start justify-between gap-4">
                                    <div className="min-w-0">
                                        <button
                                            type="button"
                                            onClick={closeProductDetail}
                                            className="mb-4 inline-flex items-center gap-2 rounded-xl bg-white/10 hover:bg-white/15 px-3 py-2 text-xs font-black text-slate-200 transition-colors"
                                        >
                                            <ArrowLeft className="w-4 h-4" />
                                            Retour inventaire
                                        </button>
                                        <div className="flex flex-wrap items-center gap-2 mb-3">
                                            <span className="rounded-lg bg-white/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-blue-100">
                                                {selectedProduct.product_type === 'service' ? 'Prestation' : 'Article stock'}
                                            </span>
                                            {isDraftProduct(selectedProduct) && (
                                                <span className="rounded-lg bg-amber-400/20 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber-100">
                                                    Brouillon catalogue
                                                </span>
                                            )}
                                        </div>
                                        <h2 className="text-3xl font-black leading-tight truncate">{selectedProduct.name}</h2>
                                        <p className="mt-2 text-sm font-bold text-slate-300">
                                            {selectedProduct.reference_base} · {selectedProduct.supplier || 'Fournisseur non renseigné'} · {selectedProduct.material_type || 'Catégorie non renseignée'}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        {selectedProduct.technical_doc_url && (
                                            <a
                                                href={selectedProduct.technical_doc_url}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="px-4 py-3 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-black inline-flex items-center gap-2"
                                            >
                                                <FileText className="w-4 h-4" />
                                                Fiche technique
                                            </a>
                                        )}
                                        {isManager && (
                                            <>
                                                <button
                                                    type="button"
                                                    onClick={(event) => openAddVariant(event, selectedProduct)}
                                                    className="px-4 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                                >
                                                    <Plus className="w-4 h-4" />
                                                    Variante
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={(event) => openEditProduct(event, selectedProduct)}
                                                    className="px-4 py-3 rounded-xl bg-white text-slate-950 text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                                >
                                                    <Edit3 className="w-4 h-4" />
                                                    Modifier
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>

                                <div className="p-6 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6">
                                    <div className="space-y-4">
                                        <div className="rounded-2xl border border-slate-200 bg-white p-4">
                                            <div className="aspect-square rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-center overflow-hidden">
                                                {selectedProduct.image_url ? (
                                                    <img src={selectedProduct.image_url} alt={selectedProduct.name} className="w-full h-full object-cover" />
                                                ) : (
                                                    <Image className="w-12 h-12 text-slate-300" />
                                                )}
                                            </div>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
	                                            <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Repères</p>
                                            <div>
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Unité</p>
                                                <p className="font-black text-slate-900">{selectedProduct.unit || 'pce'}</p>
                                            </div>
                                            <div>
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Gammes compatibles</p>
                                                <p className="text-sm font-bold text-slate-600">{selectedProduct.compatible_series || 'Non renseigné'}</p>
                                            </div>
	                                            <div>
	                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Déclinaisons</p>
	                                                <p className="font-black text-slate-900">{selectedProduct.variants?.length || 0}</p>
	                                            </div>
	                                        </div>
                                            <div className="rounded-2xl border border-slate-200 bg-white p-4">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Actions utiles</p>
                                                <div className="mt-4 grid grid-cols-1 gap-2">
                                                    {stockPermissions.receive && selectedProduct.variants?.[0] && (
                                                        <button
                                                            type="button"
                                                            onClick={() => openReceptionForVariant(selectedProduct.variants[0])}
                                                            className="rounded-xl border border-emerald-100 bg-emerald-50 hover:bg-emerald-100 px-4 py-3 text-sm font-black text-emerald-700 inline-flex items-center justify-center gap-2"
                                                        >
                                                            <Truck className="w-4 h-4" />
                                                            Entrée stock
                                                        </button>
                                                    )}
                                                    <button
                                                        type="button"
                                                        onClick={() => setCurrentMenu('audit')}
                                                        className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-3 text-sm font-black text-slate-700 inline-flex items-center justify-center gap-2"
                                                    >
                                                        <Layers className="w-4 h-4" />
                                                        Voir mouvements
                                                    </button>
                                                    {isManager && (
                                                        <button
                                                            type="button"
                                                            onClick={(event) => openEditProduct(event, selectedProduct)}
                                                            className="rounded-xl border border-blue-100 bg-blue-50 hover:bg-blue-100 px-4 py-3 text-sm font-black text-blue-700 inline-flex items-center justify-center gap-2"
                                                        >
                                                            <Edit3 className="w-4 h-4" />
                                                            Modifier la fiche
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
	                                    </div>

                                    <div className="space-y-6 min-w-0">
                                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Stock physique</p>
                                                <p className="mt-2 text-3xl font-black text-slate-950">{formatQty(selectedProductSummary.physicalStock)}</p>
                                            </div>
                                            <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-amber-700">Réservé</p>
                                                <p className="mt-2 text-3xl font-black text-amber-700">{formatQty(selectedProductSummary.reserved)}</p>
                                            </div>
                                            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
                                                <p className="text-[10px] uppercase tracking-widest font-black text-emerald-700">Disponible</p>
                                                <p className="mt-2 text-3xl font-black text-emerald-700">{formatQty(selectedProductSummary.available)}</p>
                                            </div>
                                            {isAdmin && (
                                                <div className="rounded-2xl border border-slate-200 bg-slate-950 p-4 shadow-sm text-white">
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-300">Valorisation</p>
                                                    <p className="mt-2 text-3xl font-black">{selectedProductSummary.valuation.toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })}</p>
                                                </div>
                                            )}
                                        </div>

                                        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                            <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                                                <div>
	                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Contenu stock</p>
                                                    <h3 className="text-lg font-black text-slate-950">Où se trouve cet article ?</h3>
                                                </div>
                                                {stockPermissions.receive && selectedProduct.variants?.[0] && (
                                                    <button
                                                        type="button"
                                                        onClick={() => openReceptionForVariant(selectedProduct.variants[0])}
                                                        className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-black inline-flex items-center gap-2"
                                                    >
                                                        <Truck className="w-4 h-4" />
                                                        Entrée stock
                                                    </button>
                                                )}
                                            </div>
                                            {selectedProductLocationRows.length > 0 ? (
                                                <div className="divide-y divide-slate-100">
                                                    {selectedProductLocationRows.map(row => {
                                                        const reservedQuantity = Number(row.variant?.reserved_quantity || 0);
                                                        const availableQuantity = Number(row.variant?.available_quantity ?? Math.max(Number(row.quantity || 0) - reservedQuantity, 0));
                                                        return (
                                                            <div key={`${row.variant_id}-${row.location_id}`} className="grid grid-cols-1 md:grid-cols-[1fr_150px_130px_140px_120px] gap-3 px-5 py-4 items-center">
                                                                <div className="min-w-0">
                                                                    <p className="font-black text-slate-900 truncate">{row.locationName}</p>
                                                                    <p className="text-xs font-bold text-slate-400">{row.variant?.reference || 'Référence inconnue'}</p>
                                                                </div>
                                                                <div>
                                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Physique</p>
                                                                    <p className="text-lg font-black text-slate-950">{formatQty(row.quantity)}</p>
                                                                </div>
                                                                <div>
                                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Réservé</p>
                                                                    <p className="text-lg font-black text-amber-600">{formatQty(reservedQuantity)}</p>
                                                                </div>
                                                                <div>
                                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Disponible global</p>
                                                                    <p className="text-lg font-black text-emerald-600">{formatQty(availableQuantity)}</p>
                                                                </div>
                                                                <div className="flex items-center justify-end gap-2">
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => handlePrintBarcode(row.variant.id)}
                                                                        className="p-2 rounded-xl border border-slate-200 text-slate-500 hover:text-slate-900 hover:bg-slate-50"
                                                                        title="Imprimer l'étiquette"
                                                                    >
                                                                        <Hash className="w-4 h-4" />
                                                                    </button>
                                                                    {stockPermissions.transfer && (
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => openTransferModal(row.variant, row.location_id)}
                                                                            className="px-3 py-2 rounded-xl bg-slate-900 text-white text-xs font-black inline-flex items-center gap-1.5"
                                                                        >
                                                                            Transférer <ArrowRight className="w-3.5 h-3.5" />
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            ) : (
                                                <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
                                                    Aucun stock physique trouvé sur les emplacements internes.
                                                </div>
                                            )}
                                        </div>

                                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100">
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Déclinaisons</p>
                                                    <h3 className="text-lg font-black text-slate-950">Références exploitables</h3>
                                                </div>
                                                <div className="divide-y divide-slate-100">
                                                    {(selectedProduct.variants || []).map(variant => {
                                                        const stock = getInternalStockForVariant(variant.id);
                                                        const reservedQuantity = Number(variant.reserved_quantity || 0);
                                                        const availableQuantity = Number(variant.available_quantity ?? Math.max(stock - reservedQuantity, 0));
                                                        return (
                                                            <div key={variant.id} className="px-5 py-4 flex flex-wrap items-center justify-between gap-3">
                                                                <div>
                                                                    <p className="font-black text-slate-900">{variant.color || 'Standard'}</p>
                                                                    <p className="text-xs font-mono font-bold text-slate-400">{variant.reference}</p>
                                                                    {variant.supplier_reference && <p className="text-[11px] font-bold text-slate-400">Fournisseur : {variant.supplier_reference}</p>}
                                                                </div>
                                                                <div className="flex items-center gap-2">
                                                                    <span className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-black text-slate-600">Stock {formatQty(stock)}</span>
                                                                    <span className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-black text-amber-700">Rés. {formatQty(reservedQuantity)}</span>
                                                                    <span className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-black text-emerald-700">Disp. {formatQty(availableQuantity)}</span>
                                                                    {isManager && (
                                                                        <button
                                                                            type="button"
                                                                            onClick={(event) => openEditVariant(event, variant)}
                                                                            className="p-2 rounded-xl border border-slate-200 text-slate-500 hover:text-blue-600 hover:bg-blue-50"
                                                                            title="Modifier la variante"
                                                                        >
                                                                            <FileEdit className="w-4 h-4" />
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            </div>

                                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                <div className="px-5 py-4 border-b border-slate-100">
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Réservations actives</p>
                                                    <h3 className="text-lg font-black text-slate-950">Stock bloqué</h3>
                                                </div>
                                                {selectedProductReservations.length > 0 ? (
                                                    <div className="divide-y divide-slate-100">
                                                        {selectedProductReservations.map(reservation => (
                                                            <div key={reservation.id || reservation.reference} className="px-5 py-4">
                                                                <div className="flex items-center justify-between gap-3">
                                                                    <p className="font-black text-slate-900">{reservation.reference || reservation.reservation_ref || `Réservation #${reservation.id}`}</p>
                                                                    <span className="rounded-lg bg-amber-50 text-amber-700 border border-amber-200 px-2 py-1 text-[10px] font-black uppercase">{reservation.status || 'active'}</span>
                                                                </div>
                                                                <p className="mt-1 text-xs font-bold text-slate-500">{reservation.source_label || reservation.sale_reference || reservation.order_reference || 'Document lié non renseigné'}</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
                                                        Aucune réservation active connue pour cet article.
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                                <div>
                                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Traçabilité</p>
                                                    <h3 className="text-lg font-black text-slate-950">Derniers mouvements</h3>
                                                </div>
                                                <button type="button" onClick={() => setCurrentMenu('audit')} className="text-xs font-black text-blue-600 hover:text-blue-700">
                                                    Voir tous les mouvements
                                                </button>
                                            </div>
                                            {selectedProductMovements.length > 0 ? (
                                                <div className="divide-y divide-slate-100">
                                                    {selectedProductMovements.map(tx => {
                                                        const isNegative = Number(tx.quantity_change || 0) < 0 || tx.movement_kind === 'workshop_debit';
                                                        return (
                                                            <div key={tx.id} className="grid grid-cols-1 md:grid-cols-[140px_1fr_100px] gap-3 px-5 py-4 items-center">
                                                                <div>
                                                                    <p className="text-xs font-black text-slate-700">{new Date(tx.created_at).toLocaleDateString('fr-FR')}</p>
                                                                    <p className="text-[10px] font-mono text-slate-400">{new Date(tx.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</p>
                                                                </div>
                                                                <div className="min-w-0">
                                                                    <div className="flex flex-wrap items-center gap-2">
                                                                        <span className="rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-black uppercase text-slate-600">{tx.transaction_type || tx.movement_kind || 'Mouvement'}</span>
                                                                        <span className="truncate text-[11px] font-mono font-bold text-slate-400">{tx.reference}</span>
                                                                    </div>
                                                                    <p className="mt-1 text-xs font-bold text-slate-500 truncate">{tx.notes || `${tx.location_from_name || 'Origine'} -> ${tx.location_to_name || 'Destination'}`}</p>
                                                                </div>
                                                                <p className={`text-right text-lg font-black ${isNegative ? 'text-orange-600' : 'text-emerald-600'}`}>
                                                                    {isNegative ? '' : '+'}{formatQty(tx.quantity_change)}
                                                                </p>
                                                            </div>
                                                        );
                                                    })}
                                                </div>
                                            ) : (
                                                <div className="px-5 py-8 text-center text-sm font-bold text-slate-400">
                                                    Aucun mouvement enregistré pour cet article.
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : currentMenu === 'todo' ? (
                    <div className="flex-1 overflow-y-auto w-full relative p-6 bg-slate-50">
                        <StockTodoView
                            userRole={user?.role}
                            isManager={isManager}
                            isAdmin={isAdmin}
                            permissions={stockPermissions}
                            roleFilter={todoRoleFilter}
                            setRoleFilter={setTodoRoleFilter}
                            counts={todoCounts}
                            lowStockVariants={lowStockVariants}
                            draftProducts={draftProducts}
                            reservations={reservations}
                            openInventorySessions={openInventorySessions}
                            openPurchases={openPurchases}
                            recentManualAdjustments={recentManualAdjustments}
                            actions={todoActions}
                            reservationActionId={reservationActionId}
                        />
                    </div>
                ) : currentMenu === 'risk' ? (
                    <div className="flex-1 overflow-y-auto w-full relative p-6 bg-slate-50">
                        <StockRiskView
                            loading={loadingPurchaseNeeds}
                            needs={purchaseNeeds}
                            summary={purchaseRiskSummary}
                            criticalNeeds={criticalPurchaseNeeds}
                            blockedNeeds={blockedPurchaseNeeds}
                            coveredNeeds={coveredPurchaseNeeds}
                            longLeadTimeNeeds={longLeadTimeNeeds}
                            onOpenPurchases={goToPurchases}
                            canCreatePurchaseRequest={stockPermissions.requestPurchases}
                            riskActionVariantId={riskActionVariantId}
                            onCreatePurchaseRequest={createPurchaseRequestFromRisk}
                            onOpenProduct={(productId) => {
                                const product = products.find(item => item.id === productId);
                                if (product) openProductDetail(null, product);
                            }}
                        />
                    </div>
                ) : currentMenu === 'workshop' ? (
                    <div className="flex-1 overflow-y-auto w-full relative bg-slate-50">
                        <div className="w-full p-6 space-y-6">
                            <div className="border border-slate-200 bg-white overflow-hidden shadow-sm">
                                <div className="px-6 py-5 bg-amber-50 border-b border-amber-100 flex flex-wrap items-start justify-between gap-4">
                                    <div>
                                        <p className="text-[10px] uppercase font-black tracking-widest text-amber-700 mb-2">Réservations atelier</p>
                                        <h2 className="text-2xl font-black text-slate-950 flex items-center gap-3">
                                            <ArrowRight className="w-6 h-6 text-amber-600" />
                                            Débit atelier
                                        </h2>
                                        <p className="text-sm font-bold text-slate-600 mt-1 max-w-3xl">
                                            Prévisualisez les fichiers Progers / Orgadata, réservez virtuellement le stock, puis transformez la réservation en débit réel au poste atelier.
                                        </p>
                                    </div>
                                    {stockPermissions.reserveWorkshop && (
                                        <button
                                            type="button"
                                            onClick={() => setShowWorkshopDebitModal(true)}
                                            className="px-4 py-3 rounded-xl bg-amber-500 hover:bg-amber-400 text-white text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                        >
                                            <FileText className="w-4 h-4" />
                                            Importer débit atelier
                                        </button>
                                    )}
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-6 border-b border-slate-100">
                                    <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-amber-700">Réservations ouvertes</p>
                                        <p className="text-3xl font-black text-amber-800 mt-2">{reservations.length}</p>
                                        <p className="text-xs font-bold text-amber-700 mt-1">À consommer ou à annuler.</p>
                                    </div>
                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Règle</p>
                                        <p className="text-lg font-black text-slate-950 mt-2">Réserver avant débit réel</p>
                                        <p className="text-xs font-bold text-slate-500 mt-1">Le stock physique ne baisse qu’au débit réel atelier.</p>
                                    </div>
                                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-emerald-700">Contrôle</p>
                                        <p className="text-lg font-black text-emerald-800 mt-2">Devis / ordre obligatoire</p>
                                        <p className="text-xs font-bold text-emerald-700 mt-1">Aucune consommation sans contexte validé.</p>
                                    </div>
                                </div>
                                <div className="p-6">
                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden">
                                        <div className="px-5 py-4 border-b border-slate-200 bg-white flex items-center justify-between">
                                            <div>
                                                <p className="text-xs uppercase tracking-widest font-black text-slate-400">À traiter</p>
                                                <h3 className="text-xl font-black text-slate-900">Réservations atelier actives</h3>
                                            </div>
                                        </div>
                                        {reservations.length > 0 ? (
                                            <div className="divide-y divide-slate-200">
                                                {reservations.map(reservation => {
                                                    const totalReserved = reservation.lines?.reduce((sum, line) => sum + (line.reserved_quantity || 0), 0) || 0;
                                                    return (
                                                        <div key={reservation.id} className="p-5 flex flex-wrap items-center justify-between gap-4 bg-white">
                                                            <div>
                                                                <p className="font-black text-slate-950">{reservation.order_reference || reservation.project_reference || reservation.reference}</p>
                                                                <p className="text-sm font-bold text-slate-500 mt-1">{reservation.lines?.length || 0} ligne(s) - {totalReserved.toLocaleString('fr-FR')} réservé</p>
                                                            </div>
                                                            <div className="flex gap-2">
                                                                <button onClick={() => consumeWorkshopReservation(reservation)} disabled={!stockPermissions.consumeWorkshop || reservationActionId === reservation.id} className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 text-white text-sm font-black">
                                                                    Débit réel
                                                                </button>
                                                                <button onClick={() => cancelWorkshopReservation(reservation)} disabled={!stockPermissions.reserveWorkshop || reservationActionId === reservation.id} className="px-4 py-2 rounded-xl bg-white hover:bg-slate-50 disabled:bg-slate-100 text-slate-700 text-sm font-black border border-slate-200">
                                                                    Annuler
                                                                </button>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        ) : (
                                            <div className="p-10 text-center bg-white">
                                                <Check className="w-10 h-10 mx-auto text-emerald-400 mb-3" />
                                                <p className="font-black text-slate-700">Aucune réservation atelier ouverte.</p>
                                                <p className="text-sm font-bold text-slate-400 mt-1">Importez un débit atelier quand un devis ou ordre est prêt.</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : currentMenu === 'import-export' ? (
                    <div className="flex-1 overflow-y-auto w-full relative bg-slate-50">
                        <div className="w-full p-6">
                            <div className="border border-slate-200 bg-white overflow-hidden shadow-sm">
                                <div className="px-6 py-5 bg-slate-900 text-white flex flex-wrap items-start justify-between gap-4">
                                    <div>
                                        <p className="text-[10px] uppercase font-black tracking-widest text-blue-200 mb-2">Données stock</p>
                                        <h2 className="text-2xl font-black flex items-center gap-3">
                                            <Download className="w-6 h-6 text-blue-300" />
                                            Import / Export
                                        </h2>
                                        <p className="text-sm font-bold text-slate-300 mt-1 max-w-3xl">
                                            Centralisez ici les imports PIM, la mise à jour des brouillons catalogue et les exports d’inventaire.
                                        </p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 p-6">
                                    <button
                                        type="button"
                                        onClick={() => setShowImportModal(true)}
                                        className="text-left rounded-2xl border border-blue-100 bg-blue-50 hover:bg-blue-100 p-5 transition-colors"
                                    >
                                        <FileText className="w-6 h-6 text-blue-600 mb-4" />
                                        <p className="font-black text-slate-950">Importer catalogue / stock</p>
                                        <p className="text-sm font-bold text-slate-600 mt-1">Template PIM, brouillons catalogue et fichiers Excel.</p>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleExportExcel}
                                        className="text-left rounded-2xl border border-orange-100 bg-orange-50 hover:bg-orange-100 p-5 transition-colors"
                                    >
                                        <Download className="w-6 h-6 text-orange-600 mb-4" />
                                        <p className="font-black text-slate-950">Exporter inventaire</p>
                                        <p className="text-sm font-bold text-slate-600 mt-1">Télécharger l’état courant du stock au format Excel.</p>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => selectInventoryFocus('drafts')}
                                        className="text-left rounded-2xl border border-amber-100 bg-amber-50 hover:bg-amber-100 p-5 transition-colors"
                                    >
                                        <FileEdit className="w-6 h-6 text-amber-600 mb-4" />
                                        <p className="font-black text-slate-950">Qualifier les brouillons</p>
                                        <p className="text-sm font-bold text-slate-600 mt-1">{totalDraftCount} fiche(s) catalogue à compléter.</p>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : currentMenu === 'locations' ? (
                    <div className="flex-1 overflow-y-auto w-full relative bg-slate-50">
                        <div className="w-full p-6 space-y-6">
                            <div className="border border-slate-200 bg-white overflow-hidden shadow-sm">
                                <div className="px-6 py-5 bg-slate-900 text-white flex flex-wrap items-start justify-between gap-4">
                                    <div>
                                        <p className="text-[10px] uppercase font-black tracking-widest text-blue-200 mb-2">Plan de rangement stock</p>
                                        <h2 className="text-2xl font-black flex items-center gap-3">
                                            <MapPin className="w-6 h-6 text-blue-300" />
                                            Zones & emplacements
                                        </h2>
                                        <p className="text-sm font-bold text-slate-300 mt-1 max-w-3xl">
                                            Créez les entrepôts, zones, racks et emplacements utilisés par réception, transfert, inventaire physique et débit atelier.
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {canManageLocations ? (
                                            <>
                                                <button
                                                    type="button"
                                                    onClick={() => setAddingSubLocTo('root')}
                                                    className="px-4 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-black inline-flex items-center gap-2 shadow-sm"
                                                >
                                                    <Plus className="w-4 h-4" />
                                                    Nouvel entrepôt
                                                </button>
                                                <button
                                                    type="button"
                                                    onClick={() => setShowLocationManagerModal(true)}
                                                    className="px-4 py-3 rounded-xl bg-white/10 hover:bg-white/15 border border-white/15 text-white text-sm font-black inline-flex items-center gap-2"
                                                >
                                                    <Edit3 className="w-4 h-4" />
                                                    Gestion avancée
                                                </button>
                                            </>
                                        ) : (
                                            <span className="px-4 py-3 rounded-xl bg-white/10 border border-white/15 text-sm font-black text-slate-200">
                                                Lecture seule
                                            </span>
                                        )}
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 p-6 border-b border-slate-100">
                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Zones physiques</p>
                                        <p className="text-3xl font-black text-slate-950 mt-2">{physicalLocations.length}</p>
                                        <p className="text-xs font-bold text-slate-500 mt-1">Entrepôts, racks et emplacements de stock réel.</p>
                                    </div>
                                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Racines</p>
                                        <p className="text-3xl font-black text-slate-950 mt-2">{internalRootLocations.length}</p>
                                        <p className="text-xs font-bold text-slate-500 mt-1">Points d’entrée du plan d’entrepôt.</p>
                                    </div>
                                    <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-emerald-700">Atelier</p>
                                        <p className="text-3xl font-black text-emerald-800 mt-2">{productionLocations.length}</p>
                                        <p className="text-xs font-bold text-emerald-700 mt-1">Zones de production et encours.</p>
                                    </div>
                                    <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-amber-700">Lieux virtuels</p>
                                        <p className="text-3xl font-black text-amber-800 mt-2">{virtualLocations.length}</p>
                                        <p className="text-xs font-bold text-amber-700 mt-1">Fournisseur, client, inventaire ou flux système.</p>
                                    </div>
                                </div>

                                {addingSubLocTo === 'root' && canManageLocations && (
                                    <div className="px-6 py-4 border-b border-blue-100 bg-blue-50">
                                        <div className="max-w-xl">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-blue-700 mb-2">Créer une zone principale</p>
                                            <input
                                                autoFocus
                                                value={newSubLocName}
                                                onChange={event => setNewSubLocName(event.target.value)}
                                                onBlur={() => setAddingSubLocTo(null)}
                                                onKeyDown={event => {
                                                    if (event.key === 'Escape') setAddingSubLocTo(null);
                                                    if (event.key === 'Enter') handleAddSubLocation(event, 'root');
                                                }}
                                                className="w-full text-sm p-3 bg-white border border-blue-200 rounded-xl text-slate-900 font-bold placeholder-slate-400 outline-none focus:ring-2 focus:ring-blue-500/30 transition-all"
                                                placeholder="Ex: Entrepôt principal, Rack ALU, Zone vitrage... Entrée pour créer"
                                            />
                                        </div>
                                    </div>
                                )}

                                <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6 p-6">
                                    <div className="space-y-4">
                                        <div>
                                            <p className="text-xs uppercase tracking-widest font-black text-slate-400">Arborescence physique</p>
                                            <h3 className="text-xl font-black text-slate-900">Entrepôts, zones et emplacements</h3>
                                        </div>
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-2">
                                            {internalRootLocations.map(location => (
                                                canManageLocations ? renderManagedLocationTree(location) : renderLocationTree(location)
                                            ))}
                                            {internalRootLocations.length === 0 && (
                                                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-10 text-center">
                                                    <MapPin className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                                                    <p className="font-black text-slate-600">Aucun emplacement physique configuré.</p>
                                                    <p className="text-sm font-bold text-slate-400 mt-1">
                                                        Créez au moins un entrepôt ou une zone interne avant de recevoir du stock réel.
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    <div className="space-y-4">
                                        <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                            <p className="text-xs uppercase tracking-widest font-black text-slate-400">Règle simple</p>
                                            <h3 className="font-black text-slate-900 mt-1">Physique vs virtuel</h3>
                                            <div className="space-y-3 mt-4 text-sm font-bold text-slate-600">
                                                <p><span className="text-slate-950">Stock physique</span> : là où un opérateur peut réellement trouver une pièce.</p>
                                                <p><span className="text-slate-950">Lieux virtuels</span> : étapes de flux pour fournisseur, client, production ou inventaire.</p>
                                                <p><span className="text-slate-950">Inventaire</span> : comptez toujours une zone physique clairement identifiée.</p>
                                            </div>
                                        </div>

                                        <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                            <div className="flex items-center justify-between gap-3 mb-4">
                                                <div>
                                                    <p className="text-xs uppercase tracking-widest font-black text-slate-400">Lieux système</p>
                                                    <h3 className="font-black text-slate-900">Virtuels</h3>
                                                </div>
                                                {canManageLocations && (
                                                    <button
                                                        type="button"
                                                        onClick={() => setShowLocationManagerModal(true)}
                                                        className="px-3 py-2 rounded-xl border border-slate-200 text-xs font-black text-slate-600 hover:bg-slate-50"
                                                    >
                                                        Modifier
                                                    </button>
                                                )}
                                            </div>
                                            <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                                                {virtualLocations.map(location => (
                                                    <div key={location.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                        <p className="font-black text-slate-900">{getFullLocationName(location)}</p>
                                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400 mt-1">
                                                            {locationUsageLabels[location.usage] || location.usage}
                                                        </p>
                                                    </div>
                                                ))}
                                                {virtualLocations.length === 0 && (
                                                    <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm font-bold text-slate-400 text-center">
                                                        Aucun lieu virtuel configuré.
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                ) : currentMenu === 'audit' ? (
                    <div className="flex-1 overflow-y-auto w-full relative p-6">
                        <AuditLogs transactions={transactions} locations={locations} />
                    </div>
                ) : currentMenu === 'physical-inventory' ? (
                    <div className="flex-1 overflow-y-auto w-full relative p-6 bg-slate-50">
                        <PhysicalInventoryView
                            sessions={inventorySessions}
                            products={products}
                            locations={locations}
                            quants={quants}
                            canCount={stockPermissions.countInventory}
                            canValidate={stockPermissions.validateInventory}
                            queryClient={queryClient}
                        />
                    </div>
                ) : currentMenu === 'valuation' ? (
                    <div className="flex-1 overflow-y-auto w-full relative bg-slate-50">
                        <StockValuationView products={products} locations={locations} quants={quants} />
                    </div>
                ) : (
                    <>
                        {/* HEADER INFO */}
                <div className="px-6 py-4 bg-white border-b border-slate-200 shrink-0 flex flex-wrap justify-between items-center gap-4">
                    <div>
                        <h2 className="text-xl font-black text-slate-900 flex items-center gap-3 tracking-tight">
                            {inventoryTitle}
                        </h2>
                        <p className="text-sm font-bold text-slate-500 mt-1">
                            {inventorySubtitle}
                        </p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        {activeLocationId === 'global' && currentMenu !== 'services' && isAdmin && (
                            <div className="px-4 py-2 rounded-xl border border-slate-200 bg-slate-50 flex items-center gap-3">
                                <span className="text-[10px] uppercase font-black tracking-widest text-slate-400">Valorisation</span>
                                <span className="text-lg font-black text-slate-950">{totalValuation.toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span>
                            </div>
                        )}
                        {(showLowStockOnly || showDraftOnly) && (
                            <button
                                onClick={() => {
                                    setShowLowStockOnly(false);
                                    setShowDraftOnly(false);
                                    const targetFocus = currentMenu === 'stock' ? 'stock' : 'catalog';
                                    setInventoryFocus(targetFocus);
                                    setCurrentMenu(targetFocus);
                                    setSearchTerm('');
                                }}
                                className="px-4 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-500 font-black text-xs uppercase tracking-widest"
                            >
                                Tous
                            </button>
                        )}
                        {currentMenu === 'catalog' && isManager && (
                            <button onClick={() => openNewProductModal('stockable')} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-black shadow-sm">
                                <Plus className="w-4 h-4"/> Nouvel article
                            </button>
                        )}
                        {currentMenu === 'services' && isManager && (
                            <button onClick={() => openNewProductModal('service')} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-black shadow-sm">
                                <FileEdit className="w-4 h-4"/> Nouvelle prestation
                            </button>
                        )}
                        {currentMenu === 'stock' && (
                            <>
                                {stockPermissions.receive && (
                                    <button onClick={openReceptionModal} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-black shadow-sm">
                                        <Truck className="w-4 h-4"/> Entrée stock
                                    </button>
                                )}
                                {stockPermissions.adjust && (
                                    <button onClick={openCustomerIssueModal} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm font-black shadow-sm">
                                        <ArrowRight className="w-4 h-4"/> Sortie stock
                                    </button>
                                )}
                                <button
                                    onClick={() => {
                                        setShowLowStockOnly(prev => !prev);
                                        setShowDraftOnly(false);
                                        setInventoryFocus('stock');
                                        setSearchTerm('');
                                    }}
                                    className={`px-4 py-2 rounded-xl border inline-flex items-center gap-2 transition-all ${showLowStockOnly ? 'bg-red-600 border-red-600 hover:bg-red-500 text-white' : totalLowStockCount > 0 ? 'bg-white border-red-200 hover:bg-red-50 text-red-600' : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-500'}`}
                                >
                                    <span className="text-[10px] uppercase font-black tracking-widest opacity-70">{showLowStockOnly ? 'Filtre actif' : 'Ruptures'}</span>
                                    <span className="text-lg font-black tracking-tight">{totalLowStockCount}</span>
                                </button>
                            </>
                        )}
                        {currentMenu === 'drafts' && (
                            <>
                                {isManager && (
                                    <button onClick={() => setShowImportModal(true)} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-white text-sm font-black shadow-sm">
                                        <FileText className="w-4 h-4"/> Importer brouillons
                                    </button>
                                )}
                                <div className="px-4 py-2 rounded-xl border border-amber-200 bg-amber-50 text-amber-700 inline-flex items-center gap-2">
                                    <span className="text-[10px] uppercase font-black tracking-widest">Brouillons</span>
                                    <span className="text-lg font-black tracking-tight">{totalDraftCount}</span>
                                </div>
                            </>
                        )}
                    </div>
                </div>

                {/* THE GRID / LIST */}
                <div className="flex-1 overflow-y-auto w-full relative p-4 bg-white">
                    {groupedData.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-64 border-2 border-dashed border-slate-200 rounded-3xl m-6">
                            <Box className="w-12 h-12 text-slate-300 mb-4" />
                            <p className="text-center text-slate-400 font-bold">
                                {inventoryFocus === 'services' ? 'Aucune prestation trouvée avec le filtre actuel.' : 'Aucun produit trouvé avec le filtre actuel.'} <br/> <span className="text-sm font-medium italic">Réinitialisez les filtres ou changez d'emplacement.</span>
                            </p>
                        </div>
                    )}

                    {viewMode === 'list' && groupedData.length > 0 && (
                        <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-slate-50/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-10">
                                    <tr>
                                        <th className="py-4 px-6 text-[10px] font-black text-slate-400 uppercase tracking-widest w-1/3">Famille PIM</th>
                                        <th className="py-4 px-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center">{inventoryFocus === 'services' ? 'Famille' : 'Catégorie'}</th>
                                        <th className="py-4 px-4 text-[10px] font-black text-slate-400 uppercase tracking-widest text-center">{inventoryFocus === 'services' ? 'Unité' : 'Fournisseur'}</th>
                                        <th className="py-4 px-6 text-[10px] font-black text-slate-400 uppercase tracking-widest text-right">Contenu & Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                    {groupedData.map(({ product, variants }) => {
                                        const isExpanded = expandedProducts[product.id];
                                        const draftProduct = isDraftProduct(product);
                                        return (
                                            <React.Fragment key={product.id}>
                                                <tr className="group hover:bg-slate-50 transition-colors cursor-pointer border-l-4 border-l-transparent hover:border-l-blue-400" onClick={() => toggleExpand(product.id)}>
                                                    <td className="py-4 px-6 flex items-center gap-4">
                                                        <button className="text-slate-400 bg-white shadow-sm p-1 rounded-md border border-slate-100 group-hover:text-blue-500 transition-colors">
                                                            {isExpanded ? <ChevronDown className="w-5 h-5"/> : <ChevronRight className="w-5 h-5"/>}
                                                        </button>
                                                        <div className="w-12 h-12 rounded-xl flex items-center justify-center bg-slate-50 border border-slate-200 shrink-0 overflow-hidden relative">
                                                            {product.image_url ?
                                                                <img src={product.image_url} alt={product.name} className="w-full h-full object-cover" /> :
                                                                <Image className="w-5 h-5 text-slate-300" />
                                                            }
                                                        </div>
                                                        <div>
                                                            <div className="flex items-center gap-2">
                                                                <p className="font-bold text-slate-800 text-lg group-hover:text-blue-700 transition-colors">{product.name}</p>
                                                                {draftProduct && (
                                                                    <span className="text-[9px] uppercase font-black bg-amber-100 text-amber-700 px-2 py-1 rounded-md border border-amber-200">Brouillon</span>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2 mt-0.5">
                                                                <p className="text-xs font-bold text-slate-400">Réf : {product.reference_base}</p>
                                                                {product.technical_doc_url && (
                                                                    <a href={product.technical_doc_url} target="_blank" rel="noreferrer" title="Voir Fiche Technique (PDF)" className="text-xs text-blue-500 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 p-1 rounded-md transition-colors" onClick={e => e.stopPropagation()}>
                                                                        <FileText className="w-3.5 h-3.5" />
                                                                    </a>
                                                                )}
                                                                {product.compatible_series && (
                                                                    <span className="text-[9px] uppercase font-black bg-blue-50 text-blue-500 px-1.5 py-0.5 rounded-md border border-blue-100">Gammes: {product.compatible_series}</span>
                                                                )}
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="py-4 px-4 text-center">
                                                        <span className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg text-xs font-black uppercase tracking-wider">{product.material_type}</span>
                                                    </td>
                                                    <td className="py-4 px-4 text-center">
                                                        {inventoryFocus === 'services' ? (
                                                            <span className="bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-lg text-xs uppercase tracking-wide font-black border border-emerald-100">{product.unit || 'forfait'}</span>
                                                        ) : product.supplier ? <span className="bg-slate-800 text-white px-3 py-1.5 rounded-lg text-xs uppercase tracking-wide font-black">{product.supplier}</span> : <span className="text-slate-300">-</span>}
                                                    </td>
                                                    <td className="py-4 px-6 text-right">
                                                        <div className="flex items-center justify-end gap-3">
                                                            <span className="px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-black border border-blue-100">{variants.length} {variants.length > 1 ? 'déclinaisons' : 'déclinaison'}</span>
                                                            <button
                                                                type="button"
                                                                onClick={(e) => openProductDetail(e, product)}
                                                                className="px-3 py-1.5 bg-slate-900 text-white hover:bg-slate-800 rounded-lg border border-slate-900 transition-colors text-xs font-bold shadow-sm flex items-center gap-1"
                                                                title="Ouvrir la fiche article"
                                                            >
                                                                <Box className="w-3.5 h-3.5"/> Fiche
                                                            </button>
                                                            {isManager && (
                                                                <>
                                                                    <button
                                                                        onClick={(e) => { e.stopPropagation(); openAddVariant(e, product); }}
                                                                        className="px-3 py-1.5 bg-emerald-50 text-emerald-600 hover:bg-emerald-600 hover:text-white rounded-lg border border-emerald-200 transition-colors text-xs font-bold shadow-sm flex items-center gap-1"
                                                                        title="Ajouter une déclinaison"
                                                                    >
                                                                        <Plus className="w-3.5 h-3.5"/> Ajouter Variante
                                                                    </button>
                                                                    <button
                                                                        onClick={(e) => { e.stopPropagation(); openEditProduct(e, product); }}
                                                                        className="px-3 py-1.5 bg-slate-50 text-slate-600 hover:bg-slate-200 hover:text-slate-800 rounded-lg border border-slate-200 transition-colors text-xs font-bold shadow-sm flex items-center gap-1"
                                                                    >
                                                                        <Edit3 className="w-3.5 h-3.5"/> Modifier
                                                                    </button>
                                                                </>
                                                            )}
                                                        </div>
                                                    </td>
                                                </tr>

                                                {/* EXPANDED VARIANTS SUB-TABLE */}
                                                {isExpanded && variants.map((v) => {
                                                    const isEditing = editingQuant?.variantId === v.variantId && editingQuant?.locId === v.locId;
                                                    const canEditInline = activeLocationId !== 'global';
                                                    const variantTransactions = getVariantTransactions(v.variantId);
                                                    return (
                                                        <tr key={v.variantId} className="bg-slate-50/40 transition-colors border-l-4 border-l-blue-400">
                                                            <td colSpan="4" className="py-0 px-0">
                                                                <div className="pl-24 pr-6 py-4 border-b border-slate-100/50 hover:bg-white transition-colors group/var">
                                                                    <div className="flex items-center justify-between">
                                                                        <div className="flex flex-col">
                                                                            <span className="font-bold text-slate-900 text-[15px] group-hover/var:text-blue-600 transition-colors">{v.variantLabel}</span>
                                                                            <div className="flex items-center gap-2">
                                                                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mt-0.5">{v.variantRef}</span>
                                                                                {v.fullVariant.location && (
                                                                                    <div className="text-[10px] font-black bg-orange-50 text-orange-600 px-1.5 py-0.5 rounded-md flex items-center gap-1 border border-orange-100 mt-0.5" title="Chemin de Rangement (Allée/Rayon)">
                                                                                        <MapPin className="w-2.5 h-2.5"/> {v.fullVariant.location}
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                        <div className="flex items-center gap-6">
                                                                            {/* QUANTITY : INLINE EDIT */}
                                                                            {inventoryFocus !== 'services' && (
                                                                                <div className="hidden lg:flex items-center gap-2">
                                                                                    <div className="bg-white border border-slate-200 rounded-xl px-3 py-2 text-right shadow-sm min-w-[84px]">
                                                                                        <p className="text-[9px] font-black uppercase text-slate-400 tracking-widest">Réservé</p>
                                                                                        <p className={`text-sm font-black ${v.reservedQuantity > 0 ? 'text-amber-600' : 'text-slate-400'}`}>
                                                                                            {formatQty(v.reservedQuantity)}
                                                                                        </p>
                                                                                    </div>
                                                                                    <div className="bg-white border border-slate-200 rounded-xl px-3 py-2 text-right shadow-sm min-w-[96px]">
                                                                                        <p className="text-[9px] font-black uppercase text-slate-400 tracking-widest">Disponible</p>
                                                                                        <p className={`text-sm font-black ${v.availableQuantity > 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                                                                                            {formatQty(v.availableQuantity)}
                                                                                        </p>
                                                                                    </div>
                                                                                </div>
                                                                            )}
                                                                            <div className="text-right flex items-center gap-3 bg-white border border-slate-200 shadow-sm rounded-xl pr-1 overflow-hidden">
                                                                                <span className="text-[9px] font-black uppercase text-slate-400 tracking-widest pl-3 bg-slate-50 h-full py-2 border-r border-slate-100">{inventoryFocus === 'services' ? 'Prix HT' : 'STOCK'}</span>
                                                                                {isEditing ? (
                                                                                    <input
                                                                                        autoFocus type="number" value={quantInputValue} onChange={(e) => setQuantInputValue(e.target.value)} onKeyDown={handleQuantInputKeyDown} onBlur={submitQuantEdit} className="w-20 text-center py-1 border-none text-lg font-black bg-blue-50 text-blue-700 outline-none focus:ring-0"
                                                                                    />
                                                                                ) : (
                                                                                    <div
                                                                                        className={`inline-block px-3 py-1 min-w-[3.5rem] text-center border-2 border-transparent hover:border-blue-200 hover:bg-blue-50 transition-colors font-black text-lg rounded-lg mx-1 ${inventoryFocus === 'services' ? 'text-emerald-600' : v.stockToDisplay > 0 ? 'text-emerald-600' : 'text-slate-400'} ${inventoryFocus === 'services' || !canEditInline || !isManager ? 'cursor-not-allowed opacity-50' : 'cursor-text'}`}
                                                                                        onClick={() => (canEditInline && isManager) && startEditingQuant(v.variantId, v.locId, v.stockToDisplay)}
                                                                                        title={inventoryFocus === 'services' ? "Le tarif se modifie depuis la fiche variante" : (canEditInline && isManager) ? "1-Clic : Double-tapez pour modifier le stock direct" : "Impossible (Vue globale ou permissions insuffisantes)"}
                                                                                    >
                                                                                        {inventoryFocus === 'services' ? (v.fullVariant.cost_price || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' }) : formatQty(v.stockToDisplay)}
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                            {/* ROW ACTIONS */}
                                                                            <div className="w-auto flex items-center gap-2 justify-end opacity-0 group-hover/var:opacity-100 transition-opacity">
                                                                                <button onClick={(e) => { e.stopPropagation(); handlePrintBarcode(v.variantId); }} className="text-slate-400 hover:text-slate-700 bg-white border border-slate-200 hover:border-slate-300 px-2 py-1.5 rounded-lg flex items-center shadow-sm" title="Imprimer Code-barre"><Hash className="w-3.5 h-3.5"/></button>
                                                                                {isManager && (
                                                                                    <>
                                                                                        <button onClick={(e) => openEditVariant(e, v.fullVariant)} className="text-slate-400 hover:text-blue-600 bg-white border border-slate-200 hover:border-blue-300 px-2 py-1.5 rounded-lg flex items-center shadow-sm" title="Modifier Variante"><FileEdit className="w-3.5 h-3.5"/></button>
                                                                                        {activeLocationId !== 'global' && (
                                                                                            <button onClick={() => openTransferModal(v.fullVariant, activeLocationId)} className="bg-slate-800 border border-slate-700 hover:bg-slate-700 text-white px-3 py-1.5 rounded-lg text-xs font-black flex items-center gap-1.5 shadow-md">
                                                                                                Trsf <ArrowRight className="w-3.5 h-3.5"/>
                                                                                            </button>
                                                                                        )}
                                                                                    </>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                    <div className="mt-4 rounded-2xl border border-slate-200 bg-white overflow-hidden">
                                                                        <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                                                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Historique mouvements</span>
                                                                            <span className="text-[10px] font-bold text-slate-400">{variantTransactions.length ? `${variantTransactions.length} récent(s)` : 'Aucun mouvement'}</span>
                                                                        </div>
                                                                        {variantTransactions.length > 0 ? (
                                                                            <div className="divide-y divide-slate-100">
                                                                                {variantTransactions.map(tx => {
                                                                                    const isWorkshopDebit = tx.movement_kind === 'workshop_debit' || tx.reference?.startsWith('DEBIT-ATELIER');
                                                                                    return (
                                                                                        <div key={tx.id} className="grid grid-cols-[150px_1fr_90px] gap-3 px-4 py-3 items-center">
                                                                                            <div>
                                                                                                <p className="text-[11px] font-black text-slate-600">{new Date(tx.created_at).toLocaleDateString('fr-FR')}</p>
                                                                                                <p className="text-[10px] text-slate-400 font-mono">{new Date(tx.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</p>
                                                                                            </div>
                                                                                            <div className="min-w-0">
                                                                                                <div className="flex items-center gap-2">
                                                                                                    <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-md ${isWorkshopDebit ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
                                                                                                        {isWorkshopDebit ? 'Débit atelier réel' : tx.transaction_type}
                                                                                                    </span>
                                                                                                    <span className="text-[10px] font-mono text-slate-400 truncate">{tx.reference}</span>
                                                                                                </div>
                                                                                                {tx.notes && <p className="text-[11px] text-slate-500 mt-1 truncate">{tx.notes}</p>}
                                                                                            </div>
                                                                                            <div className={`text-right text-sm font-black ${isWorkshopDebit ? 'text-orange-600' : tx.quantity_change > 0 ? 'text-emerald-600' : 'text-blue-600'}`}>
                                                                                                {isWorkshopDebit ? '-' : tx.quantity_change > 0 ? '+' : ''}{tx.quantity_change}
                                                                                            </div>
                                                                                        </div>
                                                                                    );
                                                                                })}
                                                                            </div>
                                                                        ) : (
                                                                            <p className="px-4 py-3 text-xs font-bold text-slate-400">Aucun mouvement enregistré pour cette référence.</p>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </React.Fragment>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {viewMode === 'kanban' && groupedData.length > 0 && (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-6">
                            {groupedData.map(({ product, variants }) => {
                                const totalStock = variants.reduce((acc, v) => acc + (v.stockToDisplay || 0), 0);
                                const isLowStock = false; // Add logic if needed
                                const draftProduct = isDraftProduct(product);

                                return (
                                    <div key={product.id} className="bg-white rounded-3xl border border-slate-200 overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all duration-300 flex flex-col group cursor-pointer" onClick={() => toggleExpand(product.id)}>
                                        <div className="h-48 w-full bg-slate-50 relative overflow-hidden border-b border-slate-100">
                                            {product.image_url ? (
                                                <img src={product.image_url} alt={product.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                                            ) : (
                                                <div className="w-full h-full flex flex-col items-center justify-center text-slate-300">
                                                    <Image className="w-12 h-12 mb-2 opacity-50" />
                                                    <span className="text-xs font-bold uppercase tracking-widest">Sans Image</span>
                                                </div>
                                            )}
                                            <div className="absolute top-3 left-3 px-2.5 py-1 bg-white/90 backdrop-blur border border-white/50 rounded-lg shadow-sm text-[10px] font-black tracking-wider text-slate-700 uppercase">
                                                {product.material_type}
                                            </div>
                                            {draftProduct && (
                                                <div className="absolute top-3 right-3 px-2.5 py-1 bg-amber-100 text-amber-700 border border-amber-200 rounded-lg shadow-sm text-[10px] font-black tracking-wider uppercase">
                                                    Brouillon
                                                </div>
                                            )}
                                        </div>
                                        <div className="p-5 flex-1 flex flex-col">
                                            <p className="text-xs font-bold text-slate-400 mb-1">{product.reference_base}</p>
                                            <h3 className="font-black text-lg text-slate-800 leading-tight mb-4 group-hover:text-blue-600 transition-colors">{product.name}</h3>

                                            <div className="mt-auto space-y-3">
                                                <div className="flex items-end justify-between items-center py-2 border-t border-slate-100 mt-2">
                                                    <div>
                                                        <p className="text-[10px] uppercase text-slate-400 font-bold mb-0.5">{inventoryFocus === 'services' ? 'Tarif indicatif' : 'Stock Total'}</p>
                                                        <p className={`font-black text-xl leading-none ${isLowStock ? 'text-red-500' : 'text-emerald-500'}`}>{inventoryFocus === 'services' ? ((variants[0]?.fullVariant?.cost_price || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' })) : totalStock.toFixed(0)} {inventoryFocus !== 'services' && <span className="text-sm font-bold text-slate-400">{product.unit || 'pce'}</span>}</p>
                                                    </div>
                                                    <div className="bg-slate-50 px-3 py-1.5 rounded-xl border border-slate-100">
                                                        <span className="text-xs font-bold text-slate-500 flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" /> {variants.length} réf.</span>
                                                    </div>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={(e) => openProductDetail(e, product)}
                                                    className="w-full rounded-xl bg-slate-900 hover:bg-slate-800 text-white py-2.5 text-sm font-black inline-flex items-center justify-center gap-2"
                                                >
                                                    <Box className="w-4 h-4" />
                                                    Ouvrir la fiche
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </>
            )}
            </div>
            {/* -------- LOCATION MANAGER POPUP -------- */}
            {showLocationManagerModal && (
                <div className="fixed inset-0 bg-slate-950/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl w-full max-w-5xl max-h-[90vh] border border-slate-100 overflow-hidden flex flex-col">
                        <div className="px-6 py-5 bg-slate-900 text-white flex items-start justify-between gap-4">
                            <div>
                                <p className="text-[10px] uppercase font-black tracking-widest text-blue-200 mb-2">Entrepôt & rangement</p>
                                <h3 className="text-2xl font-black flex items-center gap-3">
                                    <MapPin className="w-6 h-6 text-blue-300" />
                                    Gestion des zones
                                </h3>
                                <p className="text-sm font-bold text-slate-300 mt-1">
                                    Les zones servent à ranger, transférer, compter et geler le stock pendant inventaire.
                                </p>
                            </div>
                            <button onClick={() => setShowLocationManagerModal(false)} className="p-2 rounded-xl bg-white/10 hover:bg-white/20 text-white">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] overflow-hidden">
                            <form onSubmit={handleCreateManagedLocation} className="p-6 border-r border-slate-100 bg-slate-50 space-y-4">
                                <div>
                                    <p className="text-xs uppercase tracking-widest font-black text-slate-400">Créer une zone</p>
                                    <p className="text-sm font-bold text-slate-600 mt-1">
                                        {locationForm.parent_id
                                            ? `Sous-zone de ${locations.find(location => String(location.id) === String(locationForm.parent_id))?.name || 'la zone sélectionnée'}`
                                            : 'Créez une zone principale directement exploitable par réception, transfert et inventaire.'}
                                    </p>
                                </div>
                                <label className="block space-y-1">
                                    <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Nom</span>
                                    <input
                                        ref={locationNameInputRef}
                                        value={locationForm.name}
                                        onChange={event => setLocationForm(prev => ({ ...prev, name: event.target.value }))}
                                        placeholder={locationForm.parent_id ? "Ex: Étagère 1, Casier A, Niveau bas" : "Ex: Rack ALU A"}
                                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-black outline-none focus:ring-2 focus:ring-blue-500"
                                    />
                                </label>
                                <label className="block space-y-1">
                                    <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Parent</span>
                                    <select
                                        value={locationForm.parent_id}
                                        onChange={event => {
                                            const parent = locations.find(location => String(location.id) === event.target.value);
                                            setLocationForm(prev => ({ ...prev, parent_id: event.target.value, usage: parent?.usage || prev.usage }));
                                        }}
                                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                    >
                                        <option value="">Zone principale</option>
                                        {locations.map(location => (
                                            <option key={location.id} value={location.id}>{getFullLocationName(location)}</option>
                                        ))}
                                    </select>
                                </label>
                                <label className="block space-y-1">
                                    <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Type</span>
                                    <select
                                        value={locationForm.usage}
                                        onChange={event => setLocationForm(prev => ({ ...prev, usage: event.target.value }))}
                                        disabled={Boolean(locationForm.parent_id)}
                                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100 disabled:text-slate-400"
                                    >
                                        <option value="internal">Stock interne</option>
                                        <option value="production">Production atelier</option>
                                        <option value="supplier">Fournisseur virtuel</option>
                                        <option value="customer">Client virtuel</option>
                                        <option value="inventory">Inventaire virtuel</option>
                                    </select>
                                    {locationForm.parent_id && (
                                        <p className="text-xs font-bold text-slate-400">Une sous-zone hérite du type de son parent.</p>
                                    )}
                                </label>
                                <button
                                    type="submit"
                                    disabled={!locationForm.name.trim()}
                                    className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 text-white font-black"
                                >
                                    Créer la zone
                                </button>
                                <div className="rounded-2xl border border-amber-100 bg-amber-50 p-4 text-sm font-bold text-amber-800">
                                    Conseil : nommez les zones comme l’atelier parle réellement. Un opérateur doit pouvoir trouver la zone sans interprétation.
                                </div>
                            </form>

                            <div className="p-6 overflow-y-auto max-h-[70vh] space-y-4">
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <p className="text-xs uppercase tracking-widest font-black text-slate-400">Arborescence</p>
                                        <h4 className="text-xl font-black text-slate-900">Zones actives</h4>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => queryClient.invalidateQueries({ queryKey: ['locations'] })}
                                        className="px-3 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 text-xs font-black inline-flex items-center gap-2"
                                    >
                                        <RefreshCw className="w-4 h-4" />
                                        Actualiser
                                    </button>
                                </div>
                                <div className="space-y-2">
                                    {locations.filter(location => !location.parent_id).map(location => renderManagedLocationTree(location))}
                                    {locations.length === 0 && (
                                        <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center">
                                            <MapPin className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                                            <p className="font-black text-slate-500">Aucune zone active.</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
            {/* -------- TRANSFER POPUP -------- */}
            {showTransferModal && (
                <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-2xl shadow-2xl p-6 w-[400px] border border-slate-100">
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="font-black text-lg">Transfert <ArrowRight className="inline w-4 h-4 mx-1"/> Interne</h3>
                            <button onClick={()=>setShowTransferModal(false)} className="text-slate-400 hover:bg-slate-100 p-1.5 rounded"><X className="w-5 h-5"/></button>
                        </div>
                        <p className="text-sm font-bold text-slate-500 mb-4">{transferData.variant?.reference}</p>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase mb-1">Destination (Interne)</label>
                                <select
                                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                                    value={transferData.targetLocId} onChange={e=>setTransferData({...transferData, targetLocId: e.target.value})}
                                >
                                    <option value="">-- Choisir un emplacement --</option>
                                    {locations.filter(l => l.usage === 'internal').map(l => (
                                        <option key={l.id} value={l.id} disabled={l.id === transferData.sourceLocId}>{getFullLocationName(l)}</option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase mb-1">Quantité (Total Pces/M)</label>
                                <input
                                    type="number"
                                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 font-black text-2xl text-center outline-none focus:ring-2 focus:ring-blue-500"
                                    value={transferData.qty} onChange={e=>setTransferData({...transferData, qty: e.target.value})} placeholder="0"
                                    autoFocus
                                    onKeyDown={e => e.key === 'Enter' && submitTransfer()}
                                />
                            </div>
                            <button onClick={submitTransfer} className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 mt-2">
                                Valider Mouvement
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* -------- RECEPTION MODAL -------- */}
            {showReceptionModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100">
                        <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
                            <div className="w-12 h-12 rounded-full bg-emerald-100 flex items-center justify-center text-emerald-600 shadow-inner">
                                <Truck className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-black text-2xl text-slate-800">Entrée stock manuelle</h3>
                                <p className="text-sm font-medium text-slate-500">Initialiser ou corriger un stock hors bon fournisseur.</p>
                            </div>
                            <button onClick={()=>setShowReceptionModal(false)} className="ml-auto text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="space-y-5">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5 flex items-center justify-between">
                                    <span>Article à ajuster</span>
                                </label>
                                <div className="mb-2 relative">
                                    <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                                    <input
                                        type="text"
                                        placeholder="Rechercher (Nom, Réf, Gencod)..."
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 pl-10 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                                        value={receptionSearch}
                                        onChange={(e) => setReceptionSearch(e.target.value)}
                                    />
                                </div>
                                <select
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                                    onChange={e => {
                                        const v = products.flatMap(p => p.variants).find(vx => vx.id === parseInt(e.target.value));
                                        setReceptionData({...receptionData, variant: v});
                                    }}
                                    value={receptionData.variant?.id || ''}
                                >
                                    <option value="">-- Choisir parmi les résultats --</option>
                                    {products.map(p => {
                                        const filteredVariants = p.variants.filter(v =>
                                            !receptionSearch
                                            || p.name.toLowerCase().includes(receptionSearch.toLowerCase())
                                            || p.reference_base.toLowerCase().includes(receptionSearch.toLowerCase())
                                            || v.reference.toLowerCase().includes(receptionSearch.toLowerCase())
                                            || (v.barcode && v.barcode.includes(receptionSearch))
                                        );
                                        if (filteredVariants.length === 0) return null;
                                        return (
                                            <optgroup key={p.id} label={p.name}>
                                                {filteredVariants.map(v => <option key={v.id} value={v.id}>{v.reference} ({v.color || 'Std'})</option>)}
                                            </optgroup>
                                        );
                                    })}
                                </select>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Ranger dans le lieu</label>
                                    <select
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-emerald-500"
                                        value={receptionData.targetLocId} onChange={e=>setReceptionData({...receptionData, targetLocId: e.target.value})}
                                    >
                                        <option value="">- Dépôt Physique -</option>
                                        {locations.filter(l => l.usage === 'internal').map(l => (
                                            <option key={l.id} value={l.id}>{getFullLocationName(l)}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-emerald-500 uppercase tracking-widest mb-1.5">Quantité (Qté)</label>
                                    <input
                                        type="number"
                                        className="w-full bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-xl p-3 font-black text-2xl text-center outline-none focus:ring-2 focus:ring-emerald-500 shadow-inner placeholder-emerald-300"
                                        value={receptionData.qty} onChange={e=>setReceptionData({...receptionData, qty: e.target.value})} placeholder="0"
                                    />
                                </div>
                            </div>

                            <button onClick={submitReception} disabled={!receptionData.variant || !receptionData.targetLocId || !receptionData.qty} className="w-full py-4 mt-2 bg-emerald-600 disabled:bg-slate-300 disabled:cursor-not-allowed hover:bg-emerald-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 text-lg">
                                Valider l'entrée en stock
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* -------- CUSTOMER ISSUE MODAL -------- */}
            {showCustomerIssueModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-xl w-full border border-slate-100">
                        <div className="flex items-center gap-3 mb-6 border-b border-slate-100 pb-4">
                            <div className="w-12 h-12 rounded-full bg-slate-900 flex items-center justify-center text-white shadow-inner">
                                <ArrowRight className="w-6 h-6" />
                            </div>
                            <div>
                                <h3 className="font-black text-2xl text-slate-800">Sortie stock manuelle</h3>
                                <p className="text-sm font-medium text-slate-500">Débiter un stock hors devis/BL, avec motif obligatoire.</p>
                            </div>
                            <button onClick={()=>setShowCustomerIssueModal(false)} className="ml-auto text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 mb-5 text-sm font-bold text-amber-800">
                            Pour une vente signée, utilisez plutôt la fiche devis : elle créera la sortie client et le bon de livraison liés.
                            Cette sortie est réservée aux cas exceptionnels : casse, prélèvement client sans devis, régularisation ou don.
                        </div>

                        <div className="space-y-5">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">
                                    Article à sortir
                                </label>
                                <div className="mb-2 relative">
                                    <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                                    <input
                                        type="text"
                                        placeholder="Rechercher (Nom, Réf, Gencod)..."
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 pl-10 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-slate-900"
                                        value={customerIssueSearch}
                                        onChange={(e) => setCustomerIssueSearch(e.target.value)}
                                    />
                                </div>
                                <select
                                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-slate-900"
                                    onChange={e => {
                                        const v = products.flatMap(p => p.variants || []).find(vx => vx.id === parseInt(e.target.value));
                                        setCustomerIssueData({...customerIssueData, variant: v});
                                    }}
                                    value={customerIssueData.variant?.id || ''}
                                >
                                    <option value="">-- Choisir parmi les résultats --</option>
                                    {products
                                        .filter(p => (p.product_type || 'stockable').toLowerCase() !== 'service')
                                        .map(p => {
                                            const filteredVariants = (p.variants || []).filter(v =>
                                                !customerIssueSearch
                                                || p.name.toLowerCase().includes(customerIssueSearch.toLowerCase())
                                                || p.reference_base.toLowerCase().includes(customerIssueSearch.toLowerCase())
                                                || v.reference.toLowerCase().includes(customerIssueSearch.toLowerCase())
                                                || (v.barcode && v.barcode.includes(customerIssueSearch))
                                            );
                                            if (filteredVariants.length === 0) return null;
                                            return (
                                                <optgroup key={p.id} label={p.name}>
                                                    {filteredVariants.map(v => <option key={v.id} value={v.id}>{v.reference} ({v.color || 'Std'})</option>)}
                                                </optgroup>
                                            );
                                        })}
                                </select>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Sortir depuis</label>
                                    <select
                                        className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-slate-900"
                                        value={customerIssueData.sourceLocId} onChange={e=>setCustomerIssueData({...customerIssueData, sourceLocId: e.target.value})}
                                    >
                                        <option value="">- Emplacement physique -</option>
                                        {locations.filter(l => l.usage === 'internal').map(l => (
                                            <option key={l.id} value={l.id}>{getFullLocationName(l)}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-red-500 uppercase tracking-widest mb-1.5">Quantité à sortir</label>
                                    <input
                                        type="number"
                                        className="w-full bg-red-50 border border-red-200 text-red-700 rounded-xl p-3 font-black text-2xl text-center outline-none focus:ring-2 focus:ring-red-500 shadow-inner placeholder-red-300"
                                        value={customerIssueData.qty} onChange={e=>setCustomerIssueData({...customerIssueData, qty: e.target.value})} placeholder="0"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Motif obligatoire</label>
                                <textarea
                                    className="w-full min-h-[92px] bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-700 outline-none focus:ring-2 focus:ring-slate-900"
                                    value={customerIssueData.reason}
                                    onChange={e=>setCustomerIssueData({...customerIssueData, reason: e.target.value})}
                                    placeholder="Ex: remise client comptoir, casse constatée, régularisation inventaire..."
                                />
                            </div>

                            <button
                                onClick={submitCustomerIssue}
                                disabled={!customerIssueData.variant || !customerIssueData.sourceLocId || !customerIssueData.qty || !customerIssueData.reason.trim()}
                                className="w-full py-4 mt-2 bg-slate-900 disabled:bg-slate-300 disabled:cursor-not-allowed hover:bg-slate-800 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 text-lg"
                            >
                                <ArrowRight className="w-5 h-5" />
                                Valider la sortie stock
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* -------- EDIT PRODUCT MODAL -------- */}
            {showEditProductModal && editProductForm && (
                <div
                    className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                    onPaste={e => handlePaste(e, setEditProductForm, editProductForm)}
                >
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl">Modifier Famille</h3>
                            <button onClick={()=>setShowEditProductModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Réf Parent</label>
                                <input value={editProductForm.reference_base} onChange={e=>setEditProductForm({...editProductForm, reference_base: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Nom Long</label>
                                <input value={editProductForm.name} onChange={e=>setEditProductForm({...editProductForm, name: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Matière</label>
                                    <input value={editProductForm.material_type} onChange={e=>setEditProductForm({...editProductForm, material_type: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Unité</label>
                                    <input value={editProductForm.unit} onChange={e=>setEditProductForm({...editProductForm, unit: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Fournisseur</label>
                                    <input value={editProductForm.supplier} onChange={e=>setEditProductForm({...editProductForm, supplier: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Gammes Compatibles (Séparées par virgule)</label>
                                <input value={editProductForm.compatible_series} onChange={e=>setEditProductForm({...editProductForm, compatible_series: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" />
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Statut catalogue</label>
                                <select value={editProductForm.catalog_status} onChange={e=>setEditProductForm({...editProductForm, catalog_status: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700">
                                    <option value="DRAFT">Brouillon à qualifier</option>
                                    <option value="ACTIVE">Actif</option>
                                </select>
                            </div>
                            <div className="col-span-2 border-t border-slate-100 my-2 pt-4 flex gap-4">
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Type d'Article</label>
                                    <select value={editProductForm.product_type} onChange={e=>setEditProductForm({...editProductForm, product_type: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700">
                                        <option value="stockable">Article Stockable (Inventaire)</option>
                                        <option value="consumable">Consommable (Sans suivi fin)</option>
                                        <option value="service">Service (Pose, Main d'oeuvre)</option>
                                    </select>
                                </div>
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Image Produit (Optionnel)</label>
                                    <input type="file" accept="image/*" onChange={e => handleFileInput(e, setEditProductForm, editProductForm, 'image_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                    {editProductForm.image_url && <p className="text-xs text-emerald-500 mt-1 font-bold">Image chargée ✓</p>}
                                </div>
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Fiche Technique (PDF)</label>
                                    <input type="file" accept="application/pdf,image/*" onChange={e => handleFileInput(e, setEditProductForm, editProductForm, 'technical_doc_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                    {editProductForm.technical_doc_url && <p className="text-xs text-blue-500 mt-1 font-bold">Doc chargée ✓</p>}
                                </div>
                            </div>
                            <div className="col-span-2 flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 mt-2 py-2">
                                <label className="flex items-center gap-3 cursor-pointer w-full">
                                    <input type="checkbox" checked={editProductForm.available_in_pos} onChange={e=>setEditProductForm({...editProductForm, available_in_pos: e.target.checked})} className="w-5 h-5 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                                    <span className="font-bold text-sm text-slate-700">Visible dans l'Application Vente (PDV)</span>
                                </label>
                            </div>

                        </div>
                        <button onClick={submitEditProduct} className="w-full mt-6 py-4 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-black text-lg shadow-lg">Enregistrer</button>
                    </div>
                </div>
            )}

            {/* -------- EDIT VARIANT MODAL -------- */}
            {showEditVariantModal && editVariantForm && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl">Modifier Variante</h3>
                            <button onClick={()=>setShowEditVariantModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-black text-emerald-500 mb-1 block">Référence Exacte (Interne)</label>
                                <input value={editVariantForm.reference} onChange={e=>setEditVariantForm({...editVariantForm, reference: e.target.value})} className="w-full p-3 bg-emerald-50 text-emerald-700 font-bold border border-emerald-200 rounded-xl" />
                            </div>
                            <div>
                                <label className="text-xs font-black text-blue-500 mb-1 block">Code Barre / EAN13</label>
                                <input value={editVariantForm.barcode} onChange={e=>setEditVariantForm({...editVariantForm, barcode: e.target.value})} className="w-full p-3 bg-blue-50 text-blue-700 font-mono border border-blue-200 rounded-xl" placeholder="Scanner..." />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Réf fournisseur</label>
                                    <input value={editVariantForm.supplier_reference} onChange={e=>setEditVariantForm({...editVariantForm, supplier_reference: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Longueur / unité</label>
                                    <input type="number" value={editVariantForm.length_per_unit} onChange={e=>setEditVariantForm({...editVariantForm, length_per_unit: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" placeholder="6500" />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Spécificités (Couleur, Sens, Finition...)</label>
                                <input list="specs-list" value={editVariantForm.color} onChange={e=>setEditVariantForm({...editVariantForm, color: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Prix Achat (€)</label>
                                    <input type="number" value={editVariantForm.cost_price} onChange={e=>setEditVariantForm({...editVariantForm, cost_price: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Seuil d'alerte (Qté)</label>
                                    <input type="number" value={editVariantForm.min_threshold} onChange={e=>setEditVariantForm({...editVariantForm, min_threshold: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Emplacement cible</label>
                                <input value={editVariantForm.location} onChange={e=>setEditVariantForm({...editVariantForm, location: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" placeholder="Ex: Rack ALU A1" />
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Image Spécifique Variante (Optionnel)</label>
                                <input type="file" accept="image/*" onChange={e => handleFileInput(e, setEditVariantForm, editVariantForm, 'image_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                {editVariantForm.image_url && <p className="text-xs text-emerald-500 mt-1 font-bold">Image chargée ✓</p>}
                            </div>
                        </div>
                        <button onClick={submitEditVariant} className="w-full mt-6 py-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black text-lg shadow-lg mb-6">Enregistrer Modifications</button>

                        <div className="border-t border-slate-200 pt-6">
                            <ChatterWidget modelName="variant" recordId={editVariantForm.id} />
                        </div>
                    </div>
                </div>
            )}

            {/* -------- ADD VARIANT MODAL -------- */}
            {showAddVariantModal && addVariantForm && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100">
                        <div className="flex justify-between items-center mb-6">
                            <div>
                                <h3 className="font-black text-2xl">Nouvelle Déclinaison</h3>
                                <p className="text-sm font-bold text-slate-500">Pour : {addVariantForm.productName}</p>
                            </div>
                            <button onClick={()=>setShowAddVariantModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-black text-emerald-500 mb-1 block">Référence Exacte (Interne)</label>
                                <input autoFocus value={addVariantForm.reference} onChange={e=>setAddVariantForm({...addVariantForm, reference: e.target.value})} className="w-full p-3 bg-emerald-50 text-emerald-700 font-bold border border-emerald-200 rounded-xl" />
                            </div>
                            <div>
                                <label className="text-xs font-black text-blue-500 mb-1 block">Code Barre / EAN13</label>
                                <input value={addVariantForm.barcode} onChange={e=>setAddVariantForm({...addVariantForm, barcode: e.target.value})} className="w-full p-3 bg-blue-50 text-blue-700 font-mono border border-blue-200 rounded-xl" placeholder="Scanner..." />
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Spécificités (Couleur, Sens, Finition...)</label>
                                <input list="specs-list" value={addVariantForm.color} onChange={e=>setAddVariantForm({...addVariantForm, color: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" placeholder="Ex: RAL 9016 - GAUCHE" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Prix Achat (€)</label>
                                    <input type="number" value={addVariantForm.cost_price} onChange={e=>setAddVariantForm({...addVariantForm, cost_price: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Seuil d'alerte (Qté)</label>
                                    <input type="number" value={addVariantForm.min_threshold} onChange={e=>setAddVariantForm({...addVariantForm, min_threshold: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" />
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Image Spécifique Variante (Optionnel)</label>
                                <input type="file" accept="image/*" onChange={e => handleFileInput(e, setAddVariantForm, addVariantForm, 'image_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                {addVariantForm.image_url && <p className="text-xs text-emerald-500 mt-1 font-bold">Image chargée ✓</p>}
                            </div>
                        </div>
                        <button onClick={submitAddVariant} className="w-full mt-6 py-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black text-lg shadow-lg">Ajouter au catalogue</button>
                    </div>
                </div>
            )}

            {/* -------- NEW PRODUCT MODAL (QUICK) -------- */}
            {showNewProductModal && (
                <div
                    className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                    onPaste={e => handlePaste(e, setNewProductForm, newProductForm)}
                >
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-2xl w-full">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl">{newProductForm.product_type === 'service' ? 'Créer une Prestation' : 'Créer un Produit'}</h3>
                            <button onClick={()=>setShowNewProductModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="col-span-1">
                                <label className="text-xs font-black text-slate-400 mb-1 block">Réf Parent (ex: VEK-70)</label>
                                <input value={newProductForm.reference_base} onChange={e=>setNewProductForm({...newProductForm, reference_base: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" placeholder="Réf générique"/>
                            </div>
                            <div className="col-span-1">
                                <label className="text-xs font-black text-slate-400 mb-1 block">Nom Commercial / Description</label>
                                <input value={newProductForm.name} onChange={e=>setNewProductForm({...newProductForm, name: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" placeholder="Dormant 70mm..."/>
                            </div>

                            {/* Nouveaux Champs PIM : Catégorie, Unité, Fournisseur */}
                            <div className="col-span-1">
                                <label className="text-xs font-black text-slate-400 mb-1 block">{newProductForm.product_type === 'service' ? 'Famille prestation' : 'Catégorie Matériau'}</label>
                                <select value={newProductForm.material_type} onChange={e=>setNewProductForm({...newProductForm, material_type: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700">
                                    <option value="">Sélectionner...</option>
                                    {newProductForm.product_type === 'service' && <option value="SERVICE">SERVICE</option>}
                                    {appConfigs.filter(c => c.category === 'material').map(c => (
                                        <option key={c.id} value={c.value}>{c.value}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="col-span-1 grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Unité de Mesure</label>
                                    <select value={newProductForm.unit} onChange={e=>setNewProductForm({...newProductForm, unit: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700">
                                        <option value="">Sélectionner...</option>
                                        {newProductForm.product_type === 'service' && (
                                            <>
                                                <option value="forfait">forfait</option>
                                                <option value="heure">heure</option>
                                                <option value="jour">jour</option>
                                                <option value="ml">ml</option>
                                                <option value="u">u</option>
                                            </>
                                        )}
                                        {appConfigs.filter(c => c.category === 'unit').map(c => (
                                            <option key={c.id} value={c.value}>{c.value}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Fournisseur (opt.)</label>
                                    {/* Pour le fournisseur on laisse libre ou on propose le dictionnaire via Datalist */}
                                    <input list="supplier-list" value={newProductForm.supplier} onChange={e=>setNewProductForm({...newProductForm, supplier: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" placeholder="Cortizo..."/>
                                    <datalist id="supplier-list">
                                        {appConfigs.filter(c => c.category === 'supplier').map(c => (
                                            <option key={c.id} value={c.value} />
                                        ))}
                                    </datalist>
                                </div>
                            </div>

                            <div className="col-span-2 border-t border-slate-100 my-2 pt-4">
                                <label className="text-xs font-black text-slate-400 mb-1 block">Gammes Compatibles (Séparées par virgule, ex: COR 60, COR 70)</label>
                                <input value={newProductForm.compatible_series} onChange={e=>setNewProductForm({...newProductForm, compatible_series: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl" placeholder="Applicable pour quelles gammes ?"/>
                            </div>

                            <div className="col-span-2 border-t border-slate-100 my-2 pt-4 flex gap-4">
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Type d'Article</label>
                                    <select
                                        value={newProductForm.product_type}
                                        onChange={e => {
                                            const nextType = e.target.value;
                                            setNewProductForm({
                                                ...newProductForm,
                                                product_type: nextType,
                                                material_type: nextType === 'service' ? 'SERVICE' : newProductForm.material_type,
                                                unit: nextType === 'service' ? 'forfait' : newProductForm.unit,
                                                supplier: nextType === 'service' ? 'MMG' : newProductForm.supplier,
                                                min_threshold: nextType === 'service' ? 0 : newProductForm.min_threshold,
                                                compatible_series: nextType === 'service' ? 'Prestation devis libre' : newProductForm.compatible_series
                                            });
                                        }}
                                        className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700"
                                    >
                                        <option value="stockable">Article Stockable (Inventaire)</option>
                                        <option value="consumable">Consommable (Sans suivi fin)</option>
                                        <option value="service">Prestation (hors stock)</option>
                                    </select>
                                </div>
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Image Produit (Optionnel)</label>
                                    <input type="file" accept="image/*" onChange={e => handleFileInput(e, setNewProductForm, newProductForm, 'image_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                    {newProductForm.image_url && <p className="text-xs text-emerald-500 mt-1 font-bold">Image chargée ✓</p>}
                                </div>
                                <div className="flex-1">
                                    <label className="text-xs font-black text-slate-400 mb-1 block">Fiche Technique (PDF)</label>
                                    <input type="file" accept="application/pdf,image/*" onChange={e => handleFileInput(e, setNewProductForm, newProductForm, 'technical_doc_url')} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-xl" />
                                    {newProductForm.technical_doc_url && <p className="text-xs text-blue-500 mt-1 font-bold">Doc chargée ✓</p>}
                                </div>
                            </div>
                            <div className="col-span-2 flex items-center bg-slate-50 border border-slate-200 rounded-xl px-4 mt-2 py-2">
                                <label className="flex items-center gap-3 cursor-pointer w-full">
                                    <input type="checkbox" checked={newProductForm.available_in_pos} onChange={e=>setNewProductForm({...newProductForm, available_in_pos: e.target.checked})} className="w-5 h-5 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                                    <span className="font-bold text-sm text-slate-700">Visible dans l'Application Vente (PDV)</span>
                                </label>
                            </div>

                            <div className="col-span-2 border-t border-slate-100 my-2 pt-4">
                                <label className="text-xs font-black text-emerald-500 mb-1 block">{newProductForm.product_type === 'service' ? 'Référence prestation' : 'Déclinaison Initiale (Réf Interne)'}</label>
                                <input value={newProductForm.variant_ref} onChange={e=>setNewProductForm({...newProductForm, variant_ref: e.target.value})} className="w-full p-3 bg-emerald-50 text-emerald-700 font-bold border border-emerald-200 rounded-xl" placeholder={newProductForm.product_type === 'service' ? 'SERV-POSE-001' : 'VEK-70-BLANC'}/>
                            </div>

                            <div className="col-span-1">
                                <label className="text-xs font-black text-blue-500 mb-1 block">Code Barre / EAN13</label>
                                <input value={newProductForm.barcode} onChange={e=>setNewProductForm({...newProductForm, barcode: e.target.value})} className="w-full p-3 bg-blue-50 text-blue-700 font-mono border border-blue-200 rounded-xl" placeholder="Scanner ici..."/>
                            </div>

                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Spécificités (Couleur, Sens, Finition...)</label>
                                <input list="specs-list" value={newProductForm.color} onChange={e=>setNewProductForm({...newProductForm, color: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl uppercase" placeholder="Ex: ANODISÉ - DROIT"/>
                                <datalist id="specs-list">
                                        {appConfigs.filter(c => c.category === 'specs').map(c => (
                                            <option key={c.id} value={c.value} />
                                        ))}
                                </datalist>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">{newProductForm.product_type === 'service' ? 'Prix HT conseillé (€)' : 'Prix Achat (€)'}</label>
                                <input type="number" value={newProductForm.cost_price} onChange={e=>setNewProductForm({...newProductForm, cost_price: e.target.value})} className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono" placeholder={newProductForm.product_type === 'service' ? '80.00' : '45.50'}/>
                            </div>
                        </div>
                        <button onClick={handleQuickCreateProduct} className="w-full mt-6 py-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black text-lg shadow-lg">{newProductForm.product_type === 'service' ? 'Enregistrer la prestation' : 'Enregistrer et Continuer'}</button>
                    </div>
                </div>
            )}

            {/* -------- WORKSHOP DEBIT RESERVATION MODAL -------- */}
            {showWorkshopDebitModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-4xl w-full border border-slate-100">
                        <div className="flex justify-between items-start mb-6">
                            <div>
                                <h3 className="font-black text-2xl flex items-center gap-2">
                                    <ArrowRight className="w-6 h-6 text-amber-500" />
                                    Réservation débit atelier
                                </h3>
                                <p className="text-sm font-bold text-slate-500 mt-1">Progers TXT, Orgadata Débit optimisé PDF</p>
                            </div>
                            <button onClick={()=>setShowWorkshopDebitModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="grid grid-cols-3 gap-4 mb-5">
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Contexte workflow</label>
                                <select
                                    value={workshopContextValue}
                                    onChange={e => {
                                        setWorkshopContextValue(e.target.value);
                                        setWorkshopPreview(null);
                                    }}
                                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700"
                                >
                                    <option value="">Sélectionner...</option>
                                    {(workshopContexts.sales || []).map(s => (
                                        <option key={`sale-${s.id}`} value={`sale:${s.id}`}>
                                            Devis - {s.label}{s.is_reservable ? "" : " (prévisualisation)"}
                                        </option>
                                    ))}
                                    {(workshopContexts.production_orders || []).map(o => (
                                        <option key={`production-${o.id}`} value={`production:${o.id}`}>
                                            Atelier - {o.label}
                                        </option>
                                    ))}
                                </select>
                                {(workshopContexts.sales || []).length === 0 && (workshopContexts.production_orders || []).length === 0 && (
                                    <p className="text-xs font-bold text-amber-600 mt-2">
                                        Aucun contexte trouvé. La prévisualisation reste possible sans réservation.
                                    </p>
                                )}
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Emplacement source</label>
                                <select
                                    value={effectiveWorkshopSourceLocation}
                                    onChange={e => {
                                        setWorkshopSourceLocation(e.target.value);
                                        setWorkshopPreview(null);
                                    }}
                                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700"
                                >
                                    {internalLocations.map(l => (
                                        <option key={l.id} value={l.name}>{l.name}</option>
                                    ))}
                                </select>
                                <p className="text-[10px] font-bold text-slate-400 mt-1">La réservation sera ancrée sur cet emplacement.</p>
                            </div>
                            <div>
                                <label className="text-xs font-black text-slate-400 mb-1 block">Fichiers atelier</label>
                                <input
                                    type="file"
                                    multiple
                                    accept=".txt,.pdf"
                                    onChange={e => {
                                        setWorkshopFiles(Array.from(e.target.files || []));
                                        setWorkshopPreview(null);
                                    }}
                                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-bold text-slate-700"
                                />
                            </div>
                        </div>

                        <div className="flex gap-3 mb-6">
                            <button
                                onClick={submitWorkshopPreview}
                                disabled={workshopLoading || workshopFiles.length === 0}
                                className="px-5 py-3 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white rounded-xl font-black shadow-lg"
                            >
                                {workshopLoading ? "Analyse..." : "Prévisualiser"}
                            </button>
                            <button
                                onClick={submitWorkshopReservation}
                                disabled={workshopLoading || !workshopPreview}
                                className="px-5 py-3 bg-amber-500 hover:bg-amber-400 disabled:opacity-40 text-white rounded-xl font-black shadow-lg"
                            >
                                Réserver le stock
                            </button>
                            {workshopPreview && (workshopPreview.summary.stock_match_status?.not_found || 0) > 0 && (
                                <button
                                    onClick={createWorkshopDraftProducts}
                                    disabled={workshopLoading}
                                    className="px-5 py-3 bg-red-50 hover:bg-red-100 disabled:opacity-40 text-red-700 border border-red-200 rounded-xl font-black"
                                >
                                    Créer brouillons catalogue
                                </button>
                            )}
                        </div>

                        {workshopPreview && (
                            <div className="grid grid-cols-4 gap-3">
                                {workshopPreview.issues?.length > 0 && (
                                    <div className="col-span-4 bg-amber-50 border border-amber-200 rounded-2xl p-4">
                                        <p className="text-xs font-black text-amber-700 uppercase mb-2">Contrôles workflow</p>
                                        <div className="space-y-1">
                                            {workshopPreview.issues.map((issue, idx) => (
                                                <p key={idx} className={`text-sm font-bold ${issue.severity === 'error' ? 'text-red-700' : 'text-amber-700'}`}>
                                                    {issue.message || issue.code}
                                                </p>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4">
                                    <span className="text-[10px] font-black text-slate-400 uppercase">Lignes</span>
                                    <p className="text-2xl font-black text-slate-900">{workshopPreview.summary.debit_lines || 0}</p>
                                </div>
                                <div className="bg-emerald-50 border border-emerald-100 rounded-2xl p-4">
                                    <span className="text-[10px] font-black text-emerald-600 uppercase">OK</span>
                                    <p className="text-2xl font-black text-emerald-700">{workshopPreview.summary.stock_match_status?.ok || 0}</p>
                                </div>
                                <div className="bg-red-50 border border-red-100 rounded-2xl p-4">
                                    <span className="text-[10px] font-black text-red-600 uppercase">Inconnues</span>
                                    <p className="text-2xl font-black text-red-700">{workshopPreview.summary.stock_match_status?.not_found || 0}</p>
                                </div>
                                <div className="bg-orange-50 border border-orange-100 rounded-2xl p-4">
                                    <span className="text-[10px] font-black text-orange-600 uppercase">Manques</span>
                                    <p className="text-2xl font-black text-orange-700">{workshopPreview.summary.stock_match_status?.shortage || 0}</p>
                                </div>

                                <div className="col-span-4 border border-slate-200 rounded-2xl overflow-hidden max-h-80 overflow-y-auto">
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
                                            {workshopPreview.stock_matches?.map((line, idx) => (
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
                </div>
            )}

            {/* -------- IMPORT EXCEL MODAL -------- */}
            {showImportModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl p-8 max-w-lg w-full border border-slate-100 flex flex-col items-center">
                        <div className="w-full flex justify-between items-center mb-6">
                            <h3 className="font-black text-2xl flex items-center gap-2">
                                <FileText className="w-6 h-6 text-slate-800" />
                                Import de Masse (PIM)
                            </h3>
                            <button onClick={()=>setShowImportModal(false)} className="bg-slate-100 hover:bg-slate-200 p-2 rounded-full text-slate-500"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 mb-8 w-full">
                            <p className="text-sm font-medium text-slate-600 mb-4 font-sans">
                                Générez et remplissez le template officiel pour importer de multiples familles de produits et leurs déclinaisons instantanément.
                            </p>
                            <button type="button" onClick={downloadPimTemplate} className="w-full inline-flex font-bold justify-center items-center gap-2 py-3 bg-white border border-slate-300 shadow-sm hover:bg-slate-50 rounded-xl text-slate-700 transition-colors">
                                Télécharger le Template (.xlsx)
                            </button>
                        </div>

                        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 mb-8 w-full">
                            <p className="text-sm font-bold text-amber-800 mb-3">
                                Exporter les brouillons catalogue, les compléter, puis réimporter le fichier sans toucher aux quantités.
                            </p>
                            <button type="button" onClick={downloadDraftCatalogExport} className="w-full inline-flex font-bold justify-center items-center gap-2 py-3 bg-white border border-amber-200 shadow-sm hover:bg-amber-100 rounded-xl text-amber-800 transition-colors">
                                Télécharger les brouillons (.xlsx)
                            </button>
                            <form onSubmit={submitDraftCatalogImport} className="mt-4 space-y-3">
                                <label className="border-2 border-dashed border-amber-300 bg-white hover:bg-amber-50 transition-colors rounded-2xl flex flex-col items-center justify-center py-6 cursor-pointer group">
                                    <FileText className="w-8 h-8 text-amber-500 mb-2" />
                                    <span className="font-bold text-amber-800">{draftCatalogFile ? draftCatalogFile.name : "Sélectionner le fichier brouillons complété"}</span>
                                    <span className="text-xs text-amber-700/70 font-medium mt-1">MMG_Brouillons_Catalogue.xlsx</span>
                                    <input type="file" accept=".xlsx" className="hidden" onChange={(event) => setDraftCatalogFile(event.target.files?.[0] || null)} />
                                </label>
                                <button type="submit" disabled={!draftCatalogFile || draftCatalogImporting} className="w-full py-3 bg-amber-500 hover:bg-amber-400 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-xl font-black shadow-lg">
                                    {draftCatalogImporting ? "Import des brouillons..." : "Mettre à jour les brouillons"}
                                </button>
                            </form>
                        </div>

                        <form onSubmit={submitImportFile} className="w-full space-y-4 text-center">
                            <label className="border-2 border-dashed border-blue-300 bg-blue-50 hover:bg-blue-100 transition-colors rounded-2xl flex flex-col items-center justify-center py-10 cursor-pointer group">
                                <FileText className="w-10 h-10 text-blue-400 group-hover:text-blue-500 mb-3 transition-colors" />
                                <span className="font-bold text-blue-700">{massImportFile ? massImportFile.name : "Sélectionner un fichier PIM"}</span>
                                <span className="text-xs text-blue-500/70 font-medium mt-1">Format natif .xlsx</span>
                                <input type="file" accept=".xlsx" className="hidden" onChange={(event) => setMassImportFile(event.target.files?.[0] || null)} />
                            </label>

                            <button type="submit" disabled={!massImportFile} className="w-full py-4 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 disabled:cursor-not-allowed text-white rounded-xl font-black text-lg shadow-lg">Importer le template PIM</button>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

function StockRiskView({
    loading,
    needs,
    summary,
    criticalNeeds,
    blockedNeeds,
    coveredNeeds,
    longLeadTimeNeeds,
    onOpenPurchases,
    canCreatePurchaseRequest,
    riskActionVariantId,
    onCreatePurchaseRequest,
    onOpenProduct,
}) {
    const formatQty = value => Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
    const priorityLabel = priority => ({
        CRITICAL: 'Rupture',
        URGENT: 'Sous seuil',
        TO_PLAN: 'À planifier',
        COVERED: 'Couvert',
    }[String(priority || '').toUpperCase()] || 'À surveiller');
    const priorityClass = priority => ({
        CRITICAL: 'bg-red-100 text-red-700 border-red-200',
        URGENT: 'bg-amber-100 text-amber-700 border-amber-200',
        TO_PLAN: 'bg-blue-100 text-blue-700 border-blue-200',
        COVERED: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    }[String(priority || '').toUpperCase()] || 'bg-slate-100 text-slate-600 border-slate-200');
    const formatOrigins = origins => {
        const labels = {
            OUT_OF_STOCK: 'rupture',
            UNDER_MIN_THRESHOLD: 'seuil bas',
            ACTIVE_RESERVATIONS: 'réservations',
            OPEN_PURCHASE_ORDER: 'commande ouverte',
            OPEN_PURCHASE_REQUEST: "demande d'achat",
        };
        return (origins || []).map(origin => labels[origin] || origin).join(' · ') || 'stock à surveiller';
    };

    const sortedNeeds = [...(needs || [])].sort((a, b) => {
        const rank = { CRITICAL: 0, URGENT: 1, TO_PLAN: 2, COVERED: 3 };
        return (rank[a.priority] ?? 9) - (rank[b.priority] ?? 9)
            || Number(b.net_need_quantity || 0) - Number(a.net_need_quantity || 0)
            || String(a.supplier || '').localeCompare(String(b.supplier || ''));
    });

    return (
        <div className="mx-auto w-full max-w-7xl space-y-6">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.24em] text-red-500">Pilotage intelligent stock</p>
                    <h2 className="mt-1 text-3xl font-black tracking-tight text-slate-950">Stock à risque</h2>
                    <p className="mt-2 max-w-3xl text-sm font-bold text-slate-500">
                        Ruptures futures, seuils bas, fournisseurs bloquants, commandes entrantes et recommandations d'achat priorisées.
                    </p>
                </div>
                <div className="flex flex-wrap gap-3">
                    <button
                        type="button"
                        onClick={onOpenPurchases}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-black text-white shadow-sm hover:bg-slate-800"
                    >
                        <Truck className="h-4 w-4" />
                        Aller aux achats
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
                <RiskMetric title="Critiques" value={summary.critical_count || criticalNeeds.length} tone="red" detail="Disponible nul ou négatif" />
                <RiskMetric title="Sous seuil" value={summary.urgent_count || 0} tone="amber" detail="À sécuriser avant promesse" />
                <RiskMetric title="Bloqués" value={summary.blocked_count || blockedNeeds.length} tone="rose" detail="Fournisseur absent/bloqué" />
                <RiskMetric title="Couverts" value={summary.covered_count || coveredNeeds.length} tone="emerald" detail="Commande ou demande ouverte" />
                <RiskMetric title="Délai long" value={longLeadTimeNeeds.length} tone="blue" detail="Fournisseur >= 14 jours" />
            </div>

            <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[1fr_360px]">
                <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Priorités articles</p>
                            <h3 className="text-xl font-black text-slate-950">Références à sécuriser</h3>
                        </div>
                        <span className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-black text-slate-600">
                            {sortedNeeds.length} ligne(s)
                        </span>
                    </div>

                    {loading ? (
                        <div className="p-10 text-center text-sm font-black text-slate-400">Analyse des risques stock...</div>
                    ) : sortedNeeds.length === 0 ? (
                        <div className="p-10 text-center">
                            <Check className="mx-auto mb-3 h-10 w-10 text-emerald-400" />
                            <p className="font-black text-slate-700">Aucun stock à risque détecté.</p>
                            <p className="mt-1 text-sm font-bold text-slate-400">Les articles actifs semblent couverts par le stock et les approvisionnements.</p>
                        </div>
                    ) : (
                        <div className="divide-y divide-slate-100">
                            {sortedNeeds.map(need => (
                                <div key={need.variant_id} className="grid grid-cols-1 gap-4 px-5 py-4 xl:grid-cols-[1.2fr_140px_140px_150px_170px] xl:items-center">
                                    <div className="min-w-0">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className={`rounded-lg border px-2 py-1 text-[10px] font-black uppercase tracking-widest ${priorityClass(need.priority)}`}>
                                                {priorityLabel(need.priority)}
                                            </span>
                                            {need.supplier_status === 'BLOCKED' && (
                                                <span className="rounded-lg border border-red-200 bg-red-50 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-red-700">
                                                    fournisseur bloqué
                                                </span>
                                            )}
                                            {Number(need.supplier_lead_time_days || 0) > 0 && (
                                                <span className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                                    {need.supplier_lead_time_days} j
                                                </span>
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => onOpenProduct?.(need.product_id)}
                                            className="mt-2 block text-left text-base font-black text-slate-950 hover:text-blue-700"
                                        >
                                            {need.product_name}
                                        </button>
                                        <p className="mt-1 text-xs font-mono font-black text-slate-400">{need.reference}</p>
                                        <p className="mt-2 text-xs font-bold text-slate-500">{need.reason || formatOrigins(need.origins)}</p>
                                    </div>

                                    <RiskQty label="Disponible" value={need.available_quantity} tone={Number(need.available_quantity || 0) <= 0 ? 'red' : 'slate'} />
                                    <RiskQty label="Réservé" value={need.reserved_quantity} tone={Number(need.reserved_quantity || 0) > 0 ? 'amber' : 'slate'} />
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">À acheter net</p>
                                        <p className="mt-1 text-lg font-black text-slate-950">{formatQty(need.net_need_quantity)}</p>
                                        <p className="text-[11px] font-bold text-slate-400">suggéré {formatQty(need.suggested_quantity)}</p>
                                    </div>
                                    <div className="space-y-2">
                                        <p className="truncate text-xs font-black uppercase tracking-widest text-slate-400">{need.supplier || 'Sans fournisseur'}</p>
                                        <p className="text-xs font-bold text-slate-500">{need.blocked_reason || need.recommended_action}</p>
                                        {need.is_orderable && Number(need.net_need_quantity || 0) > 0 ? (
                                            <button
                                                type="button"
                                                onClick={() => onCreatePurchaseRequest?.(need)}
                                                disabled={!canCreatePurchaseRequest || riskActionVariantId === need.variant_id}
                                                className="w-full rounded-xl bg-emerald-600 px-3 py-2 text-xs font-black text-white hover:bg-emerald-500 disabled:bg-slate-300 disabled:text-slate-500"
                                            >
                                                {riskActionVariantId === need.variant_id ? 'Création...' : "Créer demande d'achat"}
                                            </button>
                                        ) : (
                                            <button
                                                type="button"
                                                onClick={onOpenPurchases}
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 hover:bg-slate-50"
                                            >
                                                Corriger / suivre
                                            </button>
                                        )}
                                        {need.is_orderable && !canCreatePurchaseRequest && (
                                            <p className="text-[11px] font-bold text-amber-600">Permission achats requise.</p>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </section>

                <aside className="space-y-4">
                    <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
                        <p className="text-[10px] font-black uppercase tracking-widest text-amber-700">Lecture métier</p>
                        <h3 className="mt-1 text-lg font-black text-slate-950">Ce que le système surveille</h3>
                        <div className="mt-4 space-y-3 text-sm font-bold text-amber-900">
                            <p>Stock disponible sous le seuil mini ou à zéro.</p>
                            <p>Quantités déjà réservées pour ventes ou atelier.</p>
                            <p>Commandes fournisseur et demandes d'achat déjà ouvertes.</p>
                            <p>Fournisseurs absents, bloqués ou avec délai long.</p>
                        </div>
                    </section>

                    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Approvisionnement</p>
                        <h3 className="mt-1 text-lg font-black text-slate-950">Couverture achats</h3>
                        <div className="mt-4 grid grid-cols-2 gap-3">
                            <RiskMini label="Entrant fournisseur" value={summary.incoming_purchase_quantity} />
                            <RiskMini label="Demandes achat" value={summary.open_purchase_request_quantity} />
                            <RiskMini label="Quantité suggérée" value={summary.suggested_quantity} />
                            <RiskMini label="Fournisseurs" value={summary.suppliers_count} />
                        </div>
                    </section>
                </aside>
            </div>
        </div>
    );
}

function RiskMetric({ title, value, detail, tone }) {
    const toneClass = {
        red: 'border-red-200 bg-red-50 text-red-700',
        amber: 'border-amber-200 bg-amber-50 text-amber-700',
        rose: 'border-rose-200 bg-rose-50 text-rose-700',
        emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
        blue: 'border-blue-200 bg-blue-50 text-blue-700',
    }[tone] || 'border-slate-200 bg-white text-slate-700';
    return (
        <div className={`rounded-2xl border p-5 shadow-sm ${toneClass}`}>
            <p className="text-[10px] font-black uppercase tracking-widest opacity-80">{title}</p>
            <p className="mt-2 text-3xl font-black">{Number(value || 0).toLocaleString('fr-FR')}</p>
            <p className="mt-1 text-xs font-bold opacity-80">{detail}</p>
        </div>
    );
}

function RiskQty({ label, value, tone }) {
    const valueClass = tone === 'red' ? 'text-red-600' : tone === 'amber' ? 'text-amber-600' : 'text-slate-950';
    return (
        <div>
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className={`mt-1 text-lg font-black ${valueClass}`}>{Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 })}</p>
        </div>
    );
}

function RiskMini({ label, value }) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</p>
            <p className="mt-1 text-lg font-black text-slate-950">{Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 })}</p>
        </div>
    );
}

function StockTodoView({
    userRole,
    isManager,
    isAdmin,
    permissions,
    roleFilter,
    setRoleFilter,
    counts,
    lowStockVariants,
    draftProducts,
    reservations,
    openInventorySessions,
    openPurchases,
    recentManualAdjustments,
    actions,
    reservationActionId,
}) {
    const roleTabs = [
        { id: 'me', label: 'Mes actions', helper: 'priorités utiles à mon profil' },
        { id: 'stock', label: 'Magasin', helper: 'ruptures, réceptions, transferts' },
        { id: 'atelier', label: 'Atelier', helper: 'réservations et débits réels' },
        { id: 'catalogue', label: 'Catalogue', helper: 'fiches à qualifier' },
        { id: 'achats', label: 'Achats', helper: 'commandes à recevoir' },
        { id: 'manager', label: 'Pilotage', helper: 'inventaire, audit, anomalies' },
    ];

    const normalizedRole = String(userRole || '').toUpperCase();
    const isPersonalMatch = itemRole => {
        if (isAdmin || isManager) return true;
        if (normalizedRole.includes('ATELIER')) return itemRole === 'atelier';
        if (normalizedRole.includes('PURCHASE') || normalizedRole.includes('ACHAT')) return itemRole === 'achats';
        return ['stock', 'catalogue'].includes(itemRole);
    };

    const formatDate = value => {
        if (!value) return 'Date non prévue';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return 'Date non prévue';
        return date.toLocaleDateString('fr-FR');
    };

    const cards = [
        {
            id: 'low-stock',
            role: 'stock',
            priority: counts.lowStock > 0 ? 'urgent' : 'ok',
            icon: AlertTriangle,
            title: 'Ruptures / seuils bas',
            metric: counts.lowStock,
            subtitle: counts.lowStock > 0 ? 'Variantes à sécuriser avant promesse client ou atelier.' : 'Aucune rupture visible.',
            actionLabel: 'Voir les ruptures',
            onAction: actions.showLowStock,
            canAct: true,
        },
        {
            id: 'reservations',
            role: 'atelier',
            priority: counts.reservations > 0 ? 'warning' : 'ok',
            icon: ArrowRight,
            title: 'Débits atelier à confirmer',
            metric: counts.reservations,
            subtitle: counts.reservations > 0 ? 'Stock réservé virtuellement, en attente de débit réel atelier.' : 'Aucune réservation atelier ouverte.',
            actionLabel: 'Ouvrir débit atelier',
            onAction: actions.openWorkshopDebit,
            canAct: permissions.reserveWorkshop,
        },
        {
            id: 'drafts',
            role: 'catalogue',
            priority: counts.drafts > 0 ? 'warning' : 'ok',
            icon: FileEdit,
            title: 'Fiches à qualifier',
            metric: counts.drafts,
            subtitle: counts.drafts > 0 ? 'Références créées sans fiche complète ni stock exploitable.' : 'Catalogue qualifié.',
            actionLabel: 'Qualifier les fiches',
            onAction: actions.showDrafts,
            canAct: permissions.qualifyCatalog,
        },
        {
            id: 'inventory',
            role: 'manager',
            priority: counts.inventory > 0 ? 'normal' : 'ok',
            icon: ClipboardCheck,
            title: 'Inventaires ouverts',
            metric: counts.inventory,
            subtitle: counts.inventory > 0 ? `${counts.inventoryIssues || 0} écart(s) ou ligne(s) à surveiller.` : 'Aucune campagne ouverte.',
            actionLabel: 'Ouvrir inventaire',
            onAction: actions.openPhysicalInventory,
            canAct: permissions.countInventory || permissions.validateInventory,
        },
        {
            id: 'purchases',
            role: 'achats',
            priority: counts.purchases > 0 ? 'normal' : 'ok',
            icon: Truck,
            title: 'Réceptions fournisseur',
            metric: counts.purchases,
            subtitle: counts.purchases > 0 ? 'Commandes fournisseur en attente ou partielles.' : 'Rien à réceptionner.',
            actionLabel: 'Aller aux achats',
            onAction: actions.openPurchases,
            canAct: permissions.receivePurchases,
        },
    ];

    const visibleCards = cards.filter(card => roleFilter === 'me' ? isPersonalMatch(card.role) : card.role === roleFilter);
    const visibleLowStock = roleFilter === 'me' || roleFilter === 'stock' ? lowStockVariants.slice(0, 5) : [];
    const visibleReservations = roleFilter === 'me' || roleFilter === 'atelier' ? reservations.slice(0, 5) : [];
    const visibleDrafts = roleFilter === 'me' || roleFilter === 'catalogue' ? draftProducts.slice(0, 5) : [];
    const visiblePurchases = roleFilter === 'me' || roleFilter === 'achats' ? openPurchases.slice(0, 5) : [];
    const visibleInventory = roleFilter === 'me' || roleFilter === 'manager' ? openInventorySessions.slice(0, 4) : [];
    const hasDetailedActions = visibleLowStock.length || visibleReservations.length || visibleDrafts.length || visiblePurchases.length || visibleInventory.length;

    const priorityClasses = {
        urgent: 'border-red-200 bg-red-50 text-red-700',
        warning: 'border-amber-200 bg-amber-50 text-amber-700',
        normal: 'border-blue-200 bg-blue-50 text-blue-700',
        ok: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };

    return (
        <div className="w-full space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.22em] text-blue-600 mb-2">File d'actions stock</p>
                    <h2 className="text-3xl font-black text-slate-900 tracking-tight">À traiter maintenant</h2>
                    <p className="text-sm font-bold text-slate-500 mt-1">
                        Les priorités sont regroupées par rôle pour éviter de chercher l'action dans le catalogue.
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button disabled={!permissions.receive} onClick={actions.openReception} className="px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-sm font-black shadow-sm inline-flex items-center gap-2">
                        <Truck className="w-4 h-4" />
                        Réceptionner
                    </button>
                    <button onClick={actions.openMovements} className="px-4 py-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-sm font-black inline-flex items-center gap-2">
                        <Layers className="w-4 h-4" />
                        Voir mouvements
                    </button>
                </div>
            </div>

            <div className="flex flex-wrap gap-2">
                {roleTabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setRoleFilter(tab.id)}
                        className={`px-4 py-3 rounded-2xl border text-left transition-all ${roleFilter === tab.id ? 'bg-slate-900 border-slate-900 text-white shadow-md' : 'bg-white border-slate-200 text-slate-600 hover:border-blue-200 hover:text-blue-700'}`}
                    >
                        <span className="block text-sm font-black">{tab.label}</span>
                        <span className={`block text-[10px] font-bold mt-0.5 ${roleFilter === tab.id ? 'text-white/60' : 'text-slate-400'}`}>{tab.helper}</span>
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
                {visibleCards.map(card => {
                    const Icon = card.icon;
                    return (
                        <button
                            key={card.id}
                            onClick={card.onAction}
                            disabled={!card.canAct}
                            className={`text-left rounded-2xl border p-4 shadow-sm hover:shadow-md transition-all disabled:opacity-60 disabled:cursor-not-allowed ${priorityClasses[card.priority]}`}
                        >
                            <div className="flex items-start justify-between gap-3">
                                <Icon className="w-5 h-5 shrink-0" />
                                <span className="text-3xl font-black leading-none">{card.metric}</span>
                            </div>
                            <h3 className="font-black text-slate-900 mt-4">{card.title}</h3>
                            <p className="text-xs font-bold text-slate-600 mt-1 min-h-[2.5rem]">{card.subtitle}</p>
                            <span className="inline-flex items-center gap-1 text-xs font-black mt-4">
                                {card.canAct ? card.actionLabel : 'Permission requise'}
                                <ArrowRight className="w-3.5 h-3.5" />
                            </span>
                        </button>
                    );
                })}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-5">
                <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                    <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
                        <div>
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Actions attendues</p>
                            <h3 className="font-black text-slate-900">Liste opérationnelle</h3>
                        </div>
                        <span className="text-xs font-black text-slate-400">{hasDetailedActions ? 'Priorisée automatiquement' : 'Rien d’urgent'}</span>
                    </div>
                    <div className="divide-y divide-slate-100">
                        {visibleReservations.map(reservation => (
                            <TodoRow
                                key={`rsv-${reservation.id}`}
                                badge="Atelier"
                                badgeClass="bg-amber-100 text-amber-700"
                                title={`Débit réel à confirmer ${reservation.reference || ''}`}
                                subtitle={reservation.order_reference || 'Réservation atelier active'}
                                meta={`${reservation.lines?.length || 0} ligne(s) réservée(s)`}
                                actionLabel="Débiter"
                                onAction={() => actions.consumeReservation(reservation)}
                                secondaryLabel="Annuler"
                                onSecondary={() => actions.cancelReservation(reservation)}
                                disabled={reservationActionId === reservation.id || !permissions.consumeWorkshop}
                                secondaryDisabled={reservationActionId === reservation.id || !permissions.reserveWorkshop}
                            />
                        ))}
                        {visibleLowStock.map(item => (
                            <TodoRow
                                key={`low-${item.variant.id}`}
                                badge="Magasin"
                                badgeClass="bg-red-100 text-red-700"
                                title={item.product.name}
                                subtitle={item.variant.reference}
                                meta={`Disponible ${item.availableQuantity} / seuil ${item.minThreshold}`}
                                actionLabel="Réceptionner"
                                onAction={actions.openReception}
                                disabled={!permissions.receive}
                            />
                        ))}
                        {visibleDrafts.map(product => (
                            <TodoRow
                                key={`draft-${product.id}`}
                                badge="Catalogue"
                                badgeClass="bg-amber-100 text-amber-700"
                                title={product.name}
                                subtitle={product.reference_base}
                                meta="Fiche incomplète avant exploitation stock"
                                actionLabel="Qualifier"
                                onAction={actions.showDrafts}
                                disabled={!permissions.qualifyCatalog}
                            />
                        ))}
                        {visiblePurchases.map(po => (
                            <TodoRow
                                key={`po-${po.id}`}
                                badge="Achats"
                                badgeClass="bg-blue-100 text-blue-700"
                                title={po.reference || `Commande #${po.id}`}
                                subtitle={po.supplier || 'Fournisseur non renseigné'}
                                meta={`Statut ${po.status || '-'} · prévu ${formatDate(po.expected_date)}`}
                                actionLabel="Ouvrir achats"
                                onAction={actions.openPurchases}
                                disabled={!permissions.receivePurchases}
                            />
                        ))}
                        {visibleInventory.map(session => (
                            <TodoRow
                                key={`inv-${session.id}`}
                                badge="Inventaire"
                                badgeClass="bg-indigo-100 text-indigo-700"
                                title={session.name || `Campagne #${session.id}`}
                                subtitle={session.zone_locked ? 'Zone gelée pendant comptage' : 'Campagne ouverte'}
                                meta={`Statut ${session.status || '-'}${session.lines?.length ? ` · ${session.lines.length} ligne(s)` : ''}`}
                                actionLabel="Ouvrir"
                                onAction={actions.openPhysicalInventory}
                                disabled={!permissions.countInventory && !permissions.validateInventory}
                            />
                        ))}
                        {!hasDetailedActions && (
                            <div className="p-10 text-center">
                                <Check className="w-10 h-10 mx-auto text-emerald-400 mb-3" />
                                <p className="font-black text-slate-700">Aucune action urgente pour cette vue.</p>
                                <p className="text-sm font-bold text-slate-400 mt-1">Le stock peut être consulté dans Articles & stock.</p>
                            </div>
                        )}
                    </div>
                </div>

                <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-200 bg-white p-5">
                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Règle d’usage</p>
                        <div className="space-y-3">
                            <RoleRule icon={Truck} title="Magasin" text="réceptionne, range, transfère et traite les ruptures." />
                            <RoleRule icon={ArrowRight} title="Atelier" text="confirme le débit réel seulement après réservation validée." />
                            <RoleRule icon={FileEdit} title="Catalogue" text="qualifie les brouillons avant toute exploitation stock." />
                            <RoleRule icon={ClipboardCheck} title="Manager" text="valide les inventaires, lit les écarts et audite les mouvements." />
                        </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-5">
                        <div className="flex items-center justify-between gap-3 mb-4">
                            <div>
                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Contrôle</p>
                                <h3 className="font-black text-slate-900">Derniers ajustements</h3>
                            </div>
                            {isAdmin && (
                                <button onClick={actions.openMovements} className="text-xs font-black text-blue-600 hover:text-blue-700">Audit</button>
                            )}
                        </div>
                        <div className="space-y-2">
                            {recentManualAdjustments.length > 0 ? recentManualAdjustments.map(tx => (
                                <div key={tx.id || tx.reference} className="rounded-xl bg-slate-50 border border-slate-100 p-3">
                                    <p className="font-black text-sm text-slate-800">{tx.item_name || tx.reference}</p>
                                    <p className="text-xs font-bold text-slate-500">{tx.business_reason || tx.source_screen || 'Mouvement inventaire'} · {formatDate(tx.created_at)}</p>
                                </div>
                            )) : (
                                <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-4 text-sm font-bold text-emerald-700">
                                    Aucun ajustement manuel récent à vérifier.
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function TodoRow({ badge, badgeClass, title, subtitle, meta, actionLabel, onAction, secondaryLabel, onSecondary, disabled = false, secondaryDisabled = disabled }) {
    return (
        <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 hover:bg-slate-50 transition-colors">
            <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-1 rounded-lg text-[10px] font-black uppercase ${badgeClass}`}>{badge}</span>
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Action attendue</span>
                </div>
                <p className="font-black text-slate-900 truncate">{title}</p>
                <p className="text-sm font-bold text-slate-500 truncate">{subtitle}</p>
                <p className="text-xs font-bold text-slate-400 mt-1">{meta}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
                {secondaryLabel && (
                    <button onClick={onSecondary} disabled={secondaryDisabled} className="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-400 text-slate-700 text-xs font-black">
                        {secondaryLabel}
                    </button>
                )}
                <button onClick={onAction} disabled={disabled} className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-xs font-black inline-flex items-center gap-2">
                    {actionLabel}
                    <ArrowRight className="w-3.5 h-3.5" />
                </button>
            </div>
        </div>
    );
}

function RoleRule({ icon: Icon, title, text }) {
    return (
        <div className="flex gap-3">
            <div className="w-9 h-9 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
                <Icon className="w-4 h-4" />
            </div>
            <div>
                <p className="font-black text-sm text-slate-900">{title}</p>
                <p className="text-xs font-bold text-slate-500">{text}</p>
            </div>
        </div>
    );
}

function PhysicalInventoryView({ sessions, products, locations, quants, canCount, canValidate, queryClient }) {
    const [selectedSessionId, setSelectedSessionId] = useState(sessions[0]?.id || null);
    const [newSession, setNewSession] = useState({ name: '', location_id: '', notes: '', include_all_variants: false, blind_counting: false });
    const [lineForm, setLineForm] = useState({ variant_id: '', location_id: '', counted_quantity: '', reason: '' });
    const [scanValue, setScanValue] = useState('');
    const [busy, setBusy] = useState(false);

    const internalLocations = locations.filter(location => location.usage === 'internal' && location.is_active !== false);
    const selectedSession = sessions.find(session => session.id === selectedSessionId) || sessions[0] || null;
    const selectedLocationId = selectedSession?.location_id || lineForm.location_id;
    const stockVariants = products
        .filter(product => (product.product_type || 'stockable') !== 'service')
        .flatMap(product => (product.variants || []).map(variant => ({
            ...variant,
            product_name: product.name,
            supplier: product.supplier,
            unit: product.unit,
        })));
    const selectedVariant = stockVariants.find(variant => String(variant.id) === String(lineForm.variant_id));
    const selectedLocation = internalLocations.find(location => String(location.id) === String(selectedLocationId));
    const expectedQuantity = selectedVariant && selectedLocation
        ? quants
            .filter(quant => quant.variant_id === selectedVariant.id && quant.location_id === selectedLocation.id)
            .reduce((sum, quant) => sum + Number(quant.quantity || 0), 0)
        : 0;
    const countedQuantity = lineForm.counted_quantity === '' ? null : Number(lineForm.counted_quantity);
    const variance = countedQuantity === null ? null : countedQuantity - expectedQuantity;
    const hasRecountLines = Boolean(selectedSession?.lines?.some(line => line.status === 'recount'));
    const hasPendingLines = Boolean(selectedSession?.lines?.some(line => line.status === 'pending'));
    const isBlindCounting = Boolean(selectedSession?.blind_counting && ['draft', 'counting'].includes(selectedSession?.status));
    const totalLines = selectedSession?.lines?.length || 0;
    const countedLines = (selectedSession?.lines || []).filter(line => line.status !== 'pending').length;

    const matchVariantFromScan = (value) => {
        const needle = value.trim().toLowerCase();
        if (!needle) return null;
        return stockVariants.find(variant => [
            variant.reference,
            variant.barcode,
            variant.supplier_reference,
            variant.product_name,
            variant.supplier,
        ].some(field => String(field || '').toLowerCase().includes(needle)));
    };

    const refreshInventory = async () => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['inventory-sessions'] }),
            queryClient.invalidateQueries({ queryKey: ['quants'] }),
            queryClient.invalidateQueries({ queryKey: ['products'] }),
            queryClient.invalidateQueries({ queryKey: ['transactions'] }),
        ]);
    };

    const createSession = async (event) => {
        event.preventDefault();
        if (!newSession.name.trim() || busy) return;
        setBusy(true);
        try {
            const payload = {
                name: newSession.name.trim(),
                location_id: newSession.location_id ? Number(newSession.location_id) : null,
                notes: newSession.notes || null,
                zone_locked: true,
                include_all_variants: newSession.include_all_variants,
                blind_counting: newSession.blind_counting,
            };
            const res = await api.post('/v2/stock/inventory-sessions', payload);
            setSelectedSessionId(res.data.id);
            setNewSession({ name: '', location_id: '', notes: '', include_all_variants: false, blind_counting: false });
            await refreshInventory();
        } catch (error) {
            alert(error.response?.data?.detail || "Création de campagne impossible.");
        } finally {
            setBusy(false);
        }
    };

    const submitLine = async (event) => {
        event.preventDefault();
        if (!selectedSession || !lineForm.variant_id || !selectedLocationId || lineForm.counted_quantity === '' || busy) return;
        setBusy(true);
        try {
            await api.post(`/v2/stock/inventory-sessions/${selectedSession.id}/lines`, {
                variant_id: Number(lineForm.variant_id),
                location_id: Number(selectedLocationId),
                counted_quantity: Number(lineForm.counted_quantity),
                reason: lineForm.reason || null,
            });
            setLineForm({ variant_id: '', location_id: selectedSession.location_id || '', counted_quantity: '', reason: '' });
            await refreshInventory();
        } catch (error) {
            alert(error.response?.data?.detail || "Saisie de comptage impossible.");
        } finally {
            setBusy(false);
        }
    };

    const handleScanSubmit = (event) => {
        event.preventDefault();
        const variant = matchVariantFromScan(scanValue);
        if (!variant) {
            alert("Référence introuvable dans le catalogue stock.");
            return;
        }
        setLineForm(prev => ({ ...prev, variant_id: String(variant.id) }));
        setScanValue(variant.reference || scanValue);
    };

    const focusLine = (line) => {
        setLineForm(prev => ({ ...prev, variant_id: String(line.variant_id), location_id: String(line.location_id) }));
        setScanValue(line.variant?.reference || '');
    };

    const requestRecount = async (line) => {
        if (!selectedSession || busy) return;
        const notes = window.prompt("Pourquoi demander un recompte ?", line.reason || "");
        if (notes === null) return;
        setBusy(true);
        try {
            await api.post(`/v2/stock/inventory-sessions/${selectedSession.id}/lines/${line.id}/recount`, { notes });
            await refreshInventory();
        } catch (error) {
            alert(error.response?.data?.detail || "Demande de recompte impossible.");
        } finally {
            setBusy(false);
        }
    };

    const exportSession = async () => {
        if (!selectedSession || busy) return;
        setBusy(true);
        try {
            const res = await api.get(`/v2/stock/inventory-sessions/${selectedSession.id}/export`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', `${selectedSession.reference}-rapport-inventaire.xlsx`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            alert(error.response?.data?.detail || "Export inventaire impossible.");
        } finally {
            setBusy(false);
        }
    };

    const validateSession = async () => {
        if (!selectedSession || busy) return;
        if (!window.confirm(`Valider ${selectedSession.reference} ? Les écarts créeront des mouvements d'ajustement stock.`)) return;
        setBusy(true);
        try {
            await api.post(`/v2/stock/inventory-sessions/${selectedSession.id}/validate`);
            await refreshInventory();
        } catch (error) {
            alert(error.response?.data?.detail || "Validation impossible.");
        } finally {
            setBusy(false);
        }
    };

    const cancelSession = async () => {
        if (!selectedSession || busy) return;
        if (!window.confirm(`Annuler ${selectedSession.reference} ? Aucun mouvement de stock ne sera créé.`)) return;
        setBusy(true);
        try {
            await api.post(`/v2/stock/inventory-sessions/${selectedSession.id}/cancel`);
            await refreshInventory();
        } catch (error) {
            alert(error.response?.data?.detail || "Annulation impossible.");
        } finally {
            setBusy(false);
        }
    };

    const statusLabel = {
        draft: 'Brouillon',
        counting: 'Comptage',
        validated: 'Validée',
        cancelled: 'Annulée',
    };
    const lineStatusLabel = {
        pending: 'À compter',
        ok: 'OK',
        variance: 'Écart',
        recount: 'À recompter',
        validated: 'Validé',
    };
    const lineStatusClass = {
        pending: 'bg-slate-50 text-slate-500 border-slate-200',
        ok: 'bg-emerald-50 text-emerald-700 border-emerald-100',
        variance: 'bg-amber-50 text-amber-700 border-amber-100',
        recount: 'bg-red-50 text-red-700 border-red-100',
        validated: 'bg-blue-50 text-blue-700 border-blue-100',
    };

    return (
        <div className="w-full space-y-6">
            <div className="bg-white border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-8 py-6 border-b border-slate-100 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                    <div>
                        <h3 className="text-2xl font-black text-slate-900 flex items-center gap-3">
                            <ClipboardCheck className="w-6 h-6 text-blue-600" />
                            Inventaire physique
                        </h3>
                        <p className="text-sm font-bold text-slate-500 mt-1">
                            Comptez le réel, justifiez les écarts, puis validez pour créer les ajustements stock.
                        </p>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="px-4 py-3 rounded-2xl bg-slate-50 border border-slate-200">
                            <p className="text-[10px] uppercase font-black tracking-widest text-slate-400">Campagnes</p>
                            <p className="text-xl font-black text-slate-900">{sessions.length}</p>
                        </div>
                        <div className="px-4 py-3 rounded-2xl bg-amber-50 border border-amber-100">
                            <p className="text-[10px] uppercase font-black tracking-widest text-amber-500">En cours</p>
                            <p className="text-xl font-black text-amber-700">{sessions.filter(s => ['draft', 'counting'].includes(s.status)).length}</p>
                        </div>
                        <div className="px-4 py-3 rounded-2xl bg-emerald-50 border border-emerald-100">
                            <p className="text-[10px] uppercase font-black tracking-widest text-emerald-500">Validées</p>
                            <p className="text-xl font-black text-emerald-700">{sessions.filter(s => s.status === 'validated').length}</p>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-[360px_1fr] min-h-[620px]">
                    <aside className="border-r border-slate-100 bg-slate-50/80 p-5 space-y-4">
                        <form onSubmit={createSession} className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm space-y-3">
                            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Nouvelle campagne</p>
                            <div className="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-[11px] font-black text-amber-700">
                                La zone sélectionnée sera gelée jusqu'à validation ou annulation.
                            </div>
                            <input
                                value={newSession.name}
                                onChange={event => setNewSession(prev => ({ ...prev, name: event.target.value }))}
                                placeholder="Ex: Comptage WH semaine 29"
                                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                disabled={!canValidate || busy}
                            />
                            <select
                                value={newSession.location_id}
                                onChange={event => setNewSession(prev => ({ ...prev, location_id: event.target.value }))}
                                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                disabled={!canValidate || busy}
                            >
                                <option value="">Tous emplacements internes</option>
                                {internalLocations.map(location => (
                                    <option key={location.id} value={location.id}>{location.name}</option>
                                ))}
                            </select>
                            <input
                                value={newSession.notes}
                                onChange={event => setNewSession(prev => ({ ...prev, notes: event.target.value }))}
                                placeholder="Note optionnelle"
                                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                disabled={!canValidate || busy}
                            />
                            <label className="flex items-start gap-2 text-xs font-bold text-slate-600 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={newSession.include_all_variants}
                                    onChange={event => setNewSession(prev => ({ ...prev, include_all_variants: event.target.checked }))}
                                    className="mt-0.5"
                                    disabled={!canValidate || busy}
                                />
                                <span>Inclure toutes les variantes actives (espéré 0) pour détecter les oublis</span>
                            </label>
                            <label className="flex items-start gap-2 text-xs font-bold text-slate-600 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={newSession.blind_counting}
                                    onChange={event => setNewSession(prev => ({ ...prev, blind_counting: event.target.checked }))}
                                    className="mt-0.5"
                                    disabled={!canValidate || busy}
                                />
                                <span>Comptage aveugle (espéré masqué jusqu'à validation)</span>
                            </label>
                            <button
                                type="submit"
                                disabled={!canValidate || busy || !newSession.name.trim()}
                                className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:bg-slate-300 text-white font-black text-sm"
                            >
                                Créer la campagne
                            </button>
                        </form>

                        <div className="space-y-2">
                            {sessions.map(session => {
                                const isSelected = selectedSession?.id === session.id;
                                return (
                                    <button
                                        key={session.id}
                                        onClick={() => setSelectedSessionId(session.id)}
                                        className={`w-full text-left rounded-2xl border p-4 transition-all ${isSelected ? 'bg-slate-900 text-white border-slate-900 shadow-lg' : 'bg-white text-slate-700 border-slate-200 hover:border-blue-200'}`}
                                    >
                                        <div className="flex justify-between gap-3">
                                            <p className="font-black text-sm">{session.name}</p>
                                            <span className={`text-[9px] font-black uppercase px-2 py-1 rounded-lg ${session.status === 'validated' ? 'bg-emerald-100 text-emerald-700' : session.status === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                                                {statusLabel[session.status] || session.status}
                                            </span>
                                        </div>
                                        <p className={`text-[11px] font-mono mt-1 ${isSelected ? 'text-slate-300' : 'text-slate-400'}`}>{session.reference}</p>
                                        <p className={`text-xs font-bold mt-2 ${isSelected ? 'text-slate-200' : 'text-slate-500'}`}>
                                            {session.location?.name || 'Tous emplacements'} - {session.lines?.length || 0} ligne(s)
                                        </p>
                                        {session.zone_locked && ['draft', 'counting'].includes(session.status) && (
                                            <p className={`text-[10px] font-black uppercase mt-2 ${isSelected ? 'text-amber-200' : 'text-amber-600'}`}>
                                                Zone gelée
                                            </p>
                                        )}
                                    </button>
                                );
                            })}
                            {sessions.length === 0 && (
                                <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-6 text-center text-sm font-bold text-slate-400">
                                    Aucune campagne créée.
                                </div>
                            )}
                        </div>
                    </aside>

                    <main className="p-6 space-y-5">
                        {!selectedSession ? (
                            <div className="h-full min-h-[420px] flex flex-col items-center justify-center text-center border-2 border-dashed border-slate-200 rounded-3xl">
                                <ClipboardCheck className="w-12 h-12 text-slate-300 mb-3" />
                                <p className="font-black text-slate-600">Créez une campagne pour commencer le comptage.</p>
                                <p className="text-sm text-slate-400 mt-1">Aucun stock n'est modifié avant validation.</p>
                            </div>
                        ) : (
                            <>
                                <div className="rounded-3xl border border-slate-200 bg-white p-5 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                                    <div>
                                        <p className="text-[10px] uppercase font-black tracking-widest text-slate-400">Campagne sélectionnée</p>
                                        <h4 className="text-xl font-black text-slate-900">{selectedSession.name}</h4>
                                        <p className="text-sm font-bold text-slate-500 mt-1">
                                            {selectedSession.reference} - {selectedSession.location?.name || 'Tous emplacements internes'}
                                        </p>
                                        <div className="flex flex-wrap gap-2 mt-3">
                                            <span className={`inline-flex items-center px-3 py-1 rounded-full text-[10px] uppercase font-black border ${selectedSession.zone_locked && ['draft', 'counting'].includes(selectedSession.status) ? 'bg-amber-50 text-amber-700 border-amber-100' : 'bg-slate-50 text-slate-500 border-slate-200'}`}>
                                                {selectedSession.zone_locked && ['draft', 'counting'].includes(selectedSession.status) ? 'Zone gelée' : 'Zone libérée'}
                                            </span>
                                            {selectedSession.blind_counting && (
                                                <span className="inline-flex items-center px-3 py-1 rounded-full text-[10px] uppercase font-black border bg-violet-50 text-violet-700 border-violet-100">
                                                    Comptage aveugle
                                                </span>
                                            )}
                                            {hasRecountLines && (
                                                <span className="inline-flex items-center px-3 py-1 rounded-full text-[10px] uppercase font-black border bg-red-50 text-red-700 border-red-100">
                                                    Recompte requis
                                                </span>
                                            )}
                                        </div>
                                        {totalLines > 0 && (
                                            <div className="mt-3 max-w-sm">
                                                <div className="flex justify-between text-[10px] uppercase font-black tracking-widest text-slate-400">
                                                    <span>Progression</span>
                                                    <span>{countedLines}/{totalLines} lignes comptées</span>
                                                </div>
                                                <div className="h-2 mt-1 rounded-full bg-slate-100 overflow-hidden">
                                                    <div
                                                        className={`h-full rounded-full transition-all ${countedLines === totalLines ? 'bg-emerald-500' : 'bg-blue-500'}`}
                                                        style={{ width: `${Math.round((countedLines / totalLines) * 100)}%` }}
                                                    />
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex gap-2">
                                        <button onClick={exportSession} disabled={!canValidate || busy || !selectedSession.lines?.length} title={!canValidate ? 'Réservé à la validation d\'inventaire' : undefined} className="px-4 py-3 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 font-black text-sm inline-flex items-center gap-2">
                                            <Download className="w-4 h-4" />
                                            Rapport
                                        </button>
                                        {['draft', 'counting'].includes(selectedSession.status) && (
                                            <>
                                                <button onClick={cancelSession} disabled={!canValidate || busy} className="px-4 py-3 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-50 font-black text-sm">
                                                    Annuler
                                                </button>
                                                <button onClick={validateSession} disabled={!canValidate || busy || !selectedSession.lines?.length || hasRecountLines || hasPendingLines} title={hasPendingLines ? 'Toutes les lignes doivent être comptées avant validation' : undefined} className="px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-300 text-white font-black text-sm">
                                                    Valider les écarts
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </div>

                                {['draft', 'counting'].includes(selectedSession.status) && (
                                    <form onSubmit={submitLine} className="rounded-3xl border border-blue-100 bg-blue-50/40 p-5 grid grid-cols-1 lg:grid-cols-[1.1fr_1.5fr_1fr_160px_1fr_auto] gap-3 items-end">
                                        <label className="space-y-1">
                                            <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Scan / recherche tablette</span>
                                            <input
                                                value={scanValue}
                                                onChange={event => setScanValue(event.target.value)}
                                                onKeyDown={event => {
                                                    if (event.key === 'Enter') {
                                                        event.preventDefault();
                                                        handleScanSubmit(event);
                                                    }
                                                }}
                                                placeholder="Scanner ou taper une réf."
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                                disabled={!canCount || busy}
                                            />
                                        </label>
                                        <label className="space-y-1">
                                            <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Article compté</span>
                                            <select
                                                value={lineForm.variant_id}
                                                onChange={event => setLineForm(prev => ({ ...prev, variant_id: event.target.value }))}
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                                disabled={!canCount || busy}
                                            >
                                                <option value="">Sélectionner une référence</option>
                                                {stockVariants.map(variant => (
                                                    <option key={variant.id} value={variant.id}>{variant.reference} - {variant.product_name}</option>
                                                ))}
                                            </select>
                                        </label>
                                        <label className="space-y-1">
                                            <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Emplacement</span>
                                            <select
                                                value={selectedSession.location_id || lineForm.location_id}
                                                onChange={event => setLineForm(prev => ({ ...prev, location_id: event.target.value }))}
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                                disabled={!canCount || busy || !!selectedSession.location_id}
                                            >
                                                <option value="">Choisir</option>
                                                {internalLocations.map(location => (
                                                    <option key={location.id} value={location.id}>{location.name}</option>
                                                ))}
                                            </select>
                                        </label>
                                        <label className="space-y-1">
                                            <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Compté</span>
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.01"
                                                value={lineForm.counted_quantity}
                                                onChange={event => setLineForm(prev => ({ ...prev, counted_quantity: event.target.value }))}
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-black outline-none focus:ring-2 focus:ring-blue-500"
                                                disabled={!canCount || busy}
                                            />
                                        </label>
                                        <label className="space-y-1">
                                            <span className="text-[10px] uppercase font-black tracking-widest text-slate-500">Motif écart</span>
                                            <input
                                                value={lineForm.reason}
                                                onChange={event => setLineForm(prev => ({ ...prev, reason: event.target.value }))}
                                                placeholder="Casse, erreur, retour..."
                                                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:ring-2 focus:ring-blue-500"
                                                disabled={!canCount || busy}
                                            />
                                        </label>
                                        <button
                                            type="submit"
                                            disabled={!canCount || busy || !lineForm.variant_id || !selectedLocationId || lineForm.counted_quantity === ''}
                                            className="px-5 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 text-white font-black text-sm"
                                        >
                                            Ajouter
                                        </button>
                                        {selectedVariant && selectedLocation && (
                                            <div className="lg:col-span-6 grid grid-cols-3 gap-3 text-sm">
                                                <div className="rounded-xl bg-white border border-slate-200 p-3">
                                                    <p className="text-[10px] uppercase font-black text-slate-400">Système</p>
                                                    <p className="text-xl font-black text-slate-900">{isBlindCounting ? '•••' : expectedQuantity.toLocaleString('fr-FR')}</p>
                                                </div>
                                                <div className="rounded-xl bg-white border border-slate-200 p-3">
                                                    <p className="text-[10px] uppercase font-black text-slate-400">Compté</p>
                                                    <p className="text-xl font-black text-slate-900">{countedQuantity === null ? '-' : countedQuantity.toLocaleString('fr-FR')}</p>
                                                </div>
                                                <div className={`rounded-xl border p-3 ${isBlindCounting ? 'bg-slate-50 border-slate-200' : variance === null || variance === 0 ? 'bg-emerald-50 border-emerald-100' : variance > 0 ? 'bg-blue-50 border-blue-100' : 'bg-amber-50 border-amber-100'}`}>
                                                    <p className="text-[10px] uppercase font-black text-slate-400">Écart</p>
                                                    <p className="text-xl font-black text-slate-900">{isBlindCounting ? '•••' : variance === null ? '-' : `${variance > 0 ? '+' : ''}${variance.toLocaleString('fr-FR')}`}</p>
                                                </div>
                                            </div>
                                        )}
                                    </form>
                                )}

                                <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden">
                                    <table className="w-full text-left">
                                        <thead className="bg-slate-50 border-b border-slate-100">
                                            <tr>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400">Référence</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400">Emplacement</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 text-right">Système</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 text-right">Compté</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 text-right">Écart</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400">Statut</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400">Motif</th>
                                                <th className="px-5 py-4 text-[10px] uppercase font-black tracking-widest text-slate-400 text-right">Action</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100">
                                            {(selectedSession.lines || []).map(line => (
                                                <tr key={line.id} className="hover:bg-slate-50">
                                                    <td className="px-5 py-4">
                                                        <p className="font-black text-sm text-slate-900">{line.variant?.reference || `Variante #${line.variant_id}`}</p>
                                                        <p className="text-xs font-bold text-slate-400">{line.variant?.color || 'Standard'}</p>
                                                    </td>
                                                    <td className="px-5 py-4 text-sm font-bold text-slate-600">{line.location?.name || `Lieu #${line.location_id}`}</td>
                                                    <td className="px-5 py-4 text-right font-black text-slate-700">
                                                        {isBlindCounting ? '•••' : Number(line.expected_quantity ?? 0).toLocaleString('fr-FR')}
                                                    </td>
                                                    <td className="px-5 py-4 text-right font-black text-slate-900">
                                                        {line.counted_quantity === null || line.counted_quantity === undefined ? '—' : Number(line.counted_quantity).toLocaleString('fr-FR')}
                                                    </td>
                                                    <td className={`px-5 py-4 text-right font-black ${isBlindCounting || line.variance_quantity === null || line.variance_quantity === undefined ? 'text-slate-400' : line.variance_quantity === 0 ? 'text-emerald-600' : line.variance_quantity > 0 ? 'text-blue-600' : 'text-amber-700'}`}>
                                                        {isBlindCounting ? '•••' : line.variance_quantity === null || line.variance_quantity === undefined ? '—' : `${line.variance_quantity > 0 ? '+' : ''}${Number(line.variance_quantity).toLocaleString('fr-FR')}`}
                                                    </td>
                                                    <td className="px-5 py-4">
                                                        <span className={`inline-flex items-center px-2.5 py-1 rounded-lg border text-[10px] uppercase font-black ${lineStatusClass[line.status] || 'bg-slate-50 text-slate-600 border-slate-200'}`}>
                                                            {lineStatusLabel[line.status] || line.status || 'OK'}
                                                        </span>
                                                        {line.recount_notes && (
                                                            <p className="text-[11px] font-bold text-red-500 mt-1">{line.recount_notes}</p>
                                                        )}
                                                    </td>
                                                    <td className="px-5 py-4 text-sm font-bold text-slate-500">{line.reason || '-'}</td>
                                                    <td className="px-5 py-4 text-right">
                                                        {['draft', 'counting'].includes(selectedSession.status) && line.status === 'pending' && (
                                                            <button
                                                                type="button"
                                                                onClick={() => focusLine(line)}
                                                                disabled={!canCount || busy}
                                                                className="px-3 py-2 rounded-lg border border-blue-100 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50 text-xs font-black"
                                                            >
                                                                Saisir
                                                            </button>
                                                        )}
                                                        {['draft', 'counting'].includes(selectedSession.status) && line.status !== 'pending' && line.status !== 'recount' && line.status !== 'validated' && Math.abs(Number(line.variance_quantity || 0)) > 0.000001 && (
                                                            <button
                                                                type="button"
                                                                onClick={() => requestRecount(line)}
                                                                disabled={!canValidate || busy}
                                                                className="px-3 py-2 rounded-lg border border-red-100 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50 text-xs font-black"
                                                            >
                                                                Demander recompte
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            ))}
                                            {(!selectedSession.lines || selectedSession.lines.length === 0) && (
                                                <tr>
                                                    <td colSpan="8" className="py-12 text-center text-sm font-bold text-slate-400">
                                                        Aucune ligne dans cette campagne. Scannez ou ajoutez les références réellement vérifiées.
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </>
                        )}
                    </main>
                </div>
            </div>
        </div>
    );
}

// Composant AuditLogs
function AuditLogs({ transactions }) {
    const [movementFilter, setMovementFilter] = useState('all');
    const [selectedMovementId, setSelectedMovementId] = useState(null);
    const filteredTransactions = movementFilter === 'workshop_debit'
        ? transactions.filter(tx => tx.movement_kind === 'workshop_debit' || tx.reference?.startsWith('DEBIT-ATELIER'))
        : transactions;
    const selectedMovement = filteredTransactions.find(tx => tx.id === selectedMovementId) || filteredTransactions[0] || null;
    const parseRoute = (transactionType = '') => {
        const parts = String(transactionType || '').split('➔').map(part => part.trim());
        return {
            from: parts[0] || 'Origine non renseignée',
            to: parts[1] || 'Destination non renseignée',
        };
    };
    const getMovementLabel = (tx) => {
        if (!tx) return 'Mouvement';
        if (tx.movement_kind === 'workshop_debit' || tx.reference?.startsWith('DEBIT-ATELIER')) return 'Débit atelier réel';
        if (tx.source_screen === 'sales.customer_delivery') return 'Sortie client';
        if (tx.source_screen === 'stock.manual_customer_issue') return 'Sortie stock manuelle';
        if (tx.source_screen === 'sales.customer_return') return 'Retour client';
        if (tx.source_screen === 'purchases.receipt') return 'Réception fournisseur';
        if (tx.source_screen === 'stock.physical_inventory') return 'Inventaire physique';
        if (tx.source_screen === 'stock.manual_transaction') return 'Mouvement manuel';
        return tx.transaction_type || 'Mouvement stock';
    };
    const getMovementTone = (tx) => {
        if (!tx) return 'slate';
        if (tx.movement_kind === 'workshop_debit' || tx.source_screen === 'sales.customer_delivery' || tx.source_screen === 'stock.manual_customer_issue') return 'orange';
        if (tx.source_screen === 'sales.customer_return' || tx.source_screen === 'purchases.receipt') return 'emerald';
        if (tx.source_screen === 'stock.physical_inventory') return 'blue';
        return 'slate';
    };
    const selectedRoute = selectedMovement ? parseRoute(selectedMovement.transaction_type) : null;
    const selectedTone = getMovementTone(selectedMovement);
    const exportAudit = async () => {
        const res = await api.get('/v2/stock/transactions/export', { responseType: 'blob' });
        const url = window.URL.createObjectURL(new Blob([res.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'stock-audit.xlsx');
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
    };

    return (
        <div className="bg-white border border-slate-200 shadow-sm overflow-hidden w-full">
            <div className="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <div>
                    <h3 className="font-black text-xl flex items-center gap-2">
                        <Layers className="w-5 h-5 text-slate-800" />
                        Journal d'Audit des Mouvements
                    </h3>
                    <p className="text-xs font-medium text-slate-500 mt-1">Traçabilité complète des entrées, sorties et transferts (100 derniers mouvements).</p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
                        <button
                            onClick={() => setMovementFilter('all')}
                            className={`px-4 py-2 rounded-lg text-xs font-black transition-all ${movementFilter === 'all' ? 'bg-slate-900 text-white' : 'text-slate-500 hover:text-slate-800'}`}
                        >
                            Tous
                        </button>
                        <button
                            onClick={() => setMovementFilter('workshop_debit')}
                            className={`px-4 py-2 rounded-lg text-xs font-black transition-all ${movementFilter === 'workshop_debit' ? 'bg-amber-500 text-white' : 'text-slate-500 hover:text-slate-800'}`}
                        >
                            Débits atelier
                        </button>
                    </div>
                    <button
                        onClick={exportAudit}
                        className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-black inline-flex items-center gap-2 shadow-sm hover:bg-slate-800"
                    >
                        <Download className="w-4 h-4" />
                        Export audit
                    </button>
                </div>
            </div>

            {selectedMovement && (
                <div className="p-6 border-b border-slate-100 bg-white">
                    <div className="rounded-3xl border border-slate-200 overflow-hidden shadow-sm">
                        <div className={`px-6 py-5 text-white flex flex-wrap items-start justify-between gap-4 ${selectedTone === 'orange' ? 'bg-orange-600' : selectedTone === 'emerald' ? 'bg-emerald-700' : selectedTone === 'blue' ? 'bg-blue-700' : 'bg-slate-950'}`}>
                            <div className="min-w-0">
                                <p className="text-[10px] uppercase font-black tracking-widest text-white/70 mb-2">Fiche mouvement stock</p>
                                <h3 className="text-2xl font-black leading-tight">{getMovementLabel(selectedMovement)}</h3>
                                <p className="mt-2 text-sm font-bold text-white/80">
                                    {selectedMovement.reference || `TX-#${selectedMovement.id}`} · {new Date(selectedMovement.created_at).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })}
                                </p>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] uppercase font-black tracking-widest text-white/70">Impact quantité</p>
                                <p className="text-4xl font-black">
                                    {Number(selectedMovement.quantity_change || 0) > 0 ? '+' : ''}{selectedMovement.quantity_change}
                                </p>
                            </div>
                        </div>

                        <div className="p-6 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6 bg-slate-50">
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Article impacté</p>
                                        <p className="mt-2 text-lg font-black text-slate-950">{selectedMovement.item_name || 'Produit inconnu'}</p>
                                        <p className="text-xs font-mono font-bold text-slate-400 mt-1">Variante #{selectedMovement.variant_id || '-'}</p>
                                    </div>
                                    <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                        <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Responsable</p>
                                        <p className="mt-2 text-lg font-black text-slate-950">{selectedMovement.author || 'Non renseigné'}</p>
                                        <p className="text-xs font-bold text-slate-400 mt-1">{selectedMovement.source_screen || 'Écran source non renseigné'}</p>
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400 mb-4">Flux de stock</p>
                                    <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-center">
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Origine</p>
                                            <p className="mt-1 font-black text-slate-900">{selectedRoute.from}</p>
                                        </div>
                                        <ArrowRight className="w-6 h-6 text-slate-300" />
                                        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                                            <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Destination</p>
                                            <p className="mt-1 font-black text-slate-900">{selectedRoute.to}</p>
                                        </div>
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Pourquoi ce mouvement existe ?</p>
                                    <p className="mt-2 text-sm font-bold text-slate-700">
                                        {selectedMovement.business_reason || selectedMovement.notes || 'Raison métier non renseignée.'}
                                    </p>
                                    {selectedMovement.notes && selectedMovement.business_reason && (
                                        <p className="mt-3 rounded-xl bg-slate-50 border border-slate-100 p-3 text-xs font-bold text-slate-500">{selectedMovement.notes}</p>
                                    )}
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Document lié</p>
                                    <div className="mt-3 rounded-2xl bg-slate-50 border border-slate-100 p-4">
                                        <p className="font-black text-slate-950">{selectedMovement.document_reference || 'Aucun document référencé'}</p>
                                        <p className="text-xs font-bold text-slate-400 mt-1">{selectedMovement.document_type || 'Type non renseigné'}</p>
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Audit technique</p>
                                    <div className="mt-3 space-y-2 text-xs font-bold text-slate-600">
                                        <div className="flex justify-between gap-3"><span>ID mouvement</span><span className="font-mono text-slate-900">{selectedMovement.id}</span></div>
                                        <div className="flex justify-between gap-3"><span>Type</span><span className="font-mono text-slate-900">{selectedMovement.movement_kind || '-'}</span></div>
                                        <div className="flex justify-between gap-3"><span>Écran</span><span className="font-mono text-slate-900 text-right">{selectedMovement.source_screen || '-'}</span></div>
                                        <div className="flex justify-between gap-3"><span>Horodatage</span><span className="font-mono text-slate-900 text-right">{new Date(selectedMovement.created_at).toLocaleString('fr-FR')}</span></div>
                                    </div>
                                </div>

                                <div className="rounded-2xl border border-slate-200 bg-white p-5">
                                    <p className="text-[10px] uppercase tracking-widest font-black text-slate-400">Actions utiles</p>
                                    <div className="mt-4 grid grid-cols-1 gap-2">
                                        <button
                                            type="button"
                                            onClick={() => setSelectedMovementId(null)}
                                            className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-3 text-sm font-black text-slate-700 inline-flex items-center justify-center gap-2"
                                        >
                                            <X className="w-4 h-4" />
                                            Revenir au dernier mouvement
                                        </button>
                                        <button
                                            type="button"
                                            onClick={exportAudit}
                                            className="rounded-xl border border-slate-900 bg-slate-900 hover:bg-slate-800 px-4 py-3 text-sm font-black text-white inline-flex items-center justify-center gap-2"
                                        >
                                            <Download className="w-4 h-4" />
                                            Export audit
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div className="w-full p-0">
                <table className="w-full text-left border-collapse">
                    <thead className="bg-slate-50 sticky top-0 z-10">
                        <tr>
                            <th className="px-6 py-4 text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100">Date & Heure</th>
                            <th className="px-6 py-4 text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100">Référence</th>
                            <th className="px-6 py-4 text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100">Produit Impacté</th>
                            <th className="px-6 py-4 text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 text-center">Mouvement</th>
                            <th className="px-6 py-4 text-xs font-black text-slate-400 uppercase tracking-widest border-b border-slate-100 text-center">Qté</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredTransactions.map(tx => {
                            const isWorkshopDebit = tx.movement_kind === 'workshop_debit' || tx.reference?.startsWith('DEBIT-ATELIER');
                            return (
                                <tr
                                    key={tx.id}
                                    onClick={() => setSelectedMovementId(tx.id)}
                                    className={`hover:bg-slate-50 border-b border-slate-50 transition-colors cursor-pointer ${selectedMovement?.id === tx.id ? 'bg-blue-50/60' : ''}`}
                                >
                                    <td className="px-6 py-4 text-sm text-slate-600 font-medium">
                                        {new Date(tx.created_at).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' })}
                                        <div className="text-[10px] text-slate-400 font-mono mt-1">{tx.author}</div>
                                    </td>
                                    <td className="px-6 py-4 text-sm font-mono text-slate-500 font-bold">
                                        {tx.reference || `TX-#${tx.id}`}
                                        <button
                                            type="button"
                                            onClick={(event) => { event.stopPropagation(); setSelectedMovementId(tx.id); }}
                                            className="ml-2 rounded-lg bg-slate-100 hover:bg-slate-200 px-2 py-1 text-[10px] font-black text-slate-600"
                                        >
                                            Fiche
                                        </button>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className="font-bold text-slate-800 text-[13px] block">{tx.item_name}</span>
                                        {(tx.document_reference || tx.business_reason) && (
                                            <span className="text-[10px] text-slate-500 block mt-1">
                                                {tx.document_reference && <b>{tx.document_reference}</b>}
                                                {tx.document_reference && tx.business_reason && ' · '}
                                                {tx.business_reason}
                                            </span>
                                        )}
                                        {tx.notes && <span className="text-[10px] italic text-slate-400 line-clamp-1">{tx.notes}</span>}
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span className={`${isWorkshopDebit ? 'bg-amber-100 text-amber-700 border border-amber-200' : 'bg-slate-100 text-slate-600'} px-3 py-1 rounded-full text-xs font-bold uppercase whitespace-nowrap`}>
                                            {isWorkshopDebit ? 'Débit atelier réel' : tx.transaction_type}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-center">
                                        <span className={`font-black ${isWorkshopDebit ? 'text-orange-600' : tx.quantity_change > 0 ? 'text-emerald-500' : 'text-blue-500'}`}>
                                            {isWorkshopDebit ? '-' : tx.quantity_change > 0 ? '+' : ''}{tx.quantity_change}
                                        </span>
                                    </td>
                                </tr>
                            );
                        })}
                        {filteredTransactions.length === 0 && (
                            <tr>
                                <td colSpan="5" className="text-center py-12 text-slate-400 font-bold">Aucun mouvement enregistré.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
