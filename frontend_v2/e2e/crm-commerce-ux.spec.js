import { expect, test } from '@playwright/test';


const now = '2026-09-05T08:00:00Z';

function json(route, body, status = 200) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
    });
}

async function mockCRMCommerceAPI(page, { quoteReady = false } = {}) {
    const clients = [
        {
            id: 101,
            name: 'CLIENT RECETTE COMMERCE',
            contact_name: 'Mme Atelier',
            phone: '+33102030405',
            email: 'commerce-recette@example.test',
            address: '10 rue du Test, 75000 Paris',
            tax_id: 'FRTESTCRM',
            country: 'FR',
            customer_type: 'B2B',
            segment: 'Architectes',
            tags: ['Prioritaire', 'Prescription'],
            is_active: true,
            created_at: now,
            contacts: [
                {
                    id: 501,
                    client_id: 101,
                    name: 'Mme Atelier',
                    role: 'Décisionnaire',
                    email: 'commerce-recette@example.test',
                    phone: '+33102030405',
                    priority: 1,
                    influence_role: 'DECISION_MAKER',
                    preferred_channel: 'EMAIL',
                    email_consent: true,
                    is_primary: true,
                    created_at: now,
                    updated_at: now,
                },
            ],
        },
    ];
    const sales = [
        {
            id: 301,
            reference: 'DEV-CRM-E2E-001',
            status: 'SENT',
            client_name: 'CLIENT RECETTE COMMERCE',
            client_contact: '+33102030405',
            client_email: 'commerce-recette@example.test',
            created_at: '2026-09-01T08:00:00Z',
            updated_at: '2026-09-03T08:00:00Z',
            lines: [
                { id: 1, description: 'Menuiserie aluminium anonymisée', quantity: 2, unit_price: 1200, discount_pct: 0 },
            ],
            invoices: [],
            delivery_notes: [],
        },
    ];
    const dossiers = [
        {
            id: 401,
            measure_mission_id: 401,
            reference: 'MET-CRM-E2E-001',
            client_name: 'CLIENT RECETTE COMMERCE',
            client_contact: '+33102030405',
            client_email: 'commerce-recette@example.test',
            client_address: 'Chantier recette commerce',
            status: 'TO_REVIEW',
            source_type: 'SITE_VISIT',
            project_scope: 'SUPPLY_AND_INSTALL',
            created_at: '2026-09-04T08:00:00Z',
        },
    ];
    const cockpit = {
        generated_at: now,
        horizon_days: 14,
        metrics: {
            open_opportunities: 1,
            pipeline_amount: 2400,
            weighted_pipeline_amount: 1200,
            signed_amount: 0,
            sent_quotes: 1,
            overdue_actions: 1,
            reminders_today: 1,
            overdue_reminders: 1,
            opportunities_without_action: 1,
            measures_to_schedule: 1,
            automatic_reminders: 1,
        },
        stages: [
            { stage: 'proposition_envoyee', count: 1, amount: 2400 },
        ],
        agenda: [],
        reminders: [],
        reminders_today: [],
        overdue_reminders: [
            {
                id: 701,
                client_id: 101,
                client_name: 'CLIENT RECETTE COMMERCE',
                client_email: 'commerce-recette@example.test',
                opportunity_id: 201,
                opportunity_title: 'Remplacement façades bureau',
                stage_snapshot: 'proposition_envoyee',
                due_at: '2026-09-04T08:00:00Z',
            },
        ],
        opportunities_without_action: [
            {
                id: 201,
                client_id: 101,
                client_name: 'CLIENT RECETTE COMMERCE',
                title: 'Remplacement façades bureau',
                stage: 'proposition_envoyee',
            },
        ],
        owners: [
            {
                owner_user_id: 1,
                owner_name: 'Commercial recette',
                opportunities: 1,
                sent_quotes: 1,
                signed_orders: 0,
                signed_amount: 0,
                conversion_rate: 0,
                attention_score: 72,
            },
        ],
        stage_conversions: [
            { stage: 'proposition_envoyee', opportunities: 1, conversion_rate: 0, amount: 2400 },
        ],
    };
    const opportunities = [
        {
            id: 201,
            client_id: 101,
            title: 'Remplacement façades bureau',
            stage: quoteReady ? 'proposition_a_preparer' : 'proposition_envoyee',
            sale_order_id: quoteReady ? null : 301,
            amount_estimated: 2400,
            probability: 50,
            expected_close_date: '2026-09-15',
            next_action_at: '2026-09-04T08:00:00Z',
            owner_name: 'Commercial recette',
            created_at: '2026-09-01T08:00:00Z',
            updated_at: '2026-09-03T08:00:00Z',
        },
    ];
    const ontology = {
        entities: {
            crm_opportunity: { code: 'crm_opportunity', label: 'Opportunité commerciale' },
            measure_mission: { code: 'measure_mission', label: 'Métré / BE' },
            commercial_quote: { code: 'commercial_quote', label: 'Devis commercial' },
        },
        entity_statuses: {
            crm_opportunity: [],
            measure_mission: [],
            commercial_quote: [],
        },
        business_events: [
            { code: 'quote_sent', label: 'Devis envoyé' },
            { code: 'quote_signed', label: 'Devis signé' },
        ],
        step_rbac: [
            { entity: 'crm_opportunity', permission: 'SALES_EDIT' },
            { entity: 'commercial_quote', permission: 'SALES_EDIT' },
        ],
        external_document_mappings: [],
    };

    await page.addInitScript(() => {
        localStorage.setItem('token', 'e2e-commerce-token');
        localStorage.setItem('username', 'commercial-e2e');
        localStorage.setItem('role', 'ADMIN');
        localStorage.setItem('roles', JSON.stringify(['ADMIN']));
        localStorage.setItem('stations', JSON.stringify([]));
        localStorage.setItem('permissions', JSON.stringify(['*']));
        localStorage.removeItem('mmg.crm.clientFilters.v1');
    });

    await page.route('http://127.0.0.1:5173/api/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname.replace(/^\/api/, '');
        const method = request.method();

        if (path === '/v2/partners/clients' && method === 'GET') return json(route, clients);
        if (path === '/v2/partners/clients/segmentation' && method === 'GET') {
            return json(route, {
                tags: [{ tag: 'Prioritaire', count: 1 }, { tag: 'Prescription', count: 1 }],
                segments: [{ segment: 'Architectes', count: 1 }],
                commercial_statuses: [
                    { status: 'to_follow_up', count: 1 },
                    { status: 'quote_sent', count: 1 },
                ],
                client_signals: {
                    101: {
                        client_id: 101,
                        statuses: ['to_follow_up', 'quote_sent', 'missing_next_action'],
                        open_opportunities: 1,
                        pending_reminders: 1,
                        overdue_actions: 1,
                        missing_next_action: true,
                    },
                },
            });
        }
        if (path === '/v2/mmg/missions' && method === 'GET' && quoteReady) {
            return json(route, [{ id: 401, opportunity_id: 201, status: 'VALIDATED', created_at: now }]);
        }
        if (path === '/v2/sales/301' && method === 'GET') return json(route, sales[0]);
        if (path === '/v2/sales/' && method === 'GET') return json(route, [
            ...sales,
            { ...sales[0], id: 302, reference: 'COM-CRM-E2E-002', status: 'DELIVERED', invoices: [], delivery_notes: [] },
        ]);
        if (path === '/v2/accounting/invoices' && method === 'GET') {
            return json(route, [
                { id: 1, reference: 'F-001', client_name: 'Client test', total: 120, total_paid: 40, status: 'PARTIAL',
                    accounting_status: 'CREDITED', balance_due: 0, customer_credit: 40, refund_due: 40, issue_date: now },
                { id: 2, reference: 'AV-001', client_name: 'Client test', total: -120, status: 'AVOIR',
                    accounting_status: 'AVOIR', balance_due: 0, issue_date: now, source_invoice_reference: 'F-001' },
                { id: 3, reference: 'F-002', client_name: 'Autre client test', total: 120, total_paid: 0, status: 'UNPAID',
                    accounting_status: 'UNPAID', balance_due: 120, issue_date: now },
            ]);
        }
        if (path === '/v2/mmg/' && method === 'GET') return json(route, dossiers);
        if (path === '/v2/mmg/sites' && method === 'GET') {
            return json(route, [
                {
                    id: 601,
                    client_id: 101,
                    label: 'Chantier principal',
                    address_line1: '10 rue du Test',
                    city: 'Paris',
                    is_default: true,
                },
            ]);
        }
        if (path === '/v2/mmg/opportunities' && method === 'GET') {
            const clientId = Number(url.searchParams.get('client_id'));
            return json(route, opportunities.filter(item => !clientId || item.client_id === clientId));
        }
        if (path === '/v2/mmg/activities' && method === 'GET') return json(route, []);
        if (path === '/v2/mmg/crm/cockpit' && method === 'GET') return json(route, cockpit);
        if (path === '/v2/mmg/ontology' && method === 'GET') return json(route, ontology);
        if (
            path === '/v2/mmg/crm/reminder-templates'
            || path === '/v2/mmg/crm/reminders/history'
            || path === '/v2/mmg/crm/reminder-rules'
            || path === '/v2/mmg/crm/reminder-plans'
            || path === '/v2/config/users'
            || path === '/v2/partners/clients/duplicates'
            || path === '/v2/stock/products'
        ) {
            return json(route, []);
        }

        return json(route, []);
    });
}

