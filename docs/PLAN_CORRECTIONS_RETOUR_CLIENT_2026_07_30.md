# MMG — mini-plan de corrections avant deuxième point client

> Créé le 2026-07-30 à partir du retour client en conditions réelles.
> Échéance visée : deuxième point client prévu lundi 2026-08-03.
> Source métier : `4 - RESSOURCES/par-projet/mmg/reunions/2026-07-30-tests-conditions-reelles.md`.

## Objectif

Arriver au point client du lundi 2026-08-03 avec une version plus fluide sur
les zones qui ont réellement gêné le client :

1. inventaire ;
2. parcours utilisateur global ;
3. vente / CRM avant-vente ;
4. documents externes Progest / Organata, noms à confirmer.

La cible n'est pas une refonte. La cible est un parcours suffisamment lisible
pour que le client voie que les frictions remontées ont été comprises et
traitées.

## Règle de tri

Chaque correction doit entrer dans une des trois catégories :

| Niveau | Définition | Décision |
|---|---|---|
| P0 | bloque ou décrédibilise le test client | à traiter avant lundi |
| P1 | crée une friction visible mais contournable | traiter si P0 terminé |
| P2 | amélioration utile mais non nécessaire au point client | noter, ne pas ouvrir maintenant |

Une correction est acceptée seulement si elle réduit un geste réel du client
ou clarifie une étape métier.

## 1. Module inventaire

### Problème remonté

Le module inventaire est jugé trop frictionnel. L'objectif client est de gagner
en efficacité, pas d'ajouter un rituel administratif.

### Hypothèse produit

Le client ne rejette pas nécessairement la logique d'inventaire. Il rejette le
nombre d'étapes, la charge cognitive ou le manque de guidage pour arriver au
résultat.

### À inspecter dans le code

- `frontend_v2/src/pages/StockDashboard.jsx`
- `frontend_v2/src/pages/StockMobileDashboard.jsx`
- `frontend_v2/e2e-real/inventory-complete.spec.js`
- `tests/test_inventory_operator_journey.py`
- `tests/test_inventory_physical_count_flow.py`
- `tests/test_inventory_prefill_blind_flow.py`

### Corrections candidates

| ID | Correction | Niveau | Critère d'acceptation |
|---|---|---|---|
| INV-1 | Ajouter un mode d'entrée rapide "scanner / référence / quantité / valider" visible dès l'ouverture de l'inventaire | P0 | un opérateur peut ajouter une ligne sans chercher le bon formulaire |
| INV-2 | Rendre explicite l'étape courante : créer campagne, compter, valider écarts, approuver, appliquer | P0 | l'utilisateur sait immédiatement quoi faire ensuite |
| INV-3 | Réduire les champs visibles par défaut dans le formulaire de comptage | P1 | seuls référence, quantité et note courte restent prioritaires |
| INV-4 | Ajouter un résumé final avant application des ajustements | P1 | le client voit ce qui va changer avant validation |
| INV-5 | Reporter les options avancées dans un panneau secondaire | P2 | les fonctions avancées ne polluent plus le flux principal |

## 2. Parcours utilisateur global

### Problème remonté

Il y a trop de clics pour arriver au résultat. Le client attend un gain de
temps, pas un système complet mais lourd.

### Hypothèse produit

Le problème prioritaire n'est pas uniquement graphique. C'est le manque de
"chemin évident" entre les étapes métier.

### À inspecter dans le code

- `frontend_v2/src/App.jsx`
- `frontend_v2/src/components/Sidebar.jsx`
- `frontend_v2/src/pages/SaleDetailPage.jsx`
- `frontend_v2/src/components/BusinessTimeline.jsx`
- `frontend_v2/src/utils/roleNavigation.js`

### Corrections candidates

| ID | Correction | Niveau | Critère d'acceptation |
|---|---|---|---|
| UX-1 | Ajouter un bouton primaire unique "Action suivante" sur les écrans critiques | P0 | sur un dossier, l'utilisateur voit une prochaine action claire |
| UX-2 | Regrouper les actions secondaires derrière "Plus d'actions" | P1 | l'écran ne présente pas 6 boutons concurrents au même niveau |
| UX-3 | Afficher une mini-frise métier sur les parcours dossier / vente / stock | P1 | le client comprend où il se trouve dans le workflow |
| UX-4 | Harmoniser les libellés avec le vocabulaire client entendu en réunion | P1 | les mots affichés correspondent mieux aux mots de l'atelier |
| UX-5 | Reporter les modules hors point client dans la navigation secondaire | P2 | la démo ne donne pas l'impression d'un ERP dispersé |

## 3. Vente / CRM avant-vente

### Problème remonté

Le bloc vente, notamment le CRM avant-vente, doit être revu. Le retour évoque
aussi des documents externes liés au flux commercial / technique.

### Hypothèse produit

Le client a besoin d'un parcours "prospect → opportunité → dossier exploitable"
plus direct. Les fonctions CRM riches sont moins importantes que la capacité à
enchaîner sans friction vers le dossier technique et la production.

### À inspecter dans le code

