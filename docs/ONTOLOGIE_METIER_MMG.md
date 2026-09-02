# Ontologie métier MMG

Ce document fixe le vocabulaire canonique entre CRM, bureau d'études, devis,
commande, fabrication, stock et débit atelier. La version exploitable par le
code est dans `backend/domain/ontology.py`.

## Chaîne métier cible

```text
Client
 └── Opportunité CRM
      ├── Mission de métré
      │    └── Dossier technique BE
      │         ├── Chiffrage technique PROGES/ORGADATA
      │         ├── Fiche fabrication
      │         └── Fiche de débit
      └── Devis commercial MMG
           └── Commande signée
                └── Dossier industriel
                     ├── Ordre de fabrication
                     ├── Réservation stock atelier
                     ├── Bon de préparation atelier
                     └── Débit atelier réel
```

## Définitions canoniques

| Objet MMG | Module | Définition |
| --- | --- | --- |
| Client | CRM | Personne morale ou physique à l'origine d'un projet MMG. |
| Contact client | CRM | Interlocuteur opérationnel ou décisionnaire rattaché au client. |
| Opportunité avant-vente | CRM | Projet commercial suivi avant signature, de la qualification au gagné/perdu. |
| Mission de métré | BE | Collecte et vérification des cotes, photos et contraintes chantier. |
| Dossier technique BE | BE | Dossier gouverné par le BE qui regroupe chiffrage, fabrication et débit. |
| Chiffrage technique | BE | Résultat technique issu de PROGES, ORGADATA ou saisie interne. |
| Devis commercial MMG | Devis | Proposition commerciale envoyable au client. |
| Commande signée | Commande | Devis accepté ou signé qui autorise l'industrialisation. |
| Dossier industriel | Fabrication | Vue production d'une commande signée. |
| Fiche fabrication | Fabrication | Instructions atelier pour fabriquer les ouvrages. |
| Fiche de débit | Débit | Liste matière à réserver puis couper ou consommer. |
| Référence matière stock | Stock | Article ou variante stockable identifié par référence, unité et emplacement. |
| Réservation stock atelier | Stock | Blocage logique des matières nécessaires à une fiche de débit. |
| Bon de préparation atelier | Stock | Mise à disposition physique en zone atelier d'une réservation active. |
| Ordre de fabrication | Fabrication | Ordre atelier lancé après validation commande, BE et stock. |
| Débit atelier réel | Débit | Consommation effective du stock après lancement fabrication. |

## Correspondances PROGES / ORGADATA

| Source | Type document | Objet MMG | À ne pas confondre avec |
| --- | --- | --- | --- |
| PROGES | `QUOTING` | Chiffrage technique | Devis commercial, commande signée, fiche de débit |
| PROGES | `CUTTING` | Fiche de débit | Chiffrage technique, fiche fabrication, débit réel |
| ORGADATA | `QUOTING` | Chiffrage technique | Devis commercial, commande signée, fiche de débit |
| ORGADATA | `FABRICATION` | Fiche fabrication | Fiche de débit, débit réel |
| ORGADATA | `CUTTING` | Fiche de débit | Fiche fabrication, chiffrage technique, débit réel |

## Garde-fous métier

- Un devis commercial doit rester traçable vers l'opportunité CRM quand il
  provient de l'avant-vente.
- Une fabrication ne doit pas être lancée sans commande signée ou validée.
- Une réservation stock atelier doit être basée sur une fiche de débit
  `CUTTING`, pas sur une fiche fabrication.
- Un débit atelier réel doit être lié à une réservation active, une préparation
  remise à l'atelier et une fabrication lancée.
- Une fiche fabrication explique comment produire ; elle ne consomme pas le
  stock.
- Une fiche de débit définit quoi réserver/débiter ; elle ne remplace pas le
  devis commercial client.

## Source machine-readable

Le module `backend/domain/ontology.py` expose :

- `ENTITIES` : objets métiers canoniques ;
- `RELATIONS` : liens officiels entre objets ;
- `MODEL_BINDINGS` : correspondances avec les modèles SQLAlchemy ;
- `ENTITY_STATUSES` : statuts métier par entité ;
- `EXTERNAL_DOCUMENT_MAPPINGS` : mapping PROGES/ORGADATA ;
- `BUSINESS_EVENTS` : événements métier clés ;
- `STEP_RBAC` : permissions requises par étape/action ;
- `WORKFLOW_GATES` : règles de passage critiques ;
- `resolve_external_document()` : résolution d'un document externe ;
- `validate_ontology()` : contrôle structurel utilisé par les tests.

## API

L'ontologie est exposée en lecture via :

```http
GET /v2/mmg/ontology
```

La réponse est pensée pour les écrans UI, les parseurs, les tests de recette et
les futurs usages IA/RAG.

## Utilisation par les parseurs

Les imports techniques utilisent l'ontologie pour rattacher chaque document à
un objet canonique :

- `PROGES/CUTTING` et `ORGADATA/CUTTING` alimentent `cutting_sheet` et peuvent
  servir au contrôle stock.
- `ORGADATA/FABRICATION` alimente `fabrication_sheet` et ne peut pas être
  utilisé comme source de réservation ou débit réel.
- `PROGES/QUOTING`, `ORGADATA/QUOTING` et les valorisations alimentent
  `technical_quotation`, pas le devis commercial MMG.

Les résumés d'analyse exposent `canonical_entity`, `stock_source` et
`forbidden_confusions` pour que l'UI et les contrôles BE puissent afficher le
rôle métier exact du fichier importé.

## Statuts métier suivis

| Entité | Statuts principaux |
| --- | --- |
| Opportunité avant-vente | nouvelle, qualifiée, métré à planifier, métré en cours, proposition à préparer, proposition à valider, proposition envoyée, négociation, gagnée, perdue |
| Mission de métré | brouillon, planifiée, en cours, en contrôle BE, validée BE, annulée |
| Dossier technique BE | brouillon, en contrôle BE, validé BE, à corriger |
| Devis commercial MMG | brouillon, envoyé, signé, annulé |
| Commande signée | signée, prête pour production, en production, terminée |
| Réservation stock atelier | brouillon, active, consommée, annulée |
| Ordre de fabrication | planifié, lancé, terminé |
| Débit atelier réel | à débiter, débité |

## Événements métier clés

- Opportunité créée.
- Métré soumis au BE.
- Dossier technique validé BE.
- Devis envoyé.
- Devis signé.
- Stock réservé.
- Bon atelier préparé.
- Fabrication lancée.
- Débit consommé.

## RBAC par étape

| Zone | Permission de référence |
| --- | --- |
| CRM lecture | `SALES_VIEW` |
| CRM écriture, devis, conversion commande | `SALES_EDIT` |
| Validation BE et lancement fabrication | `PRODUCTION_MANAGE` |
| Réservation, préparation atelier et débit réel | `STOCK_MANAGE` |
