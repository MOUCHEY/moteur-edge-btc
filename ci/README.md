# CI du protocole

## Statut — 13 septembre 2026

| | |
|---|---|
| Workflow | **actif** : `.github/workflows/protocole.yml`, déclenché à chaque push sur `main` |
| Permission `workflow` du jeton | accordée le 13/09/2026 |
| Exécution sur GitHub | **bloquée par GitHub avant démarrage** |
| Vérifications en local | **4 étapes passent** sur `55d3cff` |

Le premier run ([34766359464](https://github.com/MOUCHEY/moteur-edge-btc/actions/runs/34766359464))
porte l'annotation *« The job was not started because your account is locked due to a
billing issue »*. Le runner a exécuté **0 étape** et n'a produit aucun journal.

## À lire avant d'interpréter un run rouge

Tant que ce blocage n'est pas levé, **chaque push produit un run en échec qui n'a rien
exécuté**. Un run rouge ne signale donc pas un défaut du protocole.

Avant de conclure quoi que ce soit, vérifier le nombre d'étapes réellement exécutées :

```bash
gh run view <id> --json jobs -q '.jobs[] | "\(.name): \(.steps|length) etapes"'
```

`0 etapes` = le job n'a pas démarré. Seul un run avec des étapes exécutées dit quelque
chose du code.

## Ce que je ne sais pas

La cause du blocage de facturation. Le jeton utilisé ne donne pas accès aux
informations de facturation du compte. C'est à régler par le titulaire du compte, sur
`github.com/settings/billing`.

## En attendant : rejouer localement

```bash
python3 ci/rejouer_local.py
```

Le script lit les commandes **dans le fichier du workflow** et les exécute une par une.
Ce qui passe en local est exactement ce que GitHub aurait lancé.
