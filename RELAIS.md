# Note de relais — Claude → Astra

**Étape 1 : socle du dépôt.** 10 septembre 2026.

---

## Statut de chaque élément

Vocabulaire imposé : *prévu* · *implémenté* · *exécuté* · *vérifié* · *inconnu*.

| Élément | Statut | Preuve |
|---|---|---|
| Protocole expérimental (8 portes, critères chiffrés) | **implémenté** | `PROTOCOLE.md` |
| Registre de toutes les expériences | **implémenté** | `experiments/REGISTRE.md`, `ledger.json` |
| Compteur d'essais non remis à zéro | **vérifié** | garde CI exécutée sur GitHub — **décorative au premier run** (clone à 1 commit), corrigée, couverte par 4 tests `GardeFousCI` ; force-push et suppression de `main` bloqués (voir `ci/README.md`) |
| Versions figées des candidates + filiation | **implémenté** | hash de spec ; `test_le_hash_change_si_la_spec_change` |
| Rapports d'attaque séparés des réponses | **implémenté** | `RED_TEAM.md`, `.github/ISSUE_TEMPLATE/` |
| Budgets d'essais et règles d'arrêt | **vérifié** | `spec.validate()` refuse grille > budget et > 3 paramètres |
| Tests des mécanismes | **exécuté et vérifié** | **26 tests, 0 échec** |
| Harness de backtest sans lookahead | **vérifié** | détecteur de fuite + test qui lui donne une vraie fuite à attraper |
| Coffre-fort isolé, ouverture unique | **implémenté**, ouverture **non exécutée** | `vault/SEAL.md`, `OUVERTURES.log` vide |
| Coûts réalistes | **INCONNU** | hypothèses non mesurées — `docs/COUTS.md` |
| Rentabilité d'une stratégie quelconque | **inconnu** | aucune candidate testée |

## Ce qui a réellement été exécuté

- Téléchargement Binance : **70 357 barres 1h** + **281 374 barres 15m** publiques
  (2017-08-17 → 2025-08-31), 29 et 32 gaps. Hashes dans `data/MANIFEST.json`.
- **26 tests unitaires** des mécanismes : 0 échec.
- **EXP-0000**, calibration du plancher de bruit : 3 × 200 simulations.
- Scellement du coffre : 8 760 barres 1h + 35 040 barres 15m chiffrées.
- **Non exécuté** : aucune ouverture d'OOS, aucune ouverture de coffre, aucune
  connexion courtier, aucun ordre, aucune stratégie candidate évaluée.

## Le résultat qui doit orienter ta prochaine expérience

Un balayage de **neuf configurations** sur du bruit pur produit :

| | p95 | max |
|---|---|---|
| t-stat maximal du balayage | **+1,67** | **+4,03** |

médiane **positive** (+0,35). Détail et nuances : `experiments/EXP-0000-calibration/RAPPORT.md`.

Autrement dit : une grille minuscule suffit à fabriquer un t-stat de 1,7. Ce n'est
pas un argument contre ta prochaine hypothèse — c'est la barre qu'elle devra
franchir, et elle est plus haute que l'intuition ne le suggère.

Résultat annexe, utile : le **retour à la moyenne naïf sur BTC 1h est
significativement perdant** (t = −4,27, −41,3 bps/trade sur 1 128 trades, les 9
configurations perdantes). Cette famille est déjà explorée et morte ; inutile d'y
dépenser du budget.

## Trois points où je t'ai donné raison

1. **Ton objection sur la virginité du coffre était fondée**, et je l'ai vérifiée
   dans tes archives : `final_test_already_consulted: "2025-2026"`. J'avais scellé
   exactement cette période. J'ai donc séparé **VAULT-H** (historique, non vierge,
   valeur indicative) et **VAULT-F** (observations postérieures au gel, seules
   réellement inédites, collecte amorcée : 11 barres 1h).
2. **Le compteur ne repart pas de zéro** : initialisé à **136** d'après ton
   registre. C'est un minorant, et je le dis dans chaque résultat.
3. **Tes défauts A01–A03 sont portés en issues**, sources héritées non modifiées.

## Problèmes ouverts, par ordre de gravité

1. **Les coûts ne sont pas mesurés.** 6 bps aller-retour est une hypothèse. Toute
   conclusion du dépôt y est conditionnelle. Il faut les relevés cTrader réels :
   spread effectif par heure UTC, slippage signé, financement. **C'est le trou le
   plus sérieux du dépôt.**
2. **Binance spot ≠ CFD IC Markets.** Nos données ne sont pas l'instrument tradé.
   Un edge trouvé ici n'est pas garanti transférable. Non mesuré, non résoluble
   avant G7.
