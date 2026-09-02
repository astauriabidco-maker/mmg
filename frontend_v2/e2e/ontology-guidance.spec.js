import { expect, test } from '@playwright/test';


const now = '2026-09-02T16:00:00Z';

function json(route, body, status = 200) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
    });
}

const ontology = {
    modules: ['CRM', 'BE', 'DEVIS', 'COMMANDE', 'FABRICATION', 'STOCK', 'DEBIT'],
    pipeline: [
        'client',
        'crm_opportunity',
        'measure_mission',
        'technical_dossier',
        'technical_quotation',
        'commercial_quote',
        'signed_order',
        'industrial_dossier',
        'fabrication_sheet',
        'cutting_sheet',
        'stock_reservation',
        'workshop_preparation',
        'production_order',
        'real_workshop_debit',
    ],
    entities: {
        crm_opportunity: {
            id: 'crm_opportunity',
            label: 'Opportunité avant-vente',
            module: 'CRM',
            definition: 'Projet commercial suivi avant signature, de la qualification au gagné/perdu.',
        },
        measure_mission: {
            id: 'measure_mission',
            label: 'Mission de métré',
            module: 'BE',
            definition: 'Collecte et vérification des cotes, photos et contraintes chantier.',
        },
        technical_dossier: {
            id: 'technical_dossier',
            label: 'Dossier technique BE',
            module: 'BE',
            definition: 'Dossier gouverné par le BE qui regroupe les versions de chiffrage, fabrication et débit.',
        },
        technical_quotation: {
            id: 'technical_quotation',
            label: 'Chiffrage technique',
            module: 'BE',
            definition: 'Résultat technique issu de PROGES, ORGADATA ou saisie interne servant à préparer le devis commercial.',
        },
        commercial_quote: {
            id: 'commercial_quote',
            label: 'Devis commercial MMG',
            module: 'DEVIS',
            definition: 'Proposition commerciale envoyable au client, avec prix, lignes et conditions MMG.',
        },
        fabrication_sheet: {
            id: 'fabrication_sheet',
            label: 'Fiche fabrication',
            module: 'FABRICATION',
            definition: "Document d'atelier décrivant comment fabriquer les ouvrages, sans valoir consommation matière.",
        },
        cutting_sheet: {
            id: 'cutting_sheet',
            label: 'Fiche de débit',
            module: 'DEBIT',
            definition: 'Liste matière à couper ou consommer, base de réservation puis débit atelier.',
        },
        stock_item: {
            id: 'stock_item',
            label: 'Référence matière stock',
            module: 'STOCK',
            definition: 'Article ou variante stockable identifié par fournisseur, référence, unité et emplacement.',
        },
        stock_reservation: {
            id: 'stock_reservation',
            label: 'Réservation stock atelier',
            module: 'STOCK',
            definition: "Blocage logique des références matière nécessaires à une fiche de débit pour une commande.",
        },
        workshop_preparation: {
            id: 'workshop_preparation',
            label: 'Bon de préparation atelier',
            module: 'STOCK',
            definition: "Mise à disposition physique en zone atelier d'une réservation stock active.",
        },
        production_order: {
            id: 'production_order',
            label: 'Ordre de fabrication',
            module: 'FABRICATION',
            definition: 'Ordre atelier lancé après validation technique, stock et commande.',
        },
        real_workshop_debit: {
            id: 'real_workshop_debit',
            label: 'Débit atelier réel',
            module: 'DEBIT',
            definition: 'Consommation effective du stock après lancement fabrication et remise matière à l’atelier.',
        },
    },
    entity_statuses: {
        crm_opportunity: [
            { entity: 'crm_opportunity', code: 'nouveau', label: 'Nouvelle' },
            { entity: 'crm_opportunity', code: 'qualifie', label: 'Qualifiée' },
            { entity: 'crm_opportunity', code: 'metre_a_planifier', label: 'Métré à planifier' },
            { entity: 'crm_opportunity', code: 'metre_en_cours', label: 'Métré en cours' },
        ],
        technical_dossier: [
            { entity: 'technical_dossier', code: 'DRAFT', label: 'Brouillon' },
            { entity: 'technical_dossier', code: 'UNDER_REVIEW', label: 'En contrôle BE' },
            { entity: 'technical_dossier', code: 'APPROVED', label: 'Validé BE' },
            { entity: 'technical_dossier', code: 'REJECTED', label: 'À corriger' },
        ],
        commercial_quote: [
            { entity: 'commercial_quote', code: 'DRAFT', label: 'Brouillon' },
            { entity: 'commercial_quote', code: 'SENT', label: 'Envoyé' },
            { entity: 'commercial_quote', code: 'SIGNED', label: 'Signé' },
        ],
        stock_reservation: [
            { entity: 'stock_reservation', code: 'DRAFT', label: 'Brouillon' },
            { entity: 'stock_reservation', code: 'ACTIVE', label: 'Active' },
            { entity: 'stock_reservation', code: 'CONSUMED', label: 'Consommée' },
        ],
        production_order: [
            { entity: 'production_order', code: 'PLANNED', label: 'Planifié' },
            { entity: 'production_order', code: 'LAUNCHED', label: 'Lancé' },
        ],
    },
    external_document_mappings: [
        {
            source_system: 'ORGADATA',
            document_type: 'FABRICATION',
            canonical_entity: 'fabrication_sheet',
            label: 'Fiche fabrication ORGADATA ALU',
            definition: 'Instructions de fabrication atelier ; ne déclenche pas seule la consommation stock.',
            forbidden_confusions: ['cutting_sheet', 'real_workshop_debit'],
        },
        {
            source_system: 'ORGADATA',
            document_type: 'CUTTING',
            canonical_entity: 'cutting_sheet',
            label: 'Liste débit ORGADATA ALU',
            definition: 'Liste matière ALU à réserver puis débiter.',
            forbidden_confusions: ['fabrication_sheet', 'technical_quotation', 'real_workshop_debit'],
        },
    ],
    business_events: [
        { code: 'crm_opportunity_created', label: 'Opportunité créée', source_entity: 'crm_opportunity', target_entity: null, description: 'Création du dossier avant-vente.' },
        { code: 'measure_submitted_to_be', label: 'Métré soumis au BE', source_entity: 'measure_mission', target_entity: 'technical_dossier', description: 'Passage des cotes en contrôle technique.' },
        { code: 'technical_dossier_validated', label: 'Dossier technique validé BE', source_entity: 'technical_dossier', target_entity: 'commercial_quote', description: 'Validation technique.' },
        { code: 'quote_sent', label: 'Devis envoyé', source_entity: 'commercial_quote', target_entity: 'client', description: 'Transmission de la proposition.' },
        { code: 'quote_signed', label: 'Devis signé', source_entity: 'commercial_quote', target_entity: 'signed_order', description: 'Acceptation client.' },
        { code: 'stock_reserved', label: 'Stock réservé', source_entity: 'cutting_sheet', target_entity: 'stock_reservation', description: 'Réservation des matières.' },
        { code: 'workshop_prepared', label: 'Bon atelier préparé', source_entity: 'stock_reservation', target_entity: 'workshop_preparation', description: 'Mise à disposition atelier.' },
        { code: 'production_launched', label: 'Fabrication lancée', source_entity: 'production_order', target_entity: 'real_workshop_debit', description: 'Autorisation atelier.' },
        { code: 'stock_consumed', label: 'Débit consommé', source_entity: 'real_workshop_debit', target_entity: 'stock_item', description: 'Sortie effective du stock.' },
    ],
    step_rbac: [
        { entity: 'crm_opportunity', action: 'read', permission: 'SALES_VIEW', description: 'Consulter le pipeline avant-vente.' },
        { entity: 'crm_opportunity', action: 'write', permission: 'SALES_EDIT', description: 'Modifier une opportunité.' },
        { entity: 'measure_mission', action: 'write', permission: 'SALES_EDIT', description: 'Créer ou soumettre une mission de métré.' },
        { entity: 'technical_dossier', action: 'review', permission: 'PRODUCTION_MANAGE', description: 'Valider ou rejeter le dossier BE.' },
        { entity: 'commercial_quote', action: 'write', permission: 'SALES_EDIT', description: 'Préparer un devis commercial.' },
        { entity: 'stock_reservation', action: 'write', permission: 'STOCK_MANAGE', description: 'Créer une réservation matière.' },
        { entity: 'workshop_preparation', action: 'write', permission: 'STOCK_MANAGE', description: 'Préparer le bon atelier.' },
        { entity: 'production_order', action: 'launch', permission: 'PRODUCTION_MANAGE', description: 'Lancer la fabrication.' },
        { entity: 'real_workshop_debit', action: 'consume', permission: 'STOCK_MANAGE', description: 'Débiter réellement la matière.' },
    ],
    workflow_gates: [],
    relations: [],
    model_bindings: {},
};

