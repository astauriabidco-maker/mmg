import { expect, test } from '@playwright/test';


const now = '2026-09-05T08:00:00Z';

function json(route, body, status = 200) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
    });
}

async function mockCRMCommerceAPI(page) {
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
            stage: 'proposition_envoyee',
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
        localStorage.setItem('role', 'SALES');
        localStorage.setItem('roles', JSON.stringify(['SALES']));
        localStorage.setItem('stations', JSON.stringify([]));
        localStorage.setItem('permissions', JSON.stringify(['SALES_VIEW', 'SALES_EDIT']));
        localStorage.removeItem('mmg.crm.clientFilters.v1');
    });

    await page.route('http://localhost:7000/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
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
        if (path === '/v2/sales/' && method === 'GET') return json(route, sales);
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

async function closeVisibleModal(page) {
    await page.locator('.fixed.inset-0').last().locator('button').first().click();
}

test('Commerce & Ventes keeps the certified seller journey visible and guided', async ({ page }) => {
    await mockCRMCommerceAPI(page);

    await page.goto('/crm');

    await expect(page.getByText('Commerce & ventes')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Commencer par la prochaine action commerciale.' })).toBeVisible();
    await expect(page.getByText('Parcours vendeur').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'À traiter maintenant' })).toBeVisible();
    await expect(page.getByText('File commerciale')).toBeVisible();
    await expect(page.getByText('À traiter en priorité')).toBeVisible();
    await expect(page.getByText('CLIENT RECETTE COMMERCE').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Ouvrir \/ relancer|Traiter relance|Suivre métré/ }).first()).toBeVisible();

    await page.getByRole('button', { name: 'Pilotage commercial' }).first().click();
    await expect(page.getByText('Pipeline pondéré')).toBeVisible();
    await expect(page.getByText('CA signé').first()).toBeVisible();
    await expect(page.getByText('Conversion, CA signé et risques par responsable')).toBeVisible();

    await page.getByRole('button', { name: 'Pipeline' }).first().click();
    await expect(page.getByRole('heading', { name: 'Proposition envoyée' })).toBeVisible();
    await expect(page.getByText('Remplacement façades bureau')).toBeVisible();

    await page.getByRole('button', { name: 'Métrés / BE' }).first().click();
    await expect(page.getByText('Missions de métré')).toBeVisible();
    await expect(page.getByText('Contrôle BE').first()).toBeVisible();

    await page.getByRole('button', { name: 'Clients & contacts' }).first().click();
    await expect(page.getByPlaceholder('Client, téléphone...')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'CLIENT RECETTE COMMERCE' })).toBeVisible();
    await expect(page.getByText('Score commercial')).toBeVisible();
    await expect(page.getByText('Résumé auto')).toBeVisible();
    await expect(page.getByText('Meilleure prochaine action')).toBeVisible();

    await page.getByRole('button', { name: 'Nouveau client' }).first().click();
    await expect(page.getByRole('heading', { name: 'Créer une fiche client exploitable' })).toBeVisible();
    await expect(page.getByText('Identité → contact → qualification')).toBeVisible();
    await closeVisibleModal(page);

    await page.getByRole('button', { name: 'Préparer un devis' }).first().click();
    await expect(page.getByRole('heading', { name: 'Préparer un brouillon de devis' })).toBeVisible();
    await expect(page.getByText('aucun stock réservé à cette étape')).toBeVisible();
    await closeVisibleModal(page);

    await page.getByRole('button', { name: 'Lancer un métré' }).first().click();
    await expect(page.getByText('Métré assisté · BE')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Choisir la source des cotes' })).toBeVisible();
    await expect(page.getByText('Garde-fou : les cotes alimentent le BE et le devis')).toBeVisible();
});
