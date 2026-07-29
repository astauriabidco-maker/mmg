import { expect, test } from '@playwright/test';


const backendURL = 'http://127.0.0.1:7100';

test('signed dossier reaches production and a consumed workshop debit', async ({ page, request }) => {
    const loginResponse = await request.post(`${backendURL}/token`, {
        form: {
            username: 'e2e_admin',
            password: '1234',
        },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const auth = await loginResponse.json();
    const apiHeaders = { Authorization: `Bearer ${auth.access_token}` };

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
    page.on('dialog', dialog => dialog.accept());

    await page.goto('/measure-missions/1');
    await page.getByRole('button', { name: '2. Fabrication & débit' }).click();

    const fabricationUpload = page
        .locator('label')
        .filter({ hasText: 'Importer la fabrication' })
        .locator('input[type="file"]');
    await fabricationUpload.setInputFiles({
        name: 'proges-fabrication-anonymisee.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from([
            'SEPALUMIC GAMME BASE',
            "BON D'ATELIER",
            'Affaire: E2E-ALU-001',
            'Document de fabrication anonymisé',
        ].join('\n')),
    });
    await expect(page.getByText('proges-fabrication-anonymisee.txt')).toBeVisible();

    await page.locator('select:has(option[value="CUTTING"])').selectOption('CUTTING');
    const cuttingUpload = page
        .locator('label')
        .filter({ hasText: 'Importer le débit' })
        .locator('input[type="file"]');
    await cuttingUpload.setInputFiles({
        name: 'SEP-E2E-debit-anonymise.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from([
            'SEPALUMIC GAMME BASE',
            'Affaire: E2E-ALU-001',
            'BLANC;E2E-PROFILE-001;Profilé aluminium anonymisé;2;Barre 6,5',
        ].join('\n')),
    });

    await expect(page.getByText('SEP-E2E-debit-anonymise.txt')).toBeVisible();
    await expect(page.getByText('E2E-PROFILE-001').first()).toBeVisible();
    await page.getByRole('button', { name: 'Envoyer au contrôle BE' }).click();
    await expect(page.getByRole('button', { name: 'Valider BE' })).toBeVisible();
    await page.getByRole('button', { name: 'Valider BE' }).click();

    await expect(page.getByRole('button', { name: 'Valider les données stock' })).toBeVisible();
    await page.getByRole('button', { name: 'Valider les données stock' }).click();

    await expect(page.getByRole('button', { name: 'Créer la réservation depuis ce débit' })).toBeEnabled();
    await page.getByRole('button', { name: 'Créer la réservation depuis ce débit' }).click();

    const executionFlow = page.getByLabel("Flux d'exécution atelier");
    await expect(executionFlow.getByText(/RSV-ATELIER-\d+ · réservée/)).toBeVisible();
    await expect(executionFlow.getByText('À créer dans le module Stock')).toBeVisible();
    await expect(page.getByText(/créée depuis le débit validé/)).toBeVisible();

    let governanceResponse = await request.get(
        `${backendURL}/v2/mmg/missions/1/technical-dossier/governance`,
        { headers: apiHeaders },
    );
    expect(governanceResponse.ok()).toBeTruthy();
    let governance = await governanceResponse.json();
    expect(governance.gates).toEqual({
        be: 'VALIDATED',
        stock: 'VALIDATED',
        launch: 'TO_REVIEW',
    });
    expect(governance.execution.reservation.cutting_version_id).toBe(2);
    expect(governance.execution.reservation.status).toBe('reserved');

    const reservationId = governance.execution.reservation.id;
    await page.getByRole('button', { name: 'Autoriser le lancement atelier' }).click();
    await expect(page.getByRole('button', { name: 'Ouvrir la commande et lancer la production' })).toBeVisible();
    await page.getByRole('button', { name: 'Ouvrir la commande et lancer la production' }).click();

    await expect(page.getByRole('button', { name: 'Lancer la fabrication' })).toBeVisible();
    await page.getByRole('button', { name: 'Lancer la fabrication' }).click();
    await expect(page.getByRole('heading', { name: 'Timeline atelier' })).toBeVisible();

    const preparationResponse = await request.post(
        `${backendURL}/v2/stock/workshop-preparations`,
        {
            headers: apiHeaders,
            data: { reservation_id: reservationId },
        },
    );
    expect(preparationResponse.ok()).toBeTruthy();
    let preparation = await preparationResponse.json();
    expect(preparation.status).toBe('draft');

    for (const line of preparation.lines) {
        const preparedResponse = await request.patch(
            `${backendURL}/v2/stock/workshop-preparations/${preparation.id}/lines/${line.id}`,
            {
                headers: apiHeaders,
                data: { prepared_quantity: line.planned_quantity },
            },
        );
        expect(preparedResponse.ok()).toBeTruthy();
        preparation = await preparedResponse.json();
    }
    expect(preparation.status).toBe('ready');

    const handoverResponse = await request.post(
        `${backendURL}/v2/stock/workshop-preparations/${preparation.id}/handover`,
        { headers: apiHeaders },
    );
    expect(handoverResponse.ok()).toBeTruthy();

    const consumeResponse = await request.post(
        `${backendURL}/v2/stock/workshop-debits/reservations/${reservationId}/consume`,
        { headers: apiHeaders },
    );
    expect(consumeResponse.ok()).toBeTruthy();

    governanceResponse = await request.get(
        `${backendURL}/v2/mmg/missions/1/technical-dossier/governance`,
        { headers: apiHeaders },
    );
    expect(governanceResponse.ok()).toBeTruthy();
    governance = await governanceResponse.json();
    expect(governance.gates.launch).toBe('VALIDATED');
    expect(governance.execution.reservation.status).toBe('consumed');
    expect(governance.execution.preparation.status).toBe('consumed');
    expect(governance.execution.production_orders).toHaveLength(1);

    const saleResponse = await request.get(`${backendURL}/v2/sales/1`, { headers: apiHeaders });
    expect(saleResponse.ok()).toBeTruthy();
    const sale = await saleResponse.json();
    expect(sale.status).toBe('IN_PRODUCTION');
});
