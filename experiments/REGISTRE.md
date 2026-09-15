# Registre des expériences — état courant au 15 septembre 2026

Le journal courant est `events/*.json`. Il conserve les nouvelles tentatives, les contrats, les mesures et leurs issues. Le fichier `ledger.json` reste un snapshot historique immuable, avec ses formulations originales corrigées par [HISTORIQUE.json](HISTORIQUE.json).

**136 n’est ni un total unique vérifié ni un minorant démontré.** Le recouvrement entre les deux déclarations héritées reste inconnu ; le sens d’un biais DSR ne peut pas être conclu de ce seul nombre. Les neuf configurations déclarées pour EXP-0000 sont conservées séparément des 600 chemins simulés déclarés. La grille de neuf a été vérifiée sans lire de marché ; ses performances n’ont pas été reproduites dans ce lot.

Aucune nouvelle expérience de marché n’a été lancée pendant la correction du socle. Les tests synthétiques n’augmentent pas le compteur d’essais BTC. OOS et coffres restent indisponibles ; l’absence d’ouverture par cette correction ne certifie pas leur historique d’accès.

La section qui suit est la photographie documentaire antérieure, conservée pour provenance. Ses affirmations de minorant, de bruit pur et de validation du coffre ne s’appliquent pas aux nouvelles exécutions.

---

# Registre des expériences

Toute expérience lancée figure ici, **y compris les échecs, y compris les
plantages**. Une expérience qui a touché les données et n'est pas publiée est une
fraude envers soi-même.

Le compteur brut est tenu automatiquement dans `ledger.json` par le harness.

| ID | Titre | Auteur | Statut | Porte atteinte | Configs | Verdict |
|---|---|---|---|---|---|---|
| EXP-0000 | Calibration du plancher de bruit | claude | clos | — (instrument) | 9 | **p95 du bruit = +1,67** (blocs 24 h). Réel : −1,46. Le retour à la moyenne naïf sur BTC 1h est significativement perdant (t = −4,27, −41 bps/trade). Voir [RAPPORT](EXP-0000-calibration/RAPPORT.md) |

## Statuts possibles

| Statut | Sens |
|---|---|
| `ouvert` | hypothèse déposée, en attente d'exécution |
| `en cours` | le harness tourne, ou une attaque est en cours |
| `mort` | tombé sur une porte, définitif |
| `CONTAMINÉ` | chiffres de backtest dans l'hypothèse, ou spec modifiée après résultats |
| `clos` | passé toutes les portes, ou instrument de mesure |

## Portes

`G0` préenregistrement · `G1` test minimal · `G2` red team · `G3` robustesse ·
`G4` plancher de bruit · `G5` walk-forward + OOS · `G6` coffre-fort · `G7` réel

Détail dans [PROTOCOLE.md](../PROTOCOLE.md).

## Compteur d'essais

| | |
|---|---|
| Dette héritée (déclarée, non vérifiée) | **136** |
| Essais de ce dépôt | voir `ledger.json` |

La dette héritée vient de `sources/projet-2/registre-hypotheses.json` : 120 essais
de sélection (4 actifs × 3 méthodes × 5 lookbacks × 2 régimes) + 16 combinaisons de
base. C'est un **minorant** : les « périodes voisines également examinées » ne sont
pas comptées, et la part spécifique à BTC n'est pas établie
(`unique_btc_trial_count_verified = null`).

Conséquence : tout Deflated Sharpe publié ici est **optimiste**. Cette réserve
accompagne chaque résultat tant qu'Astra n'a pas établi le compte réel.

## Ouvertures consommées

| Bloc | Consommées | Restantes |
|---|---|---|
| OOS | 0 | 1 par stratégie |
| VAULT-H (historique, **non vierge**) | 0 | 1, valeur indicative seulement |
| VAULT-F (futur, vierge) | 0 | **1, définitive** |

**VAULT-H n'est pas un test final.** Les archives établissent que la période
2025-2026 a déjà été consultée (`final_test_already_consulted: "2025-2026"`).
Voir [vault/SEAL.md](../vault/SEAL.md).
