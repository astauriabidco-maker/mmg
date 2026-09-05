# Procès-verbal de recette interne

## Workflow Supply Chain / Stock / Achats fournisseurs

Date de recette : 05/09/2026  
Environnement : production `app.mmg-metal.fr`  
Statut final : validé production sur flux principal

## Objet

Ce procès-verbal fige la validation fonctionnelle du workflow Supply Chain MMG,
depuis l'identification d'un besoin stock jusqu'au paiement fournisseur, en
passant par le réapprovisionnement, la commande, la réception, le rangement
physique et le rapprochement facture.

Le périmètre validé couvre :

- gestion stock et emplacements atelier ;
- réception stock guidée ;
- transfert stock guidé ;
- réapprovisionnement et demandes d'achat ;
- rapprochement fournisseur ;
- commande fournisseur ;
- réception depuis commande fournisseur ;
- facture fournisseur ;
- litiges quantité / prix ;
- paiement fournisseur.

## Chaîne métier validée

Le flux principal validé en production est :

1. identifier les articles à risque ou en manque ;
2. regrouper les besoins par fournisseur ;
3. créer une demande d'achat ;
4. contrôler puis convertir la demande en commande fournisseur ;
5. réceptionner la commande fournisseur ;
6. ranger la matière dans un emplacement physique exploitable ;
7. rendre le stock disponible ;
8. rapprocher la facture fournisseur avec les quantités réceptionnées ;
9. contrôler les prix facturés par rapport au bon fournisseur ;
10. créer un litige bloquant paiement en cas d'écart ;
11. résoudre le litige si nécessaire ;
12. payer la facture fournisseur.

## Preuves de recette constatées

### Stock et emplacements

Écrans validés :

- `/stock` - accueil gestion stock orienté atelier ;
- `Zones & emplacements` - structure magasin / zone / rack / casier ;
- `Catalogue` - alertes articles sans emplacement clair ;
- `Stock réel` - quantités visibles par emplacement.

Contrôles validés :

- distinction claire entre zone parent, rack, casier final et zone atelier ;
- signalement des noms d'emplacements trop vagues ;
- badge `Exploitable atelier` ;
- filtre des articles sans emplacement clair ;
- alerte fiche article si du stock existe sans emplacement exploitable.

### Flux atelier / débit

Écran validé :

- file guidée `Débit atelier`.

Contrôles validés :

- priorité donnée au débit atelier dans l'accueil stock ;
- affichage des réservations ouvertes ;
- action directe `Traiter ce débit` ;
- rappel du flux réservé : importer, préparer, remettre, consommer.

### Réception et transfert stock

Contrôles validés :

- aucune réception stock sans emplacement final exploitable ;
- transfert interne guidé avec source claire, destination exploitable et
  quantité disponible ;
- mouvement stock tracé avec contexte métier.

### Réapprovisionnement / achats

Écrans validés :

- `Stock à risque` ;
- réapprovisionnement guidé ;
- demandes d'achat ;
- commandes fournisseurs.

Contrôles validés :

- transformation des manques en demandes d'achat claires ;
- regroupement des besoins par fournisseur ;
- correction / rapprochement fournisseur assisté ;
- application possible aux références similaires ;
- conversion assistée demande d'achat vers commande fournisseur ;
- écran de contrôle avant création du bon fournisseur.

### Réception depuis commande fournisseur

Contrôles validés :

- réception possible depuis un bon fournisseur avec reste à recevoir ;
- choix obligatoire d'un emplacement exploitable ;
- refus des destinations de réception trop vagues côté interface et côté API ;
- saisie d'un bon de livraison fournisseur et d'un commentaire ;
- mise à jour des quantités reçues ;
- mouvement stock créé et stock disponible mis à jour.

### Facture fournisseur et paiement

Contrôles validés :

- rapprochement facture uniquement sur quantités réceptionnées non facturées ;
- contrôle quantité facturée vs quantité reçue ;
- saisie du prix facturé par ligne ;
- comparaison prix facturé vs prix du bon fournisseur ;
- blocage de la validation UI si un écart prix n'est pas corrigé ou transformé
  en litige ;
- création d'un litige prix prérempli depuis la ligne en écart ;
- paiement bloqué tant que le litige fournisseur reste ouvert ;
- paiement possible après rapprochement conforme ou résolution du litige.

## Correctifs inclus dans la recette

Les correctifs suivants ont été intégrés, mergés et déployés avant validation
finale :

- refonte UX stock pour séparer pilotage et gestion opérationnelle ;
- accueil stock orienté atelier ;
- file débit atelier guidée ;
- emplacements atelier assistés ;
- qualité des emplacements stock ;
- réception stock guidée ;
- transfert stock guidé ;
- réapprovisionnement / achats guidés ;
- rapprochement fournisseur assisté ;
- demandes d'achat groupées ;
- conversion assistée demande d'achat vers commande fournisseur ;
- réception depuis commande fournisseur ;
- rapprochement facture fournisseur assisté avec contrôle quantité / prix.

## Résultat de recette

Le workflow Supply Chain principal est validé production.

La chaîne validée couvre :

`besoin stock → demande d'achat → commande fournisseur → réception → rangement
physique → stock disponible → facture fournisseur → litige si écart → paiement`.

## Réserves

Aucune réserve bloquante restante sur le flux principal Supply Chain.

Points de vigilance hors réserve :

- la qualité du référentiel fournisseur et article doit continuer à être
  améliorée progressivement ;
- les anciens emplacements ou articles brouillons restent visibles pour audit,
  mais les nouveaux flux guident l'utilisateur vers des données exploitables ;
- une recette terrain avec opérateur MMG reste recommandée pour mesurer la
  vitesse réelle de prise en main en atelier.
