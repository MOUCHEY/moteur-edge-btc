> Notice du 15 septembre 2026 : instructions historiques. Le [protocole révisé](PROTOCOLE.md) et le [format G0](docs/PREENREGISTREMENT.md) régissent les nouvelles exécutions ; Claude n’est pas un intermédiaire obligatoire.

# Astra — comment soumettre

Tu génères les hypothèses. Tu ne valides pas les tiennes : c'est Claude qui attaque,
et il n'a pas le droit de réparer. Ton seul moyen de répondre à une attaque est
**une nouvelle mesure**, jamais un argument.

---

## 1. Ouvre l'expérience

```
experiments/EXP-XXXX-nom-court/
  hypothesis.md      ← tu écris ça EN PREMIER, avant toute mesure
  spec.yaml          ← la stratégie figée
  results/           ← Claude y dépose les résultats et son attaque
```

### `hypothesis.md` — les cinq sections obligatoires

1. **L'hypothèse**, en une phrase falsifiable.
2. **Le mécanisme** : *qui* perd de l'argent en face, et *pourquoi il continue*.
   « Le backtest le montre » n'est pas un mécanisme et fait échouer G0 sur-le-champ.
   Un mécanisme valable ressemble à : un liquidateur forcé doit vendre quelle que
   soit la valeur ; un market maker élargit son spread quand son inventaire penche ;
   un fonds rééquilibre à heure fixe sans regarder le prix.
3. **Les prédictions de forme**, écrites AVANT de mesurer. Quelles monotonies le
   mécanisme impose-t-il ? *L'effet doit croître avec l'amplitude. Il doit
   disparaître aux heures liquides. Il doit être plus fort le week-end.*
   Quatre monotonies conformes valent mieux qu'un t-stat élevé.
4. **Le budget d'essais** : combien de configurations seront balayées, au total.
   Ce nombre entre dans le Deflated Sharpe. Le sous-déclarer, c'est se mentir.
5. **Le critère d'abandon** : ce qui, si mesuré, te ferait renoncer toi-même.
   Une hypothèse sans critère d'abandon n'est pas une hypothèse.

> **Aucun chiffre de backtest dans `hypothesis.md`.** S'il y en a un, l'expérience
> est marquée `CONTAMINÉE` et son budget est décompté quand même.

---

## 2. Écris `spec.yaml`

```yaml
id: EXP-0001
titre: "Retour après liquidation forcée"
auteur: astra

data:
  interval: 1h            # 1h ou 15m

signal:
  entry_long:  "(ret_1 < -{seuil}) & (vol_rel_24 > 3) & (taker_z_72 < -1.5)"
  entry_short: null

exit:
  mode: horizon           # horizon | bracket
  horizon: 6              # en barres
  # mode bracket :
  # stop_atr: 1.0
  # target_atr: 2.0
  # atr_col: atr_48

params:                   # 3 paramètres libres MAXIMUM (règle G1)
  seuil: [150, 200, 250]

budget_essais: 3
```

**Règles d'écriture des expressions**

- Opérateurs vectoriels : `&`, `|`, `~` — jamais `and`, `or`, `not`.
- Parenthéser chaque comparaison : `(a > 1) & (b < 2)`.
- Les paramètres s'injectent avec `{nom}`.
- Tout est en **points de base** (1 bp = 0,01 %), sauf `rsi_14`, `hour`, `dow`,
  les `z_*` et `taker_ratio`.
- Signal évalué à la **clôture** de la barre `t`, entrée à l'**open** de `t+1`.
  Tu n'as pas à le gérer : le harness l'impose, et un test automatique plante si
  une feature triche.

---

## 3. Les features disponibles

| Famille | Colonnes | Unité |
|---|---|---|
| Rendements passés | `ret_1` `ret_4` `ret_12` `ret_24` `ret_72` `ret_168` | bps |
| Volatilité | `vol_24` `vol_72` `vol_168` | bps |
| Position dans la distribution | `z_close_24` `z_close_72` `z_close_168` | écarts-types |
| Amplitude | `range_bps` `atr_14` `atr_48` `body_bps` | bps |
| Oscillateur | `rsi_14` | 0-100 |
| **Flux agressif** | `taker_ratio` `taker_ratio_24` `taker_z_72` | ratio / z |
| **Activité** | `vol_rel_24` `trade_size` `trade_size_z` | ratio / z |
| Distance aux extrêmes | `dist_high_24/72/168` `dist_low_24/72/168` | bps |
| Calendrier (UTC) | `hour` `dow` `is_weekend` | entiers |

> Le bloc **flux** mérite ton attention. `taker_ratio` est la part du volume
> exécutée à l'achat *au marché* — donc de l'agression acheteuse observable.
> C'est une donnée que la plupart des backtests OHLC n'ont pas. Si un mécanisme
> existe sur BTC, il y a une chance qu'il laisse une trace là plutôt que dans un
> énième croisement de moyennes mobiles.

---

## 4. Ce qui te fera échouer, par ordre de fréquence

1. **Pas de mécanisme.** Un motif sans explication de qui paie est du bruit
   jusqu'à preuve du contraire, pas l'inverse.
2. **Une cellule brillante dans une famille morte.** G1 exige que la **médiane**
   des t-stats de ta grille soit positive, pas seulement son maximum. Une config
   à t = 3 entourée de voisins négatifs sera rejetée sans discussion.
3. **Grille élargie après résultats.** Le hash de la spec change, c'est une
   nouvelle expérience, et l'ancienne reste publiée avec son échec.
4. **Budget sous-déclaré.** Le compteur du dépôt est global et ne se remet jamais
   à zéro.
5. **Répondre à une attaque par un argument.** La seule réponse recevable est une
   mesure reproductible par `python3 -m engine.run`.

---

## 5. Où viser

Un conseil qui vaut ce qu'il vaut, et qui n'engage que la personne qui l'écrit :
les familles les plus balayées de la littérature retail (croisements de moyennes,
RSI, cassures de range simples) sont aussi les plus mortes. Ce qui reste
plausible sur BTC tient plutôt à des **contraintes structurelles** :

- **Liquidation forcée** — les positions à effet de levier se liquident au marché,
  sans égard au prix. Trace attendue : volume anormal + flux agressif d'un seul
  côté + amplitude extrême. Le vendeur n'a pas le choix : c'est un mécanisme, pas
  une opinion.
- **Heures de rééquilibrage** — certains flux passent à heures fixes (clôtures CME,
  fixings). Trace attendue : un effet horaire qui *disparaît* le week-end, quand
  les acteurs institutionnels sont absents. Cette prédiction-là est testable et
  falsifiable, ce qui la rend intéressante.
- **Inventaire de market maker** — après un déséquilibre de flux prolongé, celui
  qui a absorbé doit se rééquilibrer.

Chacune de ces pistes impose des monotonies vérifiables. C'est ce qui les rend
attaquables — donc utiles. Une piste inattaquable ne vaut rien ici.
