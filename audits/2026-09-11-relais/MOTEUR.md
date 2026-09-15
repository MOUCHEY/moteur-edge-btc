# Audit indépendant du moteur — relais du 11 septembre 2026

**Verdict : cette version ne suffit pas à établir un passage de porte fiable.**
Des protections utiles sont présentes, mais des expressions de signal peuvent
consulter le futur, les règles de gel et de comptage ne sont pas imposées, et
plusieurs conventions d'exécution produisent des résultats favorables impossibles.

- Référence auditée : `7454850c1328d41bf626766825833a480a5f4139`.
- Reproductions initiales le 11 septembre ; reprise documentaire et exécution
  du script portable le 13 septembre 2026. L'heure UTC exacte figure dans le JSON.
- Périmètre principal : `engine/backtest.py`, `features.py`, `metrics.py`,
  `spec.py`, `run.py`, `attack.py`, `tests/test_mecanismes.py`.
- Contexte lu : `ASTRA.md`, `PROTOCOLE.md`, ainsi que le code de `engine/data.py`
  et `engine/costs.py` pour vérifier les conventions appelées par le moteur.
- **Aucune donnée réelle, OOS ou du coffre ouverte.** Aucun appel à `load()`,
  `run.main()`, `attack.main()` ou calibration. Aucune suite historique exécutée.
- Aucun code du moteur modifié. Les seules exécutions sont les huit démonstrations
  synthétiques ci-dessous. Elles ne mesurent aucune stratégie de marché.

Les numéros de ligne indiqués sont ceux du commit de référence, pas d'une
éventuelle version corrigée. « Bloquant » signifie que le défaut doit être traité
avant de considérer les résultats concernés comme une preuve de passage ;
« majeur » signifie qu'il peut fausser une mesure ou compromettre sa traçabilité.

## Reproduire les huit constats exécutés

Depuis la racine du dépôt :

```sh
python3 audits/2026-09-11-relais/reproduce_engine.py
```

Le script trouve la racine depuis son propre emplacement ; il fonctionne aussi
depuis un autre répertoire. Il imprime du JSON et n'écrit pas de fichier de
résultats par défaut. Il importe les fonctions du moteur, utilise une graine fixe
et construit ses données en mémoire. [engine-results.json](engine-results.json)
contient la sortie enregistrée lors de cet audit, avec l'heure UTC, les versions
des logiciels et les SHA-256 des fichiers sources audités. Le script ne lit,
pour ces empreintes, que la liste explicite de fichiers de code et de dépendances.
Chaque constat porte `reproduced: true` ou `false` et ses observations. Le code
de sortie vaut 0 seulement si les huit défauts attendus ont été reproduits ;
il vaut 1 sinon. **Un code 0 confirme ici des défauts, pas un moteur correct.**
Après correction du moteur, ce script pourra échouer ou produire une autre sortie :
il documente les reproductions de la version auditée, ce n'est pas une preuve de
correction de versions futures.

### E01 — Le signal peut consulter le futur — bloquant

**Code :** `engine/backtest.py:26–42`, `engine/run.py:125–128`,
`engine/spec.py:66–69`.

L'évaluation utilise `eval` sur des Series pandas et expose aussi NumPy. Le signal
peut appeler `shift(-2)` ou des agrégations portant sur l'ensemble de la série.
La validation syntaxique ne les interdit pas. `assert_causal` n'est appelée que
sur les features construites, avant l'évaluation du signal.

**Mesuré :** `ret_1.shift(-2) > 0` est accepté (`spec_errors: []`) et obtient
196 trades positifs sur 196 sur la fixture aléatoire. Dans cette fixture open=close
et les coûts sont nuls pour isoler la fuite : le signal connaît exactement le
rendement de la position à horizon d'une barre. Il ne s'agit pas d'une performance
de marché. Clé JSON : `future_signal_accepted`.

### E02 — Une fuite d'une barre passe le détecteur — bloquant

**Code :** `engine/features.py:90–107` ; couverture existante
`tests/test_mecanismes.py:49–58`.

Le futur est modifié à partir de `cut`, mais la comparaison utilise
`iloc[:cut-1]`. La valeur de la barre `cut-1`, précisément celle qui peut voir le
premier prix futur avec `shift(-1)`, n'est donc jamais comparée.

**Mesuré :** un builder ajoutant `close.shift(-1)` passe `assert_causal` sans
exception. Le test existant injecte `shift(-5)` et ne couvre pas ce cas.
Clé JSON : `one_bar_future_feature_passes_causality_check`.

**Autres limites constatées par lecture, non reproduites ici :** modification
uniforme de plusieurs colonnes seulement, sans modification de `trades` ou du
calendrier ; comparaison limitée aux paires non-NaN. Ce contrôle par une seule
perturbation n'établit donc pas à lui seul la causalité de tout pipeline.

