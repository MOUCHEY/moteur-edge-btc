# Note de relais — Claude → Astra

**Étape 1 : socle du dépôt.** 10 septembre 2026.

---

## Statut de chaque élément

Vocabulaire imposé : *prévu* · *implémenté* · *exécuté* · *vérifié* · *inconnu*.

| Élément | Statut | Preuve |
|---|---|---|
| Protocole expérimental (8 portes, critères chiffrés) | **implémenté** | `PROTOCOLE.md` |
| Registre de toutes les expériences | **implémenté** | `experiments/REGISTRE.md`, `ledger.json` |
| Compteur d'essais non remis à zéro | **vérifié** | test `test_le_deflated_sharpe_baisse_quand_les_essais_montent` + garde CI |
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
