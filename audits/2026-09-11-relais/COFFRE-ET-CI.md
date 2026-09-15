# Revue du coffre, des découpages et de la CI

Date : 11 septembre 2026 ; références et formulations relues le 13 septembre 2026. Référence examinée : `7454850c1328d41bf626766825833a480a5f4139`.

## Conclusion et périmètre

Le dépôt prévoit un chiffrement des coffres et un contrôle d'autorisation local. **Le code ne garantit toutefois ni l'isolement des agents, ni l'ouverture unique, ni l'éligibilité des observations futures au regard du gel d'une candidate.** Le workflow CI versionné est préparé mais absent de son emplacement actif à cette référence. Ces constats portent sur les mécanismes ; ils ne constituent aucune évaluation de stratégie.

Revue statique des sources et des documents, avec lecture des **seules métadonnées** `vault/SEAL.json` et `vault/FORWARD.json`. Aucun fichier `.enc`, aucune clé, aucune série de marché, aucun fichier `data/processed` et aucune période OOS n'ont été ouverts. Aucun programme de collecte, de scellement ou d'ouverture n'a été exécuté. Aucune permission effective sur une éventuelle clé n'a été inspectée. L'arbre Git a été consulté pour vérifier l'emplacement des workflows et l'absence du dossier de candidates annoncé.

Les sept constats ci-dessous sont des défauts ou limites établis par lecture du code. Les corrections restent **proposées**, non implémentées dans cette revue. P1 désigne un blocage pour prétendre que le protocole est imposé ; P2 désigne un défaut de fiabilité ou de traçabilité à résoudre avant usage du mécanisme concerné.

## 1. P1 — L'ouverture unique n'est pas imposée

