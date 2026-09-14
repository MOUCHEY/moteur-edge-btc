# CI du protocole

## Statut — 13 septembre 2026

| | |
|---|---|
| Workflow | **actif** : `.github/workflows/protocole.yml`, déclenché à chaque push sur `main` |
| Exécution sur GitHub | **fonctionne** depuis le 13/09/2026 (blocage de facturation du compte levé) |
| Premier run réel | [34766511829](https://github.com/MOUCHEY/moteur-edge-btc/actions/runs/34766511829), tentative 2 : 11 étapes, succès, 26 tests |
| Défaut révélé par ce run | le contrôle du compteur était **décoratif sur GitHub** — corrigé, voir plus bas |
| Protection de `main` | **active** : réécriture forcée et suppression refusées, sans exception — vérifié par l'usage |
| Rejeu local | `python3 ci/rejouer_local.py` |

## Le défaut révélé par le premier vrai run

Le run était vert. Il ne l'était pas pour la bonne raison.

`actions/checkout` ne récupère par défaut **qu'un seul commit**. Le contrôle « le
compteur d'essais ne redescend jamais » comparait le compteur avec celui du commit
précédent — qu'il ne voyait donc pas. Il a affiché :

```
pas d'etat precedent comparable ; compteur = 136
```

et il est **passé**. Reproduit dans un clone à un commit : avec le compteur **remis à
zéro**, il passait aussi. Le garde-fou censé empêcher qu'on efface le budget de
recherche ne gardait rien, et la coche verte le masquait.

Localement il fonctionnait, parce que le dépôt local a tout l'historique. Seules les
conditions exactes de GitHub révélaient la cécité.

**Correction :**

1. `fetch-depth: 0` : GitHub récupère tout l'historique.
2. Un clone superficiel fait désormais **échouer** le contrôle. Un garde-fou qui ne voit
   pas ses données ne doit jamais passer.
3. Monotonie vérifiée sur **tout** l'historique du compteur, pas seulement le dernier
   commit : un push de plusieurs commits ne peut plus cacher une baisse.
4. Quatre tests (`GardeFousCI`) rejouent **l'étape exacte du workflow** dans des clones —
   superficiel, saboté, intact. Vérifié contre l'ancienne version : **deux d'entre eux
   échouent** (`fetch-depth` absent, clone superficiel qui passe) — ce sont ceux qui visent
   le défaut. Les deux autres y passent aussi, et c'est attendu : en clone complet,
   l'ancien contrôle détectait déjà une baisse. Ils garantissent que la correction n'a
   cassé ni cette détection, ni le cas normal.

## Protection de `main` — active depuis le 13 septembre 2026

Ruleset `protection-main` : **réécriture forcée et suppression refusées**, **aucune
exception**, administrateur compris. Astra et Claude poussent avec le même compte
propriétaire : une exception pour l'administrateur rendrait la règle inopérante contre
eux.

Vérifié **par l'usage**, pas seulement par la configuration. Le test a été mené sur une
branche jetable protégée par une règle strictement identique, pour ne jamais risquer
`main` :

| Opération | Attendu | Obtenu |
|---|---|---|
| Envoi normal | accepté | accepté |
| `git push --force` | refusé | refusé — `GH013 … Cannot force-push to this branch` |
| Suppression de la branche | refusée | refusée — `GH013 … Cannot delete this branch` |

GitHub confirme que ces deux règles s'appliquent à `main`
(`gh api repos/MOUCHEY/moteur-edge-btc/rules/branches/main`).

### Ce que la protection ne couvre pas

- Le compte propriétaire peut **supprimer ou désactiver la règle elle-même**, par les
  réglages ou par l'API. La protection rend une réécriture de l'historique délibérée,
  elle ne la rend pas impossible.
- Les envois directs sur `main` restent autorisés, sans pull request ni attente de la
  CI. C'est un choix : garder simple le circuit Astra ↔ Claude.

## Interpréter un run rouge

Vérifier d'abord le nombre d'étapes réellement exécutées :

```bash
gh run view <id> --json jobs -q '.jobs[] | "\(.name): \(.steps|length) etapes"'
```

`0 etapes` = le job n'a pas démarré (cas du blocage de facturation du 13/09/2026) : le
run ne dit rien du code.

## Versions des actions — mises à jour le 14 septembre 2026

`actions/checkout@v7` et `actions/setup-python@v7`, qui tournent sur **Node.js 24**. Les
versions précédentes (`v4`, `v5`) visaient Node.js 20, déprécié par GitHub.

Vérifié avant la mise à jour, et pas supposé :

| Point | Constat |
|---|---|
| Node.js utilisé (`runs.using` du `action.yml`) | `node24` pour les deux |
| Runner minimum exigé depuis checkout v5 / setup-python v6 | 2.327.1 — notre runner : **2.337.0** |
| `fetch-depth` en checkout v7 (le garde-fou du compteur en dépend) | présent, même sens : `0` = tout l'historique |
| `python-version` et `cache` en setup-python v7 | présents |
| `pip-install`, retiré en setup-python v7 | non utilisé chez nous |
| checkout v6 : identifiants stockés dans un fichier séparé | sans effet : le workflow ne pousse rien et ne lit que l'historique local |
| checkout v7 : refus des forks en `pull_request_target` / `workflow_run` | sans effet : nous déclenchons sur `push` et `pull_request` |

Les actions sont référencées par tag majeur (`@v7`), comme avant. Les épingler par SHA
complet serait plus sûr contre un tag déplacé ; ce n'est pas fait.