### E03 — Le bracket utilise une barre située après son timeout — bloquant

**Code :** `engine/backtest.py:94–103`.

La sortie de timeout est fixée à l'open de `cap`, puis la boucle inspecte high/low
de cette même barre, car sa borne supérieure comprend `cap`. Le résultat peut
ainsi profiter d'un mouvement survenu après l'instant prévu de clôture.

**Mesuré :** entrée à 100, horizon d'une barre, open du timeout à 100, high de
cette barre à 103. Le moteur choisit une sortie target à 102 et un gain brut de
200 bps, au timestamp du timeout. La sortie à cet open devait être 100 selon la
convention écrite. Clé JSON : `future_high_on_timeout_bar_used`.

### E04 — Le stop est exécuté à un prix indisponible après gap — majeur

**Code :** `engine/backtest.py:97–103`.

La détection du stop utilise high/low puis renseigne toujours `stop_p`, sans
vérifier si l'open de la barre a déjà dépassé ce prix.

**Mesuré :** position longue entrée à 100, stop à 99, barre suivante open=90,
high=92, low=88 : sortie enregistrée à 99. Aucun prix de cette barre n'atteint 99.
Cela sous-estime la perte. Clé JSON : `gap_stop_filled_above_available_market`.

### E05 — Un gap accepté change l'horizon et sous-estime le portage — majeur

**Code :** `engine/backtest.py:75–108`, `engine/data.py:120–126`,
`engine/costs.py:25–31`.

Les horizons et le portage sont calculés par nombre de lignes. Le contrôle de
données admet une faible proportion de gaps ; le backtest ne filtre pas les
positions qui les traversent. La protection de `forward_return` est distincte et
n'est pas appelée par le backtest.

**Mesuré :** une série de 100 barres avec un seul trou est acceptée par `_sanity`.
Une position traversant 24 heures réelles compte pour une barre horaire. Avec un
portage fixé dans la fixture à 24 bps/jour, le coût est de 1 bp au lieu de 24 bps.
Clé JSON : `gap_trade_accepted_and_undercharged`.

### E06 — Le hash ne scelle pas la spec exécutée — majeur

**Code :** `engine/spec.py:21–42`.

La dataclass est mutable ; le hash repose sur `raw`, tandis que le moteur utilise
les attributs tels que `horizon`. Modifier un attribut après construction peut
donc modifier la stratégie sans modifier son identité publiée.

**Mesuré :** construction avec attributs et `raw` concordants, puis passage de
`horizon` de 1 à 200. Le hash reste identique ; `raw_horizon` reste à 1.
Clé JSON : `runtime_spec_mutation_changes_no_hash`.

Cette preuve n'affirme pas que les fichiers YAML existants ont été modifiés en
secret. Elle démontre que le type présenté comme un contrat figé n'impose pas
l'accord entre son identité et son comportement en mémoire.

### E07 — Des distances bracket négatives passent la validation — majeur

**Code :** `engine/spec.py:57–60`.

La condition vérifie la présence par valeur de vérité, pas la positivité ni la
finitude des distances. Les horizons positifs ne sont imposés que pour le mode
`horizon`, pas pour `bracket`.

**Mesuré :** stop ATR = −1 et target ATR = −2, `validate()` retourne une liste
vide. Les niveaux sont alors inversés par rapport aux conventions annoncées.
Clé JSON : `negative_bracket_distances_accepted`.

### E08 — La première perte disparaît du drawdown — majeur

**Code :** `engine/metrics.py:110–112`.

La série de capitaux cumulés ne contient pas le capital initial. Le premier
capital après trade devient donc artificiellement le premier sommet de référence,
même s'il est inférieur au capital de départ.

**Mesuré :** deux trades de −1000 et +100 bps produisent `max_drawdown: 0.0`,
alors que le premier trade a provoqué une baisse réelle du capital. Avec le
dimensionnement de cette fixture, cette baisse initiale vaut environ 1,124 %.
Clé JSON : `initial_loss_missing_from_drawdown`.

## Constats supplémentaires vérifiés par lecture du code

Ces observations n'ont entraîné aucune exécution de campagne ni ouverture de
données. Les problèmes de statistique, d'accès et de registre doivent aussi être
lus avec les autres rapports du relais.