test('la fiche client affiche une seule action et ouvre le devis lié', async ({ page }) => {
    await mockCRMCommerceAPI(page);
    await page.goto('/crm');

    await expect(page.getByRole('heading', { name: 'À traiter en priorité' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ouvrir / relancer' })).toBeVisible();
    const filters = page.getByRole('group', { name: 'Filtrer les actions' });
    await filters.getByRole('button', { name: 'Suivi client' }).click();
    await expect(page.getByRole('button', { name: 'Traiter relance' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Ouvrir / relancer' })).toHaveCount(0);
    await filters.getByRole('button', { name: 'Devis', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Ouvrir / relancer' })).toBeVisible();
    await page.getByRole('button', { name: 'Nouveau besoin client', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Enregistrer une nouvelle demande' })).toBeVisible();
    await page.getByRole('button', { name: 'Fermer', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Proposition envoyée' })).toBeVisible();
    await page.getByRole('button', { name: 'Métrés / BE', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Planification et contrôle technique' })).toBeVisible();
    await page.getByRole('button', { name: 'Clients & contacts', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'CLIENT RECETTE COMMERCE' })).toBeVisible();
    await page.getByText('Autres actions', { exact: true }).click();
    await page.getByRole('button', { name: 'Préparer un devis', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Préparer un brouillon de devis' })).toBeVisible();
    await page.locator('.fixed.inset-0').last().locator('button').first().click();
    await page.locator('details').filter({ has: page.getByText('Autres actions', { exact: true }) })
        .getByRole('button', { name: 'Planifier un métré', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Choisir la source des cotes' })).toBeVisible();
    await page.locator('.fixed.inset-0').last().locator('button').first().click();
    const next = page.getByRole('region', { name: 'Prochaine action' });
    await expect(next.getByRole('button')).toHaveCount(1);
    await expect(next.getByText('Remplacement façades bureau')).toBeVisible();
    await next.getByRole('button', { name: 'Suivre le devis envoyé' }).click();
    await expect(page).toHaveURL(/\/sales\/301\?from=crm$/);
});

test('l’accueil sans client mène à la création de la première fiche', async ({ page }) => {
    await mockCRMCommerceAPI(page);
    await page.route('**/api/v2/partners/clients', route => json(route, []));
    await page.route('**/api/v2/sales/', route => json(route, []));
    await page.route('**/api/v2/mmg/', route => json(route, []));
    await page.goto('/crm');

    await expect(page.getByText('Aucune action commerciale en attente.')).toBeVisible();
    await page.getByRole('button', { name: 'Ajouter un client', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Créer une fiche client exploitable' })).toBeVisible();
});

test('un métré validé ouvre sa mission pour préparer le devis lié', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockCRMCommerceAPI(page, { quoteReady: true });
    await page.goto('/crm');
    await page.getByRole('button', { name: 'Clients & contacts', exact: true }).click();
    const next = page.getByRole('region', { name: 'Prochaine action' });
    await next.getByRole('button', { name: 'Préparer le devis lié' }).click();
    await expect(page).toHaveURL(/\/measure-missions\/401$/);
});

test('les commandes ouvrent en liste et gardent la vue par étape', async ({ page }) => {
    await mockCRMCommerceAPI(page);
    await page.goto('/manager?view=sales');
    const order = page.getByRole('button', { name: /COM-CRM-E2E-002/ });
    await expect(order).toContainText('Préparer la facture finale');
    await page.getByRole('button', { name: 'Vue par étape', exact: true }).click();
    await expect(page.getByText('COM-CRM-E2E-002', { exact: true })).toHaveCount(1);
    await expect(page.getByText('Préparer la facture finale', { exact: true })).toBeVisible();
});

test('la facturation sépare les encaissements du reste dû et du crédit client', async ({ page }) => {
    await mockCRMCommerceAPI(page);
    await page.goto('/manager?view=accounting');
    await expect(page.locator('dl div').filter({ hasText: 'Encaissé' })).toContainText('40,00');
    await expect(page.locator('dl div').filter({ hasText: 'Reste dû' })).toContainText('120,00');
    await expect(page.locator('dl div').filter({ hasText: 'Crédit client' })).toContainText('40,00');
    const filter = page.getByRole('combobox', { name: 'Filtrer les factures' });
    await filter.selectOption('DUE');
    await expect(page.getByRole('row').filter({ hasText: 'F-002' })).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: 'F-001' })).toHaveCount(0);
    await filter.selectOption('CUSTOMER_CREDIT');
    const credited = page.getByRole('row').filter({ hasText: 'F-001' });
    await expect(credited).toContainText('CRÉDITÉE');
    await expect(credited.getByRole('button')).toHaveCount(1);
});