const fabricationVersion = {
    id: 31,
    dossier_id: 6,
    version_number: 4,
    document_type: 'FABRICATION',
    source_system: 'ORGADATA',
    source_reference: 'ALU-E2E-002',
    original_filename: 'orgadata-fabrication-anonymise.pdf',
    content_type: 'application/pdf',
    file_size: 42000,
    checksum_sha256: 'c'.repeat(64),
    opening_ids: [201],
    analysis_status: 'PARSED',
    detected_document_type: 'FABRICATION',
    detected_source_system: 'ORGADATA',
    detected_project_reference: 'ALU-E2E-002',
    parsed_summary: { opening_count: 1, total_quantity: 1, systems: { CORTIZO: 1 }, with_glazing: 1, with_accessories: 1 },
    parsed_records: [{ position: 'F01', description: 'Menuiserie ALU anonymisée', width_mm: 1200, height_mm: 1400, quantity: 1, system: 'CORTIZO' }],
    parsed_issues: [],
    comparison_summary: {},
    impact_status: 'INITIAL',
    revision_after_launch: false,
    revision_status: 'NOT_REQUIRED',
    created_by: 'be-e2e',
    created_at: now,
};

const cuttingVersion = {
    id: 32,
    dossier_id: 6,
    version_number: 6,
    document_type: 'CUTTING',
    source_system: 'ORGADATA',
    source_reference: 'ALU-E2E-002',
    original_filename: 'orgadata-cutting-anonymise.pdf',
    content_type: 'application/pdf',
    file_size: 36000,
    checksum_sha256: 'd'.repeat(64),
    opening_ids: [201],
    analysis_status: 'PARSED',
    detected_document_type: 'CUTTING',
    detected_source_system: 'ORGADATA',
    detected_project_reference: 'ALU-E2E-002',
    parsed_summary: { debit_lines: 3, total_quantity: 9, unique_references: 3 },
    parsed_records: [
        { reference: 'COR-E2E-001', supplier: 'CORTIZO', quantity: 4, unit: 'barre', length_mm: 6500 },
        { reference: 'COR-E2E-002', supplier: 'CORTIZO', quantity: 3, unit: 'barre', length_mm: 6500 },
        { reference: 'COR-E2E-003', supplier: 'CORTIZO', quantity: 2, unit: 'pce' },
    ],
    parsed_issues: [],
    comparison_summary: { added_count: 3, removed_count: 0, changed_count: 0, quantity_delta: 0, has_changes: false },
    impact_status: 'INITIAL',
    revision_after_launch: false,
    revision_status: 'NOT_REQUIRED',
    stock_data_approved_at: now,
    stock_data_approved_by: 'stock-e2e',
    created_by: 'be-e2e',
    created_at: now,
};

