import React, { useState } from 'react';
import { ShoppingCart, Plus, FileText, Search, ArrowRight, CheckCircle, PackageOpen, X, Truck, Users, Phone, Mail, MapPin, Sparkles, BrainCircuit, Building2, Globe2, AlertTriangle, Layers } from 'lucide-react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { downloadFileWithFeedback } from '../services/pdf';
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

const UNKNOWN_SUPPLIER = 'Fournisseur à qualifier';

const priorityLabel = (priority) => ({
    CRITICAL: 'Critique',
    URGENT: 'Urgent',
    TO_PLAN: 'À prévoir',
    COVERED: 'Couvert',
    NORMAL: 'Normal',
})[priority] || priority || 'À traiter';

const priorityTone = (priority) => ({
    CRITICAL: {
        card: 'bg-red-50 border-red-100',
        rail: 'bg-red-500',
        badge: 'bg-red-100 text-red-700',
    },
    URGENT: {
        card: 'bg-orange-50 border-orange-100',
        rail: 'bg-orange-500',
        badge: 'bg-orange-100 text-orange-700',
    },
    TO_PLAN: {
        card: 'bg-indigo-50 border-indigo-100',
        rail: 'bg-indigo-500',
        badge: 'bg-indigo-100 text-indigo-700',
    },
    COVERED: {
        card: 'bg-emerald-50 border-emerald-100',
        rail: 'bg-emerald-500',
        badge: 'bg-emerald-100 text-emerald-700',
    },
    NORMAL: {
        card: 'bg-slate-50 border-slate-200',
        rail: 'bg-slate-400',
        badge: 'bg-slate-100 text-slate-600',
    },
})[priority] || {
    card: 'bg-indigo-50 border-indigo-100',
    rail: 'bg-indigo-500',
    badge: 'bg-indigo-100 text-indigo-700',
};

const normalizePurchaseNeeds = (payload, variants, suppliers) => {
    const rawNeeds = Array.isArray(payload) ? payload : payload?.needs || [];
    const supplierByName = new Map(suppliers.map(s => [String(s.name || '').toUpperCase(), s]));
    return rawNeeds.map((need) => {
        const variant = variants.find(v => String(v.id) === String(need.variant_id));
        const reference = need.reference || variant?.reference || '';
        const parsedSupplier = reference.includes(':') ? reference.split(':')[0] : '';
        const supplier = need.supplier || variant?.product_supplier || parsedSupplier || UNKNOWN_SUPPLIER;
        const supplierRecord = supplierByName.get(String(supplier).toUpperCase());
        const priority = need.priority || (Number(need.current_stock || 0) <= 0 ? 'CRITICAL' : 'URGENT');
        const suggestedQuantity = Number(need.suggested_quantity ?? need.net_need_quantity ?? need.quantity_to_order ?? need.recommended_quantity ?? 0);
        const isCatalogDraft = (need.catalog_status || variant?.catalog_status || '').toUpperCase().includes('DRAFT');
        const isBlockedSupplier = supplierRecord?.supplier_status === 'BLOCKED';
        const hasSupplier = supplier && supplier !== UNKNOWN_SUPPLIER;
        const hasVariant = Boolean(need.variant_id || variant?.id);
        const canOrder = Boolean(need.is_orderable ?? need.can_order ?? true) && hasVariant && hasSupplier && !isCatalogDraft && !isBlockedSupplier && suggestedQuantity > 0;
        const blockedReason = !hasSupplier
            ? 'Fournisseur non renseigné'
            : !hasVariant
                ? 'Variante catalogue introuvable'
                : isCatalogDraft
                    ? 'Article brouillon à qualifier'
                    : isBlockedSupplier
                        ? 'Fournisseur bloqué'
                        : suggestedQuantity <= 0
                            ? 'Quantité suggérée invalide'
                            : '';
        return {
            ...need,
            variant_id: need.variant_id || variant?.id,
            reference,
            product_name: need.product_name || variant?.product_name || 'Article stock',
            supplier,
            supplier_status: supplierRecord?.supplier_status || null,
            current_stock: Number(need.current_stock ?? need.available_stock ?? variant?.quantity_in_stock ?? 0),
            reserved_stock: Number(need.reserved_stock ?? need.reserved_quantity ?? 0),
            min_threshold: Number(need.min_threshold ?? need.threshold ?? variant?.min_threshold ?? 0),
            incoming_purchase_quantity: Number(need.incoming_purchase_quantity ?? 0),
            open_purchase_request_quantity: Number(need.open_purchase_request_quantity ?? 0),
            net_need_quantity: Number(need.net_need_quantity ?? suggestedQuantity),
            suggested_quantity: suggestedQuantity,
            priority,
            origin: need.origin || need.source || 'Seuil stock',
            reason: need.reason || 'Besoin calculé depuis stock disponible et seuil mini.',
            unit_price: Number(need.unit_price ?? need.cost_price ?? variant?.cost_price ?? 0),
            can_order: canOrder,
            blocked_reason: need.blocked_reason || blockedReason,
        };
    });
};

const groupNeedsBySupplier = (needs) => Object.values(needs.reduce((acc, need) => {
    const key = need.supplier || UNKNOWN_SUPPLIER;
    if (!acc[key]) {
        acc[key] = {
            supplier: key,
            needs: [],
            critical_count: 0,
            urgent_count: 0,
            total_quantity: 0,
            orderable_count: 0,
        };
    }
    acc[key].needs.push(need);
    acc[key].critical_count += need.priority === 'CRITICAL' ? 1 : 0;
    acc[key].urgent_count += need.priority === 'URGENT' ? 1 : 0;
    acc[key].total_quantity += Number(need.suggested_quantity || 0);
    acc[key].orderable_count += need.can_order ? 1 : 0;
    return acc;
}, {})).sort((a, b) => b.critical_count - a.critical_count || b.urgent_count - a.urgent_count || a.supplier.localeCompare(b.supplier));

