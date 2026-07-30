import { expect, test } from '@playwright/test';


const backendURL = 'http://127.0.0.1:7100';

test('inventory campaign is counted offline, evidenced, approved and archived', async ({ context, page, request }) => {
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

    await page.goto('/stock');
    await page.getByRole('button', { name: 'Inventaire physique' }).click();
    await expect(page.getByRole('heading', { name: 'Inventaire physique' })).toBeVisible();

    const campaignForm = page.locator('form').filter({ hasText: 'Nouvelle campagne' });
    await campaignForm.getByPlaceholder('Ex: Comptage WH semaine 29').fill('Cycle E2E aluminium');
    await campaignForm.locator('select').nth(0).selectOption({ label: 'WH/Stock' });
    await campaignForm.locator('select').nth(1).selectOption('cycle');
    await campaignForm.getByPlaceholder('Cycle (jours)').fill('30');
    await campaignForm.getByPlaceholder('Seuil approb. €').fill('5');
    await campaignForm.getByText('Inclure toutes les variantes actives').click();
    await campaignForm.getByRole('button', { name: 'Créer la campagne' }).click();

    await expect(page.getByRole('heading', { name: 'Cycle E2E aluminium' })).toBeVisible();
    const countForm = page.locator('form').filter({ has: page.getByPlaceholder('Scanner ou taper une réf.') });
    await context.setOffline(true);
    await countForm.getByPlaceholder('Scanner ou taper une réf.').fill('E2E-PROFILE-001');
    await countForm.getByPlaceholder('Scanner ou taper une réf.').press('Enter');
    await countForm.locator('input[type="number"]').fill('16');
    await countForm.getByPlaceholder('Casse, erreur, retour...').fill('Saisie tablette hors ligne');
    await countForm.getByRole('button', { name: 'Ajouter' }).click();
    await expect(page.getByText('1 saisie(s) en attente de synchronisation')).toBeVisible();

    await context.setOffline(false);
    await expect(page.getByText('1 saisie(s) en attente de synchronisation')).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Par e2e_admin · v\d+/)).toBeVisible();

    await countForm.getByPlaceholder('Scanner ou taper une réf.').fill('E2E-PROFILE-001');
    await countForm.getByPlaceholder('Scanner ou taper une réf.').press('Enter');
    await countForm.locator('input[type="number"]').fill('15');
    await countForm.getByPlaceholder('Casse, erreur, retour...').fill('Contrôle E2E');
    await countForm.locator('input[type="file"]').setInputFiles({
        name: 'justificatif-inventaire.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('Justificatif anonymisé de recette inventaire.'),
    });
    await countForm.getByRole('button', { name: 'Ajouter' }).click();

    await expect(page.getByText('justificatif-inventaire.txt')).toBeVisible();
    await expect(page.getByText(/Par e2e_admin · v\d+/)).toBeVisible();
    await page.getByRole('button', { name: 'Valider les écarts' }).click();
    await expect(page.getByRole('button', { name: 'Approuver la valeur' })).toBeVisible();
    await page.getByRole('button', { name: 'Approuver la valeur' }).click();
    await expect(page.getByText(/Valeur approuvée · e2e_admin/)).toBeVisible();
    await page.getByRole('button', { name: 'Appliquer les ajustements' }).click();
    await expect(page.getByRole('button', { name: 'Archiver' })).toBeVisible();

    const quantResponse = await request.get(`${backendURL}/v2/stock/quants`, { headers: apiHeaders });
    expect(quantResponse.ok()).toBeTruthy();
    const quants = await quantResponse.json();
    expect(quants.find(quant => quant.variant_id === 1 && quant.location_id === 1)?.quantity).toBe(15);

    await page.getByRole('button', { name: 'Archiver' }).click();
    await expect(page.getByRole('heading', { name: 'Cycle E2E aluminium · cycle suivant', exact: true })).toBeVisible();
    const archivedResponse = await request.get(
        `${backendURL}/v2/stock/inventory-sessions-page?include_archived=true&search=Cycle%20E2E%20aluminium`,
        { headers: apiHeaders },
    );
    expect(archivedResponse.ok()).toBeTruthy();
    const archivedPage = await archivedResponse.json();
    expect(archivedPage.items.find(session => session.name === 'Cycle E2E aluminium')?.archived_at).toBeTruthy();
});
