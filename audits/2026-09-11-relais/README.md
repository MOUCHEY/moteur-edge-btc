# Relais Astra → Claude : qualifier le moteur avant la prochaine candidate

**Verdict : le socle contient des éléments utiles, mais les passages de validation ne sont pas encore fiables.** Cette livraison apporte un audit et des contre-exemples reproductibles. Les correctifs du moteur restent à réaliser et à revoir avant d'utiliser ses résultats pour promouvoir une candidate.

Audit commencé le 11 septembre, finalisé le 13 septembre 2026. Référence examinée : [`7454850c1328d41bf626766825833a480a5f4139`](https://github.com/MOUCHEY/moteur-edge-btc/commit/7454850c1328d41bf626766825833a480a5f4139). Les rapports décrivent cette version ; leurs numéros de ligne ne désignent pas une version corrigée.

## Ce qui doit bloquer la suite

1. **Causalité et simulation.** Un signal utilisant des rendements futurs est accepté et obtient 196 trades positifs sur 196 sur une fixture. Le détecteur laisse également passer une fuite d'une barre. Les sorties sur timeout/gap et le drawdown initial présentent des erreurs distinctes. Cela qualifie des défauts de l'outil, aucune stratégie rentable.
2. **Séparation découverte/validation.** OOS et VAULT utilisent le même balayage de paramètres que IS ; le programme peut donc choisir sur l'échantillon censé valider. Les portes et le gel ne sont pas imposés avant lecture. Une barre à la frontière peut appartenir à deux découpages.
3. **Traçabilité.** Le registre peut être contourné, une tentative échouée rester absente et des résultats antérieurs être écrasés. Le DSR reçoit le compteur avant ajout des essais du run. Une métrique est aussi injectée dans les paramètres sélectionnés.
4. **Coffre.** La lecture du code établit que l'autorisation persistante n'impose pas une ouverture unique. Le futur collecté n'est pas relié à une candidate gelée ; l'isolement effectif des agents n'est pas démontré. Ces constats ne reposent sur aucune ouverture du coffre.
5. **Statistique.** Un bootstrap de blocs, même centré, n'est pas automatiquement un monde sans prévisibilité. EXP-0000 reste une sensibilité descriptive. Le seuil G4 n'est pas qualifié ; 136 n'est pas un nombre vérifié d'essais uniques ou indépendants. Bonferroni n'exige pas l'indépendance lorsque les p-valeurs élémentaires sont valides.

## Dossier de preuves

| Document | Contenu |
|---|---|
| [MOTEUR.md](MOTEUR.md) | Huit contre-exemples du simulateur et constats supplémentaires de lecture |
| [CONTROLES.md](CONTROLES.md) | Neuf contre-exemples du chargement, de la sélection, du registre et du bootstrap |
| [COFFRE-ET-CI.md](COFFRE-ET-CI.md) | Accès, unicité, gel, collecte, scellement et CI : revue statique |
| [STATISTIQUE.md](STATISTIQUE.md) | Portée d'EXP-0000, essais multiples, historique et références primaires |
| [engine-results.json](engine-results.json) et [controls-results.json](controls-results.json) | Sorties enregistrées, versions, dates et empreintes |
| [JOURNAL.md](JOURNAL.md) | Périmètre, incident de sonde et limites de cette contribution |

Les constats des rapports se recoupent ; leurs nombres ne doivent pas être additionnés comme autant de bugs distincts. Les 17 cas exécutés sont des tests de qualification de l'outil sur données fictives, pas 17 stratégies testées sur le marché.

## Reproduire sans consulter les données réservées

Depuis la racine du dépôt, avec les dépendances Python du projet :

```sh
python3 audits/2026-09-11-relais/reproduce_engine.py
python3 audits/2026-09-11-relais/reproduce_controls.py
```

Ces deux scripts fabriquent leurs observations en mémoire ou dans un répertoire temporaire. Ils n'ouvrent ni données de marché, ni clés, ni contenu chiffré. Le second remplace explicitement les chemins et certaines fonctions pour tester le contrôle du programme. Les détails et limites figurent dans chaque rapport.

**Un code de sortie 0 signifie « défauts reproduits », pas « moteur validé ».** Les versions et empreintes dans les JSON permettent de comparer la référence. La suite historique annoncée à 26 tests réussis n'a pas été relancée : plusieurs de ses tests lisent les séries réelles, dont OOS. Aucun résultat de backtest de marché n'est confirmé par cet audit.

## Travail proposé pour le prochain relais

Claude peut contester chaque constat en citant la version et une preuve reproductible. Une réfutation solide est un résultat utile. Pour les constats confirmés, les correctifs attendus concernent l'infrastructure de recherche ; ils ne doivent pas modifier une stratégie pour sauver sa performance.

| Ordre | Livrable attendu | Critère de revue |
|---|---|---|
| 1 | Causalité complète et conventions d'exécution corrigées | Les fuites sont refusées, les résultats attendus sont vérifiés sur fixtures ; cas de timeout, gaps, durées et capital initial couverts |
| 2 | Contrat figé, portes et journal d'événements | Refus avant toute lecture non autorisée, candidate unique, sorties conservées, échecs tracés et paramètres séparés des métriques |
| 3 | Protocole statistique et historique réconciliés | EXP-0000 conservée avec sa portée limitée ; neuf configurations réelles tracées ; historique incertain séparé du compte exact ; modèle nul et précision préenregistrés |
| 4 | Coffre futur et contrôles CI effectifs | Gel identifiable, période admissible, gardien isolé, ouverture atomique unique et tests avec coffres fictifs ; contrôles actifs qui refusent une preuve manquante |

Chaque correction doit être publiée avec sa validation ciblée pour la revue suivante. Les versions antérieures et les expériences ratées restent conservées. Le chiffrement historique ne rend pas vierges des observations déjà consultées. Les coûts réels et l'écart entre Binance spot et l'instrument d'exécution demeurent également à établir avant de conclure à un avantage déployable (sujet déjà suivi dans l'issue #3).

Après qualification de ces mécanismes, Astra pourra proposer la prochaine hypothèse G0, avec mécanisme, prédictions et budget préenregistrés. La falsification devra pouvoir conclure qu'aucune candidate n'a survécu. Aucune ouverture finale ni négociation réelle n'est demandée par ce relais.
