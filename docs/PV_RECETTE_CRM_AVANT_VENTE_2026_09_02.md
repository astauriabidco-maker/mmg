# PV interne de recette - CRM avant-vente

Date de recette : 2 septembre 2026  
Environnement : production `https://app.mmg-metal.fr`  
Périmètre : CRM avant-vente, depuis création client jusqu'au devis et à la relance.

## Résultat synthétique

Statut : validé avec une réserve mineure UI observée en production sur le préremplissage du destinataire de relance. Un correctif backend est préparé et testé pour lever cette réserve après merge/déploiement.

Le workflow principal est opérationnel :

1. création client ;
2. création opportunité ;
3. qualification commerciale ;
4. création mission de métré / dossier de cotes ;
5. saisie ouvrage ;
6. ajout document source anonymisé ;
7. envoi au contrôle BE ;
8. validation BE du métré ;
9. validation client ;
10. import chiffrage PROGES fictif ;
11. contrôle BE du chiffrage ;
12. génération du devis depuis chiffrage ;
13. prévisualisation de relance email.

## Données de recette

- Client fictif : `RECETTE CRM 20260902-1758`
- Contact fictif : `Contact Recette`
- Email fictif : `recette-crm-20260902-1758@example.test`
- Opportunité : `OPP-2026-00006`
- Mission : `MET-2026-00007`
- Dossier technique : `DT-2026-00005`
- Devis généré : `DEV-2026-0005`
- Montant HT devis : `12 345,00 €`

Aucune donnée client réelle, bancaire ou commerciale réelle n'a été utilisée pour cette recette.

## Preuves fonctionnelles constatées

### Client et opportunité

- Création client fictif effectuée depuis l'interface CRM.
- Création opportunité effectuée depuis la fiche client.
- Qualification effectuée depuis le pipeline avant-vente.
- Passage vers une mission de métré / dossier de cotes confirmé.

### Métré / dossier de cotes

- Mission créée : `MET-2026-00007`.
- Ouvrage saisi : `F01 - fenêtre recette CRM`.
- Dimensions saisies : `1200 × 1400 mm`, passage utile `1300 mm`.
- Ouvrage terminé : `1/1 ouvrage(s) terminé(s)`.
- Document source fictif attaché : `mmg-recette-crm-source-20260902.txt`.
- Passage `Brouillon` vers `Saisie des cotes` validé après déploiement du correctif UI.
- Envoi au contrôle BE validé.
- Validation BE du métré validée.
- Mission affichée `Validée BE`.
- Vérification métier affichée `Bon pour fabrication`.

### Chiffrage et devis

- Import chiffrage PROGES fictif V3 validé.
- Prévisualisation affichée :
  - source : `PROGES`
  - référence : `CRM-RECETTE-20260902`
  - lignes : `1`
  - ouvrages : `1`
  - HT brut : `12 345,00 €`
  - remise : `0,00 €`
  - HT net : `12 345,00 €`
  - statut extraction : `Données extraites`
- Soumission du chiffrage au contrôle BE validée.
- Validation BE du chiffrage validée.
- Génération du devis depuis chiffrage validée.
- Devis affiché : `DEV-2026-0005`, statut `Brouillon`, total HT `12 345,00 €`.
- Ligne devis générée : `LIGNE-001 - Fenêtre ALU fictive recette CRM`.
- Lien métier confirmé entre devis, mission `MET-2026-00007` et chiffrage PROGES V3.

### Relance

- Le cockpit CRM affiche le dossier `RECETTE CRM 20260902-1758` dans les priorités sans prochaine action.
- La prévisualisation de relance email s'ouvre depuis le cockpit.
- Modèle de relance sélectionné : `Reprise de contact`.
- Objet généré : `Suivi de votre projet OPP-2026-00006`.
- Message généré automatiquement avec le contexte de l'opportunité.
- Envoi volontairement non déclenché pendant la recette.
- Le bouton `Envoyer la relance` reste désactivé tant que la confirmation humaine n'est pas cochée.

## RBAC

- Le verrouillage backend des mutations CRM avant-vente a été livré via la PR `#19 - Enforce CRM edit permissions on presales mutations`.
- La recette navigateur a été effectuée avec une session habilitée, ce qui valide l'accès opérationnel pour un profil autorisé.
- La recette UI de refus pour profil non habilité n'a pas été rejouée en production faute de session dédiée sans permission `SALES_EDIT`.

## Correctif UI validé pendant la recette

La recette a révélé qu'une mission de type dossier de cotes créée depuis la qualification CRM restait en statut `Brouillon` sans action visible pour entrer dans le contrôle BE.

Correctif livré :

- PR : `#21 - Allow CRM draft measure missions to enter review flow`
- Commit : `10c541a`
- Effet constaté après déploiement : bouton `Démarrer le contrôle des cotes` visible sur `MET-2026-00007`.
- Build local validé avant PR : `npm run build`.

## Réserve mineure

La prévisualisation de relance email s'ouvre correctement et génère l'objet/message, mais le champ `Destinataire` apparaît vide depuis l'action cockpit testée.

Impact :

- Pas de relance envoyée sans confirmation humaine.
- L'envoi reste protégé par case de confirmation.
- Le commercial peut compléter le destinataire manuellement.

Recommandation :

- Préremplir automatiquement le destinataire avec l'email client ou le contact principal de la fiche CRM.
- Ajouter un test navigateur couvrant ce préremplissage.

Correctif préparé :

- L'API de prévisualisation de relance utilise désormais `client.email`, puis l'email du contact principal, puis le premier contact email disponible.
- Test ajouté : prévisualisation avec client sans email direct mais contact principal email.
- Validation locale : `tests/test_crm_reminders.py` : 11 tests passés.

## Décision

Le module CRM avant-vente est déclaré opérationnel pour le flux métier principal en production, avec réserve mineure sur le confort/sécurité de préremplissage du destinataire de relance.

La certification "sans réserve" sera possible après merge, déploiement et recette du correctif de préremplissage automatique du destinataire de relance.
