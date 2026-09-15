# Protocole de recherche — révision du 15 septembre 2026

Cette révision corrige les garanties excessives du socle du 10 septembre à la suite de l'[audit](audits/2026-09-11-relais/README.md). Elle s'applique aux nouvelles exécutions. Les expériences anciennes, leurs résultats et leur protocole restent dans l'historique Git ; aucun succès ancien n'est requalifié automatiquement.

## Organisation

L'utilisateur a demandé de poursuivre sans dépendre de Claude. Astra assure donc les corrections de l'infrastructure et les expériences. Une seconde revue peut intervenir à un jalon important ; l'exécution de diagnostics par le même agent ne vaut pas revue indépendante.

La découverte et la falsification restent des étapes distinctes : hypothèse explicite, test minimal préenregistré, contrat figé, attaques et réponses mesurées. Une modification de stratégie ou de critères ouvre une nouvelle expérience. Corriger un bug du moteur conserve les anciennes preuves et identifie la nouvelle version. Aucune candidate survivante est une conclusion acceptable.

## État réellement disponible

| Étape | État et règle |
|---|---|
| G0 | Contrôle structurel de `G0.json` avant lecture, puis gel dans le journal. La plausibilité économique nécessite une revue ; une chaîne non vide ne la prouve pas. |
| G1 | Mesure minimale sur IS. La configuration centrale est déclarée avant mesure. Les critères chiffrés sont descriptifs, conditionnels aux coûts supposés. |
| G2 | Diagnostics disponibles sur cette configuration. Aucun verdict automatique « stratégie validée » ; une revue indépendante n'est pas simulée. |
| G3 | Sensibilités temporelles et de coûts disponibles. Les prédictions propres au mécanisme restent à vérifier explicitement. |
| G4 | **Non qualifiée.** Le bootstrap actuel mesure une sensibilité et ne peut attribuer de passage. |
| G5 | Walk-forward de recherche disponible si préenregistré. L'accès OOS reste **indisponible**. |
| G6 | Coffres historique et futur **indisponibles**, y compris par appel direct du chargeur. |
| G7 | **Indisponible.** Aucun connecteur d'ordres ni argent réel dans ce lot. |

Les portes incomplètes ne sont pas remplacées par un avertissement suivi d'une lecture. Toutes les commandes de recherche refusent OOS/VAULT avant le chargement, et le chargeur les refuse également. Un fichier local d'autorisation ne lève aucun verrou.

## Préenregistrement et gel

Chaque nouvelle expérience contient `spec.yaml` et `G0.json`. Ce dernier fixe l'empreinte complète de la spec, l'hypothèse, le mécanisme, les prédictions, le critère d'abandon, le budget exact de configurations, les paramètres centraux et un minimum de trades (au moins 100). Ce minimum est une règle de procédure, pas une preuve universelle de puissance statistique.

Le premier lancement valide et conserve le contrat avant de lire IS. Les suivants doivent retrouver exactement le même contrat pour le même identifiant d'expérience : G0, spec effective et coûts. La comparaison et l'écriture sont sérialisées. Tout changement exige un nouvel identifiant. La langue de signal n'admet que des opérations ponctuelles ; les agrégations et décalages temporels doivent être construits et vérifiés dans les features.

Un walk-forward doit être déclaré avec `"walkforward": true`. Un bootstrap doit avoir son plan dans G0 : `bootstrap` avec `sims`, `block`, `seed`, `remove_drift`. Modifier ces choix après résultats constitue une nouvelle expérience, même si l'on ne change pas la stratégie.

G1 décrit séparément : t de la configuration centrale positif, médiane de toute la grille calculable et positive, au moins le nombre de trades déclaré, et marge nette au moins trois fois le spread supposé. Les configurations non calculables restent au dénominateur. La meilleure configuration exploratoire n'est jamais utilisée comme si elle était la configuration centrale préenregistrée.

## Données et conventions de simulation

