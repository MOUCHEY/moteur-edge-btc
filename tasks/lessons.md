# Leçons — moteur EDGE RENTABLE / BTC

## 2026-09-10 — Binance a changé l'unité des timestamps EN COURS DE SÉRIE

**Symptôme :** 81,6 % de « gaps » détectés sur 9 ans de données Binance, et des
horodatages en **1970**.

**Cause :** les dumps `data.binance.vision` encodent `open_time` en millisecondes
avant 2025 et en **microsecondes** après. Détecter l'unité globalement
(`"us" if ot.max() > 1e15 else "ms"`) applique µs à toute la série et écrase toutes
les dates antérieures en 1970.

**Correction :** trancher **ligne par ligne**. Un horodatage 2017-2026 vaut ~1,5e12
en ms et ~1,5e15 en µs ; le seuil 1e14 les sépare sans ambiguïté.

**Ce qui a sauvé la mise :** un garde-fou qui refuse une série avec > 2 % de gaps.
Sans lui, la recherche tournait sur des données silencieusement corrompues.

## 2026-09-10 — Un hash de données ne doit jamais porter sur une re-sérialisation

**Symptôme :** le test d'intégrité échouait sur des données parfaitement intactes.

**Cause :** `quote_volume` atteint ~2e8 avec 8 décimales, soit 17 chiffres
significatifs — au-delà de ce que float64 restitue exactement. **Mesuré : 315
lignes sur 70 357** ne font pas un round-trip `to_csv(float_format="%.8f")` → `read_csv`
fidèle.

**Correction :** hasher les **octets décompressés** du fichier, jamais le résultat
d'une re-sérialisation pandas.

**Corollaire rencontré :** deux scripts qui sérialisaient différemment le même
fichier ont produit deux hashes de référence divergents, sans aucune alarme. Un
test de concordance entre les deux manifestes est désormais en place.

## 2026-09-10 — Le sens du biais de taille de blocs ne se devine pas

**Attente courante :** des blocs plus longs que l'horizon préservent la structure
testée, donc le plancher de bruit sort **trop haut** et le test devient trop
conservateur.

**Mesuré, l'inverse :** blocs 168 h → p95 = **+0,60** ; blocs 24 h → p95 = **+1,67**.
Les blocs longs donnent un test **plus permissif**.

**Pourquoi :** la structure préservée par les blocs longs était *défavorable* à la
stratégie testée (BTC porte du momentum, la stratégie pariait sur le retour à la
moyenne). Préserver la structure rendait les séries synthétiques hostiles.

**Règle :** le sens du biais dépend du signe de la relation entre structure
préservée et stratégie. Toujours déclarer la taille de blocs et en publier au moins
deux.

## 2026-09-10 — python.org sur macOS : urlopen échoue là où curl passe

`CERTIFICATE_VERIFY_FAILED` sur des URL parfaitement valides : le trousseau système
n'est pas câblé à OpenSSL. Correction : `ssl.create_default_context(cafile=certifi.where())`.

## 2026-09-10 — Un test qui ne peut pas échouer ne prouve rien

Le détecteur de fuite de lookahead a été validé en lui **donnant une vraie fuite à
attraper** (`close.shift(-5)`). Ce test a immédiatement révélé un défaut : le
détecteur ne pouvait pas contrôler une feature ajoutée hors du builder — il plantait
sur `KeyError` au lieu de refuser proprement. Une feature non vérifiable lève
désormais.

## 2026-09-10 — Corriger une affirmation publiée plutôt que la laisser vivre

J'avais écrit dans une issue GitHub que notre détecteur serait désactivé sous
`python -O`. **Faux :** `raise AssertionError` n'est pas supprimé par `-O`, seul le
mot-clé `assert` l'est. Vérifié par exécution, puis l'issue a été corrigée
explicitement plutôt que réécrite en silence.

## 2026-09-10 — Scope `workflow` manquant : le push est clair, l'API ment

**Symptôme au push :** `refusing to allow an OAuth App to create or update workflow
.github/workflows/protocole.yml without 'workflow' scope`. Message explicite.

**Symptôme via l'API Contents :** `{"message":"Not Found", "status":"404"}` sur
`PUT repos/:owner/:repo/contents/.github/workflows/...`. **Le 404 masque un refus de
permission**, pas un chemin erroné — et fait perdre du temps à vérifier le chemin.

**Il n'y a pas de contournement.** Ni le push, ni l'API Contents ne créent un fichier
sous `.github/workflows/` sans le scope. Seul `gh auth refresh -s workflow` le donne,
et c'est un flux OAuth interactif : un agent ne peut pas l'accorder à la place de
l'utilisateur.

**Ce qu'on peut faire en attendant :** garder le workflow hors de `.github/workflows/`,
et **rejouer ses étapes localement** en extrayant les blocs `run:` du YAML. Ça valide
la logique avant activation.

**Deux pièges du YAML de workflow repérés au passage :**
- `on:` est parsé en booléen `True` par YAML 1.1 — chercher la clé `True`, pas `"on"`.
- Le runner fournit `python`, pas un Mac. Écrire `python3` rend le workflow rejouable
  à l'identique des deux côtés.
