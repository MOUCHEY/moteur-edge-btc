# CI — à activer

`protocole.yml` est le workflow GitHub Actions qui vérifie, à chaque push, que les
mécanismes du protocole tiennent : les 26 tests, la validité de toutes les specs,
le scellement du coffre, et le fait que **le compteur d'essais ne redescend jamais**.

Il n'est pas encore à son emplacement actif. Le jeton GitHub utilisé pour créer ce
dépôt n'a pas la permission `workflow`, et GitHub refuse alors tout fichier sous
`.github/workflows/`.

## Activer (Jeunathan, dans un terminal)

```bash
cd "/Users/admin/BOT TRADING BTC"
gh auth refresh -s workflow
mkdir -p .github/workflows && git mv ci/protocole.yml .github/workflows/protocole.yml
git commit -m "Active la CI du protocole" && git push
```

`gh auth refresh` ouvre le navigateur et demande de confirmer un code : c'est une
autorisation qui doit passer par toi, aucun agent ne peut la donner à ta place.

En attendant, les mêmes vérifications se lancent en local :

```bash
python3 -m unittest discover -s tests -v
```