Les fenêtres sont semi-ouvertes : IS `[2017-08-17, 2023-01-01)`, OOS `[2023-01-01, 2025-09-01)`. Ces dates ne confèrent aucun droit d'accès. Le chargeur IS exige un fichier physique dédié sous `data/processed/IS/`. Il refuse l'ancien fichier mélangeant IS et OOS, toute ligne hors IS, les valeurs non finies et toute discontinuité. La préparation de ce nouveau jeu est une étape séparée ; ce lot ne lit ni ne découpe les fichiers historiques.

Les signaux sont formés à la clôture, les entrées à l'ouverture suivante. Un timeout sort à son ouverture sans utiliser le high/low ultérieur. Un stop dépassé à l'ouverture prend le prix d'ouverture défavorable. Les barres ambiguës appliquent une convention conservatrice explicitée dans le simulateur. Sans ticks, l'heure de sortie intrabar est majorée à la fin de la barre pour le portage et l'exposition. Un horizon incomplet est exclu et compté ; il n'est pas raccourci silencieusement.

Les pertes initiales participent au drawdown ; une ruine est absorbante. Les scénarios de dimensionnement sont illustratifs et calculés ex post. Les coûts restent hypothétiques, y compris la différence entre Binance spot et l'instrument éventuellement exécuté.

## Journal et provenance

`experiments/ledger.json` est désormais un **snapshot historique immuable**, pas le compteur courant. Ses affirmations sur 136 sont corrigées par [HISTORIQUE.json](experiments/HISTORIQUE.json). Le total historique unique et le nombre d'essais indépendants restent inconnus. Ils ne sont ni remis à zéro ni déduits d'une addition de comptes recouvrants.

Le journal courant est `experiments/events/*.json` : tentative commencée, contrat gelé, données liées, évaluations commencées/terminées/échouées, rapport publié, tentative terminée/échouée. Un arrêt brutal laisse un événement ouvert. Chaque rapport a un nom unique ; l'écriture refuse l'écrasement. Le rapport contient un snapshot du journal **avant sa publication et la clôture du run**, explicitement étiqueté ; l'état final s'obtient en relisant les événements.

Les comptes distinguent les évaluations IS, leurs identités descriptives, les répétitions, les simulations et les déclarations héritées. Les identités incluent paramètres, jeu de données et provenance du moteur. Aucun de ces comptes n'est présenté comme un nombre d'essais indépendants certifié pour le DSR.

Une chaîne d'empreintes, un verrou d'écriture et la conservation Git rendent les changements détectables par rapport à une base publiée. Ils ne protègent pas contre un utilisateur capable de réécrire tout le dépôt et ses règles. La CI doit comparer une base explicite et échouer si elle manque ; elle préserve les événements et le snapshot historique octet pour octet.

## Conditions restant à satisfaire

G4 exige un modèle nul explicite, une statistique et une procédure de sélection préenregistrées, une vérification des faux positifs et une précision Monte-Carlo documentée. Retirer une moyenne ne supprime pas la prévisibilité conditionnelle. Bonferroni ne nécessite pas l'indépendance lorsque les p-valeurs élémentaires sont valides ; le seuil `sqrt(2 log N)` est un autre objet. Le DSR courant reste non qualifié ; ce n'est pas une probabilité que l'avantage soit réel.

La validation finale exige une candidate, un protocole et une période admissible figés, puis un gardien isolé des agents, une ouverture atomique unique et une collecte conservant des lots immuables. Le coffre historique déjà exploré ne redevient pas vierge après chiffrement. La collecte future commencée avant le gel de la candidate ne prouve pas l'admissibilité de ses observations. Les anciens scripts de collecte/scellement sont mis hors service en attendant ce dispositif ; aucune clé ni série n'a été ouverte pour le faire.

Une éventuelle ouverture finale et toute utilisation d'argent réel exigent une décision explicite de l'utilisateur, après qualification des étapes précédentes.
