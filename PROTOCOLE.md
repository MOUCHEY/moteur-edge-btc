# Protocole — moteur EDGE RENTABLE / BTC

Ce document est la **loi du dépôt**. Il prime sur toute opinion, la mienne comprise.
Il ne se modifie pas au milieu d'une expérience : un changement de règle est un
commit séparé, daté, justifié, et il **ne s'applique pas rétroactivement** aux
expériences déjà closes.

---

## 0. Le principe qui gouverne tout

> On ne cherche pas une stratégie rentable. On cherche à **détruire** des
> stratégies jusqu'à ce qu'il en reste une qui refuse de mourir.

Conséquence directe : **la découverte et la falsification ne sont jamais faites
par le même acteur.**

| Acteur | Rôle | Interdit absolu |
|---|---|---|
| **Astra** | Génère des hypothèses avec mécanisme. Écrit une spec. Répond aux attaques par de nouvelles expériences. | Élargir une grille après avoir vu un résultat. Défendre une stratégie autrement que par une mesure. |
| **Claude** | Red team. Exécute le harness. Attaque : sur-optimisation, biais, instabilité, fuite de données. | **Réparer** une stratégie. Proposer une amélioration. Adoucir un verdict. |
| **Jeunathan** | Arbitre. Seul à décider d'un passage de porte contesté, d'une ouverture de coffre, et de tout ce qui touche à l'argent réel. | — |

Claude ne répare pas. Si une faille est réparable, c'est à Astra de le faire, dans
une **nouvelle** expérience qui incrémente le compteur d'essais. C'est le point qui
fait tenir tout le reste : un attaquant qui répare devient l'avocat de sa propre
correction.

---

## 1. Découpage des données — figé le 10 septembre 2026

| Bloc | Période | Qui y touche | Combien de fois |
|---|---|---|---|
| **IS** (bac à sable) | 2017-08-17 → 2022-12-31 | Astra et Claude, librement | ∞ |
| **OOS** (validation) | 2023-01-01 → 2025-08-31 | Ouvert par la porte G5 | **1 fois par stratégie** |
| **VAULT** (coffre-fort) | 2025-09-01 → dernier mois complet | Personne | **1 fois pour tout le projet** |

Le VAULT est chiffré dans le dépôt. La clé n'est pas versionnée. Son hash est publié
dans `vault/SEAL.md`. Ce n'est pas de la sécurité contre un adversaire — c'est un
verrou de procédure : si quelqu'un le touche, ou refait le découpage après coup,
ça se voit.

**Une ouverture d'OOS est irréversible.** Une stratégie dont l'OOS a été ouvert et
qui échoue est morte. Elle ne revient pas « corrigée » : une variante corrigée est
une nouvelle stratégie, avec un nouveau numéro, et l'OOS déjà consommé compte dans
le budget d'essais du projet.

---

## 2. Les portes

Une expérience monte les portes dans l'ordre. Elle ne saute rien. Chaque porte a un
critère **chiffré et pré-écrit** — pas un jugement.

### G0 — Préenregistrement (Astra)

Avant toute mesure, Astra dépose `hypothesis.md` contenant :

1. **L'hypothèse en une phrase**, falsifiable.
2. **Le mécanisme** : *qui* perd de l'argent en face, et *pourquoi* il continue.
   « Le backtest le montre » n'est pas un mécanisme et fait échouer G0 immédiatement.
