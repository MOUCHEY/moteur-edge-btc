# EXP-0000 — Calibration du plancher de bruit

**Auteur :** Claude (red team) · **Date :** 2026-09-10 · **Statut :** clos
**Nature :** instrument de mesure, **pas** une stratégie candidate.

---

## Pourquoi cette expérience existe

Le seuil théorique de tests multiples (Bonferroni, √(2 ln N)) ne s'applique pas
ici : les configurations d'un balayage partagent les mêmes données et ne sont pas
indépendantes. Plutôt que de postuler un seuil, on le **mesure** — en rejouant
exactement le même balayage sur des séries où l'on sait qu'il n'y a rien.

## Ce qui a été exécuté

Famille banale de retour à la moyenne, 9 configurations :

```
entry_long  : (z_close_{fen} < -{seuil}) & (rsi_14 < 45)
entry_short : (z_close_{fen} >  {seuil}) & (rsi_14 > 55)
sortie      : horizon fixe, 12 barres
fen ∈ {24, 72, 168} × seuil ∈ {1,5 ; 2,0 ; 2,5}
```

Données : BTCUSDT 1h, split IS (2017-08-17 → 2022-12-31), 46 983 barres.
Coûts : 6 bps aller-retour. Plancher : 200 séries synthétiques par configuration
de bootstrap, blocs de barres entières.

## Résultat 1 — le réel

| Mesure | Valeur |
|---|---|
| max t-stat sur les 9 configs | **−1,46** |
| config centrale (fen=72, seuil=2,0) | t = **−4,27**, net = **−41,3 bps/trade**, 1 128 trades |
| profit factor | 0,685 |

**Le retour à la moyenne naïf sur BTC 1h est fortement et significativement
perdant.** Ce n'est pas « pas d'edge » : c'est un edge négatif franc. Cohérent
avec un actif à structure momentum, et **aucune** des 9 configurations n'échappe
à la règle.

## Résultat 2 — le plancher de bruit

Distribution du **maximum du balayage** sur 200 séries synthétiques :

| Bootstrap | p05 | médiane | **p95** | p99 | max |
|---|---|---|---|---|---|
| blocs 168 h, avec dérive | −2,25 | −0,79 | **+0,60** | +0,85 | +1,24 |
| blocs 24 h, avec dérive | −0,98 | +0,35 | **+1,67** | +2,64 | **+4,03** |
| blocs 24 h, sans dérive | −0,90 | +0,40 | **+1,64** | +2,48 | +3,62 |

### Le chiffre à retenir

> **Un balayage de neuf configurations seulement, sur du bruit pur, produit un
> t-stat maximal supérieur à +1,67 dans 5 % des cas, et atteint +4,03.**
> Sa valeur médiane est **positive** (+0,35).

Neuf. Pas neuf cents. Toute stratégie proposée ici avec un t-stat de 1,7 sur une
grille de cette taille est, jusqu'à preuve du contraire, **indiscernable du
hasard** — quelle que soit l'élégance de son mécanisme.

### La dérive n'explique rien

Retirer la dérive de BTC déplace le p95 de 1,674 à 1,637, soit 2 %. Pour une
famille long/short symétrique, la tendance de fond s'annule : le plancher vient
de la **variance de la recherche**, pas de la hausse du bitcoin.

### La taille de blocs change le verdict, et pas dans le sens attendu

Passer de blocs de 24 h à 168 h fait tomber le p95 de **+1,67 à +0,60** — le test
devient presque trois fois plus permissif.

L'attente courante veut que des blocs plus longs que l'horizon préservent la
structure testée et rendent le test *trop conservateur*. **La mesure dit
l'inverse ici**, et la raison est instructive : la structure préservée par les
blocs longs est *défavorable* à cette stratégie (BTC porte du momentum, la
stratégie parie sur le retour). Préserver la structure rend donc les séries
synthétiques hostiles, et le plancher s'abaisse.

Le sens du biais dépend du signe de la relation entre la structure préservée et
la stratégie testée. Il ne se devine pas.

**Règle qui en découle, désormais appliquée par le code :** toute mesure de
plancher publiée dans ce dépôt déclare sa taille de blocs et en publie au moins
deux. Un plancher sans taille de blocs déclarée n'est pas recevable.

## Conséquences pour le protocole

1. **G4 se lit contre le p95 du plancher**, pas contre zéro ni contre un seuil
   théorique.
2. **Le plancher se recalcule pour chaque famille.** Ces chiffres valent pour une
   grille de 9 configs à horizon 12. Une grille plus large déplacera la barre
   vers le haut.
3. **Un t-stat isolé ne veut rien dire sans son budget de recherche.** C'est ce
   que le Deflated Sharpe formalise, et ce que ce tableau rend tangible.

## Limites de cette calibration

À dire explicitement, faute de quoi ce rapport se ferait passer pour plus qu'il
n'est :

- Une seule famille testée. Le plancher d'une famille de cassures ou de flux
  n'est **pas** mesuré et n'est pas supposé identique.
- 200 simulations : le p95 est lui-même bruité. L'incertitude sur p95 n'a pas
  été chiffrée — **non mesurée**.
- Le bootstrap de blocs préserve la distribution des rendements mais détruit les
  dépendances longues. Un mécanisme opérant à l'échelle du mois serait invisible
  dans ce null.
- Les coûts sont ceux de `engine/costs.py`, **hypothèses non mesurées**
  (voir `docs/COUTS.md`).

## Reproduire

```bash
python3 -m engine.calibrate experiments/EXP-0000-calibration/spec.yaml --sims 200 --block 24
python3 -m engine.calibrate experiments/EXP-0000-calibration/spec.yaml --sims 200 --block 168
python3 -m engine.calibrate experiments/EXP-0000-calibration/spec.yaml --sims 200 --block 24 --remove-drift
```

Résultats bruts : `results/plancher_IS.json`, `results/plancher_IS_nodrift.json`.
