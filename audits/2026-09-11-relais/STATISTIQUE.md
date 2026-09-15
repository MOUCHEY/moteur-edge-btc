# Audit méthodologique du relais et d'EXP-0000

**Analyse initiale :** 11 septembre 2026. **Relecture avant publication :** 13 septembre 2026. **Auteur :** Astra, revue indépendante des documents. **Statut :** analyse documentaire effectuée ; résultats de marché non reproduits dans cette revue.

## Décision proposée

**G4 doit rester non qualifiée.** EXP-0000 fournit une étude descriptive utile de sensibilité au rééchantillonnage, mais ne démontre pas encore un contrôle du risque de faux positifs. Le nombre de 136 essais ne constitue pas un minorant vérifié du nombre d'essais uniques ou indépendants. Les neuf variantes négatives ne réfutent pas toute la famille du retour à la moyenne.

Ces constats justifient des corrections du protocole et de ses contrôles avant une nouvelle campagne. Ce rapport ne modifie ni le protocole, ni une candidate, ni les données, ni les résultats historiques.

## Périmètre et preuves

Documents examinés : [RELAIS.md](../../RELAIS.md), [rapport EXP-0000](../../experiments/EXP-0000-calibration/RAPPORT.md), [registre du dépôt](../../experiments/REGISTRE.md) et [ledger](../../experiments/ledger.json). Les deux premières pièces ont d'abord été lues dans les copies transmises par l'utilisateur.

Comparaison avec l'archive Astra du 10 septembre : son `README.md`, section « Les échecs font partie du capital de recherche », et `sources/projet-2/registre-hypotheses.json`. Cette archive est la source héritée déjà nommée dans le ledger du dépôt. Elle indique `all_prior_unique_trials_count: null`, `unique_btc_trial_count_verified: null` et interdit explicitement d'additionner les deux comptes déclarés pour annoncer 136 essais BTC indépendants.

Aucune donnée brute, période OOS ou donnée du coffre n'a été consultée dans cette sous-revue. Les valeurs de performance citées ci-dessous sont celles des rapports de Claude, sans reproduction de ces backtests.

La revue technique parallèle d'Astra a confirmé que le bootstrap reconstruit les clôtures à partir de log-rendements et réapplique des ratios OHLC ; il conserve les dépendances internes aux blocs et le `quote_volume` d'origine. L'objection statistique porte sur les dépendances conservées par cette reconstruction. Les observations de code relèvent de cette revue parallèle ; l'analyse présente porte sur leur interprétation statistique.

## Constats prioritaires

| Identifiant | Priorité | Constat | Portée |
|---|---|---|---|
| S01 | Bloquant G4 | Le modèle nul n'est pas certifié | Le p95 simulé ne suffit pas à fixer une porte de validation |
| S02 | Bloquant toute certification DSR | 136 n'est pas un minorant démontré | Compte unique, périmètre et indépendance restent inconnus |
| S03 | Important | Bonferroni est confondu avec une approximation de maximum gaussien | Erreur mathématique établie dans le rapport |
| S04 | Important | Une grille négative est présentée comme une famille réfutée | Conclusion trop générale et significativité insuffisamment documentée |
| S05 | Important | Les essais réels de calibration influencent la sélection | Leur statut d'instrument ne supprime pas leur traçabilité obligatoire |
| S06 | Condition de validation finale | Le gel de la candidate avant VAULT-F n'est pas démontré par le relais | Vérifier uniquement les métadonnées et contrôles, sans ouvrir les observations |
| S07 | Important | Incertitude Monte-Carlo et interprétation de la dérive | Précision et explication causale excessives |

### S01 — Les blocs historiques ne sont pas du « bruit pur » démontré

Le rapport annonce un balayage sur des séries où l'on saurait qu'il n'y a aucun avantage, puis explique que les blocs de 168 heures conservent une structure défavorable à la règle de retour à la moyenne. Rééchantillonner des blocs peut préserver des relations prédictives internes. Retirer la dérive marginale des rendements ne garantit pas l'absence de rendement conditionnel prévisible à partir des informations disponibles.

Un contre-exemple suffit : le processus stationnaire `r[t] = phi * r[t-1] + epsilon[t]`, avec `0 < phi < 1` et innovations indépendantes centrées de variance finie strictement positive, a une moyenne nulle. Pourtant, la règle `sign(r[t-1])` a une espérance brute positive, `phi * E[abs(r[t-1])]`, et la règle opposée une espérance négative. Retirer la moyenne ne supprime pas cette dépendance ; des blocs peuvent la conserver. Ce contre-exemple est analytique ; il ne décrit pas un processus ajusté aux données BTC.

