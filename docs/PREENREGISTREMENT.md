# Préenregistrer une expérience

Créer un nouvel identifiant et un dossier contenant `spec.yaml` et `G0.json`, avant toute lecture de résultats. Les YAML historiques restent archivés ; ils n'ont pas automatiquement le nouveau préenregistrement requis.

Le JSON contient :

```json
{
  "spec_hash": "SHA-256 complet de la spec effective",
  "hypothesis": "Hypothèse falsifiable, sans résultat de backtest",
  "mechanism": "Qui supporterait le coût de ce comportement, pourquoi et dans quelles conditions",
  "predictions": ["Une conséquence mesurable annoncée avant le test"],
  "abandonment_rule": "Observation qui conduirait à rejeter l'hypothèse",
  "budget_configs": 1,
  "central_params": {},
  "min_trades": 100,
  "walkforward": false
}
```

Il s'agit d'un format, pas d'une hypothèse acceptable en l'état. Les paramètres centraux doivent appartenir exactement à la grille, types compris. Le budget doit correspondre au nombre de configurations. Pour obtenir l'empreinte sans lire de données de marché :

```python
from engine.spec import load
sp = load("experiments/EXP-NOUVELLE/spec.yaml")
assert not sp.validate()
print(sp.hash)
```

Un bootstrap descriptif nécessite également un champ `bootstrap` fixant les quatre options, par exemple `{"sims": 200, "block": 24, "seed": 12345, "remove_drift": false}`. Cet exemple n'est pas un calibrage recommandé ni un nombre de simulations prouvé suffisant. La commande doit reprendre exactement les options du plan. Il n'attribue jamais G4.

Au premier lancement, le moteur conserve le contrat et les coûts avant lecture d'IS. La même expérience ne peut ensuite changer sa spec, ses prédictions, sa configuration centrale ou ses critères. Une évolution crée un nouvel identifiant, en conservant les versions antérieures. Le gel protège le processus ; il ne démontre pas qu'un mécanisme économique est plausible ni qu'une description a été inventée avant toute recherche héritée.