export default function PurchasesDashboard() {
    const [currentTab, setCurrentTab] = useState('dashboard'); // dashboard, orders, requests, suppliers, ai

    // Orders state
    const [searchTerm, setSearchTerm] = useState("");
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedPO, setSelectedPO] = useState(null);
    const [showReceiveModal, setShowReceiveModal] = useState(false);
    const [showSupplierInvoiceModal, setShowSupplierInvoiceModal] = useState(false);
    const [selectedSupplierInvoice, setSelectedSupplierInvoice] = useState(null);
    const [supplierPaymentTarget, setSupplierPaymentTarget] = useState(null);
    const [supplierPaymentForm, setSupplierPaymentForm] = useState({ amount: '', method: 'TRANSFER', reference: '', notes: '' });
    const [showDisputeModal, setShowDisputeModal] = useState(false);
    const [disputeForm, setDisputeForm] = useState({
        supplier: '',
        purchase_order_id: null,
        supplier_invoice_id: null,
        title: '',
        category: 'OTHER',
        severity: 'MEDIUM',
        description: '',
        expected_quantity: '',
        received_quantity: '',
        expected_unit_price: '',
        invoiced_unit_price: '',
        expected_action: 'INFO',
        due_date: '',
        blocks_receipt: false,
        blocks_payment: false,
        impact_summary: '',
    });

    // Suppliers state
    const [selectedSupplierId, setSelectedSupplierId] = useState(null);

    // Smart purchasing state

    // Suppliers state
    const [showSupplierModal, setShowSupplierModal] = useState(false);
    const emptySupplierForm = {
        name: '',
        contact_name: '',
        email: '',
        phone: '',
        address: '',
        country: 'France',
        tax_id: '',
        supplier_status: 'ACTIVE',
        supplier_category: 'ALUMINIUM',
        default_currency: 'EUR',
        incoterm: '',
        delivery_terms: '',
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
    const [createMode, setCreateMode] = useState('order');

    // Receive form
    const [receiveTargetLoc, setReceiveTargetLoc] = useState('');
    const [receiveLines, setReceiveLines] = useState([]);
    const [supplierInvoiceRef, setSupplierInvoiceRef] = useState('');
    const [supplierInvoiceDueDate, setSupplierInvoiceDueDate] = useState('');
    const [supplierInvoiceNotes, setSupplierInvoiceNotes] = useState('');
    const [supplierInvoiceLines, setSupplierInvoiceLines] = useState([]);

    const queryClient = useQueryClient();
    const userPermissions = JSON.parse(localStorage.getItem('permissions') || '[]');
    const can = (permission) => userPermissions.includes('*') || userPermissions.includes(permission);
    const canCreatePurchaseOrder = can('purchases.order');
    const canCreatePurchaseRequest = can('purchases.request');
    const canApprovePurchaseRequest = can('purchases.approve');

    const { data: purchases = [] } = useQuery({
        queryKey: ['purchases'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/');
            return res.data;
        }
    });

    const { data: purchaseRequests = [], refetch: refetchPurchaseRequests } = useQuery({
        queryKey: ['purchase-requests'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/requests');
            return res.data;
        }
    });

    const { data: supplierDisputes = [] } = useQuery({
        queryKey: ['supplier-disputes'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/disputes');
            return res.data;
        }
    });

    const { data: purchaseDashboard = { summary: {}, actions: [] } } = useQuery({
        queryKey: ['purchase-dashboard'],
        queryFn: async () => {
            const res = await api.get('/v2/purchases/dashboard');
            return res.data;
        }
    });

    const { data: suppliers = [] } = useQuery({
        queryKey: ['suppliers', 'v2'],
        queryFn: async () => {
            const res = await api.get('/v2/suppliers/');
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
                    flatVariants.push({ ...v, product_name: p.name, product_supplier: p.supplier, catalog_status: p.catalog_status });
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

    const { data: aiRecommendations = { summary: {}, needs: [], groups: [] }, isLoading: loadingAi, refetch: refetchAiRecommendations } = useQuery({
        queryKey: ['purchase-needs'],
        queryFn: async () => {
            try {
                const res = await api.get('/v2/purchases/needs');
                return res.data;
            } catch (error) {
                const fallback = await api.get('/v2/purchases/ai-recommendations');
                return {
                    summary: {
                        needs_count: fallback.data.length,
                        critical_count: fallback.data.length,
                        urgent_count: 0,
                        to_plan_count: 0,
                        blocked_count: 0,
                        suppliers_count: 0,
                    },
                    needs: fallback.data.map(item => ({
                        ...item,
                        product_name: item.product_name,
                        supplier: null,
                        suggested_quantity: item.suggested_quantity,
                        priority: 'CRITICAL',
                        reason: item.reason,
                        is_orderable: true,
                    })),
                    groups: [],
                };
            }
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
    const purchaseNeeds = normalizePurchaseNeeds(aiRecommendations, availableVariants, suppliers);
    const filteredPurchaseNeeds = purchaseNeeds.filter(need => {
        const term = searchTerm.toLowerCase();
        return !term
            || need.product_name.toLowerCase().includes(term)
            || need.reference.toLowerCase().includes(term)
            || need.supplier.toLowerCase().includes(term)
            || need.reason.toLowerCase().includes(term);
    });
    const purchaseNeedGroups = groupNeedsBySupplier(filteredPurchaseNeeds);
    const purchaseNeedsSummary = {
        needs_count: purchaseNeeds.length,
        critical_count: purchaseNeeds.filter(need => need.priority === 'CRITICAL').length,
        urgent_count: purchaseNeeds.filter(need => need.priority === 'URGENT').length,
        blocked_count: purchaseNeeds.filter(need => !need.can_order).length,
        suppliers_count: groupNeedsBySupplier(purchaseNeeds).length,
        ...(Array.isArray(aiRecommendations) ? {} : aiRecommendations.summary || {}),
    };

    const preparePOFromNeeds = (needs, supplierName = '') => {
        const targetSupplier = supplierName && supplierName !== UNKNOWN_SUPPLIER ? supplierName : (needs[0]?.supplier || '');
        const nextMode = canCreatePurchaseRequest ? 'request' : canCreatePurchaseOrder ? 'order' : 'request';
        setNewPO({
            ...emptyPOForm,
            supplier: targetSupplier === UNKNOWN_SUPPLIER ? '' : targetSupplier,
            notes: `${nextMode === 'order' ? 'Commande' : 'Demande'} préparée depuis les besoins achats réels (${needs.length} ligne(s)) : seuil bas, rupture, réservation ou commande client.`,
            lines: needs.map(need => ({
                variant_id: need.variant_id,
                quantity: need.suggested_quantity,
                unit_price: need.unit_price || 0,
                discount_percent: 0,
                need_priority: need.priority,
                need_reason: `${priorityLabel(need.priority)} · ${need.reason || 'Besoin achat calculé.'}`,
            })),
        });
        setCreateMode(nextMode);
        setCurrentTab(nextMode === 'order' ? 'orders' : 'requests');
        setSelectedPO(null);
        setShowCreateModal(true);
    };

    const openCreatePOForSupplier = (supplierName = '') => {
        setCreateMode(canCreatePurchaseRequest ? 'request' : 'order');
        setNewPO({
            ...emptyPOForm,
            supplier: supplierName,
            notes: supplierName ? `${canCreatePurchaseRequest ? 'Demande' : 'Commande'} fournisseur ${supplierName}` : '',
        });
        setCurrentTab(canCreatePurchaseRequest ? 'requests' : 'orders');
        setSelectedPO(null);
        setShowCreateModal(true);
    };

    const openDisputeModal = ({ supplier, purchaseOrderId = null, title = '' }) => {
        setDisputeForm({
            supplier: supplier || '',
            purchase_order_id: purchaseOrderId,
            supplier_invoice_id: null,
            title,
            category: 'OTHER',
            severity: 'MEDIUM',
            description: '',
            expected_quantity: '',
            received_quantity: '',
            expected_unit_price: '',
            invoiced_unit_price: '',
            expected_action: 'INFO',
            due_date: '',
            blocks_receipt: false,
            blocks_payment: false,
            impact_summary: '',
        });
        setShowDisputeModal(true);
    };

    const handleCreateDispute = async () => {
        if (!disputeForm.supplier || !disputeForm.title.trim()) return;
        try {
            await api.post('/v2/purchases/disputes', {
                ...disputeForm,
                title: disputeForm.title.trim(),
                description: disputeForm.description.trim() || null,
                expected_quantity: disputeForm.expected_quantity === '' ? null : Number(disputeForm.expected_quantity),
                received_quantity: disputeForm.received_quantity === '' ? null : Number(disputeForm.received_quantity),
                expected_unit_price: disputeForm.expected_unit_price === '' ? null : Number(disputeForm.expected_unit_price),
                invoiced_unit_price: disputeForm.invoiced_unit_price === '' ? null : Number(disputeForm.invoiced_unit_price),
                due_date: disputeForm.due_date || null,
                impact_summary: disputeForm.impact_summary.trim() || null,
            });
            setShowDisputeModal(false);
            queryClient.invalidateQueries(['supplier-disputes']);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (selectedPO?.id) await openPODetails(selectedPO.id);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la création du litige fournisseur.");
        }
    };

    const handleStartDispute = async (disputeId) => {
        try {
            await api.post(`/v2/purchases/disputes/${disputeId}/start`);
            queryClient.invalidateQueries(['supplier-disputes']);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (selectedPO?.id) await openPODetails(selectedPO.id);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la prise en charge du litige.");
        }
    };

    const handleResolveDispute = async (disputeId) => {
        const resolution = window.prompt("Compte rendu de résolution du litige :");
        if (!resolution || !resolution.trim()) return;
        try {
            await api.post(`/v2/purchases/disputes/${disputeId}/resolve`, { resolution_notes: resolution.trim() });
            queryClient.invalidateQueries(['supplier-disputes']);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (selectedPO?.id) await openPODetails(selectedPO.id);
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la résolution du litige.");
        }
    };

    const handleDownloadPOPDF = async (po) => {
        if (!po?.id) return;
        await downloadFileWithFeedback(`/v2/purchases/${po.id}/pdf`, `bon-fournisseur-${po.reference}.pdf`);
    };

    const handleRemindSupplier = async (poId) => {
        try {
            const note = window.prompt("Message de relance fournisseur :", "");
            const res = await api.post(`/v2/purchases/${poId}/remind`, {
                channel: 'email',
                message: note && note.trim() ? note.trim() : null,
                include_pdf: true,
                send_email: true,
            });
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (selectedPO?.id === poId) await openPODetails(poId);
            const status = res.data?.status;
            if (status === 'SENT') {
                alert("Relance fournisseur envoyée avec le bon fournisseur en pièce jointe.");
            } else if (status === 'SKIPPED') {
                alert("Relance préparée mais non envoyée : SMTP non configuré.");
            } else if (status === 'FAILED') {
                alert(res.data?.reminder?.error_message || "Relance non envoyée.");
            } else {
                alert("Relance fournisseur enregistrée.");
            }
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la relance fournisseur.");
        }
    };

    const handleCreateSupplier = async () => {
        try {
            const payload = {
                ...newSupplier,
                lead_time_days: newSupplier.lead_time_days === '' ? null : parseInt(newSupplier.lead_time_days, 10),
            };
            await api.post('/v2/suppliers/', payload);
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
                need_priority: l.need_priority || null,
                need_reason: l.need_reason || null,
            }));
            const endpoint = createMode === 'request' ? '/v2/purchases/requests' : '/v2/purchases/';
            await api.post(endpoint, {
                ...newPO,
                sensitivity_reason: createMode === 'request' ? 'Demande à valider avant engagement fournisseur' : undefined,
                lines
            });
            setShowCreateModal(false);
            setNewPO(emptyPOForm);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-requests']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (createMode === 'request') {
                setCurrentTab('requests');
            }
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || `Erreur lors de la création ${createMode === 'request' ? 'de la demande' : 'de la commande'}.`);
        }
    };

    const handleApprovePurchaseRequest = async (requestId) => {
        try {
            await api.post(`/v2/purchases/requests/${requestId}/approve`);
            queryClient.invalidateQueries(['purchase-requests']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            await refetchPurchaseRequests();
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la validation de la demande.");
        }
    };

    const handleRejectPurchaseRequest = async (requestId) => {
        const reason = window.prompt("Motif du refus achat :");
        if (!reason || !reason.trim()) return;
        try {
            await api.post(`/v2/purchases/requests/${requestId}/reject`, { reason: reason.trim() });
            queryClient.invalidateQueries(['purchase-requests']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            await refetchPurchaseRequests();
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors du refus de la demande.");
        }
    };

    const handleConvertPurchaseRequest = async (requestId) => {
        try {
            const res = await api.post(`/v2/purchases/requests/${requestId}/convert`);
            queryClient.invalidateQueries(['purchase-requests']);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            await refetchPurchaseRequests();
            if (res.data?.purchase_order?.id) {
                await openPODetails(res.data.purchase_order.id);
                setCurrentTab('orders');
            }
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors de la conversion en bon fournisseur.");
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
            queryClient.invalidateQueries(['purchase-dashboard']);
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
            return res.data;
        } catch (err) {
            console.error(err);
            return null;
        }
    };

    const openSupplierInvoiceDetail = async (invoice, purchaseOrder = selectedPO) => {
        if (!invoice) return;
        let po = purchaseOrder;
        if ((!po || po.id !== invoice.purchase_order_id) && invoice.purchase_order_id) {
            po = await openPODetails(invoice.purchase_order_id);
        }
        const fullInvoice = po?.supplier_invoices?.find(item => item.id === (invoice.id || invoice.invoice_id)) || invoice;
        setSelectedSupplierInvoice({ invoice: fullInvoice, purchaseOrder: po });
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
            queryClient.invalidateQueries(['purchase-dashboard']);
            await openPODetails(selectedPO.id);
            alert("Facture fournisseur rapprochée avec les réceptions.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors du rapprochement facture fournisseur.");
        }
    };

    const openSupplierPaymentModal = (invoice) => {
        const remaining = Number(invoice.remaining_amount ?? Math.max(Number(invoice.total_amount || 0) - Number(invoice.paid_amount || 0), 0));
        setSupplierPaymentTarget(invoice);
        setSupplierPaymentForm({
            amount: remaining ? remaining.toFixed(2) : '',
            method: 'TRANSFER',
            reference: '',
            notes: '',
        });
    };

    const handlePaySupplierInvoice = async () => {
        if (!supplierPaymentTarget) return;
        const amount = Number(supplierPaymentForm.amount || 0);
        if (amount <= 0) return alert("Montant de paiement invalide.");
        try {
            await api.post(`/v2/purchases/supplier-invoices/${supplierPaymentTarget.id}/pay`, {
                amount,
                method: supplierPaymentForm.method,
                reference: supplierPaymentForm.reference.trim() || null,
                notes: supplierPaymentForm.notes.trim() || null,
            });
            setSupplierPaymentTarget(null);
            setSelectedSupplierInvoice(null);
            queryClient.invalidateQueries(['purchases']);
            queryClient.invalidateQueries(['purchase-dashboard']);
            if (selectedPO?.id) await openPODetails(selectedPO.id);
            alert("Paiement fournisseur enregistré.");
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Erreur lors du paiement fournisseur.");
        }
    };


    const filteredPurchases = purchases.filter(p =>
        p.reference.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.supplier.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="w-full h-[calc(100vh-80px)] font-sans flex overflow-hidden bg-white border-y border-slate-200/80 animate-fade-in relative">

            {/* LEFT SIDEBAR : PO LIST */}
            <div className="w-[400px] bg-white border-r border-slate-200 flex flex-col items-stretch h-full shadow-xl z-20 relative">
                <div className="p-6 border-b border-slate-200 flex flex-col gap-4 relative z-10 bg-white">
                    <h3 className="font-black text-slate-900 flex items-center gap-3 tracking-tight text-xl">
                        <ShoppingCart className="text-blue-600 w-6 h-6"/> Achats & Appro.
                    </h3>

                    {/* TABS */}
                    <div className="grid grid-cols-2 gap-1 bg-slate-100 p-1 rounded-xl">
                        <button
                            onClick={() => setCurrentTab('dashboard')}
                            className={`py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'dashboard' ? 'bg-white shadow text-slate-900' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Pilotage
                        </button>
                        <button
                            onClick={() => setCurrentTab('orders')}
                            className={`py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'orders' ? 'bg-white shadow text-blue-600' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Commandes
                        </button>
                        <button
                            onClick={() => setCurrentTab('requests')}
                            className={`py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'requests' ? 'bg-white shadow text-amber-600' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Demandes
                        </button>
                        <button
                            onClick={() => setCurrentTab('suppliers')}
                            className={`py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'suppliers' ? 'bg-white shadow text-emerald-600' : 'text-slate-500 hover:text-slate-700'}`}
                        >
                            Fournisseurs
                        </button>
                        <button
                            onClick={() => setCurrentTab('ai')}
                            className={`py-2 text-sm font-bold rounded-lg transition-all ${currentTab === 'ai' ? 'bg-white shadow text-indigo-600' : 'text-slate-500 hover:text-slate-700'}`}
                            title="Besoins d'achat nets"
                        >
                            À commander
                        </button>
                    </div>

                    <div className="relative">
                        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                        <input
                            type="text"
                            placeholder={currentTab === 'dashboard' ? "Rechercher action achat..." : currentTab === 'orders' ? "Rechercher Bon de Commande..." : currentTab === 'requests' ? "Rechercher demande achat..." : currentTab === 'suppliers' ? "Rechercher Fournisseur..." : "Rechercher une recommandation..."}
                            value={searchTerm}
                            onChange={e => setSearchTerm(e.target.value)}
                            className="w-full bg-slate-50 border border-slate-200 rounded-xl py-2.5 pl-10 pr-4 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-blue-500"
                        />
                    </div>
                    {currentTab === 'orders' && (
                        <button onClick={() => openCreatePOForSupplier()} className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <Plus className="w-5 h-5"/> {canCreatePurchaseOrder ? 'Créer Commande' : 'Créer Demande'}
                        </button>
                    )}
                    {currentTab === 'requests' && (
                        <button disabled={!canCreatePurchaseRequest} onClick={() => openCreatePOForSupplier()} className="w-full py-3 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-300 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <Plus className="w-5 h-5"/> Nouvelle demande
                        </button>
                    )}
                    {currentTab === 'suppliers' && (
                        <button onClick={() => setShowSupplierModal(true)} className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <Plus className="w-5 h-5"/> Nv. Fournisseur
                        </button>
                    )}
                    {currentTab === 'ai' && (
                        <button onClick={() => refetchAiRecommendations()} className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-black shadow-md flex justify-center items-center gap-2 transition-all hover:-translate-y-0.5">
                            <BrainCircuit className="w-5 h-5"/> Recalculer besoins
                        </button>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {currentTab === 'dashboard' && (
                        <>
                            {(purchaseDashboard.actions || [])
                                .filter(action => {
                                    const term = searchTerm.toLowerCase();
                                    return !term
                                        || String(action.reference || '').toLowerCase().includes(term)
                                        || String(action.supplier || '').toLowerCase().includes(term)
                                        || String(action.label || '').toLowerCase().includes(term);
                                })
                                .slice(0, 12)
                                .map(action => (
                                    <button
                                        key={`${action.type}-${action.reference}-${action.purchase_order_id || action.purchase_request_id || action.dispute_id}`}
                                        onClick={() => {
                                            if (action.purchase_order_id) openPODetails(action.purchase_order_id);
                                            if (action.type === 'REQUEST') setCurrentTab('requests');
                                        }}
                                        className="w-full text-left p-4 rounded-xl border-2 bg-white border-slate-100 hover:border-slate-300 shadow-sm"
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{action.type}</p>
                                                <h4 className="font-black text-slate-900">{action.label}</h4>
                                                <p className="text-xs font-bold text-slate-500">{action.supplier || 'Achat'} · {action.reference}</p>
                                            </div>
                                            {action.late_days > 0 && <span className="text-[10px] font-black text-red-700 bg-red-100 px-2 py-1 rounded-lg">{action.late_days}j</span>}
                                        </div>
                                    </button>
                                ))}
                            {(purchaseDashboard.actions || []).length === 0 && (
                                <div className="text-center py-10 text-slate-400 font-bold">Aucune action achat urgente.</div>
                            )}
                        </>
                    )}
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
                    {currentTab === 'requests' && (
                        <>
                            {purchaseRequests
                                .filter(req => {
                                    const term = searchTerm.toLowerCase();
                                    return !term
                                        || String(req.reference || '').toLowerCase().includes(term)
                                        || String(req.supplier || '').toLowerCase().includes(term)
                                        || String(req.requested_by || '').toLowerCase().includes(term);
                                })
                                .map(req => (
                                    <div
                                        key={req.id}
                                        className="p-4 rounded-xl border-2 bg-white border-slate-100 shadow-sm"
                                    >
                                        <div className="flex justify-between items-start mb-2">
                                            <span className="font-black text-slate-900">{req.reference}</span>
                                            <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-md ${
                                                req.status === 'PENDING_APPROVAL' ? 'bg-amber-100 text-amber-700'
                                                    : req.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-700'
                                                        : req.status === 'CONVERTED' ? 'bg-blue-100 text-blue-700'
                                                            : req.status === 'REJECTED' ? 'bg-red-100 text-red-700'
                                                                : 'bg-slate-100 text-slate-600'
                                            }`}>{req.status}</span>
                                        </div>
                                        <div className="flex justify-between items-center text-sm">
                                            <span className="font-bold text-slate-600">{req.supplier}</span>
                                            <span className="font-black text-slate-800">{Number(req.total_amount || 0).toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</span>
                                        </div>
                                        <div className="text-xs text-slate-400 mt-2 font-medium flex items-center gap-1">
                                            <FileText className="w-3 h-3"/> {req.lines_count} ligne(s) · demandé par {req.requested_by || 'Système'}
                                        </div>
                                    </div>
                                ))}
                            {purchaseRequests.length === 0 && (
                                <div className="text-center py-10 text-slate-400 font-bold">Aucune demande d'achat.</div>
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
                                    Calcul des besoins...
                                </div>
                            ) : (
                                <>
                                    {filteredPurchaseNeeds.map((rec) => (
                                        <div key={`${rec.variant_id}-${rec.reference}`} className={`p-4 rounded-xl border shadow-sm relative overflow-hidden ${priorityTone(rec.priority).card}`}>
                                            <div className={`absolute top-0 left-0 w-1 h-full ${priorityTone(rec.priority).rail}`}></div>
                                            <h4 className="font-black text-slate-800 text-sm flex items-start justify-between">
                                                <span>{rec.product_name}</span>
                                                <span className={`text-[10px] px-2 py-0.5 rounded-full font-black ${priorityTone(rec.priority).badge}`}>{priorityLabel(rec.priority)}</span>
                                            </h4>
                                            <p className="text-[10px] font-mono text-slate-500 mb-2">{rec.reference}</p>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">{rec.supplier}</p>

                                            <div className="flex justify-between items-center mb-2 bg-white rounded-lg p-2 border border-indigo-50">
                                                <div className="text-center">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase">Disponible</div>
                                                    <div className="font-black text-red-500">{rec.current_stock}</div>
                                                </div>
                                                <div className="text-center">
                                                    <div className="text-[10px] font-bold text-slate-400 uppercase">À commander</div>
                                                    <div className="font-black text-indigo-600">+{rec.suggested_quantity}</div>
                                                </div>
                                            </div>

                                            <p className="text-xs text-slate-600 font-medium leading-tight">
                                                {rec.reason}
                                            </p>
                                            {!rec.can_order && (
                                                <p className="mt-2 text-[10px] font-black text-red-600 uppercase tracking-widest">{rec.blocked_reason}</p>
                                            )}

                                            <button
                                                onClick={() => preparePOFromNeeds([rec], rec.supplier)}
                                                disabled={!rec.can_order}
                                                className="mt-3 w-full py-2 bg-white border border-indigo-200 hover:bg-indigo-100 disabled:bg-slate-100 disabled:text-slate-400 text-indigo-700 text-xs font-black rounded-lg transition-colors"
                                            >
                                                Préparer commande
                                            </button>
                                        </div>
                                    ))}
                                    {filteredPurchaseNeeds.length === 0 && (
                                        <div className="text-center py-10 text-slate-400 font-bold">Aucun besoin d'achat à traiter.</div>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* MAIN AREA : PO DETAILS */}
            <div className="flex-1 flex flex-col bg-slate-50 relative overflow-y-auto">
                {currentTab === 'dashboard' ? (
                    <PurchaseDashboardOverview
                        dashboard={purchaseDashboard}
                        setCurrentTab={setCurrentTab}
                        openPODetails={openPODetails}
                        openSupplierInvoiceDetail={openSupplierInvoiceDetail}
                        handleRemindSupplier={handleRemindSupplier}
                    />
                ) : currentTab === 'requests' ? (
                    <PurchaseRequestsView
                        requests={purchaseRequests}
                        canApprove={canApprovePurchaseRequest}
                        canOrder={canCreatePurchaseOrder}
                        onApprove={handleApprovePurchaseRequest}
                        onReject={handleRejectPurchaseRequest}
                        onConvert={handleConvertPurchaseRequest}
                    />
                ) : currentTab === 'ai' ? (
                    <SmartPurchasingView
                        needs={filteredPurchaseNeeds}
                        groups={purchaseNeedGroups}
                        summary={purchaseNeedsSummary}
                        loading={loadingAi}
                        refetch={refetchAiRecommendations}
                        preparePOFromNeeds={preparePOFromNeeds}
                        canCreatePurchaseOrder={canCreatePurchaseOrder}
                    />
                ) : currentTab === 'suppliers' ? (
                    selectedSupplierId ? (
                        <SupplierProfile
                            sup={suppliers.find(s => s.id === selectedSupplierId)}
                            purchases={purchases}
                            disputes={supplierDisputes}
                            openPODetails={openPODetails}
                            setCurrentTab={setCurrentTab}
                            openCreatePOForSupplier={openCreatePOForSupplier}
                            openDisputeModal={openDisputeModal}
                            onStartDispute={handleStartDispute}
                            onResolveDispute={handleResolveDispute}
                        />
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-400">
                            <Building2 className="w-24 h-24 text-slate-200 mb-6" />
                            <h2 className="text-2xl font-black text-slate-500">Aucun fournisseur sélectionné</h2>
                            <p className="font-medium mt-2">Sélectionnez un fournisseur à gauche pour voir sa fiche et son historique.</p>
                        </div>
                    )
                ) : selectedPO ? (
                    <div className="p-8 w-full">
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
                                    <span className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-md bg-blue-100 text-blue-700">
                                        {selectedPO.next_action || 'Contrôle achat'}
                                    </span>
                                    <div className="mt-2 flex flex-wrap justify-end gap-2">
                                        <button
                                            onClick={() => handleDownloadPOPDF(selectedPO)}
                                            className="px-3 py-2 rounded-xl bg-white/10 border border-white/15 text-white hover:bg-white/20 text-xs font-black flex items-center gap-2"
                                        >
                                            <FileText className="w-4 h-4" /> PDF bon
                                        </button>
                                        {Number(selectedPO.quantity_remaining || 0) > 0 && (
                                            <button
                                                onClick={() => handleRemindSupplier(selectedPO.id)}
                                                className="px-3 py-2 rounded-xl bg-amber-400/15 border border-amber-200/20 text-amber-100 hover:bg-amber-400/25 text-xs font-black"
                                            >
                                                Envoyer relance
                                            </button>
                                        )}
                                    </div>
                                    <button
                                        onClick={() => openDisputeModal({ supplier: selectedPO.supplier, purchaseOrderId: selectedPO.id, title: `Litige ${selectedPO.reference}` })}
                                        className="mt-2 px-3 py-2 rounded-xl bg-red-500/15 border border-red-300/20 text-red-100 hover:bg-red-500/25 text-xs font-black"
                                    >
                                        Déclarer litige
                                    </button>
                                </div>
                            </div>

                            <div className="p-8">
                                <div className="grid grid-cols-2 xl:grid-cols-5 gap-4 mb-8">
                                    <div className="rounded-2xl bg-blue-50 border border-blue-100 p-4">
                                        <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">Commandé</p>
                                        <p className="text-2xl font-black text-blue-700">{Number(selectedPO.quantity_ordered ?? (selectedPO.lines || []).reduce((sum, line) => sum + Number(line.quantity || 0), 0)).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-4">
                                        <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Réceptionné</p>
                                        <p className="text-2xl font-black text-emerald-700">{Number(selectedPO.quantity_received || 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-slate-50 border border-slate-200 p-4">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Reste à recevoir</p>
                                        <p className="text-2xl font-black text-slate-800">{Number(selectedPO.quantity_remaining || 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-orange-50 border border-orange-100 p-4">
                                        <p className="text-[10px] font-black text-orange-500 uppercase tracking-widest">Facturé fournisseur</p>
                                        <p className="text-2xl font-black text-orange-700">{Number(selectedPO.quantity_invoiced || 0).toLocaleString('fr-FR')}</p>
                                    </div>
                                    <div className="rounded-2xl bg-amber-50 border border-amber-100 p-4">
                                        <p className="text-[10px] font-black text-amber-500 uppercase tracking-widest">À rapprocher</p>
                                        <p className="text-2xl font-black text-amber-700">{Number(selectedPO.quantity_invoiceable || 0).toLocaleString('fr-FR')}</p>
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
                                            <th className="py-3 px-4 text-[10px] font-black text-slate-500 uppercase tracking-widest text-center">Reste</th>
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
                                                <td className="py-4 px-4 text-center font-black text-slate-700 text-lg">{line.quantity_remaining || 0}</td>
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

                                <div className="mt-8 rounded-2xl border border-blue-100 bg-blue-50 p-5">
                                    <div className="flex items-center justify-between mb-4">
                                        <div>
                                            <p className="text-[10px] font-black uppercase tracking-widest text-blue-500">Relances fournisseur</p>
                                            <h4 className="font-black text-blue-950">Historique email et suivi d'envoi</h4>
                                        </div>
                                        {Number(selectedPO.quantity_remaining || 0) > 0 && (
                                            <button onClick={() => handleRemindSupplier(selectedPO.id)} className="px-4 py-3 rounded-xl bg-blue-600 text-white font-black text-sm hover:bg-blue-500">
                                                Envoyer une relance
                                            </button>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                        {(selectedPO.supplier_reminders || []).map(reminder => (
                                            <div key={reminder.id} className="rounded-xl bg-white border border-blue-100 p-4">
                                                <div className="flex items-start justify-between gap-3">
                                                    <div>
                                                        <p className="font-black text-slate-900">{reminder.subject || 'Relance fournisseur'}</p>
                                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                                                            {reminder.recipient || 'Sans destinataire'} · {new Date(reminder.created_at).toLocaleString('fr-FR')}
                                                        </p>
                                                    </div>
                                                    <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg ${
                                                        reminder.status === 'SENT' ? 'bg-emerald-100 text-emerald-700'
                                                            : reminder.status === 'FAILED' ? 'bg-red-100 text-red-700'
                                                                : reminder.status === 'SKIPPED' ? 'bg-amber-100 text-amber-700'
                                                                    : 'bg-slate-100 text-slate-600'
                                                    }`}>
                                                        {reminder.status}
                                                    </span>
                                                </div>
                                                {reminder.error_message && (
                                                    <p className="mt-2 text-xs font-bold text-red-600">{reminder.error_message}</p>
                                                )}
                                                <p className="mt-3 text-xs font-medium text-slate-600 line-clamp-3 whitespace-pre-line">{reminder.message}</p>
                                            </div>
                                        ))}
                                        {(selectedPO.supplier_reminders || []).length === 0 && (
                                            <div className="rounded-xl bg-white border border-blue-100 p-4 text-sm font-bold text-blue-400">
                                                Aucune relance fournisseur enregistrée pour ce bon.
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="mt-8 grid grid-cols-1 xl:grid-cols-[1fr_280px_280px] gap-4">
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
                                                    <button onClick={() => openSupplierInvoiceDetail(invoice, selectedPO)} className="text-left">
                                                        <p className="font-black text-slate-900">{invoice.supplier_reference || invoice.reference}</p>
                                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{invoice.reference} · {new Date(invoice.issue_date).toLocaleDateString('fr-FR')}</p>
                                                        <p className="text-[10px] font-black text-emerald-600 uppercase tracking-widest mt-1">
                                                            Payé {Number(invoice.paid_amount || 0).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}
                                                            {' '}· Reste {Number(invoice.remaining_amount || 0).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}
                                                        </p>
                                                    </button>
                                                    <div className="text-right">
                                                        <p className="font-black text-slate-900">{Number(invoice.total_amount || 0).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</p>
                                                        <p className="text-[10px] font-black text-orange-600 uppercase tracking-widest">{invoice.status}</p>
                                                        <button onClick={() => openSupplierInvoiceDetail(invoice, selectedPO)} className="mt-2 mr-2 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-[10px] font-black uppercase tracking-widest hover:bg-slate-200">
                                                            Fiche
                                                        </button>
                                                        {Number(invoice.remaining_amount || 0) > 0 && (
                                                            <button onClick={() => openSupplierPaymentModal(invoice)} className="mt-2 px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-700 text-[10px] font-black uppercase tracking-widest hover:bg-emerald-200">
                                                                Payer
                                                            </button>
                                                        )}
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
                                    <div className="rounded-2xl border border-red-100 bg-red-50 p-5">
                                        <div className="flex items-start justify-between gap-3 mb-3">
                                            <div>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-red-500">Litiges</p>
                                                <h4 className="font-black text-red-950">Écarts fournisseur</h4>
                                            </div>
                                            <button onClick={() => openDisputeModal({ supplier: selectedPO.supplier, purchaseOrderId: selectedPO.id, title: `Litige ${selectedPO.reference}` })} className="text-xs font-black text-red-700 bg-white border border-red-100 px-3 py-2 rounded-xl">
                                                Ajouter
                                            </button>
                                        </div>
                                        <div className="space-y-2">
                                            {(selectedPO.disputes || []).length > 0 ? selectedPO.disputes.map(dispute => (
                                                <div key={dispute.id} className="rounded-xl bg-white border border-red-100 p-3">
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div>
                                                            <p className="font-black text-sm text-red-950">{dispute.title}</p>
                                                            <p className="text-[10px] font-black uppercase tracking-widest text-red-500">{dispute.reference} · {dispute.category} · {dispute.severity} · {dispute.status}</p>
                                                        </div>
                                                        <div className="flex flex-wrap gap-1 justify-end">
                                                            {dispute.blocks_receipt && <span className="text-[9px] font-black uppercase tracking-widest bg-red-100 text-red-700 px-2 py-1 rounded-md">bloque réception</span>}
                                                            {dispute.blocks_payment && <span className="text-[9px] font-black uppercase tracking-widest bg-orange-100 text-orange-700 px-2 py-1 rounded-md">bloque facture</span>}
                                                        </div>
                                                    </div>
                                                    {dispute.impact_summary && <p className="mt-2 text-xs font-bold text-red-700">{dispute.impact_summary}</p>}
                                                    {(dispute.expected_quantity !== null || dispute.received_quantity !== null || dispute.expected_unit_price !== null || dispute.invoiced_unit_price !== null) && (
                                                        <div className="mt-3 grid grid-cols-2 gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                                                            {dispute.expected_quantity !== null && <span>Attendu: {Number(dispute.expected_quantity).toLocaleString('fr-FR')}</span>}
                                                            {dispute.received_quantity !== null && <span>Reçu: {Number(dispute.received_quantity).toLocaleString('fr-FR')}</span>}
                                                            {dispute.expected_unit_price !== null && <span>Prix attendu: {Number(dispute.expected_unit_price).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</span>}
                                                            {dispute.invoiced_unit_price !== null && <span>Prix facturé: {Number(dispute.invoiced_unit_price).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}</span>}
                                                        </div>
                                                    )}
                                                    {dispute.expected_action && <p className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-500">Action attendue: {dispute.expected_action}</p>}
                                                    {dispute.status !== 'RESOLVED' && (
                                                        <div className="mt-3 flex flex-wrap gap-2">
                                                            {dispute.status === 'OPEN' && (
                                                                <button onClick={() => handleStartDispute(dispute.id)} className="text-[10px] font-black text-blue-700 bg-blue-100 px-2 py-1 rounded-lg">
                                                                    Prendre en charge
                                                                </button>
                                                            )}
                                                            <button onClick={() => handleResolveDispute(dispute.id)} className="text-[10px] font-black text-emerald-700 bg-emerald-100 px-2 py-1 rounded-lg">
                                                                Résoudre
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            )) : (
                                                <p className="text-sm font-bold text-red-400">Aucun litige sur ce bon.</p>
                                            )}
                                        </div>
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
                                    <Plus className="w-3.5 h-3.5" /> {createMode === 'request' ? 'Demande achat' : 'Achat fournisseur'}
                                </div>
                                <h3 className="font-black text-3xl">{createMode === 'request' ? "Nouvelle demande d'achat" : 'Nouveau bon de commande'}</h3>
                                <p className="text-sm font-medium text-slate-300 mt-1">
                                    {createMode === 'request'
                                        ? "La demande devra être validée avant création du bon fournisseur."
                                        : "Sélection fournisseur, articles, prix et conditions avant validation."}
                                </p>
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
                                {createMode === 'request' ? "Soumettre la demande" : "Valider la commande"}
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

            {/* SUPPLIER PAYMENT MODAL */}
            {supplierPaymentTarget && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-xl w-full border border-slate-100 overflow-hidden">
                        <div className="px-8 py-6 bg-emerald-950 text-white flex justify-between items-start">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-200 mb-2">Paiement fournisseur</p>
                                <h3 className="font-black text-3xl">{supplierPaymentTarget.supplier_reference || supplierPaymentTarget.reference}</h3>
                                <p className="text-sm font-bold text-emerald-100 mt-1">
                                    Reste à payer {Number(supplierPaymentTarget.remaining_amount || 0).toLocaleString('fr-FR', {style:'currency', currency:'EUR'})}
                                </p>
                            </div>
                            <button onClick={()=>setSupplierPaymentTarget(null)} className="text-emerald-100 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>
                        <div className="p-8 bg-slate-50 space-y-5">
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Montant payé</label>
                                <input type="number" min="0" step="0.01" value={supplierPaymentForm.amount} onChange={e=>setSupplierPaymentForm({...supplierPaymentForm, amount: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-black text-emerald-700 text-xl outline-none focus:ring-2 focus:ring-emerald-500"/>
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Méthode</label>
                                    <select value={supplierPaymentForm.method} onChange={e=>setSupplierPaymentForm({...supplierPaymentForm, method: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                        <option value="TRANSFER">Virement</option>
                                        <option value="CHEQUE">Chèque</option>
                                        <option value="CARD">Carte</option>
                                        <option value="CASH">Espèces</option>
                                        <option value="OTHER">Autre</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Référence paiement</label>
                                    <input value={supplierPaymentForm.reference} onChange={e=>setSupplierPaymentForm({...supplierPaymentForm, reference: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Réf. banque, chèque..."/>
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Notes paiement</label>
                                <textarea value={supplierPaymentForm.notes} onChange={e=>setSupplierPaymentForm({...supplierPaymentForm, notes: e.target.value})} className="w-full min-h-[90px] bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500 resize-none" placeholder="Remarque comptable, échéance, justificatif..."/>
                            </div>
                        </div>
                        <div className="px-8 py-5 bg-white border-t border-slate-100 flex justify-between items-center">
                            <button onClick={()=>setSupplierPaymentTarget(null)} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-black hover:bg-slate-50">Annuler</button>
                            <button onClick={handlePaySupplierInvoice} className="px-8 py-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                                Enregistrer paiement
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {selectedSupplierInvoice && (
                <SupplierInvoiceDetailModal
                    invoice={selectedSupplierInvoice.invoice}
                    purchaseOrder={selectedSupplierInvoice.purchaseOrder}
                    disputes={(selectedSupplierInvoice.purchaseOrder?.disputes || []).filter(dispute => (
                        dispute.supplier_invoice_id === selectedSupplierInvoice.invoice.id
                        || (!dispute.supplier_invoice_id && dispute.purchase_order_id === selectedSupplierInvoice.purchaseOrder?.id)
                    ))}
                    onClose={() => setSelectedSupplierInvoice(null)}
                    onPay={openSupplierPaymentModal}
                    onOpenPO={openPODetails}
                />
            )}

            {/* SUPPLIER DISPUTE MODAL */}
            {showDisputeModal && (
                <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl max-w-5xl w-full border border-slate-100 overflow-hidden">
                        <div className="px-8 py-6 bg-red-950 text-white flex justify-between items-start">
                            <div>
                                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/15 border border-red-300/20 text-red-100 text-[10px] font-black uppercase tracking-widest mb-3">
                                    <AlertTriangle className="w-3.5 h-3.5"/> Litige fournisseur
                                </div>
                                <h3 className="font-black text-3xl">Déclarer un litige</h3>
                                <p className="text-sm font-medium text-red-100 mt-1">
                                    {disputeForm.supplier || 'Fournisseur'} {disputeForm.purchase_order_id ? '· lié au bon sélectionné' : ''}
                                </p>
                            </div>
                            <button onClick={()=>setShowDisputeModal(false)} className="text-red-100 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                        </div>

                        <div className="p-8 bg-slate-50 space-y-6 max-h-[70vh] overflow-y-auto">
                            <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-5">
                                <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Identification</p>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Fournisseur</label>
                                        <input value={disputeForm.supplier} onChange={e=>setDisputeForm({...disputeForm, supplier: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500" placeholder="Nom fournisseur"/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Catégorie</label>
                                        <select value={disputeForm.category} onChange={e=>setDisputeForm({...disputeForm, category: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500">
                                            <option value="DELAY">Retard livraison</option>
                                            <option value="QUANTITY">Quantité manquante</option>
                                            <option value="QUALITY">Article non conforme</option>
                                            <option value="PRICE">Prix facture différent</option>
                                            <option value="DOCUMENT">Document manquant</option>
                                            <option value="OTHER">Autre</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Objet du litige</label>
                                        <input value={disputeForm.title} onChange={e=>setDisputeForm({...disputeForm, title: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500" placeholder="Ex: Quantité manquante, prix facture incohérent..."/>
                                    </div>
                                </div>
                                <div className="rounded-2xl bg-red-50 border border-red-100 p-5 space-y-4">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-red-500">Impact opérationnel</p>
                                    <div>
                                        <label className="block text-xs font-black text-red-400 uppercase tracking-widest mb-1.5">Sévérité</label>
                                        <select value={disputeForm.severity} onChange={e=>setDisputeForm({...disputeForm, severity: e.target.value})} className="w-full bg-white border border-red-100 rounded-xl p-3 font-bold text-red-950 outline-none focus:ring-2 focus:ring-red-500">
                                            <option value="LOW">Faible</option>
                                            <option value="MEDIUM">Moyenne</option>
                                            <option value="HIGH">Haute</option>
                                            <option value="BLOCKING">Bloquant</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-red-400 uppercase tracking-widest mb-1.5">Action attendue</label>
                                        <select value={disputeForm.expected_action} onChange={e=>setDisputeForm({...disputeForm, expected_action: e.target.value})} className="w-full bg-white border border-red-100 rounded-xl p-3 font-bold text-red-950 outline-none focus:ring-2 focus:ring-red-500">
                                            <option value="INFO">Information fournisseur</option>
                                            <option value="REDELIVER">Relivrer le manquant</option>
                                            <option value="REPLACE">Remplacer / reprendre</option>
                                            <option value="PRICE_CORRECTION">Corriger le prix</option>
                                            <option value="CREDIT_NOTE">Émettre un avoir</option>
                                            <option value="OTHER">Autre action</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-red-400 uppercase tracking-widest mb-1.5">Échéance attendue</label>
                                        <input type="date" value={disputeForm.due_date} onChange={e=>setDisputeForm({...disputeForm, due_date: e.target.value})} className="w-full bg-white border border-red-100 rounded-xl p-3 font-bold text-red-950 outline-none focus:ring-2 focus:ring-red-500"/>
                                    </div>
                                    <label className="flex items-center gap-3 rounded-xl bg-white border border-red-100 p-3 text-sm font-black text-red-900">
                                        <input type="checkbox" checked={disputeForm.blocks_receipt} onChange={e=>setDisputeForm({...disputeForm, blocks_receipt: e.target.checked})} className="w-4 h-4"/>
                                        Bloquer les prochaines réceptions
                                    </label>
                                    <label className="flex items-center gap-3 rounded-xl bg-white border border-red-100 p-3 text-sm font-black text-red-900">
                                        <input type="checkbox" checked={disputeForm.blocks_payment} onChange={e=>setDisputeForm({...disputeForm, blocks_payment: e.target.checked})} className="w-4 h-4"/>
                                        Bloquer le rapprochement facture
                                    </label>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Quantité attendue</label>
                                    <input type="number" min="0" step="0.01" value={disputeForm.expected_quantity} onChange={e=>setDisputeForm({...disputeForm, expected_quantity: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500"/>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Quantité reçue</label>
                                    <input type="number" min="0" step="0.01" value={disputeForm.received_quantity} onChange={e=>setDisputeForm({...disputeForm, received_quantity: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500"/>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Prix attendu</label>
                                    <input type="number" min="0" step="0.01" value={disputeForm.expected_unit_price} onChange={e=>setDisputeForm({...disputeForm, expected_unit_price: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500"/>
                                </div>
                                <div>
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Prix facturé</label>
                                    <input type="number" min="0" step="0.01" value={disputeForm.invoiced_unit_price} onChange={e=>setDisputeForm({...disputeForm, invoiced_unit_price: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500"/>
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Impact résumé</label>
                                <input value={disputeForm.impact_summary} onChange={e=>setDisputeForm({...disputeForm, impact_summary: e.target.value})} className="w-full bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500" placeholder="Ex: chantier bloqué, paiement suspendu, relivraison attendue..."/>
                            </div>
                            <div>
                                <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1.5">Description détaillée</label>
                                <textarea value={disputeForm.description} onChange={e=>setDisputeForm({...disputeForm, description: e.target.value})} className="w-full min-h-[120px] bg-white border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-red-500 resize-none" placeholder="Décrire l'écart constaté, les pièces concernées et l'action attendue."/>
                            </div>
                        </div>

                        <div className="px-8 py-5 bg-white border-t border-slate-100 flex justify-between items-center">
                            <button onClick={()=>setShowDisputeModal(false)} className="px-5 py-3 rounded-xl border border-slate-200 text-slate-600 font-black hover:bg-slate-50">Annuler</button>
                            <button onClick={handleCreateDispute} disabled={!disputeForm.supplier || !disputeForm.title.trim()} className="px-8 py-4 bg-red-600 disabled:bg-slate-300 hover:bg-red-500 text-white rounded-xl font-black shadow-lg flex justify-center items-center gap-2 text-lg">
                                Ouvrir le litige
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
                                <div className="grid grid-cols-[1fr_180px] gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Adresse fournisseur</label>
                                        <input type="text" value={newSupplier.address} onChange={e=>setNewSupplier({...newSupplier, address: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Adresse complète"/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Pays</label>
                                        <input list="supplier-country-options" type="text" value={newSupplier.country} onChange={e=>setNewSupplier({...newSupplier, country: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="France"/>
                                        <datalist id="supplier-country-options">
                                            <option value="France" />
                                            <option value="Espagne" />
                                            <option value="Italie" />
                                            <option value="Allemagne" />
                                            <option value="Portugal" />
                                            <option value="Belgique" />
                                            <option value="Cameroun" />
                                        </datalist>
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Statut fournisseur</label>
                                        <select value={newSupplier.supplier_status} onChange={e=>setNewSupplier({...newSupplier, supplier_status: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                            <option value="ACTIVE">Actif</option>
                                            <option value="TO_QUALIFY">À qualifier</option>
                                            <option value="STRATEGIC">Stratégique</option>
                                            <option value="BLOCKED">Bloqué</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Catégorie</label>
                                        <select value={newSupplier.supplier_category} onChange={e=>setNewSupplier({...newSupplier, supplier_category: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                            <option value="ALUMINIUM">Aluminium</option>
                                            <option value="PVC">PVC</option>
                                            <option value="QUINCAILLERIE">Quincaillerie</option>
                                            <option value="VITRAGE">Vitrage</option>
                                            <option value="TRANSPORT">Transport</option>
                                            <option value="SOUS_TRAITANCE">Sous-traitance</option>
                                            <option value="AUTRE">Autre</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">SIRET / TVA</label>
                                        <input type="text" value={newSupplier.tax_id} onChange={e=>setNewSupplier({...newSupplier, tax_id: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="FR..."/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Devise</label>
                                        <select value={newSupplier.default_currency} onChange={e=>setNewSupplier({...newSupplier, default_currency: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500">
                                            <option value="EUR">EUR</option>
                                            <option value="XAF">XAF</option>
                                            <option value="USD">USD</option>
                                            <option value="GBP">GBP</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Délai moyen</label>
                                        <input type="number" min="0" value={newSupplier.lead_time_days} onChange={e=>setNewSupplier({...newSupplier, lead_time_days: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="jours"/>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Paiement</label>
                                        <input type="text" value={newSupplier.payment_terms} onChange={e=>setNewSupplier({...newSupplier, payment_terms: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="30j fin de mois"/>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Incoterm</label>
                                        <input type="text" value={newSupplier.incoterm} onChange={e=>setNewSupplier({...newSupplier, incoterm: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="EXW, DAP, FCA..."/>
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
                                    <label className="block text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Conditions livraison</label>
                                    <input type="text" value={newSupplier.delivery_terms} onChange={e=>setNewSupplier({...newSupplier, delivery_terms: e.target.value})} className="w-full bg-slate-50 border border-slate-200 rounded-xl p-3 font-bold text-slate-800 outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Franco, transporteur dédié, dépôt, palette..."/>
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

const SupplierInvoiceDetailModal = ({ invoice, purchaseOrder, disputes = [], onClose, onPay, onOpenPO }) => {
    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const remainingAmount = Number(invoice.remaining_amount || 0);
    const paidAmount = Number(invoice.paid_amount || 0);
    const totalAmount = Number(invoice.total_amount || 0);
    const paidRatio = totalAmount > 0 ? Math.min((paidAmount / totalAmount) * 100, 100) : 0;
    const isOverdue = invoice.due_date && remainingAmount > 0 && new Date(invoice.due_date) < new Date(new Date().toDateString());
    const paymentBlocked = disputes.some(dispute => dispute.blocks_payment && ['OPEN', 'IN_PROGRESS'].includes(dispute.status));

    return (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl shadow-2xl max-w-6xl w-full border border-slate-100 max-h-[92vh] overflow-hidden flex flex-col">
                <div className="px-8 py-6 bg-slate-950 text-white flex justify-between items-start gap-6">
                    <div>
                        <p className="text-[10px] font-black uppercase tracking-widest text-indigo-200 mb-2">Fiche facture fournisseur</p>
                        <h3 className="font-black text-3xl">{invoice.supplier_reference || invoice.reference}</h3>
                        <p className="text-sm font-bold text-slate-300 mt-1">
                            {purchaseOrder?.supplier || invoice.supplier || 'Fournisseur'} · {invoice.reference}
                        </p>
                    </div>
                    <div className="flex items-start gap-3">
                        {purchaseOrder?.id && (
                            <button onClick={() => onOpenPO(purchaseOrder.id)} className="px-4 py-3 rounded-xl bg-white/10 border border-white/10 text-white font-black text-sm hover:bg-white/20">
                                Ouvrir le bon
                            </button>
                        )}
                        <button onClick={onClose} className="text-slate-300 hover:bg-white/10 p-2 rounded-full"><X className="w-5 h-5"/></button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto bg-slate-50 p-8 space-y-6">
                    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                        <div className="rounded-2xl bg-white border border-slate-200 p-5">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total facture</p>
                            <p className="text-3xl font-black text-slate-950 mt-2">{formatMoney(totalAmount)}</p>
                        </div>
                        <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-5">
                            <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500">Déjà payé</p>
                            <p className="text-3xl font-black text-emerald-700 mt-2">{formatMoney(paidAmount)}</p>
                        </div>
                        <div className={`rounded-2xl border p-5 ${remainingAmount > 0 ? 'bg-orange-50 border-orange-100' : 'bg-emerald-50 border-emerald-100'}`}>
                            <p className={`text-[10px] font-black uppercase tracking-widest ${remainingAmount > 0 ? 'text-orange-500' : 'text-emerald-500'}`}>Reste à payer</p>
                            <p className={`text-3xl font-black mt-2 ${remainingAmount > 0 ? 'text-orange-700' : 'text-emerald-700'}`}>{formatMoney(remainingAmount)}</p>
                        </div>
                        <div className={`rounded-2xl border p-5 ${paymentBlocked ? 'bg-rose-50 border-rose-100' : isOverdue ? 'bg-red-50 border-red-100' : 'bg-indigo-50 border-indigo-100'}`}>
                            <p className={`text-[10px] font-black uppercase tracking-widest ${paymentBlocked ? 'text-rose-500' : isOverdue ? 'text-red-500' : 'text-indigo-500'}`}>Statut paiement</p>
                            <p className={`text-2xl font-black mt-2 ${paymentBlocked ? 'text-rose-700' : isOverdue ? 'text-red-700' : 'text-indigo-700'}`}>
                                {paymentBlocked ? 'Bloqué' : remainingAmount <= 0 ? 'Payée' : isOverdue ? 'En retard' : 'À payer'}
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-[1.2fr_0.8fr] gap-6">
                        <div className="space-y-6">
                            <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
                                <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                    <div>
                                        <h4 className="font-black text-slate-900">Lignes rapprochées</h4>
                                        <p className="text-xs font-bold text-slate-500">Quantités facturées issues des réceptions fournisseur.</p>
                                    </div>
                                    <span className="text-xs font-black text-slate-400">{invoice.lines?.length || 0} ligne(s)</span>
                                </div>
                                <div className="divide-y divide-slate-100">
                                    {(invoice.lines || []).map(line => (
                                        <div key={line.id} className="grid grid-cols-[1fr_90px_110px_120px] gap-4 items-center p-5">
                                            <div>
                                                <p className="font-black text-slate-900">{line.description}</p>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Ligne achat #{line.purchase_order_line_id}</p>
                                            </div>
                                            <div className="text-center">
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Qté</p>
                                                <p className="font-black text-slate-900">{Number(line.quantity || 0).toLocaleString('fr-FR')}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">PU HT</p>
                                                <p className="font-black text-slate-900">{formatMoney(line.unit_price)}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total</p>
                                                <p className="font-black text-slate-950">{formatMoney(line.line_total)}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden">
                                <div className="px-5 py-4 border-b border-slate-100">
                                    <h4 className="font-black text-slate-900">Historique paiements</h4>
                                    <p className="text-xs font-bold text-slate-500">Traçabilité des règlements enregistrés.</p>
                                </div>
                                <div className="divide-y divide-slate-100">
                                    {(invoice.payments || []).map(payment => (
                                        <div key={payment.id} className="p-5 flex items-center justify-between gap-4">
                                            <div>
                                                <p className="font-black text-slate-900">{payment.method || 'Paiement'}</p>
                                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                                                    {payment.payment_date ? new Date(payment.payment_date).toLocaleDateString('fr-FR') : 'Date non renseignée'} · {payment.created_by || 'Système'}
                                                </p>
                                                {payment.reference && <p className="text-xs font-bold text-slate-500 mt-1">{payment.reference}</p>}
                                            </div>
                                            <p className="font-black text-emerald-700">{formatMoney(payment.amount)}</p>
                                        </div>
                                    ))}
                                    {(invoice.payments || []).length === 0 && (
                                        <div className="p-6 text-sm font-bold text-slate-400">Aucun paiement enregistré.</div>
                                    )}
                                </div>
                            </div>
                        </div>

                        <div className="space-y-6">
                            <div className="rounded-2xl bg-white border border-slate-200 p-5">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">Informations</p>
                                <div className="space-y-3 text-sm font-bold text-slate-700">
                                    <div className="flex justify-between gap-4"><span>Émission</span><span>{invoice.issue_date ? new Date(invoice.issue_date).toLocaleDateString('fr-FR') : '-'}</span></div>
                                    <div className="flex justify-between gap-4"><span>Échéance</span><span>{invoice.due_date ? new Date(invoice.due_date).toLocaleDateString('fr-FR') : 'Sans échéance'}</span></div>
                                    <div className="flex justify-between gap-4"><span>Statut</span><span>{invoice.status}</span></div>
                                    <div className="flex justify-between gap-4"><span>Bon fournisseur</span><span>{purchaseOrder?.reference || '-'}</span></div>
                                </div>
                                <div className="mt-5 h-2 rounded-full bg-slate-100 overflow-hidden">
                                    <div className="h-full bg-emerald-500" style={{ width: `${paidRatio}%` }} />
                                </div>
                                {remainingAmount > 0 && (
                                    <button
                                        onClick={() => onPay(invoice)}
                                        disabled={paymentBlocked}
                                        className="mt-5 w-full px-5 py-4 rounded-xl bg-emerald-600 disabled:bg-slate-300 text-white font-black hover:bg-emerald-500"
                                    >
                                        {paymentBlocked ? 'Paiement bloqué' : 'Enregistrer paiement'}
                                    </button>
                                )}
                            </div>

                            <div className="rounded-2xl bg-red-50 border border-red-100 p-5">
                                <p className="text-[10px] font-black uppercase tracking-widest text-red-500 mb-3">Litiges liés</p>
                                <div className="space-y-3">
                                    {disputes.map(dispute => (
                                        <div key={dispute.id} className="rounded-xl bg-white border border-red-100 p-4">
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    <p className="font-black text-red-950">{dispute.title}</p>
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-red-500">{dispute.reference} · {dispute.status}</p>
                                                </div>
                                                {dispute.blocks_payment && <span className="text-[9px] font-black uppercase tracking-widest bg-orange-100 text-orange-700 px-2 py-1 rounded-md">bloque paiement</span>}
                                            </div>
                                            {dispute.impact_summary && <p className="text-xs font-bold text-red-700 mt-2">{dispute.impact_summary}</p>}
                                        </div>
                                    ))}
                                    {disputes.length === 0 && (
                                        <p className="text-sm font-bold text-red-400">Aucun litige lié à cette facture.</p>
                                    )}
                                </div>
                            </div>

                            {invoice.notes && (
                                <div className="rounded-2xl bg-amber-50 border border-amber-100 p-5">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-amber-500 mb-2">Notes rapprochement</p>
                                    <p className="text-sm font-bold text-amber-900 whitespace-pre-line">{invoice.notes}</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const PurchaseDashboardOverview = ({ dashboard, setCurrentTab, openPODetails, openSupplierInvoiceDetail, handleRemindSupplier }) => {
    const summary = dashboard?.summary || {};
    const actions = dashboard?.actions || [];
    const paymentSchedule = dashboard?.payment_schedule || [];
    const cashOutForecast = dashboard?.cash_out_forecast || [];
    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const cards = [
        { label: 'Commandes ouvertes', value: summary.open_orders || 0, tone: 'bg-blue-50 border-blue-100 text-blue-700', tab: 'orders' },
        { label: 'À réceptionner', value: summary.to_receive || 0, tone: 'bg-emerald-50 border-emerald-100 text-emerald-700', tab: 'orders' },
        { label: 'Retards fournisseur', value: summary.late_orders || 0, tone: 'bg-red-50 border-red-100 text-red-700', tab: 'orders' },
        { label: 'Factures à rapprocher', value: summary.to_invoice || 0, tone: 'bg-orange-50 border-orange-100 text-orange-700', tab: 'orders' },
        { label: 'Factures à payer', value: summary.supplier_invoices_to_pay || 0, tone: 'bg-indigo-50 border-indigo-100 text-indigo-700', tab: 'orders' },
        { label: 'Paiements bloqués', value: summary.supplier_invoices_blocked || 0, tone: 'bg-rose-50 border-rose-100 text-rose-700', tab: 'suppliers' },
        { label: 'Demandes à valider', value: summary.pending_requests || 0, tone: 'bg-amber-50 border-amber-100 text-amber-700', tab: 'requests' },
        { label: 'Litiges ouverts', value: summary.open_disputes || 0, tone: 'bg-rose-50 border-rose-100 text-rose-700', tab: 'suppliers' },
    ];

    return (
        <div className="p-8 w-full space-y-6">
            <div className="bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden">
                <div className="px-8 py-7 bg-slate-900 text-white flex items-start justify-between gap-6">
                    <div>
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-300/20 text-blue-200 text-[10px] font-black uppercase tracking-widest mb-3">
                            <ShoppingCart className="w-3.5 h-3.5" /> Pilotage achats
                        </div>
                        <h2 className="text-3xl font-black tracking-tight">Achats à piloter maintenant</h2>
                        <p className="text-sm font-bold text-slate-300 mt-1">Retards, réceptions, factures fournisseur et litiges au même endroit.</p>
                    </div>
                    <div className="text-right">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Engagé HT</p>
                        <p className="text-3xl font-black text-emerald-300">{formatMoney(summary.amount_committed)}</p>
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-2">À payer fournisseur</p>
                        <p className="text-xl font-black text-orange-200">{formatMoney(summary.amount_to_pay)}</p>
                    </div>
                </div>

                <div className="p-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {cards.map(card => (
                            <button key={card.label} onClick={() => setCurrentTab(card.tab)} className={`text-left rounded-2xl border p-5 ${card.tone} hover:-translate-y-0.5 transition-transform`}>
                                <p className="text-[10px] font-black uppercase tracking-widest opacity-70">{card.label}</p>
                                <p className="text-4xl font-black mt-2">{card.value}</p>
                            </button>
                        ))}
                    </div>

                    <div className="mt-6 grid grid-cols-1 xl:grid-cols-[0.9fr_1.4fr] gap-6">
                        <div className="rounded-2xl bg-slate-900 text-white p-5 shadow-lg">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Cash-out prévisionnel</p>
                            <h3 className="font-black text-2xl mt-1">Décaissements fournisseur</h3>
                            <div className="mt-5 grid grid-cols-3 gap-3">
                                {cashOutForecast.map(item => (
                                    <div key={item.days} className="rounded-xl bg-white/10 border border-white/10 p-3">
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{item.label}</p>
                                        <p className="font-black text-lg mt-1">{formatMoney(item.amount)}</p>
                                    </div>
                                ))}
                                {cashOutForecast.length === 0 && (
                                    <div className="col-span-3 rounded-xl bg-white/10 border border-white/10 p-4 text-sm font-bold text-slate-300">
                                        Aucun décaissement fournisseur prévisible.
                                    </div>
                                )}
                            </div>
                            <div className="mt-4 grid grid-cols-2 gap-3 text-sm font-black">
                                <div className="rounded-xl bg-red-500/10 border border-red-300/20 p-3 text-red-100">
                                    <p className="text-[10px] uppercase tracking-widest opacity-70">En retard</p>
                                    <p>{formatMoney(summary.amount_overdue)} · {summary.supplier_invoices_overdue || 0} facture(s)</p>
                                </div>
                                <div className="rounded-xl bg-rose-500/10 border border-rose-300/20 p-3 text-rose-100">
                                    <p className="text-[10px] uppercase tracking-widest opacity-70">Bloqué litige</p>
                                    <p>{formatMoney(summary.amount_blocked)} · {summary.supplier_invoices_blocked || 0} facture(s)</p>
                                </div>
                            </div>
                        </div>

                        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                <div>
                                    <h3 className="font-black text-slate-900">Factures fournisseur à payer</h3>
                                    <p className="text-xs font-bold text-slate-500">Échéances, retards et blocages avant paiement.</p>
                                </div>
                                <span className="text-xs font-black text-slate-400">{paymentSchedule.length} ligne(s)</span>
                            </div>
                            <div className="divide-y divide-slate-100 max-h-[320px] overflow-y-auto">
                                {paymentSchedule.slice(0, 8).map(invoice => (
                                    <div key={invoice.invoice_id} className="p-4 flex items-center justify-between gap-4">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg ${
                                                    invoice.is_blocked ? 'bg-rose-100 text-rose-700'
                                                        : invoice.is_overdue ? 'bg-red-100 text-red-700'
                                                            : 'bg-indigo-100 text-indigo-700'
                                                }`}>
                                                    {invoice.is_blocked ? 'Bloqué' : invoice.is_overdue ? 'En retard' : 'À payer'}
                                                </span>
                                                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                                                    {invoice.due_date ? new Date(invoice.due_date).toLocaleDateString('fr-FR') : 'Sans échéance'}
                                                </span>
                                            </div>
                                            <h4 className="font-black text-slate-900 mt-2">{invoice.supplier}</h4>
                                            <p className="text-xs font-bold text-slate-500">
                                                {invoice.supplier_reference || invoice.reference}
                                                {invoice.blocker_references?.length ? ` · litige ${invoice.blocker_references.join(', ')}` : ''}
                                            </p>
                                        </div>
                                        <div className="text-right shrink-0">
                                            <p className="font-black text-slate-900">{formatMoney(invoice.remaining_amount)}</p>
                                            {invoice.purchase_order_id && (
                                                <button onClick={() => openSupplierInvoiceDetail(invoice)} className="mt-2 px-3 py-2 rounded-xl bg-slate-900 text-white font-black text-xs hover:bg-slate-800">
                                                    Fiche facture
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {paymentSchedule.length === 0 && (
                                    <div className="p-8 text-center text-slate-400 font-bold">Aucune facture fournisseur à payer.</div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="mt-8 grid grid-cols-1 xl:grid-cols-[1.4fr_0.8fr] gap-6">
                        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                                <div>
                                    <h3 className="font-black text-slate-900">Actions prioritaires</h3>
                                    <p className="text-xs font-bold text-slate-500">Les lignes viennent des commandes, demandes, litiges et factures à rapprocher.</p>
                                </div>
                                <span className="text-xs font-black text-slate-400">{actions.length} action(s)</span>
                            </div>
                            <div className="divide-y divide-slate-100">
                                {actions.slice(0, 10).map(action => (
                                    <div key={`${action.type}-${action.reference}-${action.purchase_order_id || action.purchase_request_id || action.dispute_id}`} className="p-5 flex items-center justify-between gap-4">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg ${
                                                    action.type === 'LATE' ? 'bg-red-100 text-red-700'
                                                        : action.type === 'INVOICE' ? 'bg-orange-100 text-orange-700'
                                                            : action.type === 'DISPUTE' ? 'bg-rose-100 text-rose-700'
                                                                : 'bg-slate-100 text-slate-600'
                                                }`}>
                                                    {action.type}
                                                </span>
                                                {(action.late_days > 0 || action.overdue_days > 0) && <span className="text-[10px] font-black text-red-600">{action.late_days || action.overdue_days} jour(s) retard</span>}
                                            </div>
                                            <h4 className="font-black text-slate-900 mt-2">{action.label}</h4>
                                            <p className="text-xs font-bold text-slate-500">
                                                {action.supplier || 'Achats'} · {action.reference}
                                                {action.remaining_amount ? ` · ${formatMoney(action.remaining_amount)}` : ''}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {action.type === 'LATE' && action.purchase_order_id && (
                                                <button onClick={() => handleRemindSupplier(action.purchase_order_id)} className="px-3 py-2 rounded-xl bg-amber-100 text-amber-800 font-black text-xs hover:bg-amber-200">
                                                    Relancer
                                                </button>
                                            )}
                                            {action.purchase_order_id ? (
                                                <button onClick={() => openPODetails(action.purchase_order_id)} className="px-3 py-2 rounded-xl bg-slate-900 text-white font-black text-xs hover:bg-slate-800">
                                                    Ouvrir
                                                </button>
                                            ) : (
                                                <button onClick={() => setCurrentTab(action.type === 'REQUEST' ? 'requests' : 'suppliers')} className="px-3 py-2 rounded-xl bg-slate-900 text-white font-black text-xs hover:bg-slate-800">
                                                    Traiter
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                                {actions.length === 0 && (
                                    <div className="p-8 text-center text-slate-400 font-bold">Aucune action fournisseur urgente.</div>
                                )}
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Règle métier</p>
                                <h3 className="font-black text-slate-900">On ne paie que ce qui est reçu.</h3>
                                <p className="text-sm font-bold text-slate-600 mt-2">Le rapprochement facture fournisseur reste bloqué par les quantités réceptionnées. Les retards et litiges doivent être visibles avant paiement.</p>
                            </div>
                            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5">
                                <p className="text-[10px] font-black uppercase tracking-widest text-emerald-500 mb-2">Raccourcis</p>
                                <div className="grid grid-cols-1 gap-2">
                                    <button onClick={() => setCurrentTab('requests')} className="rounded-xl bg-white border border-emerald-100 px-4 py-3 text-left font-black text-emerald-800">Voir les demandes d'achat</button>
                                    <button onClick={() => setCurrentTab('orders')} className="rounded-xl bg-white border border-emerald-100 px-4 py-3 text-left font-black text-emerald-800">Voir les bons fournisseur</button>
                                    <button onClick={() => setCurrentTab('suppliers')} className="rounded-xl bg-white border border-emerald-100 px-4 py-3 text-left font-black text-emerald-800">Voir les fournisseurs</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

const PurchaseRequestsView = ({ requests, canApprove, canOrder, onApprove, onReject, onConvert }) => {
    const pending = requests.filter(request => request.status === 'PENDING_APPROVAL');
    const approved = requests.filter(request => request.status === 'APPROVED');
    const closed = requests.filter(request => ['CONVERTED', 'REJECTED', 'CANCELLED'].includes(request.status));

    const renderRequest = (request) => (
        <div key={request.id} className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-5 py-4 bg-slate-50 border-b border-slate-100 flex flex-wrap items-start justify-between gap-3">
                <div>
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Demande d'achat</p>
                    <h3 className="text-xl font-black text-slate-900">{request.reference}</h3>
                    <p className="text-sm font-bold text-slate-500">{request.supplier} · demandé par {request.requested_by || 'Système'}</p>
                </div>
                <div className="text-right">
                    <span className={`inline-flex px-3 py-1 rounded-lg text-xs font-black ${
                        request.status === 'PENDING_APPROVAL' ? 'bg-amber-100 text-amber-700'
                            : request.status === 'APPROVED' ? 'bg-emerald-100 text-emerald-700'
                                : request.status === 'CONVERTED' ? 'bg-blue-100 text-blue-700'
                                    : 'bg-red-100 text-red-700'
                    }`}>{request.status}</span>
                    <p className="mt-2 text-2xl font-black text-slate-900">{Number(request.total_amount || 0).toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</p>
                </div>
            </div>
            <div className="p-5 grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-4">
                <div className="space-y-3">
                    {(request.lines || []).map(line => (
                        <div key={line.id} className="grid grid-cols-[1fr_80px_100px] gap-3 items-center rounded-xl bg-slate-50 border border-slate-100 p-3">
                            <div>
                                {line.need_priority && (
                                    <span className={`inline-flex mb-1 text-[10px] px-2 py-1 rounded-lg font-black uppercase tracking-widest ${priorityTone(line.need_priority).badge}`}>
                                        {priorityLabel(line.need_priority)}
                                    </span>
                                )}
                                <p className="font-black text-slate-900">{line.product_name}</p>
                                <p className="text-[10px] font-mono font-black text-slate-400 uppercase">{line.variant_ref}</p>
                                {line.need_reason && (
                                    <p className="mt-1 text-xs font-bold text-slate-500">{line.need_reason}</p>
                                )}
                            </div>
                            <div className="text-center">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Qté</p>
                                <p className="font-black text-slate-900">{Number(line.quantity || 0).toLocaleString('fr-FR')}</p>
                            </div>
                            <div className="text-right">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total</p>
                                <p className="font-black text-slate-900">{Number(line.line_total || 0).toLocaleString('fr-FR', {style: 'currency', currency: 'EUR'})}</p>
                            </div>
                        </div>
                    ))}
                </div>
                <aside className="rounded-2xl border border-slate-200 bg-white p-4 h-fit">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Contrôle achat</p>
                    <p className="mt-2 text-sm font-bold text-slate-600">{request.sensitivity_reason || 'Validation achat requise avant engagement fournisseur.'}</p>
                    {request.rejection_reason && (
                        <p className="mt-3 rounded-xl bg-red-50 border border-red-100 p-3 text-xs font-bold text-red-700">{request.rejection_reason}</p>
                    )}
                    <div className="mt-4 space-y-2">
                        {request.status === 'PENDING_APPROVAL' && (
                            <>
                                <button disabled={!canApprove} onClick={() => onApprove(request.id)} className="w-full py-3 rounded-xl bg-emerald-600 disabled:bg-slate-300 text-white font-black">Valider</button>
                                <button disabled={!canApprove} onClick={() => onReject(request.id)} className="w-full py-3 rounded-xl border border-red-200 text-red-600 disabled:text-slate-400 disabled:border-slate-200 font-black">Refuser</button>
                            </>
                        )}
                        {request.status === 'APPROVED' && (
                            <button disabled={!canOrder} onClick={() => onConvert(request.id)} className="w-full py-3 rounded-xl bg-blue-600 disabled:bg-slate-300 text-white font-black">Créer le bon fournisseur</button>
                        )}
                        {request.purchase_order_id && (
                            <p className="text-xs font-bold text-blue-700 bg-blue-50 rounded-xl p-3">Bon fournisseur lié #{request.purchase_order_id}</p>
                        )}
                    </div>
                </aside>
            </div>
        </div>
    );

    return (
        <div className="p-8 w-full">
            <div className="bg-white rounded-3xl shadow-xl border border-slate-200 overflow-hidden">
                <div className="px-8 py-6 border-b border-slate-100 bg-slate-900 text-white">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-300/20 text-amber-200 text-[10px] font-black uppercase tracking-widest mb-3">
                        <FileText className="w-3.5 h-3.5" /> Validation achats
                    </div>
                    <h2 className="text-3xl font-black tracking-tight">Demandes d'achat</h2>
                    <p className="text-sm font-medium text-slate-300 mt-1">Aucun engagement fournisseur sans validation quand l'achat est sensible.</p>
                </div>
                <div className="p-8 space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="rounded-2xl bg-amber-50 border border-amber-100 p-5">
                            <p className="text-[10px] font-black text-amber-500 uppercase tracking-widest">À valider</p>
                            <p className="text-3xl font-black text-amber-700">{pending.length}</p>
                        </div>
                        <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-5">
                            <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Validées</p>
                            <p className="text-3xl font-black text-emerald-700">{approved.length}</p>
                        </div>
                        <div className="rounded-2xl bg-slate-50 border border-slate-200 p-5">
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Traitées</p>
                            <p className="text-3xl font-black text-slate-900">{closed.length}</p>
                        </div>
                    </div>
                    <div className="space-y-5">
                        {requests.map(renderRequest)}
                        {requests.length === 0 && (
                            <div className="rounded-3xl border-2 border-dashed border-slate-200 bg-slate-50 py-20 flex flex-col items-center justify-center text-slate-400 font-black">
                                <CheckCircle className="w-12 h-12 mb-4 text-emerald-400" />
                                Aucune demande d'achat à traiter.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

const SmartPurchasingView = ({ needs, groups, summary, loading, refetch, preparePOFromNeeds, canCreatePurchaseOrder }) => {
    const blockedNeeds = needs.filter(need => !need.can_order);
    const criticalNeeds = needs.filter(need => need.priority === 'CRITICAL');
    const urgentNeeds = needs.filter(need => need.priority === 'URGENT');
    const firstOrderableGroup = groups.find(group => group.orderable_count > 0);

    return (
        <div className="p-8 w-full">
            <div className="bg-white rounded-3xl shadow-xl border border-slate-200 overflow-hidden">
                <div className="px-8 py-6 border-b border-slate-100 bg-slate-900 text-white flex justify-between items-start relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-56 h-56 bg-indigo-500/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"></div>
                    <div className="relative z-10">
                        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-300/20 text-indigo-200 text-[10px] font-black uppercase tracking-widest mb-3">
                            <BrainCircuit className="w-3.5 h-3.5" /> Intelligence achats
                        </div>
                        <h2 className="text-3xl font-black tracking-tight">À commander</h2>
                        <p className="text-sm font-medium text-slate-300 mt-1">
                            Besoins nets regroupés par fournisseur avant création des bons de commande.
                        </p>
                    </div>
                    <button onClick={() => refetch()} className="relative z-10 px-4 py-3 rounded-xl bg-white/10 hover:bg-white/15 text-white font-black flex items-center gap-2">
                        <BrainCircuit className="w-4 h-4" /> Recalculer
                    </button>
                </div>

                <div className="p-8 space-y-8">
                    <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
                        <div className="rounded-2xl bg-slate-900 text-white p-5 shadow-lg">
                            <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Besoins</p>
                            <p className="text-3xl font-black">{summary.needs_count ?? needs.length}</p>
                        </div>
                        <div className="rounded-2xl bg-red-50 border border-red-100 p-5">
                            <p className="text-[10px] font-black text-red-500 uppercase tracking-widest">Critiques</p>
                            <p className="text-3xl font-black text-red-700">{summary.critical_count ?? criticalNeeds.length}</p>
                        </div>
                        <div className="rounded-2xl bg-orange-50 border border-orange-100 p-5">
                            <p className="text-[10px] font-black text-orange-500 uppercase tracking-widest">Urgents</p>
                            <p className="text-3xl font-black text-orange-700">{summary.urgent_count ?? urgentNeeds.length}</p>
                        </div>
                        <div className="rounded-2xl bg-indigo-50 border border-indigo-100 p-5">
                            <p className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">Fournisseurs</p>
                            <p className="text-3xl font-black text-indigo-700">{summary.suppliers_count ?? groups.length}</p>
                        </div>
                        <div className="rounded-2xl bg-amber-50 border border-amber-100 p-5">
                            <p className="text-[10px] font-black text-amber-500 uppercase tracking-widest">Bloqués</p>
                            <p className="text-3xl font-black text-amber-700">{summary.blocked_count ?? blockedNeeds.length}</p>
                        </div>
                    </div>

                    {loading ? (
                        <div className="rounded-3xl border-2 border-dashed border-indigo-100 bg-indigo-50/40 py-20 flex flex-col items-center justify-center text-indigo-500 font-black">
                            <BrainCircuit className="w-12 h-12 animate-pulse mb-4" />
                            Calcul des besoins achats...
                        </div>
                    ) : needs.length === 0 ? (
                        <div className="rounded-3xl border-2 border-dashed border-slate-200 bg-slate-50 py-20 flex flex-col items-center justify-center text-slate-400 font-black">
                            <CheckCircle className="w-12 h-12 mb-4 text-emerald-400" />
                            Aucun achat prioritaire détecté.
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 2xl:grid-cols-[1fr_360px] gap-6">
                            <div className="space-y-5">
                                {groups.map(group => {
                                    const orderableGroupNeeds = group.needs.filter(need => need.can_order);
                                    return (
                                        <div key={group.supplier} className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                                            <div className="px-5 py-4 bg-slate-50 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                                                <div>
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Fournisseur proposé</p>
                                                    <h3 className="text-xl font-black text-slate-900 flex items-center gap-2">
                                                        <Truck className="w-5 h-5 text-indigo-500" /> {group.supplier}
                                                    </h3>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    {group.critical_count > 0 && <span className="px-3 py-1 rounded-lg bg-red-100 text-red-700 text-xs font-black">{group.critical_count} critique(s)</span>}
                                                    {group.urgent_count > 0 && <span className="px-3 py-1 rounded-lg bg-orange-100 text-orange-700 text-xs font-black">{group.urgent_count} urgent(s)</span>}
                                                    <span className="px-3 py-1 rounded-lg bg-slate-100 text-slate-600 text-xs font-black">{group.needs.length} ligne(s)</span>
                                                </div>
                                                <button
                                                    onClick={() => preparePOFromNeeds(orderableGroupNeeds, group.supplier)}
                                                    disabled={orderableGroupNeeds.length === 0}
                                                    className="px-4 py-3 rounded-xl bg-blue-600 disabled:bg-slate-300 text-white font-black hover:bg-blue-500 flex items-center gap-2"
                                                >
                                                    <Plus className="w-4 h-4" /> {canCreatePurchaseOrder ? 'Créer bon fournisseur' : 'Créer demande'}
                                                </button>
                                            </div>
                                            <div className="divide-y divide-slate-100">
                                                {group.needs.map(need => (
                                                    <div key={`${need.variant_id}-${need.reference}`} className="px-5 py-4 grid grid-cols-[1fr_120px_120px_150px] gap-4 items-center">
                                                        <div>
                                                            <div className="flex flex-wrap items-center gap-2 mb-1">
                                                                <span className={`text-[10px] px-2 py-1 rounded-lg font-black uppercase tracking-widest ${priorityTone(need.priority).badge}`}>
                                                                    {priorityLabel(need.priority)}
                                                                </span>
                                                                {!need.can_order && (
                                                                    <span className="text-[10px] px-2 py-1 rounded-lg font-black uppercase tracking-widest bg-red-50 text-red-600">
                                                                        {need.blocked_reason}
                                                                    </span>
                                                                )}
                                                            </div>
                                                            <p className="font-black text-slate-900">{need.product_name}</p>
                                                            <p className="text-[10px] font-mono font-black text-slate-400 uppercase">{need.reference}</p>
                                                            <p className="mt-1 text-xs font-bold text-slate-500">{need.reason}</p>
                                                            {need.open_purchase_request_quantity > 0 && (
                                                                <p className="mt-1 text-xs font-black text-blue-600">
                                                                    {need.open_purchase_request_quantity.toLocaleString('fr-FR')} déjà en demande d'achat
                                                                </p>
                                                            )}
                                                        </div>
                                                        <div className="rounded-xl bg-slate-50 border border-slate-100 p-3 text-center">
                                                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Disponible</p>
                                                            <p className="text-xl font-black text-slate-900">{need.current_stock.toLocaleString('fr-FR')}</p>
                                                        </div>
                                                        <div className="rounded-xl bg-indigo-50 border border-indigo-100 p-3 text-center">
                                                            <p className="text-[10px] font-black uppercase tracking-widest text-indigo-400">Suggéré</p>
                                                            <p className="text-xl font-black text-indigo-700">+{need.suggested_quantity.toLocaleString('fr-FR')}</p>
                                                        </div>
                                                        <button
                                                            onClick={() => preparePOFromNeeds([need], need.supplier)}
                                                            disabled={!need.can_order}
                                                            className="px-4 py-3 rounded-xl bg-slate-900 disabled:bg-slate-200 disabled:text-slate-400 text-white font-black hover:bg-slate-800 flex items-center justify-center gap-2"
                                                        >
                                                            {canCreatePurchaseOrder ? 'Commander' : 'Demander'} <ArrowRight className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            <aside className="space-y-4">
                                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                                    <h4 className="font-black text-slate-900 flex items-center gap-2 mb-4">
                                        <Layers className="w-5 h-5 text-indigo-500" /> Règle de calcul
                                    </h4>
                                    <div className="space-y-3 text-sm font-bold text-slate-600">
                                        <p>Le besoin part du stock disponible, des seuils mini et des futures réservations quand l’API les fournit.</p>
                                        <p>Les articles brouillons, sans fournisseur ou avec fournisseur bloqué restent visibles mais non commandables.</p>
                                        <p>La commande générée reste modifiable : prix, remises, dates et quantités doivent être validés par l’acheteur.</p>
                                    </div>
                                </div>
                                <div className="rounded-2xl border border-amber-100 bg-amber-50 p-5">
                                    <h4 className="font-black text-amber-900 flex items-center gap-2 mb-3">
                                        <AlertTriangle className="w-5 h-5" /> À qualifier
                                    </h4>
                                    <p className="text-3xl font-black text-amber-700">{blockedNeeds.length}</p>
                                    <p className="text-sm font-bold text-amber-700 mt-1">besoin(s) visibles mais non transformables en commande automatiquement.</p>
                                </div>
                                {firstOrderableGroup && (
                                    <button
                                        onClick={() => preparePOFromNeeds(firstOrderableGroup.needs.filter(need => need.can_order), firstOrderableGroup.supplier)}
                                        className="w-full px-5 py-4 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white font-black shadow-lg flex items-center justify-center gap-2"
                                    >
                                        <Plus className="w-5 h-5" /> Préparer le fournisseur prioritaire
                                    </button>
                                )}
                            </aside>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const SupplierProfile = ({ sup, purchases, disputes = [], openPODetails, setCurrentTab, openCreatePOForSupplier, openDisputeModal, onStartDispute, onResolveDispute }) => {
    const [activeTab, setActiveTab] = useState('overview');

    const supOrders = purchases.filter(p => p.supplier === sup.name);
    const supDisputes = disputes.filter(dispute => dispute.supplier === sup.name);
    const openSupplierDisputes = supDisputes.filter(dispute => ['OPEN', 'IN_PROGRESS'].includes(dispute.status));
    const formatCurrency = (amount) => Number(amount || 0).toLocaleString('fr-FR', {style: 'currency', currency: sup.default_currency || 'EUR'});
    const orderedQty = (order) => Number(order.quantity_ordered ?? (order.lines || []).reduce((sum, line) => sum + Number(line.quantity || 0), 0));
    const remainingQty = (order) => Number(order.quantity_remaining ?? Math.max(orderedQty(order) - Number(order.quantity_received || 0), 0));
    const invoiceableQty = (order) => Number(order.quantity_invoiceable ?? Math.max(Number(order.quantity_received || 0) - Number(order.quantity_invoiced || 0), 0));
    const totalSpent = supOrders.reduce((sum, order) => sum + (order.total_amount || 0), 0);
    const totalOrders = supOrders.length;
    const receivedOrders = supOrders.filter(o => o.status === 'RECEIVED').length;
    const pendingOrders = supOrders.filter(o => o.status !== 'RECEIVED' && o.status !== 'CANCELLED').length;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const openOrders = supOrders.filter(o => !['RECEIVED', 'CANCELLED'].includes(o.status));
    const toReceiveOrders = supOrders.filter(o => !['RECEIVED', 'CANCELLED'].includes(o.status) && remainingQty(o) > 0);
    const toInvoiceOrders = supOrders.filter(o => invoiceableQty(o) > 0);
    const lateOrders = supOrders.filter(o => {
        if (!o.expected_date || ['RECEIVED', 'CANCELLED'].includes(o.status)) return false;
        const expected = new Date(o.expected_date);
        expected.setHours(0, 0, 0, 0);
        return expected < today;
    });
    const supplierStatus = sup.supplier_status || 'ACTIVE';
    const canOrder = supplierStatus !== 'BLOCKED';
    const statusLabels = {
        ACTIVE: 'Actif',
        TO_QUALIFY: 'À qualifier',
        STRATEGIC: 'Stratégique',
        BLOCKED: 'Bloqué',
    };
    const statusTone = supplierStatus === 'BLOCKED'
        ? 'bg-red-100 text-red-700 border-red-200'
        : supplierStatus === 'TO_QUALIFY'
            ? 'bg-amber-100 text-amber-800 border-amber-200'
            : supplierStatus === 'STRATEGIC'
                ? 'bg-indigo-100 text-indigo-700 border-indigo-200'
                : 'bg-emerald-100 text-emerald-700 border-emerald-200';
    const qualityAlerts = lateOrders.length + toInvoiceOrders.length + supOrders.filter(o => o.status === 'PARTIAL').length + openSupplierDisputes.length;
    const qualityLabel = qualityAlerts === 0 ? 'Stable' : qualityAlerts <= 2 ? 'À surveiller' : 'Sous tension';
    const committedAmount = openOrders.reduce((sum, order) => sum + Number(order.total_amount || 0), 0);
    const quantityToReceive = toReceiveOrders.reduce((sum, order) => sum + remainingQty(order), 0);
    const quantityToInvoice = toInvoiceOrders.reduce((sum, order) => sum + invoiceableQty(order), 0);
    const operationalOrders = [...new Map([...lateOrders, ...toReceiveOrders, ...toInvoiceOrders].map(order => [order.id, order])).values()]
        .sort((a, b) => {
            const aLate = lateOrders.some(order => order.id === a.id) ? 0 : 1;
            const bLate = lateOrders.some(order => order.id === b.id) ? 0 : 1;
            if (aLate !== bLate) return aLate - bLate;
            return new Date(a.expected_date || a.created_at || 0) - new Date(b.expected_date || b.created_at || 0);
        })
        .slice(0, 6);
    const openOrder = (order) => {
        setCurrentTab('orders');
        openPODetails(order.id);
    };
    const getOrderNextAction = (order) => {
        if (lateOrders.some(lateOrder => lateOrder.id === order.id)) return 'Relancer retard';
        if (remainingQty(order) > 0) return 'Réceptionner';
        if (invoiceableQty(order) > 0) return 'Rapprocher facture';
        return order.next_action || 'Voir commande';
    };
    const supplierTimeline = [
        ...supOrders
        .flatMap(order => {
            const events = [{
                key: `${order.id}-created`,
                date: order.order_date || order.created_at,
                label: 'Commande fournisseur',
                detail: `${order.reference} · ${formatCurrency(order.total_amount)}`,
                tone: 'blue',
            }];
            if (Number(order.quantity_received || 0) > 0) {
                events.push({
                    key: `${order.id}-received`,
                    date: order.expected_date || order.order_date || order.created_at,
                    label: order.status === 'RECEIVED' ? 'Réception complète' : 'Réception partielle',
                    detail: `${Number(order.quantity_received || 0).toLocaleString('fr-FR')} unité(s) reçue(s)`,
                    tone: order.status === 'RECEIVED' ? 'emerald' : 'orange',
                });
            }
            if (Number(order.quantity_invoiced || 0) > 0) {
                events.push({
                    key: `${order.id}-invoiced`,
                    date: order.order_date || order.created_at,
                    label: 'Facture rapprochée',
                    detail: `${Number(order.quantity_invoiced || 0).toLocaleString('fr-FR')} unité(s) facturée(s)`,
                    tone: 'slate',
                });
            }
            return events;
        }),
        ...supDisputes.map(dispute => ({
            key: `dispute-${dispute.id}`,
            date: dispute.created_at,
            label: dispute.status === 'RESOLVED' ? 'Litige résolu' : 'Litige fournisseur',
            detail: `${dispute.reference} · ${dispute.title}`,
            tone: dispute.status === 'RESOLVED' ? 'emerald' : 'red',
        })),
    ]
        .sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))
        .slice(0, 6);

    // Average order value
    const avgOrderValue = totalOrders > 0 ? (totalSpent / totalOrders) : 0;
    const actionTiles = [
        {
            label: 'Créer demande',
            detail: canOrder ? 'Demande achat préremplie' : 'Fournisseur bloqué',
            value: '+',
            tone: 'slate',
            disabled: !canOrder,
            onClick: () => openCreatePOForSupplier(sup.name),
        },
        {
            label: 'À réceptionner',
            detail: `${quantityToReceive.toLocaleString('fr-FR')} unité(s) restantes`,
            value: toReceiveOrders.length,
            tone: 'emerald',
            disabled: toReceiveOrders.length === 0,
            onClick: () => openOrder(toReceiveOrders[0]),
        },
        {
            label: 'Factures à rapprocher',
            detail: `${quantityToInvoice.toLocaleString('fr-FR')} unité(s) facturables`,
            value: toInvoiceOrders.length,
            tone: 'orange',
            disabled: toInvoiceOrders.length === 0,
            onClick: () => openOrder(toInvoiceOrders[0]),
        },
        {
            label: 'Retards',
            detail: 'Commandes à relancer',
            value: lateOrders.length,
            tone: 'red',
            disabled: lateOrders.length === 0,
            onClick: () => openOrder(lateOrders[0]),
        },
        {
            label: 'Litiges',
            detail: 'Écarts fournisseur ouverts',
            value: openSupplierDisputes.length,
            tone: 'red',
            disabled: false,
            onClick: () => openDisputeModal?.({ supplier: sup.name, title: `Litige ${sup.name}` }),
        },
    ];
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
                                <span className={`border px-3 py-1 rounded-full text-xs font-black uppercase tracking-widest ${statusTone}`}>
                                    {statusLabels[supplierStatus] || supplierStatus}
                                </span>
                                {sup.supplier_category && (
                                    <span className="bg-white/10 text-slate-200 border border-white/10 px-3 py-1 rounded-full text-xs font-black uppercase tracking-widest">
                                        {sup.supplier_category}
                                    </span>
                                )}
                            </div>
                            <div className="flex items-center gap-6 text-slate-300 font-medium">
                                {sup.tax_id && (
                                    <div className="flex items-center gap-2">
                                        <Building2 className="w-4 h-4 text-slate-500" /> TVA/SIRET: {sup.tax_id}
                                    </div>
                                )}
                                {sup.country && (
                                    <div className="flex items-center gap-2">
                                        <Globe2 className="w-4 h-4 text-slate-500" /> {sup.country}
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
                            <button onClick={() => canOrder && openCreatePOForSupplier(sup.name)} disabled={!canOrder} className="bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed border border-white/10 text-white px-6 py-3 rounded-xl font-bold transition-all shadow-lg flex items-center gap-2">
                                <FileText className="w-4 h-4" /> Créer demande
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
                            <div className={`mb-8 rounded-3xl border p-6 shadow-sm ${canOrder ? 'bg-white border-slate-200' : 'bg-red-50 border-red-200'}`}>
                                <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-5">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Situation fournisseur</p>
                                        <h3 className="text-2xl font-black text-slate-900">
                                            {canOrder ? 'Fournisseur exploitable pour les achats' : 'Fournisseur bloqué'}
                                        </h3>
                                        <p className="text-sm font-bold text-slate-500 mt-1">
                                            {canOrder
                                                ? 'Contrôlez les commandes ouvertes, les réceptions et les factures à rapprocher.'
                                                : 'Aucune nouvelle commande ne doit être créée tant que le blocage n’est pas levé.'}
                                        </p>
                                    </div>
                                    <button onClick={() => canOrder && openCreatePOForSupplier(sup.name)} disabled={!canOrder} className="px-6 py-4 rounded-2xl bg-slate-900 disabled:bg-slate-300 text-white font-black shadow-lg flex items-center justify-center gap-2">
                                        <Plus className="w-5 h-5" /> Créer demande achat
                                    </button>
                                </div>
                                <div className="grid grid-cols-2 xl:grid-cols-5 gap-4 mt-6">
                                    <div className="rounded-2xl bg-slate-50 border border-slate-100 p-4">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Commandes ouvertes</p>
                                        <p className="text-3xl font-black text-slate-900 mt-1">{openOrders.length}</p>
                                    </div>
                                    <div className="rounded-2xl bg-blue-50 border border-blue-100 p-4">
                                        <p className="text-[10px] font-black text-blue-500 uppercase tracking-widest">À réceptionner</p>
                                        <p className="text-3xl font-black text-blue-700 mt-1">{quantityToReceive.toLocaleString('fr-FR')}</p>
                                        <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">{toReceiveOrders.length} commande(s)</p>
                                    </div>
                                    <div className="rounded-2xl bg-orange-50 border border-orange-100 p-4">
                                        <p className="text-[10px] font-black text-orange-500 uppercase tracking-widest">À facturer</p>
                                        <p className="text-3xl font-black text-orange-700 mt-1">{quantityToInvoice.toLocaleString('fr-FR')}</p>
                                        <p className="text-[10px] font-black text-orange-400 uppercase tracking-widest">{toInvoiceOrders.length} commande(s)</p>
                                    </div>
                                    <div className="rounded-2xl bg-red-50 border border-red-100 p-4">
                                        <p className="text-[10px] font-black text-red-500 uppercase tracking-widest">Retards</p>
                                        <p className="text-3xl font-black text-red-700 mt-1">{lateOrders.length}</p>
                                    </div>
                                    <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-4">
                                        <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Montant engagé</p>
                                        <p className="text-2xl font-black text-emerald-700 mt-1">{formatCurrency(committedAmount)}</p>
                                    </div>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 xl:grid-cols-[0.9fr_1.1fr] gap-8 mb-8">
                                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                                    <div className="p-6 border-b border-slate-100 bg-slate-50">
                                        <h3 className="font-black text-slate-800 flex items-center gap-2"><ArrowRight className="w-5 h-5 text-slate-400"/> Actions directes</h3>
                                        <p className="text-xs font-bold text-slate-500 mt-1">Les raccourcis importants selon la situation du fournisseur.</p>
                                    </div>
                                    <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        {actionTiles.map(action => (
                                            <button
                                                key={action.label}
                                                onClick={action.onClick}
                                                disabled={action.disabled}
                                                className={`text-left rounded-2xl border p-4 transition-all disabled:opacity-45 disabled:cursor-not-allowed ${
                                                    action.tone === 'emerald' ? 'bg-emerald-50 border-emerald-100 hover:bg-emerald-100'
                                                    : action.tone === 'orange' ? 'bg-orange-50 border-orange-100 hover:bg-orange-100'
                                                    : action.tone === 'red' ? 'bg-red-50 border-red-100 hover:bg-red-100'
                                                    : 'bg-slate-50 border-slate-100 hover:bg-slate-100'
                                                }`}
                                            >
                                                <div className="flex items-start justify-between gap-3">
                                                    <div>
                                                        <p className="font-black text-slate-900">{action.label}</p>
                                                        <p className="text-xs font-bold text-slate-500 mt-1">{action.detail}</p>
                                                    </div>
                                                    <span className={`min-w-10 h-10 px-2 rounded-xl flex items-center justify-center font-black ${
                                                        action.tone === 'emerald' ? 'bg-emerald-600 text-white'
                                                        : action.tone === 'orange' ? 'bg-orange-600 text-white'
                                                        : action.tone === 'red' ? 'bg-red-600 text-white'
                                                        : 'bg-slate-900 text-white'
                                                    }`}>
                                                        {action.value}
                                                    </span>
                                                </div>
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                                    <div className="p-6 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                                        <div>
                                            <h3 className="font-black text-slate-800 flex items-center gap-2"><PackageOpen className="w-5 h-5 text-slate-400"/> Commandes à traiter</h3>
                                            <p className="text-xs font-bold text-slate-500 mt-1">Retards, réceptions ouvertes et factures à rapprocher.</p>
                                        </div>
                                        <button onClick={() => setActiveTab('orders')} className="text-xs font-black text-blue-600 hover:text-blue-700">
                                            Voir tout
                                        </button>
                                    </div>
                                    <div className="divide-y divide-slate-100">
                                        {operationalOrders.map(order => (
                                            <button
                                                key={order.id}
                                                onClick={() => openOrder(order)}
                                                className="w-full p-4 text-left hover:bg-slate-50 transition-colors flex items-center justify-between gap-4"
                                            >
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <p className="font-black text-slate-900">{order.reference}</p>
                                                        <span className={`text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md ${getStatusColor(order.status)}`}>{order.status}</span>
                                                    </div>
                                                    <p className="text-xs font-bold text-slate-500 mt-1">
                                                        Reste à recevoir {remainingQty(order).toLocaleString('fr-FR')} · À rapprocher {invoiceableQty(order).toLocaleString('fr-FR')}
                                                    </p>
                                                    {order.expected_date && (
                                                        <p className={`text-[10px] font-black uppercase tracking-widest mt-1 ${lateOrders.some(lateOrder => lateOrder.id === order.id) ? 'text-red-600' : 'text-slate-400'}`}>
                                                            Livraison prévue {new Date(order.expected_date).toLocaleDateString('fr-FR')}
                                                        </p>
                                                    )}
                                                </div>
                                                <div className="text-right shrink-0">
                                                    <p className="font-black text-slate-900">{formatCurrency(order.total_amount)}</p>
                                                    <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mt-1">{getOrderNextAction(order)}</p>
                                                </div>
                                            </button>
                                        ))}
                                        {operationalOrders.length === 0 && (
                                            <div className="p-8 text-center">
                                                <CheckCircle className="w-10 h-10 text-emerald-300 mx-auto mb-3" />
                                                <p className="font-black text-slate-700">Aucune action urgente</p>
                                                <p className="text-sm font-bold text-slate-400 mt-1">Pas de retard, pas de réception ouverte, pas de facture à rapprocher.</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* KPI Row */}
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                                <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                                            <ShoppingCart className="w-5 h-5 text-blue-600" />
                                        </div>
                                    </div>
                                    <p className="text-xs font-black text-slate-400 uppercase tracking-widest mb-1">Total Dépensé</p>
                                    <h3 className="text-2xl font-black text-slate-800">{formatCurrency(totalSpent)}</h3>
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
                                    <h3 className="text-2xl font-black text-slate-800">{formatCurrency(avgOrderValue)}</h3>
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
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Pays</p>
                                                <p className="font-black text-slate-800">{sup.country || 'Non renseigné'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Catégorie</p>
                                                <p className="font-black text-slate-800">{sup.supplier_category || 'Non renseigné'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Devise</p>
                                                <p className="font-black text-slate-800">{sup.default_currency || 'EUR'}</p>
                                            </div>
                                            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
                                                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Incoterm</p>
                                                <p className="font-black text-slate-800">{sup.incoterm || 'Non renseigné'}</p>
                                            </div>
                                        </div>
                                        {sup.delivery_terms && (
                                            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 mb-6">
                                                <p className="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-1">Conditions livraison</p>
                                                <p className="font-bold text-blue-950">{sup.delivery_terms}</p>
                                            </div>
                                        )}
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
                                                    {sup.country && <p className="text-xs font-bold text-emerald-700 mt-1">Pays fiscal : {sup.country}</p>}
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

                            <div className="mt-8 bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                                <div className="p-6 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                                    <div>
                                        <h3 className="font-black text-slate-800 flex items-center gap-2"><CheckCircle className="w-5 h-5 text-slate-400"/> Qualité fournisseur</h3>
                                        <p className="text-xs font-bold text-slate-500 mt-1">Lecture opérationnelle des risques visibles dans MMG.</p>
                                    </div>
                                    <span className={`px-3 py-1 rounded-full text-xs font-black uppercase tracking-widest ${qualityAlerts === 0 ? 'bg-emerald-100 text-emerald-700' : qualityAlerts <= 2 ? 'bg-orange-100 text-orange-700' : 'bg-red-100 text-red-700'}`}>
                                        {qualityLabel}
                                    </span>
                                </div>
                                <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 p-6">
                                    <div className="rounded-2xl bg-slate-50 border border-slate-100 p-4">
                                        <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Réceptions partielles</p>
                                        <p className="text-2xl font-black text-slate-900 mt-1">{supOrders.filter(o => o.status === 'PARTIAL').length}</p>
                                    </div>
                                    <div className="rounded-2xl bg-red-50 border border-red-100 p-4">
                                        <p className="text-[10px] font-black text-red-500 uppercase tracking-widest">Retards ouverts</p>
                                        <p className="text-2xl font-black text-red-700 mt-1">{lateOrders.length}</p>
                                    </div>
                                    <div className="rounded-2xl bg-orange-50 border border-orange-100 p-4">
                                        <p className="text-[10px] font-black text-orange-500 uppercase tracking-widest">Factures à rapprocher</p>
                                        <p className="text-2xl font-black text-orange-700 mt-1">{toInvoiceOrders.length}</p>
                                    </div>
                                    <div className="rounded-2xl bg-emerald-50 border border-emerald-100 p-4">
                                        <p className="text-[10px] font-black text-emerald-500 uppercase tracking-widest">Commandes reçues</p>
                                        <p className="text-2xl font-black text-emerald-700 mt-1">{receivedOrders}</p>
                                    </div>
                                    <button
                                        onClick={() => openDisputeModal?.({ supplier: sup.name, title: `Litige ${sup.name}` })}
                                        className="rounded-2xl bg-red-50 border border-red-100 p-4 text-left hover:bg-red-100 transition-colors"
                                    >
                                        <p className="text-[10px] font-black text-red-500 uppercase tracking-widest">Litiges ouverts</p>
                                        <p className="text-2xl font-black text-red-700 mt-1">{openSupplierDisputes.length}</p>
                                        <p className="text-[10px] font-black text-red-500 uppercase tracking-widest mt-1">Déclarer</p>
                                    </button>
                                </div>
                                {openSupplierDisputes.length > 0 && (
                                    <div className="px-6 pb-6 space-y-3">
                                        {openSupplierDisputes.slice(0, 4).map(dispute => (
                                            <div key={dispute.id} className="rounded-2xl border border-red-100 bg-red-50 p-4 flex items-start justify-between gap-4">
                                                <div>
                                                    <p className="font-black text-red-950">{dispute.title}</p>
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-red-500 mt-1">
                                                        {dispute.reference} · {dispute.category} · {dispute.severity} · {dispute.status}
                                                    </p>
                                                    <div className="mt-2 flex flex-wrap gap-1">
                                                        {dispute.blocks_receipt && <span className="text-[9px] font-black uppercase tracking-widest bg-white text-red-700 px-2 py-1 rounded-md">réception bloquée</span>}
                                                        {dispute.blocks_payment && <span className="text-[9px] font-black uppercase tracking-widest bg-white text-orange-700 px-2 py-1 rounded-md">facture bloquée</span>}
                                                        {dispute.expected_action && <span className="text-[9px] font-black uppercase tracking-widest bg-white text-slate-600 px-2 py-1 rounded-md">{dispute.expected_action}</span>}
                                                    </div>
                                                    {dispute.impact_summary && <p className="mt-2 text-xs font-bold text-red-700">{dispute.impact_summary}</p>}
                                                </div>
                                                <div className="flex flex-col gap-2 shrink-0">
                                                    {dispute.status === 'OPEN' && (
                                                        <button onClick={() => onStartDispute?.(dispute.id)} className="px-3 py-2 rounded-xl bg-white border border-blue-100 text-blue-700 text-xs font-black hover:bg-blue-50">
                                                            Traiter
                                                        </button>
                                                    )}
                                                    <button onClick={() => onResolveDispute?.(dispute.id)} className="px-3 py-2 rounded-xl bg-white border border-red-100 text-emerald-700 text-xs font-black hover:bg-emerald-50">
                                                        Résoudre
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <div className="mt-8 bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
                                <div className="p-6 border-b border-slate-100 bg-slate-50">
                                    <h3 className="font-black text-slate-800 flex items-center gap-2"><FileText className="w-5 h-5 text-slate-400"/> Timeline fournisseur</h3>
                                    <p className="text-xs font-bold text-slate-500 mt-1">Derniers événements achats, réceptions et rapprochements.</p>
                                </div>
                                <div className="p-6 space-y-4">
                                    {supplierTimeline.map(event => (
                                        <div key={event.key} className="flex items-start gap-4">
                                            <div className={`w-3 h-3 rounded-full mt-2 ${event.tone === 'emerald' ? 'bg-emerald-500' : event.tone === 'orange' ? 'bg-orange-500' : event.tone === 'blue' ? 'bg-blue-500' : event.tone === 'red' ? 'bg-red-500' : 'bg-slate-400'}`}></div>
                                            <div className="flex-1 border-b border-slate-100 pb-4">
                                                <div className="flex items-center justify-between gap-4">
                                                    <p className="font-black text-slate-900">{event.label}</p>
                                                    <p className="text-xs font-bold text-slate-400">{event.date ? new Date(event.date).toLocaleDateString('fr-FR') : '-'}</p>
                                                </div>
                                                <p className="text-sm font-bold text-slate-500 mt-1">{event.detail}</p>
                                            </div>
                                        </div>
                                    ))}
                                    {supplierTimeline.length === 0 && (
                                        <p className="text-sm font-bold text-slate-400">Aucun événement fournisseur pour le moment.</p>
                                    )}
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