Le p95 plus faible avec les blocs longs peut donc refléter une structure défavorable conservée. Il n'établit pas le taux de faux positifs d'un test général d'absence d'avantage net. La conclusion « G4 se lit contre le p95 du plancher » est prématurée. La validité d'une méthode dépend de l'hypothèse nulle, du benchmark et de la procédure de sélection qu'elle évalue. Le [Reality Check de White](https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152) fournit une formulation explicite du test de la meilleure alternative rencontrée pendant une recherche contre un benchmark.

**Correction proposée :** qualifier les résultats existants de sensibilité au bootstrap, maintenir G4 non qualifiée, puis préenregistrer la statistique, le benchmark, le modèle nul et le traitement de la sélection. Distinguer les simulations d'un processus dont le mécanisme nul est connu et les tests conjoints sur les performances des variantes avec centrage approprié et conservation des dépendances. Aucun de ces choix ne doit être présenté comme valide sans en vérifier les hypothèses.

**Vérification attendue :** mesurer le taux de faux positifs du processus complet sur plusieurs processus nuls connus, avec incertitude ; inclure un cas centré mais prévisible comme contre-exemple. Préenregistrer les longueurs de blocs et leur usage, sans retenir après coup celle qui permet le passage. Vérifier aussi que les variables utilisées par la stratégie restent cohérentes après reconstruction, notamment si le volume de cotation historique est conservé.

### S02 — 136 est une addition déclarée, pas un minorant vérifié

Le relais et le ledger déduisent 136 de 120 configurations déclarées sur quatre actifs et de 16 combinaisons de base sur quatre actifs. Le registre hérité ne certifie ni les recouvrements, ni les essais BTC uniques, ni le total unique. Des variantes supplémentaires omises ne rendent pas automatiquement cette addition une borne inférieure : des doublons, des recouvrements et la définition du périmètre peuvent agir dans l'autre sens.

La phrase « nos DSR sont optimistes » n'est donc pas établie. Les omissions peuvent rendre une pénalité insuffisante ; traiter des essais corrélés comme indépendants peut la rendre excessive. Le sens net du biais est inconnu. Le [DSR original de Bailey et López de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) distingue notamment le nombre d'essais indépendants, la variance des Sharpe entre essais et les caractéristiques de la série sélectionnée. Un test montrant qu'une valeur baisse lorsque le compteur augmente ne prouve pas la validité statistique de l'ensemble.

**Correction proposée :** conserver les deux événements hérités avec leur provenance, séparer le nombre exact des nouveaux essais du compte historique inconnu, et traiter 136 comme scénario brut déclaré. Ne certifier aucun seuil DSR à partir de ce seul nombre. Cette correction n'autorise pas à effacer la recherche antérieure ou à repartir de zéro.

### S03 — Bonferroni reste valide sous dépendance, pour des p-valeurs valides

Le début du rapport associe « Bonferroni, √(2 ln N) » et rejette ce seuil au motif que les configurations partagent leurs données. Ce sont deux objets différents. Bonferroni utilise un seuil de p-valeur `alpha / N` et l'inégalité de l'union ; il n'exige pas l'indépendance entre tests. La [formulation du NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm) porte sur des événements quelconques. La dépendance peut le rendre conservateur.

`sqrt(2 * log(N))` se rapporte à une approximation de maxima gaussiens, pas au seuil Bonferroni. Cette rectification ne dispense pas d'obtenir des p-valeurs élémentaires valides et de définir la famille de tests et le traitement de l'adaptation.

**Correction proposée :** retirer la confusion de la justification de G4 ; choisir la correction des tests multiples sur ses hypothèses réelles, pas sur un rejet erroné de Bonferroni.

### S04 — Neuf variantes négatives ne réfutent pas la famille

Le résultat descriptif rapporté est précis : neuf configurations, sur un IS particulier, sous un moteur et des coûts supposés particuliers, ont perdu. Le maximum des t-statistiques est −1,46 ; la configuration centrale a une t-statistique de −4,27 et une moyenne nette de −41,3 points de base par trade.

