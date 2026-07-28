import { expect, test } from '@playwright/test';


const now = '2026-07-28T10:00:00Z';

function json(route, body, status = 200, headers = {}) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        headers,
        body: JSON.stringify(body),
    });
}

test('commercial completes the CRM presales journey and merges a duplicate', async ({ page }) => {
    const clients = [];
    const contacts = new Map();
    const opportunities = [];
    let nextClientId = 1;
    let nextContactId = 1;
    let nextOpportunityId = 1;

    await page.addInitScript(() => {
        localStorage.setItem('token', 'e2e-sales-token');
        localStorage.setItem('username', 'commercial-e2e');
        localStorage.setItem('role', 'SALES');
        localStorage.setItem('roles', JSON.stringify(['SALES']));
        localStorage.setItem('stations', JSON.stringify([]));
        localStorage.setItem('permissions', JSON.stringify(['SALES_VIEW', 'SALES_EDIT']));
    });

    page.on('dialog', dialog => dialog.accept());

    await page.route('http://localhost:7000/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
        const method = request.method();

        if (path === '/v2/partners/clients' && method === 'GET') {
            return json(route, clients);
        }
        if (path === '/v2/partners/clients' && method === 'POST') {
            const payload = request.postDataJSON();
            const client = {
                id: nextClientId++,
                created_at: now,
                country: 'FR',
                contacts: [],
                ...payload,
            };
            clients.push(client);
            const initialContacts = [];
            if (payload.contact_name || payload.email || payload.phone) {
                initialContacts.push({
                    id: nextContactId++,
                    client_id: client.id,
                    name: payload.contact_name || payload.email || payload.phone,
                    role: 'Contact principal',
                    email: payload.email,
                    phone: payload.phone,
                    is_primary: true,
                    notes: null,
                    created_at: now,
                    updated_at: now,
                });
            }
            contacts.set(client.id, initialContacts);
            client.contacts = initialContacts;
            return json(route, client);
        }
        if (/^\/v2\/partners\/clients\/\d+$/.test(path) && method === 'PUT') {
            const clientId = Number(path.split('/').at(-1));
            const payload = request.postDataJSON();
            const index = clients.findIndex(client => client.id === clientId);
            clients[index] = { ...clients[index], ...payload };
            return json(route, clients[index]);
        }
        if (/^\/v2\/partners\/clients\/\d+\/contacts$/.test(path)) {
            const clientId = Number(path.split('/').at(-2));
            if (method === 'GET') return json(route, contacts.get(clientId) || []);
            const payload = request.postDataJSON();
            const records = contacts.get(clientId) || [];
            if (payload.is_primary) records.forEach(contact => { contact.is_primary = false; });
            const contact = {
                id: nextContactId++,
                client_id: clientId,
                created_at: now,
                updated_at: now,
                ...payload,
                is_primary: payload.is_primary || records.length === 0,
            };
            records.push(contact);
            contacts.set(clientId, records);
            return json(route, contact);
        }
        if (/^\/v2\/partners\/clients\/\d+\/contacts\/\d+$/.test(path) && method === 'PATCH') {
            const parts = path.split('/');
            const clientId = Number(parts.at(-3));
            const contactId = Number(parts.at(-1));
            const payload = request.postDataJSON();
            const records = contacts.get(clientId) || [];
            if (payload.is_primary) records.forEach(contact => { contact.is_primary = false; });
            const contact = records.find(item => item.id === contactId);
            Object.assign(contact, payload, { updated_at: now });
            return json(route, contact);
        }
        if (path === '/v2/partners/clients/duplicates' && method === 'GET') {
            const duplicateClients = clients.filter(client => client.email === 'contact@acme.test');
            return json(route, duplicateClients.length > 1 ? [{
                clients: duplicateClients,
                score: 100,
                reasons: ['Même email'],
            }] : []);
        }
        if (/^\/v2\/partners\/clients\/\d+\/merge$/.test(path) && method === 'POST') {
            const targetId = Number(path.split('/').at(-2));
            const payload = request.postDataJSON();
            const target = clients.find(client => client.id === targetId);
            for (const sourceId of payload.source_client_ids) {
                const sourceIndex = clients.findIndex(client => client.id === sourceId);
                if (sourceIndex >= 0) clients.splice(sourceIndex, 1);
            }
            return json(route, {
                target,
                merged_client_ids: payload.source_client_ids,
                moved_records: {},
            });
        }
        if (path === '/v2/sales/' && method === 'GET') return json(route, []);
        if (path === '/v2/mmg/' && method === 'GET') return json(route, []);
        if (path === '/v2/mmg/sites' && method === 'GET') return json(route, []);
        if (path === '/v2/mmg/activities' && method === 'GET') return json(route, []);
        if (path === '/v2/mmg/opportunities' && method === 'GET') {
            const clientId = Number(url.searchParams.get('client_id'));
            return json(route, opportunities.filter(item => !clientId || item.client_id === clientId));
        }
        if (path === '/v2/mmg/opportunities' && method === 'POST') {
            const payload = request.postDataJSON();
            const opportunity = {
                id: nextOpportunityId++,
                reference: `OPP-E2E-${nextOpportunityId}`,
                origin: 'AGENCE',
                owner_user_id: null,
                owner_name: null,
                sale_order_id: null,
                loss_reason: null,
                won_at: null,
                lost_at: null,
                created_by: 'commercial-e2e',
                created_at: now,
                updated_at: now,
                stage_entered_at: now,
                expected_close_date: null,
                ...payload,
            };
            opportunities.push(opportunity);
            return json(route, opportunity, 201);
        }
        if (path === '/v2/mmg/crm/reminder-plans/sync' && method === 'POST') {
            return json(route, { created: 0, cancelled: 0 });
        }
        if (path === '/v2/mmg/crm/cockpit' && method === 'GET') {
            return json(route, {
                generated_at: now,
                horizon_days: 14,
                metrics: {
                    open_opportunities: 0,
                    pipeline_amount: 0,
                    weighted_pipeline_amount: 0,
                    overdue_actions: 0,
                    reminders_today: 0,
                    overdue_reminders: 0,
                    opportunities_without_action: 0,
                    measures_to_schedule: 0,
                    automatic_reminders: 0,
                },
                stages: [],
                agenda: [],
                reminders: [],
                reminders_today: [],
                overdue_reminders: [],
                opportunities_without_action: [],
                owners: [],
                stage_conversions: [],
            });
        }
        if (
            path === '/v2/mmg/crm/reminder-templates'
            || path === '/v2/mmg/crm/reminders/history'
            || path === '/v2/mmg/crm/reminder-rules'
            || path === '/v2/mmg/crm/reminder-plans'
            || path === '/v2/config/users'
        ) {
            return json(route, []);
        }

        return json(route, []);
    });

    await page.goto('/crm');
    await expect(page.getByRole('heading', { name: 'CRM Avant-vente' })).toBeVisible();
    await page.getByRole('button', { name: 'Fiches clients' }).click();
    await page.getByRole('button', { name: 'Nouveau client' }).first().click();

    await page.getByPlaceholder('Entreprise ou particulier').fill('ACME Menuiseries');
    await page.getByPlaceholder('Nom du contact').fill('Mme Martin');
    await page.getByPlaceholder('client@example.com').fill('contact@acme.test');
    await page.getByPlaceholder('Ex. Grands comptes').fill('Architectes');
    await page.getByPlaceholder('Prioritaire, Prescription').fill('Prioritaire, Prescription');
    await page.getByRole('button', { name: 'Créer le client' }).click();

    await expect(page.getByRole('heading', { name: 'ACME Menuiseries' })).toBeVisible();
    await expect(page.locator('span').filter({ hasText: /^Architectes$/ })).toBeVisible();
    await expect(page.locator('span').filter({ hasText: /^Prescription$/ })).toBeVisible();

    await page.getByRole('button', { name: 'Ajouter un contact' }).click();
    await page.getByPlaceholder('Nom du contact').fill('M. Durand');
    await page.getByPlaceholder('Fonction / rôle').fill('Décisionnaire');
    await page.getByPlaceholder('Email').fill('durand@acme.test');
    await page.getByRole('button', { name: 'Enregistrer' }).click();
    await expect(page.getByText('M. Durand', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Nouvelle opportunité' }).first().click();
    await page.getByPlaceholder('Ex. Menuiseries chantier Bonapriso').fill('Rénovation du siège');
    await page.getByRole('button', { name: 'Enregistrer' }).click();
    await expect(page.getByText('Rénovation du siège', { exact: true }).first()).toBeVisible();

    await page.getByRole('button', { name: 'Nouveau client' }).first().click();
    await page.getByPlaceholder('Entreprise ou particulier').fill('ACME Menuiseries France');
    await page.getByPlaceholder('Nom du contact').fill('Mme Martin');
    await page.getByPlaceholder('client@example.com').fill('contact@acme.test');
    await page.getByRole('button', { name: 'Créer le client' }).click();

    await page.getByRole('button', { name: 'Doublons' }).click();
    await expect(page.getByText('Même email', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Fusionner' }).click();
    await expect(page.getByText('Fiches clients fusionnées avec leur historique.')).toBeVisible();
});