3. **Les prédictions de forme**, écrites AVANT de mesurer : quelles monotonies le
   mécanisme impose (l'effet doit croître avec X, disparaître quand Y, etc.).
4. **Le budget d'essais déclaré** : combien de configurations seront balayées.
   Ce nombre entre dans le Deflated Sharpe. Le sous-déclarer, c'est se mentir.
5. **Le critère d'abandon** : ce qui, mesuré, ferait renoncer Astra elle-même.

> Aucun chiffre de backtest ne figure dans `hypothesis.md`. S'il y en a un,
> l'expérience est marquée `CONTAMINÉE` et son budget est décompté quand même.

### G1 — Test minimal (Claude exécute)

Sur **IS uniquement**. Pas d'optimisation : ≤ 3 paramètres libres, grille identique
à celle déclarée en G0. Coûts appliqués dès la première mesure, jamais ajoutés après.

Passe si **tout** est vrai :
- [ ] `t_net > 0` sur la configuration centrale
- [ ] **médiane des t-stats de la famille > 0** — pas seulement son maximum
- [ ] `slippage_de_mort ≥ 3 × spread moyen`
- [ ] ≥ 100 trades sur IS (sinon aucun test n'a de puissance)

La deuxième condition tue la majorité des candidats et c'est voulu. Une cellule
brillante dans une grille de voisins négatifs est du bruit, quel que soit son t-stat.

### G2 — Red team (Claude)

Claude applique la checklist de `RED_TEAM.md` et publie un rapport d'attaque.
Chaque faille est classée : **fatale** (l'expérience meurt), **majeure** (Astra doit
répondre par une mesure), **mineure** (consignée, sans blocage).

Passe si : aucune faille fatale, et chaque faille majeure a reçu une **réponse
mesurée** — pas une réponse argumentée.

### G3 — Robustesse structurelle

- [ ] Voisinage de paramètres positif à **≥ 75 %**
- [ ] Positif sur les **deux moitiés temporelles** de l'IS
- [ ] Les monotonies annoncées en G0 sont **vérifiées** (Spearman ρ > 0,7 sur celles
      qui sont ordinales)
- [ ] Survit à des coûts **× 1,5** et **× 2**

### G4 — Plancher de bruit

Le seuil théorique de tests multiples ne s'applique pas : les configurations
partagent les mêmes données et ne sont pas indépendantes. On mesure le plancher
au lieu de le postuler.

- [ ] **Le même balayage** rejoué sur séries synthétiques (bootstrap de blocs) :
      le résultat réel doit dépasser le **95e centile** des meilleurs résultats
      synthétiques
- [ ] **Permutation d'étiquettes** sur la condition (heure, régime, seuil) :
      p empirique < 0,05, calculé en respectant les grappes de dépendance

### G5 — Validation dynamique, puis OOS

- [ ] **Walk-forward ancré** : profitable sur ≥ 60 % des fenêtres hors échantillon
- [ ] **Monte-Carlo** sur l'ordre des trades : le 95e centile du drawdown reste
      dans le budget de risque
- [ ] **Deflated Sharpe > 0**, avec le nombre d'essais **réel** du projet entier,
      pas celui de la seule expérience

Alors, et seulement alors : **une** exécution sur OOS. Passe si `z_oos > 0` et si
l'espérance nette par trade sur OOS est ≥ 50 % de celle de l'IS.

### G6 — Coffre-fort

Ouverture unique, pour **une seule** stratégie, sur décision de Jeunathan.
Aucune modification n'est permise après. Le résultat est publié quel qu'il soit.

### G7 — Réel, très petite somme

Paramètres gelés. Le forward test mesure en priorité le **slippage réel contre la
marge**, pas le taux de réussite. Toute divergence > 30 % sur le coût par trade
arrête le test.

---

## 3. Le budget d'essais est une ressource

Le dépôt tient un **compteur global** dans `experiments/REGISTRE.md`. Chaque
configuration testée l'incrémente — y compris celles des expériences abandonnées,
y compris celles qu'on préférerait oublier.

Ce compteur entre dans le Deflated Sharpe de **toute** stratégie évaluée ensuite.
C'est ce qui rend le protocole honnête : plus on cherche, plus la barre monte.
Personne ne peut « repartir de zéro ».

---

## 4. Règles anti-triche

1. **Une spec figée est figée.** Modifier une spec après avoir vu ses résultats crée
   une nouvelle expérience et consomme du budget. Le dépôt garde les deux.
2. **Tout ce qui est lancé est enregistré**, y compris les échecs, y compris les
   plantages. Une expérience non publiée qui a touché les données est une fraude
   envers soi-même.
3. **Aucun chiffre sans mesure.** Toute valeur avancée dans un rapport doit être
   reproductible par `python3 -m engine.run`. Une estimation est marquée comme telle.
4. **Le silence n'est pas un succès.** Une porte non testée est une porte échouée.
5. **Pas de p-hacking par le choix des coûts.** Le modèle de coûts est fixé dans
   `engine/costs.py` et ne se négocie pas par expérience.

---

## 5. Ce que ce dépôt ne peut pas faire

À écrire noir sur blanc, parce que l'auto-illusion commence toujours ici :

- Des bougies OHLC ne contiennent ni carnet d'ordres, ni flux, ni calendrier. Une
  absence d'edge trouvé ici n'est pas une preuve qu'il n'y en a pas.
- Un backtest n'a ni la latence, ni l'exécution, ni le broker réel. Le seul juge de
  ces trois-là est G7.
- Le résultat le plus probable de ce protocole, honnêtement, est : **aucune
  stratégie ne passe**. C'est un résultat, pas un échec. L'avantage recherché ici
  est le process, pas un bot.