const technicalDossier = {
    id: 6,
    reference: 'DT-E2E-002',
    mission_id: 6,
    quoting_status: 'VALIDATED',
    production_status: 'VALIDATED',
    external_source_system: 'ORGADATA',
    external_project_reference: 'ALU-E2E-002',
    stock_status: 'VALIDATED',
    stock_validated_at: now,
    stock_validated_by: 'stock-e2e',
    launch_status: 'VALIDATED',
    launch_validated_at: now,
    launch_validated_by: 'atelier-e2e',
    launched_at: now,
    launched_by: 'atelier-e2e',
    production_validated_at: now,
    production_validated_by: 'be-e2e',
    versions: [fabricationVersion, cuttingVersion],
};

const mission = {
    id: 6,
    reference: 'MET-E2E-006',
    client_id: 2,
    client_name: 'CLIENT ANONYMISE',
    opportunity_id: 2,
    site_address_id: 2,
    site_reference: 'CHANTIER-ANON-002',
    assigned_user_id: 2,
    assigned_user_name: 'BE Test',
    source_type: 'SITE_VISIT',
    project_scope: 'SUPPLY_AND_INSTALL',
    status: 'QUOTED',
    verification_status: 'READY_FOR_FABRICATION',
    sale_order_id: 42,
    sale_order_status: 'VALIDATED',
    purpose: 'Recette ORGADATA ALU anonymisée',
    notes: null,
    scheduled_start: now,
    scheduled_end: '2026-09-02T18:00:00Z',
    openings: [
        { id: 201, sequence: 1, label: 'F01', room: 'Séjour', product_type: 'WINDOW', width_mm: 1200, height_mm: 1400, material: 'ALU', status: 'VALIDATED', documents: [] },
    ],
    source_documents: [],
    technical_dossier: technicalDossier,
};

