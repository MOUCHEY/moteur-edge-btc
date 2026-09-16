# Revue red team de la PR #8 — 16 septembre 2026

**Commit examiné : [`173ab068c85150811b2569013e49fec917c9f3c3`](https://github.com/MOUCHEY/moteur-edge-btc/commit/173ab068c85150811b2569013e49fec917c9f3c3)**, tête de la
[PR #8](https://github.com/MOUCHEY/moteur-edge-btc/pull/8) (`astra/qualification-moteur-20260913` → `main`, 50 fichiers, +4218/−1298).

**Verdict : le socle est nettement plus solide qu'au 10 septembre. Cinq défauts sont
reproduits, dont deux qui touchent des garanties annoncées. Aucun ne justifie de rejeter
la PR ; deux doivent être réglés avant la première expérience IS préenregistrée.**

Revue conduite sans aucune donnée de marché réservée, sans ouverture de coffre ni de clé,
sans réseau, et sans exécuter la suite historique. Seuls les 102 tests synthétiques ont
été lancés. Aucune correction du moteur n'a été apportée ; la PR n'a pas été fusionnée.

## Ce que la revue confirme

Vérifié, pas supposé :

- Les **102 tests synthétiques passent** localement sur ce commit (`Ran 102 tests ... OK`),
  et la CI distante est verte ([run 35025058786](https://github.com/MOUCHEY/moteur-edge-btc/actions/runs/35025058786)).
- **`run`, `attack` et `calibrate` refusent OOS et VAULT** avant tout accès disque, et le
  chargeur refuse une seconde fois (`engine/data.py:50`, `engine/research.py:20`).
  `_open_vault` lève sans déchiffrer. Aucun fichier local d'autorisation ne lève le verrou.
- Le **gel du contrat est atomique** : comparaison et écriture sous le même verrou
  (`engine/journal.py:187`), et il bloque réellement un G0 modifié — je l'ai reproduit.
- Les **conventions d'exécution sont pessimistes et explicites** : timeout à l'ouverture
  sans high/low de sa barre, stop franchi à l'ouverture exécuté à cette ouverture, cible
  sur gap sans amélioration de prix, priorité au stop sur barre ambiguë, horizon terminal
  incomplet exclu et compté, série discontinue refusée avant tout signal.
- L'**interpréteur d'expressions** valide l'AST complet avant toute opération : ni
  attribut, ni indexation, ni appel hors `abs`, et les valeurs non finies suppriment la
  ligne, y compris sous négation.
- Le **capital initial est inclus** et la **ruine est absorbante** (`metrics.equity_path`).
- Le **journal publié dit `null`** là où le chiffre est inconnu, au lieu d'inventer une
  précision : `historical_unique_trials`, `independent_trials`, recouvrement des
  déclarations 120 et 16.
- Aucun rapport ne présente une stratégie comme validée : `strategy_validated: false`,
  `passe_G5: False`, `verdict.passe: False`, `qualified_null: False`, et les seuils
  génériques d'`attack.py` sont renommés `condition_descriptive`.

## Défauts démontrés

Reproduction : `python3 audits/2026-09-16-redteam/reproduce_findings.py --root <racine au commit examiné>`
(sortie enregistrée dans [results.json](results.json) ; **code de sortie 0 = défauts reproduits**, jamais « moteur validé »).

### A1 — Tronquer le journal annule le gel du préenregistrement · gravité **moyenne**

**Fichier** : `engine/journal.py:187-193` (`bind_contract`), `engine/journal.py:50-72` (`read_events`).

**Contre-exemple (R3)** : geler le contrat A pour `EXP-9999` ; un contrat B est bien
refusé. Supprimer les fichiers d'événements — jamais commités — puis geler B : **accepté**,
et `read_events` considère le journal tronqué comme une chaîne valide.

**Pourquoi la chaîne ne le voit pas** : elle lie chaque événement au précédent et impose
`sequence == rang`. Supprimer un événement *au milieu* est détecté ; supprimer **toute la
fin**, ou la totalité, laisse une chaîne parfaitement cohérente. La CI ne compense que
pour les événements **présents dans la base commitée** (`ls-tree <base> experiments/events`) :
les événements créés depuis la base ne sont comparés à rien.

**Conséquence** : la réponse à « peut-on encore modifier une expérience après avoir vu ses
résultats ? » est **oui**, dans la fenêtre entre deux commits, sans laisser de trace. C'est
exactement le geste que G0 doit rendre impossible.

**Comportement attendu** : un ancrage que la suppression ne peut pas effacer — par exemple
un fichier d'ancrage commité portant le dernier `sha256` et le nombre d'événements, vérifié
au démarrage et refusant un journal plus court que l'ancre ; et une CI qui exige, pour
chaque rapport publié, la présence des événements correspondants.

**Nuance honnête** : `PROTOCOLE.md` reconnaît ne pas protéger contre un utilisateur
capable de réécrire le dépôt. Ici il ne s'agit pas de réécrire le dépôt, mais d'effacer
des fichiers locaux non commités — un geste ordinaire, non couvert par cette réserve.

### A2 — La CI ne protège ni les rapports publiés ni `HISTORIQUE.json` · gravité **moyenne**

**Fichier** : `ci/rejouer_local.py:49-74` (`verify_history`), `.github/workflows/protocole.yml:27-38` (sparse-checkout).

**Contre-exemple (R4)** : dépôt temporaire dont la base contient un rapport publié, un
`HISTORIQUE.json` et un événement. Supprimer le rapport, réécrire `HISTORIQUE.json`, créer
puis supprimer un événement postérieur à la base : `verify_history` **accepte**.

**Cause** : la comparaison octet pour octet ne porte que sur `experiments/ledger.json` et
sur les chemins listés sous `experiments/events` **dans la base**. Les rapports
(`experiments/*/results/*.json`) et `HISTORIQUE.json` ne sont ni comparés, ni même présents
dans le checkout partiel de la CI.

**Conséquence** : `PROTOCOLE.md` annonce que les sorties sont conservées et que
`HISTORIQUE.json` corrige le ledger. Un résultat gênant peut disparaître, et la correction
du compteur être réécrite, sans que la CI échoue.

**Comportement attendu** : étendre la comparaison à `experiments/HISTORIQUE.json` et à
`experiments/*/results/**`, et les inclure dans le sparse-checkout. Un rapport présent dans
la base et absent du head doit faire échouer la CI.

### A3 — `assert_causal` laisse passer une fuite confinée à des lignes rares · gravité **moyenne**

**Fichier** : `engine/features.py:114-126` (coupes par défaut).

**Contre-exemple (R2)** : builder qui remplace la valeur par `close(t+1)` **uniquement** sur
les lignes dont la position vaut 3 modulo 7. Sur 83 barres, les coupes par défaut sont
`[1, 20, 41, 62, 82]` : aucune ne tombe sur une ligne contaminée. **12 lignes** contiennent
réellement le futur, et `assert_causal` **accepte**.

**Conséquence** : c'est le seul garde-fou automatique contre une fuite introduite plus tard
dans `features.py`. Il attrape les fuites uniformes (`shift(-1)`, agrégat global, backfill —
tous testés) mais pas une fuite conditionnelle.

**Comportement attendu** : tirer davantage de coupes, à graine fixée et déclarée, plutôt
que cinq positions déterministes ; ou comparer le préfixe complet sur un balayage de coupes
couvrant chaque ligne au moins une fois sur les petits échantillons.

**Nuance** : la docstring annonce « this diagnostic is not a mathematical proof ». La
réserve est donc dans le code — mais `docs/QUALIFICATION-2026-09-15.md` présente E01–E02
comme corrigés sans la rappeler.

### A4 — La substitution de paramètre n'est pas parenthésée · gravité **faible à moyenne**

**Fichier** : `engine/expressions.py:73` (`parts.append(repr(clean[field]))`).

**Contre-exemple (R1)** : `"x > {p} ** 2"` avec `p = -2.0` devient `x > -2.0 ** 2`. Python
évalue `-(2.0**2) = -4.0` au lieu de `(-2.0)**2 = 4.0`. Signal obtenu `[True, True, True]`,
attendu `[False, False, True]`.

**Conséquence** : un contrat gelé et hashé peut signifier autre chose que ce que son auteur
a préenregistré. Le hash gèle le texte, pas l'intention. Le cas se limite à un paramètre
négatif combiné à `**`, mais les seuils négatifs sont naturels ici (z-scores).

**Comportement attendu** : entourer chaque substitution de parenthèses.

### A5 — Colonne de flux absente : exception hors du contrat d'erreurs · gravité **faible**

**Fichier** : `engine/data.py:108-110` (colonnes requises), `engine/features.py:51`, `engine/run.py:110`.

**Contre-exemple (R5)** : un CSV IS par ailleurs valide sans `taker_buy_base` passe
`_sanity`, puis `features.build` lève `KeyError`, que `run.main` n'attrape pas
(`except (ResearchError, ValueError, RuntimeError)`).

**Conséquence** : trace d'exception au lieu d'un refus lisible. Sans gravité pour la
validité des résultats — le run échoue — mais le message n'oriente pas vers la cause.

**Comportement attendu** : exiger dans `_sanity` les colonnes que `features.build` utilise,
ou lever `DataError`.

## Soupçons, non démontrés

- **`G1_descriptive_pass`** (`engine/run.py:80`) agrège quatre booléens sous un nom qui
  invite à lire « porte franchie ». Le protocole veut du descriptif. Question de
  formulation, pas de calcul.
- **`dd_p95`** (`engine/validation/montecarlo.py:57`) contient le 5<sup>e</sup> centile,
  c'est-à-dire les pires 5 %. Le commentaire le dit ; le nom dit l'inverse.
- **Dépendance entre trades** : `t_net` et `p_one_sided` supposent des observations
  indépendantes. C'est marqué `descriptif_conditionnel`, mais G1 s'appuie dessus.
  Je n'ai pas mesuré l'ampleur du biais sur ce moteur.

## Non vérifié

- La qualité scientifique d'une hypothèse future : les contrôles valident une structure.
- Les coûts réels et l'écart entre Binance spot et l'instrument exécuté (issue #3).
- Le gardien isolé, la collecte par lots et l'ouverture unique : annoncés non implémentés,
  je n'ai donc rien à réfuter.
- Le comportement du moteur sur un vrai fichier IS : **il n'existe pas** (voir ci-dessous).

## Verdict

**Peut-on commencer une première expérience IS préenregistrée ? Pas encore — et le blocage
principal n'est pas un défaut de code.**

`data/processed/IS/BTCUSDT-1h.csv.gz` **n'existe pas** dans ce commit. Le chargeur exige un
fichier physiquement dédié à IS et refuse les anciens fichiers mélangeant IS et OOS, qui
sont toujours présents dans le dépôt. Aucune expérience IS ne peut donc démarrer
aujourd'hui.

Cette préparation est elle-même l'étape risquée : découper le fichier existant suppose de
le lire, or il contient OOS. Elle doit être faite par un script versionné, préenregistré,
qui ne produit que la fenêtre IS, publie l'empreinte du fichier produit, et ne laisse
aucune sortie dérivée d'OOS. Cette étape mérite sa propre revue.

**À régler avant la première expérience IS :**

1. **A1** — sans ancrage externe, le gel du préenregistrement est déclaratif : il tient
   tant que personne n'efface un répertoire.
2. **A2** — sans extension du périmètre CI, « les résultats sont conservés » n'est pas
   vérifié par une machine.
3. La **préparation qualifiée du jeu IS**, avec sa propre revue.

**À corriger sans bloquer** : A4 avant d'écrire un contrat combinant paramètre négatif et
`**` ; A3 avant la prochaine modification de `features.py` ; A5 quand l'occasion se présente.

**Ce verdict n'autorise ni validation finale, ni ouverture de coffre, ni argent réel.**
G4 à G7 restent non qualifiées ou indisponibles, et rien dans cette revue ne change cela.
Une expérience IS qui « passerait » G1 resterait un diagnostic descriptif, conditionnel à
des coûts qui n'ont toujours pas été mesurés.

---

*Revue conduite par Claude (red team). Je ne corrige pas le moteur et ne propose pas de
stratégie : je signale et je m'arrête. Chaque constat ci-dessus est soit reproduit par le
script joint, soit explicitement marqué comme soupçon ou comme non vérifié.*
