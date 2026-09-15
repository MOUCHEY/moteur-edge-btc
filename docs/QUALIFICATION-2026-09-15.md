# Première correction du socle — 15 septembre 2026

**Le socle a été corrigé et vérifié sur 102 tests synthétiques. Aucune stratégie n'est validée par cette livraison.** Les accès et méthodes encore non qualifiés restent indisponibles. La poursuite du projet ne dépend plus d'un aller-retour obligatoire avec Claude.

L'audit initial et ses résultats sont conservés sans modification dans `audits/2026-09-11-relais/`. Ses sondes démontrent les défauts de l'ancienne référence ; leur code de sortie ne sert pas de test de réussite de la nouvelle version.

## Corrections et couverture

| Sujet de l'audit | Comportement actuel | Preuve principale |
|---|---|---|
| E01–E02 : fuite de signal et contrôle incomplet | Interprète d'expressions ponctuelles, sans attributs, méthodes, indexation ni agrégation ; comparaison de plusieurs préfixes, index et NaN compris | `test_contract_synthetic.py` |
| E03–E05 : timeout, stop après gap, temps de portage | Timeout à l'open sans futur intrabar ; stop au prix d'ouverture adverse ; séries discontinues refusées ; temps intrabar majoré explicitement | `test_execution_synthetic.py` |
| E06–E07 : contrat modifiable et valeurs invalides | Spec profondément immuable, empreinte complète des champs effectifs, grilles et types validés | `test_contract_synthetic.py` |
| E08 : première perte oubliée | Capital initial inclus ; ruine absorbante ; dimensionnement et Monte-Carlo explicitement hypothétiques | `test_execution_synthetic.py` |
| C01–C02 : recouvrement et réoptimisation OOS | Fenêtres semi-ouvertes ; OOS, VAULT et chargement combiné refusés avant lecture ; IS exige un fichier dédié | `test_data_synthetic.py`, `test_research_synthetic.py` |
| C03–C05 : contournement, écrasement, compteur et échecs | Journal obligatoire, tentatives et évaluations tracées, noms de rapports uniques, publication exclusive ; historique indépendant inconnu, DSR non qualifié | `test_research_synthetic.py` |
| C06–C08 : « bruit pur », seuil insuffisant et erreurs perdues | Bootstrap descriptif, sans passage G4 ; paramètres, graines, chaque statistique et type d'erreur conservés ; volume de cotation reconstruit de façon cohérente | `test_research_synthetic.py` |
| C09 : métrique prise pour un paramètre | Paramètres issus de la grille typée d'origine, séparés des métriques | `test_research_synthetic.py` |
| Préenregistrement modifié après résultat | G0, spec et coûts figés sous le même verrou pour l'identifiant d'expérience ; un changement exige un nouvel identifiant | `test_research_synthetic.py` |
| Coffre, collecte et scellement hérités | Chemins d'accès et anciens scripts indisponibles sans clé, lecture ni réseau ; futur dispositif non prétendu implémenté | `test_data_synthetic.py`, `test_research_synthetic.py` |
| CI décorative ou historique effacé | Base de comparaison explicite obligatoire ; snapshot et événements antérieurs conservés octet pour octet ; suite synthétique exclusivement | `test_data_synthetic.py`, `ci/rejouer_local.py` |

Les intitulés et IDs se recoupent ; ils ne dénombrent pas des bugs indépendants. Les diagnostics génériques de retard et de concentration horaire ne sont plus transformés en verdicts universels de survie. Le voisinage garde les configurations non calculables dans son dénominateur. Les permutations de grappes de tailles inégales sont refusées au lieu de redimensionner les observations.

## Exécution vérifiée

Le parcours complet charge un CSV créé temporairement, applique les vrais contrôles, construit les features, simule les trades et publie un rapport avec ses événements. Les autres tests isolent les propriétés et les scénarios d'échec, dont les écritures concurrentes et les fichiers symboliques.

- [Journal exact des tests](qualification-2026-09-15/tests.log).
- [Versions, empreintes et référence du code vérifié](qualification-2026-09-15/validation.json).
- Commande : `python3 ci/rejouer_local.py --base a7fd59d28559a3e0632b4b3d775ea99d2bfcc18e`.
- Résultat local : **102 tests, aucun échec**, et conservation de l'historique vérifiée.

Les mises à jour de main jusqu'à `a7fd59d` sont intégrées, notamment les actions CI v7 et les tests historiques supplémentaires. Ces tests historiques ne sont pas exécutés ici, car certains consultent les séries réelles. L'audit ancien, le ledger hérité et les observations réservées restent préservés.

Ce journal ne certifie pas une exécution GitHub : le run distant de la contribution doit être vérifié séparément. Les preuves JSON incluent les empreintes des sources et des scripts contrôlés afin de comparer une réexécution.

## Historique et incidents conservés

Le compteur hérité n'est pas réécrit pour lui donner une précision qu'il n'a pas. Un événement `history_recorded` enregistre la correction d'interprétation : déclarations 120 et 16 avec recouvrement inconnu, neuf variantes réelles déclarées d'EXP-0000 et 600 chemins simulés déclarés. La grille de neuf est vérifiée à partir de sa spec ; les performances ne sont pas recalculées.

La revue de ce lot a repéré un gel G0 incomplet : le contrat était conservé mais pouvait être modifié entre deux lancements. Le contrôle atomique et sa non-régression ont été ajoutés. Elle a également précisé le snapshot du journal dans chaque rapport : il décrit l'instant avant publication et clôture, tandis que l'état final est porté par les événements. Les interruptions de travail n'ont déclenché aucune expérience de marché.

## Limites et prochain travail

1. Préparer et qualifier un fichier IS physiquement séparé, sans lire OOS ni les coffres ; définir une politique explicite pour les discontinuités. Le moteur les refuse actuellement.
2. Préenregistrer une hypothèse avec mécanisme et prédictions réels. Les nouveaux contrôles valident la structure du contrat, pas sa qualité scientifique.
3. Qualifier G4 : modèle nul, sélection et adaptation, précision Monte-Carlo et tests de faux positifs. Les diagnostics existants ne la remplacent pas.
4. Construire un gardien isolé et une collecte par lots immuables avant d'envisager une validation future unique. Les anciens dispositifs sont désactivés dans cette version, pas remplacés par un faux isolement local.
5. Mesurer les conditions et coûts de l'instrument effectivement exécuté avant de conclure à un résultat déployable.

Le journal local et les règles GitHub protègent contre des erreurs ordinaires et permettent une revue contre une base publiée ; un compte qui peut réécrire les mécanismes n'est pas un tiers isolé. Une nouvelle revue indépendante sera utile aux étapes décisives. Aucun coffre, clé, série réservée, collecte ou ordre réel n'a été utilisé pour cette qualification.

## Première exécution distante et correction du checkout

Le [premier run GitHub](https://github.com/MOUCHEY/moteur-edge-btc/actions/runs/35024826177) a exécuté les 102 tests : 101 ont réussi et un a rencontré un fichier absent. Le checkout restreint omettait les YAML de contrats nécessaires au test de compatibilité des specs héritées. Le workflow inclut maintenant uniquement `experiments/*/spec.yaml` en plus de sa liste existante ; aucune série de marché n'est ajoutée. Le [constat de cet échec](qualification-2026-09-15/ci-initial.json) est conservé. Les preuves locales précédentes restent inchangées et identifient leur propre référence.
