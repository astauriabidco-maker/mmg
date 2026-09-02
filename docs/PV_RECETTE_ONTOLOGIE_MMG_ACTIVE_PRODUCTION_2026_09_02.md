# PV de recette interne — Ontologie MMG active production

Date de recette : 02/09/2026  
Environnement : production `https://app.mmg-metal.fr`  
Déploiement contrôlé : `c4ca818`  
Objet : validation de l'ontologie métier MMG active dans l'interface opérateur.

## Périmètre validé

L'ontologie MMG relie les étapes métier suivantes :

CRM → BE → devis → commande → fabrication → stock → débit.

Elle sert de référentiel visible pour lever les ambiguïtés entre :

- métré ;
- chiffrage PROGES / ORGADATA ;
- devis commercial MMG ;
- fiche fabrication ;
- fiche de débit ;
- réservation stock atelier ;
- préparation atelier ;
- ordre de fabrication ;
- débit atelier réel.

## Résultat global

Statut : validé production.

L'ontologie est désormais :

- documentée ;
- exposée via l'API `/v2/mmg/ontology` ;
- utilisée par les parseurs PROGES / ORGADATA pour classifier les documents ;
- visible dans l'interface CRM / BE / Stock / Atelier ;
- reliée aux statuts métier, événements métier et permissions RBAC par étape.

## Contrôles navigateur effectués

### 1. CRM cockpit

URL contrôlée :

`/manager?view=crm&deploy=c4ca818`

Statut : OK.

Constats :

- le bloc `ONTOLOGIE ACTIVE` est visible ;
- le repère `Flux avant-vente certifié` est affiché ;
- les entités métier visibles incluent :
  - opportunité avant-vente ;
  - mission de métré ;
  - dossier technique BE ;
  - devis commercial MMG ;
- les permissions visibles incluent `SALES_VIEW` et `SALES_EDIT` ;
- les événements métier visibles incluent :
  - opportunité créée ;
  - métré soumis au BE ;
  - devis envoyé ;
  - devis signé.

### 2. Métré / BE

URL contrôlée :

`/measure-missions/6?deploy=c4ca818`

Statut : OK.

Constats :

- le bloc `ONTOLOGIE ACTIVE` est visible sur le dossier `MET-2026-00006` ;
- le repère `BE → devis` est affiché ;
- le chiffrage technique est clairement présenté comme base de préparation du devis commercial ;
- il ne vaut ni commande client, ni consommation matière.

### 3. Fabrication & débit

URL contrôlée :

`/measure-missions/6?deploy=c4ca818`

Statut : OK.

Constats :

- le repère `Fabrication → stock → débit` est visible ;
- la différence métier est explicitée :
  - la fiche fabrication décrit comment produire les ouvrages ;
  - la fiche de débit indique quoi réserver puis consommer ;
- les entités visibles incluent :
  - fiche fabrication ;
  - fiche de débit ;
  - réservation stock atelier ;
  - ordre de fabrication ;
  - débit atelier réel ;
- les permissions visibles incluent `PRODUCTION_MANAGE` et `STOCK_MANAGE` ;
- l'ordre métier verrouillé est affiché :
  1. réserver stock ;
  2. préparer / remettre le bon atelier ;
  3. lancer fabrication ;
  4. consommer le débit réel.

### 4. Classification PROGES / ORGADATA

URL contrôlée :

`/measure-missions/6?deploy=c4ca818`

Statut : OK.

Constats :

- dans le formulaire d'import de révision, les classifications ORGADATA sont visibles ;
- `ORGADATA/FABRICATION` est reconnu comme fiche fabrication ALU ;
- `ORGADATA/CUTTING` est reconnu comme liste de débit ALU ;
- les confusions dangereuses sont prévenues par l'aide métier affichée.

### 5. Stock / Atelier

URL contrôlée :

`/stock?deploy=c4ca818`

Statut : OK.

Constats :

- le bloc `ONTOLOGIE ACTIVE` est visible ;
- le repère `Garde-fou stock / atelier` est affiché ;
- la règle visible confirme que le stock réel est consommé uniquement après :
  - réservation ;
  - préparation atelier ;
  - lancement fabrication ;
- les entités visibles incluent :
  - référence matière stock ;
  - réservation stock atelier ;
  - bon de préparation atelier ;
  - ordre de fabrication ;
  - débit atelier réel ;
- la permission `STOCK_MANAGE` est affichée.

## Décision

La recette navigateur confirme que l'ontologie MMG est active, visible et exploitable en production.

Décision : ontologie MMG active production validée.

## Réserves

Aucune réserve bloquante constatée sur le périmètre de recette.

Les avertissements techniques restants sont hors périmètre fonctionnel de cette recette :

- cache navigateur ou service worker à vider si une ancienne URL de déploiement est conservée ;
- environnement de test Python local à reconstruire si l'on souhaite relancer les tests backend depuis ce poste.

