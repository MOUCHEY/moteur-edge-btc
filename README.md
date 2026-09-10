# moteur EDGE RENTABLE / BTC

> Un moteur de recherche qui découvre, teste et **détruit** des stratégies sur BTC
> jusqu'à ce qu'il n'en reste plus qu'une qui tienne vraiment la route.

Ce dépôt n'est pas un bot. C'est un **processus contradictoire**, avec deux agents
qui ne poursuivent pas le même but, et un arbitre humain.

L'avantage recherché ici n'est pas un algorithme secret. C'est le process, les
données, et la rigueur. Un bot se copie ; un protocole de falsification, non.

---

## Le principe

La faute qui coûte de l'argent est toujours la même : **optimiser sur l'historique,
y croire, perdre en réel.** Elle vient d'un défaut de structure — la même personne
cherche l'edge et le valide, donc devient l'avocat de sa propre découverte.

D'où la règle qui gouverne tout ce dépôt :

**Celui qui découvre ne valide jamais. Celui qui attaque ne répare jamais.**

| | **Astra** | **Claude** | **Jeunathan** |
|---|---|---|---|
| Rôle | Découverte | **Red team** | Arbitre |
| Produit | Hypothèses + specs figées | Attaques + exécutions du harness | Décisions |
| Interdit | Élargir une grille après coup | **Réparer une stratégie** | — |

Claude ne propose jamais d'amélioration. S'il trouve une faille réparable, c'est à
Astra de la réparer — dans une **nouvelle** expérience qui consomme du budget.
Un attaquant qui répare devient l'avocat de sa propre correction, et le dispositif
s'effondre.

---

## Comment ça circule

```
   Astra                        GitHub                        Claude
     │                            │                              │
     │  1. hypothesis.md ────────►│                              │
     │     (mécanisme, prédictions,│                             │
     │      budget — AUCUN chiffre)│                             │
     │                            │◄──── 2. exécute le harness ──│
     │                            │      publie les résultats     │
     │                            │◄──── 3. rapport d'attaque ────│
     │                            │      failles fatales/majeures │
     │  4. réponse par une ───────►│                             │
     │     NOUVELLE mesure         │                             │
     │        (jamais un argument) │                             │
     ▼                            ▼                              ▼
              les 8 portes, dans l'ordre, sans en sauter
```

Les règles de passage sont dans **[PROTOCOLE.md](PROTOCOLE.md)**. Elles sont
chiffrées et pré-écrites : une porte se franchit sur un critère, pas sur un avis.

---

## Les données

| Bloc | Période | Barres (1h) | Accès |
|---|---|---|---|
| **IS** — bac à sable | 2017-08-17 → 2022-12-31 | 46 983 | libre |
| **OOS** — validation | 2023-01-01 → 2025-08-31 | 23 375 | 1 ouverture par stratégie |
| **VAULT-H** — coffre historique | 2025-09-01 → 2026-08-31 | 8 760 | 1 ouverture, **valeur indicative seulement** |
| **VAULT-F** — coffre futur | à partir du 2026-09-10 | croît | **1 ouverture, définitive** |

Source : dumps publics Binance spot (`data.binance.vision`), BTCUSDT, 1h et 15m.
Téléchargement reproductible par `python3 data/fetch.py`, hash publié dans
`data/MANIFEST.json`.

**Il y a deux coffres, et un seul est propre.** Astra a objecté — archives à
l'appui — que la période 2025-2026 avait déjà été consultée comme test final dans
un projet antérieur (`final_test_already_consulted: "2025-2026"`). Changer de
fournisseur de données ne rétablit pas l'indépendance : ce sont les mêmes prix,
déjà regardés. **VAULT-H peut donc tuer une stratégie, jamais l'anoblir.** Seul
**VAULT-F**, collecté après le gel du 10 septembre 2026, est vierge par
construction. Détail : [vault/SEAL.md](vault/SEAL.md).

**Le coffre est chiffré, pas seulement rangé à part.** La période scellée est
physiquement absente des fichiers publiés, et `data/fetch.py` est borné pour
qu'un retéléchargement ne la réécrive pas en clair. La clé AES-256 vit hors du dépôt, dans
`~/.moteur-edge-btc/vault.key`, et a été générée par un sous-processus qui l'a
écrite directement sur disque — elle n'a jamais transité par la sortie standard,
donc aucun des deux agents ne l'a lue. Le verrou tient même contre nous.

Ouvrir le coffre demande de déposer un fichier `vault/OPEN_AUTHORISATION`. Chaque
ouverture est journalisée dans `vault/OUVERTURES.log` et le hash du contenu est
vérifié : une altération se voit.

---

## Démarrer

```bash
pip install -r requirements.txt
python3 data/fetch.py                      # données, vérifiées et hashées
python3 -m unittest discover -s tests -v   # 26 tests des mécanismes du protocole
python3 -m engine.run experiments/EXP-0000-calibration/spec.yaml --split IS
python3 -m engine.attack experiments/EXP-0000-calibration/spec.yaml --params '{"fen":72,"seuil":2.0}'
```

Structure :

```
PROTOCOLE.md        les 8 portes et les règles anti-triche — la loi du dépôt
ASTRA.md            comment Astra soumet une hypothèse
RED_TEAM.md         la checklist d'attaque de Claude
engine/             harness : données, features, backtest, métriques, validation
experiments/        une expérience = un dossier, résultats inclus, échecs inclus
  ledger.json       compteur d'essais du projet — il ne se remet jamais à zéro
vault/              le coffre-fort chiffré
```

---

## Le compteur d'essais

`experiments/ledger.json` compte **toutes** les configurations testées depuis le
début du projet — y compris celles des expériences abandonnées. Ce nombre entre
dans le Deflated Sharpe de toute stratégie évaluée ensuite.

C'est ce qui rend le protocole honnête : **plus on cherche, plus la barre monte,
et personne ne peut repartir de zéro.**

---

## Ce que ce dépôt ne peut pas faire

À écrire noir sur blanc, parce que l'auto-illusion commence toujours ici.

- Des bougies OHLC ne contiennent ni carnet d'ordres, ni flux réel, ni calendrier.
  Ne rien trouver ici ne prouve pas qu'il n'y a rien.
- Un backtest n'a ni la latence, ni l'exécution, ni le broker réel.
- Les coûts utilisés (**6 bps aller-retour**) sont une **hypothèse non mesurée**,
  pas un relevé. Tout résultat est conditionnel à ce chiffre tant que les relevés
  cTrader réels ne l'ont pas remplacé. Voir `docs/COUTS.md`.
- **Le résultat le plus probable de ce protocole est qu'aucune stratégie ne passe.**
  C'est un résultat, pas un échec.

---

## La barre à franchir

Mesuré, pas supposé — `experiments/EXP-0000-calibration/RAPPORT.md` :

> Un balayage de **neuf configurations** sur du **bruit pur** produit un t-stat
> maximal de **+1,67 au 95ᵉ centile** et **+4,03 au maximum**, avec une médiane
> positive.

Neuf. Une grille minuscule suffit à fabriquer un t-stat de 1,7. C'est le chiffre
que toute stratégie proposée ici doit battre.

## Statut

| | |
|---|---|
| Harness | opérationnel, test anti-lookahead automatique |
| Données publiques | 70 357 barres 1h + 281 374 barres 15m, 29 et 32 gaps |
| Tests des mécanismes | **26, 0 échec** |
| Coffres | scellés le 2026-09-10, **0 ouverture** |
| Compteur d'essais | **136** (dette héritée déclarée, minorant) |
| Stratégies passées en G7 | **0** |
