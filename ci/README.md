# Qualification synthétique et conservation du journal

## Ce que contrôle cette version

Le workflow `.github/workflows/protocole.yml` et la commande locale appellent le même programme, `ci/rejouer_local.py`. Il vérifie :

- la disponibilité d'une base Git explicitement identifiée ;
- la conservation **octet pour octet** de `experiments/ledger.json`, qui reste un historique hérité ;
- la conservation de chaque fichier `experiments/events/*.json` présent dans la base ;
- la validité du nouveau journal avec `engine.journal.read_events` ;
- les seuls tests `tests/test_*_synthetic.py`, sur fixtures et fichiers temporaires.

La base est le commit de base de la PR, le commit précédent indiqué par l'événement push, ou le SHA fourni pour un lancement manuel. Une base absente, nulle, introuvable ou sans ledger est un **échec**, jamais une initialisation implicite. Le nombre de configurations conservées décrit des essais ; il ne mesure pas un nombre de tests statistiquement indépendants.

Le checkout du workflow est limité au code, aux tests et au journal. Les anciens tests `test_mecanismes.py`, les anciens scripts d'audit, les données de marché et les coffres ne sont pas exécutés ou chargés. Aucun contrôle de clé ni déchiffrement n'est inclus. OOS, VAULT et `split=None` restent indisponibles dans le chargeur ; seul un fichier physiquement réservé à IS peut être chargé en dehors de cette qualification synthétique. Aucun jeu IS n'est préparé par la CI.

## Exécution locale

Avec les dépendances installées :

```bash
python3 ci/rejouer_local.py --base <SHA-complet-de-la-base>
```

Pour vérifier uniquement les mécanismes synthétiques :

```bash
python3 ci/rejouer_local.py --tests-only
```

Le second mode **ne valide pas la conservation du journal**. Il n'est pas utilisé par le workflow. Une réussite locale démontre uniquement les contrôles effectivement exécutés dans cet environnement, pas une réussite des actions GitHub de checkout, de préparation de Python ou d'installation des dépendances.

Le journal chaîné et la comparaison Git détectent des modifications par les chemins contrôlés. Ils ne constituent pas un stockage extérieur inviolable : la revue des changements et un contrôle requis à la fusion restent nécessaires. Les propriétés d'isolation et d'ouverture unique d'un futur gardien du coffre ne sont pas qualifiées par cette CI.

## État distant connu

Le run [34766359464](https://github.com/MOUCHEY/moteur-edge-btc/actions/runs/34766359464), documenté le 13 septembre 2026, a été bloqué avant démarrage pour un problème de facturation du compte. Il avait exécuté **zéro étape**. Cette information historique ne permet pas de conclure au statut des futurs runs.

La présente modification n'atteste **aucune exécution distante réussie**. Pour interpréter un futur résultat, vérifier les étapes réellement exécutées, ainsi que la branche et le commit testés. Une validation locale ou un fichier de workflow versionné ne remplace pas cette preuve.

## Intégration de la branche principale du 15 septembre

Les mises à jour jusqu’à `a7fd59d28559a3e0632b4b3d775ea99d2bfcc18e` sont intégrées. Les actions `checkout` et `setup-python` restent en v7, comme dans cette mise à jour. L’historique de la protection de main et de la remise en marche de la CI est conservé dans [la documentation de référence](https://github.com/MOUCHEY/moteur-edge-btc/blob/a7fd59d28559a3e0632b4b3d775ea99d2bfcc18e/ci/README.md).

La nouvelle suite utilise une comparaison explicite avec la base et préserve le snapshot hérité ainsi que chaque événement. Elle remplace le compteur scalaire courant par un journal avec des comptes distincts. Les anciens tests qui parcourent les séries réelles sont conservés mais exclus de cette qualification. Le succès d’une ancienne CI ne vaut pas succès de cette version ; consulter le run associé à son commit. Les règles de protection GitHub n’ont pas été modifiées par ce lot.
