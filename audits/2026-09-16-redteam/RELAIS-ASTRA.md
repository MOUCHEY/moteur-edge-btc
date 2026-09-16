# Relais Claude → Astra — revue red team de la PR #8

**Commit examiné : `173ab068c85150811b2569013e49fec917c9f3c3`** (tête de la PR #8).
Revue du 16 septembre 2026. Rapport complet : `audits/2026-09-16-redteam/README.md`.

## En une phrase

Le socle est nettement plus solide qu'au 10 septembre ; **cinq défauts sont reproduits**,
dont deux touchent des garanties que la qualification annonce comme acquises, et la
première expérience IS reste impossible parce que le jeu IS n'existe pas.

## Ce que je confirme, et qui ne se rediscute pas

Tu peux considérer ces points comme tenus, je les ai vérifiés et non supposés :

- 102 tests synthétiques verts localement, CI distante verte.
- `run`, `attack`, `calibrate` refusent OOS et VAULT **avant tout accès disque** ; le
  chargeur refuse une seconde fois ; `_open_vault` ne déchiffre rien.
- Le gel du contrat est **réellement atomique** : j'ai reproduit le refus d'un G0 modifié.
- Conventions d'exécution pessimistes et explicites (timeout, gap, barre ambiguë, horizon
  terminal, série discontinue).
- Capital initial inclus, ruine absorbante.
- Aucun rapport ne présente une stratégie comme validée.
- Le journal écrit `null` là où le chiffre est inconnu, au lieu d'inventer une précision.
  C'est la bonne décision et elle doit le rester.

## Les cinq défauts, par ordre d'urgence

Reproduction unique pour tous :

```sh
python3 audits/2026-09-16-redteam/reproduce_findings.py --root <racine au commit 173ab068>
```

### A1 · moyenne · `engine/journal.py:187` et `:50`

Supprimer les fichiers d'événements **non encore commités** annule le gel du
préenregistrement. J'ai gelé un contrat A, obtenu le refus attendu pour un contrat B, puis
effacé le répertoire : le contrat B est alors **accepté**, et `read_events` considère le
journal tronqué comme une chaîne valide.

La chaîne détecte une suppression *au milieu*, jamais une troncature *de la fin*. La CI ne
compense que pour les événements présents dans la base commitée.

**Attendu** : un ancrage que la suppression ne peut pas effacer — par exemple un fichier
commité portant le dernier `sha256` et le nombre d'événements, vérifié au démarrage, qui
refuse un journal plus court que l'ancre. Et une CI qui exige, pour chaque rapport publié,
la présence de ses événements.

### A2 · moyenne · `ci/rejouer_local.py:49`, `.github/workflows/protocole.yml:27`

`verify_history` ne compare ni les rapports publiés (`experiments/*/results/**`) ni
`experiments/HISTORIQUE.json` — ils ne sont même pas dans le checkout partiel. J'ai
supprimé un rapport commité et réécrit `HISTORIQUE.json` : la CI **accepte**.

**Attendu** : étendre la comparaison octet pour octet à ces chemins et les inclure dans le
sparse-checkout. Un rapport présent dans la base et absent du head doit faire échouer.

### A3 · moyenne · `engine/features.py:114`

`assert_causal` accepte une fuite confinée à des lignes rares. Sur 83 barres, un builder
qui lit `close(t+1)` une ligne sur sept contamine 12 lignes ; les cinq coupes par défaut
`[1, 20, 41, 62, 82]` tombent toutes à côté.

Les fuites uniformes sont bien attrapées — tu les as testées. C'est la fuite
*conditionnelle* qui passe.

**Attendu** : davantage de coupes, tirées avec une graine fixée et déclarée, plutôt que
cinq positions déterministes.

### A4 · faible à moyenne · `engine/expressions.py:73`

La substitution de paramètre n'est pas parenthésée : `"x > {p} ** 2"` avec `p = -2.0`
devient `x > -2.0 ** 2`, que Python évalue à **−4.0**. Un contrat gelé et hashé peut donc
signifier autre chose que ce que son auteur a préenregistré — le hash gèle le texte, pas
l'intention. Les seuils négatifs sont naturels ici (z-scores).

**Attendu** : entourer chaque substitution de parenthèses.

### A5 · faible · `engine/data.py:108`, `engine/features.py:51`

Un CSV IS sans `taker_buy_base` passe `_sanity`, puis `features.build` lève `KeyError`, que
`run.main` n'attrape pas. Trace d'exception au lieu d'un refus lisible.

**Attendu** : exiger dans `_sanity` les colonnes utilisées par `features.build`.

## Trois soupçons, que je n'ai pas démontrés

- `G1_descriptive_pass` (`run.py:80`) : nom qui invite à lire « porte franchie ».
- `dd_p95` (`montecarlo.py:57`) contient le 5<sup>e</sup> centile, donc les pires 5 %.
- `t_net` et `p_one_sided` supposent des trades indépendants, et G1 s'appuie dessus. Je
  n'ai pas mesuré l'ampleur du biais.

## Le vrai blocage n'est pas dans le code

`data/processed/IS/BTCUSDT-1h.csv.gz` **n'existe pas**. Le chargeur exige un fichier
physiquement dédié à IS et refuse les anciens fichiers mixtes, toujours présents.

Cette préparation est l'étape risquée : découper le fichier existant suppose de le lire, or
il contient OOS. Elle demande un script versionné et préenregistré qui ne produit que la
fenêtre IS, publie l'empreinte du fichier produit, et ne laisse aucune sortie dérivée
d'OOS. Elle mérite sa propre revue avant usage.

## Ordre que je propose

1. **A1**, sinon le gel du préenregistrement tient tant que personne n'efface un répertoire.
2. **A2**, sinon « les résultats sont conservés » n'est vérifié par aucune machine.
3. **Préparation qualifiée du jeu IS**, avec sa revue.
4. A4, puis A3 avant la prochaine modification de `features.py`, puis A5.

Ensuite seulement : préenregistrer une hypothèse G0 avec un mécanisme réel.

## Ce que cette revue n'autorise pas

Ni validation finale, ni ouverture de coffre, ni argent réel. G4 à G7 restent non
qualifiées ou indisponibles. Une expérience IS qui « passerait » G1 resterait un diagnostic
descriptif, conditionnel à des coûts jamais mesurés.

Je n'ai corrigé ni le moteur ni aucune stratégie, et je n'ai pas fusionné la PR. Si tu
contestes un constat, cite la version et une preuve reproductible : une réfutation solide
est un résultat utile.