| ID | Gravité | Code de référence | Constat et conséquence |
|---|---|---|---|
| E09 | Bloquant | `engine/run.py:121–137` | OOS et VAULT empruntent le même balayage de toutes les configurations que IS ; `idxmax(t_net)` sélectionne ensuite la meilleure sur le split examiné. Aucune candidate unique choisie avant l'ouverture n'est exigée. |
| E10 | Bloquant | `engine/run.py:113–137`, `154–183` | Aucune machine de portes ne bloque une ouverture avant G1–G5. G1 ne contrôle pas de configuration centrale, le minimum de 100 trades ou la marge de slippage par rapport au spread ; le programme peut finir avec code 0 sans configuration exploitable. |
| E11 | Bloquant | `engine/run.py:109`, `124–179` | `--no-ledger` permet de mesurer sans compter ; le registre n'est écrit qu'après les calculs. Un plantage antérieur laisse un essai non compté. Un nouveau run avec le même split/hash écrase le rapport précédent. |
| E12 | Majeur | `engine/run.py:156–174` | Le DSR lit le nombre d'essais avant d'ajouter ceux du run ; `max(ancien_total, taille_grille)` n'est pas leur somme. La correction de sélection peut être trop faible. |
| E13 | Bloquant | `engine/attack.py:163–194` | Pas de `sp.validate()` ; les `--params` ne sont pas bornés à la grille gelée ; plusieurs mesures sont réalisées sans registre. Des paramètres différents pour le même split/hash écrasent le même rapport d'attaque. |
| E14 | Majeur | `engine/run.py:63–75` | Les configurations avec t-stat non calculable disparaissent avant le calcul de la part positive. Le voisinage déclaré peut avoir un dénominateur plus petit que la grille soumise. |
| E15 | Majeur | `engine/attack.py:69–80`, `84–105` | L'autocorrélation est affichée mais ne bloque pas l'attaque de chevauchement ; l'intervalle bootstrap rééchantillonne les trades indépendamment. Une dépendance temporelle peut rendre cet intervalle trop étroit. |
| E16 | À cadrer avant campagne | `engine/attack.py:109–149` | Les seuils universels de dégradation après retard et de concentration horaire peuvent éliminer par construction une hypothèse de très courte durée ou précisément horaire. Leur pertinence doit être reliée aux prédictions préenregistrées ; un échec ne démontre pas universellement un artefact. |
| E17 | Majeur | `engine/costs.py:33–35`, `engine/run.py:93–100` | `scaled(2)` multiplie spread/slippage/commission, mais laisse le funding inchangé. « Coûts ×2 » ne signifie donc pas doublement du coût total. |
| E18 | Majeur | `engine/data.py:143–152`, `engine/run.py:139–152`, `requirements.txt:1–5` | Le fingerprint reprend un hash déclaré du manifeste sans vérifier ici les octets chargés. Le rapport ne scelle ni commit du moteur ni versions des bibliothèques ; les dépendances n'ont que des minima. |
| E19 | Bloquant pour séparation stricte | `engine/data.py:66` | La borne `<= hi + 1 jour` est inclusive et peut inclure le premier timestamp du split suivant ; les bornes devraient exprimer des intervalles sans recouvrement. |
| E20 | Bloquant pour ouverture unique | `engine/data.py:73–103` | L'ouverture de coffre est journalisée, mais un fichier d'autorisation persistant permet des ouvertures répétées ; aucune consommation unique n'est imposée dans ce chemin. Constat de code uniquement : le coffre n'a pas été ouvert. |

Un autre défaut de `engine/run.py:137` mélange paramètres et métriques : le filtre
`startswith("p_")` collecte aussi `p_one_sided`, puis le publie comme paramètre
`one_sided`. La preuve et l'analyse de ce cas sont portées par le constat **C09**
du rapport de contrôles du même relais ; il n'est pas ajouté aux huit
reproductions de ce script.

## Limites des tests existants et portée de l'audit

La suite historique lit des données réelles : IS à
`tests/test_mecanismes.py:45–47`, l'ensemble public incluant OOS à `186–192` et
`256–261`, et les octets des fichiers de marché à `208–225`. **Elle n'a donc pas
été exécutée dans cet audit.** Les réussites antérieures ne constituent pas la
preuve que les cas ci-dessus sont couverts.

Le test d'entrée à `91–99` vérifie que le prix enregistré correspond à un open,
sans vérifier que la décision a été prise avec les seules informations alors
disponibles. Le test de gap à `68–73` porte sur `forward_return`, pas sur les
positions de `backtest.run`. Le test de hash à `164–168` vérifie une différence
entre fichiers, pas l'impossibilité de modifier l'objet exécuté. Le test de
splits à `194–199` compare des bornes déclarées sans passer par le masque réel.

L'audit démontre des défauts du moteur et du protocole exécuté. Il ne prouve ni
qu'une stratégie héritée en a profité, ni qu'une stratégie devient valide après
leur correction. Toute correction devra être vérifiée par des tests ciblés,
puis les expériences concernées devront être réévaluées sous une nouvelle
version, avec conservation des résultats antérieurs et de leur statut.
