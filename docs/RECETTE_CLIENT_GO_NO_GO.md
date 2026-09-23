# MMG — recette client et décision go/no-go

> Préparée le 2026-07-30. Durée cible : 60 à 90 minutes.
> Objectif : valider le cœur métier avec un cas réel, pas présenter tout l'ERP.

## Résultat attendu

À la fin de la session, prendre une décision explicite :

- **GO pilote** : une première affaire réelle peut être traitée dans MMG ;
- **GO conditionnel** : le pilote démarre après quelques corrections ciblées ;
- **NO-GO** : le workflow métier exige une modification structurante.

La session est réussie si elle produit une décision, même si cette décision
est un no-go.

## Périmètre

### Inclus

Le parcours principal de fabrication sur mesure :

1. client et opportunité ;
2. mission de métrage sur chantier ;
3. ouvertures, dimensions, photos et contrôle ;
4. dossier technique et chiffrage Proges/Progers ;
5. devis validé par le client ;
6. documents de fabrication et débit ;
7. validation bureau d'études et stock ;
8. réservation matière ;
9. autorisation et lancement en atelier.

### Hors périmètre du premier go/no-go

- POS et vente comptoir ;
- WhatsApp, IA et automatisations optionnelles ;
- comptabilité ou promesse de conformité fiscale complète ;
- logistique avancée et application chauffeur ;
- achats fournisseurs complets ;
- optimisation générale de l'interface.

Un module hors périmètre ne devient bloquant que si le client confirme qu'il
est indispensable dès la première affaire pilote.

## Préparation avant la session

- [ ] Utiliser un environnement de recette, pas la production.
- [ ] Préparer un compte pour chaque rôle réellement présent.
- [ ] Choisir **une affaire représentative**, suffisamment simple pour tenir
      dans la session.
- [ ] Préparer des données anonymisées ou autorisées :
  - client et adresse de chantier ;
  - deux ouvertures représentatives ;
  - photos ou justificatifs ;
  - fichier de chiffrage Proges/Progers ;
  - fichier de fabrication ;
  - fichier de débit TXT ou PDF supporté ;
  - références et quantités de stock correspondantes.
- [ ] Vérifier que les comptes de démonstration et PIN triviaux ne sont pas
      utilisés comme comptes réels.
- [ ] Conserver un moyen de repartir d'un jeu de données propre.
- [ ] Noter qui décide du go/no-go côté client.

## 1. Comprendre le workflow réel — 10 minutes

Avant d'ouvrir MMG, demander au client de raconter la dernière affaire réelle :

1. Qui crée le dossier et à quel moment ?
2. Qui prend et valide les mesures ?
3. Qui chiffre dans Proges/Progers ?
4. À quel moment le client valide-t-il le devis ?
5. Qui prépare les débits et contrôle la disponibilité matière ?
6. Qui autorise le lancement en atelier ?
7. À quel moment le stock est-il réellement consommé ?

Noter uniquement les écarts entre ce récit et le parcours MMG.

## 2. Exécuter une affaire représentative

Pour chaque étape, noter `OK`, `FRICTION`, `BLOQUANT` ou `HORS PÉRIMÈTRE`.

| Étape | Résultat observable | Verdict | Note |
|---|---|---|---|
| Créer/retrouver le client et l'opportunité | Le dossier commercial est identifiable sans doublon |  |  |
| Planifier la mission | Le chantier, le responsable et l'horaire sont clairs |  |  |
| Saisir deux ouvertures | Dimensions, matière et type d'ouverture sont complets |  |  |
| Ajouter les preuves | Photos/documents sont visibles et liés à la bonne ouverture |  |  |
| Envoyer au contrôle | Une ouverture incomplète ne peut pas être validée |  |  |
| Importer le chiffrage | Les lignes Proges/Progers sont lisibles et contrôlables |  |  |
| Valider le dossier technique | Le devis est généré une seule fois avec les bons montants |  |  |
| Valider le devis client | La fabrication reste verrouillée avant validation |  |  |
| Importer fabrication et débit | Les fichiers sont liés à la bonne affaire |  |  |
| Valider BE et stock | Les références inconnues ou quantités manquantes sont visibles |  |  |
| Créer la réservation | Le stock est réservé sans être consommé prématurément |  |  |
| Autoriser l'atelier | Seul le rôle prévu peut donner le feu vert |  |  |
| Lancer la fabrication | L'affaire passe à `IN_PRODUCTION` |  |  |
| Préparer/remettre/consommer | La consommation réelle correspond à la remise atelier |  |  |

## 3. Questions métier à trancher

- Le vocabulaire de MMG correspond-il aux mots employés dans l'atelier ?
- Les rôles réels correspondent-ils aux validations demandées ?
- Une ouverture peut-elle être modifiée après validation ? Par qui ?
- Le devis signé est-il le bon événement pour déverrouiller la fabrication ?
- La réservation doit-elle se faire avant ou après le contrôle bureau d'études ?
- Le stock doit-il être consommé au débit, à la remise atelier ou à une autre étape ?
- Quel document papier ou Excel continuerait d'être utilisé malgré MMG ?
- Quelle étape ferait refuser l'outil aux opérateurs dès la première semaine ?

## 4. Critères de décision

### GO pilote

Tous les critères suivants sont vrais :

- le client reconnaît son workflow sans réarchitecture majeure ;
- l'affaire représentative atteint `IN_PRODUCTION` ;
- aucune donnée n'est perdue ou rattachée au mauvais dossier ;
- devis non validé, stock insuffisant et rôle non autorisé sont bien bloqués ;
- les écarts restants ont un contournement acceptable pour le pilote ;
- le client choisit une première affaire réelle et une date de démarrage.

### GO conditionnel

- aucun problème d'intégrité, sécurité ou stock ;
- au maximum quelques corrections ciblées clairement attribuées ;
- une date de revalidation est fixée avant l'affaire pilote.

### NO-GO

Un seul de ces constats suffit :

- le workflow réel exige une étape structurante absente ;
- un devis non validé peut déclencher la fabrication ;
- la réservation ou la consommation de stock est incorrecte ;
- l'affaire ne peut pas atteindre `IN_PRODUCTION` ;
- les rôles indispensables ne peuvent pas exécuter leur travail ;
- les données nécessaires ne peuvent pas être saisies ou importées ;
- aucune affaire pilote ni date ne peut être choisie.

## 5. Décision de fin de session

```yaml
date:
participants:
affaire_testee:
decision: GO | GO_CONDITIONNEL | NO_GO
premiere_affaire_pilote:
date_pilote:
blocages:
corrections_avant_pilote:
modules_explicitement_hors_perimetre:
responsable_validation_client:
```

## État technique vérifié le 2026-07-30

- 36 tests backend ciblés passent :
  - métrage et dossiers MMG ;
  - dossier technique ;
  - réservation stock ;
  - lancement atelier.
- 3 tests Playwright du parcours commercial/BE/stock passent.
- 2 recettes Playwright avec backend et base réels passent :
  - dossier signé jusqu'à `IN_PRODUCTION` et consommation du débit ;
  - inventaire complet.

### Risques à fermer avant la session client

- Le dépôt contient des modifications locales non commitées sur le
  déverrouillage de la fabrication et le parcours inventaire. Elles sont
  préservées. Le diff courant doit être relu et intégré proprement avant la
  recette client.
- La préparation, la remise atelier et la consommation sont validées avec un
  backend réel, mais les gestes magasin du scénario automatisé passent encore
  par l'API. Leur exécution complète dans l'interface doit être vérifiée
  manuellement avant de promettre ce parcours au client.