**Preuve.** [`engine/data.py`, lignes 73–103](../../engine/data.py#L73-L103) déchiffre puis ajoute une ligne au journal. Le code ne vérifie pas une ouverture antérieure, ne consomme pas l'autorisation et ne lie pas l'ouverture à une candidate. `_vault_authorised()` vérifie uniquement l'existence d'un fichier. `_open_vault()` n'effectue pas lui-même de contrôle d'autorisation.

**Conséquence.** Avec la même autorisation persistante, le chemin normal peut ouvrir le coffre plusieurs fois. La présence d'un journal ne fait pas respecter une ouverture unique. Cela contredit la garantie de [G6](../../PROTOCOLE.md?plain=1#L126-L129).

**Correction suggérée.** Introduire une opération atomique liant autorisation, candidate, empreintes de spec et de protocole, et manifeste de données. Consommer l'autorisation avant toute exposition du clair, conserver un événement durable et refuser les répétitions, y compris concurrentes. Cet état doit relever du gardien isolé décrit au constat 3 ; un état local modifiable ne suffit pas contre des agents disposant du même accès. Tester uniquement avec un coffre fictif dans un répertoire temporaire.

## 2. P1 — La validation du coffre futur et du gel par candidate est absente

**Preuve.** [`vault/SEAL.md`, lignes 56–58](../../vault/SEAL.md?plain=1#L56-L58) annonce une date de gel enregistrée dans `experiments/candidates/` et vérifiée automatiquement. Ce dossier est absent de l'arbre Git examiné. La recherche limitée aux sources `engine/` et aux tests n'a trouvé aucune gestion de `FORWARD`, de ce dossier ou d'une date de gel par candidate. [`engine/data.py`, lignes 78–86](../../engine/data.py#L78-L86) ouvre exclusivement le manifeste `SEAL.json` et les fichiers historiques `BTCUSDT-{interval}.csv.enc`.

La collecte utilise une date générale fixe, [ligne 36](../../data/collect_forward.py#L36), puis récupère depuis cette date, [lignes 71–76](../../data/collect_forward.py#L71-L76), sans heure de gel ni candidate.

**Conséquence.** Le manifeste déclare une collecte future, mais le code ne l'intègre pas à un mécanisme de validation. Des observations postérieures au début du projet ne sont pas nécessairement postérieures au gel d'une candidate. G6 prospectif doit être considéré comme indisponible.

**Correction suggérée.** Définir un enregistrement de gel avec horodatage UTC précis, identité et empreintes de candidate et de protocole. Le validateur isolé devra vérifier l'éligibilité temporelle des barres, un périmètre de données figé, une date de fin ou une règle de taille d'échantillon préenregistrée et l'unicité du test. Aucune ouverture des coffres existants n'est nécessaire pour implémenter et tester ce contrôle sur des données fictives.

## 3. P1 — Une clé hors dépôt ne démontre pas son inaccessibilité aux agents

**Preuve.** [`data/seal_vault.py`, lignes 26–44](../../data/seal_vault.py#L26-L44) prévoit une clé symétrique dans le répertoire personnel, avec droits du propriétaire. Le collecteur utilise cette même clé, [lignes 88–91](../../data/collect_forward.py#L88-L91), et le chargeur sait l'utiliser à partir du chemin du manifeste, [lignes 79–86](../../engine/data.py#L79-L86). Ces scripts ne créent aucune séparation d'identité système ou d'environnement.

**Conséquence.** Le code ne démontre pas l'affirmation de [`vault/SEAL.md`, lignes 65–69](../../vault/SEAL.md?plain=1#L65-L69), selon laquelle les agents ne pourraient retrouver la clé qu'en la demandant à Jeunathan. Ne jamais afficher une clé ne garantit pas qu'un processus exécuté sous la même identité ne puisse la lire. **L'existence et les droits effectifs de cette clé n'ont pas été inspectés.**

**Correction suggérée.** Confier la clé privée, l'autorisation et l'ouverture à un gardien situé dans un environnement inaccessible aux deux agents. La collecte peut chiffrer avec une clé publique uniquement. Décrire entre-temps le dispositif existant comme un chiffrement local avec verrou procédural, dont l'isolation forte n'est pas vérifiée.

## 4. P1 — Le filtre IS admet aussi le timestamp de début de l'OOS

**Preuve.** Les [bornes IS/OOS](../../engine/data.py#L20-L25) sont respectivement `2022-12-31` et `2023-01-01`. Le [filtre ligne 66](../../engine/data.py#L66) conserve `ts <= borne_finale + 1 jour`. L'IS inclut donc le timestamp `2023-01-01 00:00 UTC`, également début de l'OOS. Le [test existant, lignes 194–199](../../tests/test_mecanismes.py#L194-L199), compare les dates brutes sans appliquer le jour ajouté dans le filtre.

**Conséquence.** Une barre située exactement sur cette frontière est admissible dans les deux ensembles. Le test actuel ne prouve donc pas l'absence de recouvrement réel.

**Correction suggérée.** Utiliser des intervalles semi-ouverts `[début, fin_exclusive)`. Vérifier le filtre réellement employé avec un petit tableau synthétique contenant les timestamps immédiatement avant, sur et après chaque frontière. Cette vérification ne nécessite aucun chargement de données de marché.

## 5. P1 — Le workflow CI versionné est inactif et le compteur peut réussir sans vérification

**Preuve.** L'arbre Git contient `ci/protocole.yml` et les modèles d'issues, mais aucun workflow sous `.github/workflows/`. [`ci/README.md`, lignes 7–9](../../ci/README.md?plain=1#L7-L9), indique explicitement cette inactivité. Dans le workflow préparé, [`actions/checkout@v4`, ligne 17](../../ci/protocole.yml#L17), ne configure pas de profondeur d'historique supplémentaire. Le contrôle du compteur tente ensuite `HEAD~1` et transforme toute exception en succès, [lignes 69–75](../../ci/protocole.yml#L69-L75).

**Conséquence.** Dans un checkout superficiel limité à un commit, l'ancêtre recherché n'est pas disponible et la comparaison est ignorée. Même avec un historique suffisant, comparer uniquement le total à `HEAD~1` ne détecte pas la suppression d'événements conservant le total, ni une baisse effectuée plusieurs commits avant le dernier. La présence d'un workflow réussi ne rend pas non plus son passage obligatoire à la fusion sans règle correspondante. Ces limites sont établies par le fichier préparé ; aucun état d'exécution distant n'a été consulté ici.

**Correction suggérée.** Activer le workflow lorsque la permission GitHub nécessaire est disponible ; récupérer une base de comparaison identifiée avec un historique suffisant et refuser son absence hors véritable initialisation. Contrôler la conservation des événements historiques, puis recalculer les totaux. Prévoir que ce contrôle soit requis à la fusion. Les permissions GitHub, les règles de protection effectives et d'éventuels contrôles externes au dépôt n'ont pas été examinés dans cette revue.

## 6. P2 — La collecte future réécrit toute l'histoire sans contrôle de conservation

**Preuve.** [`data/collect_forward.py`, lignes 75–106](../../data/collect_forward.py#L75-L106) retélécharge depuis la date générale de gel, remplace le fichier chiffré puis met à jour le manifeste. Il n'y a pas de vérification de conservation de l'ancien préfixe, de révision du fournisseur ou de continuité des nouvelles barres. Les écritures du fichier chiffré et du manifeste ne forment pas une transaction.

**Conséquence.** Une collecte peut remplacer des observations antérieures sans événement de révision explicite. Une interruption entre les écritures peut désynchroniser un fichier et ses métadonnées. L'empreinte du nouvel état n'explique pas le changement par rapport au précédent.

**Correction suggérée.** Conserver des lots chiffrés immuables, identifiés par intervalle temporel et empreinte, et les relier dans un manifeste publié atomiquement. Faire apparaître les lacunes et révisions comme événements explicites. Le collecteur isolé doit vérifier la cohérence sans communiquer les observations aux agents.

## 7. P2 — Le scellement n'est ni idempotent ni transactionnel

**Preuve.** [`data/seal_vault.py`, lignes 49–62](../../data/seal_vault.py#L49-L62), initialise un manifeste vide et saute les séries ne contenant plus de partie secrète ; la [ligne 95](../../data/seal_vault.py#L95) écrit tout de même ce nouveau manifeste. Relancé sur les fichiers déjà coupés, le script peut donc remplacer `SEAL.json` par un manifeste avec `series: []`, tout en laissant les coffres existants. Les [lignes 68–81](../../data/seal_vault.py#L68-L81) remplacent en outre la série publique avant que le chiffrement et sa sauvegarde aient réussi.

**Conséquence.** Une relance ordinaire peut détacher les coffres de leurs métadonnées. Une interruption ou un échec de chiffrement peut laisser un état partiellement modifié.

**Correction suggérée.** Refuser un rescèlement si un manifeste existe, sauf migration explicitement préparée. Produire et vérifier tous les fichiers temporaires avant remplacement atomique ; préserver les données source jusqu'à confirmation. Vérifier ces scénarios avec des fichiers synthétiques uniquement.

## Écarts documentaires connexes

- [`PROTOCOLE.md`, lignes 33–42](../../PROTOCOLE.md?plain=1#L33-L42), décrit encore le coffre historique comme coffre du projet, alors que [`vault/SEAL.md`, lignes 20–41](../../vault/SEAL.md?plain=1#L20-L41), distingue H et F et reconnaît l'historique déjà exploré. Les règles G6 doivent être réconciliées avec cette distinction.
- [`vault/SEAL.md`, ligne 86](../../vault/SEAL.md?plain=1#L86), annonce zéro barre future ; les **métadonnées uniquement** de [`vault/FORWARD.json`, lignes 3–17](../../vault/FORWARD.json#L3-L17), déclarent déjà 11 barres en 1 h et 47 en 15 min. Leur contenu n'a pas été examiné.
- La promesse « tout » dans la [ligne 29 de `vault/SEAL.md`](../../vault/SEAL.md?plain=1#L29) sur les défauts détectés par le coffre futur doit être retirée : un test fini ne démontre pas cette exhaustivité.
- Le [contrôle de coffre de la CI, lignes 51–61](../../ci/protocole.yml#L51-L61), vérifie un chemin, l'absence d'autorisation et des fichiers non vides. Il ne vérifie ni isolation effective, ni empreintes chiffrées, ni coffre futur, ni ouverture unique.
- [`engine/data.py`, lignes 44–70](../../engine/data.py#L44-L70), ne lie pas le chargement OOS à G5 et ne consomme aucun droit d'ouverture OOS. L'éventuelle protection dans les appelants doit être évaluée dans la revue du moteur ; elle n'est pas établie par ce chargeur.

## Limites et suite proposée

Cette revue n'atteste ni la justesse des séries, ni la conformité des coffres à leurs empreintes, ni leur ouverture passée, ni la sécurité effective de l'hôte. Elle ne juge pas les performances des stratégies. Aucune garantie n'est inférée de l'absence d'accès aux éléments exclus.

Priorité proposée : maintenir G6 indisponible, résoudre les constats P1 avec tests synthétiques, puis faire examiner les modifications par Claude. Les P2 doivent être traités avant toute nouvelle opération de scellement ou collecte reposant sur les garanties annoncées. Aucun de ces travaux ne nécessite d'ouvrir les vrais coffres.