3. **La dette héritée de 136 est déclarée, non vérifiée.** La part BTC est
   inconnue. Tant que ce n'est pas établi, nos DSR sont optimistes.
4. **Le plancher de bruit dépend fortement de la taille de blocs** (p95 : 0,60 à
   1,67 selon 168 h ou 24 h) — et le sens du biais ne se devine pas. Le code
   avertit désormais, mais le choix reste à justifier famille par famille.
5. **L'incertitude sur le p95 lui-même n'est pas chiffrée** (200 simulations).

## Ce que j'attends de toi

Une hypothèse préenregistrée via `.github/ISSUE_TEMPLATE/hypothese.md`, avec un
mécanisme nommant **qui perd de l'argent en face**, et des prédictions de forme
écrites avant toute mesure.

Tes H1 (cassure) et H2 (correction d'écart) sont recevables comme point de départ,
à condition d'être réécrites au format G0 — leurs paramètres hérités ne doivent pas
être recopiés comme un optimum validé, puisqu'ils n'ont jamais été exécutés.

Une remarque de red team, à prendre pour ce qu'elle vaut : H2 appartient à la
famille du retour à la moyenne, que EXP-0000 vient de mesurer comme franchement
perdante sur BTC 1h. Ce n'est pas une réfutation de H2 — son mécanisme et ses
paramètres diffèrent — mais le budget dépensé de ce côté part avec un handicap
mesuré. Le choix reste le tien : je signale, je ne répare pas et je ne dirige pas.

## Comment je travaille

Je n'exécute rien qui ne soit reproductible par `python3 -m engine.run` ou
`python3 -m engine.attack`. Je ne répare aucune stratégie. Je ne modifie aucun
paramètre de risque, de volume ou de position. Quand je n'ai pas mesuré, je l'écris.

## Issues ouvertes

| # | Titre | Gravité |
|---|---|---|
| [#3](https://github.com/MOUCHEY/moteur-edge-btc/issues/3) | Les coûts de transaction ne sont pas mesurés | **bloquant** |
| [#5](https://github.com/MOUCHEY/moteur-edge-btc/issues/5) | La dette héritée de 136 essais est déclarée, non vérifiée | **bloquant** |
| [#6](https://github.com/MOUCHEY/moteur-edge-btc/issues/6) | Réécrire H1 et H2 au format de préenregistrement | G0 — **à toi** |
| [#1](https://github.com/MOUCHEY/moteur-edge-btc/issues/1) | A01 — vérification dépendante des originaux | hérité |
| [#2](https://github.com/MOUCHEY/moteur-edge-btc/issues/2) | A02 — assertions supprimées sous `python -O` | hérité |
| [#4](https://github.com/MOUCHEY/moteur-edge-btc/issues/4) | A03 — résultat accepté puis refusé par le contrôle suivant | hérité |

Sur #2 : j'y avais d'abord écrit que notre détecteur de lookahead serait désactivé
sous `python -O`. C'était faux, je l'ai mesuré, et l'issue porte la correction —
`raise AssertionError` n'est pas supprimé par `-O`, seul le mot-clé `assert` l'est,
et il n'y en a aucun dans `engine/` ni `data/`.

---

## Mise à jour — 13 septembre 2026

**La CI tourne sur GitHub.** Le blocage de facturation du compte est levé. Premier run
réel : 11 étapes, succès, 26 tests.

**Et ce premier run vert a révélé un défaut dans mon propre harness.** Le contrôle
« le compteur d'essais ne redescend jamais » ne voyait pas l'historique sur GitHub
(clone à un seul commit par défaut). Il passait sans rien comparer — reproduit : il
passait aussi avec le compteur remis à zéro. Corrigé, et la suite compte désormais
**30 tests** : les 4 nouveaux rejouent l'étape exacte du workflow dans des clones.
Contre l'ancienne version, deux échouent — ceux qui visent le défaut ; les deux autres
vérifient que la correction n'a rien cassé. Détail : `ci/README.md`.

Je le signale parce que c'est le type de défaut que tu dois chercher chez moi aussi :
**un garde-fou qui passe quand il ne peut pas vérifier.** Un compteur d'essais
effaçable rendrait le Deflated Sharpe de toute ta future stratégie optimiste, sans
aucune alarme.

**Protection de `main` activée** avec l'accord de Jeunathan : réécriture forcée et
suppression refusées, sans exception, vérifiées par l'usage sur une branche jetable. La
règle elle-même reste supprimable par le compte propriétaire. Détail : `ci/README.md`.

**Rien ne change pour ta prochaine expérience** : l'issue #6 (H1 et H2 au format G0)
reste la suite attendue.
