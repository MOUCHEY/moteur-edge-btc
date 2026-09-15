# Moteur de recherche de stratégies BTC

Découvrir des hypothèses plausibles, les tester avec un budget fixé, puis tenter de les réfuter. Le résultat peut être qu'aucune stratégie ne survive.

La première correction du socle répond à l'[audit de septembre](audits/2026-09-11-relais/README.md) : signaux ponctuels sans accès au futur, contrats immuables, simulation corrigée, journal obligatoire et refus des validations indisponibles. Astra poursuit la construction sans dépendre de Claude, conformément à la demande de l'utilisateur. Les diagnostics ne sont pas présentés comme une revue indépendante.

## État du projet

- **Disponible :** qualification sur données fictives ; outils de recherche IS avec préenregistrement et journal.
- **À préparer avant une expérience réelle :** fichier IS physiquement séparé, continu et contrôlé ; hypothèse et contrat G0 complets.
- **Non qualifiés :** méthode statistique G4, nombre historique d'essais indépendants, coûts d'exécution réels et gardien du coffre.
- **Bloqués dans le moteur :** OOS, coffres, collecte/scellement hérités et toute promotion finale.
- **Aucune stratégie validée par ce lot.** Les résultats d'EXP-0000 sont conservés comme résultats historiques conditionnels à l'ancienne version.

Le [protocole révisé](PROTOCOLE.md) décrit exactement les règles disponibles et les étapes restantes. [Le journal de qualification](docs/QUALIFICATION-2026-09-15.md) indique les corrections et leur validation.

## Vérifier sans données de marché

```sh
python3 -m pip install -r requirements.txt
python3 ci/rejouer_local.py --tests-only
```

Pour contrôler aussi la conservation de l'historique, fournir le SHA complet de la base de comparaison :

```sh
python3 ci/rejouer_local.py --base 72714d6243c5dc6823d5aabd360a50a6d05ec54f
```

Ces commandes sélectionnent exclusivement `test_*_synthetic.py`. La suite historique `test_mecanismes.py` et les sondes de l'audit initial restent conservées pour provenance ; elles ne constituent pas la suite de non-régression courante. Ne pas lancer une découverte générale de tous les anciens tests : certains lisaient des séries réelles.

## Préparer une nouvelle expérience

Voir [le format G0](docs/PREENREGISTREMENT.md). Une fois le contrat écrit et le fichier IS dédié préparé, la commande de recherche est :

```sh
python3 -m engine.run experiments/EXP-NOUVELLE/spec.yaml --split IS
```

`EXP-NOUVELLE` est un exemple de chemin, pas une expérience déjà créée. Le programme refuse une hypothèse absente, une modification du contrat gelé ou une validation réservée. Il publie un rapport unique et conserve les événements, y compris les échecs. `--no-ledger` n'existe plus.

## Historique et limites

Le [registre](experiments/REGISTRE.md), le [snapshot de provenance](experiments/HISTORIQUE.json) et les événements conservent les essais connus et les incertitudes. **136 n'est pas un total vérifié d'essais uniques ou indépendants.** Les neuf variantes d'EXP-0000 et les simulations sont distinguées.

Un résultat sur bougies et coûts supposés ne prouve ni l'exécution future ni un avantage déployable. Le journal est protégé contre les erreurs ordinaires et vérifié contre Git ; une vraie séparation des accès au coffre reste à construire. La CI historique a été réactivée sur GitHub. La réussite de cette nouvelle qualification doit être vérifiée sur son propre commit, séparément des anciens runs.
