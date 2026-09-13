# Contre-exemples des contrôles d'exécution

Référence : `7454850c1328d41bf626766825833a480a5f4139`. Exécution finale : 13 septembre 2026.

Les neuf constats ci-dessous ont été reproduits par [reproduce_controls.py](reproduce_controls.py). La sortie exacte est conservée dans [controls-results.json](controls-results.json), avec date UTC, versions et empreintes du code.

Le script crée des prix fictifs et un registre dans un répertoire temporaire. `data.PROC` est remplacé pendant les appels au chargeur : les libellés IS/OOS désignent exclusivement ce fichier fictif. Pour C02–C05 et C09, le backtest est remplacé par des tableaux de rendements fixes afin d'isoler les contrôles du programme ; le fingerprint et certains calculs secondaires sont également remplacés. Le chargement de la spec fictive, le balayage, la sélection, les écritures de rapports et du compteur restent ceux du moteur. C06–C08 utilisent directement le module de bootstrap avec des nombres générés.

**Aucune série de marché, observation réservée, clé ou donnée chiffrée n'est ouverte.** Aucune performance de stratégie n'est mesurée. Les nombres 136 et 139 de C04 appartiennent à une fixture ; ils ne certifient pas le nombre d'essais historiques.

## Résultats

| ID | Code au commit audité | Observation et portée |
|---|---|---|
| C01 | `engine/data.py:66` | Le timestamp fictif `2023-01-01 00:00 UTC` apparaît à la fois dans IS et OOS. Confirme le défaut de borne identifié par lecture ; ne présume pas la présence de cette barre dans les vrais fichiers. |
| C02 | `engine/run.py:121–137` | Sans preuve de passage préalable, la commande OOS finit avec code 0, évalue les trois valeurs de x et sélectionne x=3 sur ce même OOS fictif. Ce chemin réoptimise au lieu d'imposer une candidate précédemment figée. |
| C03 | `engine/run.py:109`, `172–179` | Deux passages OOS avec `--no-ledger` laissent le registre inchangé et un seul fichier de résultat. Une sentinelle écrite dans le premier rapport est remplacée par le second. |
| C04 | `engine/run.py:156–173` | Avec un compteur fictif initial à 136 et trois configurations nouvelles, l'appel DSR reçoit 136, puis le registre passe à 139. Le test inspecte l'argument transmis ; il n'évalue pas ici la formule DSR. |
| C05 | `engine/run.py:124`, `172–174` | Un échec injecté au chargement se propage sans événement dans le registre. Une tentative commencée et échouée peut donc disparaître de la trace. Ce cas ne signifie pas que trois configurations ont effectivement été mesurées. |
| C06 | `engine/validation/synthetic.py:block_bootstrap` | Un processus fictif de douze rendements positifs puis douze négatifs conserve une prévisibilité après bootstrap par blocs de 24 et retrait de dérive. Le produit moyen du signe retardé par le rendement suivant vaut environ 0,00797. C'est un contre-exemple à la garantie universelle de « bruit sans prévisibilité », sans estimation sur BTC ni conclusion nette de coûts. |
| C07 | `engine/validation/synthetic.py:noise_floor`, `verdict` | Une seule simulation valide de statistique 1 suffit à produire `passe: true` pour une statistique comparée de 2. Aucune exigence de précision, de taille minimale préenregistrée ou de validité du modèle nul n'est imposée. |
| C08 | `engine/validation/synthetic.py:noise_floor` | Les trois évaluations simulées échouent. La sortie indique zéro simulation valide, mais ne conserve ni erreurs individuelles ni compte explicite des échecs. Le diagnostic de l'expérience est perdu. |
| C09 | `engine/run.py:52–53`, `137` | La métrique `p_one_sided` est prise pour un paramètre parce qu'elle commence par `p_`. `meilleure_config` contient `one_sided` en plus du seul paramètre déclaré x. Dans cette fixture, le faux backtest ignore cet argument : l'effet démontré est la contamination du contrat et des paramètres transmis, pas un changement de rendement réel. |

## Reproduction et interprétation

Depuis la racine du dépôt :

```sh
python3 audits/2026-09-11-relais/reproduce_controls.py
```

Le code de sortie 0 signifie que les neuf défauts attendus sont reproduits sur la version auditée. Il ne signifie pas que le moteur est correct. Un contre-exemple qui disparaît après correction doit conduire à un test de non-régression portant sur le comportement attendu ; il ne faut pas modifier le moteur pour conserver le résultat de cet audit.

La première version du contrôle C02 attendait exactement `{"x": 3}`. Elle a échoué parce que `one_sided` apparaissait aussi dans le résultat. L'analyse de cet échec a révélé C09. C02 a ensuite été limité à la sélection de x et au nombre de configurations, et C09 ajouté séparément. La sortie conservée est celle de cette version corrigée de la sonde. Aucun code du moteur n'a été modifié pour obtenir ces reproductions.

## Vérifications attendues après correction

- Des frontières synthétiques disjointes après application du vrai filtre.
- Un refus avant lecture des données si une porte, un gel ou une autorisation manque ; aucun balayage sur la validation finale.
- Une trace durable de chaque tentative, puis de son issue, avec distinction entre tentative, configuration mesurée et simulation ; aucun écrasement des anciennes sorties.
- Un compteur cohérent avec les essais réellement connus, séparant historique incertain et nouveaux événements exacts.
- Des paramètres extraits uniquement du contrat déclaré, distincts des métriques.
- Une procédure statistique préenregistrée et testée sous des modèles nuls explicites, avec conservation des erreurs et précision Monte-Carlo documentée.

Les exigences d'accès au coffre et de correction statistique sont développées dans [COFFRE-ET-CI.md](COFFRE-ET-CI.md) et [STATISTIQUE.md](STATISTIQUE.md).