const governance = {
    dossier_reference: technicalDossier.reference,
    external_source_system: 'ORGADATA',
    external_project_reference: 'ALU-E2E-002',
    document_matrix: {
        complete: true,
        reference_consistent: true,
        documents: [
            { document_type: 'FABRICATION', required: true, present: true, version_number: 4 },
            { document_type: 'CUTTING', required: true, present: true, version_number: 6 },
            { document_type: 'VALUATION', required: false, present: false },
        ],
    },
    stock: { ready: true, line_count: 3, ok_count: 3, unknown_count: 0, shortage_count: 0 },
    execution: {
        sale_order_id: 42,
        reservation: {
            id: 90,
            reference: 'RSV-E2E-0090',
            status: 'consumed',
            source_label: 'dossier_technique',
            cutting_version_id: cuttingVersion.id,
        },
        preparation: {
            id: 12,
            reference: 'BPA-E2E-0012',
            status: 'consumed',
        },
        consumption: { status: 'consumed' },
        consumed: true,
        production_orders: [{ id: 7, reference: 'OF-E2E-0007' }],
    },
    gates: { be: 'VALIDATED', stock: 'VALIDATED', launch: 'VALIDATED' },
    latest_revision: {
        version_id: cuttingVersion.id,
        version_number: cuttingVersion.version_number,
        impact_status: 'INITIAL',
        revision_after_launch: false,
        revision_status: 'NOT_REQUIRED',
        comparison_summary: { added_count: 3, removed_count: 0, changed_count: 0, quantity_delta: 0, has_changes: false },
    },
};

async function authenticate(page) {
    await page.addInitScript(() => {
        localStorage.setItem('token', 'e2e-ontology-token');
        localStorage.setItem('username', 'ontology-e2e');
        localStorage.setItem('role', 'ADMIN');
        localStorage.setItem('roles', JSON.stringify(['ADMIN']));
        localStorage.setItem('stations', JSON.stringify([]));
        localStorage.setItem('permissions', JSON.stringify([
            'SALES_VIEW',
            'SALES_EDIT',
            'STOCK_VIEW',
            'STOCK_MANAGE',
            'PRODUCTION_MANAGE',
            'workshop.reserve_stock',
            'workshop.consume_stock',
        ]));
    });
}

