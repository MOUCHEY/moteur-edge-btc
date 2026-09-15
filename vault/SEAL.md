> Notice du 15 septembre 2026 : état documentaire historique. Les annonces d’ouverture unique, d’isolement et de validation automatique ci-dessous ne sont pas des garanties qualifiées. Les accès et scripts hérités sont désactivés ; voir le [protocole révisé](../PROTOCOLE.md). Aucun coffre ni clé n’a été ouvert pour cette correction.

# Le coffre-fort — et pourquoi il en faut deux

**Gel : 10 septembre 2026.**

## L'objection qui a forcé cette page

Astra, dans son audit de reprise :

> « L'historique 2018 – 8 septembre 2026 a déjà servi à la recherche, y compris
> 2025-2026. […] Changer de fichier, de fournisseur ou d'unité de temps sur les
> mêmes prix ne rétablit pas cette indépendance. »

Elle a raison, et cela vise directement le premier coffre que j'avais scellé.
J'avais pris des données Binance là où les projets précédents utilisaient IC
Markets, et j'aurais pu présenter la période 2025-09 → 2026-08 comme « vierge ».
Elle ne l'est pas : **ce sont les mêmes prix sous-jacents, déjà regardés.**

Changer de fournisseur change la mesure, pas l'événement mesuré.

## Les deux coffres

| | **VAULT-H** (historique) | **VAULT-F** (futur) |
|---|---|---|
| Période | 2025-09-01 → 2026-08-31 | à partir du **2026-09-10** |
| Barres 1h | 8 760 | croît avec le temps |
| État | scellé, chiffré | à collecter |
| Virginité | **NON — période déjà explorée** | **oui, par construction** |
| Ce qu'il prouve | rien de définitif | test final légitime |
| Ce qu'il détecte | un surapprentissage grossier | tout |
| Ouvertures | 1, à titre indicatif | 1, définitive |

### VAULT-H — utile, mais pas un test final

Il n'a jamais été touché *dans ce dépôt*, ce qui a une valeur réelle : une
stratégie construite ici et qui s'effondre dessus est morte, sans discussion.
C'est un filtre efficace **dans un seul sens**.

Mais il ne peut pas anoblir une stratégie. Un succès sur VAULT-H ne signifie pas
« validé sur données inédites » — il signifie « n'a pas échoué sur une période que
d'autres campagnes avaient déjà parcourue ». Toute publication qui présenterait un
succès VAULT-H comme une validation finale serait une faute, et je la traiterai
comme telle.

### VAULT-F — le seul coffre réellement propre

Les observations postérieures au gel n'existaient pas quand la recherche a
commencé. Aucune campagne, ancienne ou nouvelle, n'a pu les regarder. C'est la
seule forme de virginité qui ne repose sur la parole de personne.

Sa contrepartie est le temps : il faut attendre qu'il se remplisse. Collecte par

```bash
python3 data/collect_forward.py     # ajoute les nouvelles barres, chiffrées
```

Un candidat gelé le jour J ne peut être jugé sur VAULT-F qu'avec les barres
postérieures à J — la date de gel de chaque candidate est enregistrée dans
`experiments/candidates/` et vérifiée automatiquement.

## Le dispositif d'isolement

1. **Séparation physique.** Les fichiers publiés ne contiennent que IS + OOS. La
   période scellée en a été retirée, pas seulement ignorée par un filtre.
2. **Chiffrement AES-256-CBC**, PBKDF2, 200 000 itérations.
3. **Clé hors dépôt**, dans `~/.moteur-edge-btc/vault.key`, générée par un
   sous-processus qui l'a écrite directement sur disque. Elle n'est jamais passée
   par une sortie standard, un argument de ligne de commande, ni le contexte d'un
   agent. **Ni Astra ni Claude ne l'ont lue** — et aucun des deux ne peut la
   retrouver autrement qu'en la demandant à Jeunathan.
4. **Autorisation explicite** : l'ouverture exige un fichier
   `vault/OPEN_AUTHORISATION`, non versionné, que seul Jeunathan dépose.
5. **Journal** : `vault/OUVERTURES.log` enregistre chaque déchiffrement.
6. **Témoin d'intégrité** : le SHA-256 du clair est vérifié à l'ouverture. Une
   altération du coffre est détectée.

Ce que ce dispositif **ne fait pas** : empêcher Jeunathan d'ouvrir le coffre.
Il n'est pas conçu contre lui — il est conçu contre l'ouverture distraite, contre
l'agent trop zélé, et contre l'oubli. Une ouverture reste possible ; elle ne peut
plus être accidentelle ni silencieuse.

## État

| | |
|---|---|
| VAULT-H | scellé, **0 ouverture** |
| VAULT-F | 0 barre collectée (gel le 2026-09-10) |
| Empreintes | `vault/SEAL.json` |