Le maximum −1,46 ne prouve pas que les neuf variantes sont chacune significativement perdantes. La valeur centrale constitue un signal négatif à examiner, mais le rapport ne présente pas de variance temporelle robuste, d'intervalle ni de traitement de la sélection permettant de valider sa qualification statistique. Les conditions d'estimation comptent : [Newey et West](https://www.nber.org/papers/t0055) traitent précisément l'estimation d'une covariance tenant compte de l'hétéroscédasticité et de l'autocorrélation ; une telle méthode doit elle-même être justifiée pour la série et l'estimand retenus.

La formule « cette famille est [...] morte » du relais dépasse ces résultats et rend ambiguë la portée du rejet, alors que le même relais précise ensuite que H2 n'est pas réfutée. Une lecture momentum du BTC est une hypothèse explicative, pas une cause identifiée par cette expérience.

**Formulation proposée :** « Les neuf variantes testées ont perdu sur cet IS, sous les hypothèses du moteur. Leur portée statistique et les causes restent à établir. Cette expérience ne réfute pas H2 ni toute la famille du retour à la moyenne. »

**Vérification attendue :** après qualification du simulateur, intervalle tenant compte de la dépendance temporelle et analyse de concentration des pertes, avec méthode fixée avant nouvelle inspection. Aucun réglage de candidate n'est proposé par cet audit.

### S05 — L'étiquette « calibration » ne retire pas les essais du processus de sélection

EXP-0000 teste neuf variantes sur l'IS réel et utilise leur résultat pour orienter les recherches suivantes. Ces mesures font partie de l'historique de sélection, même si aucune candidate formelle n'est déclarée. Le registre Markdown les mentionne ; le ledger consulté contient toujours `runs: []` et `total_configs: 136`. Cette divergence doit être traitée explicitement.

**Correction proposée :** tracer les neuf configurations distinctes évaluées sur l'IS, toutes leurs exécutions et les décisions qu'elles ont influencées dans le registre canonique. Réexécuter la même configuration ne crée pas automatiquement un nouvel essai indépendant. Tracer séparément les chemins Monte-Carlo ; ils ne représentent pas autant de nouvelles configurations évaluées sur le marché réel. Les choix de modèles nuls, de longueurs de blocs et de méthodes de validation motivés par les résultats sont aussi des décisions de recherche à conserver. Cette distinction n'autorise ni à additionner les simulations au compte des configurations uniques, ni à ignorer l'adaptation de la validation.

### S06 — La séparation historique/futur est utile ; le gel doit être prouvé

Qualifier VAULT-H d'historique déjà consulté est une correction utile. Le relais indique cependant onze premières barres collectées pour VAULT-F tout en demandant encore une hypothèse G0 ; il ne démontre pas qu'une candidate et son protocole de décision ont été gelés avant cette collecte.

Notre règle héritée exige un gel de la candidate et de la décision avant les observations réservées. Un gel du socle logiciel ou d'un calendrier générique ne suffit pas. L'absence d'une preuve dans ce relais n'établit pas à elle seule qu'aucun contrôle n'existe : ce point relève de la revue des métadonnées et permissions.

**Vérification attendue, sans ouverture :** identifiant et empreinte de la candidate, protocole, instant de gel, première observation admissible, échéance fixe, régime d'accès et comportement après incident. À défaut, qualifier la collecte déjà amorcée de préparatoire et ne pas la faire passer pour une validation finale de la future candidate.

### S07 — Incertitude des queues et interprétation de la dérive

Avec 200 simulations, le p95 dépend d'environ dix observations de queue et le p99 d'environ deux. Le maximum 4,03 est un maximum observé dans ces simulations, pas une borne générale. Le seuil 1,67 ne permet pas de déclarer universellement qu'un t-stat de 1,7 est « indiscernable du hasard ».

Le déplacement 1,674 → 1,637 après retrait de dérive décrit une faible sensibilité dans les simulations rapportées. Il ne démontre pas que « la dérive n'explique rien ». Des règles long/short symétriques ne garantissent pas des expositions réalisées symétriques ; la cause du changement de p95 selon la longueur de bloc reste une interprétation.

**Correction proposée :** publier les graines, les statistiques simulées conservées, une incertitude du quantile ou des rangs et un nombre de réplications préenregistré. Rapporter la comparaison avec/sans dérive comme une sensibilité mesurée, avec son incertitude, sans conclure à une annulation générale.

## Conditions avant une nouvelle candidate

1. Qualifier le simulateur et ses métriques dans la revue technique parallèle ; conserver les anciennes sorties avec leur statut antérieur.
2. Corriger la description et la traçabilité de l'historique des essais sans effacement.
3. Préenregistrer puis vérifier une méthode de validation dont l'hypothèse nulle et la sélection sont explicites. Jusqu'à cette preuve, G4 reste non qualifiée.
4. Réserver la validation finale à une candidate, un protocole et une période admissible identifiés ; vérifier l'isolement sans ouvrir les observations.

Ce document fournit des constats et des expériences de qualification à effectuer. Il ne constitue ni un passage de porte, ni une stratégie préenregistrée, ni une autorisation d'accès au coffre ou de négociation.