async function mockApi(page) {
    await page.route('http://localhost:7000/**', async route => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;

        if (path === '/v2/mmg/ontology') return json(route, ontology);
        if (path === '/v2/mmg/missions/6') return json(route, mission);
        if (path === '/v2/mmg/missions/6/technical-dossier/governance') return json(route, governance);
        if (path === '/v2/mmg/crm/cockpit') {
            return json(route, {
                generated_at: now,
                horizon_days: 14,
                metrics: {
                    open_opportunities: 1,
                    pipeline_amount: 12000,
                    weighted_pipeline_amount: 9000,
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
            path === '/v2/partners/clients'
            || path === '/v2/partners/clients/duplicates'
            || path === '/v2/sales/'
            || path === '/v2/mmg/'
            || path === '/v2/mmg/sites'
            || path === '/v2/mmg/activities'
            || path === '/v2/mmg/opportunities'
            || path === '/v2/mmg/crm/reminder-templates'
            || path === '/v2/mmg/crm/reminders/history'
            || path === '/v2/mmg/crm/reminder-rules'
            || path === '/v2/mmg/crm/reminder-plans'
            || path === '/v2/config/users'
            || path === '/v2/config/app_configs'
            || path === '/v2/suppliers/'
            || path === '/v2/stock/products'
            || path === '/v2/stock/locations'
            || path === '/v2/stock/quants'
            || path === '/v2/stock/transactions'
            || path === '/v2/stock/workshop-preparations'
            || path === '/v2/stock/inventory-sessions'
            || path === '/v2/purchases/'
            || path === '/v2/purchases/needs'
        ) {
            return json(route, []);
        }

        if (path === '/v2/stock/workshop-debits/contexts') {
            return json(route, { sales: [], production_orders: [] });
        }
        if (path === '/v2/stock/workshop-debits/reservations') {
            return json(route, [{
                id: 90,
                reference: 'RSV-E2E-0090',
                status: 'reserved',
                sale_order_reference: 'DEV-E2E-0042',
                sale_status: 'IN_PRODUCTION',
                line_count: 3,
                production_order_id: 7,
            }]);
        }

        return json(route, []);
    });
}

test.beforeEach(async ({ page }) => {
    await authenticate(page);
    await mockApi(page);
});

test('CRM cockpit exposes active ontology guidance', async ({ page }) => {
    await page.goto('/crm');

    await expect(page.getByRole('heading', { name: 'CRM Avant-vente' })).toBeVisible();
    await expect(page.getByText('ONTOLOGIE ACTIVE').first()).toBeVisible();
    await expect(page.getByText('Flux avant-vente certifié')).toBeVisible();
    await expect(page.getByText('Opportunité avant-vente', { exact: true })).toBeVisible();
    await expect(page.getByText('Mission de métré', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Dossier technique BE', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Devis commercial MMG', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('WRITE · SALES_EDIT').first()).toBeVisible();
    await expect(page.getByText('MÉTRÉ SOUMIS AU BE')).toBeVisible();
    await expect(page.getByText('DEVIS SIGNÉ')).toBeVisible();
});

test('BE and workshop dossier expose ontology guardrails and ORGADATA classifications', async ({ page }) => {
    await page.goto('/measure-missions/6');

    await expect(page.getByText('Repère BE → devis')).toBeVisible();
    await expect(page.getByText('Chiffrage technique', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Devis commercial MMG', { exact: true }).first()).toBeVisible();

    await page.getByRole('button', { name: '2. Fabrication & débit' }).click();

    await expect(page.getByText('Repère fabrication → stock → débit')).toBeVisible();
    await expect(page.getByText('La fiche fabrication décrit les ouvrages ; seule la fiche de débit alimente la réservation puis le débit réel.')).toBeVisible();
    await expect(page.getByText('Fiche fabrication', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Fiche de débit', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Ordre métier verrouillé')).toBeVisible();
    await expect(page.getByText('Réserver stock → préparer/remettre le bon atelier → lancer fabrication → consommer le débit réel.')).toBeVisible();
    await expect(page.getByText('CONSUME · STOCK_MANAGE').first()).toBeVisible();

    await page.getByRole('button', { name: 'Importer une nouvelle révision' }).click();
    await page.locator('select').first().selectOption('FABRICATION');
    await page.locator('select').nth(1).selectOption('ORGADATA');
    await expect(page.getByText('ORGADATA/FABRICATION')).toBeVisible();
    await expect(page.getByText('Fiche fabrication ORGADATA ALU')).toBeVisible();

    await page.locator('select').first().selectOption('CUTTING');
    await expect(page.getByText('ORGADATA/CUTTING')).toBeVisible();
    await expect(page.getByText('Liste débit ORGADATA ALU')).toBeVisible();
});

test('stock dashboard exposes ontology guardrail before workshop debit', async ({ page }) => {
    await page.goto('/stock');

    await expect(page.getByText('ONTOLOGIE ACTIVE').first()).toBeVisible();
    await expect(page.getByText('Garde-fou stock / atelier')).toBeVisible();
    await expect(page.getByText('Le stock réel est consommé uniquement après réservation, préparation atelier et lancement fabrication.')).toBeVisible();
    await expect(page.getByText(/Référence matière stock/i)).toBeVisible();
    await expect(page.getByText(/Réservation stock atelier/i)).toBeVisible();
    await expect(page.getByText(/Bon de préparation atelier/i)).toBeVisible();
    await expect(page.getByText(/Ordre de fabrication/i)).toBeVisible();
    await expect(page.getByText(/Débit atelier réel/i)).toBeVisible();
    await expect(page.getByText('CONSUME · STOCK_MANAGE').first()).toBeVisible();
});
