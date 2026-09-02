# Procès-verbal de recette interne

## Workflow industriel PVC + ALU

Date de recette : 02/09/2026  
Environnement : production `app.mmg-metal.fr`  
Statut final : validé sans réserve

## Objet

Ce procès-verbal fige la validation fonctionnelle du workflow industriel, depuis le dossier métier issu du métré jusqu'au contrôle matière, la réservation/préparation atelier, l'autorisation de lancement et le débit réel.

Le périmètre couvre les flux :

- PVC avec documents PROGES ;
- ALU avec documents ORGADATA / LogiKal.

## Preuves de recette constatées

### Flux ALU ORGADATA

Dossier de recette : `MET-2026-00006`  
Référence industrielle : `ALU-RECETTE-2026-002`  
Devis lié : `DEV-2026-0004`  
Environnement validé : production, déploiement incluant le commit `a16f446`

Documents techniques validés :

- `FABRICATION V4` - ORGADATA - `03-bon-atelier-orgadata-alu-recette-002.pdf`
  - statut : données extraites ;
  - ouvrages extraits : 2/2 ;
  - vitrages extraits : 2 ;
  - accessoires extraits : 2 ;
  - contrôle croisé métré / chiffrage / débit : aucun écart automatique.
- `CUTTING V6` - ORGADATA - `04-debit-optimise-orgadata-alu-recette-002-v2.pdf`
  - statut : données extraites ;
  - lignes matière : 3 ;
  - quantité totale : 8 ;
  - références matière : 3 ;
  - alertes : 0.

Contrôles métier validés :

- contrôle BE : validé par `admin` ;
- validation stock : validée par `admin` ;
- autorisation atelier : validée par `admin` ;
- inconnues matière : 0 ;
- manques matière : 0 ;
- réservation atelier : consommée ;
- préparation magasin : consommée ;
- débit matière réel : enregistré.

### Flux PVC PROGES

Le flux PVC PROGES a été validé précédemment sur le même enchaînement métier :

1. import des documents PROGES ;
2. extraction des lignes de débit ;
3. création/rapprochement des références inventaire ;
4. contrôle matière ;
5. validation BE ;
6. validation stock ;
7. réservation atelier ;
8. préparation magasin ;
9. autorisation atelier ;
10. débit réel.

Statut constaté : opérationnel et certifié production sur recette.

## Correctifs inclus dans la recette

Les correctifs suivants ont été intégrés, mergés et déployés avant validation finale :

- parsing des fiches fabrication ORGADATA / LogiKal ;
- prévisualisation lisible des ouvrages, dimensions, systèmes, finitions, vitrages, accessoires et remarques atelier ;
- contrôle croisé automatique entre métré, chiffrage, fiche fabrication et débit ;
- contrôle de cohérence documentaire basé sur les dernières versions actives par type ;
- réapprobation atelier post-révision autorisée uniquement si la matière déjà consommée correspond au dernier débit validé ;
- maintien du verrou empêchant une nouvelle réservation complète après consommation réelle non régularisée.

## Résultat de recette

Le workflow industriel est validé comme complet production sans réserve pour les périmètres PVC PROGES et ALU ORGADATA.

La chaîne métier validée est :

1. prise de commande / devis signé ;
2. dossier métier et métré ;
3. import chiffrage ;
4. validation BE du chiffrage ;
5. import fiche fabrication ;
6. import débit matière ;
7. prévisualisation et contrôle croisé ;
8. validation BE fabrication et débit ;
9. contrôle matière ;
10. validation stock ;
11. réservation atelier ;
12. préparation magasin ;
13. autorisation atelier ;
14. lancement fabrication ;
15. débit matière réel.

## Réserves

Aucune réserve bloquante restante sur le workflow industriel PVC + ALU.

Point de vigilance hors réserve : les anciennes versions historiques restent visibles dans le dossier pour audit, mais les contrôles métier s'appuient sur les dernières versions actives validées.