- `frontend_v2/src/pages/CRMWorkspacePage.jsx`
- `frontend_v2/src/pages/CRMClientsDashboard.jsx`
- `frontend_v2/src/components/CRMClientActionWorkspace.jsx`
- `frontend_v2/src/components/CRMOpportunityPipeline.jsx`
- `frontend_v2/src/components/CRMCockpit.jsx`
- `frontend_v2/src/pages/SalesDashboard.jsx`
- `frontend_v2/e2e/crm-presales.spec.js`
- `frontend_v2/e2e-real/crm-production-real.spec.js`
- `backend/services/crm_clients.py`
- `backend/services/crm_cockpit.py`
- `backend/services/crm_opportunity_workflow.py`

### Corrections candidates

| ID | Correction | Niveau | Critère d'acceptation |
|---|---|---|---|
| CRM-1 | Clarifier le parcours "créer client → créer opportunité → ouvrir dossier" | P0 | le commercial peut créer un dossier exploitable sans hésitation |
| CRM-2 | Mettre en avant les actions commerciales utiles au point client | P1 | relance, prise de mesure, devis et passage au dossier sont visibles |
| CRM-3 | Réduire les informations CRM non nécessaires au premier pilote | P1 | l'écran ne ressemble pas à un CRM généraliste trop large |
| CRM-4 | Vérifier que le Kanban / pipeline garde bien les changements utiles | P1 | les étapes avant-vente ne disparaissent pas ou ne se réinitialisent pas |
| CRM-5 | Lier clairement le CRM au dossier technique / vente | P0 | le client comprend comment l'avant-vente déclenche la suite |

## 4. Documents externes : Progest / Organata

### Problème remonté

La transcription mentionne "Progest" et "Organata". Les noms exacts doivent
être confirmés, mais le besoin est clair : les documents externes doivent être
plus faciles à intégrer ou à retrouver dans le parcours.

### À inspecter dans le code et la doc

- `docs/STOCK_IMPORT.md`
- `docs/WORKSHOP_DEBITS_IMPORT.md`
- `frontend_v2/src/pages/ManualUpload.jsx`
- `backend/services/mmg_to_proges.py`
- `backend/services/technical_document_analysis.py`
- `backend/services/technical_dossier_governance.py`
- `scripts/import_real_stock.py`
- `scripts/import_workshop_debits.py`

### Corrections candidates

| ID | Correction | Niveau | Critère d'acceptation |
|---|---|---|---|
| DOC-1 | Confirmer les noms et formats exacts attendus : Progest / Proges / Organata | P0 | aucune correction technique ne part sur un mauvais nom ou format |
| DOC-2 | Ajouter une zone visible "Documents externes" dans le parcours dossier | P1 | le client sait où déposer ou retrouver le fichier |
| DOC-3 | Afficher le statut de traitement du document : importé, à vérifier, validé, rejeté | P1 | l'utilisateur sait si le document est exploitable |
| DOC-4 | Lier chaque document au bon dossier / opportunité / vente | P0 | aucun document ne flotte hors contexte métier |

## Séquence recommandée avant lundi

### Bloc 1 — cadrage très court

- Relire la note client du 2026-07-30.
- Confirmer les noms exacts "Progest / Organata" si possible.
- Choisir 3 à 5 corrections maximum dans les P0.

### Bloc 2 — inventaire

- Parcourir manuellement `/stock` comme un opérateur.
- Compter le nombre de gestes nécessaires pour créer ou traiter une ligne
  d'inventaire.
- Corriger d'abord le guidage et le bouton d'action suivante.
- Vérifier avec le test existant :

```bash
cd "2 - PROJETS/mmg/mmg/frontend_v2"
npm run test:e2e:real -- e2e-real/inventory-complete.spec.js
```

### Bloc 3 — CRM avant-vente

- Parcourir le scénario "client → opportunité → dossier".
- Supprimer ou masquer ce qui détourne de ce chemin pendant la démo.
- Vérifier avec :

```bash
cd "2 - PROJETS/mmg/mmg/frontend_v2"
npm run test:e2e -- e2e/crm-presales.spec.js
```

### Bloc 4 — validation finale

- Rejouer une affaire représentative avec la checklist go/no-go :
  `docs/RECETTE_CLIENT_GO_NO_GO.md`.
- Préparer une synthèse client en 4 lignes :
  - ce qui a été remonté ;
  - ce qui a été corrigé ;
  - ce qui reste volontairement hors périmètre ;
  - ce qu'on veut décider lundi.

## Definition of done avant le point client

- [ ] Les P0 choisis sont corrigés ou explicitement reportés.
- [ ] Le parcours inventaire a une action suivante évidente.
- [ ] Le parcours CRM avant-vente mène clairement vers un dossier exploitable.
- [ ] Les documents externes ont un emplacement et un statut compréhensibles.
- [ ] Les tests inventaire et CRM ciblés passent ou les écarts sont notés.
- [ ] La checklist go/no-go est prête pour le point du lundi 2026-08-03.

## Message de préparation client possible

> Suite à notre test en conditions réelles, j'ai repris les points de friction
> sur l'inventaire, le parcours utilisateur et le CRM avant-vente. L'objectif
> du point de lundi est de vérifier ensemble si les corrections rendent le
> parcours assez fluide pour lancer un pilote conditionnel, ou s'il reste un
> blocage métier à traiter avant.

## Non-objectifs

- Ne pas ouvrir POS, comptabilité, logistique avancée ou achats fournisseurs
  sauf si le client les rend explicitement bloquants pour le pilote.
- Ne pas refondre toute l'interface avant lundi.
- Ne pas promettre une automatisation complète des documents externes tant que
  les formats exacts ne sont pas confirmés.
