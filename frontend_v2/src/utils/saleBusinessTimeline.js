export const SALE_TIMELINE_STEPS = [
    { key: 'signed', label: 'CRM signé' },
    { key: 'deposit', label: 'Acompte' },
    { key: 'measure', label: 'BE / Métré' },
    { key: 'workshopPrep', label: 'Préparation atelier' },
    { key: 'reservation', label: 'Réservation' },
    { key: 'production', label: 'Production' },
    { key: 'delivery', label: 'Livraison' },
    { key: 'finalInvoice', label: 'Solde facture' },
    { key: 'payment', label: 'Paiement' },
];

export function isCreditNote(invoice) {
    const status = String(invoice?.status || '').toUpperCase();
    const invoiceType = String(invoice?.invoice_type || '').toUpperCase();
    const reference = String(invoice?.reference || '').toUpperCase();
    return status === 'AVOIR' || status === 'CREDIT_NOTE' || invoiceType === 'CREDIT_NOTE' || reference.startsWith('AV-') || Number(invoice?.total || 0) < 0;
}

export function isDepositInvoice(invoice) {
    return String(invoice?.invoice_type || '').toUpperCase() === 'DEPOSIT';
}

export function buildSaleWorkflowTrace(sale) {
    const reservations = sale?.reservations || [];
    const deliveryNotes = sale?.delivery_notes || [];
    const invoices = sale?.invoices || [];
    const billableInvoices = invoices.filter(invoice => !isCreditNote(invoice) && !['DRAFT', 'CANCELLED', 'VOID'].includes(String(invoice.status || '').toUpperCase()));
    const depositInvoices = billableInvoices.filter(isDepositInvoice);
    const finalInvoices = billableInvoices.filter(invoice => !isDepositInvoice(invoice));
    const activeReservations = reservations.filter(reservation => reservation.status === 'reserved');
    const consumedReservations = reservations.filter(reservation => reservation.status === 'consumed');
    const returnedReservations = reservations.filter(reservation => reservation.status === 'returned');
    const workshopReservations = reservations.filter(reservation => !['devis libre', 'devis_libre'].includes(String(reservation.source_label || '').toLowerCase()));
    const commercialReservations = reservations.filter(reservation => ['devis libre', 'devis_libre'].includes(String(reservation.source_label || '').toLowerCase()));
    const returnedDeliveryNotes = deliveryNotes.filter(note => ['RETURNED', 'CANCELLED'].includes(note.status));
    const hasStockLines = (sale?.lines || []).some(line => line.line_type === 'STOCK_ITEM' || line.variant_id);
    const workflowType = sale?.workflow_type || 'FREE_SALE';
    const isFabrication = workflowType !== 'FREE_SALE';
    const isSigned = Boolean(sale?.signed_at) || ['VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale?.status);
    const isReserved = activeReservations.length > 0 || consumedReservations.length > 0 || (sale?.lines || []).some(line => Number(line.reserved_quantity || 0) > 0);
    const isReturned = returnedReservations.length > 0 || returnedDeliveryNotes.length > 0;
    const isDelivered = !isReturned && (sale?.status === 'DELIVERED' || deliveryNotes.some(note => note.status === 'DELIVERED' || note.signed_at));
    const finalPaid = finalInvoices.length > 0 && finalInvoices.every(invoice => String(invoice.status || '').toUpperCase() === 'PAID');
    const depositPaid = depositInvoices.length > 0 && depositInvoices.every(invoice => String(invoice.status || '').toUpperCase() === 'PAID');

    return {
        reservations,
        activeReservations,
        consumedReservations,
        returnedReservations,
        workshopReservations,
        commercialReservations,
        deliveryNotes,
        returnedDeliveryNotes,
        invoices,
        billableInvoices,
        depositInvoices,
        finalInvoices,
        creditNotes: invoices.filter(isCreditNote),
        hasStockLines,
        workflowType,
        isFabrication,
        isSigned,
        hasDepositInvoice: depositInvoices.length > 0,
        depositPaid,
        isReserved,
        hasWorkshopReservation: workshopReservations.length > 0,
        hasProductionOrder: ['READY_FOR_PROD', 'IN_PRODUCTION'].includes(sale?.status),
        isInProduction: sale?.status === 'IN_PRODUCTION',
        isDelivered,
        isReturned,
        hasFinalInvoice: finalInvoices.length > 0,
        finalPaid,
        hasCreditNote: invoices.some(isCreditNote),
    };
}

function stepState({ done = false, active = false, skipped = false, blocked = false } = {}) {
    if (blocked) return 'blocked';
    if (skipped) return 'skipped';
    if (done) return 'done';
    if (active) return 'active';
    return 'todo';
}

export function buildSaleBusinessTimeline(sale) {
    const trace = buildSaleWorkflowTrace(sale);
    const isCancelled = sale?.status === 'CANCELLED';
    const isFreeSale = trace.workflowType === 'FREE_SALE';
    const measureDone = isFreeSale || trace.workflowType === 'FABRICATION_FROM_MEASURE' || (sale?.mmg_dossiers || []).length > 0;
    const workshopReady = isFreeSale || trace.hasWorkshopReservation || ['READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale?.status);
    const productionDone = isFreeSale || ['IN_PRODUCTION', 'DELIVERED'].includes(sale?.status);
    const reservationDone = trace.isReserved || trace.hasFinalInvoice || trace.isDelivered;

    const steps = [
        {
            key: 'signed',
            label: 'CRM signé',
            state: stepState({ done: trace.isSigned, active: sale?.status === 'SENT', blocked: isCancelled }),
            detail: trace.isSigned ? 'Client validé' : (sale?.status === 'SENT' ? 'Signature attendue' : 'Avant-vente'),
        },
        {
            key: 'deposit',
            label: 'Acompte',
            state: stepState({ done: trace.hasDepositInvoice || isFreeSale, active: trace.isSigned && trace.isFabrication && !trace.hasDepositInvoice, skipped: isFreeSale, blocked: isCancelled }),
            detail: isFreeSale ? 'Non requis' : trace.hasDepositInvoice ? (trace.depositPaid ? 'Acompte payé' : 'Facture émise') : 'À émettre',
        },
        {
            key: 'measure',
            label: 'BE / Métré',
            state: stepState({ done: measureDone, active: trace.isFabrication && trace.isSigned && !measureDone, skipped: isFreeSale, blocked: isCancelled }),
            detail: isFreeSale ? 'Non requis' : measureDone ? 'Données techniques OK' : 'À rattacher',
        },
        {
            key: 'workshopPrep',
            label: 'Préparation atelier',
            state: stepState({ done: workshopReady, active: trace.isFabrication && measureDone && !workshopReady, skipped: isFreeSale, blocked: isCancelled }),
            detail: isFreeSale ? 'Non requis' : workshopReady ? 'Débit contrôlé' : 'À préparer',
        },
        {
            key: 'reservation',
            label: 'Réservation',
            state: stepState({ done: reservationDone, active: trace.isSigned && trace.hasStockLines && !reservationDone, blocked: isCancelled }),
            detail: reservationDone ? 'Stock bloqué' : (trace.hasStockLines ? 'À réserver' : 'Sans stock'),
        },
        {
            key: 'production',
            label: 'Production',
            state: stepState({ done: productionDone, active: trace.isFabrication && workshopReady && !productionDone, skipped: isFreeSale, blocked: isCancelled }),
            detail: isFreeSale ? 'Non requis' : trace.isInProduction ? 'En cours' : productionDone ? 'Lancée' : 'À lancer',
        },
        {
            key: 'delivery',
            label: 'Livraison',
            state: stepState({ done: trace.isDelivered || trace.isReturned, active: trace.isSigned && !trace.isDelivered && !trace.isReturned, blocked: isCancelled }),
            detail: trace.isReturned ? 'Retourné' : trace.isDelivered ? 'BL généré' : 'À livrer',
        },
        {
            key: 'finalInvoice',
            label: 'Solde facture',
            state: stepState({ done: trace.hasFinalInvoice, active: trace.isDelivered && !trace.hasFinalInvoice, blocked: isCancelled }),
            detail: trace.hasFinalInvoice ? 'Facture liée' : 'À facturer',
        },
        {
            key: 'payment',
            label: 'Paiement',
            state: stepState({ done: trace.finalPaid, active: trace.hasFinalInvoice && !trace.finalPaid, blocked: isCancelled }),
            detail: trace.finalPaid ? 'Soldé' : trace.hasFinalInvoice ? 'À encaisser' : 'À venir',
        },
    ];

    const activeIndex = steps.findIndex(step => step.state === 'active' || step.state === 'blocked');
    const lastDoneIndex = steps.reduce((lastIndex, step, index) => (step.state === 'done' ? index : lastIndex), -1);
    return {
        trace,
        steps,
        activeIndex: activeIndex >= 0 ? activeIndex : Math.max(0, lastDoneIndex),
        isCancelled,
    };
}
