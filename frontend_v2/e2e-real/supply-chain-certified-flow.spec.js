import { expect, test } from '@playwright/test';

const backendURL = 'http://127.0.0.1:7100';

async function authenticate(page, request) {
    const loginResponse = await request.post(`${backendURL}/token`, {
        form: {
            username: 'e2e_admin',
            password: '1234',
        },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const auth = await loginResponse.json();

    await page.addInitScript(({ accessToken, role, roles, stations, permissions }) => {
        localStorage.setItem('token', accessToken);
        localStorage.setItem('username', 'e2e_admin');
        localStorage.setItem('role', role);
        localStorage.setItem('roles', JSON.stringify(roles));
        localStorage.setItem('stations', JSON.stringify(stations));
        localStorage.setItem('permissions', JSON.stringify(permissions));
    }, {
        accessToken: auth.access_token,
        role: auth.role,
        roles: auth.roles,
        stations: auth.stations,
        permissions: auth.permissions,
    });

    return { Authorization: `Bearer ${auth.access_token}` };
}

async function createLocation(request, headers, name, parentId = null) {
    const response = await request.post(`${backendURL}/v2/stock/locations`, {
        headers,
        data: {
            name,
            usage: 'internal',
            parent_id: parentId,
        },
    });
    expect(response.ok()).toBeTruthy();
    return response.json();
}

async function fetchPurchaseOrder(request, headers, purchaseOrderId) {
    const response = await request.get(`${backendURL}/v2/purchases/${purchaseOrderId}`, { headers });
    expect(response.ok()).toBeTruthy();
    return response.json();
}

test('supply chain flow protects purchase, receipt, transfer, invoice dispute and payment', async ({ page, request }) => {
    test.setTimeout(60_000);

    const headers = await authenticate(page, request);
    await page.setViewportSize({ width: 1600, height: 1200 });
    page.on('dialog', dialog => dialog.accept());

    const suffix = Date.now();
    const supplier = `E2E SUPPLY ${suffix}`;
    const variantReference = `E2E-SC-${suffix}-A`;

    const magasin = await createLocation(request, headers, `MAGASIN E2E ${suffix}`);
    const zone = await createLocation(request, headers, `ZONE E2E ${suffix}`, magasin.id);
    const rack = await createLocation(request, headers, `RACK E2E ${suffix}`, zone.id);
    const receiptLocation = await createLocation(request, headers, `CASIER RECEPTION E2E ${suffix}`, rack.id);
    const transferLocation = await createLocation(request, headers, `CASIER TRANSFERT E2E ${suffix}`, rack.id);

    const productResponse = await request.post(`${backendURL}/v2/stock/products`, {
        headers,
        data: {
            reference_base: `E2E-SC-${suffix}`,
            name: `Article Supply Chain E2E ${suffix}`,
            category: 'E2E',
            material_type: 'ACCESSOIRE',
            unit: 'pce',
            supplier,
            product_type: 'stockable',
            catalog_status: 'ACTIVE',
            variants: [{
                reference: variantReference,
                supplier_reference: variantReference,
                quantity_in_stock: 0,
                min_threshold: 2,
                cost_price: 12,
            }],
        },
    });
    expect(productResponse.ok()).toBeTruthy();
    const product = await productResponse.json();
    const variantId = product.variants[0].id;

    const purchaseRequestResponse = await request.post(`${backendURL}/v2/purchases/requests`, {
        headers,
        data: {
            supplier,
            sensitivity_reason: 'Recette e2e Supply Chain',
            notes: 'Demande anonymisée créée par Playwright.',
            lines: [{
                variant_id: variantId,
                quantity: 4,
                unit_price: 12,
                need_priority: 'HIGH',
                need_reason: 'Sécuriser la boucle achat → réception → paiement.',
            }],
        },
    });
    expect(purchaseRequestResponse.ok()).toBeTruthy();
    const purchaseRequest = await purchaseRequestResponse.json();

    const approveResponse = await request.post(`${backendURL}/v2/purchases/requests/${purchaseRequest.id}/approve`, { headers });
    expect(approveResponse.ok()).toBeTruthy();

    const convertResponse = await request.post(`${backendURL}/v2/purchases/requests/${purchaseRequest.id}/convert`, { headers });
    expect(convertResponse.ok()).toBeTruthy();
    const converted = await convertResponse.json();
    const purchaseOrderId = converted.purchase_order.id;
    const purchaseOrderReference = converted.purchase_order.reference;

    await page.goto('/manager?view=purchases');
    await expect(page.getByRole('heading', { name: 'Achats & Appro', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Commandes', exact: true }).click();
    await page.getByText(purchaseOrderReference).click();
    await expect(page.getByRole('heading', { name: purchaseOrderReference })).toBeVisible();

    await page.getByRole('button', { name: /Réceptionner les Articles/i }).click();
    const receiveModal = page.locator('.fixed').filter({ hasText: 'Réceptionner, ranger, rendre disponible' });
    await expect(receiveModal.getByRole('heading', { name: 'Réceptionner, ranger, rendre disponible' })).toBeVisible();
    await expect(receiveModal.getByText('Emplacement final', { exact: true })).toBeVisible();
    await receiveModal.locator('select').selectOption(String(receiptLocation.id));
    await expect(receiveModal.getByText('Destination validée')).toBeVisible();
    await receiveModal.getByPlaceholder('Ex: BL fournisseur, colis, transporteur...').fill(`BL-E2E-${suffix}`);
    await receiveModal.getByPlaceholder('Ex: réception complète, contrôle visuel OK...').fill('Réception e2e complète et rangée.');
    await receiveModal.getByRole('button', { name: 'Valider réception et ranger en stock' }).click();
    await expect(receiveModal).not.toBeVisible();

    let po = await fetchPurchaseOrder(request, headers, purchaseOrderId);
    expect(po.quantity_received).toBe(4);
    expect(po.quantity_invoiceable).toBe(4);

    const transferResponse = await request.post(`${backendURL}/v2/stock/transaction`, {
        headers,
        data: {
            variant_id: variantId,
            location_id: receiptLocation.id,
            location_dest_id: transferLocation.id,
            quantity: 1,
            notes: 'Transfert interne guidé validé par e2e.',
            reason: 'Rangement atelier clair.',
            source_screen: 'playwright.supply_chain',
            document_type: 'e2e_stock_transfer',
            document_reference: purchaseOrderReference,
        },
    });
    expect(transferResponse.ok()).toBeTruthy();

    const quantsResponse = await request.get(`${backendURL}/v2/stock/quants`, { headers });
    expect(quantsResponse.ok()).toBeTruthy();
    const quants = await quantsResponse.json();
    expect(quants.find(quant => quant.variant_id === variantId && quant.location_id === receiptLocation.id)?.quantity).toBe(3);
    expect(quants.find(quant => quant.variant_id === variantId && quant.location_id === transferLocation.id)?.quantity).toBe(1);

    await expect(page.getByRole('button', { name: 'Rapprocher facture' })).toBeVisible();
    await page.getByRole('button', { name: 'Rapprocher facture' }).click();
    const invoiceModal = page.locator('.fixed').filter({ hasText: 'Rapprocher une facture' });
    await expect(invoiceModal.getByRole('heading', { name: 'Rapprocher une facture' })).toBeVisible();
    await invoiceModal.getByPlaceholder('Ex: FAC-CORTIZO-2026-0716').fill(`FAC-E2E-${suffix}`);

    const invoiceNumberInputs = invoiceModal.locator('input[type="number"]');
    await invoiceNumberInputs.nth(1).fill('13');
    await expect(invoiceModal.getByText('Créer litige prix')).toBeVisible();
    await expect(invoiceModal.getByRole('button', { name: 'Valider rapprochement et ouvrir paiement' })).toBeDisabled();

    await invoiceNumberInputs.nth(1).fill('12');
    await expect(invoiceModal.getByText('Prix OK')).toBeVisible();
    const reconcileInvoiceButton = invoiceModal.getByRole('button', { name: 'Valider rapprochement et ouvrir paiement' });
    await expect(reconcileInvoiceButton).toBeEnabled();
    await reconcileInvoiceButton.scrollIntoViewIfNeeded();
    await reconcileInvoiceButton.click({ force: true });

    const paymentModal = page.locator('.fixed').filter({ hasText: 'Paiement fournisseur' });
    await expect(paymentModal.getByText('Paiement fournisseur')).toBeVisible();
    await paymentModal.getByRole('button', { name: 'Annuler' }).click();

    po = await fetchPurchaseOrder(request, headers, purchaseOrderId);
    expect(po.quantity_invoiced).toBe(4);
    expect(po.supplier_invoices).toHaveLength(1);
    const supplierInvoice = po.supplier_invoices[0];
    expect(supplierInvoice.remaining_amount).toBe(48);

    const disputeResponse = await request.post(`${backendURL}/v2/purchases/disputes`, {
        headers,
        data: {
            supplier,
            purchase_order_id: purchaseOrderId,
            supplier_invoice_id: supplierInvoice.id,
            title: 'Écart prix bloquant paiement E2E',
            description: 'Litige anonymisé créé pour verrouiller le garde-fou paiement.',
            category: 'PRICE',
            severity: 'BLOCKING',
            expected_unit_price: 12,
            invoiced_unit_price: 13,
            expected_action: 'PRICE_CORRECTION',
            blocks_payment: true,
            impact_summary: 'Paiement impossible tant que le litige prix est ouvert.',
        },
    });
    expect(disputeResponse.ok()).toBeTruthy();
    const dispute = await disputeResponse.json();

    const blockedPaymentResponse = await request.post(`${backendURL}/v2/purchases/supplier-invoices/${supplierInvoice.id}/pay`, {
        headers,
        data: {
            amount: 48,
            method: 'TRANSFER',
            reference: `VIR-BLOCKED-${suffix}`,
            notes: 'Ce paiement doit être bloqué par le litige ouvert.',
        },
    });
    expect(blockedPaymentResponse.status()).toBe(409);
    expect(await blockedPaymentResponse.text()).toContain('bloqué par litige ouvert');

    const resolveResponse = await request.post(`${backendURL}/v2/purchases/disputes/${dispute.id}/resolve`, {
        headers,
        data: {
            resolution_notes: 'Prix corrigé et validation comptable e2e.',
        },
    });
    expect(resolveResponse.ok()).toBeTruthy();

    const paymentResponse = await request.post(`${backendURL}/v2/purchases/supplier-invoices/${supplierInvoice.id}/pay`, {
        headers,
        data: {
            amount: 48,
            method: 'TRANSFER',
            reference: `VIR-E2E-${suffix}`,
            notes: 'Paiement e2e après résolution litige.',
        },
    });
    expect(paymentResponse.ok()).toBeTruthy();
    const paidInvoice = await paymentResponse.json();
    expect(paidInvoice.status).toBe('PAID');
    expect(paidInvoice.remaining_amount).toBe(0);
});
