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
- `EXTERNAL_DOCUMENT_MAPPINGS` : mapping PROGES/ORGADATA ;
- `WORKFLOW_GATES` : règles de passage critiques ;
- `resolve_external_document()` : résolution d'un document externe ;
- `validate_ontology()` : contrôle structurel utilisé par les tests.

